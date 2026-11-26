const { spawn } = require('node:child_process');
const { once } = require('node:events');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const origin = process.env.OCOTE_F10_PREVIEW;
if (!/^https:\/\/localhost:\d+$/.test(origin || '') || origin === 'https://localhost:8443') throw Error('A separate loopback HTTPS preview is required');
const identity = number => '00000000-0000-4000-8000-' + String(number).padStart(12, '0');
const departmentId = identity(1), userId = identity(2), taskId = identity(3);
const policy = { version: 1, password_min_length: 12, require_upper: true, require_lower: true, require_digit: true, require_symbol: true, access_ttl_seconds: 300, refresh_absolute_seconds: 86400, idle_timeout_seconds: 900, failed_attempt_threshold: 5, failed_window_seconds: 300, lockout_seconds: 300, page_sizes: [5, 10, 20, 50], import_max_rows: 1000, import_max_bytes: 10485760, export_max_bytes: 16777216 };
const flags = Object.fromEntries(['integrations', 'calendar', 'notifications', 'email_notifications', 'corporate_messaging', 'calendar_feeds'].map(code => [code, true]));
const configuration = () => ({ revision: 11, branding: { version: 0, organization_name: 'OCOTE', organization_name_version: 0, token_overrides: {}, logo_asset_id: null }, flags, page_sizes: policy.page_sizes, security_policy: policy, modules: Object.keys(flags).map(code => ({ code, installed: true, enabled: flags[code], version: 1 })) });
const preferences = { id: identity(4), version: 1, user_id: userId, opt_in: true, channels: ['in_app', 'email', 'messaging'], timezone: 'America/Mexico_City', quiet_start: '22:00', quiet_end: '07:00' };
const feed = { id: identity(5), version: 1, name: 'Calendario sintetico F10', expires_at: '2027-01-02T18:00:00Z', revoked_at: null };
const connectors = ['smtp', 'slack', 'teams', 'telegram'].map((provider, index) => ({ id: identity(10 + index), version: 1, name: provider.toUpperCase() + ' sintetico F10', provider, scope_kind: 'organization', department_id: null, config_revision: 1, is_active: false, tested_at: '2026-11-26T14:00:00Z', secret_configured: true, config: { provider, host: { smtp: 'smtp.example.invalid', slack: 'hooks.slack.com', teams: 'synthetic.webhook.office.com', telegram: 'api.telegram.org' }[provider], approved_addresses: ['8.8.8.8'], allow_private_endpoint: false, connect_timeout_seconds: 3, read_timeout_seconds: 5, rate_per_minute: 10, audience_approved: true, destination: 'Audiencia sintetica F10', port: 587, security: 'starttls', authentication: 'login', username: 'synthetic@example.invalid', sender_email: 'synthetic@example.invalid', sender_name: 'OCOTE sintetico', test_recipient: 'synthetic@example.invalid' } }));
const rule = { id: identity(20), version: 1, name: 'Vencimiento sintetico F10', department_id: departmentId, trigger: 'upcoming_due', recipient_mode: 'assignee', channels: ['in_app', 'email'], connector_ids: [connectors[0].id], threshold_days: 3, day_basis: 'business', max_age_hours: 24, max_attempts: 3, retry_base_seconds: 30, enabled: true };
const principal = { id: identity(21), version: 1, name: 'Worker sintetico F10', department_ids: [departmentId], approved_scopes: ['notifications:dispatch'], is_active: true };
const pageOf = items => ({ items, next_cursor: null });
let role = 'admin';
function synthetic(endpoint, method) {
  if (method === 'PATCH' && endpoint === '/notification-preferences') return { status: 409, data: { status: 409, code: 'VERSION_CONFLICT', request_id: 'synthetic-f10-409' } };
  if (method === 'POST' && endpoint === '/integrations/calendar-feeds') return { status: 201, data: { ...feed, capability: 'SYNTHETIC-NOT-A-VALID-CAPABILITY' } };
  let data;
  if (endpoint === '/auth/csrf') data = { csrf_token: 'synthetic' };
  else if (endpoint === '/auth/refresh') data = { access_token: 'synthetic', csrf_token: 'synthetic', expires_in: 300 };
  else if (endpoint === '/auth/me') data = { id: userId, display_name: 'Operador sintetico F10', email: 'synthetic@example.invalid', department_id: departmentId, role, permissions: role === 'admin' ? ['administration:manage', 'tasks:manage'] : ['tasks:transition'] };
  else if (['/configuration', '/admin/configuration'].includes(endpoint)) data = configuration();
  else if (endpoint === '/notifications') data = { ...pageOf([{ id: identity(30), version: 1, created_at: '2026-11-26T14:00:00Z', read_at: null, safe_projection: { trigger: 'assignment', resource_type: 'task', resource_id: taskId } }]), unread_count: 1 };
  else if (endpoint === '/notification-preferences') data = preferences;
  else if (endpoint === '/integrations/calendar-feeds') data = pageOf([feed]);
  else if (endpoint === '/notification-connectors') data = pageOf(connectors);
  else if (endpoint === '/notification-rules') data = pageOf([rule]);
  else if (endpoint === '/notifications/service-principals') data = pageOf([principal]);
  else if (endpoint === '/catalogs/departments') data = pageOf([{ id: departmentId, version: 1, name: 'Departamento sintetico F10', is_active: true }]);
  else if (/^\/notification-connectors\/[^/]+\/health-checks$/.test(endpoint)) data = pageOf([{ id: identity(31), status: 'passed', result_code: 'PROVIDER_ACCEPTED', latency_ms: 12, created_at: '2026-11-26T14:00:00Z' }]);
  else throw Error('Unexpected synthetic API: ' + method + ' ' + endpoint);
  return { status: 200, data };
}

