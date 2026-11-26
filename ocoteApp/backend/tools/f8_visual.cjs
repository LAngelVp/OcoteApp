const { spawn } = require('node:child_process');
const { once } = require('node:events');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const origin = process.env.OCOTE_F8_PREVIEW || 'https://localhost:8443';
if (!/^https:\/\/localhost:\d+$/.test(origin)) throw Error('Preview must be local HTTPS');

const policy = { version:1,password_min_length:12,require_upper:true,require_lower:true,require_digit:true,require_symbol:true,access_ttl_seconds:300,refresh_absolute_seconds:86400,idle_timeout_seconds:900,failed_attempt_threshold:5,failed_window_seconds:300,lockout_seconds:300,page_sizes:[5,10,20,50],import_max_rows:1000,import_max_bytes:10485760,export_max_bytes:16777216 };
const flags = Object.fromEntries(['subtasks','due_date_requests','kanban','timeline','analytics','evaluations','exports','integrations','calendar'].map(code => [code,true]));
const branding = { version:0,organization_name:'OCOTE',organization_name_version:0,welcome_text:'',footer_text:'',token_overrides:{},logo_asset_id:null };
const configuration = { revision:10,branding,flags,page_sizes:[5,10,20,50],security_policy:policy,modules:Object.keys(flags).map(code => ({ code,installed:true,enabled:true,version:1 })) };
function synthetic(endpoint, method) {
  if (method !== 'GET' && endpoint === '/admin/security-policy') return { status:409,data:{ code:'VERSION_CONFLICT',request_id:'synthetic-f8-conflict' } };
  let data = { items:[],next_cursor:null };
  if (endpoint === '/auth/csrf') data = { csrf_token:'synthetic' };
  if (endpoint === '/auth/refresh') data = { access_token:'synthetic',csrf_token:'synthetic',expires_in:300 };
  if (endpoint === '/auth/me') data = { id:'synthetic',display_name:'Revision sintetica F8',email:'synthetic@example.invalid',role:'admin',department_id:null,permissions:['administration:manage','planning:manage','analytics:read','evaluations:read','date-requests:create'] };
  if (['/configuration','/admin/configuration'].includes(endpoint)) data = configuration;
  if (endpoint === '/admin/calendars') data = { items:[{ id:'synthetic-calendar',version:1,name:'Calendario sintetico',scope_kind:'organization',department_id:null,weekday_mask:31,inheritance:'replace' }],next_cursor:null };
  return { status:200,data };
}
async function main() {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(),'ocote-f8-chrome-'));
  const artifacts = fs.mkdtempSync(path.join(os.tmpdir(),'ocote-f8-visual-'));
  const chrome = spawn(process.env.CHROME_BIN || 'C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless=new','--remote-debugging-port=0','--user-data-dir='+profile,'--ignore-certificate-errors','--disable-gpu','--no-first-run','about:blank'],{ stdio:['ignore','ignore','pipe'] });
  let socket, session, sequence = 0;
  const pending = new Map(), errors = [], requests = [], results = [], cancelled = [];
  try {
    const endpoint = await new Promise((resolve,reject) => { let output=''; chrome.stderr.on('data',data => {output+=data;const match=output.match(/DevTools listening on (ws:\/\/[^\s]+)/);if(match)resolve(match[1]);});chrome.once('error',reject);chrome.once('exit',()=>reject(Error('Chrome exited before CDP'))); });
    socket = new WebSocket(endpoint); await once(socket,'open');
    const send = (method,params={},sessionId) => new Promise((resolve,reject) => {const id=++sequence;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));});
    socket.addEventListener('message',async event => {
      const message=JSON.parse(event.data);
      if(message.id){const callback=pending.get(message.id);if(callback){pending.delete(message.id);message.error?callback.reject(Error(JSON.stringify(message.error))):callback.resolve(message.result);}return;}
      if(message.method==='Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text);
      if(message.method!=='Fetch.requestPaused')return;
      try {const request=message.params.request,url=new URL(request.url),endpoint=url.pathname.slice(7),response=synthetic(endpoint,request.method);requests.push({method:request.method,path:endpoint});await send('Fetch.fulfillRequest',{requestId:message.params.requestId,responseCode:response.status,responseHeaders:[{name:'Content-Type',value:response.status===409?'application/problem+json':'application/json'},{name:'Cache-Control',value:'no-store'}],body:Buffer.from(JSON.stringify(response.data)).toString('base64')},session);}catch(error){if(error.message==='{"code":-32602,"message":"Invalid InterceptionId."}')cancelled.push(message.params.request.url);else errors.push(String(error));}
    });
    const target=await send('Target.createTarget',{url:'about:blank'});
    session=(await send('Target.attachToTarget',{targetId:target.targetId,flatten:true})).sessionId;
    const page=(method,params={})=>send(method,params,session);
    await page('Page.enable');await page('Runtime.enable');await page('Security.setIgnoreCertificateErrors',{ignore:true});
    await page('Fetch.enable',{patterns:[{urlPattern:origin+'/api/v1/*',requestStage:'Request'}]});
    const evaluate=async expression=>{const response=await page('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(response.exceptionDetails)throw Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text);return response.result.value;};
    const wait=expression=>evaluate(`new Promise((resolve,reject)=>{const end=Date.now()+20000;function check(){if(${expression})resolve(true);else if(Date.now()>end)reject(Error('DOM condition timed out'));else requestAnimationFrame(check);}check();})`);
    const shot=async name=>{await evaluate('Promise.all(document.getAnimations().map(animation=>animation.finished.catch(()=>{})))');const image=await page('Page.captureScreenshot',{captureBeyondViewport:false});fs.writeFileSync(path.join(artifacts,name+'.png'),Buffer.from(image.data,'base64'));};
    const inspect=async name=>{
      await evaluate('document.fonts.ready');
      await wait('[...document.images].every(image=>image.complete && image.naturalWidth>0)');
      const metrics=await evaluate(`({width:innerWidth,scroll:document.documentElement.scrollWidth,images:[...document.images].map(image=>({src:image.currentSrc,naturalWidth:image.naturalWidth,width:image.getBoundingClientRect().width})),overflow:[...document.querySelectorAll('h1,h2,h3,button,input,img')].filter(element=>{const box=element.getBoundingClientRect();return box.width>0 && (box.left<-.5 || box.right>innerWidth+.5);}).map(element=>element.tagName+':'+element.textContent.trim().slice(0,40))})`);
      if(metrics.scroll>metrics.width || metrics.overflow.length || metrics.images.some(image=>!image.naturalWidth))throw Error(name+':'+JSON.stringify(metrics));
      await shot(name);results.push({name,...metrics});
    };
    for(const width of [1280,360]){
      await page('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
      await page('Page.navigate',{url:origin+'/login'});await wait('document.querySelector(".login-brand img")');await inspect('login-'+width);
      const icon=await evaluate('new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image.naturalWidth);image.onerror=reject;image.src=document.querySelector("link[rel=icon]").href;})');if(icon<=0)throw Error('Favicon missing');
      await page('Page.navigate',{url:origin+'/administracion/configuracion'});await wait('document.body.innerText.includes("Politicas de acceso y limites")');await inspect('security-'+width);
      const header=await evaluate('document.querySelector(".brand img").currentSrc');if(!header.endsWith(width>=1280?'/logos/ocote-text.webp':'/logos/ocote-icon.png'))throw Error('Wrong responsive identity: '+header);
      for(const label of ['Modulos','Branding','Calendarios','Almacenamiento externo']){
        await evaluate(`(()=>{const tab=[...document.querySelectorAll('[role=tab]')].find(element=>element.textContent.trim()===${JSON.stringify(label)});tab.click();})()`);
        await wait(`document.querySelector('[role=tab][aria-selected=true]').textContent.trim()===${JSON.stringify(label)}`);
        await inspect(label.toLowerCase().replace(/ /g,'-')+'-'+width);
        if(label==='Branding'){
          await evaluate('(()=>{const input=document.querySelector("input[type=color]");input.value="#ffffff";input.dispatchEvent(new Event("input",{bubbles:true}));})()');
          await wait('document.body.innerText.includes("Contraste insuficiente")');
          const blocked=await evaluate('[...document.querySelectorAll("button")].find(button=>button.textContent.includes("Guardar identidad")).disabled');if(!blocked)throw Error('AA client guard failed');
          await shot('branding-AA-blocked-'+width);
        }
      }
      await evaluate('[...document.querySelectorAll("[role=tab]")].find(tab=>tab.textContent.trim()==="Seguridad").click()');
      await evaluate('[...document.querySelectorAll("button")].find(button=>button.textContent.includes("Configurar")).click()');
      await wait('document.querySelector("mat-dialog-container input[type=password]")');
      await evaluate('(()=>{for(const [selector,value] of [["input[type=password]","Synthetic-only-123!"],["textarea","Motivo sintetico F8 para conservar ante conflicto"]]){const input=document.querySelector("mat-dialog-container "+selector);input.value=value;input.dispatchEvent(new Event("input",{bubbles:true}));}})()');
      await evaluate('document.querySelector("mat-dialog-container button[type=submit]").click()');
      await wait('document.querySelector("mat-dialog-container").innerText.includes("synthetic-f8-conflict")');
      const retained=await evaluate('document.querySelector("mat-dialog-container button[type=submit]").disabled && document.querySelector("mat-dialog-container textarea").value.includes("conservar")');if(!retained)throw Error('409 retention failed');
      await inspect('conflict-'+width);
      await evaluate('[...document.querySelectorAll("mat-dialog-container button")].find(button=>button.textContent.includes("Descartar")).click()');await wait('!document.querySelector("mat-dialog-container")');
    }
    if(errors.length)throw Error(JSON.stringify(errors));
    const report={artifacts,results,syntheticRequests:requests.length,syntheticWrites:requests.filter(request=>request.method!=='GET'),cancelledRequests:cancelled,runtimeErrors:errors};fs.writeFileSync(path.join(artifacts,'results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));await send('Browser.close');
  }finally{if(socket)socket.close();if(chrome.exitCode===null){chrome.kill();await once(chrome,'exit');}fs.rmSync(profile,{recursive:true,force:true});}
}
main().catch(error=>{console.error(error);process.exitCode=1;});