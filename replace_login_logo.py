from pathlib import Path
from datetime import datetime
import shutil
root=Path(__file__).parent
backup=root/'backups'/('logo-change-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
for name in ('login.html','login.css'):
    shutil.copy2(root/'static'/name,backup/name)
p=root/'static/login.html'
s=p.read_text(encoding='utf-8').replace('/static/brand/sopvision-logo.png','/static/brand/sopvision-logo-v2.png').replace('width="1024" height="338"','width="201" height="119"').replace('login-2','login-3')
p.write_text(s,encoding='utf-8')
p=root/'static/login.css'
s=p.read_text(encoding='utf-8')
s+="""
/* Show the supplied logo at native resolution; hide screenshot edges in the frame. */
.login-brand{width:201px;height:78px;flex-shrink:0}
.login-brand img{width:100%;height:auto;transform:translateY(-16.8%)}
@media(max-width:360px){.login-brand{width:190px;height:74px}}
"""
p.write_text(s,encoding='utf-8')
p=root/'tests/login_design.cjs'
s=p.read_text(encoding='utf-8').replace('naturalWidth === 1024','naturalWidth === 201')
p.write_text(s,encoding='utf-8')
print('New supplied logo applied to login/setup and browser icon.')
