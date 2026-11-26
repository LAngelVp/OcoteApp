import { DatePipe } from '@angular/common';
import { Component, effect, inject, signal, untracked } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Api, Row, text, version } from '../core/api';
import { Configuration } from '../core/configuration';
import { Problem, problem } from '../core/problem';
import { Session } from '../core/session';
import { CHANNELS, TRIGGERS } from '../operations/notifications.page';
import { Editor, Field, options, reason } from '../shared/editor';
import { Feedback } from '../shared/feedback';

const pick = (key: string, label: string, values: string[], value?: unknown): Field => ({ key, label, type: 'select', required: true, options: values.map(value => ({ value, label: value })), value });
const number = (key: string, label: string, min: number, max: number, value?: unknown): Field => ({ key, label, type: 'number', required: true, min, max, value });
export const addresses = (value: unknown): string[] => String(value ?? '').split(/\r?\n/).map(line => line.trim()).filter(Boolean);

export function connectorPayload(provider: string, values: Row, record?: Row): Row {
  const keys = ['host', 'connect_timeout_seconds', 'read_timeout_seconds', 'rate_per_minute', 'audience_approved', ...(provider === 'smtp' ? ['port', 'security', 'authentication', 'sender_email', 'sender_name', 'test_recipient'] : ['destination'])];
  const config: Row = Object.fromEntries(keys.map(key => [key, values[key]]));
  Object.assign(config, { provider, approved_addresses: addresses(values['approved_addresses']), allow_private_endpoint: provider === 'smtp' && values['allow_private_endpoint'] === true });
  if (provider === 'smtp') config['username'] = values['authentication'] === 'login' ? values['username'] : null;
  return { name: values['name'], scope_kind: values['scope_kind'], department_id: values['scope_kind'] === 'department' ? values['department_id'] : null,
    config, expected_version: record ? version(record) : 0, reason: values['reason'], current_password: values['current_password'],
    ...(typeof values['credential'] === 'string' && values['credential'].length > 0 ? { credential: values['credential'] } : {}) };
}

export function rulePayload(values: Row, record?: Row): Row {
  return { ...values, department_id: values['department_id'] || null, expected_version: record ? version(record) : 0,
    threshold_days: ['upcoming_due', 'overdue'].includes(String(values['trigger'])) ? values['threshold_days'] : null };
}

