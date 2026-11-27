import { DatePipe } from '@angular/common';
import { Component, DestroyRef, effect, inject, OnDestroy, signal, untracked } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Api, Page, Row, text, version } from '../core/api';
import { Configuration } from '../core/configuration';
import { Problem, problem } from '../core/problem';
import { Session } from '../core/session';
import { ssoDestination, SSO_NAVIGATION } from '../auth/auth.pages';
import { Editor, Field, options, reason } from '../shared/editor';
import { Feedback } from '../shared/feedback';
import { Pager, Pagination } from '../shared/pager';

export const KEY_SCOPES = ['tasks:read', 'tasks:create', 'tasks:update_metadata'];
export const PRINCIPAL_SCOPES = [...KEY_SCOPES, 'subtasks:create', 'notifications:dispatch'];
export const WEBHOOK_EVENTS = ['dependency_changed', 'impediment_changed', 'comment_changed', 'recurrence_generated', 'assignment', 'upcoming_due', 'overdue', 'due_date_request', 'due_date_decision', 'evaluation_finalized'];
export function replayPayload(row: Row, values: Row, idempotency: string): Row {
  return { expected_version: version(row), delivery_id: row['id'], idempotency_key: idempotency, current_password: values['current_password'], reason: values['reason'] };
}
export function webhookFilters(values: Row): Record<string, string> {
  return { ...(values['state'] && values['state'] !== 'all' ? { state: String(values['state']) } : {}),
    ...(values['subscription_id'] && values['subscription_id'] !== 'all' ? { subscription_id: String(values['subscription_id']) } : {}),
    ...(utcInput(values['since']) ? { since: utcInput(values['since'])! } : {}), ...(utcInput(values['until']) ? { until: utcInput(values['until'])! } : {}) };
}
const pick = (key: string, label: string, values: string[], value?: unknown): Field => ({ key, label, type: 'select', required: true, options: values.map(value => ({ value, label: value })), value });
const lines = (value: unknown): string[] => String(value ?? '').split(/\r?\n/).map(line => line.trim()).filter(Boolean);
const networkKey = (prefix: string, key: string): string => prefix ? prefix + '__' + key : key;
export function endpointPayload(prefix: string, values: Row, https = true): Row {
  return { ...Object.fromEntries(['host', 'connect_timeout_seconds', 'read_timeout_seconds', 'rate_per_minute', 'allow_private_endpoint', 'audience_approved', ...(https ? ['url'] : [])].map(key => [key, values[networkKey(prefix, key)]])),
    approved_addresses: lines(values[networkKey(prefix, 'approved_addresses')]), ca_certificates_pem: values[networkKey(prefix, 'ca_certificates_pem')] || null };
}
function endpointFields(prefix: string, label: string, value: Row = {}, https = true): Field[] {
  const field = (key: string, name: string, type: Field['type'] = 'text', max?: number): Field => ({ key: networkKey(prefix, key), label: label + ': ' + name, type, required: true, max, value: value[key] });
  return [
    ...(https ? [field('url', 'URL HTTPS exacta', 'text', 2048)] : []), field('host', 'Hostname TLS', 'text', 253),
    { ...field('approved_addresses', 'Direcciones IP aprobadas', 'textarea', 1000), value: (value['approved_addresses'] as string[] ?? []).join('\n') },
    { ...field('ca_certificates_pem', 'CA publica PEM', 'textarea', 65536), required: false },
    ...[['connect_timeout_seconds', 'Conexion (s)', 10], ['read_timeout_seconds', 'Lectura (s)', 15], ['rate_per_minute', 'Solicitudes por minuto', 1000]].map(([key, name, max]) => ({ ...field(String(key), String(name), 'number', Number(max)), min: 1 })),
    { ...field('allow_private_endpoint', 'Apruebo este destino privado', 'check'), required: false },
    { ...field('audience_approved', 'Apruebo este destino y audiencia', 'check'), required: false },
  ];
}
export function integrationPayload(provider: string, values: Row, record?: Row): Row {
  const previous = record?.['config'] as Row ?? {};
  const config: Row = { provider };
  if (['oidc', 'saml', 'ldap'].includes(provider)) Object.assign(config, {
    emergency_admin_id: values['emergency_admin_id'], revocation_window_seconds: values['revocation_window_seconds'],
    jit_enabled: previous['jit_enabled'] === true, jit_mappings: previous['jit_mappings'] ?? [],
    jit_email_attribute: previous['jit_email_attribute'] ?? null, jit_name_attribute: previous['jit_name_attribute'] ?? null,
  });
  const copy = (keys: string[]) => Object.assign(config, Object.fromEntries(keys.map(key => [key, values[key]])));
  if (provider === 'oidc') {
    copy(['issuer', 'client_id', 'token_auth_method']);
    for (const prefix of ['authorization_endpoint', 'token_endpoint', 'jwks_endpoint']) config[prefix] = endpointPayload(prefix, values);
  } else if (provider === 'saml') {
    copy(['entity_id', 'idp_certificate_pem', 'sp_certificate_pem']); config['sso_endpoint'] = endpointPayload('sso_endpoint', values);
  } else if (provider === 'ldap') {
    copy(['port', 'security', 'bind_dn', 'user_search_base', 'username_attribute', 'subject_attribute']); Object.assign(config, endpointPayload('', values, false));
  } else if (provider === 'github' || provider === 'gitlab') {
    config['api_endpoint'] = endpointPayload('api_endpoint', values); config['web_origin'] = values['web_origin'];
    config['repositories'] = record ? previous['repositories'] : [{ repository_id: values['repository_id'], path: values['repository_path'] }];
  } else config['endpoint'] = endpointPayload('endpoint', values);
  const credential = provider === 'github' || provider === 'gitlab'
    ? values['access_token'] || values['webhook_secret'] ? JSON.stringify({ access_token: values['access_token'], webhook_secret: values['webhook_secret'] }) : null
    : values['credential'];
  return { name: values['name'], scope_kind: values['scope_kind'], department_id: values['scope_kind'] === 'department' ? values['department_id'] : null,
    config, expected_version: record ? version(record) : 0, current_password: values['current_password'], reason: values['reason'],
    ...(typeof credential === 'string' && credential.length ? { credential } : {}) };
}
export function approvedEntries(entries: Row[], index: number, operation: string, value: Row): Row[] {
  if (!['add', 'change', 'remove'].includes(operation) || operation !== 'add' && (!Number.isInteger(index) || index < 0 || index >= entries.length)) throw new Error('Invalid approved entry');
  const updated = entries.map(entry => ({ ...entry }));
  if (operation === 'add') updated.push(value);
  else if (operation === 'change') updated[index] = value;
  else updated.splice(index, 1);
  return updated;
}
export function utcInput(value: unknown): string | null {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return null;
  const date = new Date(value + 'Z');
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 16) === value ? date.toISOString() : null;
}
export function apiKeyPayload(values: Row, record?: Row): Row {
  return { ...Object.fromEntries(['name', 'service_principal_id', 'owner_user_id', 'scopes', 'department_ids', 'rate_per_minute', 'current_password', 'reason'].map(key => [key, values[key]])),
    expected_version: record ? version(record) : 0, expires_at: utcInput(values['expires_at']),
    allowed_networks: values['network_policy'] === 'cidr' ? lines(values['allowed_networks']) : null };
}

