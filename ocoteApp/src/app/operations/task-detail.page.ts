import { JsonPipe } from '@angular/common';
import { Component, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { firstValueFrom } from 'rxjs';
import { Api, Page, Row, text, version } from '../core/api';
import { Session } from '../core/session';
import { problem, Problem } from '../core/problem';
import { Editor, Field, options, reason } from '../shared/editor';
import { Feedback } from '../shared/feedback';
import { instant, label, nested, progress } from '../shared/presentation';
import { dateField, descriptionField, titleField } from './tasks.page';
import { Evidence } from './evidence';
import { Transition } from './transition';

@Component({
  standalone: true, imports: [JsonPipe, RouterLink, MatButtonModule, MatDialogModule, MatIconModule, MatMenuModule, MatTooltipModule, Feedback, Evidence],
  template: `<header class="page-heading"><div><p class="eyebrow">EJECUCION</p><h1>{{ task()?.['title'] ?? 'Tarea' }}</h1></div><div class="actions"><a mat-button routerLink="/tareas"><mat-icon>arrow_back</mat-icon>Tareas</a><button mat-icon-button aria-label="Recargar tarea" matTooltip="Recargar" [disabled]="loading()" (click)="load()"><mat-icon>refresh</mat-icon></button></div></header>
    <ocote-feedback [issue]="issue()" />@if (notice()) { <p class="notice" role="status">{{ notice() }}</p> }@if (loading()) { <p role="status">Cargando tarea...</p> }
    @if (task(); as row) {
      <section class="detail-section"><dl class="facts"><div><dt>Plan</dt><dd>{{ nested(row, 'annual_plan')['title'] }}</dd></div><div><dt>Objetivo</dt><dd>{{ nested(row, 'objective')['title'] }}</dd></div>
        <div><dt>Etapa</dt><dd><span class="status" [class.bad]="stageKind(row) === 'blocked'">{{ stageName(row) }}</span></dd></div><div><dt>Prioridad</dt><dd>{{ nested(row, 'priority')['name'] }}</dd></div>
        <div><dt>Responsable</dt><dd>{{ assigneeName(row) }}</dd></div><div><dt>Inicio</dt><dd>{{ row['start_date'] }}</dd></div>
        <div><dt>Compromiso original</dt><dd>{{ row['original_due_date'] }}</dd></div><div><dt>Compromiso vigente</dt><dd>{{ row['due_date'] }}</dd></div>
        <div><dt>Puntualidad original</dt><dd>{{ label(row['baseline_punctuality_status']) }}<small>{{ row['baseline_delay_days'] }} dias de retraso</small></dd></div>
        <div><dt>Puntualidad vigente</dt><dd class="status" [class.bad]="row['is_overdue'] || row['punctuality_status'] === 'late'">{{ label(row['punctuality_status']) }} · {{ row['delay_days'] }} dias</dd></div>
        <div><dt>Cambio de compromiso</dt><dd>{{ row['due_date_delta_days'] }} dias</dd></div><div><dt>Cierre real</dt><dd>{{ instant(row['completed_at']) }}</dd></div>
        <div><dt>Version</dt><dd>{{ row['version'] }}</dd></div></dl>
        <p class="description">{{ row['description'] }}</p><div class="progress-line"><progress max="100" [value]="row['progress_percent']" aria-label="Avance de tarea"></progress><strong>{{ progress(row['progress_percent']) }}</strong>@if (row['pending_closure']) { <span class="status warn">Pendiente de cierre</span> }</div>
        @if (!row['completed_at']) { <div class="toolbar">
          @if (session.has('tasks:manage')) { <button mat-stroked-button (click)="editTask(row)"><mat-icon>edit</mat-icon>Editar</button><button mat-stroked-button (click)="assign(row)"><mat-icon>person</mat-icon>Reasignar</button><button mat-stroked-button (click)="schedule(row)"><mat-icon>event</mat-icon>Cambiar inicio</button> }
          @if (session.has('tasks:transition')) { <button mat-flat-button (click)="transition(row)"><mat-icon>sync_alt</mat-icon>Cambiar etapa</button> }
          @if (session.has('dates:decide')) { <button mat-stroked-button (click)="due(row)"><mat-icon>edit_calendar</mat-icon>Cambiar compromiso</button> }
          @if (session.has('date-requests:create')) { <button mat-stroked-button (click)="requestDate(row)"><mat-icon>event_repeat</mat-icon>Solicitar fecha</button> }
        </div> }
      </section>
      <section class="detail-section"><header class="page-heading"><h2>Subtareas</h2>@if (session.has('tasks:manage') && !row['completed_at']) { <button mat-stroked-button (click)="addChild(row)"><mat-icon>add</mat-icon>Subtarea</button> }</header>
        @if (!children().length) { <p class="muted">Sin subtareas.</p> } @else { <div class="table-wrap" role="region" aria-label="Subtareas" tabindex="0"><table class="data-table"><thead><tr><th scope="col">Titulo</th><th scope="col">Inicio</th><th scope="col">Original</th><th scope="col">Vigente</th><th scope="col">Estado y puntualidad</th><th scope="col">Acciones</th></tr></thead><tbody>
          @for (child of children(); track child['id']) { <tr><td>{{ child['title'] }}</td><td>{{ child['start_date'] }}</td><td>{{ child['original_due_date'] }}</td><td>{{ child['due_date'] }}</td><td>{{ label(child['status']) }}<small>{{ label(child['punctuality_status']) }}</small></td>
            <td>@if (!row['completed_at'] && child['status'] !== 'completed') { <div class="actions">
              @if (session.has('tasks:transition')) { <button mat-icon-button aria-label="Completar subtarea" matTooltip="Completar subtarea" (click)="completeChild(row, child)"><mat-icon>check_circle</mat-icon></button> }
              @if (session.has('tasks:manage') || session.has('dates:decide') || session.has('date-requests:create')) {
                <button mat-icon-button [matMenuTriggerFor]="menu" aria-label="Acciones de subtarea" matTooltip="Acciones"><mat-icon>more_vert</mat-icon></button><mat-menu #menu="matMenu">
                @if (session.has('tasks:manage')) { <button mat-menu-item (click)="editChild(row, child)"><mat-icon>edit</mat-icon>Editar titulo</button><button mat-menu-item (click)="schedule(child, row)"><mat-icon>event</mat-icon>Cambiar inicio</button> }
                @if (session.has('dates:decide')) { <button mat-menu-item (click)="due(child, row)"><mat-icon>edit_calendar</mat-icon>Cambiar compromiso</button> }
                @if (session.has('date-requests:create')) { <button mat-menu-item (click)="requestDate(child, row)"><mat-icon>event_repeat</mat-icon>Solicitar fecha</button> }
              </mat-menu> }
            </div> }</td></tr> }
        </tbody></table></div> }
        @if (childNext()) { <button mat-stroked-button [disabled]="childBusy()" (click)="moreChildren()">Mas subtareas</button> }
      </section>
      <ocote-evidence [task]="row" (refresh)="load()" />
      <section class="detail-section"><header class="page-heading"><h2>Historial</h2><button mat-stroked-button [disabled]="historyBusy()" (click)="loadHistory()"><mat-icon>history</mat-icon>Consultar historial</button></header>
        @if (historyBusy()) { <p role="status">Cargando historial...</p> }
        @if (historyLoaded() && !history().length) { <p class="muted">Sin eventos disponibles.</p> }
        @for (event of history(); track event['id']) { <article class="detail-section"><h3>{{ event['event_type'] }}</h3><p>{{ instant(event['created_at']) }} · Actor {{ event['actor_id'] }}</p><p>{{ event['reason'] }}</p><small>Referencia: {{ event['request_id'] }}</small>
          <details><summary>Antes y despues</summary><h4>Antes</h4><pre>{{ event['before_data'] | json }}</pre><h4>Despues</h4><pre>{{ event['after_data'] | json }}</pre></details></article> }
        @if (historyNext()) { <button mat-stroked-button [disabled]="historyBusy()" (click)="loadHistory(historyNext()!)">Mas eventos</button> }
      </section>
    }`,
})
export class TaskDetailPage implements OnInit {
  private readonly api = inject(Api);
  private readonly route = inject(ActivatedRoute);
  private readonly destroy = inject(DestroyRef);
  private readonly dialog = inject(MatDialog);
  private readonly transitions = inject(Transition);
  readonly session = inject(Session);
  readonly task = signal<Row | null>(null);
  readonly children = signal<Row[]>([]);
  readonly history = signal<Row[]>([]);
  readonly historyLoaded = signal(false);
  readonly childNext = signal<string | null>(null);
  readonly historyNext = signal<string | null>(null);
  readonly childBusy = signal(false);
  readonly historyBusy = signal(false);
  readonly loading = signal(false);
  readonly issue = signal<Problem | null>(null);
  readonly notice = signal('');
  readonly label = label;
  readonly nested = nested;
  readonly instant = instant;
  readonly progress = progress;
  private workflow: { stages: Row[]; transitions: Row[] } = { stages: [], transitions: [] };
  private assignees: Row[] = [];
  private identity = '';
  private epoch = 0;
  stageName(row: Row): string { return text(this.workflow.stages.find(stage => stage['id'] === row['stage_id']) ?? {}, 'name'); }
  stageKind(row: Row): string { return text(this.workflow.stages.find(stage => stage['id'] === row['stage_id']) ?? {}, 'kind'); }
  assigneeName(row: Row): string { return text(this.assignees.find(user => user['id'] === row['assignee_id']) ?? {}, 'display_name') || (row['assignee_id'] === this.session.user()?.id ? this.session.user()!.display_name : 'Responsable no disponible'); }
  ngOnInit(): void { this.route.paramMap.pipe(takeUntilDestroyed(this.destroy)).subscribe(params => { this.identity = params.get('id') ?? ''; void this.load(); }); }
  async load(): Promise<void> {
    const epoch = ++this.epoch, path = '/tasks/' + encodeURIComponent(this.identity);
    this.loading.set(true); this.issue.set(null); this.task.set(null); this.history.set([]); this.historyLoaded.set(false); this.historyNext.set(null);
    try {
      const [task, children, workflow, assignees] = await Promise.all([
        this.api.get(path), this.api.get<Page>(path + '/subtasks', { limit: '50' }),
        this.api.get<{ stages: Row[]; transitions: Row[] }>('/catalogs/workflow'), this.api.all('/catalogs/assignees'),
      ]);
      if (epoch === this.epoch) { this.task.set(task); this.children.set(children.items); this.childNext.set(children.next_cursor ?? null); this.workflow = workflow; this.assignees = assignees; }
    } catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); }
    finally { if (epoch === this.epoch) this.loading.set(false); }
  }
  async moreChildren(): Promise<void> {
    if (this.childBusy() || !this.childNext()) return;
    this.childBusy.set(true); const epoch = this.epoch;
    try { const page = await this.api.get<Page>('/tasks/' + encodeURIComponent(this.identity) + '/subtasks', { cursor: this.childNext()!, limit: '50' });
      if (epoch === this.epoch) { this.children.update(rows => [...rows, ...page.items]); this.childNext.set(page.next_cursor ?? null); }
    } catch (error) { this.issue.set(problem(error)); } finally { this.childBusy.set(false); }
  }
  async loadHistory(cursor = ''): Promise<void> {
    if (this.historyBusy()) return;
    this.historyBusy.set(true); const epoch = this.epoch;
    try { const page = await this.api.get<Page>('/tasks/' + encodeURIComponent(this.identity) + '/history', { limit: '50', ...(cursor ? { cursor } : {}) });
      if (epoch === this.epoch) { this.history.set(cursor ? [...this.history(), ...page.items] : page.items); this.historyLoaded.set(true); this.historyNext.set(page.next_cursor ?? null); }
    } catch (error) { this.issue.set(problem(error)); } finally { this.historyBusy.set(false); }
  }
  private async command(title: string, fields: Field[], path: string, base: Row, method: 'POST' | 'PATCH' = 'POST', message?: string): Promise<void> {
    const result = await firstValueFrom(this.dialog.open(Editor, { width: '640px', maxWidth: '96vw', data: {
      title, fields, message, submit: (values: Row) => this.api.command(path, { ...values, ...base }, method),
    } }).afterClosed());
    if (result) { this.notice.set(result === 'reload' ? 'Datos recargados. Revisa las versiones antes de volver a editar.' : 'Cambio guardado.'); await this.load(); }
  }
  async editTask(row: Row): Promise<void> {
    try {
      const priorities = await this.api.all('/catalogs/priorities');
      if (!priorities.some(priority => priority['id'] === row['priority_id'])) priorities.push(nested(row, 'priority'));
      await this.command('Editar tarea', [titleField(row), descriptionField(row), { key: 'priority_id', label: 'Prioridad', type: 'select', required: true, value: row['priority_id'], options: options(priorities) }], '/tasks/' + text(row,'id'), { expected_version: version(row) }, 'PATCH');
    } catch (error) { this.issue.set(problem(error)); }
  }
  async assign(row: Row): Promise<void> {
    try {
      const objective = await this.api.get('/objectives/' + text(row,'objective_id'));
      const users = await this.api.all('/catalogs/assignees', { department_id: text(objective,'department_id') });
      await this.command('Reasignar tarea', [{ key:'assignee_id',label:'Responsable',type:'select',required:true,options:options(users,'display_name') }, reason()], '/tasks/' + text(row,'id') + '/assignments', { expected_version: version(row) });
    } catch (error) { this.issue.set(problem(error)); }
  }
  async transition(row: Row): Promise<void> {
    try { if (await this.transitions.open(row)) await this.load(); }
    catch (error) { this.issue.set(problem(error)); }
  }
  async schedule(row: Row, task?: Row): Promise<void> {
    await this.command('Cambiar inicio', [dateField('start_date','Nuevo inicio',row['start_date']),reason()], (task ? '/subtasks/' : '/tasks/') + text(row,'id') + '/schedule-changes', { expected_version:version(row),...(task ? { expected_task_version:version(task) } : {}) });
  }
  async due(row: Row, task?: Row): Promise<void> {
    await this.command('Cambiar compromiso vigente', [dateField('due_date','Nuevo compromiso',row['due_date']),reason()], (task ? '/subtasks/' : '/tasks/') + text(row,'id') + '/due-date-changes', { expected_version:version(row),...(task ? { expected_task_version:version(task) } : {}) });
  }
  async requestDate(row: Row, task?: Row): Promise<void> {
    await this.command('Solicitar cambio de fecha', [dateField('proposed_due_date','Fecha propuesta'),reason()], (task ? '/subtasks/' : '/tasks/') + text(row,'id') + '/due-date-requests', { expected_task_version:version(task ?? row),...(task ? { expected_subtask_version:version(row) } : {}) });
  }
  async addChild(row: Row): Promise<void> {
    await this.command('Crear subtarea', [titleField(),dateField('start_date','Inicio'),dateField('due_date','Compromiso')], '/tasks/' + text(row,'id') + '/subtasks', { expected_version:version(row) });
  }
  async editChild(task: Row, row: Row): Promise<void> {
    await this.command('Editar subtarea', [titleField(row)], '/subtasks/' + text(row,'id'), { expected_version:version(row),expected_task_version:version(task) }, 'PATCH');
  }
  async completeChild(task: Row, row: Row): Promise<void> {
    await this.command('Completar definitivamente · ' + text(row,'title'), [], '/subtasks/' + text(row,'id') + '/completion', { expected_version:version(row),expected_task_version:version(task) }, 'POST', 'La subtarea "' + text(row,'title') + '" quedara completada sin reapertura.');
  }
}