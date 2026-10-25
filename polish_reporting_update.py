from pathlib import Path
root=Path(__file__).resolve().parent
p=root/'static/app.js';s=p.read_text(encoding='utf-8')
old="const timeDate=s=>{try{return new Date(s).toLocaleString('th-TH',{dateStyle:'short',timeStyle:'short',timeZone:'Asia/Bangkok'})}catch{return s}};"
new="const timeDate=s=>{try{return new Date(/(?:Z|[+-]\\d\\d:\\d\\d)$/.test(s)?s:s.replace(' ','T')+'Z').toLocaleString('th-TH',{dateStyle:'short',timeStyle:'short',timeZone:'Asia/Bangkok'})}catch{return s}};"
assert s.count(old)==1;s=s.replace(old,new)
# Distinguish running, quarantined and interrupted production records everywhere.
label="({active:'กำลังทำ',passed:'ผ่านสถานี',blocked:'แยกพัก',interrupted:'หยุดกลางงาน'})[r.state]"
s=s.replace("${r.status==='pass'?'ผ่าน':r.status==='running'?'กำลังทำ':'ต้องตรวจสอบ'}","${r.mode==='flow'?"+label+":r.status==='pass'?'ผ่าน':r.status==='running'?'กำลังทำ':'ต้องตรวจสอบ'}")
s=s.replace("${ok?'ผ่าน SOP':'ต้องตรวจสอบ'}","${r.mode==='flow'?"+label+":ok?'ผ่าน SOP':'ต้องตรวจสอบ'}")
p.write_text(s,encoding='utf-8')
p=root/'static/production.js';s=p.read_text(encoding='utf-8')
s+="""
let flowLookupBusy=false;
setInterval(async()=>{
  if(document.hidden||FLOW.work||FLOW.submitting||flowLookupBusy||!document.getElementById('view-flow')?.classList.contains('active')||!document.getElementById('flowQr')?.value.trim())return;
  flowLookupBusy=true;try{await flowLookup();}finally{flowLookupBusy=false;}
},3000);
"""
p.write_text(s,encoding='utf-8')
p=root/'static/admin.js';s=p.read_text(encoding='utf-8')
s=s.replace("new Date($(id).value+':00+07:00').toISOString()","new Date($(id).value+($(id).value.length===16?':00':'')+'+07:00').toISOString()")
p.write_text(s,encoding='utf-8')
p=root/'README.md';s=p.read_text(encoding='utf-8')
s+="""

## รายงานแอดมินและข้อมูลตรงกันทุกหน้า
- หน้าแรกนับงานผลิต QR จาก read model เดียวกับ /api/flow/admin ส่วนประวัติรวม /api/records แยกประเภทงานผลิตกับ Live/Upload อิสระชัดเจน ไม่ถือว่ารายงานอัปโหลดปลดล็อกงานผลิต
- หน้าพนักงานอ่านประวัติจริงจากฐานข้อมูล กรองรหัสพนักงานแบบตรงตัวและสถานี แสดง 15 รอบล่าสุด ยอดรวมเป็นทั้งหมดที่ตรงกับพนักงาน/สถานีนั้น และไม่หายเมื่อรีเฟรช
- หน้าแอดมินกรองคำค้น สถานี สถานะ และช่วงเวลาไทย ยอดการ์ดตามตัวกรอง พร้อมส่งออก CSV UTF-8 BOM สำหรับ Excel และ HTML สำหรับพิมพ์เป็น PDF แบบ A4 แนวนอน
- ส่งออกทุกหน้าที่ตรงกับตัวกรอง ไม่จำกัดเฉพาะ 50 แถวที่เปิดอยู่ รายงานเกิน 50,000 แถวจะปฏิเสธอย่างชัดเจนให้จำกัดช่วงเวลา ไม่ตัดข้อมูลทิ้งเงียบ ๆ
- CSV ป้องกัน formula injection; HTML escape ข้อมูลที่ผู้ใช้กรอก รวมเวลา +07:00 และเวลาสร้างรายงาน สถานะขั้นตอนเป็นผลที่บันทึกไว้ ไม่ประเมินใหม่ด้วย SOP ปัจจุบัน
- ตัวเลขอาจเปลี่ยนระหว่างการเปิดหน้าและกดส่งออกหากมีงานใหม่เข้ามา ให้เทียบตัวกรองและเวลาสร้างข้อมูล แต่ละ response อ่าน SQLite ภายใน transaction เดียว
- การส่งออกรายงานใช้สิทธิ์เข้าถึงหน้าแอดมินเดิม ระบบต้นแบบยังไม่มี authentication หรือ role-based access control
"""
p.write_text(s,encoding='utf-8')
print('Parity labels, Thai dates, QR auto-refresh and reporting documentation updated')
