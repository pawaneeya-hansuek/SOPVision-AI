"""Use concise task-focused Thai in the existing interface."""
from pathlib import Path
from datetime import datetime
import re,shutil
root=Path(__file__).parent
backup=root/'backups'/('plain-language-'+datetime.now().strftime('%Y%m%d-%H%M%S'));backup.mkdir(parents=True)
for p in (root/'static').iterdir():
    if p.suffix in ('.html','.js','.css'):shutil.copy2(p,backup/p.name)
labels={
 'QUALITY CONTROL CENTER':'ตรวจสอบงาน',
 'ทุกการตัดสินใจ มีหลักฐาน':'งานรอพิจารณา',
 'อนุมัติให้เริ่มตรวจใหม่ได้ โดยเก็บผลที่ไม่ผ่านและเหตุการณ์เดิมไว้ครบถ้วน':'ตรวจผลและหลักฐานก่อนอนุมัติให้ตรวจซ้ำ',
 'ADMIN / PRODUCTION MONITOR':'ผู้ดูแลระบบ',
 'PRODUCTION / ADMIN WORKSPACE':'งานผลิต',
 'ข้อมูลจากการสแกนและตรวจงานของพนักงาน อัปเดตจากฐานข้อมูลทุก 2 วินาที':'ดูผลตรวจแต่ละสถานีและส่งออกรายงาน',
 'กำลังอ่านข้อมูลจากเซิร์ฟเวอร์…':'กำลังโหลดข้อมูล…',
 'ภาพสดประมาณ 4 ภาพ/วินาที จากทุกหน้าที่เปิดกล้องในระบบ แม้ยังไม่เริ่มชิ้นงาน · เมื่อหยุดส่ง ภาพจะมีสถานะออฟไลน์':'แสดงกล้องที่เปิดอยู่ หากไม่ได้รับภาพจะแสดงว่าออฟไลน์',
 'UNIFIED WORK HISTORY':'ประวัติงาน',
 'ค้นประวัติงานรวมด้วย QR':'ค้นประวัติจาก QR',
 'ข้อมูลเก่าที่ไม่มี QR อ้างอิงจะไม่ถูกจับคู่โดยคาดเดา':'กรอก QR หรือรหัสรอบงานเพื่อค้นหา',
 'ยอดงานผลิตและรายงานใช้ตัวกรองเดียวกัน · ส่งออกครบทุกหน้าของรายการที่ตรงตัวกรอง':'รายงานจะรวมทุกรายการตามตัวกรองที่เลือก',
 'PRODUCTION RECORDS':'รายการงาน',
 'รายการงานของพนักงาน':'รายการตรวจงาน',
 'CAMERA ARCHIVE':'วิดีโอย้อนหลัง',
 'ดูกล้องย้อนหลังตลอดช่วงเปิดกล้อง':'วิดีโอกล้องย้อนหลัง',
 'ยอดนับแยก “รอบงานแต่ละสถานี” กับ “ชิ้นงานที่ผ่านครบทุกสถานี” · แยกสิทธิ์ผู้ใช้และบันทึกการอนุมัติตรวจซ้ำแล้ว · ยอดเริ่มต้นแสดงเฉพาะผลิตจริง':'รอบงานนับแยกตามสถานี ส่วนชิ้นงานเสร็จสมบูรณ์ต้องผ่านครบทุกสถานี',
 'WORKSPACE':'เมนูหลัก','Prototype mode':'ก่อนเริ่มงาน',
 'ทดสอบกับชิ้นงานสีจำลองก่อนใช้งานกับกระบวนการจริง':'ตรวจแสงและตำแหน่งกล้องให้ตรงกับค่าตั้ง',
 'SYSTEM READY':'พร้อมใช้งาน','v0.1 MVP':'v1.0',
 'OPERATIONS':'งานผลิต','OVERVIEW':'ภาพรวม',
 'FACTORY INTELLIGENCE / DASHBOARD':'ภาพรวมงานผลิต',
 'SOPVISION · ASSEMBLY WORKSPACE':'งานผลิต 3 สถานี',
 'ตรวจงานเป็นขั้นตอน':'ภาพรวมงานผลิต',
 'ส่งต่องานอย่างมั่นใจ':'สถานะและผลตรวจล่าสุด',
 'สแกนใบงาน ตรวจลำดับ SOP และดูหลักฐานย้อนหลังได้ในที่เดียว เริ่มต้นง่าย ๆ จากรหัส QR ของงาน':'เลือกสถานี สแกน QR และตรวจงานตามขั้นตอน',
 'VISION ANALYSIS':'ภาพตัวอย่าง','OBJECT DETECTED':'ตัวอย่างชิ้นงาน',
 'ยอดงานผลิตรวมทุกสถานี ตรงกับหน้าแอดมินเมื่อไม่ใช้ตัวกรอง · ประวัติด้านล่างแยกรอบงาน QR กับการตรวจอิสระ':'ยอดผลิตจริงรวมทุกสถานี ไม่รวมรอบทดสอบ',
 'PRODUCTION JOBS':'','PASSED STATION ATTEMPTS':'','QUARANTINED ATTEMPTS':'','COMPLETED JOBS':'',
 'MONITORING':'การตรวจงาน','Live Inspection':'ตรวจผ่านกล้อง','Video Upload':'ตรวจจากวิดีโอ',
 'LATEST ACTIVITY':'รายการล่าสุด','PRODUCTION / QR WORKFLOW INTERLOCK':'เริ่มงาน',
 'QR Production':'งานผลิต','Flow Control':'ตามสถานี','3-STATION DEMO':'3 สถานี',
 'SCAN TO START':'เริ่มตรวจงาน','เริ่มงานจาก QR Code':'เริ่มงานจาก QR',
 'SERVER GATE':'สถานะสถานี','รหัสพนักงาน (ตัวอย่าง)':'ผู้ปฏิบัติงาน',
 'QR Code ของงาน (ใช้ QR เดิมได้)':'QR ชิ้นงาน','HANDOFF GATE':'การส่งต่องาน',
 'STATION CALIBRATION':'ตั้งค่ากล้อง','CAMERA RECORDING + LIVE SOP':'ตรวจและบันทึก',
 'STANDBY':'รอเริ่มงาน','INSPECTION / LIVE CAMERA':'ตรวจผ่านกล้อง',
 'COLOR MARKER MVP':'ตรวจตามค่าตั้ง','CAMERA 01':'กล้อง',
 'STEP TRACKER':'ขั้นตอน','INSPECTION / VIDEO REVIEW':'ตรวจจากวิดีโอ',
 'Video Analysis':'','MAX 80MB · 120 SEC':'ไม่เกิน 80 MB / 2 นาที',
 'INPUT SOURCE':'ไฟล์วิดีโอ','QUICK TEST · STATION 01':'ตัวอย่างสถานี 1',
 'CONFIGURATION / STANDARD OPERATING PROCEDURES':'ตั้งค่าขั้นตอน','SOP Management':'',
 'ASSEMBLY SEQUENCE':'ขั้นตอนงาน','ANALYTICS / INSPECTION HISTORY':'ประวัติการตรวจ',
 'Reports':'','INSPECTION LOG':'ผลตรวจ','INDUSTRIAL QUALITY LAB':'ระบบตรวจงานประกอบ',
 'PROTOTYPE FOR EDUCATION · NO EMPLOYEE PERFORMANCE SCORING':'',
 'INSPECTION DETAILS':'รายละเอียด','OPERATOR WORKSPACE':'หน้าพนักงาน',
 'PRODUCTION / STATION WORKSPACE':'งานประจำสถานี','หน้าปฏิบัติงานพนักงาน':'ตรวจงานประจำสถานี',
 'สแกนชิ้นงาน → ตรวจทีละขั้น → บันทึกวิดีโอตลอดงาน → ส่งต่อเมื่อผ่าน':'เลือกสถานี เปิดกล้อง แล้วสแกน QR เพื่อเริ่มงาน',
 'LIVE CAMERA':'ภาพจากกล้อง','STANDARD OPERATING PROCEDURE':'ขั้นตอนงาน','THIS SESSION':'งานล่าสุด',
 'ชิ้นงานล่าสุดของพนักงาน':'รายการที่ตรวจจากเครื่องนี้',
 'ยังไม่มีชิ้นงานในรอบการเปิดหน้านี้':'ยังไม่มีรายการตรวจ',
 'PRODUCTION WORKSPACE':'ระบบตรวจงานประกอบ',
 'INTELLIGENT INSPECTION':'สำหรับฝ่ายผลิต',
 'เห็นทุกขั้นตอน':'ตรวจงานประกอบ',
 'มั่นใจทุกชิ้นงาน':'ตามขั้นตอนที่กำหนด',
 'เปลี่ยนทุกการตรวจให้เป็นหลักฐาน<br>เชื่อมทีมผลิตและทีมคุณภาพไว้ในที่เดียว':'สแกน QR เพื่อตรวจงานตามสถานี<br>ดูผลและวิดีโอย้อนหลังได้จากรายงาน',
 'SOP INSPECTION':'ตัวอย่างการตรวจ',
 'POSITION CHECK':'ตำแหน่งติดตั้ง','SEQUENCE VERIFIED':'ลำดับงาน',
 'BUILT FOR EVERY STEP.':'',
 'WELCOME TO YOUR WORKSPACE':'สำหรับแอดมินและหัวหน้างาน',
 'พร้อมเริ่มงานแล้วใช่ไหม':'เข้าสู่ระบบ',
 'เข้าสู่ระบบเพื่อเริ่มตรวจงานและติดตามการผลิต':'จัดการงานผลิต ดูผลตรวจ และส่งออกรายงาน',
 'หน้าพนักงาน · เลือกสเตชั่นแล้วเริ่มงาน ↗':'พนักงาน — เลือกสถานีเพื่อเริ่มงาน ↗',
 'พื้นที่ทำงานเฉพาะทีมของคุณ<br>หากยังไม่มีบัญชี ติดต่อผู้ดูแลระบบ':'พนักงานเข้าได้จากปุ่มด้านบน<br>หากไม่มีบัญชีผู้ดูแล ให้ติดต่อแอดมิน',
 'YOUR PROCESS. YOUR VISION.':'',
 'INTELLIGENT INSPECTION. CONNECTED PRODUCTION.':'ระบบตรวจงานประกอบ',
 'ออกแบบเพื่อทุกขั้นตอนของทีมคุณ':'',
}
# Only replace whole visible text nodes, leaving classes, endpoint names, IDs and
# original logo alt text intact.
for p in (root/'static').glob('*.html'):
    s=p.read_text(encoding='utf-8')
    s=re.sub(r'>([^<>]+)<',lambda m:'>'+labels.get(m.group(1).strip(),m.group(1))+'<',s)
    for old,new in labels.items():
        if '<br>' in old:s=s.replace(old,new)
    s=re.sub(r'<div class="(?:section-eyebrow|panel-eyebrow)">[^<]*</div>','',s)
    s=re.sub(r'<div class="story-footer">.*?</div>','',s)
    s=re.sub(r'<div class="form-footer">.*?</div>','',s)
    s=s.replace('auth-client.js?v=station-5','auth-client.js?v=copy-6').replace('worker.js?v=station-5','worker.js?v=copy-6')
    s=s.replace('app.js?v=traceability-3','app.js?v=copy-6').replace('production.js?v=traceability-3','production.js?v=copy-6')
    s=s.replace('admin.js?v=reports-4','admin.js?v=copy-6').replace('camera-admin.js?v=reports-4','camera-admin.js?v=copy-6')
    s=s.replace('access.js?v=access-1','access.js?v=copy-6').replace('login.css?v=login-3','login.css?v=copy-6')
    p.write_text(s,encoding='utf-8')
