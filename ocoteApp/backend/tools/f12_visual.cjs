const { execFileSync, spawn } = require('node:child_process');
const { once } = require('node:events');
const fs = require('node:fs');
const https = require('node:https');
const os = require('node:os');
const path = require('node:path');

const origin = 'https://localhost:8445';
const identity = number => '00000000-0000-4000-8000-' + String(number).padStart(12, '0');
const moment = '2026-11-26T14:00:00Z';
const actor = identity(1), department = identity(2), importId = identity(3);
const pageOf = items => ({ items, next_cursor: null });
let role = 'admin';
const flags = { imports: true, executive_reports: true, advanced_operations: true, evaluations: true, exports: true };
const imported = { id: importId, version: 2, entity_type: 'task', file_format: 'csv', file_hash: 'a'.repeat(64), file_size: 240, headers: ['Titulo', 'Objetivo', 'Responsable', 'Inicio', 'Compromiso'], mapping: { Titulo: 'title', Objetivo: 'objective_id', Responsable: 'assignee_id', Inicio: 'start_date', Compromiso: 'due_date' }, state: 'previewed', row_count: 2, error_count: 0, preview_attempts: 1, config_hash: 'b'.repeat(64), preview_hash: 'c'.repeat(64), created_at: moment, updated_at: moment, expires_at: '2026-11-26T15:00:00Z', result_ids: null, rows: [1, 2].map(number => ({ row: number, valid: true, errors: [], preview: { title: 'Tarea sintetica ' + number, start_date: '2026-11-01', due_date: '2026-12-01' } })) };
const report = { id: identity(4), version: 1, final_evaluation_id: identity(5), department_id: department, file_format: 'xlsx', snapshot_at: moment, calculation_version: 'v1', organization_timezone: 'America/Mexico_City', row_count: 20, byte_count: 5300, result_hash: 'd'.repeat(64), created_at: moment, expires_at: '2026-11-26T15:00:00Z' };
const agent = { configured: true, id: identity(6), version: 3, config_revision: 1, is_active: true, tested_version: 1, tested_at: moment, service_principal_id: identity(7), destination_ref: identity(8), capabilities: ['backup', 'restore_verify'], authentication_configured: true };
const backup = { id: identity(9), version: 1, created_at: moment, job_id: identity(10), instance_id: identity(11), source_revision: '20261126_0011', size_bytes: 530000, manifest_hash: 'e'.repeat(64), dump_hash: 'f'.repeat(64), restore_verified: true, duration_ms: 4200 };
const policy = { id: identity(12), version: 2, category: 'evidence', minimum_days: 365, legal_hold: true, responsible_user_id: actor, approval_ref: 'Aprobacion sintetica F12', created_at: moment };
function synthetic(route, method) {
  if (route === '/imports/' + importId + '/dry-run' && method === 'POST') return { status: 409, data: { code: 'IMPORT_PREVIEW_STALE', request_id: 'synthetic-f12-409' } };
  let data;
  if (route === '/auth/csrf') data = { csrf_token: 'synthetic' };
  else if (route === '/auth/refresh') data = { access_token: 'synthetic', csrf_token: 'synthetic', expires_in: 300 };
  else if (route === '/auth/me') data = { id: actor, role, display_name: 'Operador sintetico F12', email: 'synthetic@example.invalid', department_id: department, permissions: role === 'admin' ? ['administration:manage', 'tasks:manage', 'planning:manage', 'exports:read', 'evaluations:read'] : role === 'colaborador' ? ['tasks:transition'] : ['tasks:manage', 'exports:read', 'evaluations:read'] };
  else if (route === '/configuration') data = { revision: 12, branding: { token_overrides: {} }, flags, page_sizes: [5, 10, 20, 50] };
  else if (route === '/imports') data = pageOf([imported]);
  else if (route === '/imports/' + importId) data = imported;
  else if (route === '/executive-reports') data = pageOf([report]);
  else if (route === '/evaluations') data = pageOf([{ id: identity(5), status: 'final', period_start: '2026-01-01', period_end: '2026-10-31' }]);
  else if (route === '/admin/operations/health') data = { database: { status: 'ready', revision: '20261126_0011' }, vault_available: true, evidence_configuration_verified: false, agent, last_verified_backup: backup, purge_authorized: false, customer_operational_acceptance: false };
  else if (route === '/admin/operations/backups') data = pageOf([backup]);
  else if (route === '/admin/operations/jobs') data = pageOf([{ id: identity(10), kind: 'backup', version: 2, created_at: moment, updated_at: moment, state: 'succeeded', attempt: 1 }]);
  else if (route === '/admin/operations/retention-policies') data = pageOf([policy]);
  else if (route === '/users') data = pageOf([{ id: actor, display_name: 'Responsable sintetico F12', is_active: true }]);
  else if (route === '/admin/operations/principals') data = pageOf([{ id: identity(7), name: 'Agente sintetico F12', is_active: true }]);
  else throw Error('Unexpected synthetic API: ' + method + ' ' + route);
  return { status: 200, data };
}

