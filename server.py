"""Urna comunitária: totais agregados, sem cédulas individuais no banco."""
import hashlib, hmac, json, os, secrets, sqlite3, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from http.cookies import SimpleCookie

ROOT = Path(__file__).parent
DB = os.environ.get('DATABASE_PATH', str(ROOT / 'data' / 'urna.sqlite'))
ORIGIN = os.environ.get('PUBLIC_URL', 'https://' + os.environ['RAILWAY_PUBLIC_DOMAIN'] if os.environ.get('RAILWAY_PUBLIC_DOMAIN') else 'http://localhost:8080').rstrip('/')
PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
SECRET = os.environ.get('APP_SECRET', '')
SESSIONS = {}
LOCK = threading.Lock()
LOGIN_ATTEMPTS = []

class Invalid(Exception):
    pass

def connect():
    c = sqlite3.connect(DB, timeout=20, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=20000')
    return c

def init():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS election(id INTEGER PRIMARY KEY CHECK(id=1), title TEXT NOT NULL, status TEXT NOT NULL, access TEXT NOT NULL, digits INTEGER NOT NULL);
        INSERT OR IGNORE INTO election VALUES(1,'Minha votação','draft','cpf',2);
        CREATE TABLE IF NOT EXISTS candidates(number TEXT PRIMARY KEY, name TEXT NOT NULL, party TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS totals(choice TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS credentials(digest TEXT PRIMARY KEY, used INTEGER NOT NULL DEFAULT 0);
        ''')

def valid_cpf(value):
    if not isinstance(value,str) or len(value)>20:
        return None
    value=''.join(ch for ch in value if ch not in '.- ')
    if not value.isascii() or not value.isdigit() or len(value)!=11 or len(set(value))==1:
        return None
    for size in (9,10):
        check=(sum(int(value[i])*(size+1-i) for i in range(size))*10)%11
        if check==10:
            check=0
        if int(value[size])!=check:
            return None
    return value

def digest(code):
    return hmac.new(SECRET.encode(), code.strip().upper().encode(), hashlib.sha256).hexdigest()

def state(admin=False):
    with connect() as c:
        e = dict(c.execute('SELECT * FROM election').fetchone())
        e.pop('id')
        e['candidates'] = [dict(r) for r in c.execute('SELECT * FROM candidates ORDER BY number')]
        if e['status'] == 'closed':
            e['totals'] = {r['choice']: r['count'] for r in c.execute('SELECT * FROM totals')}
        return e

def configure(data):
    title = str(data.get('title','')).strip()
    access = data.get('access')
    digits = data.get('digits')
    candidates = data.get('candidates')
    if not 1 <= len(title) <= 100 or access != 'cpf' or type(digits) is not int or not 2 <= digits <= 5:
        raise Invalid('Informe título, acesso e de 2 a 5 dígitos.')
    if not isinstance(candidates, list) or not 2 <= len(candidates) <= 100:
        raise Invalid('Cadastre entre 2 e 100 candidatos.')
    rows, numbers = [], set()
    for item in candidates:
        n, name, party = (str(item.get(k,'')).strip() for k in ('number','name','party'))
        if not n.isascii() or not n.isdigit() or len(n)!=digits or n in numbers or not 1<=len(name)<=80 or len(party)>60:
            raise Invalid('Confira os candidatos: números únicos, tamanho correto e nomes preenchidos.')
        numbers.add(n)
        rows.append((n,name,party))
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            if c.execute('SELECT status FROM election').fetchone()[0] != 'draft':
                raise Invalid('Candidatos e regras ficam bloqueados após a abertura.')
            c.execute('UPDATE election SET title=?, access=?, digits=?', (title, access, digits))
            c.execute('DELETE FROM candidates')
            c.executemany('INSERT INTO candidates VALUES(?,?,?)',rows)
            c.execute('COMMIT')
        except:
            c.execute('ROLLBACK')
            raise

def transition(action):
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            e=c.execute('SELECT * FROM election').fetchone()
            if action=='start':
                if e['status']!='draft' or c.execute('SELECT COUNT(*) FROM candidates').fetchone()[0]<2:
                    raise Invalid('Salve ao menos dois candidatos antes de abrir.')
                c.execute("UPDATE election SET status='open'")
            elif action=='close':
                if e['status']!='open':
                    raise Invalid('A votação não está aberta.')
                c.execute("UPDATE election SET status='closed'")
            else:
                raise Invalid('Ação inválida.')
            c.execute('COMMIT')
        except:
            c.execute('ROLLBACK')
            raise

def vote(data):
    value, code = data.get('choice'), data.get('code','')
    if not isinstance(value,str) or not isinstance(code,str) or len(code)>100:
        raise Invalid('Voto inválido.')
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            e=c.execute('SELECT * FROM election').fetchone()
            if e['status']!='open':
                raise Invalid('A votação não está aberta.')
            if value!='branco' and (not value.isascii() or not value.isdigit() or len(value)!=e['digits']):
                raise Invalid('Complete o número ou escolha BRANCO.')
            if e['access']=='cpf':
                cpf=valid_cpf(data.get('cpf'))
                if not cpf:
                    raise Invalid('CPF inválido. Confira os 11 dígitos.')
                try:
                    c.execute('INSERT INTO credentials(digest,used) VALUES(?,1)',(digest(cpf),))
                except sqlite3.IntegrityError:
                    raise Invalid('Não foi possível autorizar: CPF já utilizado nesta votação.')
            choice=value if value=='branco' or c.execute('SELECT 1 FROM candidates WHERE number=?',(value,)).fetchone() else 'nulo'
            c.execute('INSERT INTO totals(choice,count) VALUES(?,1) ON CONFLICT(choice) DO UPDATE SET count=count+1',(choice,))
            c.execute('COMMIT')
        except:
            c.execute('ROLLBACK')
            raise

class Handler(BaseHTTPRequestHandler):
    # Não registrar endereços IP, códigos ou conteúdo de requisições.
    def log_message(self,*args):
        pass

    def respond(self,status,data,ctype='application/json; charset=utf-8',cookie=None):
        body=json.dumps(data,ensure_ascii=False).encode() if ctype.startswith('application/json') else data
        self.send_response(status)
        self.send_header('Content-Type',ctype)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie',cookie)
        self.end_headers()
        self.wfile.write(body)

    def session(self):
        try:
            cookie=SimpleCookie(self.headers.get('Cookie',''))
            sid=cookie['admin'].value
        except (KeyError,ValueError):
            return None
        with LOCK:
            s=SESSIONS.get(sid)
            return s if s and s['expires']>time.time() else None

    def do_GET(self):
        path=self.path.split('?')[0]
        if path=='/api/state':
            return self.respond(200,state())
        if path=='/api/admin':
            session=self.session()
            return self.respond(200,{'state':state(True),'csrf':session['csrf']}) if session else self.respond(401,{'error':'Entre como administrador.'})
        files={'/':('index.html','text/html; charset=utf-8'),'/admin':('admin.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
        if path not in files:
            return self.respond(404,{'error':'Página não encontrada.'})
        name,ctype=files[path]
        return self.respond(200,(ROOT/'public'/name).read_bytes(),ctype)

    def do_POST(self):
        try:
            if self.headers.get('Origin')!=ORIGIN:
                return self.respond(403,{'error':'Origem não permitida.'})
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=65536 or 'application/json' not in self.headers.get('Content-Type',''):
                return self.respond(400,{'error':'Envie JSON de até 64 KB.'})
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict):
                raise Invalid('Dados inválidos.')
            path=self.path
            if path=='/api/login':
                with LOCK:
                    now=time.time()
                    LOGIN_ATTEMPTS[:]=[t for t in LOGIN_ATTEMPTS if t>now-60]
                    if len(LOGIN_ATTEMPTS)>=10:
                        return self.respond(429,{'error':'Muitas tentativas. Aguarde um minuto.'})
                    LOGIN_ATTEMPTS.append(now)
                if not isinstance(data.get('password'),str) or not hmac.compare_digest(data['password'].encode(),PASSWORD.encode()):
                    return self.respond(401,{'error':'Senha inválida.'})
                sid,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
                with LOCK:
                    for key in list(SESSIONS):
                        if SESSIONS[key]['expires']<time.time():
                            del SESSIONS[key]
                    SESSIONS[sid]={'csrf':csrf,'expires':time.time()+3600}
                secure='; Secure' if ORIGIN.startswith('https://') else ''
                return self.respond(200,{'ok':True},cookie=f'admin={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600{secure}')
            if path=='/api/vote':
                vote(data)
                return self.respond(200,{'ok':True})
            session=self.session()
            if not session:
                return self.respond(401,{'error':'Entre como administrador.'})
            if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf']):
                return self.respond(403,{'error':'Sessão inválida. Recarregue a página.'})
            if path=='/api/configure':
                configure(data)
            elif path in ('/api/start','/api/close'):
                transition(path.rsplit('/',1)[1])
            elif path=='/api/logout':
                with LOCK:
                    for sid,s in list(SESSIONS.items()):
                        if s is session:
                            del SESSIONS[sid]
                return self.respond(200,{'ok':True},cookie='admin=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            else:
                return self.respond(404,{'error':'Rota inexistente.'})
            return self.respond(200,{'ok':True})
        except (Invalid,ValueError,TypeError,AttributeError) as e:
            return self.respond(400,{'error':str(e) if isinstance(e,Invalid) else 'Dados inválidos.'})
        except Exception:
            return self.respond(500,{'error':'Falha ao processar. Não repita o voto automaticamente; consulte o administrador.'})

if __name__=='__main__':
    if len(PASSWORD)<16 or len(SECRET)<32:
        raise SystemExit('Configure ADMIN_PASSWORD com pelo menos 16 caracteres e APP_SECRET com pelo menos 32 caracteres.')
    init()
    ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8080'))),Handler).serve_forever()
