import { DatePipe } from '@angular/common';
import { Component, DestroyRef, effect, inject, signal, untracked } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Api, Page, Row, text, version } from '../core/api';
import { Configuration } from '../core/configuration';
import { Problem, problem } from '../core/problem';
import { Session } from '../core/session';
import { Editor, Field, options, reason } from '../shared/editor';
import { Feedback } from '../shared/feedback';
import { Pager, Pagination } from '../shared/pager';

export const IMPORT_FIELDS: Record<string, string[]> = {
  plan: ['title', 'start_date', 'due_date', 'horizon_type', 'custom_fields', 'tag_ids'],
  objective: ['title', 'description', 'annual_plan_id', 'department_id', 'start_date', 'due_date', 'horizon_type', 'custom_fields', 'tag_ids'],
  task: ['title', 'description', 'objective_id', 'assignee_id', 'priority_id', 'start_date', 'due_date', 'custom_fields', 'tag_ids'],
};
const FIELD_LABELS: Record<string, string> = {
  title: 'Titulo', description: 'Descripcion', start_date: 'Inicio', due_date: 'Compromiso',
  horizon_type: 'Horizonte', annual_plan_id: 'ID del plan', department_id: 'ID del departamento',
  objective_id: 'ID del objetivo', assignee_id: 'ID del responsable', priority_id: 'ID de prioridad',
  custom_fields: 'Campos personalizados (JSON)', tag_ids: 'IDs de etiquetas (JSON)',
};
export function importMapping(headers: string[], selected: Row, entity: string): Record<string, string> {
  const allowed = IMPORT_FIELDS[entity];
  if (!allowed) throw new Error('Invalid import entity');
  const mapping = Object.fromEntries(headers.flatMap((header, index) => {
    const target = selected[String(index)];
    return typeof target === 'string' && target ? [[header, target]] : [];
  }));
  if (!Object.keys(mapping).length || new Set(Object.values(mapping)).size !== Object.keys(mapping).length ||
      Object.values(mapping).some(value => !allowed.includes(value))) throw new Error('Invalid import mapping');
  return mapping;
}
export async function fileContent(file: File): Promise<string> {
  if (!file.size || file.size > 10485760 || !/\.(csv|xlsx)$/i.test(file.name)) throw new Error('Invalid import file');
  const content = new Uint8Array(await file.arrayBuffer());
  let encoded = '';
  for (let offset = 0; offset < content.length; offset += 32768) encoded += String.fromCharCode(...content.subarray(offset, offset + 32768));
  return btoa(encoded);
}
export const BULK_STYLES = `:host{display:block;min-width:0}.toolbar,.actions,.record-heading{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.toolbar,.record-heading{justify-content:space-between;padding:16px 0}.field-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr));gap:16px}.field-grid>*{min-width:0;max-width:100%}.wide{grid-column:1/-1}.section{border-top:1px solid var(--ocote-border);padding:20px 0}.meta{color:var(--ocote-text-secondary);font-size:.875rem;overflow-wrap:anywhere}h2{font-size:1.25rem}h3{font-size:1rem}mat-form-field{width:100%;min-width:0}.record-heading strong,.data-table td,.data-table th{overflow-wrap:anywhere}.status-line{display:flex;gap:20px;flex-wrap:wrap}.status-line div{min-width:0}.status-line dt{font-size:.875rem;color:var(--ocote-text-secondary)}.status-line dd{margin:4px 0;font-weight:600}.data-table button{width:40px;height:40px;flex:0 0 40px}.selected{background:var(--ocote-surface-variant)}button{max-width:100%}.file-name{overflow-wrap:anywhere;min-width:0}.mapping-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr));gap:8px 16px}.table-wrap{max-width:100%;overflow:auto}.data-table{min-width:600px}@media(max-width:480px){.status-line{gap:12px}.toolbar{align-items:flex-start}}`;

@Component({
  imports: [DatePipe, ReactiveFormsModule, MatButtonModule, MatDialogModule, MatIconModule, MatInputModule, MatSelectModule, MatTooltipModule, Feedback, Pager],
  styles: [BULK_STYLES],
  template: `<header class="page-heading"><div><p class="eyebrow">OPERACION</p><h1>Importaciones</h1></div><div class="actions"><button mat-icon-button aria-label="Nuevo archivo" matTooltip="Nuevo archivo" [disabled]="busy()" (click)="reset()"><mat-icon>upload_file</mat-icon></button><button mat-icon-button aria-label="Recargar importaciones" matTooltip="Recargar" [disabled]="busy() || !!issue()?.conflict" (click)="load()"><mat-icon>refresh</mat-icon></button></div></header>
    <ocote-feedback [issue]="issue()" />@if (notice()) { <p role="status">{{ notice() }}</p> }
    @if (issue()?.conflict) { <button mat-stroked-button (click)="discardAndReload()"><mat-icon>restart_alt</mat-icon>Descartar cambios y recargar</button> }
    @if (!available()) { <p role="status">Importaciones no disponibles.</p> } @else {
      @if (!record()) { <section><form class="field-grid" [formGroup]="form" (ngSubmit)="upload()">
        <mat-form-field><mat-label>Entidad</mat-label><mat-select formControlName="entity_type"><mat-option value="">Seleccionar entidad</mat-option>@for (entity of entities(); track entity.value) { <mat-option [value]="entity.value">{{ entity.label }}</mat-option> }</mat-select></mat-form-field>
        <div><input #source type="file" accept=".csv,.xlsx" hidden (change)="chooseFile($event)"><button mat-stroked-button type="button" (click)="source.click()" [disabled]="busy()"><mat-icon>attach_file</mat-icon>Seleccionar archivo</button><p class="file-name">{{ filename() || 'Ningun archivo seleccionado' }}</p></div>
        <mat-form-field class="wide"><mat-label>Motivo</mat-label><textarea matInput [formControl]="reason" rows="2" maxlength="1000"></textarea></mat-form-field>
        <div class="actions wide"><button mat-flat-button type="submit" [disabled]="busy() || form.invalid || reason.invalid || !filename() || !!issue()?.conflict"><mat-icon>upload</mat-icon>Analizar archivo</button></div>
      </form></section> }
      @if (record(); as job) { <section class="section"><header class="record-heading"><div><h2>{{ entityLabel(asText(job, 'entity_type')) }}</h2><p class="meta">{{ job['id'] }}</p></div><strong>{{ stateLabel(asText(job, 'state')) }}</strong></header>
        <dl class="status-line"><div><dt>Filas</dt><dd>{{ job['row_count'] }}</dd></div><div><dt>Errores</dt><dd>{{ job['error_count'] }}</dd></div><div><dt>Version</dt><dd>{{ job['version'] }}</dd></div><div><dt>Vigencia</dt><dd>{{ asText(job, 'expires_at') | date:'medium' }}</dd></div></dl>
        @if (editable()) { <form [formGroup]="mapping" (ngSubmit)="preview()"><div class="mapping-grid">@for (header of headers(); track $index; let index = $index) { <mat-form-field><mat-label>{{ header }}</mat-label><mat-select [formControl]="mapping.controls['' + index]" [disabled]="busy() || !!issue()?.conflict"><mat-option value="">Sin asignar</mat-option>@for (field of fields(); track field) { <mat-option [value]="field">{{ fieldLabel(field) }}</mat-option> }</mat-select></mat-form-field> }</div>
          <mat-form-field><mat-label>Motivo de simulacion</mat-label><textarea matInput [formControl]="reason" rows="2" maxlength="1000"></textarea></mat-form-field>
          <div class="actions"><button mat-stroked-button type="submit" [disabled]="busy() || reason.invalid || !!issue()?.conflict"><mat-icon>fact_check</mat-icon>Simular lote</button><button mat-flat-button type="button" [disabled]="busy() || job['state'] !== 'previewed' || !!issue()?.conflict" (click)="commit()"><mat-icon>done_all</mat-icon>Confirmar lote</button></div>
        </form> }
        @if (previewRows().length) { <div class="table-wrap" role="region" aria-label="Resultado de simulacion" tabindex="0"><table class="data-table"><thead><tr><th scope="col">Fila</th><th scope="col">Titulo normalizado</th><th scope="col">Periodo</th><th scope="col">Estado</th><th scope="col">Columna</th><th scope="col">Resultado</th></tr></thead><tbody>@for (row of previewRows(); track row['row']) { <tr><th scope="row">{{ row['row'] }}</th><td>{{ previewValue(row, 'title') }}</td><td>{{ previewValue(row, 'start_date') }} a {{ previewValue(row, 'due_date') }}</td><td>{{ row['valid'] ? 'Valida' : 'Rechazada' }}</td><td>{{ errorColumns(row) }}</td><td>{{ errorCodes(row) }}</td></tr> }</tbody></table></div> }
        @if (job['state'] === 'committed') { <p role="status">Lote confirmado: {{ job['row_count'] }} registros.</p> }
      </section> }
      <section class="section"><header class="toolbar"><h2>Historial de lotes</h2>@if (busy()) { <span role="status">Cargando...</span> }</header>
        <div class="table-wrap" role="region" aria-label="Historial de importaciones" tabindex="0"><table class="data-table"><thead><tr><th scope="col">Entidad</th><th scope="col">Fecha</th><th scope="col">Filas</th><th scope="col">Estado</th><th scope="col">Abrir</th></tr></thead><tbody>@for (row of rows(); track row['id']) { <tr [class.selected]="record()?.['id'] === row['id']"><th scope="row">{{ entityLabel(asText(row, 'entity_type')) }}</th><td>{{ asText(row, 'created_at') | date:'short' }}</td><td>{{ row['row_count'] }}</td><td>{{ stateLabel(asText(row, 'state')) }}</td><td><button mat-icon-button aria-label="Abrir lote" matTooltip="Abrir lote" [disabled]="busy() || !!issue()?.conflict" (click)="open(row)"><mat-icon>open_in_new</mat-icon></button></td></tr> } @empty { <tr><td colspan="5">Sin lotes disponibles.</td></tr> }</tbody></table></div>
        <ocote-pager [state]="pagination" [busy]="busy()" (navigate)="load($event)" (sizeChange)="resize($event)" />
      </section>
    }`,
})
export class ImportsPage {
  private readonly api = inject(Api); private readonly dialog = inject(MatDialog);
  readonly session = inject(Session); readonly configuration = inject(Configuration);
  readonly issue = signal<Problem | null>(null); readonly notice = signal(''); readonly busy = signal(false);
  readonly rows = signal<Row[]>([]); readonly record = signal<Row | null>(null); readonly filename = signal('');
  readonly pagination = new Pagination(); readonly asText = text;
  readonly form = new FormGroup({ entity_type: new FormControl('', { nonNullable: true, validators: [Validators.required] }) });
  readonly reason = new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(10), Validators.maxLength(1000)] });
  mapping = new FormGroup<Record<string, FormControl<string>>>({});
  private source: File | null = null; private uploadKey = ''; private epoch = 0; private actor = '';
  private opened?: { close: () => void };
  constructor() {
    inject(DestroyRef).onDestroy(() => { ++this.epoch; this.source = null; this.opened?.close(); });
    effect(() => { this.session.user(); this.configuration.value(); untracked(() => {
      const current = this.session.user();
      const actor = current ? [current.id, current.role, current.department_id].join('|') : '';
      if (actor !== this.actor || !this.available()) { this.clear(); this.rows.set([]); this.opened?.close(); }
      this.actor = actor;
      if (this.available()) void this.load();
    }); });
  }
  available(): boolean { return this.session.user()?.role !== 'colaborador' && !!this.session.user() && this.configuration.enabled('imports'); }
  entities(): { value: string; label: string }[] {
    const role = this.session.user()?.role;
    return [...(['admin', 'gerente'].includes(role ?? '') ? [{ value: 'plan', label: 'Planes' }, { value: 'objective', label: 'Objetivos' }] : []), ...(['admin', 'lider'].includes(role ?? '') ? [{ value: 'task', label: 'Tareas' }] : [])];
  }
  entityLabel(value: string): string { return ({ plan: 'Planes', objective: 'Objetivos', task: 'Tareas' } as Row)[value] as string ?? value; }
  stateLabel(value: string): string { return ({ uploaded: 'Analizado', previewed: 'Simulacion valida', rejected: 'Con errores', committed: 'Confirmado', expired: 'Vencido' } as Row)[value] as string ?? value; }
  fieldLabel(value: string): string { return FIELD_LABELS[value] ?? value; }
  headers(): string[] { return (this.record()?.['headers'] as string[] ?? []); }
  fields(): string[] { return IMPORT_FIELDS[text(this.record() ?? {}, 'entity_type')] ?? []; }
  previewRows(): Row[] { return this.record()?.['rows'] as Row[] ?? []; }
  errors(row: Row): Row[] { return row['errors'] as Row[] ?? []; }
  previewValue(row: Row, key: string): string { return text(row['preview'] as Row ?? {}, key); }
  errorColumns(row: Row): string { return this.errors(row).map(error => text(error, 'column')).join(', ') || '-'; }
  errorCodes(row: Row): string { return this.errors(row).map(error => text(error, 'code')).join(', ') || 'Validacion completa'; }
  editable(): boolean { return ['uploaded', 'previewed', 'rejected'].includes(text(this.record() ?? {}, 'state')); }
  private clear(): void { ++this.epoch; this.record.set(null); this.filename.set(''); this.source = null; this.reason.reset(); this.mapping = new FormGroup({}); }
  reset(): void { if (this.busy()) return; this.clear(); this.issue.set(null); this.notice.set(''); }
  async chooseFile(event: Event): Promise<void> {
    const element = event.target as HTMLInputElement; const file = element.files?.[0]; element.value = '';
    if (!file || this.busy()) return;
    if (!file.size || file.size > 10485760 || !/\.(csv|xlsx)$/i.test(file.name)) { this.issue.set({ message: 'Selecciona un CSV o XLSX de hasta 10 MiB.', conflict: false }); return; }
    this.source = file; this.filename.set(file.name); this.uploadKey = crypto.randomUUID(); this.issue.set(null);
  }
  private accept(job: Row): void {
    const mapping = new FormGroup<Record<string, FormControl<string>>>({});
    const selected = job['mapping'] as Row ?? {};
    for (const [index, header] of (job['headers'] as string[] ?? []).entries()) mapping.addControl(String(index), new FormControl(String(selected[header] ?? ''), { nonNullable: true }));
    this.mapping = mapping; this.record.set(job);
  }
  async upload(): Promise<void> {
    if (!this.available() || this.busy() || this.form.invalid || this.reason.invalid || !this.source || this.issue()?.conflict) return;
    const epoch = this.epoch; this.busy.set(true); this.issue.set(null);
    try { const file = this.source; const content = await fileContent(file); const result = await this.api.command('/imports', { entity_type: this.form.controls.entity_type.value, file_format: /\.xlsx$/i.test(file.name) ? 'xlsx' : 'csv', content, idempotency_key: this.uploadKey, reason: this.reason.value.trim() });
      if (epoch === this.epoch) { this.accept(result); this.source = null; this.filename.set(''); this.reason.reset(); }
    } catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); } finally { this.busy.set(false); }
  }
  async preview(): Promise<void> {
    const record = this.record(); if (!record || !this.available() || this.busy() || this.reason.invalid || this.issue()?.conflict) return;
    let mapping: Record<string, string>;
    try { mapping = importMapping(this.headers(), this.mapping.getRawValue(), text(record, 'entity_type')); }
    catch { this.issue.set({ message: 'Asigna campos distintos y permitidos a las columnas del lote.', conflict: false }); return; }
    this.busy.set(true); this.issue.set(null); const epoch = this.epoch;
    try { const value = await this.api.command('/imports/' + encodeURIComponent(text(record, 'id')) + '/dry-run', { mapping, expected_version: version(record), reason: this.reason.value.trim() }); if (epoch === this.epoch) { this.accept(value); this.reason.reset(); } }
    catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); } finally { this.busy.set(false); }
  }
  commit(): void {
    const record = this.record(); if (!record || !this.available() || this.busy() || record['state'] !== 'previewed' || this.issue()?.conflict) return;
    const idempotency = crypto.randomUUID(), epoch = this.epoch;
    this.opened = this.dialog.open(Editor, { width: '560px', maxWidth: '96vw', data: { title: 'Confirmar lote de ' + text(record, 'row_count') + ' registros', fields: [{ ...reason(), max: 1000 }], confirm: 'Confirmar lote', submit: async (values: Row) => {
      if (!this.available() || epoch !== this.epoch) throw new Error('Context changed');
      const result = await this.api.command('/imports/' + encodeURIComponent(text(record, 'id')) + '/commit', { ...values, expected_version: version(record), preview_hash: record['preview_hash'], idempotency_key: idempotency });
      if (epoch === this.epoch) { this.accept(result); this.notice.set('Lote confirmado.'); void this.load(); }
    } } });
  }
  async open(row: Row): Promise<void> {
    if (!this.available() || this.busy() || this.issue()?.conflict) return;
    this.busy.set(true); const epoch = this.epoch;
    try { const job = await this.api.get('/imports/' + encodeURIComponent(text(row, 'id'))); if (epoch === this.epoch) this.accept(job); }
    catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); } finally { this.busy.set(false); }
  }
  async discardAndReload(): Promise<void> { const record = this.record(); this.clear(); this.issue.set(null); if (record) await this.open(record); await this.load(); }
  resize(size: number): void { if (this.pagination.resize(size)) void this.load(); }
  async load(cursor = ''): Promise<void> {
    if (!this.available()) return;
    const epoch = this.epoch;
    try { const page = await this.api.get<Page>('/imports', { limit: String(this.pagination.size()), ...(cursor ? { cursor } : {}) }); if (epoch === this.epoch) { this.rows.set(page.items); this.pagination.accept(cursor, page.next_cursor); } }
    catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); }
  }
}

@Component({
  imports: [DatePipe, MatButtonModule, MatDialogModule, MatIconModule, MatTooltipModule, Feedback, Pager],
  styles: [BULK_STYLES],
  template: `<header class="page-heading"><div><p class="eyebrow">GERENCIA</p><h1>Reportes ejecutivos</h1></div><div class="actions"><button mat-icon-button aria-label="Recargar reportes" matTooltip="Recargar" (click)="load()" [disabled]="busy()"><mat-icon>refresh</mat-icon></button>@if (available()) { <button mat-flat-button (click)="create()" [disabled]="busy()"><mat-icon>add_chart</mat-icon>Generar reporte</button> }</div></header>
    <ocote-feedback [issue]="issue()" />@if (notice()) { <p role="status">{{ notice() }}</p> }
    @if (!available()) { <p role="status">Reportes ejecutivos no disponibles.</p> } @else {
      @if (busy()) { <p role="status">Cargando reportes...</p> }
      <div class="table-wrap" role="region" aria-label="Reportes ejecutivos" tabindex="0"><table class="data-table"><thead><tr><th scope="col">Reporte</th><th scope="col">Foto original</th><th scope="col">Zona</th><th scope="col">Filas</th><th scope="col">Vigencia</th><th scope="col">Descargar</th></tr></thead><tbody>
        @for (row of rows(); track row['id']) { <tr><th scope="row">{{ asText(row, 'file_format').toUpperCase() }}<p class="meta">{{ row['id'] }}</p></th><td>{{ asText(row, 'snapshot_at') | date:'medium' }}<p class="meta">{{ row['calculation_version'] }}</p></td><td>{{ row['organization_timezone'] }}</td><td>{{ row['row_count'] }}</td><td>{{ asText(row, 'expires_at') | date:'medium' }}</td><td><button mat-icon-button aria-label="Descargar reporte" matTooltip="Descargar reporte" (click)="download(row)" [disabled]="busy()"><mat-icon>download</mat-icon></button></td></tr> }
        @empty { <tr><td colspan="6">Sin reportes disponibles.</td></tr> }
      </tbody></table></div><ocote-pager [state]="pagination" [busy]="busy()" (navigate)="load($event)" (sizeChange)="resize($event)" />
    }`,
})
export class ExecutiveReportsPage {
  private readonly api = inject(Api); private readonly dialog = inject(MatDialog);
  readonly session = inject(Session); readonly configuration = inject(Configuration);
  readonly rows = signal<Row[]>([]); readonly busy = signal(false); readonly issue = signal<Problem | null>(null); readonly notice = signal('');
  readonly pagination = new Pagination(); readonly asText = text;
  private epoch = 0; private opened?: { close: () => void };
  constructor() {
    inject(DestroyRef).onDestroy(() => { ++this.epoch; this.rows.set([]); this.opened?.close(); });
    effect(() => { this.session.user(); this.configuration.value(); untracked(() => { ++this.epoch; this.rows.set([]); this.opened?.close(); this.pagination.reset(); if (this.available()) void this.load(); }); });
  }
  available(): boolean { return !!this.session.user() && this.session.has('exports:read') && this.configuration.enabled('executive_reports') && this.configuration.enabled('evaluations') && this.configuration.enabled('exports'); }
  resize(size: number): void { if (this.pagination.resize(size)) void this.load(); }
  async load(cursor = ''): Promise<void> {
    if (!this.available()) return;
    const epoch = this.epoch; this.busy.set(true); this.issue.set(null);
    try { const page = await this.api.get<Page>('/executive-reports', { limit: String(this.pagination.size()), ...(cursor ? { cursor } : {}) }); if (epoch === this.epoch) { this.rows.set(page.items); this.pagination.accept(cursor, page.next_cursor); } }
    catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); } finally { this.busy.set(false); }
  }
  async create(): Promise<void> {
    if (!this.available() || this.busy()) return;
    const epoch = this.epoch; this.busy.set(true); this.issue.set(null);
    try {
      const evaluations = await this.api.all('/evaluations', { status: 'final' });
      if (epoch !== this.epoch || !this.available()) return;
      const fields: Field[] = [
        { key: 'evaluation_id', label: 'Evaluacion final', type: 'select', required: true, options: options(evaluations.map(row => ({ ...row, label: text(row, 'period_start') + ' a ' + text(row, 'period_end') + ' · ' + text(row, 'id') })), 'label') },
        { key: 'file_format', label: 'Formato', type: 'select', required: true, options: [{ value: 'pdf', label: 'PDF' }, { value: 'xlsx', label: 'XLSX' }] },
        { ...reason(), max: 1000 },
      ];
      const key = crypto.randomUUID();
      const dialog = this.dialog.open(Editor, { width: '640px', maxWidth: '96vw', data: { title: 'Generar reporte ejecutivo', fields, confirm: 'Generar', submit: async (values: Row) => {
        if (epoch !== this.epoch || !this.available()) throw new Error('Context changed');
        return this.api.command('/executive-reports', { ...values, idempotency_key: key });
      } } }); this.opened = dialog;
      dialog.afterClosed().subscribe(result => { if (epoch === this.epoch && this.available() && result) { this.notice.set(result === 'reload' ? 'Cambios descartados; datos recargados.' : 'Reporte preparado.'); void this.load(); } });
    } catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); } finally { this.busy.set(false); }
  }
  async download(row: Row): Promise<void> {
    if (!this.available() || this.busy()) return;
    const epoch = this.epoch; this.busy.set(true); this.issue.set(null);
    try {
      const content = await this.api.reportFile(text(row, 'id'));
      if (epoch !== this.epoch || !this.available()) return;
      const format = text(row, 'file_format');
      if (!['pdf', 'xlsx'].includes(format) || !content.size || content.size > 16777216) throw new Error('Invalid report');
      const url = URL.createObjectURL(content), anchor = document.createElement('a');
      anchor.href = url; anchor.download = 'ocote-report-' + text(row, 'id') + '.' + format; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); } finally { this.busy.set(false); }
  }
}