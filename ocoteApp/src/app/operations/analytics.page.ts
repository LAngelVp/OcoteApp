import { Component, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { NgxEchartsDirective, provideEchartsCore } from 'ngx-echarts';
import * as echarts from 'echarts/core';
import type { EChartsOption } from 'echarts';
import { BarChart, LineChart } from 'echarts/charts';
import { AriaComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { Api, Page, Row, text } from '../core/api';
import { Session } from '../core/session';
import { problem, Problem } from '../core/problem';
import { Feedback } from '../shared/feedback';
import { Pager, Pagination } from '../shared/pager';
import { ExportMenu } from '../shared/export-menu';
import { instant, label, progress } from '../shared/presentation';

echarts.use([BarChart, LineChart, AriaComponent, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);
interface Report extends Page { snapshot_at: string; organization_timezone: string; metrics?: Row; filters: Row; series?: Row[]; }

@Component({
  standalone: true,
  imports: [ReactiveFormsModule, MatButtonModule, MatFormFieldModule, MatInputModule, MatSelectModule, MatIconModule, MatTooltipModule, NgxEchartsDirective, Feedback, Pager, ExportMenu],
  providers: [provideEchartsCore({ echarts })],
  template: `<header class="page-heading"><div><p class="eyebrow">MEDICION</p><h1>Analitica</h1></div><div class="actions">
    <button mat-icon-button aria-label="Recargar analitica" matTooltip="Recargar analitica" [disabled]="loading()" (click)="apply()"><mat-icon>refresh</mat-icon></button>
    @if (session.has('exports:read')) { <ocote-export path="/exports/tasks" [filters]="applied()" [disabled]="loading()" /> }
    </div></header><ocote-feedback [issue]="issue()" />
    <form class="filters" [formGroup]="form" (ngSubmit)="apply()">
      <mat-form-field><mat-label>Plan</mat-label><mat-select formControlName="annual_plan_id"><mat-option value="">Todos</mat-option>@for (row of plans(); track row['id']) { <mat-option [value]="row['id']">{{ row['title'] }}</mat-option> }</mat-select></mat-form-field>
      <mat-form-field><mat-label>Departamento</mat-label><mat-select formControlName="department_id"><mat-option value="">Alcance autorizado</mat-option>@for (row of departments(); track row['id']) { <mat-option [value]="row['id']">{{ row['name'] }}</mat-option> }</mat-select></mat-form-field>
      <mat-form-field><mat-label>Responsable</mat-label><mat-select formControlName="assignee_id"><mat-option value="">Todos</mat-option>@for (row of people(); track row['id']) { <mat-option [value]="row['id']">{{ row['display_name'] }}</mat-option> }</mat-select></mat-form-field>
      <mat-form-field><mat-label>Compromiso original desde</mat-label><input matInput type="date" formControlName="period_start"></mat-form-field>
      <mat-form-field><mat-label>Compromiso original hasta</mat-label><input matInput type="date" formControlName="period_end"></mat-form-field>
      <mat-form-field><mat-label>Clase de etapa</mat-label><mat-select formControlName="status"><mat-option value="">Todas</mat-option>@for (status of ['open','blocked','completed']; track status) { <mat-option [value]="status">{{ label(status) }}</mat-option> }</mat-select></mat-form-field>
      <mat-form-field><mat-label>Puntualidad vigente</mat-label><mat-select formControlName="punctuality_status"><mat-option value="">Todas</mat-option>@for (status of ['on_time','late','pending','overdue']; track status) { <mat-option [value]="status">{{ label(status) }}</mat-option> }</mat-select></mat-form-field>
      <button mat-flat-button type="submit" [disabled]="loading()"><mat-icon>filter_alt</mat-icon>Aplicar filtros</button><button mat-icon-button type="button" aria-label="Limpiar filtros" matTooltip="Limpiar filtros" [disabled]="loading()" (click)="clear()"><mat-icon>filter_alt_off</mat-icon></button>
    </form>@if (form.hasError('period')) { <p role="alert">Indica ambas fechas en orden inclusivo.</p> }
    @if (loading()) { <p role="status">Cargando analitica...</p> }
    @if (metrics(); as totals) { <section class="detail-section" aria-label="Resumen de cohorte"><dl class="facts">
      <div><dt>Tareas (denominador)</dt><dd>{{ totals['task_count'] }}</dd></div><div><dt>Avance</dt><dd>{{ progress(totals['progress_percent']) }}</dd></div>
      <div><dt>Tasa de cierre</dt><dd>{{ progress(totals['completion_rate']) }}</dd></div><div><dt>A tiempo original</dt><dd>{{ progress(totals['baseline_on_time_rate']) }}</dd></div><div><dt>A tiempo vigente</dt><dd>{{ progress(totals['on_time_rate']) }}</dd></div>
      <div><dt>Bloqueadas</dt><dd>{{ totals['blocked_count'] }}</dd></div><div><dt>Pendientes de cierre</dt><dd>{{ totals['pending_closure_count'] }}</dd></div><div><dt>Tareas reprogramadas</dt><dd>{{ totals['rescheduled_count'] }}</dd></div><div><dt>Cambios de compromiso</dt><dd>{{ totals['due_date_change_count'] }}</dd></div>
      <div><dt>Retraso medio vigente (dias)</dt><dd>{{ decimal(totals['average_delay_days']) }}</dd></div><div><dt>Retraso medio original (dias)</dt><dd>{{ decimal(totals['average_baseline_delay_days']) }}</dd></div><div><dt>Variacion media de compromiso (dias)</dt><dd>{{ decimal(totals['average_due_date_delta_days']) }}</dd></div>
    </dl><p class="muted">{{ context() }}</p></section> }
    @for (panel of panels; track panel.kind) { <section class="report-section"><h2>{{ panel.title }}</h2>
      @if (panel.report(); as report) { <p class="muted">Corte: {{ instant(report.snapshot_at) }} · {{ report.organization_timezone }}</p>
        @if (report.items.length) { <div echarts class="report-chart" [options]="panel.chart()" [autoResize]="true" role="img" [attr.aria-label]="panel.title + ': tasas sobre todas las tareas de la cohorte'"></div>
          <div class="table-wrap" role="region" [attr.aria-label]="panel.title" tabindex="0"><table class="data-table"><thead><tr><th scope="col">{{ panel.kind === 'summary' ? 'Departamento' : 'Mes original' }}</th><th scope="col">Tareas</th><th scope="col">Avance</th><th scope="col">Cierre</th><th scope="col">A tiempo original</th><th scope="col">A tiempo vigente</th><th scope="col">Bloqueadas</th><th scope="col">Reprogramadas</th><th scope="col">Retraso vigente (dias)</th><th scope="col">Retraso original (dias)</th></tr></thead><tbody>
            @for (row of report.items; track rowKey(row)) { <tr><th scope="row">{{ row[panel.key] }}</th><td class="numeric">{{ row['task_count'] }}</td><td class="numeric">{{ progress(row['progress_percent']) }}</td><td class="numeric">{{ progress(row['completion_rate']) }}</td><td class="numeric">{{ progress(row['baseline_on_time_rate']) }}</td><td class="numeric">{{ progress(row['on_time_rate']) }}</td><td class="numeric">{{ row['blocked_count'] }}</td><td class="numeric">{{ row['rescheduled_count'] }}</td><td class="numeric">{{ decimal(row['average_delay_days']) }}</td><td class="numeric">{{ decimal(row['average_baseline_delay_days']) }}</td></tr> }
          </tbody></table></div>
        } @else if (!loading()) { <p class="empty-state">Sin datos para esta cohorte.</p> }
      }<ocote-pager [state]="panel.pagination" [busy]="loading()" (navigate)="load(panel.kind, $event)" (sizeChange)="resize(panel.kind, $event)" />
    </section> }`,
  styles: [':host { display:block; min-width:0; } .report-section { padding:24px 0; border-top:1px solid var(--ocote-border); min-width:0; } .report-section h2 { font-size:22px; } .report-chart { width:100%; max-width:100%; min-width:0; height:320px; } .muted { overflow-wrap:anywhere; }'],
})
export class AnalyticsPage implements OnInit {
  private readonly api = inject(Api);
  private readonly destroy = inject(DestroyRef);
  readonly session = inject(Session);
  readonly plans = signal<Row[]>([]); readonly departments = signal<Row[]>([]); readonly people = signal<Row[]>([]);
  readonly loading = signal(false); readonly issue = signal<Problem | null>(null); readonly metrics = signal<Row | null>(null);
  readonly applied = signal<Record<string, string>>({}); readonly context = signal('');
  readonly form = new FormGroup({ annual_plan_id: new FormControl('', { nonNullable: true }), department_id: new FormControl('', { nonNullable: true }), assignee_id: new FormControl('', { nonNullable: true }), period_start: new FormControl('', { nonNullable: true }), period_end: new FormControl('', { nonNullable: true }), status: new FormControl('', { nonNullable: true }), punctuality_status: new FormControl('', { nonNullable: true }) }, { validators: group => { const start = group.get('period_start')?.value, end = group.get('period_end')?.value; return (!!start !== !!end || start && start > end) ? { period: true } : null; } });
  readonly panels = [
    { kind: 'summary' as const, title: 'Comparacion departamental', key: 'name', pagination: new Pagination(), report: signal<Report | null>(null), chart: signal<EChartsOption>({}) },
    { kind: 'series' as const, title: 'Tendencia mensual', key: 'month', pagination: new Pagination(), report: signal<Report | null>(null), chart: signal<EChartsOption>({}) },
  ];
  readonly instant = instant; readonly label = label; readonly progress = progress;
  readonly rowKey = (row: Row): string => text(row, 'id') || text(row, 'month');
  readonly decimal = (value: unknown): string => typeof value === 'number' ? value.toLocaleString('es-MX', { maximumFractionDigits: 2 }) : 'Sin datos';
  private epoch = 0;
  ngOnInit(): void {
    if (!this.session.has('analytics:read')) return;
    this.destroy.onDestroy(() => { ++this.epoch; });
    void Promise.all([this.api.all('/annual-plans'), this.api.all('/catalogs/departments'), this.api.all('/catalogs/assignees')]).then(([plans, departments, people]) => { this.plans.set(plans); this.departments.set(departments); this.people.set(people); }).catch(error => this.issue.set(problem(error)));
    void this.load();
  }
  apply(): void { if (this.form.invalid) return; this.applied.set(Object.fromEntries(Object.entries(this.form.getRawValue()).filter(([, value]) => value !== ''))); this.panels.forEach(panel => panel.pagination.reset()); void this.load(); }
  clear(): void { this.form.reset(); this.apply(); }
  resize(kind: string, size: number): void { const panel = this.panels.find(panel => panel.kind === kind)!; if (panel.pagination.resize(size)) void this.load(kind); }
  async load(kind = '', cursor = ''): Promise<void> {
    if (!this.session.has('analytics:read')) return;
    const epoch = ++this.epoch; this.loading.set(true); this.issue.set(null);
    const cursors = this.panels.map(panel => panel.kind === kind ? cursor : panel.pagination.cursor());
    try {
      const reports = await Promise.all(this.panels.map((panel, index) => this.api.get<Report>('/analytics/' + panel.kind, { ...this.applied(), limit: String(panel.pagination.size()), ...(cursors[index] ? { cursor: cursors[index] } : {}) })));
      if (epoch !== this.epoch) return;
      reports.forEach((report, index) => { const panel = this.panels[index]; panel.report.set(report); panel.pagination.accept(cursors[index], report.next_cursor); panel.chart.set(this.chart(report, panel.kind)); });
      this.metrics.set(reports[0].metrics ?? {});
      const filters = reports[0].filters;
      this.context.set('Cohorte por compromiso original: ' + (filters['period_start'] ?? 'sin limite inicial') + ' a ' + (filters['period_end'] ?? 'sin limite final') + ' · Plan: ' + (filters['annual_plan_id'] ?? 'todos') + ' · Departamento: ' + (filters['department_id'] ?? 'global autorizado') + ' · Responsable: ' + (filters['assignee_id'] ?? 'todos') + ' · Etapa: ' + label(filters['status'] ?? 'todas') + ' · Puntualidad: ' + label(filters['punctuality_status'] ?? 'todas'));
    } catch (error) { if (epoch === this.epoch) { this.issue.set(problem(error)); this.metrics.set(null); this.panels.forEach(panel => panel.report.set(null)); } }
    finally { if (epoch === this.epoch) this.loading.set(false); }
  }
  private chart(report: Report, kind: string): EChartsOption {
    const rows = kind === 'series' ? report.series ?? report.items : report.items;
    const styles = getComputedStyle(document.documentElement);
    return { animation: false, aria: { enabled: true, decal: { show: true } }, color: ['--ocote-primary', '--ocote-secondary', '--ocote-series-contrast'].map(token => styles.getPropertyValue(token).trim()), tooltip: { trigger: 'axis', renderMode: 'richText' }, legend: { top: 0, textStyle: { fontFamily: 'Source Sans 3', fontSize: 12 } }, grid: { top: 64, left: 48, right: 12, bottom: 80 }, xAxis: { type: 'category', data: rows.map(row => text(row, kind === 'series' ? 'month' : 'name')), axisLabel: { rotate: 35, width: 90, overflow: 'truncate' } }, yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } }, series: [['Cierre', 'completion_rate'], ['A tiempo original', 'baseline_on_time_rate'], ['A tiempo vigente', 'on_time_rate']].map(([name, key]) => ({ name, type: kind === 'series' ? 'line' as const : 'bar' as const, data: rows.map(row => typeof row[key] === 'number' ? Number(row[key]) : null), connectNulls: false, emphasis: { focus: 'series' as const } })) };
  }
}