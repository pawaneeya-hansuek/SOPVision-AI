(() => {
  'use strict';
  const password = document.getElementById('password');
  const toggle = document.getElementById('togglePassword');
  const form = document.getElementById('loginForm');
  const submit = document.getElementById('submit');
  const caps = document.getElementById('capsLock');
  toggle.addEventListener('click', () => {
    const visible = password.type === 'password';
    password.type = visible ? 'text' : 'password';
    toggle.setAttribute('aria-pressed', String(visible));
    toggle.setAttribute('aria-label', visible ? 'ซ่อนรหัสผ่าน' : 'แสดงรหัสผ่าน');
  });
  password.addEventListener('keyup', event => {
    caps.hidden = !event.getModifierState('CapsLock');
  });
  password.addEventListener('blur', () => { caps.hidden = true; });
  new MutationObserver(() => {
    form.setAttribute('aria-busy', String(submit.disabled));
  }).observe(submit, {attributes: true, attributeFilter: ['disabled']});
})();
