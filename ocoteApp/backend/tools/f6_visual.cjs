const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { once } = require('node:events');

const metrics = { task_count:36,completed_count:18,completion_rate:50,progress_percent:62.5,baseline_on_time_rate:25,on_time_rate:50,blocked_count:3,pending_closure_count:2,rescheduled_count:7,due_date_change_count:9,average_delay_days:2.5,average_baseline_delay_days:4.25,average_due_date_delta_days:3,annual_plan:{ title:'Plan sintetico plurianual de operaciones',horizon_type:'custom',start_date:'2024-01-01',due_date:'2027-12-31' },department:{ name:'Departamento sintetico de operaciones' },evaluator:{ display_name:'Evaluador sintetico' } };
const departments = Array.from({ length:13 },(_,index) => ({ id:'department-' + index,name:'Departamento sintetico ' + (index + 1),...metrics }));
const months = Array.from({ length:24 },(_,index) => ({ month:(2025 + Math.floor(index / 12)) + '-' + String(index % 12 + 1).padStart(2,'0'),...metrics }));
const tasks = Array.from({ length:13 },(_,index) => ({ id:'task-' + index,title:'Tarea sintetica ' + (index + 1),objective:{ title:'Objetivo sintetico',horizon_type:'quarterly',start_date:'2025-01-01',due_date:'2025-03-31' },assignee:{ display_name:'Responsable sintetico' },stage:{ name:'En ejecucion' },priority:{ name:'Normal sintetica' },original_due_date:'2025-03-15',due_date:'2025-03-31',completed_at:null,progress_percent:50,baseline_punctuality_status:'overdue',punctuality_status:'overdue' }));

function paginate(items,url) {
  const start = url.searchParams.get('cursor') ? 5 : 0, size = Number(url.searchParams.get('limit') || 5);
  return { items:items.slice(start,start + size),next_cursor:start + size < items.length ? 'next' : null };
}
function synthetic(url) {
  const endpoint = url.pathname.slice(7);
  let data = { items:[],next_cursor:null }, status = 200;
  if (endpoint === '/auth/csrf') data = { csrf_token:'synthetic' };
  else if (endpoint === '/auth/refresh') data = { access_token:'synthetic',csrf_token:'synthetic',expires_in:900 };
  else if (endpoint === '/auth/me') data = { id:'synthetic',display_name:'Revision sintetica F6',email:'synthetic@example.invalid',role:'admin',department_id:null,permissions:['analytics:read','evaluations:read','evaluations:manage','exports:read','planning:manage','administration:manage'] };
  else if (endpoint === '/annual-plans') data = { items:[{ id:'plan',title:'Plan sintetico plurianual' }],next_cursor:null };
  else if (endpoint === '/catalogs/departments') data = { items:[{ id:'department',name:'Departamento sintetico' }],next_cursor:null };
  else if (endpoint === '/catalogs/assignees') data = { items:[{ id:'person',display_name:'Responsable sintetico' }],next_cursor:null };
  else if (endpoint.startsWith('/analytics/')) data = { ...paginate(endpoint.endsWith('summary') ? departments : months,url),metrics,series:months,snapshot_at:'2026-11-25T18:00:00Z',organization_timezone:'America/Mexico_City',filters:{ period_start:'2025-01-01',period_end:'2026-12-31' } };
  else if (endpoint === '/evaluations') data = { items:[{ id:'synthetic-draft',metrics,version:3,status:'draft',period_start:'2025-01-01',period_end:'2025-03-31',snapshot_at:'2026-11-25T18:00:00Z' },{ id:'synthetic-final',metrics,version:2,status:'final',period_start:'2025-04-01',period_end:'2025-06-30',snapshot_at:'2026-11-25T18:00:00Z' }],next_cursor:null };
  else if (endpoint.endsWith('/finalize')) { status = 409; data = { code:'CONCURRENCY_CONFLICT',request_id:'synthetic-conflict-f6' }; }
  else if (endpoint.startsWith('/evaluations/')) {
    const final = endpoint.includes('synthetic-final'), empty = endpoint.includes('synthetic-empty');
    data = { id:final ? 'synthetic-final' : 'synthetic-draft',version:3,status:final ? 'final' : 'draft',can_finalize:!final && !empty,finalization_reason:empty ? 'no_data' : final ? 'final' : null,period_start:'2025-01-01',period_end:'2025-03-31',snapshot_at:'2026-11-25T18:00:00Z',organization_timezone:'America/Mexico_City',calculation_version:'1.0',metrics:empty ? { ...metrics,task_count:0 } : metrics,summary:final ? 'Conclusion gerencial sintetica sellada.' : null,...paginate(empty ? [] : tasks,url) };
  }
  return { data,status };
}

