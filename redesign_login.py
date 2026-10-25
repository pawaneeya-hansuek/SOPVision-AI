from pathlib import Path
from datetime import datetime
import shutil
root=Path(__file__).parent
backup=root/'backups'/('login-design-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
for name in ('login.html','auth-login.js'):
    shutil.copy2(root/'static'/name,backup/name)
html='''<!doctype html>
<html lang="th">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="theme-color" content="#102a49"><title>เข้าสู่ระบบ | SOPVision AI</title>
  <link rel="icon" type="image/png" href="/static/brand/sopvision-logo.png">
  <link rel="stylesheet" href="/static/auth.css?v=login-2">
  <link rel="stylesheet" href="/static/login.css?v=login-2">
</head>
<body class="auth-page login-page">
<div class="login-container">
  <header class="login-header">
    <a class="login-brand" href="/login" aria-label="SOPVision AI หน้าเข้าสู่ระบบ"><img src="/static/brand/sopvision-logo.png" width="1024" height="338" alt="SOPVision AI — Intelligent Inspection"></a>
    <span class="workspace-label"><i></i> PRODUCTION WORKSPACE</span>
  </header>
  <main class="auth-layout login-layout">
    <section class="auth-story login-story" aria-labelledby="storyTitle">
      <div class="story-grid" aria-hidden="true"></div>
      <div class="story-copy"><span class="story-eyebrow"><span></span> INTELLIGENT INSPECTION</span>
      <h1 id="storyTitle">เห็นทุกขั้นตอน<br><span>มั่นใจทุกชิ้นงาน</span></h1>
      <p>เปลี่ยนทุกการตรวจให้เป็นหลักฐาน<br>เชื่อมทีมผลิตและทีมคุณภาพไว้ในที่เดียว</p></div>
      <div class="inspection-visual" aria-hidden="true">
        <div class="visual-top"><span><i></i> SOP INSPECTION</span><span class="demo-label">ภาพจำลองระบบ</span></div>
        <div class="scan-view">
          <svg class="assembly-graphic" viewBox="0 0 480 230" fill="none">
            <defs><linearGradient id="plate" x1="90" y1="40" x2="370" y2="220" gradientUnits="userSpaceOnUse"><stop stop-color="#284969"/><stop offset="1" stop-color="#122d49"/></linearGradient><linearGradient id="part" x1="180" y1="40" x2="320" y2="190"><stop stop-color="#54d9ed"/><stop offset="1" stop-color="#1776bf"/></linearGradient></defs>
            <path d="M40 36H20V56M440 36H460V56M20 174V194H40M440 194H460V174" stroke="#49d3e6" stroke-width="3" stroke-linecap="round"/>
            <path d="M76 152L237 63L406 143L245 230Z" fill="#061a2b" opacity=".65"/>
            <path d="M80 116L237 29L400 110V137L242 223L80 143Z" fill="#12334f" stroke="#365b76"/>
            <path d="M80 116L237 29L400 110L242 196Z" fill="url(#plate)" stroke="#53728d"/>
            <path d="M242 196V223M400 110V137" stroke="#52718b"/>
            <path d="M139 113L238 58L343 110L243 166Z" fill="#10273d" stroke="#31879e" stroke-dasharray="5 5"/>
            <path d="M161 106L236 65L316 104V126L242 169L161 130Z" fill="#106589" stroke="#4fbed3"/>
            <path d="M161 106L236 65L316 104L242 146Z" fill="url(#part)" stroke="#83e7ee"/>
            <path d="M242 146V169M316 104V126" stroke="#76d7e4"/>
            <ellipse cx="240" cy="105" rx="29" ry="17" fill="#103d5e" stroke="#73e2eb" stroke-width="2"/>
            <ellipse cx="240" cy="105" rx="12" ry="7" fill="#0b2540" stroke="#3898b8"/>
            <ellipse cx="114" cy="117" rx="7" ry="4" fill="#75a6b9"/><ellipse cx="240" cy="48" rx="7" ry="4" fill="#75a6b9"/><ellipse cx="366" cy="111" rx="7" ry="4" fill="#75a6b9"/><ellipse cx="244" cy="177" rx="7" ry="4" fill="#75a6b9"/>
            <path d="M155 77V62H176M304 62H325V77M155 139V151H176M304 151H325V139" stroke="#69f0d1" stroke-width="2"/>
            <path d="M326 78L366 53H420" stroke="#5a9db6"/><circle cx="326" cy="78" r="3" fill="#6cebd2"/>
            <path d="M138 140L99 165H49" stroke="#5a9db6"/><circle cx="138" cy="140" r="3" fill="#6cebd2"/>
          </svg>
          <span class="scan-caption scan-caption-top">POSITION CHECK</span><span class="scan-caption scan-caption-bottom">SEQUENCE VERIFIED</span>
          <div class="scan-line"></div>
        </div>
        <div class="visual-bottom"><span class="visual-check">✓</span><span>ตรวจลำดับ · ตำแหน่ง · หลักฐาน</span><span class="visual-signal"><b></b><b></b><b></b><b></b></span></div>
      </div>
      <div class="story-features"><span><b>01</b> สแกน QR</span><i></i><span><b>02</b> ตรวจตาม SOP</span><i></i><span><b>03</b> ติดตามผล</span></div>
      <div class="story-footer"><span class="footer-line"></span> BUILT FOR EVERY STEP.</div>
    </section>
    <section class="auth-form-wrap login-form-wrap" aria-labelledby="title">
      <div class="form-intro"><span class="auth-kicker">WELCOME TO YOUR WORKSPACE</span>
        <h2 id="title">พร้อมเริ่มงานแล้วใช่ไหม</h2><p class="auth-description" id="description">เข้าสู่ระบบเพื่อเริ่มตรวจงานและติดตามการผลิต</p>
      </div>
      <form id="loginForm" class="auth-form login-form">
        <label id="codeLabel" hidden>รหัสตั้งค่าผู้ดูแลครั้งแรก<input id="setupCode" type="password" autocomplete="off"></label>
        <label id="displayLabel" hidden>ชื่อที่แสดง<input id="displayName" value="ผู้ดูแลระบบ" maxlength="100"></label>
        <label for="username">ชื่อบัญชี</label>
        <div class="login-input"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="8" r="3.5"/><path d="M5 21V19a7 7 0 0 1 14 0v2"/></svg><input id="username" autocomplete="username" required maxlength="80" placeholder="กรอกชื่อบัญชีของคุณ" autocapitalize="none" spellcheck="false"></div>
        <label for="password">รหัสผ่าน</label>
        <div class="login-input"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/></svg><input id="password" type="password" autocomplete="current-password" required maxlength="200" placeholder="กรอกรหัสผ่าน"><button id="togglePassword" type="button" class="password-toggle" aria-label="แสดงรหัสผ่าน" aria-pressed="false"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg></button></div>
        <span id="capsLock" class="caps-lock" hidden>Caps Lock เปิดอยู่</span>
        <label id="confirmLabel" hidden>ยืนยันรหัสผ่าน<input id="confirmPassword" type="password" autocomplete="new-password"></label>
        <button class="auth-primary login-submit" id="submit" type="submit">เข้าสู่ระบบ</button>
      </form>
      <p class="auth-message" id="message" role="status" aria-live="polite"></p>
      <div class="login-help"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6Z"/><path d="m8.5 12 2.5 2.5 4.5-5"/></svg><p class="auth-help" id="help">พื้นที่ทำงานเฉพาะทีมของคุณ<br>หากยังไม่มีบัญชี ติดต่อผู้ดูแลระบบ</p></div>
      <a href="/setup" id="setupLink" class="auth-link setup-link" hidden>ตั้งค่าผู้ดูแลระบบครั้งแรก <span aria-hidden="true">↗</span></a>
      <div class="form-footer"><span>YOUR PROCESS. YOUR VISION.</span><span>SOPVISION AI</span></div>
    </section>
  </main>
  <footer class="login-page-footer"><span>INTELLIGENT INSPECTION. CONNECTED PRODUCTION.</span><span>ออกแบบเพื่อทุกขั้นตอนของทีมคุณ</span></footer>
</div>
<script src="/static/auth-login.js?v=login-2" defer></script><script src="/static/login-ui.js?v=login-2" defer></script>
</body></html>'''
(root/'static/login.html').write_text(html,encoding='utf-8')
print('Login HTML updated; previous files backed up.')
