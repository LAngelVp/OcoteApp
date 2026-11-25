import { Component, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Api, Page, Row, text, version } from '../core/api';
import { Session } from '../core/session';
import { Problem, problem } from '../core/problem';
import { Feedback } from '../shared/feedback';
import { Editor, reason } from '../shared/editor';
import { instant, label } from '../shared/presentation';

@Component({
  standalone: true, imports: [RouterLink, MatButtonModule, MatDialogModule, MatIconModule, MatSelectModule, MatTooltipModule, Feedback],
  template: `<header class="page-heading"><div><p class="eyebrow">COMPROMISOS</p><h1>Solicitudes de fecha</h1></div><button mat-icon-button aria-label="Recargar solicitudes" matTooltip="Recargar" [disabled]="loading()" (click)="load()"><mat-icon>refresh</mat-icon></button></header>
    <ocote-feedback [issue]="issue()" />@if (notice()) { <p class="notice" role="status">{{ notice() }}</p> }@if (loading()) { <p role="status">Cargando solicitudes...</p> }
    @if (record(); as row) {
      <section class="detail-section"><h2>{{ context()?.['title'] || 'Solicitud de cambio de fecha' }}</h2><dl class="facts"><div><dt>Estado</dt><dd>{{ label(row['status']) }}</dd></div>
        <div><dt>Compromiso anterior</dt><dd>{{ row['previous_due_date'] }}</dd></div><div><dt>Fecha propuesta</dt><dd>{{ row['proposed_due_date'] }}</dd></div>
        <div><dt>Solicitante</dt><dd class="code">{{ row['requested_by'] }}</dd></div><div><dt>Registrada</dt><dd>{{ instant(row['created_at']) }}</dd></div>
        <div><dt>Version de tarea al solicitar</dt><dd>{{ row['task_version_at_request'] }}</dd></div>@if (row['subtask_id']) { <div><dt>Version de subtarea al solicitar</dt><dd>{{ row['subtask_version_at_request'] }}</dd></div> }
        <div><dt>Version de solicitud</dt><dd>{{ row['version'] }}</dd></div></dl>
        <p class="description">{{ row['reason'] }}</p>@if (row['decision_reason']) { <h3>Decision</h3><p class="description">{{ row['decision_reason'] }}</p><small>{{ instant(row['decided_at']) }}</small> }
        @if (row['status'] === 'pending') {
          @if (stale()) { <p class="problem">El recurso cambio o ya esta completado. Esta solicitud no se puede aprobar; puede rechazarse o cancelarse para presentar una nueva.</p> }
          @if (row['requested_by'] === session.user()?.id && session.has('dates:decide')) { <p>No puedes aprobar tu propia solicitud.</p> }
          <div class="actions">@if (session.has('dates:decide')) {
            @if (row['requested_by'] !== session.user()?.id) { <button mat-flat-button [disabled]="stale() || !context()" (click)="decide(row,'approve')"><mat-icon>check</mat-icon>Aprobar</button> }
            <button mat-stroked-button (click)="decide(row,'reject')"><mat-icon>close</mat-icon>Rechazar</button>
          }@if (session.has('dates:decide') || row['requested_by'] === session.user()?.id) { <button mat-stroked-button (click)="decide(row,'cancel')">Cancelar solicitud</button> }</div>
        }
        <div class="toolbar"><a mat-button [routerLink]="['/tareas',row['task_id']]">Ver tarea e historial</a><a mat-button routerLink="/solicitudes-fecha">Volver al listado</a></div>
      </section>
    } @else if (!identity) {
      <div class="filters"><mat-form-field><mat-label>Estado</mat-label><mat-select [(value)]="status" (selectionChange)="load()"><mat-option value="">Todos</mat-option>@for (state of statuses; track state) { <mat-option [value]="state">{{ label(state) }}</mat-option> }</mat-select></mat-form-field></div>
      @if (!loading()) { @if (!rows().length) { <section class="empty-state"><mat-icon>event_repeat</mat-icon><h2>Sin solicitudes</h2><p>No hay solicitudes para este alcance y filtro.</p></section> }
      @else { <div class="table-wrap" role="region" aria-label="Solicitudes de fecha" tabindex="0"><table class="data-table"><thead><tr><th scope="col">Solicitud</th><th scope="col">Anterior</th><th scope="col">Propuesta</th><th scope="col">Estado</th><th scope="col">Registro</th></tr></thead><tbody>
        @for (row of rows(); track row['id']) { <tr><td><a [routerLink]="['/solicitudes-fecha',row['id']]">Revisar {{ row['subtask_id'] ? 'subtarea' : 'tarea' }}</a><small class="code">{{ row['id'] }}</small></td><td>{{ row['previous_due_date'] }}</td><td>{{ row['proposed_due_date'] }}</td><td>{{ label(row['status']) }}</td><td>{{ instant(row['created_at']) }}</td></tr> }
      </tbody></table></div><div class="pager"><button mat-button [disabled]="!cursor()" (click)="load()">Primera pagina</button><button mat-stroked-button [disabled]="!next()" (click)="load(next()!)">Siguiente</button></div> } }
    }`,
})
export class RequestsPage implements OnInit {
  private readonly api = inject(Api);
  private readonly dialog = inject(MatDialog);
  private readonly route = inject(ActivatedRoute);
  private readonly destroy = inject(DestroyRef);
  readonly session = inject(Session);
  readonly rows = signal<Row[]>([]);
  readonly record = signal<Row | null>(null);
  readonly context = signal<Row | null>(null);
  private task: Row | null = null;
  readonly loading = signal(false);
  readonly issue = signal<Problem | null>(null);
  readonly notice = signal('');
  readonly next = signal<string | null>(null);
  readonly cursor = signal('');
  readonly statuses = ['pending','approved','rejected','cancelled'];
  readonly label = label;
  readonly instant = instant;
  identity = '';
  status = '';
  private epoch = 0;
  ngOnInit(): void { this.route.paramMap.pipe(takeUntilDestroyed(this.destroy)).subscribe(params => { this.identity = params.get('id') ?? ''; void this.load(); }); }
  stale(): boolean {
    const row = this.record(), context = this.context(), task = this.task;
    return !!row && !!context && !!task && (version(task) !== row['task_version_at_request'] || !!task['completed_at'] || !!context['completed_at'] || !!row['subtask_id'] && version(context) !== row['subtask_version_at_request']);
  }
  async load(cursor = ''): Promise<void> {
    const epoch = ++this.epoch; this.loading.set(true); this.issue.set(null); this.record.set(null); this.context.set(null); this.task = null;
    try {
      if (this.identity) {
        const row = await this.api.get('/due-date-requests/' + encodeURIComponent(this.identity));
        if (epoch !== this.epoch) return;
        this.record.set(row);
        const task = await this.api.get('/tasks/' + text(row,'task_id'));
        const context = row['subtask_id'] ? await this.api.get('/subtasks/' + text(row,'subtask_id')) : task;
        if (epoch === this.epoch) { this.context.set(context); this.task = task; }
      } else {
        const page = await this.api.get<Page>('/due-date-requests', { limit:'50',...(cursor ? { cursor } : {}),...(this.status ? { status:this.status } : {}) });
        if (epoch === this.epoch) { this.rows.set(page.items); this.next.set(page.next_cursor ?? null); this.cursor.set(cursor); }
      }
    } catch (error) { if (epoch === this.epoch) { this.rows.set([]); this.issue.set(problem(error)); } }
    finally { if (epoch === this.epoch) this.loading.set(false); }
  }
  decide(row: Row, decision: 'approve' | 'reject' | 'cancel'): void {
    this.dialog.open(Editor, { width:'560px',maxWidth:'96vw',data: {
      title: ({ approve:'Aprobar cambio de fecha', reject:'Rechazar solicitud', cancel:'Cancelar solicitud' })[decision], fields:[reason()],
      submit:(values:Row) => this.api.command('/due-date-requests/' + text(row,'id') + '/' + decision, { ...values,expected_version:version(row) }),
    } }).afterClosed().subscribe(result => { if (result) { this.notice.set(result === 'reload' ? 'Datos recargados. Revisa el recurso y sus versiones.' : 'Decision registrada.'); void this.load(); } });
  }
}