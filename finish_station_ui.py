from pathlib import Path
p=Path('static/worker.js');s=p.read_text(encoding='utf-8')
s=s.replace("$('currentOperator').textContent='พนักงาน '+operator;","$('currentOperator').textContent=window.Auth?.account?.guest?'สถานี '+station_id:'พนักงาน '+operator;")
p.write_text(s,encoding='utf-8')
p=Path('tests/access_ui.cjs');s=p.read_text(encoding='utf-8').replace("assert(await page.locator('#operator').inputValue()==='browseradmin');","assert(await page.locator('#operator').inputValue()==='STATION-1');assert(!(await page.locator('#operator').isVisible()));")
p.write_text(s,encoding='utf-8')
p=Path('README.md');s=p.read_text(encoding='utf-8')
s+="""

## หน้าพนักงานไม่ต้องล็อกอิน
- เปิด /worker หรือ /worker?station=2 ได้โดยตรง เลือกสถานีแล้วเปิดกล้องสแกนงาน ไม่ต้องมีบัญชีหรือกรอกรหัสพนักงาน
- ระบบสร้างเซสชันสถานีให้อัตโนมัติแยกแต่ละเบราว์เซอร์ ใช้ CSRF และจำกัดการอ่าน/แก้ไขเฉพาะงานและกล้องของเซสชันนั้น ไม่ได้เปิด API แอดมินให้สาธารณะ
- ช่องประวัติแสดงงานของเซสชันนี้ในสถานีที่เลือก พนักงานคนอื่นในคนละเครื่องเริ่มทำสถานีถัดไปได้เมื่อ QR ผ่าน SOP จากสถานีก่อนหน้าแล้ว
- บันทึกผู้ปฏิบัติงานเป็นรหัสเซสชันสถานีอัตโนมัติ ไม่อ้างว่าเป็นตัวตนพนักงานจริง แอดมินยังดูรวมทุกสถานีและส่งออกรายงานได้
- หน้า /admin, /access, รายงาน, การแก้ SOP และการอนุมัติตรวจซ้ำยังต้องเข้าสู่ระบบและมีสิทธิ์เหมือนเดิม
"""
p.write_text(s,encoding='utf-8')
print('Station-only labels and documentation updated')