replacements={
 'app.js':{
  'เชื่อมต่อแล้ว · โหมดทดลอง':'เชื่อมต่อแล้ว',
  "Inspection #":"รายการ ",
  'กำลังให้ AI วิเคราะห์ภาพหลักฐาน...':'กำลังตรวจภาพด้วย Gemini...',
 },
 'admin.js':{
  'Gemini AI Review · ความเห็นเพิ่มเติม':'ตรวจภาพเพิ่มเติมด้วย Gemini',
  'วิเคราะห์ภาพหลักฐานและผล CV เพื่อชี้ข้อสังเกต/จุดที่ควรตรวจซ้ำ ผลนี้ไม่เปลี่ยนสถานะงานหรือการปลดล็อก':'ส่งภาพให้ Gemini ช่วยตรวจเพิ่มเติม ผลตรวจนี้ไม่เปลี่ยนสถานะงาน',
  'ให้ Gemini วิเคราะห์รายการนี้':'ให้ Gemini ตรวจภาพ',
  'กำลังส่งภาพหลักฐานให้ Gemini วิเคราะห์...':'กำลังตรวจภาพด้วย Gemini...',
  'AI Review ไม่สำเร็จ':'ตรวจภาพไม่สำเร็จ',
 },
 'camera-admin.js':{'รายงานตรวจ Live / Upload':'ผลตรวจจากกล้องและวิดีโอ'},
 'access.js':{'ข้อมูลล่าสุด ':'อัปเดตล่าสุด '},
 'worker.js':{
  'กรุณาเปิดกล้องก่อนสแกนเริ่มงาน':'เปิดกล้องก่อนสแกน QR',
  'ระบุรหัสพนักงานและสแกน QR ก่อนเริ่มงาน':'เลือกสถานีและสแกน QR ก่อนเริ่มงาน',
  'ระบุรหัสพนักงานก่อนเปิดกล้อง':'เลือกสถานีก่อนเปิดกล้อง',
  'ระบุพนักงานและสถานีเพื่อดูประวัติจากฐานข้อมูล':'เลือกสถานีเพื่อดูรายการล่าสุด',
  'ยังไม่มีรอบงานที่ปิดแล้ว · แสดง 15 รอบล่าสุดจากฐานข้อมูล':'ยังไม่มีงานที่ปิดแล้ว',
  'อ่านประวัติไม่สำเร็จ · ข้อมูลอาจเก่า: ':'โหลดประวัติไม่สำเร็จ: ',
 },
 'auth-client.js':{
  'เลือกสเตชั่นแล้วเริ่มตรวจงานได้เลย':'เลือกสถานีเพื่อเริ่มงาน',
  'คิวตรวจซ้ำ / บัญชี':'พิจารณางาน / ผู้ใช้',
  'รอบเดียวกันทุกสถานี':'รอบทดสอบ',
  'ชื่อรอบ เช่น เทสเร็ว ครั้งที่ 2':'ชื่อรอบทดสอบ',
  'ยอดงานจริงใช้เฉพาะโหมดผลิตจริง':'ไม่นับรอบทดสอบรวมกับยอดผลิต',
  'ทดสอบเท่านั้น · QR เดิมเริ่มใหม่ได้เมื่อสร้างรอบใหม่ · สถานี 1–3 ต้องเลือกรอบเดียวกัน':'ทุกสถานีต้องเลือกรอบเดียวกัน สร้างรอบใหม่เพื่อทดสอบ QR เดิมอีกครั้ง',
  'รอบใหม่พร้อมแล้ว · ใช้ QR เดิมเริ่มที่สถานี 1 ได้':'สร้างรอบแล้ว เริ่มทดสอบที่สถานี 1 ได้',
 },
}
for name,values in replacements.items():
    p=root/'static'/name;s=p.read_text(encoding='utf-8')
    for old,new in values.items():s=s.replace(old,new)
    p.write_text(s,encoding='utf-8')
