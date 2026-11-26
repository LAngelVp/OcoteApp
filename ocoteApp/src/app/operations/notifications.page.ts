import { DatePipe } from '@angular/common';
import { Component, DestroyRef, effect, inject, signal, untracked } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { Api, Page, Row, text, version } from '../core/api';
import { Configuration } from '../core/configuration';
import { Problem, problem } from '../core/problem';
import { Session } from '../core/session';
import { Editor, Field, reason } from '../shared/editor';
import { Feedback } from '../shared/feedback';

export const CHANNELS = [
  { value: 'in_app', label: 'Bandeja' }, { value: 'email', label: 'Correo' },
  { value: 'messaging', label: 'Mensajeria corporativa' },
];
export const TRIGGERS: Record<string, string> = {
  assignment: 'Asignacion', mention: 'Mencion', upcoming_due: 'Proxima a vencer', overdue: 'Vencida',
  due_date_request: 'Solicitud de fecha', due_date_decision: 'Decision de fecha',
  impediment: 'Impedimento', evaluation_finalized: 'Evaluacion finalizada',
};

export function preferencesPayload(values: Row, record: Row | null): Row {
  return { ...values, expected_version: record ? version(record) : 0,
    quiet_start: values['quiet_start'] || null, quiet_end: values['quiet_end'] || null };
}

@Component({
  imports: [MatDialogModule, MatInputModule, MatButtonModule, MatIconModule, MatTooltipModule],
  styles: [`textarea{width:100%;min-height:120px;overflow-wrap:anywhere;resize:vertical}mat-dialog-content{min-width:0}.copy{color:var(--ocote-success)}`],
  template: `<h2 mat-dialog-title>Enlace privado de calendario</h2><mat-dialog-content><mat-label>Capacidad privada</mat-label><textarea matInput readonly aria-label="Enlace privado de calendario" [value]="data.url" autocomplete="off" spellcheck="false"></textarea>@if (copied()) { <p class="copy" role="status">Enlace copiado.</p> }@if (failed()) { <p role="alert">No se pudo acceder al portapapeles.</p> }</mat-dialog-content><mat-dialog-actions align="end"><button mat-icon-button aria-label="Copiar enlace privado" matTooltip="Copiar enlace privado" (click)="copy()"><mat-icon>content_copy</mat-icon></button><button mat-button mat-dialog-close>Cerrar</button></mat-dialog-actions>`,
})
export class FeedCapability {
  readonly data = inject<{ url: string }>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<FeedCapability>);
  private readonly session = inject(Session);
  readonly copied = signal(false); readonly failed = signal(false);
  constructor() {
    inject(DestroyRef).onDestroy(() => this.data.url = '');
    effect(() => { if (!this.session.user()) { this.data.url = ''; this.ref.close(); } });
  }
  async copy(): Promise<void> {
    this.failed.set(false);
    try { await navigator.clipboard.writeText(this.data.url); this.copied.set(true); }
    catch { this.failed.set(true); }
  }
}

