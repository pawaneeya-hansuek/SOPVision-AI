'use strict';
const el=id=>document.getElementById(id);
const query=new URLSearchParams(location.search),setup=location.pathname==='/setup';
if(!setup){
 const heading='เข้าสู่ระบบ';
 document.title=heading+' | SOPVision AI';el('title').textContent=heading;
 el('description').textContent='กรอกบัญชีและรหัสผ่าน ระบบจะเปิดหน้าตามสิทธิ์ของคุณ';
 el('help').textContent='ใช้บัญชีของคุณเอง หากยังไม่มีบัญชีให้ติดต่อผู้ดูแลระบบ';
}
const code=query.get('token');if(code){el('setupCode').value=code;history.replaceState(null,'','/setup');}
(async()=>{try{
 const status=await(await fetch('/api/auth/status',{cache:'no-store'})).json();
 if(setup&&status.configured){location.replace('/login');return;}
 if(!status.configured)el('setupLink').hidden=false;
 if(setup){
  el('title').textContent='สร้างบัญชีผู้ดูแล';
  el('description').textContent='ตั้งรหัสผ่านของคุณเอง ไม่มีบัญชีหรือรหัสผ่านเริ่มต้น';
  for(const id of ['codeLabel','displayLabel','confirmLabel'])el(id).hidden=false;
  el('setupCode').required=true;el('confirmPassword').required=true;
  el('password').minLength=10;el('password').autocomplete='new-password';
  el('submit').textContent='สร้างบัญชีและเริ่มใช้งาน';
  el('help').textContent='เปิด setup_admin.bat บนคอมที่รันระบบ เพื่อเปิดหน้านี้พร้อมรหัสตั้งค่าครั้งเดียว หรืออ่านรหัสจากไฟล์ sopvision.admin-setup-code ในโฟลเดอร์โปรเจกต์';
 }
}catch{el('message').textContent='เชื่อมต่อระบบไม่ได้ กรุณาตรวจเซิร์ฟเวอร์';}})();
el('loginForm').onsubmit=async e=>{
 e.preventDefault();el('message').className='auth-message';el('message').textContent='';
 if(setup&&el('password').value!==el('confirmPassword').value){el('message').textContent='รหัสผ่านสองช่องไม่ตรงกัน';return;}
 el('submit').disabled=true;
 try{
  const body={username:el('username').value.trim(),password:el('password').value};
  if(setup)Object.assign(body,{code:el('setupCode').value.trim(),display_name:el('displayName').value.trim()});
  const r=await fetch('/api/auth/'+(setup?'setup':'login'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'กรุณาตรวจข้อมูลที่กรอก');
  location.replace(data.home||(data.role==='supervisor'?'/supervisor':data.role==='operator'?'/worker':'/admin'));
 }catch(error){el('message').className='auth-message bad';el('message').textContent=error.message;}
 finally{el('submit').disabled=false;}
};
