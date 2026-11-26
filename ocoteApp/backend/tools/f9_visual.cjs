const { spawn } = require('node:child_process');
const { once } = require('node:events');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const origin = process.env.OCOTE_F9_PREVIEW;
if (!/^https:\/\/localhost:\d+$/.test(origin || '') || origin === 'https://localhost:8443') throw Error('A separate loopback HTTPS preview is required');
const identity = number => '00000000-0000-4000-8000-' + String(number).padStart(12, '0');
const taskId = identity(1), objectiveId = identity(2), planId = identity(3), departmentId = identity(4), userId = identity(5);
const policy = { version: 1, password_min_length: 12, require_upper: true, require_lower: true, require_digit: true, require_symbol: true, access_ttl_seconds: 300, refresh_absolute_seconds: 86400, idle_timeout_seconds: 900, failed_attempt_threshold: 5, failed_window_seconds: 300, lockout_seconds: 300, page_sizes: [5, 10, 20, 50], import_max_rows: 1000, import_max_bytes: 10485760, export_max_bytes: 16777216 };
const flags = Object.fromEntries(['subtasks', 'due_date_requests', 'kanban', 'timeline', 'analytics', 'evaluations', 'exports', 'integrations', 'calendar', 'comments', 'dependencies', 'impediments', 'tags', 'custom_fields', 'templates', 'recurrence', 'search', 'saved_views'].map(code => [code, true]));
const configuration = { revision: 10, branding: { version: 0, organization_name: 'OCOTE', organization_name_version: 0, token_overrides: {}, logo_asset_id: null }, flags, page_sizes: policy.page_sizes, security_policy: policy, modules: Object.keys(flags).map(code => ({ code, installed: true, enabled: true, version: 1 })) };
const dates = { start_date: '2027-12-01', due_date: '2028-02-20', horizon_type: 'custom' };
const plan = { id: planId, version: 1, title: 'Plan sintetico F9', status: 'active', ...dates };
const objective = { id: objectiveId, version: 1, title: 'Objetivo sintetico F9', annual_plan_id: planId, department_id: departmentId, description: '', ...dates };
const user = { id: userId, display_name: 'Operador sintetico F9', role: 'admin', department_id: departmentId };
const stages = [{ id: identity(6), version: 1, name: 'En curso', code: 'active', kind: 'in_progress', is_initial: true, is_active: true }, { id: identity(7), version: 1, name: 'Completada', code: 'done', kind: 'completed', is_active: true }];
const priority = { id: identity(8), version: 1, name: 'Normal', code: 'normal' };
const task = { id: taskId, version: 1, title: 'Coordinar entrega departamental F9', description: 'Trabajo sintetico para revision aislada.', assignee_id: userId, objective_id: objectiveId, stage_id: stages[0].id, priority_id: priority.id, ...dates, original_due_date: dates.due_date, completed_at: null, progress_percent: 50, punctuality_status: 'pending', baseline_punctuality_status: 'pending', delay_days: 0, baseline_delay_days: 0, due_date_delta_days: 0, objective, annual_plan: plan, priority, template_version_id: identity(9), collaboration: { open_impediments: 1, pending_predecessors: 1, impeded_seconds: 3600 } };
const kinds = ['text', 'number', 'boolean', 'date', 'select', 'multi_select', 'url'];
const definitions = kinds.map((kind, index) => ({ id: identity(20 + index), version: 1, entity_type: 'task', key: 'synthetic_' + kind, label: ['Referencia operativa', 'Importe', 'Confirmado', 'Fecha de control', 'Categoria', 'Canales', 'Referencia HTTPS'][index], data_type: kind, active: true, required_on_create: false, required_stage_ids: [], constraints: {}, scope_kind: 'organization', department_id: null, options: ['select', 'multi_select'].includes(kind) ? [{ id: identity(40 + index), code: 'synthetic', label: 'Opcion sintetica', version: 1, position: 0, is_active: true }] : [] }));
const metadataValues = ['Texto literal de referencia', 12.125, false, '2027-12-15', identity(44), [identity(45)], 'https://example.invalid/reference'];
const tags = ['forest', 'rust', 'ink', 'danger'].map((color, index) => ({ id: identity(50 + index), version: 1, label: ['Operacion', 'Seguimiento', 'Control', 'Atencion'][index], color_code: color, scope_kind: 'organization', department_id: null, is_active: true }));
const blueprint = { title: 'Tarea desde plantilla', description: '', horizon_type: 'custom', priority_id: priority.id, start_offset_days: 0, duration_days: 2, subtasks: [], objectives: [], tasks: [], custom_fields: {}, tag_ids: [] };
const template = { id: identity(60), version: 1, name: 'Plantilla operativa F9', entity_type: 'task', scope_kind: 'organization', department_id: null, is_active: true, current_version: 1, template_version: { id: identity(9), template_version: 1, schema_version: 1, payload: blueprint } };
const comment = { id: identity(70), version: 1, task_id: taskId, objective_id: null, author_id: userId, parent_comment_id: null, current_revision: 1, annulled_at: null, created_at: '2027-12-12T12:00:00Z', body: '<em>Comentario literal F9, sin HTML ejecutable.</em>', mention_ids: [], can_edit: true };
const pageOf = items => ({ items, next_cursor: null });
let writeStatus = 409, role = 'admin';
function synthetic(endpoint, method) {
  if (method === 'PUT' && endpoint.endsWith('/metadata')) return { status: writeStatus, data: { status: writeStatus, code: writeStatus === 409 ? 'VERSION_CONFLICT' : 'CUSTOM_FIELD_TYPE_OR_CONSTRAINT', request_id: 'synthetic-f9-' + writeStatus } };
  if (endpoint === '/collaboration/search' && method === 'POST') return { status: 200, data: { ...pageOf([{ id: taskId, entity_type: 'task', task_id: taskId, objective_id: objectiveId, snippet: task.title, score: 1 }]), counts: { task: 1 } } };
  let data;
  if (endpoint === '/auth/csrf') data = { csrf_token: 'synthetic' };
  else if (endpoint === '/auth/refresh') data = { access_token: 'synthetic', csrf_token: 'synthetic', expires_in: 300 };
  else if (endpoint === '/auth/me') data = { ...user, role, email: 'synthetic@example.invalid', permissions: role === 'admin' ? ['administration:manage', 'planning:manage', 'tasks:manage', 'tasks:transition', 'analytics:read', 'evaluations:read', 'date-requests:create'] : ['tasks:transition', 'date-requests:create'] };
  else if (['/configuration', '/admin/configuration'].includes(endpoint)) data = configuration;
  else if (endpoint === '/catalogs/workflow') data = { stages, transitions: [] };
  else if (endpoint === '/catalogs/priorities') data = pageOf([priority]);
  else if (['/catalogs/assignees', '/users'].includes(endpoint)) data = pageOf([user]);
  else if (['/catalogs/departments', '/departments'].includes(endpoint)) data = pageOf([{ id: departmentId, version: 1, name: 'Departamento sintetico', is_active: true }]);
  else if (endpoint === '/catalogs/horizons') data = pageOf(['annual', 'semiannual', 'quarterly', 'monthly', 'custom'].map(code => ({ code, name: code })));
  else if (endpoint === '/annual-plans') data = pageOf([plan]);
  else if (endpoint === '/annual-plans/' + planId) data = plan;
  else if (endpoint === '/objectives') data = pageOf([objective]);
  else if (endpoint === '/objectives/' + objectiveId) data = objective;
  else if (endpoint === '/tasks') data = pageOf([task]);
  else if (endpoint === '/tasks/' + taskId) data = task;
  else if (endpoint === '/tasks/' + taskId + '/subtasks') data = pageOf([]);
  else if (endpoint === '/tasks/' + taskId + '/evidence') data = pageOf([]);
  else if (endpoint === '/tasks/' + taskId + '/dependencies') data = { ...pageOf([{ id: identity(80), version: 1, predecessor_task_id: identity(81), successor_task_id: taskId, active: true }]), plan_version: 1, task_version: 1 };
  else if (endpoint === '/tasks/' + taskId + '/impediments') data = { ...pageOf([{ id: identity(82), version: 1, owner_user_id: userId, reason: 'Confirmacion externa pendiente de recibir.', severity: 'high', kind: 'external', opened_at: '2027-12-12T12:00:00Z', closed_at: null, resolution: null }]), task_version: 1 };
  else if (endpoint === '/collaboration/task/' + taskId + '/metadata' || endpoint === '/collaboration/metadata-schema/task') data = { resource_version: 1, fields: definitions, values: definitions.map((field, index) => ({ id: identity(90 + index), definition_id: field.id, value: metadataValues[index] })), tags, tag_ids: tags.map(tag => tag.id) };
  else if (endpoint === '/collaboration/task/' + taskId + '/comments') data = { ...pageOf([comment]), resource_version: 1 };
  else if (endpoint === '/collaboration/task/' + taskId + '/comments/' + comment.id + '/revisions') data = pageOf([{ id: identity(71), comment_id: comment.id, revision_no: 1, body: '<b>Revision historica literal F9</b>', reason: 'Motivo sintetico de revision historica', created_at: comment.created_at, annulment: false }]);
  else if (endpoint === '/collaboration/task/' + taskId + '/mentions') data = pageOf([user]);
  else if (endpoint === '/collaboration/custom-fields') data = pageOf(definitions);
  else if (endpoint === '/collaboration/tags') data = pageOf(tags);
  else if (endpoint === '/collaboration/templates') data = pageOf([template]);
  else if (endpoint === '/collaboration/service-principals') data = pageOf([{ id: identity(100), version: 1, name: 'Actor interno F9', is_active: true, department_ids: [departmentId], approved_scopes: ['tasks:create'] }]);
  else if (endpoint === '/collaboration/recurrence-schedules') data = pageOf([{ id: identity(101), version: 1, enabled: false, template_version_id: identity(9), owner_user_id: userId, service_principal_id: identity(100), objective_id: objectiveId, assignee_id: userId, calendar_id: identity(110), frequency: 'weekly', interval: 1, start_date: '2027-12-01', end_date: '2028-02-01', occurrence_count: null, end_policy: 'last_day', non_business_policy: 'next', missed_policy: 'catch_up', next_due_at: '2027-12-01' }]);
  else if (endpoint === '/collaboration/calendar-context/' + objectiveId) data = { id: identity(110), name: 'Calendario sintetico F9', version: 1, timezone: 'America/Mexico_City' };
  else if (endpoint === '/collaboration/saved-views') data = pageOf([{ id: identity(102), version: 1, owner_id: userId, name: 'Seguimiento personal', scope_kind: 'personal', entity_type: 'task', department_id: null, active: true, filters: { q: '', entity_type: 'task' } }]);
  else if (endpoint === '/kanban') data = { columns: stages.map((stage, index) => ({ stage, count: index ? 0 : 1, items: index ? [] : [task], next_cursor: null })) };
  else if (endpoint === '/timeline') data = { ...pageOf([{ ...task, task_id: taskId, scope_department_id: departmentId, scope_assignee_id: userId }]), organization_timezone: 'America/Mexico_City' };
  else if (endpoint === '/admin/calendars' || endpoint === '/admin/object-storage') data = pageOf([]);
  else throw Error('Unexpected synthetic API: ' + method + ' ' + endpoint);
  return { status: 200, data };
}

