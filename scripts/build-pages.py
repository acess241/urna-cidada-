"""Empacota somente a interface pública; não inclui banco, Python ou segredos de servidor."""
import json,os,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=root/'pages-dist'
if out.exists():shutil.rmtree(out)
out.mkdir()
defaults=json.loads((root/'public'/'supabase-public.json').read_text())
url=(os.environ.get('SUPABASE_URL') or defaults['url']).rstrip('/')
key=os.environ.get('SUPABASE_ANON_KEY') or defaults['key']
if not url.startswith('https://') or not key:
    raise SystemExit('Configure SUPABASE_URL e SUPABASE_ANON_KEY antes de publicar.')
for name in ('index.html','admin.html','app.js','style.css','supabase-adapter.js'):
    content=(root/'public'/name).read_text()
    if name.endswith('.html'):
        content=content.replace('href="/admin"','href="./admin.html"').replace('href="/"','href="./"').replace('href="/style.css"','href="./style.css"')
        content=content.replace('<script src="/app.js"></script>','<script src="./config.js"></script><script src="./supabase-adapter.js"></script><script src="./app.js"></script>')
        if name=='admin.html':
            content=content.replace('<label for="password">','<label for="adminEmail">E-mail do administrador</label><input id="adminEmail" type="email" required autocomplete="username"><label for="password">')
            content=content.replace('minlength="16"','minlength="1"')
            content=content.replace('Administração protegida por senha e sessão temporária.','Administração pelo Supabase Auth. Recarregar a página exige novo login.')
    (out/name).write_text(content)
(out/'config.js').write_text('window.urnaSupabase='+json.dumps({'url':url,'key':key})+';\n')
(out/'.nojekyll').touch()
print('Interface preparada em pages-dist/.')
