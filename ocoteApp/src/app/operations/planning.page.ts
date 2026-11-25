import { Component, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSelectModule } from '@angular/material/select';
import { Api, Page, Row, text, version } from '../core/api';
import { Session } from '../core/session';
import { Problem, problem } from '../core/problem';
import { Editor, Field, options, reason } from '../shared/editor';
import { Feedback } from '../shared/feedback';
import { label, progress } from '../shared/presentation';

@Component({
  standalone: true, imports: [RouterLink, MatButtonModule, MatDialogModule, MatIconModule, MatTooltipModule, MatSelectModule, Feedback],
  template: `<header class="page-heading"><div><p class="eyebrow">PLANIFICACION</p><h1>{{ record() ? record()!['title'] : title }}</h1></div><div class="actions">
    <button mat-icon-button aria-label="Recargar" matTooltip="Recargar" [disabled]="loading()" (click)="load()"><mat-icon>refresh</mat-icon></button>
    @if (!identity && session.has('planning:manage')) { <button mat-flat-button (click)="edit()"><mat-icon>add</mat-icon>{{ plans ? 'Crear plan' : 'Crear objetivo' }}</button> }
    </div></header><ocote-feedback [issue]="issue()" />
    @if (notice()) { <p class="notice" role="status">{{ notice() }}</p> }
    @if (loading()) { <p role="status">Cargando {{ title.toLowerCase() }}...</p> }
    @if (!identity && !plans) { <div class="filters"><mat-form-field><mat-label>Plan</mat-label><mat-select [(value)]="planFilter" (selectionChange)="load()"><mat-option value="">Todos</mat-option>@for (plan of planOptions(); track plan['id']) { <mat-option [value]="plan['id']">{{ plan['title'] }}</mat-option> }</mat-select></mat-form-field></div> }
    @if (record(); as row) {
      <section class="detail-section"><dl class="facts"><div><dt>Horizonte</dt><dd>{{ label(row['horizon_type']) }}</dd></div><div><dt>Inicio</dt><dd>{{ row['start_date'] }}</dd></div><div><dt>Fin inclusivo</dt><dd>{{ row['due_date'] }}</dd></div>
        @if (plans) { <div><dt>Estado</dt><dd>{{ label(row['status']) }}</dd></div> }
        <div><dt>Avance</dt><dd>{{ progress(row['progress_percent']) }}</dd></div><div><dt>Version</dt><dd>{{ row['version'] }}</dd></div></dl>
        @if (!plans) { <p class="description">{{ row['description'] }}</p> }
        <div class="actions">@if (session.has('planning:manage') && !closed()) {
          <button mat-stroked-button (click)="edit(row)"><mat-icon>edit</mat-icon>Editar</button><button mat-stroked-button (click)="period(row)"><mat-icon>date_range</mat-icon>Cambiar periodo</button>
          @if (plans && row['status'] === 'draft') { <button mat-flat-button (click)="status(row, 'active')"><mat-icon>play_arrow</mat-icon>Activar</button> }
          @if (plans && row['status'] === 'active') { <button mat-stroked-button (click)="status(row, 'closed')"><mat-icon>lock</mat-icon>Cerrar plan</button> }
        }
        @if (plans) { <a mat-button routerLink="/objetivos" [queryParams]="{ annual_plan_id: row['id'] }">Ver objetivos</a> }
        @else { <a mat-button [routerLink]="['/planes', row['annual_plan_id']]">Ver plan</a><a mat-button routerLink="/tareas" [queryParams]="{ objective_id: row['id'] }">Ver tareas</a> }
        <a mat-button [routerLink]="plans ? '/planes' : '/objetivos'">Volver al listado</a></div>
      </section>
    } @else if (!loading() && !identity) {
      @if (!rows().length) { <section class="empty-state"><mat-icon>flag</mat-icon><h2>Sin {{ title.toLowerCase() }}</h2><p>No hay registros para este alcance y filtro.</p></section> }
      @else { <div class="table-wrap" role="region" [attr.aria-label]="title" tabindex="0"><table class="data-table"><thead><tr><th scope="col">Titulo</th><th scope="col">Horizonte</th><th scope="col">Inicio</th><th scope="col">Fin</th><th scope="col">Avance</th>@if (plans) { <th scope="col">Estado</th> }</tr></thead><tbody>
        @for (row of rows(); track row['id']) { <tr><td><a [routerLink]="[plans ? '/planes' : '/objetivos', row['id']]">{{ row['title'] }}</a></td><td>{{ label(row['horizon_type']) }}</td><td>{{ row['start_date'] }}</td><td>{{ row['due_date'] }}</td><td class="numeric">{{ progress(row['progress_percent']) }}</td>@if (plans) { <td>{{ label(row['status']) }}</td> }</tr> }
      </tbody></table></div><div class="pager"><button mat-button [disabled]="!cursor()" (click)="load()">Primera pagina</button><button mat-stroked-button [disabled]="!next()" (click)="load(next()!)">Siguiente</button></div> }
    }`,
})
export class PlanningPage implements OnInit {
  private readonly api = inject(Api);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroy = inject(DestroyRef);
  private readonly dialog = inject(MatDialog);
  readonly session = inject(Session);
  readonly plans = this.route.snapshot.data['kind'] === 'plans';
  readonly title = this.plans ? 'Planes' : 'Objetivos';
  readonly endpoint = this.plans ? '/annual-plans' : '/objectives';
  identity = '';
  planFilter = this.route.snapshot.queryParamMap.get('annual_plan_id') ?? '';
  readonly rows = signal<Row[]>([]);
  readonly planOptions = signal<Row[]>([]);
  readonly record = signal<Row | null>(null);
  readonly parent = signal<Row | null>(null);
  readonly loading = signal(false);
  readonly issue = signal<Problem | null>(null);
  readonly notice = signal('');
  readonly next = signal<string | null>(null);
  readonly cursor = signal('');
  readonly label = label;
  readonly progress = progress;
  private epoch = 0;
  closed(): boolean { return (this.plans ? this.record() : this.parent())?.['status'] === 'closed'; }
  ngOnInit(): void {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroy)).subscribe(params => { this.identity = params.get('id') ?? ''; void this.load(); });
    if (!this.plans && !this.identity) void this.api.all('/annual-plans').then(rows => this.planOptions.set(rows)).catch(error => this.issue.set(problem(error)));
  }
  async load(cursor = ''): Promise<void> {
    const epoch = ++this.epoch; this.loading.set(true); this.issue.set(null); this.record.set(null); this.parent.set(null);
    try {
      if (this.identity) {
        const row = await this.api.get(this.endpoint + '/' + encodeURIComponent(this.identity));
        const parent = this.plans ? null : await this.api.get('/annual-plans/' + text(row, 'annual_plan_id'));
        if (epoch === this.epoch) { this.record.set(row); this.parent.set(parent); }
      } else {
        const page = await this.api.get<Page>(this.endpoint, { limit: '50', ...(cursor ? { cursor } : {}), ...(!this.plans && this.planFilter ? { annual_plan_id: this.planFilter } : {}) });
        if (epoch === this.epoch) { this.rows.set(page.items); this.next.set(page.next_cursor ?? null); this.cursor.set(cursor); }
      }
    } catch (error) { if (epoch === this.epoch) { this.rows.set([]); this.issue.set(problem(error)); } }
    finally { if (epoch === this.epoch) this.loading.set(false); }
  }
  private async periods(row?: Row): Promise<Field[]> {
    return [{ key: 'horizon_type', label: 'Horizonte', type: 'select', required: true, options: options(await this.api.all('/catalogs/horizons'), 'name', 'code'), value: row?.['horizon_type'] },
      { key: 'start_date', label: 'Inicio inclusivo', type: 'date', required: true, value: row?.['start_date'] },
      { key: 'due_date', label: 'Fin inclusivo', type: 'date', required: true, value: row?.['due_date'] }];
  }
  private open(title: string, fields: Field[], submit: (values: Row) => Promise<unknown>): void {
    this.dialog.open(Editor, { width: '640px', maxWidth: '96vw', data: { title, fields, submit } }).afterClosed().subscribe(result => {
      if (result) { this.notice.set(result === 'reload' ? 'Datos recargados. Revisa el registro antes de volver a editar.' : 'Cambio guardado.'); void this.load(); }
    });
  }
  async edit(row?: Row): Promise<void> {
    if (!this.session.has('planning:manage')) return;
    try {
      const fields: Field[] = [{ key: 'title', label: 'Titulo', required: true, max: 200, value: row?.['title'] }];
      if (!this.plans) fields.push({ key: 'description', label: 'Descripcion', type: 'textarea', max: 10000, value: row?.['description'] ?? '' });
      if (!row) {
        fields.push(...await this.periods());
        if (!this.plans) fields.push(
          { key: 'annual_plan_id', label: 'Plan', type: 'select', required: true, options: options((await this.api.all('/annual-plans')).filter(plan => plan['status'] !== 'closed'), 'title') },
          { key: 'department_id', label: 'Departamento', type: 'select', required: true, options: options(await this.api.all('/catalogs/departments')) });
      }
      this.open((row ? 'Editar ' : 'Crear ') + (this.plans ? 'plan' : 'objetivo'), fields, values => this.api.command(this.endpoint + (row ? '/' + text(row, 'id') : ''), { ...values, ...(row ? { expected_version: version(row) } : {}) }, row ? 'PATCH' : 'POST'));
    } catch (error) { this.issue.set(problem(error)); }
  }
  async period(row: Row): Promise<void> {
    try { this.open('Cambiar periodo', [...await this.periods(row), reason()], values => this.api.command(this.endpoint + '/' + text(row, 'id') + '/period-changes', { ...values, expected_version: version(row) })); }
    catch (error) { this.issue.set(problem(error)); }
  }
  status(row: Row, status: 'active' | 'closed'): void {
    this.open(status === 'active' ? 'Activar plan' : 'Cerrar plan definitivamente', [{ ...reason(), required: false }], values => this.api.command(this.endpoint + '/' + text(row, 'id') + '/status-changes', { expected_version: version(row), status, ...(values['reason'] ? { reason: values['reason'] } : {}) }));
  }
}