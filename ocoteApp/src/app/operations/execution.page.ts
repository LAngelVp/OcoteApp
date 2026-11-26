import { AfterViewInit, Component, ElementRef, inject, NgZone, OnDestroy, OnInit, signal, ViewChild } from '@angular/core';
import { CdkDragDrop, DragDropModule } from '@angular/cdk/drag-drop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Timeline, TimelineGroup, TimelineItem } from 'vis-timeline/standalone';
import { Api, Page, Row, text } from '../core/api';
import { Session } from '../core/session';
import { problem, Problem } from '../core/problem';
import { Field } from '../shared/editor';
import { Feedback } from '../shared/feedback';
import { Pager, Pagination } from '../shared/pager';
import { label, progress } from '../shared/presentation';
import { executionCatalogs } from './tasks.page';
import { Transition } from './transition';
import { CollaborationIndicators } from './collaboration';
import { Search } from './search';

export interface Lane { stage: Row; count: number; items: Row[]; next_cursor?: string | null; }
export function civilDate(value: string, following = false): Date {
  const parts = value.split('-').map(Number), date = new Date(0);
  date.setFullYear(parts[0], parts[1] - 1, parts[2] + (following ? 1 : 0)); date.setHours(0, 0, 0, 0);
  return date;
}
function safeContent(value: string): HTMLElement { const content = document.createElement('span'); content.textContent = value; return content; }