@Component({
  imports: [MatDialogModule, MatInputModule, MatButtonModule, MatIconModule, MatTooltipModule],
  styles: [`textarea{width:100%;min-height:120px;resize:vertical;overflow-wrap:anywhere}mat-dialog-content{min-width:0}`],
  template: `<h2 mat-dialog-title>{{ data.title }}</h2><mat-dialog-content><mat-label>Secreto emitido</mat-label><textarea matInput readonly aria-label="Secreto emitido una sola vez" [value]="data.value" autocomplete="off" spellcheck="false"></textarea>@if (copied()) { <p role="status">Secreto copiado.</p> }@if (failed()) { <p role="alert">Portapapeles no disponible.</p> }</mat-dialog-content><mat-dialog-actions align="end"><button mat-icon-button aria-label="Copiar secreto" matTooltip="Copiar secreto" (click)="copy()"><mat-icon>content_copy</mat-icon></button><button mat-button mat-dialog-close>Cerrar</button></mat-dialog-actions>`,
})
export class IntegrationSecret {
  readonly data = inject<{ title: string; value: string }>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<IntegrationSecret>); private readonly session = inject(Session);
  private readonly owner = this.session.user()?.id;
  readonly copied = signal(false); readonly failed = signal(false);
  constructor() {
    inject(DestroyRef).onDestroy(() => this.data.value = '');
    effect(() => { if (!this.owner || this.session.user()?.id !== this.owner) { this.data.value = ''; this.ref.close(); } });
  }
  async copy(): Promise<void> {
    this.failed.set(false);
    try { await navigator.clipboard.writeText(this.data.value); this.copied.set(true); }
    catch { this.failed.set(true); }
  }
}