async function main() {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'ocote-f10-chrome-'));
  const artifacts = fs.mkdtempSync(path.join(os.tmpdir(), 'ocote-f10-visual-'));
  const chrome = spawn(process.env.CHROME_BIN || 'C:/Program Files/Google/Chrome/Application/chrome.exe', ['--headless=new', '--remote-debugging-port=0', '--user-data-dir=' + profile, '--ignore-certificate-errors', '--disable-gpu', '--no-first-run', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
  const pending = new Map(), errors = [], requests = [], results = [];
  let socket, session, sequence = 0;
  try {
    const endpoint = await new Promise((resolve, reject) => { let output = ''; chrome.stderr.on('data', data => { output += data; const match = output.match(/DevTools listening on (ws:\/\/[^\s]+)/); if (match) resolve(match[1]); }); chrome.once('error', reject); chrome.once('exit', () => reject(Error('Chrome exited before CDP'))); });
    socket = new WebSocket(endpoint); await once(socket, 'open');
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
        const endpoint = url.pathname.slice(7), response = synthetic(endpoint, request.method);
        requests.push({ method: request.method, path: endpoint, role, intercepted: true });
        await send('Fetch.fulfillRequest', { requestId, responseCode: response.status, responseHeaders: [{ name: 'Content-Type', value: response.status >= 400 ? 'application/problem+json' : 'application/json' }, { name: 'Cache-Control', value: 'no-store' }], body: Buffer.from(JSON.stringify(response.data)).toString('base64') }, session);
      } catch (error) { errors.push(String(error)); await send('Fetch.failRequest', { requestId, errorReason: 'BlockedByClient' }, session).catch(() => undefined); }
    });
    const target = await send('Target.createTarget', { url: 'about:blank' });
    session = (await send('Target.attachToTarget', { targetId: target.targetId, flatten: true })).sessionId;
    const page = (method, params = {}) => send(method, params, session);
    await page('Page.enable'); await page('Runtime.enable'); await page('Network.enable'); await page('Security.setIgnoreCertificateErrors', { ignore: true });
    await page('Fetch.enable', { patterns: [{ urlPattern: '*', requestStage: 'Request' }] });
    const evaluate = async expression => { const response = await page('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (response.exceptionDetails) throw Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text); return response.result.value; };
    const wait = expression => evaluate(`new Promise((resolve,reject)=>{const end=Date.now()+25000;function check(){if(${expression})resolve(true);else if(Date.now()>end)reject(Error('DOM condition timed out: '+${JSON.stringify(expression)}));else requestAnimationFrame(check);}check();})`);
    const click = expression => evaluate(`(()=>{const element=${expression};if(!element)throw Error('Missing control');element.click();})()`);
    const button = label => `[...document.querySelectorAll('button')].find(element=>element.textContent.includes(${JSON.stringify(label)}))`;
    const tab = label => `[...document.querySelectorAll('[role=tab]')].find(element=>element.textContent.includes(${JSON.stringify(label)}))`;
    const control = label => `document.querySelector(${JSON.stringify('button[aria-label="' + label + '"]')})`;
    const close = async () => { await page('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 }); await page('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 }); await wait('!document.querySelector("mat-dialog-container")'); };
    const navigate = async (route, condition) => { const result = await page('Page.navigate', { url: origin + route }); if (result.errorText) throw Error(result.errorText); await wait(condition); };
    const inspect = async name => {
      await evaluate('document.fonts.ready'); await wait('[...document.images].every(image=>image.complete && image.naturalWidth>0)');
      await evaluate('Promise.all(document.getAnimations().map(animation=>animation.finished.catch(()=>{})))');
      const metrics = await evaluate(`({width:innerWidth,scroll:document.documentElement.scrollWidth,images:[...document.images].map(image=>({src:image.currentSrc,naturalWidth:image.naturalWidth})),overflow:[...document.querySelectorAll('h1,h2,h3,button,input,img,textarea')].filter(element=>{const box=element.getBoundingClientRect();return box.width>0 && (box.left<-.5 || box.right>innerWidth+.5) && !element.closest('[role=tablist]');}).map(element=>element.tagName+':'+element.textContent.trim().slice(0,40)),bodyLength:document.body.innerText.trim().length,passwords:[...document.querySelectorAll('input[type=password]')].every(element=>!element.value)})`);
      if (metrics.scroll > metrics.width || metrics.overflow.length || metrics.bodyLength < 100 || !metrics.passwords) throw Error(name + ':' + JSON.stringify(metrics));
      const image = await page('Page.captureScreenshot', { captureBeyondViewport: false }); fs.writeFileSync(path.join(artifacts, name + '.png'), Buffer.from(image.data, 'base64')); results.push({ name, ...metrics });
    };
    for (const width of [1280, 360]) {
      await page('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: false });
      await navigate('/mi-actividad', 'document.body.innerText.includes("No leidas: 1")'); await inspect('inbox-' + width);
      await click(tab('Preferencias')); await wait('document.body.innerText.includes("America/Mexico_City")'); await inspect('preferences-' + width);
      await click(control('Editar preferencias')); await wait('document.querySelector("mat-dialog-container textarea")'); await inspect('preferences-editor-' + width);
      await evaluate('(()=>{const input=document.querySelector("mat-dialog-container textarea");input.value="Motivo sintetico F10 para conflicto";input.dispatchEvent(new Event("input",{bubbles:true}));})()');
      await click('document.querySelector("mat-dialog-container button[type=submit]")'); await wait('document.querySelector("mat-dialog-container").innerText.includes("synthetic-f10-409")');
      if (!await evaluate('document.querySelector("mat-dialog-container button[type=submit]").disabled && document.querySelector("mat-dialog-container textarea").value.includes("conflicto")')) throw Error('409 did not retain and block draft'); await inspect('conflict-' + width);
      await click(button('Descartar cambios y recargar')); await wait('!document.querySelector("mat-dialog-container")');
      await click(tab('Calendarios')); await wait('document.body.innerText.includes("Calendario sintetico F10")'); await inspect('feeds-' + width);
      await click(button('Calendario')); await wait('document.querySelector("mat-dialog-container input[type=datetime-local]")');
      await evaluate('(()=>{for(const [selector,value] of [["input[type=text]","Feed sintetico F10"],["input[type=datetime-local]","2026-12-01T18:00"],["textarea","Motivo sintetico F10 para calendario"]]){const input=document.querySelector("mat-dialog-container "+selector);input.value=value;input.dispatchEvent(new Event("input",{bubbles:true}));}})()');
      await click('document.querySelector("mat-dialog-container button[type=submit]")'); await wait('document.querySelector("textarea[readonly]")');
      if (await evaluate('!!document.querySelector("a[href*=capability]")')) throw Error('Private capability exposed as navigation'); await inspect('feed-capability-synthetic-' + width);
      await click(button('Cerrar')); await wait('!document.querySelector("textarea[readonly]")');
      await navigate('/administracion/notificaciones', 'document.body.innerText.includes("SMTP sintetico F10")'); await inspect('connectors-' + width);
      for (let index = 0; index < connectors.length; index++) {
        await click(`document.querySelectorAll('button[aria-label="Editar conector"]')[${index}]`); await wait('document.querySelector("mat-dialog-container input[type=password]")'); await inspect(connectors[index].provider + '-editor-' + width); await close();
      }
      await click(control('Probar conector')); await wait('document.body.innerText.includes("Destino exacto aprobado")'); await inspect('test-confirmation-' + width); await close();
      await click(control('Historial de pruebas')); await wait('document.body.innerText.includes("PROVIDER_ACCEPTED")'); await inspect('connector-health-' + width);
      await click(tab('Reglas')); await wait('document.body.innerText.includes("Vencimiento sintetico F10")'); await inspect('rules-' + width);
      await click(control('Editar regla')); await wait('document.querySelector("mat-dialog-container textarea")'); await inspect('rule-editor-' + width); await close();
      await click(tab('Actores tecnicos')); await wait('document.body.innerText.includes("Worker sintetico F10")'); await inspect('principals-' + width);
      await click(control('Editar actor tecnico')); await wait('document.querySelector("mat-dialog-container textarea")'); await inspect('principal-editor-' + width); await close();
      role = 'colaborador'; const before = requests.length;
      await navigate('/mi-actividad', 'document.body.innerText.includes("No leidas: 1")'); await inspect('collaborator-inbox-' + width);
      if (requests.slice(before).some(request => /^\/(notification-connectors|notification-rules|notifications\/service-principals)/.test(request.path))) throw Error('Collaborator requested administration');
      role = 'admin'; flags.notifications = false; flags.calendar_feeds = false;
      const disabled = requests.length; await navigate('/mi-actividad', 'document.body.innerText.includes("Actividad personal no disponible")'); await inspect('disabled-' + width);
      if (requests.slice(disabled).some(request => /^\/(notifications$|notification-preferences|integrations\/calendar-feeds)/.test(request.path))) throw Error('Disabled modules requested personal data');
      flags.notifications = true; flags.calendar_feeds = true;
    }
    if (errors.length) throw Error(errors.join('\n'));
    fs.writeFileSync(path.join(artifacts, 'results.json'), JSON.stringify({ synthetic: true, providerHomologation: false, origin, results, requests, errors }, null, 2));
    console.log(JSON.stringify({ artifacts, screenshots: results.length, requests: requests.length, errors }));
  } catch (error) { fs.writeFileSync(path.join(artifacts, 'failure.json'), JSON.stringify({ error: String(error), errors, requests, results }, null, 2)); console.error('F10 visual artifacts: ' + artifacts); throw error; }
  finally { if (socket) socket.close(); const stopped = once(chrome, 'exit'); chrome.kill(); await stopped; fs.rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });