from pathlib import Path
def edit(name,old,new):
 p=Path(name);s=p.read_text(encoding='utf-8');assert old in s,name+old[:60];p.write_text(s.replace(old,new),encoding='utf-8')
edit('reporting.py',"""OR id LIKE ? ESCAPE '\\\\')""","""OR id LIKE ? ESCAPE '\\\\' OR qr IN (SELECT qr FROM flow_jobs WHERE source_qr LIKE ? ESCAPE '\\\\'))""")
edit('reporting.py',"params.extend(['%' + literal + '%'] * 3)","params.extend(['%' + literal + '%'] * 4)")
edit('reporting.py',"WHERE qr IS NULL OR qr IN (SELECT qr FROM flow_jobs WHERE is_test=0) ORDER BY created_at","WHERE qr IS NULL OR qr NOT IN (SELECT qr FROM flow_jobs WHERE is_test=1) ORDER BY created_at")
edit('production.py',"row['test_run_id']=job['test_run_id'] if job else None","""row['test_run_id']=job['test_run_id'] if job else None
    with db.connect() as c:
        review=c.execute('SELECT r.status,r.decision,r.reason,r.reviewed_at,u.username reviewer FROM supervisor_reviews r LEFT JOIN users u ON u.id=r.reviewer_id WHERE attempt_id=?',(row['id'],)).fetchone()
    row['review']=dict(review) if review else None""")
edit('reporting.py',"r.get('test_run_id') or '']","r.get('test_run_id') or '',r.get('rework_of') or '',(r.get('review') or {}).get('decision') or '',(r.get('review') or {}).get('reviewer') or '',(r.get('review') or {}).get('reason') or '']")
edit('reporting.py',"'รอบทดสอบ']","'รอบทดสอบ','ตรวจซ้ำจากรอบงาน','ผลพิจารณา','ผู้พิจารณา','เหตุผลการพิจารณา']")
# Preserve current source-specific UI and accurately explain the detector.
edit('static/worker.html','ระบบนี้ยังตรวจสี ไม่ได้ตรวจท่าทางการประกอบจริง','ระบบใช้สีร่วมกับกรอบตำแหน่ง ขนาด รูปร่าง และลำดับเวลา ต้องตั้งค่าให้ตรงชิ้นงาน และทดสอบกับงานจริงก่อนยืนยันความแม่นยำ')
edit('static/admin.html','id="scopeFilter" aria-label=','id="scopeFilter" class="flow-input" aria-label=')
p=Path('README.md');s=p.read_text(encoding='utf-8')
s=s.replace('หน้าแอดมินยังมีข้อจำกัดเรื่อง Login/Role ของโปรเจกต์เดิม','หน้าแอดมินตรวจสิทธิ์จาก session ของผู้ใช้')
s=s.replace('แต่ยังไม่มี Login/Role หรือการเชื่อม MES/ERP ภายนอก','มี Login/Role และคิวอนุมัติตรวจซ้ำ แต่ยังไม่มีการเชื่อม MES/ERP ภายนอก')
s=s.replace('ระบบนี้ยังไม่มี Login/Role จึงใช้ในเครือข่ายทดสอบส่วนตัวเท่านั้น','ระบบนี้มี Login/Role แล้ว ใบรับรองนี้ใช้สำหรับเครือข่ายทดสอบส่วนตัว')
s=s.replace('ปัจจุบันยัง **ไม่มี Login/Role/การรับรอง QR ต้นทาง**','ปัจจุบันมี **Login/Role และ audit การอนุมัติตรวจซ้ำ** แต่ยัง **ไม่มีการรับรอง QR ต้นทาง**')
s=s.replace('ต้องเพิ่มบัญชีผู้ใช้จริง, ','')
s=s.replace('ผู้ส่งออกรายงานมีสิทธิ์เข้าถึงหน้าแอดมินเดิม ระบบต้นแบบยังไม่มี authentication หรือ role-based access control','ผู้ส่งออกรายงานต้องเข้าสู่ระบบด้วยสิทธิ์แอดมิน หัวหน้างาน หรือ QC; พนักงานไม่สามารถเรียก API รายงานหรือข้อมูลของผู้อื่นได้')
s+="""

## บัญชีผู้ใช้ โหมดทดสอบ และการตรวจซ้ำ
- ครั้งแรกเปิดเซิร์ฟเวอร์ แล้วดับเบิลคลิก setup_admin.bat บนคอมเครื่องนี้ จะเปิดแบบฟอร์มสร้างแอดมินพร้อมรหัสตั้งค่าครั้งเดียว ให้เจ้าของระบบตั้งชื่อและรหัสผ่านเอง (อย่างน้อย 10 ตัวอักษร) ไม่มีรหัสผ่านเริ่มต้น รหัสตั้งค่าถูกลบหลังสร้างสำเร็จ
- แอดมินสร้าง/เปิด/ปิดบัญชีได้ที่ /access; ปิดบัญชีตนเองหรือแอดมินคนสุดท้ายไม่ได้ การปิดบัญชีเพิกถอน session ทันที
- พนักงานตรวจและดูประวัติงานของบัญชีตนเอง ระบบใช้ชื่อบัญชีเป็นรหัสผู้ปฏิบัติงาน; QC ดูรายงาน หลักฐาน และยืนยันแยกพัก; หัวหน้างานเพิ่มสิทธิ์อนุมัติให้ตรวจซ้ำ; แอดมินเพิ่มสิทธิ์จัดการบัญชีและ SOP
- Session 8 ชั่วโมง ใช้ cookie HttpOnly/SameSite Strict และ Secure เมื่อผ่าน HTTPS; คำขอแก้ไขต้องมี CSRF token; รหัสผ่านเก็บเป็น PBKDF2 hash และจำกัดการลองเข้าสู่ระบบผิด
- เลือกโหมดทดสอบที่หน้าตรวจงาน สร้างรอบใหม่เพื่อใช้ QR เดิมเริ่มที่สถานี 1 ได้อีกครั้ง ทุกสถานีต้องเลือกรอบเดียวกัน ขณะมีงานหรือคำขอค้างจะเปลี่ยนรอบไม่ได้
- ยอดหน้าแรกและรายงานเริ่มต้นนับผลิตจริงเท่านั้น หน้าแอดมินเลือกผลิตจริง/ทดสอบ/ทั้งหมดได้ ตัวกรองเดียวกันใช้กับ CSV และรายงานพิมพ์ รวมรหัส QR ที่อ่านได้ รหัสภายใน รอบทดสอบ และข้อมูลพิจารณาตรวจซ้ำ
- งานแยกพัก/หยุดกลางงานที่ปิดแล้วเข้าคิว /access; หัวหน้า/แอดมินอนุมัติตรวจซ้ำพร้อมเหตุผลอย่างน้อย 10 ตัวอักษร ผลเดิมไม่ถูกแก้เป็นผ่าน รอบใหม่เชื่อม rework_of กับรอบเดิม และต้องตรวจ SOP ใหม่ครบก่อนส่งต่อ
- หากไม่ได้รับภาพตรวจเกิน 45 วินาที เซิร์ฟเวอร์แยกพักงาน บันทึก connection_timeout เก็บหลักฐาน และส่งเข้าคิว การอัปโหลดวิดีโอเพียงอย่างเดียวไม่นับว่าได้รับภาพตรวจ
- ปุ่มออกจากระบบอยู่บนแถบผู้ใช้ทุกหน้า การเปิดหน้ากล้องบน iPhone ต้องเข้าสู่ระบบผ่าน HTTPS และอนุญาตกล้องบน Safari
- ตรวจอัตโนมัติด้วย tests รวมสิทธิ์/CSRF, การเพิกถอน session, test rounds, supervisor review, watchdog และ browser UI ผ่าน Edge ด้วยกล้องจำลอง การทดสอบนี้ไม่แทนการวัดความแม่นยำกับชิ้นงานจริง/มือบัง/ความเร็วจริง
"""
p.write_text(s,encoding='utf-8');print('Search, audit report columns and docs updated')
