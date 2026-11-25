import { Component, inject, OnInit, signal, DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSelectModule } from '@angular/material/select';
import { Api, Page, Row, text, version } from '../core/api';
import { Feedback } from '../shared/feedback';
import { RecordDetails } from '../shared/record-details';
import { Editor, Field, options, reason } from '../shared/editor';
import { commandMessage, problem, Problem } from '../core/problem';
import { stageProblem, transitionProblem, WorkflowEditor } from './workflow.editor';

interface Resource { title: string; api: string; columns: [string, string][]; readonly?: boolean; }
const resources: Record<string, Resource> = {
  departamentos: { title: 'Departamentos', api: '/departments', columns: [['code','Codigo'],['name','Nombre'],['is_active','Activo'],['version','Version']] },
  usuarios: { title: 'Usuarios', api: '/users', columns: [['display_name','Nombre'],['email','Correo'],['role','Rol'],['is_active','Activo'],['version','Version']] },
  etapas: { title: 'Etapas', api: '/workflow-stages', columns: [['code','Codigo'],['name','Nombre'],['kind','Clase'],['position','Orden'],['is_active','Activa']] },
  transiciones: { title: 'Transiciones', api: '/workflow-transitions', columns: [['from_stage_id','Origen'],['to_stage_id','Destino'],['allowed_roles','Roles'],['is_active','Activa']] },
  prioridades: { title: 'Prioridades', api: '/priorities', columns: [['code','Codigo'],['name','Nombre'],['position','Orden'],['is_active','Activa']] },
  horizontes: { title: 'Horizontes', api: '/horizon-types', columns: [['code','Codigo'],['name','Nombre'],['position','Orden'],['is_active','Activo']] },
  parametros: { title: 'Parametros', api: '/settings', columns: [['key','Clave'],['value','Valor'],['version','Version']] },
  auditoria: { title: 'Auditoria', api: '/audit-events', readonly: true, columns: [['created_at','Instante'],['event_type','Evento'],['entity_type','Entidad'],['outcome','Resultado']] },
  releases: { title: 'Releases', api: '/releases', readonly: true, columns: [['application_version','Aplicacion'],['target_revision','Revision'],['status','Estado'],['result_code','Resultado']] },
};
const keys = ['organization_name', 'organization_timezone', 'evidence_max_bytes', 'export_max_rows'];
const roles = ['admin', 'gerente', 'lider', 'colaborador'].map(value => ({ value, label: value }));
const code = (): Field => ({ key: 'code', label: 'Codigo', required: true, max: 40, pattern: '^[a-z][a-z0-9_]*$' });
const name = (): Field => ({ key: 'name', label: 'Nombre', required: true, max: 120 });
const active = (): Field => ({ key: 'is_active', label: 'Activo', type: 'check' });
const position = (): Field => ({ key: 'position', label: 'Posicion', type: 'number', required: true, min: 0, max: 2147483647 });

@Component({
  standalone: true, imports: [RouterLink, MatButtonModule, MatIconModule, MatTooltipModule, MatSelectModule, MatDialogModule, Feedback, RecordDetails],
  template: `<header class="page-heading"><div><p class="eyebrow">ADMINISTRACION</p><h1>{{ config()?.title ?? 'Configuracion' }}</h1></div>
    <div class="actions"><button mat-icon-button aria-label="Recargar" matTooltip="Recargar" [disabled]="loading()" (click)="load()"><mat-icon>refresh</mat-icon></button>
      @if (section() === 'configuracion') { <button mat-stroked-button (click)="workflow()"><mat-icon>account_tree</mat-icon>Editar grafo</button> }
      @if (section() === 'prioridades' || section() === 'horizontes') { <button mat-stroked-button [disabled]="loading() || !rows().length" (click)="reorder()"><mat-icon>swap_vert</mat-icon>Ordenar</button> }
      @if (config() && !config()?.readonly) { <button mat-flat-button [disabled]="section() === 'parametros' && (!settingKey || loading())" (click)="edit()"><mat-icon>add</mat-icon>Crear</button> }
    </div></header><ocote-feedback [issue]="issue()" />
    @if (notice()) { <p class="notice" role="status">{{ notice() }}</p> }
    @if (section() === 'configuracion') {
      @if (status(); as status) { <section class="detail-section"><h2>Estado operativo</h2><p class="status" [class.good]="status['complete']">{{ status['complete'] ? 'Configuracion completa' : 'Configuracion incompleta' }}</p>
        <dl class="facts"><div><dt>Parametros pendientes</dt><dd>{{ array(status['missing_settings']) || 'Ninguno' }}</dd></div>
        <div><dt>Horizontes pendientes</dt><dd>{{ array(status['missing_horizons']) || 'Ninguno' }}</dd></div>
        <div><dt>Prioridad normal activa</dt><dd>{{ status['normal_present'] ? 'Si' : 'No' }}</dd></div><div><dt>Workflow valido</dt><dd>{{ status['workflow_valid'] ? 'Si' : 'No' }}</dd></div></dl>
        @if (!status['workflow_valid']) { <p class="problem" role="status">{{ commandMessage(status['workflow_error']) || 'Completa la etapa inicial abierta, la terminal activa y los caminos de todas las etapas activas hacia la terminal.' }}</p><div class="actions"><a mat-stroked-button routerLink="/administracion/etapas"><mat-icon>account_tree</mat-icon>Etapas</a><a mat-stroked-button routerLink="/administracion/transiciones"><mat-icon>sync_alt</mat-icon>Transiciones</a></div> }
      </section> }
    } @else { @if (config(); as config) {
      @if (section() === 'parametros') { <div class="toolbar"><mat-form-field><mat-label>Parametro a crear</mat-label><mat-select [(value)]="settingKey">@for (key of availableKeys(); track key) { <mat-option [value]="key">{{ key }}</mat-option> }</mat-select></mat-form-field></div> }
      @if (loading()) { <p role="status">Cargando registros...</p> }
      @else if (!rows().length) { <section class="empty-state"><mat-icon>inbox</mat-icon><h2>Sin registros</h2><p>No hay elementos disponibles.</p></section> }
      @else { <div class="table-wrap" role="region" [attr.aria-label]="config.title" tabindex="0"><table class="data-table"><thead><tr>@for (column of config.columns; track column[0]) { <th scope="col">{{ column[1] }}</th> }<th scope="col">Acciones</th></tr></thead>
        <tbody>@for (row of rows(); track rowKey(row)) { <tr>@for (column of config.columns; track column[0]) { <td>{{ display(row, column[0]) }}</td> }
          <td><div class="actions">@if (!config.readonly) { <button mat-icon-button aria-label="Editar registro" matTooltip="Editar" (click)="edit(row)"><mat-icon>edit</mat-icon></button> }
            <button mat-icon-button aria-label="Consultar detalle" matTooltip="Consultar detalle" (click)="inspect(row)"><mat-icon>visibility</mat-icon></button>
            @if (canChangeActivity(row)) { <button mat-icon-button [attr.aria-label]="row['is_active'] ? 'Desactivar registro' : 'Activar registro'" [matTooltip]="row['is_active'] ? 'Desactivar' : 'Activar'" (click)="changeActivity(row)"><mat-icon>{{ row['is_active'] ? 'block' : 'check_circle' }}</mat-icon></button> }
            @if (section() === 'usuarios') { <button mat-icon-button aria-label="Restablecer contrasena" matTooltip="Restablecer contrasena" (click)="resetPassword(row)"><mat-icon>key</mat-icon></button> }
          </div></td></tr> }</tbody></table></div>
        <div class="pager"><button mat-button [disabled]="!cursor()" (click)="load()">Primera pagina</button><button mat-stroked-button [disabled]="!next()" (click)="load(next()!)">Siguiente</button></div>
      }
      @if (selected(); as row) { <section class="detail-section" aria-labelledby="record-detail-title"><div class="page-heading"><h2 id="record-detail-title">Detalle del registro</h2><button mat-icon-button aria-label="Cerrar detalle" matTooltip="Cerrar detalle" (click)="selected.set(null)"><mat-icon>close</mat-icon></button></div><ocote-record-details [record]="row" [summary]="true" /></section> }
    } }
    @if (section() === 'configuracion' && loading()) { <p role="status">Cargando configuracion...</p> }`,
})
export class AdminPage implements OnInit {
  private readonly api = inject(Api);
  private readonly dialog = inject(MatDialog);
  private readonly route = inject(ActivatedRoute);
  private readonly destroy = inject(DestroyRef);
  readonly section = signal('');
  readonly config = signal<Resource | null>(null);
  readonly rows = signal<Row[]>([]);
  readonly selected = signal<Row | null>(null);
  readonly status = signal<Row | null>(null);
  readonly loading = signal(false);
  readonly issue = signal<Problem | null>(null);
  readonly notice = signal('');
  readonly next = signal<string | null>(null);
  readonly cursor = signal('');
  private epoch = 0;
  settingKey = '';
  readonly array = (value: unknown) => Array.isArray(value) ? value.join(', ') : '';
  readonly commandMessage = commandMessage;
  rowKey(row: Row): string { return text(row, 'id') || text(row, 'key'); }
  canChangeActivity(row: Row): boolean {
    if (this.config()?.readonly || typeof row['is_active'] !== 'boolean') return false;
    return !(this.section() === 'prioridades' && row['code'] === 'normal') && !(this.section() === 'horizontes' && row['code'] === 'custom') && !(this.section() === 'etapas' && (row['is_initial'] || row['kind'] === 'completed'));
  }
  async inspect(row: Row): Promise<void> {
    const config = this.config(), epoch = this.epoch; if (!config) return;
    this.issue.set(null); this.selected.set(null);
    try {
      const current = config.readonly ? row : await this.api.get(config.api + '/' + encodeURIComponent(config.api === '/settings' ? text(row, 'key') : text(row, 'id')));
      if (epoch === this.epoch) this.selected.set(current);
    } catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); }
  }
  changeActivity(row: Row): void {
    const config = this.config(), section = this.section(); if (!config || !this.canChangeActivity(row)) return;
    const fields = section === 'usuarios' ? ['display_name','role','department_id'] : section === 'transiciones' ? ['allowed_roles'] : section === 'etapas' ? ['name','position','requires_reason','requires_evidence'] : section === 'prioridades' || section === 'horizontes' ? ['name','position'] : ['name'];
    const values: Row = Object.fromEntries(fields.map(key => [key, row[key]]));
    const activating = !row['is_active'];
    this.dialog.open(Editor, { width:'560px',maxWidth:'96vw',data: {
      title:(activating ? 'Activar' : 'Desactivar') + ' · ' + (text(row,'name') || text(row,'display_name') || config.title),
      message:activating ? 'El registro volvera a estar disponible si cumple las reglas vigentes.' : 'El registro dejara de estar disponible para nuevas operaciones. Sus referencias e historial se conservan; las dependencias pueden impedir el cambio.',
      confirm:activating ? 'Activar' : 'Desactivar',fields:[reason()],
      submit:(input:Row) => this.api.command(config.api + '/' + encodeURIComponent(text(row,'id')), { ...values,is_active:activating,expected_version:version(row),reason:input['reason'] },'PATCH'),
    } }).afterClosed().subscribe(result => { if (result && section === this.section()) void this.load(); });
  }
  availableKeys(): string[] { return keys.filter(key => !this.rows().some(row => row['key'] === key)); }
  ngOnInit(): void {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroy)).subscribe(params => {
      const section = params.get('section') ?? 'configuracion';
      this.section.set(section); this.config.set(resources[section] ?? null); this.rows.set([]); this.status.set(null);
      this.selected.set(null); this.notice.set(''); this.settingKey = ''; void this.load();
    });
  }
  async load(cursor = ''): Promise<void> {
    const epoch = ++this.epoch, config = this.config(); this.loading.set(true); this.issue.set(null); this.selected.set(null);
    try {
      if (this.section() === 'configuracion') {
        const status = await this.api.get('/configuration-status'); if (epoch === this.epoch) this.status.set(status);
      } else if (config) {
        const page = await this.api.get<Page>(config.api, { limit: '50', ...(cursor ? { cursor } : {}) });
        if (epoch === this.epoch) {
          this.rows.set(page.items); this.next.set(page.next_cursor ?? null); this.cursor.set(cursor);
          if (this.section() === 'parametros' && page.items.some(row => row['key'] === this.settingKey)) this.settingKey = '';
        }
      } else throw new Error('Unknown route');
    } catch (error) { if (epoch === this.epoch) { this.rows.set([]); this.status.set(null); this.issue.set(problem(error)); } }
    finally { if (epoch === this.epoch) this.loading.set(false); }
  }
  display(row: Row, key: string): string {
    const value = row[key];
    if (typeof value === 'boolean') return value ? 'Si' : 'No';
    if (Array.isArray(value)) return value.join(', ');
    if (key === 'created_at' && typeof value === 'string') return new Intl.DateTimeFormat('es-MX', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Mexico_City' }).format(new Date(value));
    return String(value ?? '—');
  }
  private async fields(row?: Row, stages: Row[] = []): Promise<Field[]> {
    const section = this.section(); let fields: Field[];
    if (section === 'parametros') {
      const key = row ? text(row, 'key') : this.settingKey;
      const numeric = key === 'evidence_max_bytes' || key === 'export_max_rows';
      fields = [{ key: 'value', label: key, type: numeric ? 'number' : 'text', required: true,
        ...(numeric ? { min: 1, max: key === 'evidence_max_bytes' ? 10485760 : 10000 } : { max: key === 'organization_timezone' ? 100 : 160 }) }];
    } else if (section === 'usuarios') {
      const departments = await this.api.all('/departments');
      fields = [...(row ? [] : [{ key: 'email', label: 'Correo', type: 'email', required: true, max: 254 } as Field,
        { key: 'password', label: 'Contrasena inicial', type: 'password', required: true, min: 12, max: 128 } as Field]),
        { key: 'display_name', label: 'Nombre', required: true, max: 120 },
        { key: 'role', label: 'Rol', type: 'select', required: true, options: roles },
        { key: 'department_id', label: 'Departamento', type: 'select', requiredWhen: { key: 'role', values: ['lider','colaborador'] }, options: options(departments.filter(department => department['is_active'] || department['id'] === row?.['department_id'])) }, active()];
    } else if (section === 'transiciones') {
      fields = [...(row ? [] : [
        { key: 'from_stage_id', label: 'Etapa origen', type: 'select', required: true, options: options(stages.filter(stage => stage['kind'] !== 'completed')) } as Field,
        { key: 'to_stage_id', label: 'Etapa destino', type: 'select', required: true, options: options(stages) } as Field,
      ]), { key: 'allowed_roles', label: 'Roles permitidos', type: 'multi', required: true, options: roles.filter(role => role.value !== 'gerente') }, active()];
    } else {
      const catalog = ['etapas', 'prioridades', 'horizontes'].includes(section);
      fields = [...(row ? [] : [section === 'horizontes' ? { ...code(), type: 'select' as const, options: ['annual','semiannual','quarterly','monthly','custom'].map(value => ({ value, label: value })) } : code()]), name(), ...(catalog ? [position()] : []), active()];
      if (section === 'etapas') fields.push(...(row ? [] : [
        { key: 'kind', label: 'Clase', type: 'select', required: true, options: ['open','blocked','completed'].map(value => ({ value, label: value })) } as Field,
        { key: 'is_initial', label: 'Etapa inicial', type: 'check' } as Field,
      ]), { key: 'requires_reason', label: 'Requiere motivo', type: 'check' }, { key: 'requires_evidence', label: 'Requiere evidencia', type: 'check' });
    }
    return [...fields.map(field => ({ ...field, value: row?.[field.key] })), reason()];
  }
  async edit(row?: Row): Promise<void> {
    const config = this.config(); if (!config || config.readonly) return;
    const section = this.section(), settingKey = row ? text(row, 'key') : this.settingKey;
    if (section === 'parametros' && !keys.includes(settingKey)) return;
    try {
      const stages = section === 'transiciones' ? await this.api.all('/workflow-stages') : [];
      const fields = await this.fields(row, stages);
      if (section !== this.section()) return;
      const ref = this.dialog.open(Editor, { width: '640px', maxWidth: '96vw', data: {
        title: (row ? 'Editar · ' : 'Crear · ') + config.title, fields,
        validate: (values: Row) => {
          const current = { ...row, ...values };
          if (section === 'prioridades' && current['code'] === 'normal' && !current['is_active']) return 'La prioridad normal debe permanecer activa.';
          if (section === 'horizontes' && current['code'] === 'custom' && !current['is_active']) return 'El horizonte custom debe permanecer activo.';
          if (section === 'etapas') return stageProblem({ ...row, ...values });
          if (section === 'transiciones') return transitionProblem({ ...row, ...values }, stages);
          if (section === 'parametros' && settingKey === 'organization_timezone') {
            try { new Intl.DateTimeFormat('es-MX', { timeZone: String(values['value'] ?? '').trim() }); }
            catch { return 'Indica una zona IANA valida.'; }
          }
          return null;
        },
        submit: (values: Row) => this.api.command(config.api + (row ? '/' + encodeURIComponent(config.api === '/settings' ? text(row, 'key') : text(row, 'id')) : ''),
          { ...values, ...(row ? { expected_version: version(row) } : config.api === '/settings' ? { key: settingKey } : {}) }, row ? 'PATCH' : 'POST'),
      } });
      ref.afterClosed().subscribe(result => { if (result && section === this.section()) { this.notice.set(result === 'reload' ? 'Datos recargados. Abre de nuevo el registro para revisar tus cambios.' : 'Cambio guardado.'); void this.load(); } });
    } catch (error) { this.issue.set(problem(error)); }
  }
  resetPassword(row: Row): void {
    this.dialog.open(Editor, { width: '560px', maxWidth: '96vw', data: {
      title: 'Restablecer contrasena · ' + text(row, 'display_name'),
      fields: [{ key: 'new_password', label: 'Nueva contrasena', type: 'password', required: true, min: 12, max: 128 }, reason()],
      submit: (values: Row) => this.api.command('/users/' + text(row, 'id') + '/reset-password', { ...values, expected_version: version(row) }),
    } }).afterClosed().subscribe(result => { if (result) void this.load(); });
  }
  async reorder(): Promise<void> {
    const config = this.config(); if (!config || !['prioridades','horizontes'].includes(this.section())) return;
    try {
      const rows = await this.api.all(config.api);
      if (!rows.length) return;
      this.dialog.open(Editor, { width:'640px',maxWidth:'96vw',data: {
        title:'Ordenar ' + config.title.toLowerCase(), fields:[...rows.map(row => ({ key:text(row,'id'),label:text(row,'name'),type:'number',required:true,min:0,max:2147483647,value:row['position'] } as Field)),reason()],
        validate:(values:Row) => new Set(rows.map(row => values[text(row,'id')])).size === rows.length ? null : 'Las posiciones deben ser distintas.',
        submit:(values:Row) => this.api.command(config.api + '/reorder', { items:rows.map(row => ({ id:row['id'],position:values[text(row,'id')],expected_version:version(row) })),reason:values['reason'] }),
      } }).afterClosed().subscribe(result => { if (result) void this.load(); });
    } catch (error) { this.issue.set(problem(error)); }
  }
  async workflow(): Promise<void> {
    if (this.section() !== 'configuracion') return;
    try {
      const [stages, transitions] = await Promise.all([this.api.all('/workflow-stages'), this.api.all('/workflow-transitions')]);
      this.dialog.open(WorkflowEditor, { width: '1000px', maxWidth: '96vw', data: { stages, transitions } })
        .afterClosed().subscribe(result => { if (result) void this.load(); });
    } catch (error) { this.issue.set(problem(error)); }
  }
}