@Component({
  imports: [DatePipe, MatButtonModule, MatIconModule, MatTabsModule, MatTooltipModule, Pager, Feedback],
  styles: [`:host{display:block;min-width:0}.toolbar,.line{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.toolbar{padding:20px 0}.line{padding:16px 0;border-bottom:1px solid var(--ocote-border)}.line>div{min-width:0;overflow-wrap:anywhere}.line p{margin:4px 0}.meta{font-size:.875rem;color:var(--ocote-text-secondary)}.actions{display:flex;gap:4px;flex-wrap:wrap}h2{font-size:1.25rem}`],
  template: `<header class="page-heading"><div><p class="eyebrow">ADMINISTRACION</p><h1>Integraciones</h1></div><button mat-icon-button aria-label="Recargar integraciones" matTooltip="Recargar" (click)="load()" [disabled]="loading()"><mat-icon>refresh</mat-icon></button></header>
    <ocote-feedback [issue]="issue()" />@if (notice()) { <p role="status">{{ notice() }}</p> }
    @if (available()) { <mat-tab-group animationDuration="0ms" [selectedIndex]="selectedIndex()" (selectedIndexChange)="choose($event)">
      @for (tab of tabs(); track tab.path) { <mat-tab [label]="tab.label">@if (current() === tab.path) {
        <section><header class="toolbar"><h2>{{ tab.label }}</h2>
          @if (tab.path === 'service-principals') { <button mat-stroked-button (click)="principal()" [disabled]="loading()"><mat-icon>add</mat-icon>Actor tecnico</button> }
          @if (tab.path === 'api-keys') { <button mat-stroked-button (click)="key()" [disabled]="loading()"><mat-icon>add</mat-icon>API Key</button> }
          @if (tab.path === 'configs') { <button mat-stroked-button (click)="newConnector()" [disabled]="loading()"><mat-icon>add</mat-icon>Conector</button> }
          @if (tab.path === 'webhook-subscriptions') { <button mat-stroked-button (click)="subscription()" [disabled]="loading()"><mat-icon>add</mat-icon>Suscripcion</button> }
          @if (tab.path === 'webhook-deliveries') { <button mat-icon-button aria-label="Filtrar entregas" matTooltip="Filtrar entregas" (click)="filterDeliveries()" [disabled]="loading()"><mat-icon>filter_alt</mat-icon></button> }
        </header>@if (loading()) { <p role="status">Cargando integraciones...</p> }
        @for (row of rows(); track row['id']) { <div class="line"><div><strong>{{ row['name'] || row['issuer'] || row['id'] }}</strong><p class="meta">{{ summary(row) }}</p>
          @if (row['expires_at']) { <p class="meta">Expira {{ asText(row, 'expires_at') | date:'medium' }}</p> }
        </div><div class="actions">
          @if (tab.path === 'configs') {
            <button mat-icon-button aria-label="Editar conector" matTooltip="Editar conector" (click)="connector(row)" [disabled]="!kindEnabled(row)"><mat-icon>edit</mat-icon></button>
            <button mat-icon-button aria-label="Probar conector" matTooltip="Probar conector" (click)="test(row)" [disabled]="!kindEnabled(row)"><mat-icon>science</mat-icon></button>
            <button mat-icon-button [attr.aria-label]="row['is_active'] ? 'Desactivar conector' : 'Activar conector'" [matTooltip]="row['is_active'] ? 'Desactivar' : 'Activar'" (click)="activation(row)" [disabled]="!kindEnabled(row) || (!row['is_active'] && !row['tested_at'])"><mat-icon>{{ row['is_active'] ? 'pause_circle' : 'play_circle' }}</mat-icon></button>
            <button mat-icon-button aria-label="Historial de pruebas" matTooltip="Historial de pruebas" (click)="health(row)" [disabled]="!kindEnabled(row)"><mat-icon>monitor_heart</mat-icon></button>
            @if (row['kind'] === 'sso') { <button mat-icon-button aria-label="Mapeos JIT" matTooltip="Mapeos JIT" (click)="entries(row, true)" [disabled]="!kindEnabled(row)"><mat-icon>account_tree</mat-icon></button> }
            @if (row['kind'] === 'devops') { <button mat-icon-button aria-label="Repositorios aprobados" matTooltip="Repositorios aprobados" (click)="entries(row, false)" [disabled]="!kindEnabled(row)"><mat-icon>source</mat-icon></button><button mat-icon-button aria-label="Eventos Git recibidos" matTooltip="Eventos Git recibidos" (click)="inbox(row)" [disabled]="!kindEnabled(row)"><mat-icon>move_to_inbox</mat-icon></button> }
          }
          @if (tab.path === 'service-principals') { <button mat-icon-button aria-label="Editar actor tecnico" matTooltip="Permisos y revocacion" (click)="principal(row)"><mat-icon>manage_accounts</mat-icon></button> }
          @if (tab.path === 'api-keys' && !row['revoked_at']) { <button mat-icon-button aria-label="Rotar API Key" matTooltip="Rotar API Key" (click)="key(row)"><mat-icon>autorenew</mat-icon></button><button mat-icon-button aria-label="Revocar API Key" matTooltip="Revocar API Key" (click)="revoke(row)"><mat-icon>key_off</mat-icon></button> }
          @if (tab.path === 'external-identities' && !row['revoked_at']) { <button mat-icon-button aria-label="Revocar identidad" matTooltip="Revocar identidad" (click)="revoke(row)"><mat-icon>link_off</mat-icon></button> }
          @if (tab.path === 'webhook-subscriptions') { <button mat-icon-button aria-label="Editar suscripcion" matTooltip="Editar o pausar suscripcion" (click)="subscription(row)"><mat-icon>edit_notifications</mat-icon></button> }
          @if (tab.path === 'webhook-deliveries') { <button mat-icon-button aria-label="Consultar intentos" matTooltip="Intentos" (click)="attempts(row)"><mat-icon>receipt_long</mat-icon></button>@if (terminal(row)) { <button mat-icon-button aria-label="Crear replay vinculado" matTooltip="Crear replay vinculado" (click)="replay(row)"><mat-icon>replay</mat-icon></button> } }
        </div></div> } @empty { @if (!loading()) { <p>Sin registros disponibles.</p> } }
        <ocote-pager [state]="pagination" [busy]="loading()" (navigate)="load($event)" (sizeChange)="resize($event)" /></section>
        @if (detailPath()) { <section><h2>{{ detailTitle() }}</h2>@for (check of details(); track check['id']) { <div class="line">@if (check['event_type']) { <p>{{ check['event_type'] }} · {{ check['delivery_id'] }} · {{ asText(check, 'created_at') | date:'medium' }}</p> } @else { <p>{{ check['status'] || check['outcome'] }} · {{ check['result_code'] }}@if (check['attempt_no']) { · Intento {{ check['attempt_no'] }} · HTTP {{ check['status_code'] || 'sin respuesta' }} } · {{ check['latency_ms'] }} ms · {{ asText(check, 'created_at') | date:'medium' }}</p> }</div> } @empty { <p>Sin registros disponibles.</p> }<ocote-pager [state]="detailPagination" [busy]="loadingDetails()" (navigate)="loadDetails($event)" (sizeChange)="resizeDetails($event)" /></section> }
      }</mat-tab> }
    </mat-tab-group> } @else { <p>Administracion de integraciones no disponible.</p> }`,
})
export class IntegrationsPage implements OnDestroy {
  private readonly api = inject(Api); private readonly dialog = inject(MatDialog);
  private readonly navigateSSO = inject(SSO_NAVIGATION);
  readonly session = inject(Session); readonly configuration = inject(Configuration);
  readonly asText = text; readonly pagination = new Pagination();
  readonly rows = signal<Row[]>([]); readonly loading = signal(false);
  readonly current = signal('configs'); readonly issue = signal<Problem | null>(null); readonly notice = signal('');
  readonly details = signal<Row[]>([]); readonly detailPath = signal(''); readonly detailTitle = signal(''); readonly detailPagination = new Pagination(); readonly loadingDetails = signal(false);
  readonly deliveryFilters = signal<Row>({});
  private epoch = 0; private destroyed = false; private opened?: { close: () => void };
  constructor() { effect(() => { this.configuration.value(); this.session.user(); untracked(() => { this.opened?.close(); this.pagination.reset(); if (!this.tabs().some(tab => tab.path === this.current())) this.current.set(this.tabs()[0]?.path ?? ''); void this.load(); }); }); }
  admin(): boolean { return this.session.user()?.role === 'admin'; }
  available(): boolean { return this.admin() && this.configuration.enabled('integrations'); }
  tabs(): { path: string; label: string }[] {
    return [{ path: 'configs', label: 'Conectores' }, ...(this.configuration.enabled('api_keys') ? [{ path: 'service-principals', label: 'Actores tecnicos' }, { path: 'api-keys', label: 'API Keys' }] : []), ...(this.configuration.enabled('sso') ? [{ path: 'external-identities', label: 'Identidades' }] : []), ...(this.configuration.enabled('outgoing_webhooks') ? [{ path: 'webhook-subscriptions', label: 'Suscripciones' }, { path: 'webhook-deliveries', label: 'Entregas' }] : [])];
  }
  selectedIndex(): number { return Math.max(0, this.tabs().findIndex(tab => tab.path === this.current())); }
  choose(index: number): void { const tab = this.tabs()[index]; if (tab && tab.path !== this.current()) { this.current.set(tab.path); this.pagination.reset(); void this.load(); } }
  resize(size: number): void { if (this.pagination.resize(size)) void this.load(); }
  summary(row: Row): string {
    if (this.current() === 'configs') return text(row, 'provider') + ' · Revision ' + text(row, 'config_revision') + ' · ' + (row['is_active'] ? 'Activo' : 'Inactivo') + ' · ' + (row['secret_configured'] ? 'Secreto configurado' : 'Sin secreto');
    if (this.current() === 'service-principals') return (row['is_active'] ? 'Activo' : 'Revocado') + ' · ' + (row['approved_scopes'] as string[] ?? []).join(', ');
    if (this.current() === 'api-keys') return (row['revoked_at'] ? 'Revocada' : 'Emitida') + ' · ' + (row['scopes'] as string[] ?? []).join(', ');
    if (this.current() === 'webhook-subscriptions') return (row['enabled'] ? 'Habilitada' : 'Pausada') + ' · ' + (row['event_types'] as string[] ?? []).join(', ');
    if (this.current() === 'webhook-deliveries') return text(row, 'state') + ' · ' + text(row, 'attempt_count') + '/' + text(row, 'max_attempts') + ' intentos' + (row['retry_of_id'] ? ' · Replay de ' + text(row, 'retry_of_id') : '');
    return text(row, 'subject') + ' · ' + (row['revoked_at'] ? 'Revocada' : 'Activa');
  }
  async load(cursor = ''): Promise<void> {
    const epoch = ++this.epoch; this.rows.set([]); this.issue.set(null); this.loading.set(true); this.detailPath.set(''); this.details.set([]);
    try {
      if (!this.available() || !this.tabs().some(tab => tab.path === this.current())) return;
      const page = await this.api.get<Page>('/integrations/' + this.current(), { limit: String(this.pagination.size()), ...(cursor ? { cursor } : {}), ...(this.current() === 'webhook-deliveries' ? webhookFilters(this.deliveryFilters()) : {}) });
      if (epoch === this.epoch && !this.destroyed) { this.rows.set(page.items); this.pagination.accept(cursor, page.next_cursor); }
    } catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); }
    finally { if (epoch === this.epoch) this.loading.set(false); }
  }
  private open(title: string, fields: Field[], submit: (values: Row) => Promise<Row>, validate?: (values: Row) => string | null, afterSaved?: (result: Row) => void): void {
    if (!this.available()) return;
    const actor = this.session.user()?.id;
    let secret = ''; let saved: Row | undefined;
    const dialog = this.dialog.open(Editor, { width: '720px', maxWidth: '96vw', data: {
      title, fields: [...fields, { key: 'current_password', label: 'Contrasena local actual', type: 'password', required: true, min: 1, max: 128 }, { ...reason(), max: 1000 }], validate,
      submit: async (values: Row) => {
        const response = await submit(values);
        secret = text(response, 'api_key') || text(response, 'issued_secret'); delete response['api_key']; delete response['issued_secret'];
        saved = response;
      },
    } }); this.opened = dialog;
    dialog.afterClosed().subscribe(result => {
      if (!this.destroyed && this.available() && this.session.user()?.id === actor) {
        if (result === true || result === 'reload') { this.notice.set(result === 'reload' ? 'Cambios descartados; datos recargados.' : 'Cambio guardado.'); void this.load(); }
        if (result === true && secret) this.opened = this.dialog.open(IntegrationSecret, { width: '640px', maxWidth: '96vw', data: { title: 'Secreto emitido una sola vez', value: secret } });
        if (result === true && saved) afterSaved?.(saved);
      }
      secret = '';
    });
  }
  kindEnabled(row: Row): boolean { return this.configuration.enabled(row['kind'] === 'outgoing_webhook' ? 'outgoing_webhooks' : text(row, 'kind')); }
  newConnector(): void {
    if (!this.available()) return;
    const providers = [...(this.configuration.enabled('sso') ? ['oidc', 'saml', 'ldap'] : []), ...(this.configuration.enabled('devops') ? ['github', 'gitlab'] : []), ...(this.configuration.enabled('outgoing_webhooks') ? ['outgoing_webhook'] : [])];
    let provider = '';
    const dialog = this.dialog.open(Editor, { width: '480px', maxWidth: '96vw', data: { title: 'Proveedor', fields: [pick('provider', 'Proveedor', providers)], submit: async (values: Row) => { provider = String(values['provider']); } } });
    this.opened = dialog; dialog.afterClosed().subscribe(result => { if (result === true && !this.destroyed) void this.connector(undefined, provider); });
  }
  async connector(row?: Row, provider = row ? text(row, 'provider') : ''): Promise<void> {
    if (!this.available() || row && !this.kindEnabled(row)) return;
    const epoch = this.epoch;
    try {
      const [departments, users] = await Promise.all([this.api.all('/catalogs/departments'), ['oidc', 'saml', 'ldap'].includes(provider) ? this.api.all('/users') : Promise.resolve([])]);
      if (epoch !== this.epoch || this.destroyed) return;
      const config = row?.['config'] as Row ?? {};
      const field = (key: string, label: string, max: number, type: Field['type'] = 'text'): Field => ({ key, label, type, required: true, max, value: config[key] });
      const fields: Field[] = [{ key: 'name', label: 'Nombre', required: true, max: 120, value: row?.['name'] }, pick('scope_kind', 'Alcance', ['organization', 'department'], row?.['scope_kind']), { key: 'department_id', label: 'Departamento', type: 'select', requiredWhen: { key: 'scope_kind', values: ['department'] }, options: options(departments), value: row?.['department_id'] }];
      if (['oidc', 'saml', 'ldap'].includes(provider)) fields.push({ key: 'emergency_admin_id', label: 'Administrador local de emergencia', type: 'select', required: true, options: options(users.filter(user => user['role'] === 'admin' && user['is_active'] === true), 'display_name'), value: config['emergency_admin_id'] }, { key: 'revocation_window_seconds', label: 'Ventana de revocacion (s)', type: 'number', required: true, min: 30, max: 3600, value: config['revocation_window_seconds'] });
      if (provider === 'oidc') {
        fields.push(field('issuer', 'Issuer HTTPS exacto', 512), field('client_id', 'Client ID', 254), pick('token_auth_method', 'Autenticacion del cliente', ['client_secret_basic', 'client_secret_post', 'none'], config['token_auth_method']));
        for (const [prefix, label] of [['authorization_endpoint', 'Autorizacion'], ['token_endpoint', 'Tokens'], ['jwks_endpoint', 'JWKS']]) fields.push(...endpointFields(prefix, label, config[prefix] as Row));
        fields.push({ key: 'credential', label: 'Client secret', type: 'password', min: 1, max: 16384, ...(!row?.['secret_configured'] ? { requiredWhen: { key: 'token_auth_method', values: ['client_secret_basic', 'client_secret_post'] } } : {}) });
      } else if (provider === 'saml') fields.push(field('entity_id', 'Entity ID', 512), field('idp_certificate_pem', 'Certificado publico IdP PEM', 16384, 'textarea'), field('sp_certificate_pem', 'Certificado publico SP PEM', 16384, 'textarea'), ...endpointFields('sso_endpoint', 'SSO', config['sso_endpoint'] as Row), { key: 'credential', label: 'Clave privada SP PEM', type: 'secret', required: !row, min: 1, max: 65536 });
      else if (provider === 'ldap') fields.push(...endpointFields('', 'Directorio', config, false), { key: 'port', label: 'Puerto TLS', type: 'number', min: 1, max: 65535, required: true, value: config['port'] }, pick('security', 'Proteccion', ['ldaps', 'starttls'], config['security']), field('bind_dn', 'Bind DN', 1000), field('user_search_base', 'Base de busqueda DN', 1000), pick('username_attribute', 'Atributo de usuario', ['uid', 'sAMAccountName', 'userPrincipalName'], config['username_attribute']), pick('subject_attribute', 'Identificador estable', ['entryUUID', 'objectGUID'], config['subject_attribute']), { key: 'credential', label: 'Credencial del bind', type: 'password', required: !row, min: 1, max: 16384 });
      else if (provider === 'github' || provider === 'gitlab') {
        fields.push(...endpointFields('api_endpoint', 'API', config['api_endpoint'] as Row), field('web_origin', 'Origen web HTTPS', 512));
        if (!row) fields.push({ key: 'repository_id', label: 'ID numerico del repositorio', required: true, max: 128, pattern: '^[1-9][0-9]*$' }, { key: 'repository_path', label: 'Ruta exacta del repositorio', required: true, max: 512 });
        fields.push({ key: 'access_token', label: 'Access token del proveedor', type: 'password', required: !row, min: 1, max: 16384 }, { key: 'webhook_secret', label: provider === 'gitlab' ? 'Token nativo del webhook GitLab' : 'Secreto HMAC del webhook GitHub', type: 'password', required: !row, min: 16, max: 1024 });
      } else fields.push(...endpointFields('endpoint', 'Webhook', config['endpoint'] as Row), { key: 'credential', label: 'Secreto de firma opcional', type: 'password', min: 32, max: 1024 });
      this.open(row ? 'Editar conector ' + provider : 'Crear conector ' + provider, fields, values => this.api.command('/integrations/configs' + (row ? '/' + text(row, 'id') : ''), integrationPayload(provider, values, row), row ? 'PATCH' : 'POST'), values => {
        if (fields.filter(field => field.key.endsWith('audience_approved')).some(field => values[field.key] !== true)) return 'La audiencia y el destino requieren aprobacion expresa.';
        if ((provider === 'github' || provider === 'gitlab') && !!values['access_token'] !== !!values['webhook_secret']) return 'La rotacion requiere ambos secretos del proveedor.';
        return null;
      });
    } catch (error) { this.issue.set(problem(error)); }
  }
  test(row: Row): void {
    if (!this.kindEnabled(row)) return;
    const sso = row['kind'] === 'sso';
    const fields: Field[] = [{ key: 'confirmed', label: 'Confirmo este destino y audiencia para la prueba sintetica', type: 'check' }];
    if (sso) fields.push({ key: 'revocation_confirmed', label: 'Confirmo la ventana de revocacion configurada', type: 'check' }, { key: 'emergency_password', label: 'Contrasena del administrador local de emergencia', type: 'password', required: true, min: 1, max: 128 });
    if (row['provider'] === 'ldap') fields.push({ key: 'test_username', label: 'Usuario de prueba del directorio', required: true, max: 254 }, { key: 'test_password', label: 'Contrasena de prueba del directorio', type: 'password', required: true, min: 1, max: 16384 });
    this.open('Probar ' + text(row, 'name'), fields, values => this.api.command('/integrations/configs/' + text(row, 'id') + '/test', { ...values, expected_version: version(row), revocation_confirmed: sso ? values['revocation_confirmed'] : null, emergency_password: sso ? values['emergency_password'] : null, test_username: row['provider'] === 'ldap' ? values['test_username'] : null, test_password: row['provider'] === 'ldap' ? values['test_password'] : null }), values => values['confirmed'] !== true || sso && values['revocation_confirmed'] !== true ? 'La prueba requiere confirmar destino, audiencia y revocacion.' : null, result => {
      if (result['authorization_url']) { try { this.navigateSSO(ssoDestination(text(result, 'authorization_url'))); } catch (error) { this.issue.set(problem(error)); } }
      else if (sso && result['ready']) void this.session.finishSSO(text(result, 'transaction_id'), 'probe').then(() => { this.notice.set('Prueba aprobada; conector inactivo.'); void this.load(); }).catch(error => this.issue.set(problem(error)));
      else this.notice.set(result['passed'] ? 'Prueba aprobada; conector inactivo.' : 'Prueba fallida; conector inactivo.');
    });
  }
  activation(row: Row): void { if (this.kindEnabled(row)) this.open(row['is_active'] ? 'Desactivar conector' : 'Activar revision probada', [], values => this.api.command('/integrations/configs/' + text(row, 'id') + (row['is_active'] ? '/deactivate' : '/activate'), { ...values, expected_version: version(row) })); }
  private updateConfig(row: Row, config: Row, values: Row): Promise<Row> {
    return this.api.command('/integrations/configs/' + text(row, 'id'), { name: row['name'], scope_kind: row['scope_kind'], department_id: row['department_id'], config, expected_version: version(row), current_password: values['current_password'], reason: values['reason'] }, 'PATCH');
  }
  entries(row: Row, jit: boolean): void {
    if (!this.available() || !this.kindEnabled(row)) return;
    const config = row['config'] as Row, records = config[jit ? 'jit_mappings' : 'repositories'] as Row[];
    let selected = '';
    const dialog = this.dialog.open(Editor, { width: '640px', maxWidth: '96vw', data: {
      title: jit ? 'Mapeos JIT' : 'Repositorios aprobados',
      fields: [{ key: 'entry', label: jit ? 'Mapeo' : 'Repositorio', type: 'select', required: true, options: [
        { value: 'new', label: jit ? 'Nuevo mapeo' : 'Nuevo repositorio', disabled: records.length >= (jit ? 20 : 100) },
        ...records.map((record, index) => ({ value: String(index), label: jit ? text(record, 'attribute') + ' = ' + text(record, 'value') + ' · ' + text(record, 'role') : text(record, 'repository_id') + ' · ' + text(record, 'path') })),
        ...(jit ? [{ value: 'disable', label: 'Retirar todos los mapeos y desactivar JIT' }] : []),
      ] }], submit: async (values: Row) => { selected = String(values['entry']); },
    } }); this.opened = dialog;
    dialog.afterClosed().subscribe(result => { if (result === true && !this.destroyed) void this.entry(row, jit, selected); });
  }
  private async entry(row: Row, jit: boolean, selected: string): Promise<void> {
    if (!this.available() || !this.kindEnabled(row)) return;
    const config = row['config'] as Row, key = jit ? 'jit_mappings' : 'repositories', records = config[key] as Row[];
    if (jit && selected === 'disable') {
      this.open('Retirar todos los mapeos JIT', [{ key: 'confirmed', label: 'Retirar todos los mapeos y desactivar JIT', type: 'check' }], values => this.updateConfig(row, { ...config, jit_enabled: false, jit_mappings: [], jit_email_attribute: null, jit_name_attribute: null }, values), values => values['confirmed'] === true ? null : 'Confirma la retirada de todos los mapeos.'); return;
    }
    const index = selected === 'new' ? -1 : Number(selected), record = records[index];
    if (selected !== 'new' && (!Number.isInteger(index) || !record)) return;
    const fields: Field[] = record ? [pick('operation', 'Accion', ['change', 'remove'])] : [];
    let departments: Row[] = [];
    const epoch = this.epoch;
    try { if (jit) departments = await this.api.all('/catalogs/departments'); }
    catch (error) { this.issue.set(problem(error)); return; }
    if (this.destroyed || epoch !== this.epoch) return;
    const directoryAttributes = ['memberOf', 'department', 'departmentNumber', 'employeeType', 'title', 'ou', 'userPrincipalName', 'mail', 'displayName', 'givenName', 'sn'];
    if (jit) fields.push(
      row['provider'] === 'ldap' ? pick('attribute', 'Atributo', directoryAttributes, record?.['attribute']) : { key: 'attribute', label: 'Atributo', required: true, max: 120, pattern: '^[a-zA-Z0-9_.:/-]+$', value: record?.['attribute'] },
      { key: 'value', label: 'Valor literal exacto', required: true, max: 512, preserveWhitespace: true, pattern: '^[^\\r\\n\\x00]+$', value: record?.['value'] },
      pick('role', 'Rol permitido', ['lider', 'colaborador'], record?.['role']),
      { key: 'department_id', label: 'Departamento aprobado', type: 'select', required: true, options: options(departments), value: record?.['department_id'] },
      row['provider'] === 'ldap' ? pick('jit_email_attribute', 'Atributo de correo', directoryAttributes, config['jit_email_attribute']) : { key: 'jit_email_attribute', label: 'Atributo de correo verificado', required: true, max: 120, value: config['jit_email_attribute'] },
      row['provider'] === 'ldap' ? pick('jit_name_attribute', 'Atributo de nombre', directoryAttributes, config['jit_name_attribute']) : { key: 'jit_name_attribute', label: 'Atributo de nombre', required: true, max: 120, value: config['jit_name_attribute'] },
      { key: 'jit_enabled', label: 'JIT habilitado solo para los mapeos aprobados', type: 'check', value: config['jit_enabled'] },
    );
    else fields.push({ key: 'repository_id', label: 'ID numerico del repositorio', required: true, max: 128, pattern: '^[1-9][0-9]*$', value: record?.['repository_id'] }, { key: 'path', label: 'Ruta exacta', required: true, max: 512, value: record?.['path'] });
    const updated = (values: Row): Row[] => approvedEntries(records, index, record ? String(values['operation']) : 'add', Object.fromEntries((jit ? ['attribute', 'value', 'role', 'department_id'] : ['repository_id', 'path']).map(key => [key, values[key]])));
    this.open(jit ? 'Mapeo JIT explicito' : 'Repositorio aprobado', fields, values => this.updateConfig(row, { ...config, [key]: updated(values), ...(jit ? { jit_enabled: values['jit_enabled'], jit_email_attribute: values['jit_email_attribute'], jit_name_attribute: values['jit_name_attribute'] } : {}) }, values), values => {
      if (record && !values['operation']) return null;
      const entries = updated(values);
      if (jit) {
        if (entries.length > 20 || !!entries.length !== values['jit_enabled']) return 'JIT requiere uno a veinte mapeos explicitos o su desactivacion sin mapeos.';
        if (new Set(entries.map(entry => JSON.stringify([entry['attribute'], entry['value']]))).size !== entries.length) return 'El atributo y valor de cada mapeo deben ser unicos.';
        if (row['provider'] === 'oidc' && values['jit_email_attribute'] !== 'email') return 'OIDC requiere el atributo estandar email verificado.';
      } else if (entries.length < 1 || entries.length > 100 || new Set(entries.map(entry => entry['repository_id'])).size !== entries.length || new Set(entries.map(entry => text(entry, 'path').toLowerCase())).size !== entries.length) return 'Selecciona uno a cien repositorios con ID y ruta unicos.';
      return null;
    });
  }
  health(row: Row): void { this.detailPath.set('/integrations/configs/' + text(row, 'id') + '/checks'); this.detailTitle.set('Pruebas de ' + text(row, 'name')); this.detailPagination.reset(); void this.loadDetails(); }
  inbox(row: Row): void { this.detailPath.set('/integrations/devops/' + text(row, 'id') + '/inbox'); this.detailTitle.set('Recepcion Git de ' + text(row, 'name')); this.detailPagination.reset(); void this.loadDetails(); }
  async loadDetails(cursor = ''): Promise<void> {
    const epoch = this.epoch, path = this.detailPath(); if (!path || !this.available()) return;
    this.loadingDetails.set(true);
    try { const page = await this.api.get<Page>(path, { limit: String(this.detailPagination.size()), ...(cursor ? { cursor } : {}) }); if (epoch === this.epoch && path === this.detailPath() && !this.destroyed) { this.details.set(page.items); this.detailPagination.accept(cursor, page.next_cursor); } }
    catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); }
    finally { if (epoch === this.epoch) this.loadingDetails.set(false); }
  }
  resizeDetails(size: number): void { if (this.detailPagination.resize(size)) void this.loadDetails(); }
  async subscription(row?: Row): Promise<void> {
    if (!this.available() || !this.configuration.enabled('outgoing_webhooks')) return;
    const epoch = this.epoch;
    try {
      const [departments, users, connectors] = await Promise.all([this.api.all('/catalogs/departments'), this.api.all('/users'), this.api.all('/integrations/configs')]);
      if (epoch !== this.epoch || this.destroyed) return;
      this.open(row ? 'Editar o pausar suscripcion' : 'Crear suscripcion webhook', [
        { key: 'integration_id', label: 'Conector saliente', type: 'select', required: true, options: options(connectors.filter(connector => connector['kind'] === 'outgoing_webhook' && (!row || connector['id'] === row['integration_id']))), value: row?.['integration_id'] },
        { key: 'owner_user_id', label: 'Propietario humano', type: 'select', required: true, options: options(users.filter(user => row ? user['id'] === row['owner_user_id'] : user['is_active'] === true), 'display_name'), value: row?.['owner_user_id'] },
        { key: 'department_ids', label: 'Departamentos aprobados', type: 'multi', required: true, options: options(departments), value: row?.['department_ids'] },
        { key: 'event_types', label: 'Eventos aprobados', type: 'multi', required: true, options: WEBHOOK_EVENTS.map(value => ({ value, label: value })), value: row?.['event_types'] },
        { key: 'max_attempts', label: 'Intentos maximos', type: 'number', required: true, min: 1, max: 10, value: row?.['max_attempts'] },
        { key: 'retry_base_seconds', label: 'Espera inicial (s)', type: 'number', required: true, min: 5, max: 300, value: row?.['retry_base_seconds'] },
        { key: 'max_delay_seconds', label: 'Espera maxima (s)', type: 'number', required: true, min: 300, max: 86400, value: row?.['max_delay_seconds'] },
        { key: 'enabled', label: 'Habilitada', type: 'check', value: row?.['enabled'] },
      ], values => this.api.command('/integrations/webhook-subscriptions' + (row ? '/' + text(row, 'id') : ''), { ...values, expected_version: row ? version(row) : 0 }, row ? 'PATCH' : 'POST'));
    } catch (error) { this.issue.set(problem(error)); }
  }
  terminal(row: Row): boolean { return ['delivered', 'dead_letter', 'cancelled'].includes(text(row, 'state')); }
  replay(row: Row): void {
    if (!this.terminal(row) || !this.configuration.enabled('outgoing_webhooks')) return;
    const idempotency = crypto.randomUUID();
    this.open('Crear nueva entrega vinculada', [], values => this.api.command('/integrations/webhook-subscriptions/' + text(row, 'subscription_id') + '/replay', replayPayload(row, values, idempotency)));
  }
  attempts(row: Row): void { this.detailPath.set('/integrations/webhook-deliveries/' + text(row, 'id') + '/attempts'); this.detailTitle.set('Intentos de ' + text(row, 'id')); this.detailPagination.reset(); void this.loadDetails(); }
  async filterDeliveries(): Promise<void> {
    if (!this.available() || !this.configuration.enabled('outgoing_webhooks')) return;
    const epoch = this.epoch;
    try {
      const subscriptions = await this.api.all('/integrations/webhook-subscriptions'); if (epoch !== this.epoch || this.destroyed) return;
      const current = this.deliveryFilters();
      const dialog = this.dialog.open(Editor, { width: '640px', maxWidth: '96vw', data: {
        title: 'Filtrar entregas', confirm: 'Aplicar', fields: [
          pick('state', 'Estado', ['all', 'pending', 'sending', 'delivered', 'dead_letter', 'cancelled'], current['state'] || 'all'),
          { key: 'subscription_id', label: 'Suscripcion', type: 'select', required: true, options: [{ value: 'all', label: 'Todas' }, ...options(subscriptions, 'id')], value: current['subscription_id'] || 'all' },
          { key: 'since', label: 'Desde UTC', type: 'datetime-local', value: current['since'] }, { key: 'until', label: 'Hasta UTC', type: 'datetime-local', value: current['until'] },
        ], validate: (values: Row) => values['since'] && !utcInput(values['since']) || values['until'] && !utcInput(values['until']) || values['since'] && values['until'] && String(values['since']) > String(values['until']) ? 'El intervalo UTC no es valido.' : null,
        submit: async (values: Row) => { this.deliveryFilters.set(values); },
      } }); this.opened = dialog;
      dialog.afterClosed().subscribe(result => { if (result === true && !this.destroyed) { this.pagination.reset(); void this.load(); } });
    } catch (error) { this.issue.set(problem(error)); }
  }
  async principal(row?: Row): Promise<void> {
    if (!this.available() || !this.configuration.enabled('api_keys')) return;
    const epoch = this.epoch;
    try {
      const departments = await this.api.all('/catalogs/departments');
      if (epoch !== this.epoch || this.destroyed) return;
      this.open(row ? 'Permisos y revocacion del actor tecnico' : 'Crear actor tecnico', [
        { key: 'name', label: 'Nombre', required: true, max: 120, value: row?.['name'] },
        { key: 'department_ids', label: 'Departamentos aprobados', type: 'multi', required: true, options: options(departments), value: row?.['department_ids'] },
        { key: 'approved_scopes', label: 'Acciones aprobadas', type: 'multi', required: true, options: PRINCIPAL_SCOPES.map(value => ({ value, label: value })), value: row?.['approved_scopes'] },
        { key: 'is_active', label: 'Activo', type: 'check', value: row?.['is_active'] },
      ], values => this.api.command('/integrations/service-principals' + (row ? '/' + text(row, 'id') : ''), { ...values, expected_version: row ? version(row) : 0 }, row ? 'PATCH' : 'POST'));
    } catch (error) { this.issue.set(problem(error)); }
  }
  async key(row?: Row): Promise<void> {
    if (!this.available() || !this.configuration.enabled('api_keys')) return;
    const epoch = this.epoch;
    try {
      const [departments, users, principals] = await Promise.all([this.api.all('/catalogs/departments'), this.api.all('/users'), this.api.all('/integrations/service-principals')]);
      if (epoch !== this.epoch || this.destroyed) return;
      this.open(row ? 'Rotar API Key' : 'Emitir API Key', [
        { key: 'name', label: 'Nombre', required: true, max: 120, value: row?.['name'] },
        { key: 'service_principal_id', label: 'Actor tecnico', type: 'select', required: true, options: options(principals.filter(principal => row ? principal['id'] === row['service_principal_id'] : principal['is_active'] === true)), value: row?.['service_principal_id'] },
        { key: 'owner_user_id', label: 'Propietario humano', type: 'select', required: true, options: options(users.filter(user => row ? user['id'] === row['owner_user_id'] : user['is_active'] === true), 'display_name'), value: row?.['owner_user_id'] },
        { key: 'scopes', label: 'Scopes', type: 'multi', required: true, options: KEY_SCOPES.filter(value => !row || (row['scopes'] as string[]).includes(value)).map(value => ({ value, label: value })), value: row?.['scopes'] },
        { key: 'department_ids', label: 'Departamentos', type: 'multi', required: true, options: options(departments.filter(department => !row || (row['department_ids'] as string[]).includes(text(department, 'id')))), value: row?.['department_ids'] },
        { key: 'rate_per_minute', label: 'Solicitudes por minuto', type: 'number', required: true, min: 1, max: row ? Number(row['rate_per_minute']) : 1000, value: row?.['rate_per_minute'] },
        { key: 'expires_at', label: 'Expiracion UTC', type: 'datetime-local', required: true },
        pick('network_policy', 'Acceso de red', ['unrestricted', 'cidr'], row ? row['allowed_networks'] ? 'cidr' : 'unrestricted' : undefined),
        { key: 'allowed_networks', label: 'Redes CIDR aprobadas', type: 'textarea', max: 5000, requiredWhen: { key: 'network_policy', values: ['cidr'] }, value: (row?.['allowed_networks'] as string[] ?? []).join('\n') },
      ], values => this.api.command('/integrations/api-keys' + (row ? '/' + text(row, 'id') + '/rotate' : ''), apiKeyPayload(values, row)), values => !utcInput(values['expires_at']) ? 'La fecha y hora UTC no son validas.' : row?.['allowed_networks'] && values['network_policy'] === 'unrestricted' ? 'La rotacion no admite ampliar el acceso de red.' : null);
    } catch (error) { this.issue.set(problem(error)); }
  }
  revoke(row: Row): void {
    if (row['revoked_at']) return;
    const path = this.current();
    this.open(path === 'api-keys' ? 'Revocar API Key' : 'Revocar identidad empresarial', [], values => this.api.command('/integrations/' + path + '/' + text(row, 'id') + '/revoke', { ...values, expected_version: version(row) }));
  }
  ngOnDestroy(): void { this.destroyed = true; ++this.epoch; this.opened?.close(); this.rows.set([]); }
}