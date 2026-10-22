import concurrent.futures, importlib.util, json, os, tempfile, threading, unittest, urllib.request, urllib.error
from pathlib import Path
spec=importlib.util.spec_from_file_location('urna',Path(__file__).parents[1]/'server.py')
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

def synthetic_cpf(seed):
    digits=list(map(int,f'{seed:09d}'))
    for size in (9,10):
        x=(sum(digits[i]*(size+1-i) for i in range(size))*10)%11
        digits.append(0 if x==10 else x)
    return ''.join(map(str,digits))

class VotingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        app.DB=str(Path(self.tmp.name)/'test.sqlite')
        app.SECRET='test-secret-only-'+('z'*40)
        app.PASSWORD='test-password-not-for-production'
        app.SESSIONS.clear()
        app.LOGIN_ATTEMPTS.clear()
        app.init()
        app.configure({'title':'Escolha da comunidade','access':'cpf','digits':2,'candidates':[{'number':'91','name':'Opção A','party':''},{'number':'92','name':'Opção B','party':''}]})
    def tearDown(self):
        self.tmp.cleanup()
    def test_cpf_validation(self):
        value=synthetic_cpf(123456780)
        self.assertEqual(app.valid_cpf(value),value)
        self.assertIsNone(app.valid_cpf('11111111111'))
        self.assertIsNone(app.valid_cpf(value[:-1]+str((int(value[-1])+1)%10)))
        self.assertIsNone(app.valid_cpf('１２３４５６７８９０１'))
    def test_status_and_results(self):
        cpf=synthetic_cpf(123456780)
        with self.assertRaises(app.Invalid):app.vote({'choice':'91','cpf':cpf})
        app.transition('start')
        with self.assertRaises(app.Invalid):app.configure({'title':'Changed','access':'cpf','digits':2,'candidates':[{'number':'91','name':'A'},{'number':'92','name':'B'}]})
        app.vote({'choice':'91','cpf':cpf})
        app.vote({'choice':'branco','cpf':synthetic_cpf(123456781)})
        app.vote({'choice':'99','cpf':synthetic_cpf(123456782)})
        self.assertNotIn('totals',app.state())
        app.transition('close')
        self.assertEqual(app.state()['totals'],{'91':1,'branco':1,'nulo':1})
        with self.assertRaises(app.Invalid):app.vote({'choice':'92','cpf':synthetic_cpf(123456783)})
        with self.assertRaises(app.Invalid):app.transition('start')
        app.init()
        self.assertEqual(app.state()['status'],'closed')
        self.assertEqual(app.state()['totals']['91'],1)
    def test_duplicate_cpf_atomic(self):
        app.transition('start')
        cpf=synthetic_cpf(234567890)
        def submit(_):
            try:app.vote({'choice':'91','cpf':cpf});return True
            except app.Invalid:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            self.assertEqual(sum(pool.map(submit,range(20))),1)
        app.transition('close')
        self.assertEqual(app.state()['totals'],{'91':1})
        with app.connect() as c:
            cols={r[1] for r in c.execute('PRAGMA table_info(credentials)')}
            self.assertEqual(cols,{'digest','used'})
            row=c.execute('SELECT digest FROM credentials').fetchone()[0]
            self.assertNotEqual(row,cpf)
            self.assertEqual(len(row),64)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM credentials').fetchone()[0],1)
    def test_invalid_vote_does_not_consume_cpf(self):
        app.transition('start')
        cpf=synthetic_cpf(345678900)
        for choice in ('9','invalid','<script>'):
            with self.assertRaises(app.Invalid):app.vote({'choice':choice,'cpf':cpf})
        app.vote({'choice':'92','cpf':cpf})
        with self.assertRaises(app.Invalid):app.vote({'choice':'91','cpf':cpf})
    def test_admin_http_permissions(self):
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        origin=f'http://127.0.0.1:{server.server_port}'
        app.ORIGIN=origin
        def request(path,data=None,headers=None):
            h={'Origin':origin,'Content-Type':'application/json'};h.update(headers or {})
            req=urllib.request.Request(origin+path,data=json.dumps(data).encode() if data is not None else None,headers=h)
            try:
                with urllib.request.urlopen(req) as r:return r.status,json.load(r),r.headers
            except urllib.error.HTTPError as e:return e.code,json.load(e),e.headers
        try:
            self.assertEqual(request('/api/admin')[0],401)
            self.assertEqual(request('/api/start',{})[0],401)
            self.assertEqual(request('/api/login',{'password':app.PASSWORD},{'Origin':'https://untrusted.example'})[0],403)
            self.assertEqual(request('/api/login',{'password':'incorrect'})[0],401)
            code,body,headers=request('/api/login',{'password':app.PASSWORD})
            self.assertEqual(code,200)
            cookie=headers['Set-Cookie'].split(';')[0]
            h={'Cookie':cookie}
            self.assertEqual(request('/api/start',{},h)[0],403)
            code,body,_=request('/api/admin',headers=h)
            self.assertEqual(code,200)
            h['X-CSRF-Token']=body['csrf']
            self.assertEqual(request('/api/start',{},h)[0],200)
            self.assertEqual(request('/api/state')[1]['status'],'open')
            self.assertEqual(request('/api/close',{},h)[0],200)
            self.assertEqual(request('/api/logout',{},h)[0],200)
            self.assertEqual(request('/api/admin',headers=h)[0],401)
            self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
        finally:
            server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