async function preview() {
  const certificate = [
    'import datetime, ipaddress, json',
    'from cryptography import x509',
    'from cryptography.hazmat.primitives import hashes, serialization',
    'from cryptography.hazmat.primitives.asymmetric import rsa',
    'from cryptography.x509.oid import NameOID',
    'key = rsa.generate_private_key(public_exponent=65537, key_size=2048)',
    'name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])',
    'now = datetime.datetime.now(datetime.UTC)',
    'cert = x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1)).not_valid_after(now+datetime.timedelta(hours=1)).add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False).sign(key, hashes.SHA256())',
    'print(json.dumps({"key": key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode(), "cert": cert.public_bytes(serialization.Encoding.PEM).decode()}))',
  ].join('\n');
  const credentials = JSON.parse(execFileSync(path.resolve('backend/.venv/Scripts/python'), ['-c', certificate], { encoding: 'utf8' }));
  const root = path.resolve('dist/ocote-app/browser');
  const types = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.png': 'image/png', '.webp': 'image/webp', '.ico': 'image/x-icon' };
  const server = https.createServer(credentials, (request, response) => {
    try {
      const url = new URL(request.url, origin);
      if (request.method !== 'GET' || url.pathname.startsWith('/api/')) { response.writeHead(503); response.end(); return; }
      let file = path.resolve(root, '.' + decodeURIComponent(url.pathname));
      if (file !== root && !file.startsWith(root + path.sep)) { response.writeHead(404); response.end(); return; }
      if (!fs.existsSync(file) || !fs.statSync(file).isFile()) file = path.join(root, 'index.html');
      response.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' }); response.end(fs.readFileSync(file));
    } catch { response.writeHead(404); response.end(); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(8445, '127.0.0.1', resolve); });
  return server;
}

async function main() {
  const server = await preview();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'ocote-f12-chrome-'));
  const artifacts = fs.mkdtempSync(path.join(os.tmpdir(), 'ocote-f12-visual-'));
  const chrome = spawn(process.env.CHROME_BIN || 'C:/Program Files/Google/Chrome/Application/chrome.exe', ['--headless=new', '--remote-debugging-port=0', '--user-data-dir=' + profile, '--ignore-certificate-errors', '--disable-gpu', '--no-first-run', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
  const pending = new Map(), errors = [], requests = [], results = [];
  let socket, session, sequence = 0;
  try {
    const address = await new Promise((resolve, reject) => { let output = ''; chrome.stderr.on('data', data => { output += data; const match = output.match(/DevTools listening on (ws:\/\/[^\s]+)/); if (match) resolve(match[1]); }); chrome.once('error', reject); chrome.once('exit', () => reject(Error('Chrome exited before CDP'))); });
    socket = new WebSocket(address); await once(socket, 'open');
    const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => { const id = ++sequence; pending.set(id, { resolve, reject }); socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) })); });
    socket.addEventListener('message', async event => {
      const message = JSON.parse(event.data);
      if (message.id) { const callback = pending.get(message.id); if (callback) { pending.delete(message.id); message.error ? callback.reject(Error(JSON.stringify(message.error))) : callback.resolve(message.result); } return; }
      if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text);
      if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') errors.push(message.params.args.map(argument => argument.value || argument.description || '').join(' '));
      if (message.method !== 'Fetch.requestPaused') return;
      const requestId = message.params.requestId;
      try {
        const request = message.params.request, url = new URL(request.url);
        if (url.origin !== origin) throw Error('External request blocked: ' + url.origin);
        if (!url.pathname.startsWith('/api/v1/')) { await send('Fetch.continueRequest', { requestId }, session); return; }
        const route = url.pathname.slice(7), response = synthetic(route, request.method);
        requests.push({ method: request.method, path: route, role, intercepted: true });
        await send('Fetch.fulfillRequest', { requestId, responseCode: response.status, responseHeaders: [{ name: 'Content-Type', value: response.status >= 400 ? 'application/problem+json' : 'application/json' }, { name: 'Cache-Control', value: 'no-store' }], body: Buffer.from(JSON.stringify(response.data)).toString('base64') }, session);
      } catch (error) { errors.push(String(error)); await send('Fetch.failRequest', { requestId, errorReason: 'BlockedByClient' }, session).catch(() => undefined); }
    });
    const target = await send('Target.createTarget', { url: 'about:blank' });
    session = (await send('Target.attachToTarget', { targetId: target.targetId, flatten: true })).sessionId;
    const page = (method, params = {}) => send(method, params, session);
    await page('Page.enable'); await page('Runtime.enable'); await page('Network.enable'); await page('Security.setIgnoreCertificateErrors', { ignore: true });
    await page('Fetch.enable', { patterns: [{ urlPattern: '*', requestStage: 'Request' }] });
    const evaluate = async expression => { const response = await page('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (response.exceptionDetails) throw Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text); return response.result.value; };
    const wait = expression => evaluate(`new Promise((resolve,reject)=>{const end=Date.now()+25000;function check(){if(${expression})resolve(true);else if(Date.now()>end)reject(Error('DOM condition timed out'));else requestAnimationFrame(check);}check();})`);
    const click = expression => evaluate(`(()=>{const element=${expression};if(!element)throw Error('Missing control');element.click();})()`);
    const button = label => `[...document.querySelectorAll('button')].find(element=>element.textContent.includes(${JSON.stringify(label)}))`;
    const control = label => `document.querySelector(${JSON.stringify('button[aria-label="' + label + '"]')})`;
    const tab = label => `[...document.querySelectorAll('[role=tab]')].find(element=>element.textContent.includes(${JSON.stringify(label)}))`;
    const close = async () => { await page('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 }); await page('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 }); await wait('!document.querySelector("mat-dialog-container")'); };
    const navigate = async (route, condition) => { const result = await page('Page.navigate', { url: origin + route }); if (result.errorText) throw Error(result.errorText); await wait(condition); };
    const inspect = async name => {
      await evaluate('document.fonts.ready');
      await evaluate(`Promise.all([...document.images].map(image=>image.decode()))`);
      await evaluate('Promise.all(document.getAnimations().map(animation=>animation.finished.catch(()=>{})))');
      const metrics = await evaluate(`({width:innerWidth,scroll:document.documentElement.scrollWidth,images:[...document.images].map(image=>({src:image.currentSrc,naturalWidth:image.naturalWidth})),overflow:[...document.querySelectorAll('h1,h2,h3,button,input,img,textarea,mat-select')].filter(element=>{const box=element.getBoundingClientRect();return box.width>0 && (box.left<-.5 || box.right>innerWidth+.5) && !element.closest('[role=tablist],.table-wrap,nav.main-nav');}).map(element=>element.tagName+':'+element.textContent.trim().slice(0,60)),bodyLength:document.body.innerText.trim().length,passwords:[...document.querySelectorAll('input[type=password]')].every(element=>!element.value)})`);
      if (metrics.scroll > metrics.width || metrics.overflow.length || metrics.bodyLength < 80 || !metrics.passwords) throw Error(name + ':' + JSON.stringify(metrics));
      const contrast = await evaluate(`(()=>{
        const canvas=document.createElement('canvas');canvas.width=canvas.height=1;const context=canvas.getContext('2d',{willReadFrequently:true});
        const color=value=>{context.clearRect(0,0,1,1);context.fillStyle=value;context.fillRect(0,0,1,1);const channels=[...context.getImageData(0,0,1,1).data];return channels.map((value,index)=>value/255);};
        const blend=(front,back)=>[0,1,2].map(index=>front[index]*front[3]+back[index]*(1-front[3]));
        const luminance=channels=>channels.map(value=>value<=.04045?value/12.92:((value+.055)/1.055)**2.4).reduce((sum,value,index)=>sum+value*[.2126,.7152,.0722][index],0);
        const root=document.querySelector('mat-dialog-container')||document.body;let tested=0;const failures=[];
        for(const element of root.querySelectorAll('h1,h2,h3,p,strong,td,th,dt,dd,mat-label,.mdc-button__label')){
          const box=element.getBoundingClientRect();if(!element.textContent.trim()||!element.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})||box.bottom<0||box.top>innerHeight||box.right<0||box.left>innerWidth||element.closest(':disabled,[aria-disabled=true],.mat-form-field-disabled,.mdc-text-field--disabled')||element.closest('mat-form-field')?.querySelector(':disabled,[aria-disabled=true]'))continue;
          const style=getComputedStyle(element);let background=[1,1,1];const chain=[];for(let parent=element;parent;parent=parent.parentElement)chain.unshift(parent);
          for(const parent of chain)background=blend(color(getComputedStyle(parent).backgroundColor),background);
          const foreground=blend(color(style.color),background);const values=[luminance(foreground),luminance(background)];const ratio=(Math.max(...values)+.05)/(Math.min(...values)+.05);
          const large=parseFloat(style.fontSize)>=24||(parseFloat(style.fontSize)>=18.66&&parseInt(style.fontWeight)>=700);tested++;if(ratio<(large?3:4.5))failures.push({text:element.textContent.trim().slice(0,60),ratio,foreground:style.color,background});
        }return {tested,failures};})()`);
      if (contrast.failures.length) throw Error(name + ':contrast:' + JSON.stringify(contrast));
      metrics.contrast = contrast;
      const image = await page('Page.captureScreenshot', { captureBeyondViewport: false }); fs.writeFileSync(path.join(artifacts, name + '.png'), Buffer.from(image.data, 'base64')); results.push({ name, ...metrics });
    };
    for (const width of [1280, 360]) {
      await page('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: false });
      role = 'admin';
      await navigate('/importaciones', 'document.body.innerText.includes("Historial de lotes")'); await inspect('imports-upload-' + width);
      await click(control('Abrir lote')); await wait('document.body.innerText.includes("Tarea sintetica 1")'); await inspect('imports-preview-' + width);
      await click(button('Confirmar lote')); await wait('document.querySelector("mat-dialog-container")'); await inspect('imports-confirm-' + width); await close();
      await evaluate(`(()=>{const field=[...document.querySelectorAll('mat-form-field')].find(element=>element.querySelector('mat-label')?.textContent.trim()==='Motivo de simulacion')?.querySelector('textarea');if(!field)throw Error('Missing reason');field.value='Motivo sintetico F12 para conflicto';field.dispatchEvent(new Event('input',{bubbles:true}));})()`);
      await click(button('Simular lote')); await wait('document.body.innerText.includes("synthetic-f12-409")');
      if (!await evaluate(`${button('Simular lote')}.disabled`)) throw Error('409 did not block preview');
      await inspect('imports-conflict-' + width);
      await navigate('/reportes-ejecutivos', 'document.body.innerText.includes("America/Mexico_City")'); await inspect('executive-reports-' + width);
      await click(button('Generar reporte')); await wait('document.querySelector("mat-dialog-container mat-select")'); await inspect('executive-report-editor-' + width); await close();
      await navigate('/administracion/operaciones', 'document.body.innerText.includes("Base de datos")'); await inspect('operations-health-' + width);
      await click(tab('Respaldos')); await wait('document.body.innerText.includes("530000")'); await inspect('operations-backups-' + width);
      await click(button('Solicitar respaldo')); await wait('document.querySelector("mat-dialog-container input[type=password]")'); await inspect('backup-request-' + width); await close();
      await click(control('Solicitar restore aislado')); await wait('document.querySelector("mat-dialog-container input[type=password]")'); await inspect('isolated-restore-request-' + width); await close();
      await click(tab('Retencion')); await wait('document.body.innerText.includes("Aprobacion sintetica F12")'); await inspect('retention-policies-' + width);
      await click(control('Editar politica de retencion')); await wait('document.querySelector("mat-dialog-container input[type=number]")'); await inspect('retention-editor-' + width); await close();
      await click(tab('Agente')); await wait('document.body.innerText.includes("Autenticacion")'); await inspect('operations-agent-' + width);
      await click(button('Editar agente')); await wait('document.querySelectorAll("mat-dialog-container input[type=password]").length===2'); await inspect('agent-editor-' + width); await close();
      await click(button('Desactivar agente')); await wait('document.querySelector("mat-dialog-container input[type=password]")'); await inspect('agent-deactivation-' + width); await close();
      flags.imports = false;
      const disabled = requests.length;
      await navigate('/importaciones', 'document.body.innerText.includes("Importaciones no disponibles")'); await inspect('imports-disabled-' + width);
      if (requests.slice(disabled).some(request => request.path.startsWith('/imports'))) throw Error('Disabled imports requested data'); flags.imports = true;
      role = 'colaborador'; const denied = requests.length;
      await navigate('/administracion/operaciones', 'document.body.innerText.includes("Acceso no disponible")'); await inspect('operations-role-denied-' + width);
      if (requests.slice(denied).some(request => request.path.startsWith('/admin/operations'))) throw Error('Collaborator requested operations');
    }
    if (errors.length) throw Error(errors.join('\n'));
    fs.writeFileSync(path.join(artifacts, 'results.json'), JSON.stringify({ synthetic: true, origin, providerHomologation: false, results, requests, errors }, null, 2));
    console.log(JSON.stringify({ artifacts, screenshots: results.length, requests: requests.length, errors }));
  } catch (error) { fs.writeFileSync(path.join(artifacts, 'failure.json'), JSON.stringify({ error: String(error), errors, requests, results }, null, 2)); console.error('F12 visual artifacts: ' + artifacts); throw error; }
  finally {
    if (socket) socket.close();
    if (chrome.exitCode === null) { const stopped = once(chrome, 'exit'); chrome.kill(); await stopped; }
    await new Promise(resolve => server.close(resolve));
    fs.rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });