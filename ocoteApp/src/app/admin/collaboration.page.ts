import { Component, effect, inject, signal, untracked } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { firstValueFrom } from 'rxjs';
import { Api, Row, text, version } from '../core/api';
import { Configuration } from '../core/configuration';
import { Problem, problem } from '../core/problem';
import { Session } from '../core/session';
import { Editor, Field, options, reason } from '../shared/editor';
import { Feedback } from '../shared/feedback';
import { RecordDetails } from '../shared/record-details';
import { creationMetadata, metadataPayload } from '../operations/collaboration';

const pick = (key: string, label: string, values: string[], value?: unknown): Field => ({ key, label, type: 'select', required: true, options: values.map(value => ({ value, label: value })), value });
const number = (key: string, label: string, min: number, max: number, value?: unknown): Field => ({ key, label, type: 'number', required: true, min, max, value });

@Component({
  imports: [MatButtonModule, MatIconModule, MatTabsModule, MatTooltipModule, Feedback, RecordDetails],
  styles: [`:host{display:block;min-width:0}section{padding:24px 0;border-bottom:1px solid var(--ocote-border)}h2{font-size:1.25rem}.toolbar,.line{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}.line{padding:12px 0;border-bottom:1px solid var(--ocote-border)}.line p{margin:0;overflow-wrap:anywhere;min-width:0}.actions{display:flex;gap:4px;flex-wrap:wrap}details{max-width:100%;margin:12px 0}.empty{padding:24px 0;color:var(--ocote-text-secondary)}`],
  template: `<header class="page-heading"><div><p class="eyebrow">{{ admin() ? 'ADMINISTRACION' : 'PLANIFICACION' }}</p><h1>Colaboracion y plantillas</h1></div><button mat-icon-button aria-label="Recargar colaboracion" matTooltip="Recargar" (click)="load()" [disabled]="loading()"><mat-icon>refresh</mat-icon></button></header><ocote-feedback [issue]="issue()" />@if (notice()) { <p role="status">{{ notice() }}</p> }@if (loading()) { <p role="status">Cargando configuracion...</p> }
    <mat-tab-group animationDuration="0ms">
    @if (admin() && configuration.enabled('custom_fields')) { <mat-tab label="Campos"><section><header class="toolbar"><h2>Definiciones</h2><button mat-stroked-button (click)="field()"><mat-icon>add</mat-icon>Campo</button></header>@for (row of fields(); track row['id']) { <div class="line"><p><strong>{{ row['label'] }}</strong> · {{ row['key'] }} · {{ row['data_type'] }} · {{ row['entity_type'] }} · {{ row['active'] ? 'Activo' : 'Inactivo' }}</p><div class="actions"><button mat-icon-button aria-label="Editar campo" matTooltip="Editar campo" (click)="field(row)"><mat-icon>edit</mat-icon></button>@if (selection(row)) { <button mat-icon-button aria-label="Agregar opcion" matTooltip="Agregar opcion" (click)="option(row)"><mat-icon>playlist_add</mat-icon></button> }</div></div>@for (option of choices(row); track option['id']) { <div class="line"><p>{{ option['code'] }} · {{ option['label'] }} · {{ option['is_active'] ? 'Activa' : 'Archivada' }}</p><button mat-icon-button aria-label="Editar opcion" matTooltip="Editar opcion" (click)="editOption(row,option)"><mat-icon>edit</mat-icon></button></div> } } @empty { <p class="empty">Sin campos definidos.</p> }</section></mat-tab> }
    @if (admin() && configuration.enabled('tags')) { <mat-tab label="Etiquetas"><section><header class="toolbar"><h2>Etiquetas</h2><button mat-stroked-button (click)="tag()"><mat-icon>add</mat-icon>Etiqueta</button></header>@for (row of tags(); track row['id']) { <div class="line"><p>{{ row['label'] }} · {{ row['color_code'] }} · {{ row['is_active'] ? 'Activa' : 'Archivada' }}</p><button mat-icon-button aria-label="Editar etiqueta" matTooltip="Editar" (click)="tag(row)"><mat-icon>edit</mat-icon></button></div> } @empty { <p class="empty">Sin etiquetas.</p> }</section></mat-tab> }
    @if (configuration.enabled('templates')) { <mat-tab label="Plantillas"><section><header class="toolbar"><h2>Plantillas versionadas</h2><button mat-stroked-button (click)="template()"><mat-icon>add</mat-icon>Plantilla</button></header>@for (row of templates(); track row['id']) { <div class="line"><p><strong>{{ row['name'] }}</strong> · {{ row['entity_type'] }} · v{{ row['current_version'] }} · {{ row['is_active'] ? 'Activa' : 'Inactiva' }}</p><div class="actions"><button mat-icon-button aria-label="Editar plantilla" matTooltip="Editar" (click)="template(row)"><mat-icon>edit</mat-icon></button><button mat-icon-button aria-label="Agregar elemento a plantilla" matTooltip="Estructura" (click)="child(row)"><mat-icon>account_tree</mat-icon></button><button mat-icon-button aria-label="Valores de plantilla" matTooltip="Campos y etiquetas" (click)="templateMetadata(row)"><mat-icon>label</mat-icon></button><button mat-icon-button aria-label="Usar plantilla" matTooltip="Vista previa y crear" [disabled]="!row['is_active']" (click)="instantiate(row)"><mat-icon>content_copy</mat-icon></button></div></div><details><summary>Contenido de version {{ row['current_version'] }}</summary><ocote-record-details [record]="payload(row)" /></details> } @empty { <p class="empty">Sin plantillas.</p> }</section></mat-tab> }
    @if (configuration.enabled('recurrence') && session.user()?.role !== 'gerente') { <mat-tab label="Recurrencia"><section><header class="toolbar"><h2>Programaciones</h2><button mat-stroked-button (click)="schedule()"><mat-icon>add</mat-icon>Programacion</button></header>@for (row of schedules(); track row['id']) { <div class="line"><p>{{ row['frequency'] }} · {{ row['start_date'] }} · {{ row['enabled'] ? 'Habilitada' : 'Deshabilitada' }} · {{ row['next_due_at'] ?? 'Sin siguiente fecha' }}</p><div class="actions"><button mat-icon-button aria-label="Editar programacion" matTooltip="Editar" (click)="schedule(row)"><mat-icon>edit</mat-icon></button><button mat-icon-button aria-label="Ejecutar programacion" matTooltip="Ejecutar hasta fecha" [disabled]="!row['enabled']" (click)="run(row)"><mat-icon>play_arrow</mat-icon></button></div></div> } @empty { <p class="empty">Sin programaciones.</p> }</section>
      @if (admin()) { <section><header class="toolbar"><h2>Actores tecnicos</h2><button mat-stroked-button (click)="principal()"><mat-icon>add</mat-icon>Actor tecnico</button></header>@for (row of principals(); track row['id']) { <div class="line"><p>{{ row['name'] }} · {{ row['is_active'] ? 'Activo' : 'Revocado' }}</p><button mat-icon-button aria-label="Editar actor tecnico" matTooltip="Permisos y revocacion" (click)="principal(row)"><mat-icon>manage_accounts</mat-icon></button></div> } @empty { <p class="empty">Sin actores tecnicos.</p> }</section> }</mat-tab> }
    </mat-tab-group>`,
})
export class CollaborationPage {
  private readonly api = inject(Api);
  private readonly dialog = inject(MatDialog);
  readonly configuration = inject(Configuration);
  readonly session = inject(Session);
  readonly fields = signal<Row[]>([]); readonly tags = signal<Row[]>([]);
  readonly templates = signal<Row[]>([]); readonly schedules = signal<Row[]>([]);
  readonly principals = signal<Row[]>([]); readonly departments = signal<Row[]>([]);
  readonly loading = signal(false); readonly issue = signal<Problem | null>(null); readonly notice = signal('');
  private epoch = 0;
  constructor() { effect(() => { this.configuration.value(); untracked(() => void this.load()); }); }
  admin(): boolean { return this.session.user()?.role === 'admin'; }
  selection(row: Row): boolean { return ['select', 'multi_select'].includes(text(row, 'data_type')); }
  choices(row: Row): Row[] { return row['options'] as Row[] ?? []; }
  payload(row: Row): Row { return (row['template_version'] as Row)?.['payload'] as Row ?? {}; }
  async load(): Promise<void> {
    const epoch = ++this.epoch; this.loading.set(true); this.issue.set(null);
    try { const jobs: Promise<void>[] = [];
      for (const [module, path, target] of [['custom_fields', 'custom-fields', this.fields], ['tags', 'tags', this.tags], ['templates', 'templates', this.templates], ['recurrence', 'recurrence-schedules', this.schedules], ['recurrence', 'service-principals', this.principals]] as const) {
        if (this.configuration.enabled(module) && (this.admin() || module === 'templates' || module === 'recurrence' && this.session.user()?.role === 'lider')) jobs.push(this.api.all('/collaboration/' + path).then(rows => { if (epoch === this.epoch) target.set(rows); }));
      }
      jobs.push(this.api.all('/catalogs/departments').then(rows => { if (epoch === this.epoch) this.departments.set(rows); }));
      await Promise.all(jobs);
    } catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); } finally { if (epoch === this.epoch) this.loading.set(false); }
  }
  private open(title: string, fields: Field[], submit: (values: Row) => Promise<unknown>): void {
    this.dialog.open(Editor, { width: '720px', maxWidth: '96vw', data: { title, fields: [...fields, reason()], submit } }).afterClosed().subscribe(result => { if (result) { this.notice.set(result === 'reload' ? 'Cambios descartados; datos recargados.' : 'Cambio guardado.'); void this.load(); } });
  }
  private scope(row?: Row): Field[] { return [pick('scope_kind', 'Alcance', this.admin() ? ['organization', 'department'] : ['department'], row?.['scope_kind']), { key: 'department_id', label: 'Departamento', type: 'select', requiredWhen: { key: 'scope_kind', values: ['department'] }, options: options(this.departments()), value: row?.['department_id'] }]; }
  private scoped(values: Row): Row { return { ...values, department_id: values['scope_kind'] === 'organization' ? null : values['department_id'] }; }
  private fieldBody(row: Row, values: Row): Row {
    const { options: _options, id: _id, created_at: _created, updated_at: _updated, version: _version, impacted_count: _impacted, ...body } = row;
    return { ...body, ...values, options: this.choices(row).map(option => this.optionBody(option)), expected_version: version(row) };
  }
  private optionBody(option: Row): Row { return { id: option['id'] ?? null, expected_version: option['version'] ?? 0, code: option['code'], label: option['label'], position: option['position'], is_active: option['is_active'] }; }
  private async saveField(identity: string, body: Row): Promise<Row> {
    const preflight = await this.api.command('/collaboration/custom-fields/' + identity + '/preflight', body);
    const count = Number(preflight['impacted_count']);
    if (count > 0) {
      const accepted = await firstValueFrom(this.dialog.open(Editor, { width: '560px', maxWidth: '96vw', data: { title: count + ' recursos abiertos sin valor', fields: [], confirm: 'Confirmar requisito', submit: async () => undefined } }).afterClosed());
      if (accepted !== true) throw new Error('Preflight no confirmado');
    }
    return this.api.command('/collaboration/custom-fields/' + identity, { ...body, expected_impacted_count: count }, 'PUT');
  }
  async field(row?: Row): Promise<void> {
    try { const workflow = await this.api.get<{ stages: Row[] }>('/catalogs/workflow');
      this.open(row ? 'Editar campo' : 'Definir campo', [{ key: 'key', label: 'Clave', required: true, max: 64, pattern: '^[a-z][a-z0-9_]*$', value: row?.['key'] }, { key: 'label', label: 'Etiqueta', required: true, max: 120, value: row?.['label'] }, pick('entity_type', 'Recurso', ['plan', 'objective', 'task'], row?.['entity_type']), pick('data_type', 'Tipo', ['text', 'number', 'date', 'boolean', 'select', 'multi_select', 'url'], row?.['data_type']), ...this.scope(row),
        { key: 'required_on_create', label: 'Requerido al crear', type: 'check', value: row?.['required_on_create'] }, { key: 'required_stage_ids', label: 'Requerido en etapas de tarea', type: 'multi', options: options(workflow.stages), value: row?.['required_stage_ids'] }, { key: 'active', label: 'Activo', type: 'check', value: row?.['active'] },
        { key: 'min_length', label: 'Longitud minima de texto', type: 'number', min: 0, max: 2000, value: (row?.['constraints'] as Row)?.['min_length'] }, { key: 'max_length', label: 'Longitud maxima de texto', type: 'number', min: 0, max: 2000, value: (row?.['constraints'] as Row)?.['max_length'] },
        { key: 'min', label: 'Minimo numerico', type: 'decimal', value: (row?.['constraints'] as Row)?.['min'] }, { key: 'max', label: 'Maximo numerico', type: 'decimal', value: (row?.['constraints'] as Row)?.['max'] }], values => {
          const { min_length, max_length, min, max, ...rest } = this.scoped(values);
          const constraints = Object.fromEntries(Object.entries({ min_length, max_length, min, max }).filter(([, value]) => value != null && value !== ''));
          return this.saveField(row ? text(row, 'id') : crypto.randomUUID(), { ...rest, constraints, options: row ? this.choices(row).map(option => this.optionBody(option)) : [], expected_version: row ? version(row) : 0 });
        });
    } catch (error) { this.issue.set(problem(error)); }
  }
  option(row: Row): void { this.editOption(row); }
  editOption(row: Row, option?: Row): void {
    this.open(option ? 'Editar opcion' : 'Agregar opcion', [{ key: 'code', label: 'Codigo estable', required: true, max: 64, pattern: '^[a-z][a-z0-9_]*$', value: option?.['code'] }, { key: 'label', label: 'Etiqueta', required: true, max: 120, value: option?.['label'] }, number('position', 'Posicion', 0, 10000, option?.['position']), { key: 'is_active', label: 'Activa', type: 'check', value: option?.['is_active'] }], values => this.saveField(text(row, 'id'), { ...this.fieldBody(row, { reason: values['reason'] }), options: [...this.choices(row).filter(entry => entry['id'] !== option?.['id']).map(entry => this.optionBody(entry)), { ...values, reason: undefined, id: option?.['id'] ?? null, expected_version: option ? version(option) : 0 }] }));
  }
  tag(row?: Row): void { this.open(row ? 'Editar etiqueta' : 'Crear etiqueta', [{ key: 'label', label: 'Nombre', required: true, max: 60, value: row?.['label'] }, ...this.scope(row), pick('color_code', 'Color', ['forest', 'rust', 'ink', 'danger'], row?.['color_code']), { key: 'is_active', label: 'Activa', type: 'check', value: row?.['is_active'] }], values => this.api.command('/collaboration/tags/' + (row ? text(row, 'id') : crypto.randomUUID()), { ...this.scoped(values), expected_version: row ? version(row) : 0 }, 'PUT')); }
  async template(row?: Row): Promise<void> {
    try { const horizons = await this.api.all('/catalogs/horizons'), priorities = await this.api.all('/catalogs/priorities'), payload = row ? this.payload(row) : {};
      this.open(row ? 'Nueva version de plantilla' : 'Crear plantilla', [{ key: 'name', label: 'Nombre de plantilla', required: true, max: 120, value: row?.['name'] }, pick('entity_type', 'Recurso', this.admin() ? ['plan', 'objective', 'task'] : this.session.user()?.role === 'gerente' ? ['plan', 'objective'] : ['task'], row?.['entity_type']), ...this.scope(row), { key: 'is_active', label: 'Activa', type: 'check', value: row?.['is_active'] }, { key: 'title', label: 'Titulo del recurso nuevo', required: true, max: 200, value: payload['title'] }, { key: 'description', label: 'Descripcion', type: 'textarea', max: 10000, value: payload['description'] ?? '' }, { key: 'horizon_type', label: 'Horizonte', type: 'select', required: true, options: options(horizons, 'name', 'code'), value: payload['horizon_type'] }, { key: 'priority_id', label: 'Prioridad de tarea', type: 'select', options: options(priorities), value: payload['priority_id'] }, number('duration_days', 'Duracion inclusiva en dias', 1, 36600, payload['duration_days'])], values => {
        const { title, description, horizon_type, priority_id, duration_days, ...rest } = this.scoped(values);
        return this.api.command('/collaboration/templates/' + (row ? text(row, 'id') : crypto.randomUUID()), { ...rest, expected_version: row ? version(row) : 0, payload: { ...payload, title, description: description ?? '', horizon_type, priority_id: priority_id || null, duration_days, start_offset_days: payload['start_offset_days'] ?? 0, objectives: payload['objectives'] ?? [], tasks: payload['tasks'] ?? [], subtasks: payload['subtasks'] ?? [] } }, 'PUT');
      });
    } catch (error) { this.issue.set(problem(error)); }
  }
  private saveTemplate(row: Row, payload: Row, reason: unknown): Promise<Row> { return this.api.command('/collaboration/templates/' + text(row, 'id'), { entity_type: row['entity_type'], name: row['name'], scope_kind: row['scope_kind'], department_id: row['department_id'], is_active: row['is_active'], expected_version: version(row), reason, payload }, 'PUT'); }
  async templateMetadata(row: Row): Promise<void> {
    try { let department = text(row, 'department_id') || undefined;
      if (row['entity_type'] !== 'plan' && !department) {
        const selected = await firstValueFrom(this.dialog.open(Editor, { width: '560px', maxWidth: '96vw', data: {
          title: 'Contexto de campos y etiquetas', fields: [{ key: 'department_id', label: 'Departamento', type: 'select', required: true, options: options(this.departments()) }],
          submit: async (values: Row) => { department = String(values['department_id']); },
        } }).afterClosed());
        if (selected !== true) return;
      }
      const fields = await creationMetadata(this.api, text(row, 'entity_type'), department);
      const payload = this.payload(row), stored = payload['custom_fields'] as Row ?? {};
      this.open('Valores de plantilla', fields.map(field => ({ ...field, value: field.key === 'tag_ids' ? payload['tag_ids'] : stored[field.key] })), values => this.saveTemplate(row, { ...payload, ...metadataPayload(values, fields) }, values['reason']));
    } catch (error) { this.issue.set(problem(error)); }
  }
  child(row: Row): void {
    const payload = this.payload(row), kind = text(row, 'entity_type');
    const objectivePaths = (payload['objectives'] as Row[] ?? []).map((entry, index) => ({ value: String(index), label: text(entry, 'title') }));
    this.open('Agregar estructura', [pick('child_kind', 'Tipo', kind === 'plan' ? ['objective', ...(objectivePaths.length ? ['task'] : [])] : kind === 'objective' ? ['task'] : ['subtask']), ...(kind === 'plan' && objectivePaths.length ? [{ key: 'objective_index', label: 'Objetivo padre de tarea', type: 'select' as const, options: objectivePaths }] : []), { key: 'title', label: 'Titulo', required: true, max: 200 }, number('start_offset_days', 'Desplazamiento desde inicio del padre', 0, 36600), number('duration_days', 'Duracion inclusiva en dias', 1, 36600), pick('horizon_type', 'Horizonte', ['annual', 'semiannual', 'quarterly', 'monthly', 'custom'])], values => {
      const clone = structuredClone(payload), type = String(values['child_kind']);
      const child: Row = { title: values['title'], start_offset_days: values['start_offset_days'], duration_days: values['duration_days'], ...(type !== 'subtask' ? { description: '', horizon_type: values['horizon_type'], priority_id: null, subtasks: [], objectives: [], tasks: [] } : {}) };
      const parent = type === 'task' && kind === 'plan' ? (clone['objectives'] as Row[])[Number(values['objective_index'])] : clone;
      if (!parent) throw new Error('Objetivo padre requerido');
      const key = type === 'objective' ? 'objectives' : type === 'task' ? 'tasks' : 'subtasks';
      parent[key] = [...parent[key] as Row[] ?? [], child];
      return this.saveTemplate(row, clone, values['reason']);
    });
  }
  async instantiate(row: Row): Promise<void> {
    try { const payload = this.payload(row), kind = text(row, 'entity_type');
      const [plans, objectives, users, horizons] = await Promise.all([this.api.all('/annual-plans'), this.api.all('/objectives'), this.api.all('/catalogs/assignees'), this.api.all('/catalogs/horizons')]);
      const bindings: { path: string; kind: string; title: string }[] = [];
      const visit = (node: Row, type: string, path: string) => { bindings.push({ path, kind: type, title: text(node, 'title') }); for (const [index, child] of (node['objectives'] as Row[] ?? []).entries()) visit(child, 'objective', 'objectives.' + index); for (const [index, child] of (node['tasks'] as Row[] ?? []).entries()) visit(child, 'task', (path === 'root' ? '' : path + '.') + 'tasks.' + index); };
      visit(payload, kind, 'root');
      this.open('Vista previa de plantilla', [{ key: 'start_date', label: 'Inicio', type: 'date', required: true }, { key: 'due_date', label: 'Fin inclusivo', type: 'date', required: true }, { key: 'horizon_type', label: 'Horizonte', type: 'select', required: true, options: options(horizons, 'name', 'code') }, ...(kind === 'objective' ? [{ key: 'annual_plan_id', label: 'Plan padre', type: 'select' as const, required: true, options: options(plans, 'title') }] : kind === 'task' ? [{ key: 'objective_id', label: 'Objetivo padre', type: 'select' as const, required: true, options: options(objectives, 'title') }] : [{ key: 'activate_plan', label: 'Activar plan nuevo', type: 'check' as const }]), ...bindings.flatMap(binding => binding.kind === 'plan' ? [] : [{ key: binding.path + ':department', label: binding.title + ' · Departamento', type: 'select' as const, required: true, options: options(this.departments()) }, ...(binding.kind === 'task' ? [{ key: binding.path + ':assignee', label: binding.title + ' · Responsable', type: 'select' as const, required: true, options: options(users, 'display_name') }] : [])])], async values => {
        const parent = kind === 'task' ? objectives.find(objective => objective['id'] === values['objective_id']) : plans.find(plan => plan['id'] === values['annual_plan_id']);
        const body = { template_version_id: (row['template_version'] as Row)['id'], start_date: values['start_date'], due_date: values['due_date'], horizon_type: values['horizon_type'], annual_plan_id: values['annual_plan_id'] ?? null, objective_id: values['objective_id'] ?? null, activate_plan: values['activate_plan'] ?? false, expected_version: parent ? version(parent) : 0, reason: values['reason'], bindings: bindings.map(binding => ({ path: binding.path, department_id: values[binding.path + ':department'] ?? null, assignee_id: values[binding.path + ':assignee'] ?? null })) };
        const preview = await this.api.command('/collaboration/templates/preview', body);
        const confirmed = await firstValueFrom(this.dialog.open(Editor, { width: '560px', maxWidth: '96vw', data: { title: 'Crear ' + (preview['items'] as Row[]).length + ' recursos nuevos', fields: [], confirm: 'Crear recursos', submit: () => this.api.command('/collaboration/templates/instantiate', body) } }).afterClosed());
        if (confirmed !== true) throw new Error('Creacion no confirmada');
      });
    } catch (error) { this.issue.set(problem(error)); }
  }
  principal(row?: Row): void { this.open(row ? 'Permisos del actor tecnico' : 'Crear actor tecnico', [{ key: 'name', label: 'Nombre', required: true, max: 120, value: row?.['name'] }, { key: 'department_ids', label: 'Departamentos aprobados', type: 'multi', required: true, options: options(this.departments()), value: row?.['department_ids'] }, { key: 'approved_scopes', label: 'Acciones aprobadas', type: 'multi', required: true, options: options(['tasks:create', 'subtasks:create'].map(value => ({ id: value, name: value }))), value: row?.['approved_scopes'] }, { key: 'is_active', label: 'Activo', type: 'check', value: row?.['is_active'] }], values => this.api.command('/collaboration/service-principals/' + (row ? text(row, 'id') : crypto.randomUUID()), { ...values, expected_version: row ? version(row) : 0 }, 'PUT')); }
  async schedule(row?: Row): Promise<void> {
    try { const objectives = await this.api.all('/objectives'); let objectiveId = row ? text(row, 'objective_id') : '';
      if (!objectiveId) { const result = await firstValueFrom(this.dialog.open(Editor, { width: '560px', maxWidth: '96vw', data: { title: 'Objetivo de programacion', fields: [{ key: 'objective_id', label: 'Objetivo', type: 'select', required: true, options: options(objectives, 'title') }], submit: async (values: Row) => { objectiveId = String(values['objective_id']); } } }).afterClosed()); if (result !== true) return; }
      const context = await this.api.get('/collaboration/calendar-context/' + objectiveId), users = await this.api.all('/catalogs/assignees');
      this.open(row ? 'Editar programacion' : 'Crear programacion deshabilitada', [{ key: 'template_version_id', label: 'Version de plantilla de tarea', type: 'select', required: true, options: this.templates().filter(template => template['entity_type'] === 'task' && template['is_active']).map(template => ({ value: text(template['template_version'] as Row, 'id'), label: text(template, 'name') + ' v' + template['current_version'] })), value: row?.['template_version_id'] }, { key: 'owner_user_id', label: 'Propietario A/L', type: 'select', required: true, options: options(users, 'display_name'), value: row?.['owner_user_id'] }, { key: 'assignee_id', label: 'Responsable de tarea', type: 'select', required: true, options: options(users, 'display_name'), value: row?.['assignee_id'] }, { key: 'service_principal_id', label: 'Actor tecnico aprobado', type: 'select', required: true, options: options(this.principals()), value: row?.['service_principal_id'] }, { key: 'calendar_id', label: 'Calendario · ' + context['timezone'], type: 'select', required: true, options: options([context]), value: row?.['calendar_id'] }, pick('frequency', 'Frecuencia', ['daily', 'weekly', 'monthly', 'yearly'], row?.['frequency']), number('interval', 'Intervalo', 1, 366, row?.['interval']), { key: 'start_date', label: 'Primera fecha', type: 'date', required: true, value: row?.['start_date'] }, { key: 'end_date', label: 'Fecha final excluyente de cantidad', type: 'date', value: row?.['end_date'] }, { key: 'occurrence_count', label: 'Cantidad excluyente de fecha final', type: 'number', min: 1, max: 1000, value: row?.['occurrence_count'] }, pick('end_policy', 'Dia inexistente', ['skip', 'last_day'], row?.['end_policy']), pick('non_business_policy', 'Dia no laboral', ['keep', 'skip', 'next', 'previous'], row?.['non_business_policy']), pick('missed_policy', 'Ocurrencias vencidas', ['skip', 'catch_up'], row?.['missed_policy']), ...(row ? [{ key: 'enabled', label: 'Habilitada', type: 'check' as const, value: row['enabled'] }] : [])], values => this.api.command('/collaboration/recurrence-schedules/' + (row ? text(row, 'id') : crypto.randomUUID()), { ...values, objective_id: objectiveId, end_date: values['end_date'] || null, occurrence_count: values['occurrence_count'] ?? null, enabled: row ? values['enabled'] : false, expected_version: row ? version(row) : 0 }, 'PUT'));
    } catch (error) { this.issue.set(problem(error)); }
  }
  run(row: Row): void { const key = crypto.randomUUID(); this.open('Ejecutar programacion', [{ key: 'through_date', label: 'Ejecutar hasta fecha', type: 'date', required: true }, number('limit', 'Maximo de ocurrencias', 1, 100)], async values => { const result = await this.api.command('/collaboration/recurrence-schedules/' + text(row, 'id') + '/runs', { ...values, expected_version: version(row), idempotency_key: key }); this.notice.set('Ejecucion: ' + String((result['job'] as Row)['state'])); return result; }); }
}