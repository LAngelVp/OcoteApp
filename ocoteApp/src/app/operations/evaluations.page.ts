import { Component, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatSelectModule } from '@angular/material/select';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Api, Page, Row, text, version } from '../core/api';
import { Session } from '../core/session';
import { problem, Problem } from '../core/problem';
import { Editor, Field, options } from '../shared/editor';
import { ExportMenu } from '../shared/export-menu';
import { Feedback } from '../shared/feedback';
import { Pager, Pagination } from '../shared/pager';
import { instant, label, nested, progress } from '../shared/presentation';

@Component({
    imports: [ReactiveFormsModule, RouterLink, MatButtonModule, MatDialogModule, MatSelectModule, MatIconModule, MatTooltipModule, ExportMenu, Feedback, Pager],
    template: `<header class="page-heading"><div><p class="eyebrow">GERENCIA</p><h1>{{ identity ? 'Evaluacion departamental' : 'Evaluaciones' }}</h1></div><div class="actions">
    <button mat-icon-button aria-label="Recargar evaluaciones" matTooltip="Recargar evaluaciones" [disabled]="loading()" (click)="load()"><mat-icon>refresh</mat-icon></button>
    @if (!identity && session.has('evaluations:manage')) { <button mat-flat-button [disabled]="loading()" (click)="create()"><mat-icon>add</mat-icon>Crear evaluacion</button> }
    </div></header><ocote-feedback [issue]="issue()" />
    @if (loading()) { <p role="status">Cargando evaluaciones...</p> }
    @if (!identity) { <form class="filters" [formGroup]="form" (ngSubmit)="apply()">
      <mat-form-field><mat-label>Plan</mat-label><mat-select formControlName="annual_plan_id"><mat-option value="">Todos</mat-option>@for (row of plans(); track row['id']) { <mat-option [value]="row['id']">{{ row['title'] }}</mat-option> }</mat-select></mat-form-field>
      <mat-form-field><mat-label>Departamento</mat-label><mat-select formControlName="department_id"><mat-option value="">Alcance autorizado</mat-option>@for (row of departments(); track row['id']) { <mat-option [value]="row['id']">{{ row['name'] }}</mat-option> }</mat-select></mat-form-field>
      <mat-form-field><mat-label>Estado</mat-label><mat-select formControlName="status"><mat-option value="">Todos los permitidos</mat-option>@if (session.has('evaluations:manage')) { <mat-option value="draft">Borrador</mat-option> }<mat-option value="final">Final</mat-option></mat-select></mat-form-field>
      <button mat-flat-button type="submit" [disabled]="loading()"><mat-icon>filter_alt</mat-icon>Aplicar filtros</button>
    </form>
      @if (rows().length) { <div class="table-wrap" role="region" aria-label="Evaluaciones" tabindex="0"><table class="data-table"><thead><tr><th scope="col">Plan al corte</th><th scope="col">Departamento al corte</th><th scope="col">Periodo inclusivo</th><th scope="col">Corte</th><th scope="col">Estado</th><th scope="col">Tareas</th><th scope="col">Cierre</th><th scope="col">A tiempo original</th></tr></thead><tbody>
        @for (row of rows(); track row['id']) { <tr><th scope="row"><a [routerLink]="['/evaluaciones', row['id']]">{{ nested(nested(row,'metrics'),'annual_plan')['title'] }}</a></th><td>{{ nested(nested(row,'metrics'),'department')['name'] }}</td><td>{{ row['period_start'] }} a {{ row['period_end'] }}</td><td>{{ instant(row['snapshot_at']) }}</td><td>{{ label(row['status']) }}</td><td class="numeric">{{ nested(row,'metrics')['task_count'] }}</td><td class="numeric">{{ progress(nested(row,'metrics')['completion_rate']) }}</td><td class="numeric">{{ progress(nested(row,'metrics')['baseline_on_time_rate']) }}</td></tr> }
      </tbody></table></div> } @else if (!loading()) { <section class="empty-state"><h2>Sin evaluaciones</h2><p>No hay registros para este alcance y filtro.</p></section> }
    } @if (record(); as row) {
      <section class="detail-section"><dl class="facts">
        <div><dt>Plan al corte</dt><dd>{{ nested(nested(row,'metrics'),'annual_plan')['title'] }}</dd></div><div><dt>Horizonte del plan</dt><dd>{{ label(nested(nested(row,'metrics'),'annual_plan')['horizon_type']) }}</dd></div><div><dt>Intervalo del plan al corte</dt><dd>{{ nested(nested(row,'metrics'),'annual_plan')['start_date'] }} a {{ nested(nested(row,'metrics'),'annual_plan')['due_date'] }}</dd></div>
        <div><dt>Departamento al corte</dt><dd>{{ nested(nested(row,'metrics'),'department')['name'] }}</dd></div><div><dt>Periodo inclusivo (cohorte original)</dt><dd>{{ row['period_start'] }} a {{ row['period_end'] }}</dd></div><div><dt>Corte real</dt><dd>{{ instant(row['snapshot_at']) }}</dd></div><div><dt>Zona del corte</dt><dd>{{ row['organization_timezone'] }}</dd></div><div><dt>Formula</dt><dd>{{ row['calculation_version'] }}</dd></div>
        <div><dt>Estado</dt><dd>{{ label(row['status']) }}</dd></div><div><dt>Version</dt><dd>{{ row['version'] }}</dd></div><div><dt>Evaluador al corte</dt><dd>{{ nested(nested(row,'metrics'),'evaluator')['display_name'] }}</dd></div><div><dt>Tareas (denominador)</dt><dd>{{ nested(row,'metrics')['task_count'] }}</dd></div>
        <div><dt>Avance</dt><dd>{{ progress(nested(row,'metrics')['progress_percent']) }}</dd></div><div><dt>Cierre</dt><dd>{{ progress(nested(row,'metrics')['completion_rate']) }}</dd></div><div><dt>A tiempo original</dt><dd>{{ progress(nested(row,'metrics')['baseline_on_time_rate']) }}</dd></div><div><dt>A tiempo vigente</dt><dd>{{ progress(nested(row,'metrics')['on_time_rate']) }}</dd></div>
      </dl>@if (row['summary']) { <h2>Conclusion gerencial</h2><p class="description">{{ row['summary'] }}</p> }
      <div class="actions">@if (row['status'] === 'draft' && session.has('evaluations:manage')) {
        <button mat-stroked-button [disabled]="loading()" (click)="change(row, false)"><mat-icon>update</mat-icon>Recalcular corte</button>
        <button mat-flat-button [disabled]="loading() || !row['can_finalize']" aria-describedby="finalization-state" (click)="change(row, true)"><mat-icon>lock</mat-icon>Finalizar evaluacion</button>
      }@if (row['status'] === 'final' && session.has('exports:read')) { <ocote-export [path]="'/exports/evaluations/' + row['id']" [disabled]="loading()" /> }
      <a mat-button routerLink="/evaluaciones">Volver al listado</a></div>
      @if (row['status'] === 'draft') { <p id="finalization-state" class="muted">{{ row['finalization_reason'] === 'period_open' ? 'Periodo en curso.' : row['finalization_reason'] === 'no_data' ? 'Sin tareas en el corte.' : 'Periodo concluido y cohorte disponible.' }}</p> }
      </section><section class="detail-section"><h2>Tareas en la foto</h2>
        @if (row.items.length) { <div class="table-wrap" role="region" aria-label="Tareas en la foto de evaluacion" tabindex="0"><table class="data-table"><thead><tr><th scope="col">Tarea al corte</th><th scope="col">Objetivo y horizonte</th><th scope="col">Responsable</th><th scope="col">Etapa</th><th scope="col">Prioridad</th><th scope="col">Compromiso original</th><th scope="col">Vigente</th><th scope="col">Cierre real</th><th scope="col">Avance</th><th scope="col">Puntualidad original</th><th scope="col">Puntualidad vigente</th></tr></thead><tbody>
          @for (item of row.items; track item['id']) { <tr><th scope="row">{{ item['title'] }}</th><td>{{ nested(item,'objective')['title'] }} · {{ label(nested(item,'objective')['horizon_type']) }} · {{ nested(item,'objective')['start_date'] }} a {{ nested(item,'objective')['due_date'] }}</td><td>{{ nested(item,'assignee')['display_name'] }}</td><td>{{ nested(item,'stage')['name'] }}</td><td>{{ nested(item,'priority')['name'] }}</td><td>{{ item['original_due_date'] }}</td><td>{{ item['due_date'] }}</td><td>{{ item['completed_at'] ? instant(item['completed_at']) : 'Pendiente' }}</td><td class="numeric">{{ progress(item['progress_percent']) }}</td><td>{{ label(item['baseline_punctuality_status']) }}</td><td>{{ label(item['punctuality_status']) }}</td></tr> }
        </tbody></table></div> } @else { <p class="muted">Sin tareas en el corte.</p> }
      </section>
    }<ocote-pager [state]="pagination" [busy]="loading()" (navigate)="load($event)" (sizeChange)="resize($event)" />`,
    styles: [':host { display:block; min-width:0; } h2 { font-size:22px; } .facts dd,.description { overflow-wrap:anywhere; }']
})
export class EvaluationsPage implements OnInit {
  private readonly api = inject(Api); private readonly route = inject(ActivatedRoute); private readonly router = inject(Router); private readonly dialog = inject(MatDialog); private readonly destroy = inject(DestroyRef);
  readonly session = inject(Session); readonly loading = signal(false); readonly issue = signal<Problem | null>(null);
  readonly rows = signal<Row[]>([]); readonly record = signal<(Page & Row) | null>(null); readonly plans = signal<Row[]>([]); readonly departments = signal<Row[]>([]);
  readonly pagination = new Pagination(); readonly nested = nested; readonly label = label; readonly progress = progress; readonly instant = instant;
  readonly form = new FormGroup({ annual_plan_id: new FormControl('', { nonNullable: true }), department_id: new FormControl('', { nonNullable: true }), status: new FormControl('', { nonNullable: true }) });
  identity = ''; private epoch = 0; private applied: Record<string,string> = {};
  ngOnInit(): void {
    if (!this.session.has('evaluations:read')) return;
    this.destroy.onDestroy(() => { ++this.epoch; });
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroy)).subscribe(params => { this.identity = params.get('id') ?? ''; this.pagination.reset(); void this.load(); });
    void Promise.all([this.api.all('/annual-plans'), this.api.all('/catalogs/departments')]).then(([plans, departments]) => { this.plans.set(plans); this.departments.set(departments); }).catch(error => this.issue.set(problem(error)));
  }
  apply(): void { this.applied = Object.fromEntries(Object.entries(this.form.getRawValue()).filter(([, value]) => value !== '')); this.pagination.reset(); void this.load(); }
  resize(size: number): void { if (this.pagination.resize(size)) void this.load(); }
  async load(cursor = ''): Promise<void> {
    if (!this.session.has('evaluations:read')) return;
    const epoch = ++this.epoch; this.loading.set(true); this.issue.set(null); this.record.set(null);
    try { const page = await this.api.get<Page & Row>('/evaluations' + (this.identity ? '/' + encodeURIComponent(this.identity) : ''), { ...(!this.identity ? this.applied : {}), limit: String(this.pagination.size()), ...(cursor ? { cursor } : {}) });
      if (epoch === this.epoch) { if (this.identity) this.record.set(page); else this.rows.set(page.items); this.pagination.accept(cursor, page.next_cursor); }
    } catch (error) { if (epoch === this.epoch) { this.rows.set([]); this.issue.set(problem(error)); } } finally { if (epoch === this.epoch) this.loading.set(false); }
  }
  create(): void {
    if (!this.session.has('evaluations:manage')) return;
    const fields: Field[] = [{ key:'annual_plan_id',label:'Plan',type:'select',required:true,options:options(this.plans(),'title') },{ key:'department_id',label:'Departamento',type:'select',required:true,options:options(this.departments()) },{ key:'period_start',label:'Inicio inclusivo',type:'date',required:true },{ key:'period_end',label:'Fin inclusivo',type:'date',required:true }];
    let created = '';
    this.dialog.open(Editor, { width:'640px',maxWidth:'96vw',data:{ title:'Crear evaluacion departamental',fields,validate:(values:Row) => String(values['period_start']) > String(values['period_end']) ? 'El inicio no puede superar el fin.' : null,submit:async (values:Row) => { const result = await this.api.command('/evaluations',values); created = text(result,'id'); return result; } } }).afterClosed().subscribe(result => { if (result === true && created) void this.router.navigate(['/evaluaciones',created]); else if (result) void this.load(); });
  }
  change(row: Row, finalize: boolean): void {
    if (!this.session.has('evaluations:manage') || row['status'] !== 'draft' || finalize && !row['can_finalize']) return;
    this.dialog.open(Editor, { width:'640px',maxWidth:'96vw',data:{ title:finalize ? 'Finalizar evaluacion' : 'Recalcular corte',message:finalize ? 'Se recalculara el corte y se sellara una foto final inmutable.' : 'El nuevo corte reemplazara la foto del borrador con lo conocido al generar.',fields:finalize ? [{ key:'summary',label:'Conclusion gerencial',type:'textarea',required:true,min:10,max:4000 }] : [],submit:(values:Row) => this.api.command('/evaluations/' + text(row,'id') + (finalize ? '/finalize' : '/recalculate'), { ...values,expected_version:version(row) }) } }).afterClosed().subscribe(result => { if (result) void this.load(); });
  }
}