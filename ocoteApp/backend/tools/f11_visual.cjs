const { execFileSync, spawn } = require('node:child_process');
const { once } = require('node:events');
const fs = require('node:fs');
const https = require('node:https');
const os = require('node:os');
const path = require('node:path');

const origin = process.env.OCOTE_F11_PREVIEW;
if (!/^https:\/\/localhost:\d+$/.test(origin || '') || origin === 'https://localhost:8443') throw Error('A separate loopback HTTPS preview is required');
const identity = number => '00000000-0000-4000-8000-' + String(number).padStart(12, '0');
const departmentId = identity(1), userId = identity(2), taskId = identity(3), transactionId = identity(4);
const moment = '2026-11-26T14:00:00Z';
const endpoint = url => ({ url, host: new URL(url).hostname, approved_addresses: ['93.184.216.34'], allow_private_endpoint: false, ca_certificates_pem: null, connect_timeout_seconds: 3, read_timeout_seconds: 5, rate_per_minute: 10, audience_approved: true });
const sso = { emergency_admin_id: userId, revocation_window_seconds: 300, jit_enabled: false, jit_mappings: [], jit_email_attribute: null, jit_name_attribute: null };
const configs = [
  { provider: 'oidc', ...sso, issuer: 'https://idp.example.invalid', client_id: 'synthetic-client', token_auth_method: 'client_secret_basic', authorization_endpoint: endpoint('https://idp.example.invalid/authorize'), token_endpoint: endpoint('https://idp.example.invalid/token'), jwks_endpoint: endpoint('https://idp.example.invalid/jwks') },
  { provider: 'saml', ...sso, entity_id: 'synthetic-entity', idp_certificate_pem: 'SYNTHETIC PUBLIC CERTIFICATE', sp_certificate_pem: 'SYNTHETIC PUBLIC CERTIFICATE', sso_endpoint: endpoint('https://idp.example.invalid/sso') },
  { provider: 'ldap', ...sso, ...endpoint('https://ldap.example.invalid'), port: 636, security: 'ldaps', bind_dn: 'cn=synthetic,dc=example,dc=invalid', user_search_base: 'dc=example,dc=invalid', username_attribute: 'uid', subject_attribute: 'entryUUID' },
  { provider: 'github', api_endpoint: endpoint('https://api.github.com'), web_origin: 'https://github.com', repositories: [{ repository_id: '123', path: 'synthetic/repository' }] },
  { provider: 'gitlab', api_endpoint: endpoint('https://gitlab.example.invalid/api/v4'), web_origin: 'https://gitlab.example.invalid', repositories: [{ repository_id: '456', path: 'synthetic/repository' }] },
  { provider: 'outgoing_webhook', endpoint: endpoint('https://receiver.example.invalid/events') },
];
delete configs[2].url;
const connectors = configs.map((config, index) => ({ id: identity(10 + index), version: 2, name: config.provider.toUpperCase() + ' sintetico F11', provider: config.provider, kind: index < 3 ? 'sso' : index < 5 ? 'devops' : 'outgoing_webhook', scope_kind: 'organization', department_id: null, config_revision: 1, tested_version: 1, tested_at: moment, is_active: false, secret_configured: true, config }));
const principal = { id: identity(20), version: 2, name: 'Actor sintetico F11', is_active: true, department_ids: [departmentId], approved_scopes: ['tasks:read', 'notifications:dispatch'] };
const apiKey = { id: identity(21), version: 1, name: 'Credencial sintetica F11', service_principal_id: principal.id, owner_user_id: userId, scopes: ['tasks:read'], department_ids: [departmentId], rate_per_minute: 10, allowed_networks: ['192.0.2.0/24'], expires_at: '2026-12-01T18:00:00Z', revoked_at: null };
const binding = { id: identity(22), version: 2, integration_id: connectors[0].id, user_id: userId, issuer: 'https://idp.example.invalid', subject: 'synthetic-stable-subject', created_at: moment, last_authenticated_at: moment, revoked_at: null };
const subscription = { id: identity(23), version: 2, integration_id: connectors[5].id, owner_user_id: userId, event_types: ['assignment'], department_ids: [departmentId], max_attempts: 3, retry_base_seconds: 30, max_delay_seconds: 600, enabled: false };
const delivery = { id: identity(24), version: 4, subscription_id: subscription.id, outbox_id: identity(25), state: 'dead_letter', attempt_count: 3, max_attempts: 3, next_attempt_at: moment, created_at: moment, retry_of_id: null };
const link = { id: identity(26), version: 1, task_id: taskId, integration_id: connectors[3].id, kind: 'branch', repository_id: '123', external_id: 'feature/synthetic-f11', canonical_url: 'https://github.com/synthetic/repository/tree/feature%2Fsynthetic-f11', safe_projection: { name: 'feature/synthetic-f11' }, deactivated_at: null };
const flags = Object.fromEntries(['integrations', 'sso', 'devops', 'api_keys', 'outgoing_webhooks'].map(code => [code, true]));
const pageOf = items => ({ items, next_cursor: null });
let role = 'admin';
function synthetic(route, method) {
  if (route === '/auth/csrf' && role === 'anonymous') return { status: 401, data: { code: 'INVALID_CREDENTIALS' } };
  if (method === 'PATCH' && route === '/integrations/configs/' + connectors[0].id) return { status: 409, data: { code: 'VERSION_CONFLICT', request_id: 'synthetic-f11-409' } };
  if (method === 'POST' && route === '/integrations/api-keys') return { status: 201, data: { ...apiKey, api_key: 'SYNTHETIC-NOT-A-VALID-API-KEY' } };
  let data;
  if (route === '/auth/csrf') data = { csrf_token: 'synthetic' };
  else if (route === '/auth/refresh') data = { access_token: 'synthetic', csrf_token: 'synthetic', expires_in: 300 };
  else if (route === '/auth/me') data = { id: userId, role, display_name: 'Operador sintetico F11', email: 'synthetic@example.invalid', department_id: departmentId, permissions: role === 'admin' ? ['administration:manage', 'tasks:manage'] : ['tasks:transition'] };
  else if (route === '/configuration') data = { revision: 12, branding: { token_overrides: {} }, flags, page_sizes: [5, 10, 20, 50] };
  else if (route === '/integrations/configs') data = pageOf(connectors);
  else if (route === '/integrations/service-principals') data = pageOf([principal]);
  else if (route === '/integrations/api-keys') data = pageOf([apiKey]);
  else if (route === '/integrations/external-identities' || route === '/auth/sso/identities') data = pageOf([binding]);
  else if (route === '/integrations/webhook-subscriptions') data = pageOf([subscription]);
  else if (route === '/integrations/webhook-deliveries') data = pageOf([delivery]);
  else if (route === '/integrations/webhook-deliveries/' + delivery.id + '/attempts') data = pageOf([{ id: identity(27), attempt_no: 3, outcome: 'ambiguous', status_code: null, result_code: 'LEASE_EXPIRED', latency_ms: 0, created_at: moment }]);
  else if (/^\/integrations\/configs\/[^/]+\/checks$/.test(route)) data = pageOf([{ id: identity(28), status: 'passed', result_code: 'F11_SYNTHETIC_VERIFIED', latency_ms: 12, created_at: moment }]);
  else if (/^\/integrations\/devops\/[^/]+\/inbox$/.test(route)) data = pageOf([{ id: identity(29), event_type: 'push', delivery_id: 'synthetic-delivery', created_at: moment }]);
  else if (route === '/catalogs/departments') data = pageOf([{ id: departmentId, name: 'Departamento sintetico F11', is_active: true }]);
  else if (route === '/users' || route === '/catalogs/assignees') data = pageOf([{ id: userId, display_name: 'Operador sintetico F11', role: 'admin', is_active: true }]);
  else if (route === '/auth/sso/providers') data = pageOf(flags.sso ? connectors.slice(0, 3).map(row => ({ id: row.id, name: row.name, provider: row.provider })) : []);
  else if (route === '/auth/sso/' + connectors[2].id + '/start') data = { transaction_id: transactionId, authorization_url: null, expires_at: '2026-11-26T14:05:00Z', state: 'SYNTHETIC-STATE-NOT-AN-OPERATIONAL-SECRET' };
  else if (route === '/auth/sso/transactions/' + transactionId) data = { transaction_id: transactionId, purpose: 'probe', provider_name: 'OIDC sintetico F11', expires_at: '2026-11-26T14:05:00Z' };
  else if (route === '/tasks/' + taskId) data = { id: taskId, version: 4, objective_id: identity(30), title: 'Tarea sintetica F11', description: 'Trazabilidad sintetica', assignee_id: userId, stage_id: identity(31), start_date: '2026-11-01', due_date: '2026-12-01', original_due_date: '2026-12-01', progress_percent: 0, completed_at: null, annual_plan: { title: 'Plan sintetico' }, objective: { title: 'Objetivo sintetico' }, priority: { name: 'Normal sintetica' } };
  else if (route === '/catalogs/workflow') data = { stages: [{ id: identity(31), name: 'Abierta', kind: 'open' }], transitions: [] };
  else if (route === '/tasks/' + taskId + '/external-links') data = pageOf([link]);
  else if (route === '/tasks/' + taskId + '/external-link-providers') data = pageOf([{ id: connectors[3].id, name: connectors[3].name, provider: connectors[3].provider, repositories: connectors[3].config.repositories }]);
  else if (route === '/tasks/' + taskId + '/subtasks') data = pageOf([]);
  else if (route === '/tasks/' + taskId + '/evidence') data = { ...pageOf([]), uploads_configured: false, upload_limit_bytes: 1048576 };
  else throw Error('Unexpected synthetic API: ' + method + ' ' + route);
  return { status: 200, data };
}

