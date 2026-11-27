import { DatePipe } from '@angular/common';
import { Component, DestroyRef, effect, inject, signal, untracked } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Api, Page, Row, text, version } from '../core/api';
import { Configuration } from '../core/configuration';
import { Problem, problem } from '../core/problem';
import { Session } from '../core/session';
import { BULK_STYLES } from '../operations/bulk.page';
import { Editor, Field, options, reason } from '../shared/editor';
import { Feedback } from '../shared/feedback';
import { Pager, Pagination } from '../shared/pager';

export const RETENTION_CATEGORIES = ['evidence', 'audit', 'task_history', 'evaluations', 'releases', 'import_staging', 'reports', 'backups'];
const categoryLabels: Record<string, string> = { evidence: 'Evidencias', audit: 'Auditoria', task_history: 'Historia de tareas', evaluations: 'Evaluaciones', releases: 'Releases', import_staging: 'Staging de importaciones', reports: 'Reportes temporales', backups: 'Respaldos' };
export function retentionPayload(values: Row, record?: Row): Row {
  return { ...Object.fromEntries(['category', 'minimum_days', 'legal_hold', 'responsible_user_id', 'approval_ref', 'current_password', 'reason'].map(key => [key, values[key]])), expected_version: record ? version(record) : 0 };
}

@Component({
  imports: [DatePipe, MatButtonModule, MatDialogModule, MatIconModule, MatTabsModule, MatTooltipModule, Feedback, Pager],
  styles: [BULK_STYLES + '.health-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,200px),1fr));gap:16px;padding:20px 0}.health-grid div{border-bottom:1px solid var(--ocote-border);padding:12px 0;min-width:0}.health-grid dt{font-size:.875rem;color:var(--ocote-text-secondary)}.health-grid dd{margin:8px 0;font-weight:600;overflow-wrap:anywhere}.entry{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;border-bottom:1px solid var(--ocote-border);padding:16px 0}.entry>div{min-width:0;overflow-wrap:anywhere}'],
  template: `<header class="page-heading"><div><p class="eyebrow">ADMINISTRACION</p><h1>Operaciones avanzadas</h1></div><button mat-icon-button aria-label="Recargar operaciones" matTooltip="Recargar" (click)="load()" [disabled]="busy()"><mat-icon>refresh</mat-icon></button></header>
    <ocote-feedback [issue]="issue()" />@if (notice()) { <p role="status">{{ notice() }}</p> }
    @if (!available()) { <p role="status">Operaciones avanzadas no disponibles.</p> } @else {
      <mat-tab-group animationDuration="0ms" (selectedIndexChange)="choose($event)">
        <mat-tab label="Salud">@if (health(); as status) { <dl class="health-grid">
          <div><dt>Base de datos</dt><dd>{{ nested(status, 'database')['status'] === 'ready' ? 'Disponible' : 'No disponible' }}</dd><span class="meta">{{ nested(status, 'database')['revision'] }}</span></div>
          <div><dt>Boveda</dt><dd>{{ status['vault_available'] ? 'Disponible' : 'No disponible' }}</dd></div>
          <div><dt>Almacenamiento y antivirus</dt><dd>{{ status['evidence_configuration_verified'] ? 'Verificados' : 'Sin verificar' }}</dd></div>
          <div><dt>Agente de operaciones</dt><dd>{{ nested(status, 'agent')['is_active'] ? 'Activo' : 'Inactivo' }}</dd></div>
        </dl>@if (status['last_verified_backup']; as last) { <section class="section"><h2>Ultimo respaldo verificado</h2><p>{{ backupDate(last) }}</p></section> } } @else if (busy()) { <p role="status">Consultando salud...</p> }</mat-tab>
        <mat-tab label="Respaldos"><section class="section"><header class="toolbar"><h2>Respaldos verificados</h2><button mat-flat-button (click)="backup()" [disabled]="busy() || !agent()['is_active']"><mat-icon>backup</mat-icon>Solicitar respaldo</button></header>
          <div class="table-wrap" role="region" aria-label="Respaldos verificados" tabindex="0"><table class="data-table"><thead><tr><th scope="col">Fecha</th><th scope="col">Revision</th><th scope="col">Tamano</th><th scope="col">Restore</th><th scope="col">Verificar</th></tr></thead><tbody>@for (row of backups(); track row['id']) { <tr><th scope="row">{{ asText(row, 'created_at') | date:'medium' }}</th><td>{{ row['source_revision'] }}</td><td>{{ row['size_bytes'] }} bytes</td><td>{{ row['restore_verified'] ? 'Verificado' : 'Pendiente' }}</td><td><button mat-icon-button aria-label="Solicitar restore aislado" matTooltip="Verificar restore aislado" [disabled]="busy() || !agent()['is_active']" (click)="backup(row)"><mat-icon>verified_user</mat-icon></button></td></tr> } @empty { <tr><td colspan="5">Sin respaldos verificados.</td></tr> }</tbody></table></div>
          <ocote-pager [state]="backupPagination" [busy]="busy()" (navigate)="loadBackups($event)" (sizeChange)="resize('backups', $event)" />
          <h2>Solicitudes</h2>@for (job of jobs(); track job['id']) { <div class="entry"><div><strong>{{ job['kind'] === 'backup' ? 'Respaldo' : 'Verificacion aislada' }}</strong><p class="meta">{{ job['id'] }}</p></div><div>{{ stateLabel(asText(job, 'state')) }}<p class="meta">{{ asText(job, 'updated_at') | date:'medium' }}</p></div></div> } @empty { <p>Sin solicitudes disponibles.</p> }
          <ocote-pager [state]="jobPagination" [busy]="busy()" (navigate)="loadJobs($event)" (sizeChange)="resize('jobs', $event)" />
        </section></mat-tab>
        <mat-tab label="Retencion"><section class="section"><header class="toolbar"><h2>Politicas de conservacion</h2><button mat-stroked-button (click)="retention()" [disabled]="busy()"><mat-icon>add</mat-icon>Politica</button></header>
          @for (row of policies(); track row['id']) { <div class="entry"><div><strong>{{ category(asText(row, 'category')) }}</strong><p>{{ row['minimum_days'] }} dias · {{ row['legal_hold'] ? 'Retencion legal' : 'Sin retencion legal adicional' }}</p><p class="meta">{{ row['approval_ref'] }}</p></div><button mat-icon-button aria-label="Editar politica de retencion" matTooltip="Editar politica" [disabled]="busy()" (click)="retention(row)"><mat-icon>edit</mat-icon></button></div> } @empty { <p>Sin politicas configuradas.</p> }
          <ocote-pager [state]="policyPagination" [busy]="busy()" (navigate)="loadPolicies($event)" (sizeChange)="resize('policies', $event)" />
        </section></mat-tab>
        <mat-tab label="Agente"><section class="section"><header class="toolbar"><h2>Agente local</h2><button mat-stroked-button (click)="configureAgent()" [disabled]="busy()"><mat-icon>settings</mat-icon>{{ agent()['configured'] ? 'Editar agente' : 'Registrar agente' }}</button></header>
          <dl class="status-line"><div><dt>Configuracion</dt><dd>{{ agent()['configured'] ? 'Registrada' : 'Pendiente' }}</dd></div><div><dt>Estado</dt><dd>{{ agent()['is_active'] ? 'Activo' : 'Inactivo' }}</dd></div><div><dt>Revision</dt><dd>{{ agent()['config_revision'] || '-' }}</dd></div><div><dt>Autenticacion</dt><dd>{{ agent()['authentication_configured'] ? 'Configurada' : 'Pendiente' }}</dd></div></dl>
          @if (agent()['configured']) { <p class="meta">{{ capabilities() }}</p><div class="actions"><button mat-stroked-button (click)="agentAction(false)" [disabled]="busy()"><mat-icon>science</mat-icon>Probar agente</button>@if (agent()['is_active']) { <button mat-stroked-button (click)="deactivateAgent()" [disabled]="busy()"><mat-icon>pause</mat-icon>Desactivar agente</button> } @else { <button mat-flat-button (click)="agentAction(true)" [disabled]="busy() || !agent()['tested_at']"><mat-icon>play_arrow</mat-icon>Activar agente</button> }</div> }
        </section></mat-tab>
      </mat-tab-group>
    }`,
})
export class AdvancedOperationsPage {
  private readonly api = inject(Api); private readonly dialog = inject(MatDialog);
  readonly session = inject(Session); readonly configuration = inject(Configuration);
  readonly health = signal<Row | null>(null); readonly agent = signal<Row>({});
  readonly backups = signal<Row[]>([]); readonly jobs = signal<Row[]>([]); readonly policies = signal<Row[]>([]);
  readonly busy = signal(false); readonly issue = signal<Problem | null>(null); readonly notice = signal('');
  readonly backupPagination = new Pagination(); readonly jobPagination = new Pagination(); readonly policyPagination = new Pagination();
  readonly asText = text; private epoch = 0; private selected = 0; private opened?: { close: () => void };
  constructor() {
    inject(DestroyRef).onDestroy(() => { ++this.epoch; this.opened?.close(); });
    effect(() => { this.session.user(); this.configuration.value(); untracked(() => { ++this.epoch; this.opened?.close(); this.health.set(null); this.agent.set({}); this.backups.set([]); this.jobs.set([]); this.policies.set([]); if (this.available()) void this.load(); }); });
  }
  available(): boolean { return this.session.user()?.role === 'admin' && this.configuration.enabled('advanced_operations'); }
  nested(row: Row, key: string): Row { return row[key] as Row ?? {}; }
  backupDate(value: unknown): string { return text(value as Row, 'created_at'); }
  category(value: string): string { return categoryLabels[value] ?? value; }
  stateLabel(value: string): string { return ({ running: 'Pendiente', succeeded: 'Completada', failed: 'Fallida', paused: 'Pausada' } as Record<string, string>)[value] ?? value; }
  capabilities(): string { return (this.agent()['capabilities'] as string[] ?? []).map(value => value === 'backup' ? 'Respaldo' : 'Restore aislado').join(' · '); }
  choose(index: number): void { this.selected = index; void this.load(); }
  resize(kind: 'backups' | 'jobs' | 'policies', size: number): void { const pager = kind === 'backups' ? this.backupPagination : kind === 'jobs' ? this.jobPagination : this.policyPagination; if (pager.resize(size)) void (kind === 'backups' ? this.loadBackups() : kind === 'jobs' ? this.loadJobs() : this.loadPolicies()); }
  async load(): Promise<void> {
    if (!this.available()) return;
    const epoch = this.epoch; this.busy.set(true); this.issue.set(null);
    try { const health = await this.api.get('/admin/operations/health'); if (epoch !== this.epoch) return; this.health.set(health); this.agent.set(health['agent'] as Row ?? {}); if (this.selected === 1) await Promise.all([this.loadBackups(), this.loadJobs()]); if (this.selected === 2) await this.loadPolicies(); }
    catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); } finally { this.busy.set(false); }
  }
  private async listing(path: string, pager: Pagination, destination: (rows: Row[]) => void, cursor: string): Promise<void> {
    if (!this.available()) return;
    const epoch = this.epoch;
    try { const page = await this.api.get<Page>('/admin/operations/' + path, { limit: String(pager.size()), ...(cursor ? { cursor } : {}) }); if (epoch === this.epoch) { destination(page.items); pager.accept(cursor, page.next_cursor); } }
    catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); }
  }
  loadBackups(cursor = ''): Promise<void> { return this.listing('backups', this.backupPagination, rows => this.backups.set(rows), cursor); }
  loadJobs(cursor = ''): Promise<void> { return this.listing('jobs', this.jobPagination, rows => this.jobs.set(rows), cursor); }
  loadPolicies(cursor = ''): Promise<void> { return this.listing('retention-policies', this.policyPagination, rows => this.policies.set(rows), cursor); }
  private editor(title: string, fields: Field[], submit: (values: Row) => Promise<Row>): void {
    if (!this.available()) return;
    const epoch = this.epoch;
    const dialog = this.dialog.open(Editor, { width: '680px', maxWidth: '96vw', data: { title, fields: [...fields, { key: 'current_password', label: 'Contrasena local actual', type: 'password', required: true, min: 1, max: 128 }, { ...reason(), max: 1000 }], submit: async (values: Row) => { if (!this.available() || epoch !== this.epoch) throw new Error('Context changed'); return submit(values); } } });
    this.opened = dialog;
    dialog.afterClosed().subscribe(result => { if (epoch === this.epoch && this.available() && result) { this.notice.set(result === 'reload' ? 'Cambios descartados; datos recargados.' : 'Operacion registrada.'); void this.load(); } });
  }
  backup(record?: Row): void {
    if (!this.available() || !this.agent()['is_active']) return;
    const key = crypto.randomUUID(); const agent = this.agent();
    this.editor(record ? 'Solicitar restore aislado' : 'Solicitar respaldo', [], values => this.api.command('/admin/operations/backups' + (record ? '/' + encodeURIComponent(text(record, 'id')) + '/verify' : ''), { ...values, expected_version: version(record ?? agent), idempotency_key: key }));
  }
  async retention(record?: Row): Promise<void> {
    if (!this.available() || this.busy()) return;
    this.busy.set(true); const epoch = this.epoch;
    try { const users = await this.api.all('/users'); if (epoch !== this.epoch) return;
      const fields: Field[] = [
        { key: 'category', label: 'Categoria', type: 'select', required: true, options: (record ? [text(record, 'category')] : RETENTION_CATEGORIES).map(value => ({ value, label: this.category(value) })), value: record?.['category'] },
        { key: 'minimum_days', label: 'Conservacion minima (dias)', type: 'number', required: true, min: 1, max: 36500, value: record?.['minimum_days'] },
        { key: 'legal_hold', label: 'Retencion legal', type: 'check', value: record?.['legal_hold'] },
        { key: 'responsible_user_id', label: 'Responsable', type: 'select', required: true, options: options(users, 'display_name'), value: record?.['responsible_user_id'] },
        { key: 'approval_ref', label: 'Referencia de aprobacion', required: true, min: 10, max: 200, value: record?.['approval_ref'] },
      ];
      this.editor(record ? 'Editar politica de retencion' : 'Crear politica de retencion', fields, values => this.api.command('/admin/operations/retention-policies' + (record ? '/' + encodeURIComponent(text(record, 'id')) : ''), retentionPayload(values, record), record ? 'PATCH' : 'POST'));
    } catch (error) { this.issue.set(problem(error)); } finally { this.busy.set(false); }
  }
  async configureAgent(): Promise<void> {
    if (!this.available() || this.busy()) return;
    this.busy.set(true); const epoch = this.epoch;
    try { const principals = await this.api.all('/admin/operations/principals'); if (epoch !== this.epoch) return; const agent = this.agent();
      this.editor('Registrar agente local', [
        { key: 'service_principal_id', label: 'Actor tecnico aprobado', type: 'select', required: true, options: options(principals), value: agent['service_principal_id'] },
        { key: 'capabilities', label: 'Capacidades aprobadas', type: 'multi', required: true, options: [{ value: 'backup', label: 'Respaldo' }, { value: 'restore_verify', label: 'Verificacion aislada' }], value: agent['capabilities'] },
        { key: 'destination_ref', label: 'Referencia UUID del destino aprobado', required: true, value: agent['destination_ref'] },
        { key: 'authentication_secret', label: 'Secreto de autenticacion del agente', type: 'password', required: true, min: 32, max: 256 },
      ], values => this.api.command('/admin/operations/agent', { ...values, expected_version: Number(agent['version'] ?? 0) }));
    } catch (error) { this.issue.set(problem(error)); } finally { this.busy.set(false); }
  }
  agentAction(activate: boolean): void {
    if (!this.available()) return;
    const agent = this.agent();
    this.editor(activate ? 'Activar agente' : 'Probar agente', [], values => this.api.command('/admin/operations/agent/' + (activate ? 'activate' : 'tests'), { ...values, expected_version: version(agent) }));
  }
  deactivateAgent(): void {
    if (!this.available() || !this.agent()['is_active']) return;
    const agent = this.agent();
    this.editor('Desactivar agente', [], values => this.api.command('/admin/operations/agent/deactivate', { ...values, expected_version: version(agent) }));
  }
}