async function main() {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'ocote-f9-chrome-'));
  const artifacts = fs.mkdtempSync(path.join(os.tmpdir(), 'ocote-f9-visual-'));
  const chrome = spawn(process.env.CHROME_BIN || 'C:/Program Files/Google/Chrome/Application/chrome.exe', ['--headless=new', '--remote-debugging-port=0', '--user-data-dir=' + profile, '--ignore-certificate-errors', '--disable-gpu', '--no-first-run', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
  let socket, session, sequence = 0, diagnose = async () => ({});
  const pending = new Map(), errors = [], requests = [], results = [], cancelled = [];
  try {
    const endpoint = await new Promise((resolve, reject) => { let output = ''; chrome.stderr.on('data', data => { output += data; const match = output.match(/DevTools listening on (ws:\/\/[^\s]+)/); if (match) resolve(match[1]); }); chrome.once('error', reject); chrome.once('exit', () => reject(Error('Chrome exited before CDP'))); });
    socket = new WebSocket(endpoint); await once(socket, 'open');
    const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => { const id = ++sequence; pending.set(id, { resolve, reject }); socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) })); });
    socket.addEventListener('message', async event => {
      const message = JSON.parse(event.data);
      if (message.id) { const callback = pending.get(message.id); if (callback) { pending.delete(message.id); message.error ? callback.reject(Error(JSON.stringify(message.error))) : callback.resolve(message.result); } return; }
      if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text);
      if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') errors.push(message.params.args.map(argument => argument.value || argument.description || '').join(' '));
      if (message.method === 'Network.loadingFailed') errors.push(message.params.errorText);
      if (message.method !== 'Fetch.requestPaused') return;
      try { const request = message.params.request, url = new URL(request.url); if (url.origin !== origin) throw Error('Unexpected API origin'); const response = synthetic(url.pathname.slice(7), request.method); requests.push({ method: request.method, path: url.pathname.slice(7), intercepted: true }); await send('Fetch.fulfillRequest', { requestId: message.params.requestId, responseCode: response.status, responseHeaders: [{ name: 'Content-Type', value: response.status >= 400 ? 'application/problem+json' : 'application/json' }, { name: 'Cache-Control', value: 'no-store' }], body: Buffer.from(JSON.stringify(response.data)).toString('base64') }, session); }
      catch (error) { if (error.message.includes('Invalid InterceptionId')) cancelled.push(message.params.request.url); else { errors.push(String(error)); await send('Fetch.failRequest', { requestId: message.params.requestId, errorReason: 'BlockedByClient' }, session).catch(() => undefined); } }
    });
    const target = await send('Target.createTarget', { url: 'about:blank' });
    session = (await send('Target.attachToTarget', { targetId: target.targetId, flatten: true })).sessionId;
    const page = (method, params = {}) => send(method, params, session);
    await page('Page.enable'); await page('Runtime.enable'); await page('Network.enable'); await page('Security.setIgnoreCertificateErrors', { ignore: true });
    await page('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*', requestStage: 'Request' }] });
    const evaluate = async expression => { const response = await page('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (response.exceptionDetails) throw Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text); return response.result.value; };
    const wait = expression => evaluate(`new Promise((resolve,reject)=>{const end=Date.now()+25000;function check(){if(${expression})resolve(true);else if(Date.now()>end)reject(Error('DOM condition timed out: '+${JSON.stringify(expression)}));else requestAnimationFrame(check);}check();})`);
    const click = expression => evaluate(`(()=>{const element=${expression};if(!element)throw Error('Missing control');element.click();})()`);
    const button = label => `[...document.querySelectorAll('button')].find(element=>element.textContent.includes(${JSON.stringify(label)}))`;
    diagnose = async () => { const document = await evaluate('({url:location.href,title:document.title,body:document.body.innerText.slice(0,8000)})'); const image = await page('Page.captureScreenshot'); fs.writeFileSync(path.join(artifacts, 'failure.png'), Buffer.from(image.data, 'base64')); return document; };
    const navigate = async (route, condition) => { const result = await page('Page.navigate', { url: origin + route }); if (result.errorText) throw Error(result.errorText); await wait(condition); };
    const inspect = async name => {
      await evaluate('document.fonts.ready'); await wait('[...document.images].every(image=>image.complete && image.naturalWidth>0)');
      await evaluate('Promise.all(document.getAnimations().map(animation=>animation.finished.catch(()=>{})))');
      const metrics = await evaluate(`({width:innerWidth,scroll:document.documentElement.scrollWidth,images:[...document.images].map(image=>({src:image.currentSrc,naturalWidth:image.naturalWidth})),overflow:[...document.querySelectorAll('h1,h2,h3,button,input,img,textarea')].filter(element=>{const box=element.getBoundingClientRect();return box.width>0 && (box.left<-.5 || box.right>innerWidth+.5) && !element.closest('.kanban');}).map(element=>element.tagName+':'+element.textContent.trim().slice(0,40)),bodyLength:document.body.innerText.trim().length})`);
      if (metrics.scroll > metrics.width || metrics.overflow.length || metrics.bodyLength < 100 || metrics.images.some(image => !image.naturalWidth)) throw Error(name + ':' + JSON.stringify(metrics));
      const image = await page('Page.captureScreenshot', { captureBeyondViewport: false }); fs.writeFileSync(path.join(artifacts, name + '.png'), Buffer.from(image.data, 'base64')); results.push({ name, ...metrics });
    };
    for (const width of [1280, 360]) {
      await page('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: false });
      await navigate('/tareas/' + taskId, 'document.body.innerText.includes("Comentario literal F9")'); await inspect('task-' + width);
      await evaluate('document.querySelector("ocote-collaboration").scrollIntoView({block:"start"})'); await inspect('task-collaboration-' + width);
      await evaluate('document.querySelector("ocote-collaboration .thread").scrollIntoView({block:"center"})'); await inspect('comment-plaintext-' + width);
      await click(`document.querySelector('button[aria-label="Historial de comentario"]')`); await wait('document.body.innerText.includes("Revision historica literal F9")'); await inspect('comment-history-' + width);
      if (await evaluate(`!!document.querySelector('[aria-label="Revisiones del comentario"] b')`)) throw Error('Revision interpreted as HTML');
      if (await evaluate('!!document.querySelector("ocote-collaboration .body em")')) throw Error('Comment interpreted as HTML');
      await click(button('Editar valores')); await wait('document.querySelector("mat-dialog-container textarea")');
      await evaluate('(()=>{const input=document.querySelector("mat-dialog-container input[type=text]");input.value="Borrador F9 conservado";input.dispatchEvent(new Event("input",{bubbles:true}));const reason=document.querySelector("mat-dialog-container textarea");reason.value="Motivo sintetico F9 para conservar cambios";reason.dispatchEvent(new Event("input",{bubbles:true}));})()');
      writeStatus = 409; await click('document.querySelector("mat-dialog-container button[type=submit]")'); await wait('document.querySelector("mat-dialog-container").innerText.includes("synthetic-f9-409")');
      if (!await evaluate('document.querySelector("mat-dialog-container button[type=submit]").disabled && document.querySelector("mat-dialog-container input[type=text]").value.includes("conservado")')) throw Error('409 did not retain and block draft'); await inspect('conflict-' + width);
      await click(button('Descartar cambios y recargar')); await wait('!document.querySelector("mat-dialog-container")'); await wait('document.body.innerText.includes("Comentario literal F9")');
      await click(button('Editar valores')); await wait('document.querySelector("mat-dialog-container textarea")'); await evaluate('(()=>{const input=document.querySelector("mat-dialog-container textarea");input.value="Motivo sintetico para validacion 422";input.dispatchEvent(new Event("input",{bubbles:true}));})()');
      writeStatus = 422; await click('document.querySelector("mat-dialog-container button[type=submit]")'); await wait('document.querySelector("mat-dialog-container").innerText.includes("synthetic-f9-422")');
      if (await evaluate('document.querySelector("mat-dialog-container button[type=submit]").disabled')) throw Error('422 prevented correction'); await inspect('validation-' + width);
      await page('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 }); await page('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 }); await wait('!document.querySelector("mat-dialog-container")');
      await navigate('/tareas', 'document.querySelector("ocote-search input") && document.body.innerText.includes("Coordinar entrega")');
      await evaluate('(()=>{const input=document.querySelector("ocote-search input");input.value="Coordinar";input.dispatchEvent(new Event("input",{bubbles:true}));document.querySelector("ocote-search form").requestSubmit();})()'); await wait('document.body.innerText.includes("1 resultados autorizados")'); await inspect('tasks-search-' + width);
      await navigate('/kanban', 'document.querySelector(".task-card ocote-collaboration-indicators")'); await evaluate('document.querySelector(".kanban").scrollIntoView({block:"start"})'); await inspect('kanban-' + width);
      await page('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 }); await page('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 }); if (!await evaluate('document.activeElement && document.activeElement !== document.body')) throw Error('Keyboard focus missing');
      await navigate('/timeline', 'document.querySelector(".vis-item")'); await evaluate('document.querySelector(".vis-item").scrollIntoView({block:"center"})'); await inspect('timeline-' + width);
      await navigate('/administracion/colaboracion', 'document.body.innerText.includes("Definiciones") && document.body.innerText.includes("Referencia operativa")');
      for (const label of ['Campos', 'Etiquetas', 'Plantillas', 'Recurrencia']) {
        await click(`[...document.querySelectorAll('[role=tab]')].find(element=>element.textContent.trim()===${JSON.stringify(label)})`); await wait(`document.querySelector('[role=tab][aria-selected=true]').textContent.trim()===${JSON.stringify(label)}`); await inspect('admin-' + label.toLowerCase() + '-' + width);
        const action = { Campos: 'Editar campo', Etiquetas: 'Editar etiqueta', Plantillas: 'Editar plantilla', Recurrencia: 'Editar programacion' }[label];
        await click(`document.querySelector('button[aria-label=${JSON.stringify(action)}]')`); await wait('document.querySelector("mat-dialog-container textarea")'); await inspect('admin-form-' + label.toLowerCase() + '-' + width);
        await click('document.querySelector("mat-dialog-container button[type=button]")'); await wait('!document.querySelector("mat-dialog-container")');
      }
      await navigate('/administracion/configuracion', 'document.body.innerText.includes("Politicas de acceso y limites")'); await click('[...document.querySelectorAll("[role=tab]")].find(element=>element.textContent.trim()==="Modulos")'); await wait('document.body.innerText.includes("saved_views")'); await inspect('modules-' + width);
      role = 'colaborador'; await navigate('/tareas/' + taskId, 'document.body.innerText.includes("Comentario literal F9")');
      if (await evaluate('[...document.querySelectorAll("button")].some(button=>button.textContent.includes("Editar valores") || button.textContent.includes("Predecesora"))')) throw Error('Collaborator management controls exposed'); await inspect('collaborator-' + width); role = 'admin';
    }
    if (errors.length) throw Error(JSON.stringify(errors));
    const report = { artifacts, results, cssWidths: [1280, 360], requests, cancelledRequests: cancelled, runtimeErrors: errors, realApiRequests: 0, syntheticOnly: true };
    fs.writeFileSync(path.join(artifacts, 'results.json'), JSON.stringify(report, null, 2)); console.log(JSON.stringify({ artifacts, screenshots: results.length, cssWidths: report.cssWidths, syntheticRequests: requests.length, runtimeErrors: errors }, null, 2)); await send('Browser.close');
  } catch (error) { const document = await diagnose().catch(failure => ({ failure: String(failure) })); fs.writeFileSync(path.join(artifacts, 'failure.json'), JSON.stringify({ error: String(error), errors, document, requests, results }, null, 2)); console.error('F9 visual evidence: ' + artifacts); throw error; }
  finally { if (socket) socket.close(); if (chrome.exitCode === null) { chrome.kill(); await once(chrome, 'exit'); } fs.rmSync(profile, { recursive: true, force: true }); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });