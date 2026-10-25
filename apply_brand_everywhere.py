from pathlib import Path
from datetime import datetime
import re,shutil
root=Path(__file__).parent
backup=root/'backups'/('brand-all-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
logo='/static/brand/sopvision-logo-current.png?v=brand-4'
img=f'<img class="brand-image" src="{logo}" width="1024" height="338" alt="SOPVision AI — Intelligent Inspection">'
for p in (root/'static').glob('*.html'):
    shutil.copy2(p,backup/p.name)
    s=p.read_text(encoding='utf-8')
    s=re.sub(r'<link[^>]+rel="icon"[^>]*>','',s)
    s=s.replace('</head>',f'<link rel="icon" type="image/png" href="{logo}"><link rel="stylesheet" href="/static/brand.css?v=brand-4"></head>')
    s=re.sub(r'/static/brand/sopvision-logo(?:-v2)?\.png',logo,s)
    if p.name=='login.html':
        s=re.sub(r'<img src="[^"]+" width="201" height="119" alt="SOPVision AI[^"]*">',img,s)
        s=s.replace('<span>SOPVISION AI</span>',f'<span class="form-footer-brand">{img}</span>')
    if p.name in ('worker.html','admin.html','access.html'):
        s=s.replace('SOP<span>VISION</span> AI',img)
    if p.name=='index.html':
        old='<div class="brand"><div class="brand-logo"><svg class="icon"><use href="#ic-spark"/></svg></div><div><div class="brand-title">SOP<span>VISION</span><sup>AI</sup></div><div class="brand-sub">INTELLIGENT INSPECTION</div></div></div>'
        assert old in s
        s=s.replace(old,f'<a class="brand workspace-brand" href="/" aria-label="SOPVision AI หน้าแรก">{img}</a>')
        s=s.replace('<span>SOPVISION AI <span class="footer-accent">/</span> INDUSTRIAL QUALITY LAB</span>',f'<span class="footer-brand">{img}<span class="footer-accent">/</span> INDUSTRIAL QUALITY LAB</span>')
    p.write_text(s,encoding='utf-8')
p=root/'reporting.py';shutil.copy2(p,backup/p.name)
s=p.read_text(encoding='utf-8')
old="    html='''<!doctype html><html lang=\"th\"><meta charset=\"utf-8\">"
new="""    # Embed the current logo so saved/printed reports retain the same brand offline.
    from pathlib import Path
    from base64 import b64encode
    logo_data=b64encode((Path(__file__).parent/'static/brand/sopvision-logo-current.png').read_bytes()).decode('ascii')
    report_brand='<img alt="SOPVision AI — Intelligent Inspection" width="220" height="73" style="display:block;object-fit:contain;margin:0 0 16px" src="data:image/png;base64,'+logo_data+'">'
    html='''<!doctype html><html lang="th"><meta charset="utf-8">"""
assert old in s;s=s.replace(old,new)
old="    html+='<p>สร้างเมื่อ '"
assert old in s;s=s.replace(old,"    html=html.replace('<h1>',report_brand+'<h1>',1)\n"+old)
p.write_text(s,encoding='utf-8')
p=root/'tests/login_design.cjs';s=p.read_text(encoding='utf-8').replace('naturalWidth === 201','naturalWidth === 1024');p.write_text(s,encoding='utf-8')
print('Shared logo applied across all 5 HTML pages, footers, icons and printable reports.')
