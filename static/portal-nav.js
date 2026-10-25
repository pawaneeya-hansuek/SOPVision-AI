/* Section navigation and focused detail dialogs shared by staff portals. */
(()=>{'use strict';
 const groups=[];
 document.querySelectorAll('[data-portal-nav]').forEach(nav=>{
  const name=nav.dataset.portalNav,tabs=[...nav.querySelectorAll('[data-portal-tab]')];
  const panels=[...document.querySelectorAll('[data-portal-panel]')].filter(panel=>panel.dataset.portalGroup===name);
  const select=(value,focus=false)=>{
   if(!tabs.some(tab=>tab.dataset.portalTab===value))value=tabs[0].dataset.portalTab;
   tabs.forEach(tab=>{const active=tab.dataset.portalTab===value;tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;if(active&&focus)tab.focus();});
   panels.forEach(panel=>{const active=panel.dataset.portalPanel===value;panel.hidden=!active;if(!active)panel.querySelectorAll('video').forEach(video=>video.pause());});
   if(name==='supervisor'&&value!=='archive')document.getElementById('stopVideoQr')?.click();
   if(nav.hasAttribute('data-portal-hash'))history.replaceState(null,'','#'+value);
   document.dispatchEvent(new CustomEvent('portal:change',{detail:{group:name,section:value}}));
  };
  tabs.forEach(tab=>{tab.onclick=()=>select(tab.dataset.portalTab);tab.onkeydown=event=>{
   const index=tabs.indexOf(tab);let next;
   if(event.key==='ArrowRight')next=(index+1)%tabs.length;
   if(event.key==='ArrowLeft')next=(index+tabs.length-1)%tabs.length;
   if(event.key==='Home')next=0;if(event.key==='End')next=tabs.length-1;
   if(next!==undefined){event.preventDefault();select(tabs[next].dataset.portalTab,true);}
  };});
  const initial=nav.hasAttribute('data-portal-hash')?location.hash.slice(1):tabs[0].dataset.portalTab;
  select(initial);groups.push({nav,select});
 });
 window.addEventListener('hashchange',()=>groups.filter(group=>group.nav.hasAttribute('data-portal-hash')).forEach(group=>group.select(location.hash.slice(1))));
 const dialogs=[...document.querySelectorAll('[data-portal-overlay]')];
 if(!dialogs.length)return;
 const shade=document.createElement('div');shade.className='portal-shade';shade.hidden=true;document.body.append(shade);
 let active=null,previousFocus=null;
 const close=()=>{if(!active)return;const button=active.querySelector('[data-portal-close],#closeDetail,#closePlayback');if(button)button.click();else active.hidden=true;};
 const update=()=>{
  const next=dialogs.find(dialog=>!dialog.hidden)||null;
  if(next===active)return;
  if(active)active.querySelectorAll('video').forEach(video=>video.pause());
  if(next){previousFocus=document.activeElement;active=next;shade.hidden=false;document.body.classList.add('portal-dialog-open');next.scrollTop=0;next.querySelector('button,a,input')?.focus({preventScroll:true});}
  else{active=null;shade.hidden=true;document.body.classList.remove('portal-dialog-open');previousFocus?.focus?.({preventScroll:true});}
 };
 dialogs.forEach(dialog=>{
  dialog.setAttribute('role','dialog');dialog.setAttribute('aria-modal','true');
  dialog.querySelectorAll('[data-portal-close]').forEach(button=>button.onclick=()=>{dialog.hidden=true;});
  new MutationObserver(update).observe(dialog,{attributes:true,attributeFilter:['hidden']});
 });
 shade.onclick=close;
 document.addEventListener('keydown',event=>{
  if(!active)return;
  if(event.key==='Escape'){event.preventDefault();close();}
  if(event.key==='Tab'){
   const controls=[...active.querySelectorAll('button,a[href],input,select,textarea,video[controls]')].filter(el=>!el.disabled&&el.getClientRects().length);
   const first=controls[0],last=controls.at(-1);
   if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
   else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
  }
 });update();
})();