@Component({
  imports: [DatePipe, MatButtonModule, MatIconModule, MatTabsModule, MatTooltipModule, Feedback],
  styles: [`:host{display:block;min-width:0}section{padding:24px 0;border-bottom:1px solid var(--ocote-border)}h2{font-size:1.25rem}.toolbar,.line{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.line{padding:16px 0;border-bottom:1px solid var(--ocote-border)}.line p{margin:0;min-width:0;overflow-wrap:anywhere}.meta{font-size:.875rem;color:var(--ocote-text-secondary)}.actions{display:flex;gap:4px;flex-wrap:wrap}.empty{padding:24px 0;color:var(--ocote-text-secondary)}.result{padding:12px 0;border-bottom:1px solid var(--ocote-border)}`],
  template: `<header class="page-heading"><div><p class="eyebrow">ADMINISTRACION</p><h1>Notificaciones</h1></div><button mat-icon-button aria-label="Recargar notificaciones" matTooltip="Recargar" (click)="load()" [disabled]="loading()"><mat-icon>refresh</mat-icon></button></header><ocote-feedback [issue]="issue()" />@if (notice()) { <p role="status">{{ notice() }}</p> }@if (loading()) { <p role="status">Cargando configuracion...</p> }
  @if (admin() && configuration.enabled('notifications')) { <mat-tab-group animationDuration="0ms">
    @if (configuration.enabled('integrations')) { <mat-tab label="Conectores"><section><header class="toolbar"><h2>Proveedores</h2><button mat-stroked-button (click)="newConnector()"><mat-icon>add</mat-icon>Conector</button></header>@for (row of connectors(); track row['id']) { <div class="line"><div><p><strong>{{ row['name'] }}</strong> · {{ row['provider'] }}</p><p class="meta">{{ row['scope_kind'] === 'department' ? 'Departamento' : 'Organizacion' }} · Revision {{ row['config_revision'] }} · {{ row['is_active'] ? 'Activo' : 'Inactivo' }} · {{ row['secret_configured'] ? 'Credencial configurada' : 'Sin credencial' }}</p></div><div class="actions"><button mat-icon-button aria-label="Editar conector" matTooltip="Editar conector" (click)="connector(row)"><mat-icon>edit</mat-icon></button><button mat-icon-button aria-label="Probar conector" matTooltip="Probar conector" (click)="test(row)" [disabled]="!channelEnabled(row)"><mat-icon>science</mat-icon></button><button mat-icon-button [attr.aria-label]="row['is_active'] ? 'Desactivar conector' : 'Activar conector'" [matTooltip]="row['is_active'] ? 'Desactivar' : 'Activar'" (click)="activation(row)" [disabled]="!row['is_active'] && !row['tested_at']"><mat-icon>{{ row['is_active'] ? 'pause_circle' : 'play_circle' }}</mat-icon></button><button mat-icon-button aria-label="Historial de pruebas" matTooltip="Historial de pruebas" (click)="health(row)"><mat-icon>monitor_heart</mat-icon></button></div></div> } @empty { <p class="empty">Sin conectores configurados.</p> }</section>@if (checksName()) { <section><h2>{{ checksName() }}</h2>@for (row of checks(); track row['id']) { <p class="result">{{ row['status'] === 'passed' ? 'Aprobada' : 'Fallida' }} · {{ row['result_code'] }} · {{ row['latency_ms'] }} ms · {{ asText(row, 'created_at') | date:'medium' }}</p> } @empty { <p class="empty">Sin pruebas registradas.</p> }</section> }</mat-tab> }
    <mat-tab label="Reglas"><section><header class="toolbar"><h2>Reglas y umbrales</h2><button mat-stroked-button (click)="rule()"><mat-icon>add</mat-icon>Regla</button></header>@for (row of rules(); track row['id']) { <div class="line"><div><p><strong>{{ row['name'] }}</strong> · {{ trigger(row) }}</p><p class="meta">{{ row['enabled'] ? 'Habilitada' : 'Deshabilitada' }} · {{ channelNames(row) }}@if (row['threshold_days'] != null) { · {{ row['threshold_days'] }} dias {{ row['day_basis'] === 'business' ? 'habiles' : 'naturales' }} }</p></div><button mat-icon-button aria-label="Editar regla" matTooltip="Editar regla" (click)="rule(row)"><mat-icon>edit</mat-icon></button></div> } @empty { <p class="empty">Sin reglas configuradas.</p> }</section></mat-tab>
    <mat-tab label="Actores tecnicos"><section><header class="toolbar"><h2>Permisos del worker</h2><button mat-stroked-button (click)="principal()"><mat-icon>add</mat-icon>Actor tecnico</button></header>@for (row of principals(); track row['id']) { <div class="line"><div><p><strong>{{ row['name'] }}</strong></p><p class="meta">{{ row['is_active'] ? 'Activo' : 'Revocado' }}</p></div><button mat-icon-button aria-label="Editar actor tecnico" matTooltip="Permisos y revocacion" (click)="principal(row)"><mat-icon>manage_accounts</mat-icon></button></div> } @empty { <p class="empty">Sin actores tecnicos.</p> }</section></mat-tab>
  </mat-tab-group> } @else { <p class="empty">Administracion de notificaciones no disponible.</p> }`,
})
export class NotificationsAdminPage {
  readonly asText = text;
  private readonly api = inject(Api); private readonly dialog = inject(MatDialog);
  readonly session = inject(Session); readonly configuration = inject(Configuration);
  readonly connectors = signal<Row[]>([]); readonly rules = signal<Row[]>([]); readonly departments = signal<Row[]>([]);
  readonly checks = signal<Row[]>([]); readonly checksName = signal('');
  readonly principals = signal<Row[]>([]);
  readonly loading = signal(false); readonly issue = signal<Problem | null>(null); readonly notice = signal('');
  private epoch = 0;
  constructor() { effect(() => { this.configuration.value(); this.session.user(); untracked(() => void this.load()); }); }
  admin(): boolean { return this.session.user()?.role === 'admin'; }
  trigger(row: Row): string { return TRIGGERS[text(row, 'trigger')] ?? 'Notificacion'; }
  channelNames(row: Row): string { return CHANNELS.filter(channel => (row['channels'] as string[]).includes(channel.value)).map(channel => channel.label).join(', '); }
  channelEnabled(row: Row): boolean { return this.configuration.enabled(row['provider'] === 'smtp' ? 'email_notifications' : 'corporate_messaging'); }
  async load(): Promise<void> {
    const epoch = ++this.epoch; this.loading.set(true); this.issue.set(null); this.connectors.set([]); this.rules.set([]); this.departments.set([]); this.checks.set([]); this.checksName.set(''); this.principals.set([]);
    try { if (!this.admin() || !this.configuration.enabled('notifications')) return;
      const [rules, departments, connectors, principals] = await Promise.all([this.api.all('/notification-rules'), this.api.all('/catalogs/departments'), this.configuration.enabled('integrations') ? this.api.all('/notification-connectors') : Promise.resolve([]), this.api.all('/notifications/service-principals')]);
      if (epoch === this.epoch) { this.rules.set(rules); this.departments.set(departments); this.connectors.set(connectors); this.principals.set(principals); }
    } catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); }
    finally { if (epoch === this.epoch) this.loading.set(false); }
  }
  private open(title: string, fields: Field[], submit: (values: Row) => Promise<unknown>, validate?: (values: Row) => string | null): void {
    this.notice.set('');
    this.dialog.open(Editor, { width: '720px', maxWidth: '96vw', data: { title, fields: [...fields, { key: 'current_password', label: 'Contrasena actual', type: 'password', required: true, min: 1, max: 128 }, { ...reason(), max: 1000 }], submit, validate } }).afterClosed().subscribe(result => { if (result) { if (result === 'reload') this.notice.set('Cambios descartados; datos recargados.'); else if (!this.notice()) this.notice.set('Cambio guardado.'); void this.load(); } });
  }
  newConnector(): void {
    let provider = '';
    this.dialog.open(Editor, { width: '480px', maxWidth: '96vw', data: { title: 'Proveedor del conector', fields: [pick('provider', 'Proveedor', ['smtp', 'slack', 'teams', 'telegram'])], submit: async (values: Row) => { provider = String(values['provider']); } } }).afterClosed().subscribe(result => { if (result === true) this.connector(undefined, provider); });
  }
  connector(row?: Row, provider = row ? text(row, 'provider') : ''): void {
    const config = row?.['config'] as Row ?? {};
    const fields: Field[] = [{ key: 'name', label: 'Nombre', required: true, max: 120, value: row?.['name'] }, pick('scope_kind', 'Alcance', ['organization', 'department'], row?.['scope_kind']), { key: 'department_id', label: 'Departamento', type: 'select', options: options(this.departments()), requiredWhen: { key: 'scope_kind', values: ['department'] }, value: row?.['department_id'] }, { key: 'host', label: 'Hostname aprobado', required: true, max: 253, value: config['host'] }, { key: 'approved_addresses', label: 'Direcciones IP aprobadas', type: 'textarea', required: true, max: 800, value: (config['approved_addresses'] as string[] ?? []).join('\n') }, number('connect_timeout_seconds', 'Tiempo de conexion (s)', 1, 10, config['connect_timeout_seconds']), number('read_timeout_seconds', 'Tiempo de lectura (s)', 1, 15, config['read_timeout_seconds']), number('rate_per_minute', 'Intentos por minuto', 1, 1000, config['rate_per_minute'])];
    if (provider === 'smtp') fields.push(number('port', 'Puerto TLS', 1, 65535, config['port']), pick('security', 'Proteccion', ['tls', 'starttls'], config['security']), pick('authentication', 'Autenticacion', ['none', 'login'], config['authentication']), { key: 'username', label: 'Usuario SMTP', requiredWhen: { key: 'authentication', values: ['login'] }, max: 254, value: config['username'] }, { key: 'sender_email', label: 'Correo remitente', type: 'email', required: true, max: 254, value: config['sender_email'] }, { key: 'sender_name', label: 'Nombre remitente', required: true, max: 120, value: config['sender_name'] }, { key: 'test_recipient', label: 'Destinatario de prueba aprobado', type: 'email', required: true, max: 254, value: config['test_recipient'] }, { key: 'allow_private_endpoint', label: 'Apruebo este host y estas IP privadas SMTP', type: 'check', value: config['allow_private_endpoint'] });
    else fields.push({ key: 'destination', label: provider === 'telegram' ? 'Chat ID o canal aprobado' : 'Audiencia del webhook aprobada', required: true, max: 200, value: config['destination'] });
    fields.push({ key: 'audience_approved', label: 'Apruebo expresamente este destino y su audiencia', type: 'check', value: config['audience_approved'] }, { key: 'credential', label: provider === 'smtp' ? 'Credencial SMTP' : provider === 'telegram' ? 'Token del bot' : 'URL privada del webhook', type: 'password', required: !row && provider !== 'smtp', min: 1, max: 16384 });
    this.open(row ? 'Editar conector ' + provider : 'Crear conector ' + provider, fields, values => this.api.command('/notification-connectors' + (row ? '/' + text(row, 'id') : ''), connectorPayload(provider, values, row), row ? 'PATCH' : 'POST'), values => addresses(values['approved_addresses']).length > 16 ? 'El maximo es de 16 direcciones IP aprobadas.' : null);
  }
  test(row: Row): void {
    this.open('Probar destino sintetico confirmado', [{ key: 'destination', label: 'Destino exacto aprobado', required: true, max: 254 }, { key: 'confirmed', label: 'Confirmo el envio sintetico a este destino y audiencia', type: 'check' }], async values => {
      const result = await this.api.command('/notification-connectors/' + text(row, 'id') + '/tests', { ...values, expected_version: version(row) });
      this.notice.set(result['passed'] ? 'Prueba aprobada; conector inactivo.' : 'Prueba fallida; conector inactivo.');
    }, values => values['confirmed'] === true ? null : 'Confirma expresamente el destino y la audiencia.');
  }
  activation(row: Row): void { this.open(row['is_active'] ? 'Desactivar conector' : 'Activar conector probado', [], values => this.api.command('/notification-connectors/' + text(row, 'id') + (row['is_active'] ? '/deactivate' : '/activate'), { ...values, expected_version: version(row) })); }
  principal(row?: Row): void {
    this.open(row ? 'Permisos del actor tecnico' : 'Crear actor tecnico', [{ key: 'name', label: 'Nombre', required: true, max: 120, value: row?.['name'] }, { key: 'department_ids', label: 'Departamentos aprobados', type: 'multi', required: true, options: options(this.departments()), value: row?.['department_ids'] }, { key: 'approved_scopes', label: 'Acciones aprobadas', type: 'multi', required: true, options: ['notifications:dispatch', 'tasks:create', 'subtasks:create'].map(value => ({ value, label: value })), value: row?.['approved_scopes'] }, { key: 'is_active', label: 'Activo', type: 'check', value: row?.['is_active'] }], values => this.api.command('/notifications/service-principals/' + (row ? text(row, 'id') : crypto.randomUUID()), { ...values, expected_version: row ? version(row) : 0 }, 'PUT'));
  }
  async health(row: Row): Promise<void> {
    const epoch = this.epoch;
    try { const checks = await this.api.all('/notification-connectors/' + text(row, 'id') + '/health-checks'); if (epoch === this.epoch) { this.checks.set(checks); this.checksName.set('Pruebas de ' + text(row, 'name')); } }
    catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); }
  }
  rule(row?: Row): void {
    this.open(row ? 'Editar regla' : 'Crear regla', [{ key: 'name', label: 'Nombre', required: true, max: 120, value: row?.['name'] }, { key: 'department_id', label: 'Departamento', type: 'select', options: options(this.departments()), value: row?.['department_id'] }, { key: 'trigger', label: 'Evento', type: 'select', required: true, options: Object.entries(TRIGGERS).map(([value, label]) => ({ value, label })), value: row?.['trigger'] }, pick('recipient_mode', 'Destinatarios', ['assignee', 'mentioned', 'requester', 'department_leaders', 'admins', 'evaluator'], row?.['recipient_mode']), { key: 'channels', label: 'Canales', type: 'multi', required: true, options: CHANNELS, value: row?.['channels'] }, { key: 'connector_ids', label: 'Conectores explicitos', type: 'multi', options: options(this.connectors()), value: row?.['connector_ids'] }, { key: 'threshold_days', label: 'Umbral (dias)', type: 'number', min: 0, max: 365, requiredWhen: { key: 'trigger', values: ['upcoming_due', 'overdue'] }, value: row?.['threshold_days'] }, pick('day_basis', 'Base del calendario', ['natural', 'business'], row?.['day_basis']), number('max_age_hours', 'Vigencia maxima (horas)', 1, 720, row?.['max_age_hours']), number('max_attempts', 'Intentos maximos', 1, 10, row?.['max_attempts']), number('retry_base_seconds', 'Espera inicial (s)', 5, 300, row?.['retry_base_seconds']), { key: 'enabled', label: 'Habilitada', type: 'check', value: row?.['enabled'] }], values => this.api.command('/notification-rules' + (row ? '/' + text(row, 'id') : ''), rulePayload(values, row), row ? 'PATCH' : 'POST'));
  }
}