async function staticPreview() {
  if (process.env.OCOTE_F11_STATIC_PREVIEW !== '1') return null;
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
  let credentials;
  try { credentials = JSON.parse(execFileSync(path.resolve('backend/.venv/Scripts/python'), ['-c', certificate], { encoding: 'utf8' })); }
  catch { throw Error('Ephemeral preview certificate unavailable'); }
  const root = path.resolve('dist/ocote-app/browser');
  const types = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.woff2': 'font/woff2', '.png': 'image/png', '.webp': 'image/webp', '.ico': 'image/x-icon' };
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
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(Number(new URL(origin).port), '127.0.0.1', resolve); });
  return server;
}

async function main() {
  const preview = await staticPreview();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'ocote-f11-chrome-'));
  const artifacts = fs.mkdtempSync(path.join(os.tmpdir(), 'ocote-f11-visual-'));
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
    const wait = expression => evaluate(`new Promise((resolve,reject)=>{const end=Date.now()+25000;function check(){if(${expression})resolve(true);else if(Date.now()>end)reject(Error('DOM condition timed out: '+${JSON.stringify(expression)}));else requestAnimationFrame(check);}check();})`);
    const click = expression => evaluate(`(()=>{const element=${expression};if(!element)throw Error('Missing control');element.click();})()`);
    const button = label => `[...document.querySelectorAll('button')].find(element=>element.textContent.includes(${JSON.stringify(label)}))`;
    const tab = label => `[...document.querySelectorAll('[role=tab]')].find(element=>element.textContent.includes(${JSON.stringify(label)}))`;
    const control = label => `document.querySelector(${JSON.stringify('button[aria-label="' + label + '"]')})`;
    const field = label => `[...document.querySelectorAll('mat-dialog-container mat-form-field')].find(element=>element.querySelector('mat-label')?.textContent.trim()===${JSON.stringify(label)})?.querySelector('input,textarea,mat-select')`;
    const close = async () => { await page('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 }); await page('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 }); await wait('!document.querySelector("mat-dialog-container")'); };
    const navigate = async (route, condition) => { const result = await page('Page.navigate', { url: origin + route }); if (result.errorText) throw Error(result.errorText); await wait(condition); };
    const inspect = async name => {
      await evaluate('document.fonts.ready');
      await evaluate(`Promise.all([...document.images].map(image=>image.decode().catch(()=>{throw Error('Image did not decode: '+image.currentSrc+' complete='+image.complete)})))`);
      await evaluate('Promise.all(document.getAnimations().map(animation=>animation.finished.catch(()=>{})))');
      const metrics = await evaluate(`({width:innerWidth,scroll:document.documentElement.scrollWidth,images:[...document.images].map(image=>({src:image.currentSrc,naturalWidth:image.naturalWidth})),overflow:[...document.querySelectorAll('h1,h2,h3,button,input,img,textarea')].filter(element=>{const box=element.getBoundingClientRect();return box.width>0 && (box.left<-.5 || box.right>innerWidth+.5) && !element.closest('[role=tablist]');}).map(element=>element.tagName+':'+element.textContent.trim().slice(0,60)),bodyLength:document.body.innerText.trim().length,passwords:[...document.querySelectorAll('input[type=password]')].every(element=>!element.value)})`);
      if (metrics.scroll > metrics.width || metrics.overflow.length || metrics.bodyLength < 80 || !metrics.passwords) throw Error(name + ':' + JSON.stringify(metrics));
      const image = await page('Page.captureScreenshot', { captureBeyondViewport: false }); fs.writeFileSync(path.join(artifacts, name + '.png'), Buffer.from(image.data, 'base64')); results.push({ name, ...metrics });
    };
    for (const width of [1280, 360]) {
      await page('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: false });
      role = 'anonymous'; await navigate('/login', 'document.body.innerText.includes("LDAP sintetico F11")'); await inspect('login-' + width);
      await click(button('LDAP sintetico F11')); await wait('document.body.innerText.includes("Usuario del directorio")'); await inspect('ldap-login-' + width);
      role = 'admin'; await navigate('/login?sso_transaction=' + transactionId, 'document.body.innerText.includes("Registrar prueba")'); await inspect('probe-return-' + width);
      if (await evaluate('location.search.includes("sso_transaction")')) throw Error('SSO correlation retained in URL');
      await navigate('/perfil', 'document.body.innerText.includes("synthetic-stable-subject")'); await inspect('profile-identities-' + width);
      await click(control('Revocar identidad')); await wait('document.querySelector("mat-dialog-container input[type=password]")'); await inspect('binding-revocation-' + width); await close();
      await navigate('/administracion/integraciones', 'document.body.innerText.includes("OIDC sintetico F11")'); await inspect('connectors-' + width);
      for (let index = 0; index < connectors.length; index++) {
        await click(`document.querySelectorAll('button[aria-label="Editar conector"]')[${index}]`); await wait('document.querySelector("mat-dialog-container input[type=password]")'); await inspect(connectors[index].provider + '-editor-' + width); await close();
      }
      await click(control('Mapeos JIT')); await wait('document.querySelector("mat-dialog-container mat-select")'); await inspect('jit-mappings-' + width); await close();
      await click(control('Repositorios aprobados')); await wait('document.querySelector("mat-dialog-container mat-select")'); await inspect('repositories-' + width); await close();
      await click(control('Probar conector')); await wait('document.body.innerText.includes("Contrasena del administrador local de emergencia")'); await inspect('sso-probe-confirmation-' + width); await close();
      await click(control('Historial de pruebas')); await wait('document.body.innerText.includes("F11_SYNTHETIC_VERIFIED")'); await inspect('connector-checks-' + width);
      await click(control('Eventos Git recibidos')); await wait('document.body.innerText.includes("synthetic-delivery")'); await inspect('git-inbox-' + width);
      await click(control('Editar conector')); await wait(field('Motivo'));
      await evaluate(`(()=>{const password=${field('Contrasena local actual')},reason=${field('Motivo')};password.value='synthetic-local-password';reason.value='Motivo sintetico F11 para conflicto';for(const input of [password,reason])input.dispatchEvent(new Event('input',{bubbles:true}));})()`);
      await click('document.querySelector("mat-dialog-container button[type=submit]")'); await wait('document.querySelector("mat-dialog-container").innerText.includes("synthetic-f11-409")');
      if (!await evaluate(`document.querySelector('mat-dialog-container button[type=submit]').disabled && (${field('Motivo')}).value.includes('conflicto')`)) throw Error('409 did not retain and block draft');
      await evaluate(`(()=>{const input=${field('Contrasena local actual')};input.value='';input.dispatchEvent(new Event('input',{bubbles:true}));})()`); await inspect('conflict-' + width);
      await click(button('Descartar cambios y recargar')); await wait('!document.querySelector("mat-dialog-container")');
      await click(tab('Actores tecnicos')); await wait('document.body.innerText.includes("Actor sintetico F11")'); await inspect('principals-' + width);
      await click(control('Editar actor tecnico')); await wait('document.querySelector("mat-dialog-container textarea")'); await inspect('principal-editor-' + width); await close();
      await click(tab('API Keys')); await wait('document.body.innerText.includes("Credencial sintetica F11")'); await inspect('keys-' + width);
      await click(control('Rotar API Key')); await wait('document.querySelector("mat-dialog-container input[type=datetime-local]")'); await inspect('key-rotation-' + width); await close();
      await click(control('Revocar API Key')); await wait('document.querySelector("mat-dialog-container input[type=password]")'); await inspect('key-revocation-' + width); await close();
      await click(tab('Identidades')); await wait('document.body.innerText.includes("synthetic-stable-subject")'); await inspect('admin-identities-' + width);
      await click(tab('Suscripciones')); await wait(control('Editar suscripcion')); await inspect('subscriptions-' + width);
      await click(control('Editar suscripcion')); await wait('document.querySelector("mat-dialog-container textarea")'); await inspect('subscription-editor-' + width); await close();
      await click(tab('Entregas')); await wait('document.body.innerText.includes("dead_letter")'); await inspect('deliveries-' + width);
      await click(control('Filtrar entregas')); await wait('document.querySelector("mat-dialog-container input[type=datetime-local]")'); await inspect('delivery-filters-' + width); await close();
      await click(control('Consultar intentos')); await wait('document.body.innerText.includes("LEASE_EXPIRED")'); await inspect('delivery-attempts-' + width);
      await click(control('Crear replay vinculado')); await wait('document.querySelector("mat-dialog-container textarea")'); await inspect('linked-replay-' + width); await close();
      await navigate('/tareas/' + taskId, 'document.body.innerText.includes("feature/synthetic-f11")'); await inspect('task-links-' + width);
      await click(button('Enlace verificado')); await wait('document.querySelector("mat-dialog-container mat-select")'); await inspect('task-repository-' + width); await close();
      role = 'colaborador'; const before = requests.length;
      await navigate('/administracion/integraciones', 'document.body.innerText.includes("Acceso no disponible")'); await inspect('collaborator-denied-' + width);
      if (requests.slice(before).some(request => /^\/integrations\/(configs|api-keys|service-principals)/.test(request.path))) throw Error('Collaborator requested administration');
      role = 'admin'; flags.integrations = false; const disabled = requests.length;
      await navigate('/administracion/integraciones', 'document.body.innerText.includes("Administracion de integraciones no disponible")'); await inspect('disabled-' + width);
      if (requests.slice(disabled).some(request => /^\/integrations\//.test(request.path))) throw Error('Disabled modules requested data'); flags.integrations = true;
    }
    if (errors.length) throw Error(errors.join('\n'));
    fs.writeFileSync(path.join(artifacts, 'results.json'), JSON.stringify({ synthetic: true, providerHomologation: false, origin, results, requests, errors }, null, 2));
    console.log(JSON.stringify({ artifacts, screenshots: results.length, requests: requests.length, errors }));
  } catch (error) { fs.writeFileSync(path.join(artifacts, 'failure.json'), JSON.stringify({ error: String(error), errors, requests, results }, null, 2)); console.error('F11 visual artifacts: ' + artifacts); throw error; }
  finally { if (socket) socket.close(); const stopped = once(chrome, 'exit'); chrome.kill(); await stopped; if (preview) await new Promise(resolve => preview.close(resolve)); fs.rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });