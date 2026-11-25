import { Component, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSelectModule } from '@angular/material/select';
import { firstValueFrom } from 'rxjs';
import { Api, Page, Row, text } from '../core/api';
import { Session } from '../core/session';
import { Problem, problem } from '../core/problem';
import { Editor, Field, options } from '../shared/editor';
import { Feedback } from '../shared/feedback';
import { Pager, Pagination } from '../shared/pager';
import { label, nested, progress } from '../shared/presentation';

export const titleField = (row?: Row): Field => ({ key: 'title', label: 'Titulo', required: true, max: 200, value: row?.['title'] });
export const descriptionField = (row?: Row): Field => ({ key: 'description', label: 'Descripcion', type: 'textarea', max: 10000, value: row?.['description'] ?? '' });
export const dateField = (key: string, label: string, value?: unknown): Field => ({ key, label, type: 'date', required: true, value });

export async function executionCatalogs(api: Api, role: string) {
  const [workflow, priorities, assignees] = await Promise.all([api.get<{ stages: Row[]; transitions: Row[] }>('/catalogs/workflow'), api.all('/catalogs/priorities'), api.all('/catalogs/assignees')]);
  const fields: Field[] = [];
  let departments: Row[] = [];
  if (role !== 'colaborador') {
    const [plans, scopedDepartments, objectives] = await Promise.all([api.all('/annual-plans'), api.all('/catalogs/departments'), api.all('/objectives')]);
    departments = scopedDepartments;
    fields.push({ key:'annual_plan_id',label:'Plan',options:options(plans,'title') }, { key:'department_id',label:'Departamento',options:options(departments) }, { key:'objective_id',label:'Objetivo',options:options(objectives,'title') }, { key:'assignee_id',label:'Responsable',options:options(assignees,'display_name') });
  }
  fields.push({ key:'stage_id',label:'Etapa',options:options(workflow.stages) }, { key:'priority_id',label:'Prioridad',options:options(priorities) },
    { key:'punctuality_status',label:'Puntualidad vigente',options:['pending','on_time','late','overdue'].map(value => ({ value, label: label(value) })) });
  return { workflow, assignees, departments, fields };
}

@Component({
  standalone: true, imports: [RouterLink, MatButtonModule, MatDialogModule, MatIconModule, MatTooltipModule, MatSelectModule, Feedback, Pager],
  template: `<header class="page-heading"><div><p class="eyebrow">EJECUCION</p><h1>{{ session.user()?.role === 'colaborador' ? 'Mis tareas' : 'Tareas' }}</h1></div><div class="actions">
    <button mat-icon-button aria-label="Recargar tareas" matTooltip="Recargar" [disabled]="loading()" (click)="load()"><mat-icon>refresh</mat-icon></button>
    @if (session.has('tasks:manage')) { <button mat-flat-button (click)="create()"><mat-icon>add</mat-icon>Crear tarea</button> }
    </div></header><ocote-feedback [issue]="issue()" />
    <div class="filters">@for (filter of filters(); track filter.key) { <mat-form-field><mat-label>{{ filter.label }}</mat-label><mat-select [value]="query[filter.key] || ''" (selectionChange)="filterChanged(filter.key, $event.value)"><mat-option value="">Todos</mat-option>@for (option of filter.options; track option.value) { <mat-option [value]="option.value">{{ option.label }}</mat-option> }</mat-select></mat-form-field> }</div>
    @if (loading()) { <p role="status">Cargando tareas...</p> }
    @else if (!rows().length) { <section class="empty-state"><mat-icon>task_alt</mat-icon><h2>Sin tareas</h2><p>No hay tareas para este alcance y filtros.</p></section> }
    @else { <div class="table-wrap" role="region" aria-label="Tareas" tabindex="0"><table class="data-table"><thead><tr><th scope="col">Tarea</th><th scope="col">Etapa</th><th scope="col">Prioridad</th><th scope="col">Responsable</th><th scope="col">Compromiso original</th><th scope="col">Compromiso vigente</th><th scope="col">Puntualidad</th><th scope="col">Avance</th></tr></thead><tbody>
      @for (row of rows(); track row['id']) { <tr><td><a [routerLink]="['/tareas', row['id']]">{{ row['title'] }}</a><small>{{ nested(row, 'objective')['title'] }}</small></td>
      <td>{{ stageName(row) }}</td><td>{{ nested(row, 'priority')['name'] }}</td><td>{{ assigneeName(row) }}</td><td>{{ row['original_due_date'] }}</td><td>{{ row['due_date'] }}</td>
      <td><span class="status" [class.bad]="row['is_overdue'] || row['punctuality_status'] === 'late'">{{ label(row['punctuality_status']) }}</span>@if (row['due_date_delta_days']) { <small>{{ row['due_date_delta_days'] }} dias frente al original</small> }</td><td class="numeric">{{ progress(row['progress_percent']) }}@if (row['pending_closure']) { <small>Pendiente de cierre</small> }</td></tr> }
    </tbody></table></div> }<ocote-pager [state]="pagination" [busy]="loading()" (navigate)="load($event)" (sizeChange)="resize($event)" />`,
})
export class TasksPage implements OnInit {
  private readonly api = inject(Api);
  private readonly dialog = inject(MatDialog);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  readonly session = inject(Session);
  readonly rows = signal<Row[]>([]);
  readonly filters = signal<Field[]>([]);
  readonly loading = signal(false);
  readonly issue = signal<Problem | null>(null);
  readonly pagination = new Pagination();
  readonly next = this.pagination.next;
  readonly cursor = this.pagination.cursor;
  readonly label = label;
  readonly nested = nested;
  readonly progress = progress;
  readonly query: Record<string, string> = {};
  private stages: Row[] = [];
  private assignees: Row[] = [];
  private epoch = 0;
  stageName(row: Row): string { return text(this.stages.find(stage => stage['id'] === row['stage_id']) ?? {}, 'name') || 'Etapa no disponible'; }
  assigneeName(row: Row): string { return text(this.assignees.find(user => user['id'] === row['assignee_id']) ?? {}, 'display_name') || (row['assignee_id'] === this.session.user()?.id ? this.session.user()!.display_name : 'Responsable no disponible'); }
  ngOnInit(): void {
    for (const key of ['annual_plan_id','department_id','objective_id','assignee_id','stage_id','priority_id','punctuality_status']) {
      const value = this.route.snapshot.queryParamMap.get(key); if (value) this.query[key] = value;
    }
    void this.loadFilters(); void this.load();
  }
  async loadFilters(): Promise<void> {
    try {
      const catalogs = await executionCatalogs(this.api, this.session.user()?.role ?? '');
      this.stages = catalogs.workflow.stages; this.assignees = catalogs.assignees; this.filters.set(catalogs.fields);
    } catch (error) { this.issue.set(problem(error)); }
  }
  filterChanged(key: string, value: string): void { if (value) this.query[key] = value; else delete this.query[key]; void this.load(); }
  resize(size: number): void { if (this.pagination.resize(size)) void this.load(); }
  async load(cursor = ''): Promise<void> {
    const epoch = ++this.epoch; this.loading.set(true); this.issue.set(null);
    try { const page = await this.api.get<Page>('/tasks', { ...this.query, limit: String(this.pagination.size()), ...(cursor ? { cursor } : {}) });
      if (epoch === this.epoch) { this.rows.set(page.items); this.pagination.accept(cursor, page.next_cursor); }
    } catch (error) { if (epoch === this.epoch) { this.rows.set([]); this.issue.set(problem(error)); } }
    finally { if (epoch === this.epoch) this.loading.set(false); }
  }
  async create(): Promise<void> {
    if (!this.session.has('tasks:manage')) return;
    try {
      const [plans, objectives] = await Promise.all([this.api.all('/annual-plans'), this.api.all('/objectives')]);
      const active = new Set(plans.filter(plan => plan['status'] === 'active').map(plan => plan['id']));
      let selected: Row | undefined;
      const result = await firstValueFrom(this.dialog.open(Editor, { width: '560px', maxWidth: '96vw', data: {
        title: 'Seleccionar objetivo', confirm: 'Continuar', fields: [{ key: 'objective_id', label: 'Objetivo de un plan activo', type: 'select', required: true, options: options(objectives.filter(row => active.has(row['annual_plan_id'])), 'title') }],
        submit: async (values: Row) => { selected = objectives.find(row => row['id'] === values['objective_id']); },
      } }).afterClosed());
      if (result !== true || !selected) return;
      const objective = selected;
      const [assignees, priorities] = await Promise.all([this.api.all('/catalogs/assignees', { department_id: text(objective, 'department_id') }), this.api.all('/catalogs/priorities')]);
      let created: Row | undefined;
      const saved = await firstValueFrom(this.dialog.open(Editor, { width: '640px', maxWidth: '96vw', data: {
        title: 'Crear tarea · ' + text(objective, 'title'),
        fields: [titleField(), descriptionField(), dateField('start_date', 'Inicio'), dateField('due_date', 'Compromiso'),
          { key:'assignee_id',label:'Responsable',type:'select',required:true,options:options(assignees,'display_name') },
          { key:'priority_id',label:'Prioridad',type:'select',required:true,options:options(priorities) }],
        submit: async (values: Row) => { created = await this.api.command('/tasks', { ...values, objective_id: objective['id'] }); },
      } }).afterClosed());
      if (saved === true && created) await this.router.navigate(['/tareas', text(created, 'id')]);
    } catch (error) { this.issue.set(problem(error)); }
  }
}