# Shorten explanatory copy while keeping instructions that affect inspection.
for name,values in {
 'worker.html':{
  'กล้องอ่าน QR อัตโนมัติระหว่างรอและระหว่างทำงาน; QR ใหม่จะปิดวิดีโอของงานก่อนหน้า':'กล้องอ่าน QR อัตโนมัติ สแกนชิ้นถัดไปเพื่อปิดงานปัจจุบัน',
  'บันทึกวิดีโอต่อเนื่องไม่ว่าจะผ่านหรือผิดขั้นตอน แม้ตรวจครบแล้วก็ยังไม่หยุด จนกว่าจะสแกน QR งานถัดไป จากนั้นระบบตรวจเฟรมสุดท้ายและปิดงานเดิม; งานไม่ครบหรือผิดลำดับจะถูกล็อกและส่งต่อไม่ได้':'สแกน QR ชิ้นถัดไปเพื่อปิดงานและบันทึกวิดีโอ งานที่ตรวจไม่ผ่านจะถูกแยกพักและส่งต่อไม่ได้',
  'เปิดกล้อง / เชื่อมกล้องมือถือ':'เปิดกล้อง',
 },
 'access.html':{
  'พนักงานเข้าถึงงานของตนเอง · QC อ่านผลและยืนยันแยกพัก · หัวหน้าอนุมัติตรวจซ้ำ · แอดมินจัดการบัญชีและ SOP':'สร้างบัญชีสำหรับผู้ตรวจ หัวหน้างาน และแอดมิน ส่วนพนักงานเลือกสถานีได้โดยไม่ต้องมีบัญชี',
 },
}.items():
    p=root/'static'/name;s=p.read_text(encoding='utf-8')
    for old,new in values.items():s=s.replace(old,new)
    p.write_text(s,encoding='utf-8')
print('Plain-language copy applied across login, worker, overview, reports and user management.')