@Component({
  imports: [DatePipe, RouterLink, MatButtonModule, MatIconModule, MatTabsModule, MatTooltipModule, Feedback],
  styles: [`:host{display:block;min-width:0}section{padding:24px 0;border-bottom:1px solid var(--ocote-border)}h2{font-size:1.25rem}.toolbar,.line{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.line{padding:16px 0;border-bottom:1px solid var(--ocote-border)}.line p{margin:0;min-width:0;overflow-wrap:anywhere}.meta{color:var(--ocote-text-secondary);font-size:.875rem}.actions{display:flex;gap:4px;flex-wrap:wrap}.preferences{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr));gap:16px;margin:16px 0}.preferences div{min-width:0}.preferences dt{color:var(--ocote-text-secondary)}.preferences dd{margin:4px 0;overflow-wrap:anywhere}.unread{border-left:3px solid var(--ocote-forest);padding-left:12px}.empty{padding:24px 0;color:var(--ocote-text-secondary)}`],
  template: `<header class="page-heading"><div><p class="eyebrow">PERSONAL</p><h1>Mi actividad</h1></div><button mat-icon-button aria-label="Recargar actividad" matTooltip="Recargar" (click)="load()" [disabled]="loading()"><mat-icon>refresh</mat-icon></button></header><ocote-feedback [issue]="issue()" />@if (notice()) { <p role="status">{{ notice() }}</p> }@if (loading()) { <p role="status">Cargando actividad...</p> }
    <mat-tab-group animationDuration="0ms">
    @if (configuration.enabled('notifications')) {
      <mat-tab label="Bandeja"><section><header class="toolbar"><h2>No leidas: {{ unread() }}</h2><button mat-stroked-button (click)="toggleUnread()"><mat-icon>{{ unreadOnly() ? 'filter_alt_off' : 'filter_alt' }}</mat-icon>{{ unreadOnly() ? 'Todas' : 'Solo no leidas' }}</button></header>@for (row of notifications(); track row['id']) { <div class="line" [class.unread]="!row['read_at']"><div><p><strong>{{ trigger(row) }}</strong></p><p class="meta">{{ asText(row, 'created_at') | date:'medium' }}</p></div><div class="actions"><a mat-icon-button [routerLink]="resourceLink(row)" aria-label="Abrir recurso" matTooltip="Abrir recurso"><mat-icon>open_in_new</mat-icon></a>@if (!row['read_at']) { <button mat-icon-button aria-label="Marcar como leida" matTooltip="Marcar como leida" (click)="markRead(row)"><mat-icon>mark_email_read</mat-icon></button> }</div></div> } @empty { <p class="empty">Sin notificaciones disponibles.</p> }@if (cursor()) { <button mat-stroked-button [disabled]="loading()" (click)="more()"><mat-icon>expand_more</mat-icon>Mas notificaciones</button> }</section></mat-tab>
      <mat-tab label="Preferencias"><section><header class="toolbar"><h2>Mis preferencias</h2><button mat-icon-button aria-label="Editar preferencias" matTooltip="Editar preferencias" (click)="editPreferences()"><mat-icon>tune</mat-icon></button></header>@if (preferences(); as row) { <dl class="preferences"><div><dt>Recepcion</dt><dd>{{ row['opt_in'] ? 'Aceptada' : 'Desactivada' }}</dd></div><div><dt>Canales</dt><dd>{{ channelNames(row) }}</dd></div><div><dt>Horario silencioso</dt><dd>{{ row['quiet_start'] ? row['quiet_start'] + ' a ' + row['quiet_end'] : 'Sin intervalo' }}</dd></div><div><dt>Zona horaria</dt><dd>{{ row['timezone'] }}</dd></div></dl> } @else { <p class="empty">Sin preferencias configuradas.</p> }</section></mat-tab>
    }
    @if (feedsEnabled()) { <mat-tab label="Calendarios"><section><header class="toolbar"><h2>Mis feeds</h2><button mat-stroked-button (click)="createFeed()"><mat-icon>add</mat-icon>Calendario</button></header>@for (row of feeds(); track row['id']) { <div class="line"><div><p><strong>{{ row['name'] }}</strong></p><p class="meta">{{ row['revoked_at'] ? 'Revocado' : 'Expira' }} {{ (asText(row, 'revoked_at') || asText(row, 'expires_at')) | date:'medium' }}</p></div>@if (!row['revoked_at']) { <button mat-icon-button aria-label="Revocar calendario" matTooltip="Revocar calendario" (click)="revokeFeed(row)"><mat-icon>link_off</mat-icon></button> }</div> } @empty { <p class="empty">Sin feeds creados.</p> }</section></mat-tab> }
    </mat-tab-group>@if (!configuration.enabled('notifications') && !feedsEnabled()) { <p class="empty">Actividad personal no disponible.</p> }`,
})
export class NotificationsPage {
  readonly asText = text;
  private readonly api = inject(Api); private readonly dialog = inject(MatDialog);
  readonly configuration = inject(Configuration); readonly session = inject(Session);
  readonly notifications = signal<Row[]>([]); readonly preferences = signal<Row | null>(null);
  readonly feeds = signal<Row[]>([]); readonly unread = signal(0); readonly cursor = signal<string | null>(null);
  readonly unreadOnly = signal(false); readonly loading = signal(false);
  readonly issue = signal<Problem | null>(null); readonly notice = signal('');
  private epoch = 0;
  constructor() { effect(() => { this.configuration.value(); this.session.user(); untracked(() => void this.load()); }); }
  feedsEnabled(): boolean { return this.configuration.enabled('calendar') && this.configuration.enabled('calendar_feeds'); }
  trigger(row: Row): string { return TRIGGERS[text(row['safe_projection'] as Row, 'trigger')] ?? 'Notificacion'; }
  resourceLink(row: Row): string[] { const value = row['safe_projection'] as Row; return [value['resource_type'] === 'task' ? '/tareas' : value['resource_type'] === 'objective' ? '/objetivos' : '/evaluaciones', text(value, 'resource_id')]; }
  channelNames(row: Row): string { return CHANNELS.filter(channel => (row['channels'] as string[]).includes(channel.value)).map(channel => channel.label).join(', '); }
  private query(cursor?: string): Record<string, string> { return { limit: '5', ...(cursor ? { cursor } : {}), ...(this.unreadOnly() ? { unread: 'true' } : {}) }; }
  async load(): Promise<void> {
    const epoch = ++this.epoch; this.loading.set(true); this.issue.set(null);
    this.notifications.set([]); this.preferences.set(null); this.feeds.set([]); this.unread.set(0); this.cursor.set(null);
    try {
      if (!this.session.user()) return;
      if (this.configuration.enabled('notifications')) {
        const [page, preferences] = await Promise.all([this.api.get<Page & { unread_count: number }>('/notifications', this.query()), this.api.get<Row | null>('/notification-preferences')]);
        if (epoch === this.epoch) { this.notifications.set(page.items); this.cursor.set(page.next_cursor ?? null); this.unread.set(page.unread_count); this.preferences.set(preferences); }
      }
      if (this.feedsEnabled()) { const feeds = await this.api.all('/integrations/calendar-feeds'); if (epoch === this.epoch) this.feeds.set(feeds); }
    } catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); }
    finally { if (epoch === this.epoch) this.loading.set(false); }
  }
  async more(): Promise<void> {
    const cursor = this.cursor(), epoch = this.epoch; if (!cursor || this.loading()) return;
    this.loading.set(true);
    try { const page = await this.api.get<Page & { unread_count: number }>('/notifications', this.query(cursor));
      if (epoch === this.epoch) { this.notifications.update(rows => [...rows, ...page.items]); this.cursor.set(page.next_cursor ?? null); this.unread.set(page.unread_count); }
    } catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); }
    finally { if (epoch === this.epoch) this.loading.set(false); }
  }
  toggleUnread(): void { this.unreadOnly.update(value => !value); void this.load(); }
  private open(title: string, fields: Field[], submit: (values: Row) => Promise<unknown>, validate?: (values: Row) => string | null): void {
    this.dialog.open(Editor, { width: '640px', maxWidth: '96vw', data: { title, fields: [...fields, { ...reason(), max: 1000 }], submit, validate } }).afterClosed().subscribe(result => { if (result) { this.notice.set(result === 'reload' ? 'Cambios descartados; datos recargados.' : 'Cambio guardado.'); void this.load(); } });
  }
  editPreferences(): void {
    const row = this.preferences();
    this.open('Mis preferencias', [{ key: 'opt_in', label: 'Acepto recibir notificaciones', type: 'check', value: row?.['opt_in'] }, { key: 'channels', label: 'Canales aceptados', type: 'multi', required: true, options: CHANNELS, value: row?.['channels'] }, { key: 'timezone', label: 'Zona horaria IANA', required: true, max: 64, value: row?.['timezone'] }, { key: 'quiet_start', label: 'Inicio silencioso', type: 'time', value: row?.['quiet_start'] }, { key: 'quiet_end', label: 'Fin silencioso', type: 'time', value: row?.['quiet_end'] }], values => this.api.command('/notification-preferences', preferencesPayload(values, row), 'PATCH'), values => (!!values['quiet_start'] !== !!values['quiet_end'] || values['quiet_start'] && values['quiet_start'] === values['quiet_end']) ? 'El intervalo silencioso requiere dos horas distintas.' : null);
  }
  markRead(row: Row): void { this.open('Marcar notificacion como leida', [], values => this.api.command('/notifications/' + text(row, 'id') + '/read', { ...values, expected_version: version(row) })); }
  createFeed(): void {
    this.open('Crear calendario privado', [{ key: 'name', label: 'Nombre', required: true, max: 120 }, { key: 'expires_at', label: 'Expiracion (UTC)', type: 'datetime-local', required: true }], async values => {
      const response = await this.api.command('/integrations/calendar-feeds', { ...values, expires_at: new Date(String(values['expires_at']) + 'Z').toISOString(), expected_version: 0 });
      this.dialog.open(FeedCapability, { width: '640px', maxWidth: '96vw', data: { url: location.origin + '/api/v1/calendar-feeds/' + encodeURIComponent(text(response, 'id')) + '/content?capability=' + encodeURIComponent(text(response, 'capability')) } });
    }, values => { const raw = String(values['expires_at'] ?? ''), value = new Date(raw + 'Z'); return Number.isFinite(value.getTime()) && value.toISOString().slice(0, 16) === raw ? null : 'Selecciona una fecha y hora UTC valida.'; });
  }
  revokeFeed(row: Row): void { this.open('Revocar calendario privado', [], values => this.api.command('/integrations/calendar-feeds/' + text(row, 'id') + '/revoke', { ...values, expected_version: version(row) })); }
}