@Component({
    imports: [RouterLink, DragDropModule, MatButtonModule, MatIconModule, MatSelectModule, MatTooltipModule, Feedback, Pager, CollaborationIndicators, Search],
    template: `<header class="page-heading"><div><p class="eyebrow">EJECUCION</p><h1>{{ view === 'kanban' ? 'Kanban' : 'Timeline' }}</h1></div><div class="actions"><a mat-button routerLink="/tareas"><mat-icon>list</mat-icon>Tareas</a><button mat-icon-button aria-label="Recargar vista" matTooltip="Recargar" [disabled]="loading() || moving()" (click)="load()"><mat-icon>refresh</mat-icon></button></div></header>
    <ocote-feedback [issue]="issue()" /><p class="sr-only" role="status" aria-live="polite">{{ notice() }}</p>
    <ocote-search (apply)="filterChanged('f9_filters',encodeFilters($event))" />
    <div class="filters">@for (filter of filters(); track filter.key) { <mat-form-field><mat-label>{{ filter.label }}</mat-label><mat-select [value]="query[filter.key] || ''" [disabled]="moving()" (selectionChange)="filterChanged(filter.key, $event.value)"><mat-option value="">Todos</mat-option>@for (option of filter.options; track option.value) { <mat-option [value]="option.value">{{ option.label }}</mat-option> }</mat-select></mat-form-field> }</div>
    @if (view === 'kanban') {
      @if (loading()) { <p role="status">Cargando tablero...</p> }
      <div class="kanban" cdkDropListGroup role="region" aria-label="Tablero por etapas" tabindex="0">
        @for (lane of lanes(); track lane.stage['id']) { <section class="kanban-lane"><header><h2>{{ lane.stage['name'] }}</h2><span class="numeric" [attr.aria-label]="lane.count + ' tareas'">{{ lane.count }}</span></header>
          <div class="lane-body" cdkDropList [id]="'lane-' + lane.stage['id']" [cdkDropListData]="lane" [cdkDropListSortingDisabled]="true" [cdkDropListDisabled]="!session.has('tasks:transition') || moving() || loading()" (cdkDropListDropped)="drop($event)">
            @for (row of lane.items; track row['id']) { <article class="task-card" cdkDrag [cdkDragData]="row" [cdkDragDisabled]="!session.has('tasks:transition') || !!row['completed_at'] || moving()"><header><a [routerLink]="['/tareas',row['id']]">{{ row['title'] }}</a>@if (session.has('tasks:transition') && !row['completed_at']) { <button mat-icon-button aria-label="Cambiar etapa" matTooltip="Cambiar etapa" [disabled]="moving()" (click)="move(row)"><mat-icon>sync_alt</mat-icon></button> }</header>
              <small>{{ responsible(row) }}</small><dl><div><dt>Original</dt><dd>{{ row['original_due_date'] }}</dd></div><div><dt>Vigente</dt><dd>{{ row['due_date'] }}</dd></div></dl>
              <span class="status" [class.bad]="row['is_overdue'] || row['punctuality_status'] === 'late'">{{ label(row['punctuality_status']) }}</span><div class="progress-line"><progress max="100" [value]="row['progress_percent']" aria-label="Avance"></progress><span>{{ progress(row['progress_percent']) }}</span></div>
              @if (row['pending_closure']) { <small class="status warn">Pendiente de cierre</small> }
              <ocote-collaboration-indicators [record]="row" />
            </article> }
            @if (!lane.items.length) { <p class="muted lane-empty">Sin tareas.</p> }
          </div>@if (lane.next_cursor) { <button mat-button [disabled]="!!laneBusy() || moving()" (click)="moreLane(lane)">Mas tareas</button> }
        </section> }
      </div>@if (!lanes().length && !loading()) { <section class="empty-state"><h2>Sin etapas activas</h2></section> }
    } @else {
      <div class="toolbar"><mat-form-field><mat-label>Nivel</mat-label><mat-select [value]="kind()" (selectionChange)="changeKind($event.value)">@for (item of kinds; track item.value) { <mat-option [value]="item.value">{{ item.name }}</mat-option> }</mat-select></mat-form-field>
        <mat-form-field><mat-label>Agrupar</mat-label><mat-select [value]="group()" (selectionChange)="group.set($event.value); render()"><mat-option value="">Elemento</mat-option><mat-option value="scope_department_id">Departamento</mat-option><mat-option value="scope_assignee_id">Responsable</mat-option></mat-select></mat-form-field>
        <button mat-icon-button aria-label="Acercar Timeline" matTooltip="Acercar" (click)="zoom(true)"><mat-icon>zoom_in</mat-icon></button><button mat-icon-button aria-label="Alejar Timeline" matTooltip="Alejar" (click)="zoom(false)"><mat-icon>zoom_out</mat-icon></button><button mat-icon-button aria-label="Ajustar Timeline" matTooltip="Ajustar periodo" (click)="fit()"><mat-icon>fit_screen</mat-icon></button>
      </div><p class="timeline-legend"><span>Barra: compromiso vigente</span><span class="original-key">Rombo: compromiso original</span><span class="completed-key">Punto: cierre real</span></p>
    }
    <div #timelineHost class="timeline-host" [hidden]="view !== 'timeline'" role="region" aria-label="Cronologia de compromisos" tabindex="0"></div>
    @if (view === 'timeline') {
      @if (loading()) { <p role="status">Cargando cronologia...</p> } @else if (!rows().length) { <p class="empty-state">Sin elementos para este alcance y filtros.</p> }
      <div class="table-wrap" role="region" aria-label="Fechas de Timeline" tabindex="0"><table class="data-table"><thead><tr><th>Elemento</th><th>Inicio</th><th>Compromiso original</th><th>Vigente</th><th>Cierre real</th><th>Puntualidad</th></tr></thead><tbody>@for (row of rows(); track row['id']) { <tr><td>@if (row['task_id']) { <a [routerLink]="['/tareas',row['task_id']]">{{ row['title'] }}</a> } @else { {{ row['title'] }} }</td><td>{{ row['start_date'] }}</td><td>{{ row['original_due_date'] || 'No aplica' }}</td><td>{{ row['due_date'] }}</td><td>{{ instant(row['completed_at']) }}</td><td>{{ label(row['punctuality_status']) }}</td></tr> }</tbody></table></div>
      @for (row of rows(); track row['id']) { @if (row['collaboration']) { <div class="toolbar"><span>{{ row['title'] }}</span><ocote-collaboration-indicators [record]="row" /></div> } }
      <ocote-pager [state]="pagination" [busy]="loading()" (navigate)="load($event)" (sizeChange)="resize($event)" />
    }`,
    styles: [`.kanban{display:flex;gap:16px;overflow:auto;align-items:flex-start;padding:20px 3px;min-height:300px}.kanban-lane{flex:0 0 280px;max-width:85vw;border-top:3px solid var(--ocote-secondary);background:var(--ocote-surface-secondary)}.kanban-lane>header,.task-card header{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}.kanban-lane>header{padding:12px}.kanban-lane h2{font-size:18px;margin:0}.lane-body{min-height:160px;padding:0 8px 8px}.task-card{background:var(--ocote-surface);border:1px solid var(--ocote-border);border-radius:8px;padding:12px;margin-bottom:8px;overflow-wrap:anywhere}.task-card a{font-weight:600;min-width:0}.task-card button{flex-shrink:0}.task-card dl{display:flex;gap:16px;font-size:14px;margin:12px 0}.task-card dd{margin-bottom:0}.task-card progress{width:120px}.lane-empty{padding:24px 8px}.timeline-host{height:440px;max-width:100%;background:var(--ocote-surface)}.toolbar mat-form-field{width:200px;max-width:100%}.timeline-legend{display:flex;gap:16px;flex-wrap:wrap;font-size:14px}.original-key{color:var(--ocote-primary-dark)}.completed-key{color:var(--ocote-success)}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}.cdk-drag-preview{box-shadow:0 4px 12px #0003}.cdk-drag-placeholder{opacity:.3}`]
})
export class ExecutionPage implements OnInit, AfterViewInit, OnDestroy {
  private readonly api = inject(Api);
  private readonly transitions = inject(Transition);
  private readonly zone = inject(NgZone);
  readonly session = inject(Session);
  readonly view = inject(ActivatedRoute).snapshot.data['view'] as 'kanban' | 'timeline';
  @ViewChild('timelineHost') host?: ElementRef<HTMLElement>;
  readonly lanes = signal<Lane[]>([]);
  readonly rows = signal<Row[]>([]);
  readonly filters = signal<Field[]>([]);
  readonly loading = signal(false);
  readonly moving = signal(false);
  readonly laneBusy = signal('');
  readonly issue = signal<Problem | null>(null);
  readonly notice = signal('');
  readonly pagination = new Pagination();
  readonly next = this.pagination.next;
  readonly cursor = this.pagination.cursor;
  readonly kind = signal('task');
  readonly group = signal('');
  readonly query: Record<string, string> = {};
  readonly encodeFilters = JSON.stringify;
  readonly label = label;
  readonly progress = progress;
  instant(value: unknown): string {
    if (!value) return '-';
    if (!this.timezone) return 'Zona no disponible';
    return new Intl.DateTimeFormat('es-MX', { timeZone:this.timezone,dateStyle:'medium',timeStyle:'short' }).format(new Date(String(value)));
  }
  readonly kinds = [{ value:'plan',name:'Planes' },{ value:'objective',name:'Objetivos' },{ value:'task',name:'Tareas' },{ value:'subtask',name:'Subtareas' }].filter(item => this.session.user()?.role !== 'colaborador' || ['task','subtask'].includes(item.value));
  private assignees: Row[] = [];
  private departments: Row[] = [];
  private timezone = '';
  private timeline?: Timeline;
  private epoch = 0;
  private destroyed = false;
  async ngOnInit(): Promise<void> {
    void this.load();
    try { const catalogs = await executionCatalogs(this.api, this.session.user()?.role ?? '');
      if (!this.destroyed) { this.filters.set(catalogs.fields); this.assignees = catalogs.assignees; this.departments = catalogs.departments; this.render(); }
    } catch (error) { if (!this.destroyed) this.issue.set(problem(error)); }
  }
  ngAfterViewInit(): void { this.render(); }
  ngOnDestroy(): void { this.destroyed = true; ++this.epoch; this.zone.runOutsideAngular(() => this.timeline?.destroy()); }
  responsible(row: Row): string { return text(this.assignees.find(person => person['id'] === row['assignee_id']) ?? {}, 'display_name') || 'Responsable no disponible'; }
  filterChanged(key: string, value: string): void { if (value) this.query[key] = value; else delete this.query[key]; void this.load(); }
  changeKind(kind: string): void { this.kind.set(kind); void this.load(); }
  resize(size: number): void { if (this.view === 'timeline' && this.pagination.resize(size)) void this.load(); }
  async load(cursor = ''): Promise<void> {
    const epoch = ++this.epoch;
    this.loading.set(true); this.issue.set(null);
    try {
      if (this.view === 'kanban') {
        const page = await this.api.get<{ columns: Lane[] }>('/kanban', { ...this.query, limit:'25' });
        if (epoch === this.epoch) this.lanes.set(page.columns);
      } else {
        const page = await this.api.get<Page & { organization_timezone: string }>('/timeline', { ...this.query, kind:this.kind(), limit:String(this.pagination.size()), ...(cursor ? { cursor } : {}) });
        if (epoch === this.epoch) { this.rows.set(page.items); this.timezone = page.organization_timezone; this.pagination.accept(cursor, page.next_cursor); this.render(); }
      }
    } catch (error) { if (epoch === this.epoch) { this.lanes.set([]); this.rows.set([]); this.render(); this.issue.set(problem(error)); } }
    finally { if (epoch === this.epoch) this.loading.set(false); }
  }
  async moreLane(lane: Lane): Promise<void> {
    if (!lane.next_cursor || this.laneBusy()) return;
    const epoch = this.epoch; this.laneBusy.set(text(lane.stage,'id'));
    try {
      const page = await this.api.get<{ columns: Lane[] }>('/kanban', { ...this.query, lane_id:text(lane.stage,'id'), cursor:lane.next_cursor, limit:'25' });
      const next = page.columns[0];
      if (epoch === this.epoch && next) this.lanes.update(lanes => lanes.map(item => item.stage['id'] === next.stage['id'] ? { ...next, items:[...item.items,...next.items] } : item));
    } catch (error) { this.issue.set(problem(error)); } finally { this.laneBusy.set(''); }
  }
  async move(row: Row, target = ''): Promise<void> {
    if (this.moving() || !this.session.has('tasks:transition') || row['completed_at']) return;
    this.moving.set(true);
    try { const saved = await this.transitions.open(row, target); if (saved) { await this.load(); this.notice.set(saved === 'reload' ? 'Datos recargados.' : 'Etapa actualizada.'); } }
    catch (error) { this.issue.set(problem(error)); } finally { this.moving.set(false); }
  }
  drop(event: CdkDragDrop<Lane>): void { const row = event.item.data as Row; if (row['stage_id'] !== event.container.data.stage['id']) void this.move(row, text(event.container.data.stage,'id')); }
  render(): void {
    this.zone.runOutsideAngular(() => this.renderTimeline());
  }
  private renderTimeline(): void {
    if (this.destroyed || this.view !== 'timeline' || !this.host) return;
    const groups = new Map<string, TimelineGroup>(), items: TimelineItem[] = [];
    for (const row of this.rows()) {
      const identity = text(row,'id'), grouping = this.group(), group = grouping ? text(row,grouping) || 'unassigned' : identity;
      const catalogs = grouping === 'scope_department_id' ? this.departments : this.assignees;
      const name = grouping ? text(catalogs.find(item => item['id'] === row[grouping]) ?? {}, grouping === 'scope_department_id' ? 'name' : 'display_name') || 'Sin agrupacion' : text(row,'title');
      groups.set(group, { id:group,content:safeContent(name) });
      items.push({ id:identity,group,start:civilDate(text(row,'start_date')),end:civilDate(text(row,'due_date'),true),type:'range',content:safeContent(text(row,'title')),className:'ocote-current' });
      if (row['original_due_date']) items.push({ id:identity+'-original',group,start:civilDate(text(row,'original_due_date')),type:'point',content:safeContent('Original'),className:'ocote-original' });
      if (row['completed_at'] && this.timezone) {
        const parts = new Intl.DateTimeFormat('en-CA',{ timeZone:this.timezone,year:'numeric',month:'2-digit',day:'2-digit' }).formatToParts(new Date(text(row,'completed_at')));
        const date = ['year','month','day'].map(key => parts.find(part => part.type === key)!.value).join('-');
        items.push({ id:identity+'-completed',group,start:civilDate(date),type:'point',content:safeContent('Cierre real'),className:'ocote-completed' });
      }
    }
    if (!this.timeline) this.timeline = new Timeline(this.host.nativeElement, [], {
      height:'440px',stack:true,editable:false,selectable:true,showCurrentTime:false,locale:'es',
      orientation:'top',zoomKey:'ctrlKey',margin:{ item:14,axis:20 },
    });
    this.timeline.setGroups([...groups.values()]); this.timeline.setItems(items); this.fit();
  }
  fit(): void { this.timeline?.fit({ animation:false }); }
  zoom(closer: boolean): void { if (closer) this.timeline?.zoomIn(.4,{ animation:false }); else this.timeline?.zoomOut(.4,{ animation:false }); }
}