async function main() {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(),'ocote-f6-chrome-'));
  const artifacts = fs.mkdtempSync(path.join(os.tmpdir(),'ocote-f6-visual-'));
  const chrome = spawn(process.env.CHROME_BIN || 'C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless=new','--remote-debugging-port=0','--user-data-dir=' + profile,'--ignore-certificate-errors','--disable-gpu','--no-first-run','about:blank'],{ stdio:['ignore','ignore','pipe'] });
  let socket, session, sequence = 0, loaded = 0;
  const pending = new Map(), loadWaiters = [], failures = [], reads = [], results = [];
  try {
    const endpoint = await new Promise((resolve,reject) => {
      let output = '';
      chrome.stderr.on('data',data => { output += data; const match = output.match(/DevTools listening on (ws:\/\/[^\s]+)/); if (match) resolve(match[1]); });
      chrome.once('error',reject); chrome.once('exit',() => reject(Error('Chrome exited before CDP')));
    });
    socket = new WebSocket(endpoint); await once(socket,'open');
    const send = (method,params = {},sessionId) => new Promise((resolve,reject) => {
      const id = ++sequence; pending.set(id,{ resolve,reject });
      socket.send(JSON.stringify({ id,method,params,...(sessionId ? { sessionId } : {}) }));
    });
    socket.addEventListener('message',async event => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const callback = pending.get(message.id);
        if (callback) { pending.delete(message.id); message.error ? callback.reject(Error(JSON.stringify(message.error))) : callback.resolve(message.result); }
        return;
      }
      if (message.method === 'Page.loadEventFired') { loaded++; loadWaiters.splice(0).forEach(resolve => resolve()); }
      if (message.method === 'Runtime.exceptionThrown') failures.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text);
      if (message.method !== 'Fetch.requestPaused') return;
      try {
        const request = message.params.request, url = new URL(request.url), { data,status } = synthetic(url);
        reads.push({ method:request.method,path:url.pathname.slice(7),query:url.search });
        await send('Fetch.fulfillRequest',{ requestId:message.params.requestId,responseCode:status,responseHeaders:[{ name:'Content-Type',value:status === 409 ? 'application/problem+json' : 'application/json' },{ name:'Cache-Control',value:'no-store' }],body:Buffer.from(JSON.stringify(data)).toString('base64') },session);
      } catch (error) { failures.push(String(error)); }
    });
    const target = await send('Target.createTarget',{ url:'about:blank' });
    session = (await send('Target.attachToTarget',{ targetId:target.targetId,flatten:true })).sessionId;
    const page = (method,params = {}) => send(method,params,session);
    await page('Page.enable'); await page('Runtime.enable'); await page('Security.setIgnoreCertificateErrors',{ ignore:true });
    await page('Fetch.enable',{ patterns:[{ urlPattern:'*://localhost:8443/api/v1/*',requestStage:'Request' }] });
    const evaluate = async expression => {
      const response = await page('Runtime.evaluate',{ expression,returnByValue:true,awaitPromise:true });
      if (response.exceptionDetails) throw Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text);
      return response.result.value;
    };
    const wait = expression => evaluate(`new Promise((resolve,reject)=>{const end=Date.now()+15000;function check(){if(${expression})resolve(true);else if(Date.now()>end)reject(Error("DOM condition timed out"));else requestAnimationFrame(check);}check();})`);
    const navigate = async route => {
      const before = loaded;
      await page('Page.navigate',{ url:'https://localhost:8443' + route });
      if (loaded === before) await new Promise(resolve => loadWaiters.push(resolve));
      try {
        await wait('document.querySelector("h1") && !document.body.innerText.includes("Cargando evaluaciones...") && (document.querySelector("tbody tr") || document.body.innerText.includes("Sin tareas en el corte"))');
      } catch (error) {
        throw Error(JSON.stringify({ route,error:String(error),body:await evaluate('document.body.innerText'),reads:reads.slice(-10),failures }));
      }
    };
    const screenshot = async name => {
      await evaluate('Promise.all(document.getAnimations().map(animation=>animation.finished.catch(()=>{})))');
      const shot = await page('Page.captureScreenshot',{ captureBeyondViewport:false });
      fs.writeFileSync(path.join(artifacts,name + '.png'),Buffer.from(shot.data,'base64'));
    };
    for (const width of [1280,360]) {
      await page('Emulation.setDeviceMetricsOverride',{ width,height:900,deviceScaleFactor:1,mobile:false });
      await navigate('/analitica');
      await wait('document.querySelectorAll(".report-chart canvas").length===2 && [...document.querySelectorAll(".report-chart canvas")].every(canvas=>canvas.getContext("2d").getImageData(0,0,canvas.width,canvas.height).data.some((value,index)=>index%4===3&&value>0))');
      const analytics = await evaluate(`({viewport:innerWidth,scroll:document.documentElement.scrollWidth,tables:[...document.querySelectorAll("tbody")].map(body=>body.rows.length),canvases:[...document.querySelectorAll(".report-chart canvas")].map(canvas=>{const data=canvas.getContext("2d").getImageData(0,0,canvas.width,canvas.height).data;let pixels=0;const colors=new Set();for(let index=0;index<data.length;index+=4){if(data[index+3])pixels++;colors.add(Array.from(data.slice(index,index+4)).join(","));}return {width:canvas.width,height:canvas.height,pixels,colors:colors.size};})})`);
      if (analytics.scroll > width || analytics.tables.some(count => count !== 5) || analytics.canvases.some(canvas => canvas.pixels < 100 || canvas.colors < 20)) throw Error('Analytics viewport/canvas check failed: ' + JSON.stringify(analytics));
      await screenshot('analytics-' + width); await evaluate('document.querySelector(".report-section").scrollIntoView()'); await screenshot('charts-' + width);
      await navigate('/evaluaciones'); await screenshot('evaluations-' + width);
      await navigate('/evaluaciones/synthetic-final');
      const final = await evaluate('({scroll:document.documentElement.scrollWidth,rows:document.querySelectorAll("tbody tr").length,summary:document.body.innerText.includes("Conclusion gerencial sintetica sellada."),mutable:[...document.querySelectorAll("button")].some(button=>button.textContent.includes("Recalcular corte"))})');
      if (final.scroll > width || final.rows !== 5 || !final.summary || final.mutable) throw Error('Final snapshot check failed');
      await screenshot('evaluation-final-' + width);
      await navigate('/evaluaciones/synthetic-draft');
      await evaluate('[...document.querySelectorAll("button")].find(button=>button.textContent.includes("Finalizar evaluacion")).click()');
      await wait('document.querySelector("mat-dialog-container textarea")');
      await evaluate('(()=>{const input=document.querySelector("mat-dialog-container textarea");input.value="Conclusion gerencial sintetica conservada ante conflicto.";input.dispatchEvent(new Event("input",{bubbles:true}));})()');
      await evaluate('document.querySelector("mat-dialog-container button[type=submit]").click()');
      await wait('document.querySelector("mat-dialog-container").innerText.includes("synthetic-conflict-f6")');
      const conflict = await evaluate('({disabled:document.querySelector("mat-dialog-container button[type=submit]").disabled,value:document.querySelector("mat-dialog-container textarea").value,scroll:document.documentElement.scrollWidth,dialogWidth:document.querySelector("mat-dialog-container").getBoundingClientRect().width})');
      if (!conflict.disabled || !conflict.value.includes('conservada') || conflict.scroll > width || conflict.dialogWidth > width) throw Error('Conflict retention/mobile dialog check failed');
      await screenshot('evaluation-conflict-' + width);
      await evaluate('[...document.querySelectorAll("mat-dialog-container button")].find(button=>button.textContent.includes("Descartar cambios y recargar")).click()');
      await wait('!document.querySelector("mat-dialog-container")');
      await navigate('/evaluaciones/synthetic-empty');
      const empty = await evaluate('[...document.querySelectorAll("button")].find(button=>button.textContent.includes("Finalizar evaluacion")).disabled');
      if (!empty) throw Error('Empty cohort must not finalize');
      results.push({ width,analytics,final,conflict,emptyBlocked:empty });
    }
    if (failures.length) throw Error(JSON.stringify(failures));
    const result = { artifacts,results,syntheticRequests:reads.length,apiWrites:reads.filter(read => read.method !== 'GET'),runtimeErrors:failures };
    fs.writeFileSync(path.join(artifacts,'results.json'),JSON.stringify(result,null,2));
    console.log(JSON.stringify(result,null,2)); await send('Browser.close');
  } finally {
    if (socket) socket.close();
    if (chrome.exitCode === null) { chrome.kill(); await once(chrome,'exit'); }
    fs.rmSync(profile,{ recursive:true,force:true });
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });