import { Component, effect, inject, input, OnDestroy, output, signal, untracked } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Api, Page, Row, text, version } from '../core/api';
import { Configuration } from '../core/configuration';
import { Problem, problem } from '../core/problem';
import { Session } from '../core/session';
import { Editor, reason } from '../shared/editor';
import { Feedback } from '../shared/feedback';
import { Pager, Pagination } from '../shared/pager';

export function externalLinkPayload(task: Row, provider: Row, repository: Row, values: Row): Row {
  return { expected_version: version(task), integration_id: provider['id'], repository_id: repository['repository_id'], kind: values['kind'], external_id: values['external_id'], reason: values['reason'] };
}
export function externalLinkHref(row: Row): string | null {
  try { const url = new URL(text(row, 'canonical_url')); return url.protocol === 'https:' && !url.username && !url.password && !url.hash ? url.href : null; }
  catch { return null; }
}

@Component({
  selector: 'ocote-external-links', imports: [MatButtonModule, MatIconModule, MatTooltipModule, Pager, Feedback],
  styles: [`:host{display:block;min-width:0}.toolbar,.line{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.line{padding:16px 0;border-bottom:1px solid var(--ocote-border)}.line>div{min-width:0;overflow-wrap:anywhere}.meta{color:var(--ocote-text-secondary);font-size:.875rem}.actions{display:flex;gap:4px;flex-wrap:wrap}`],
  template: `@if (available()) { <section class="detail-section" aria-labelledby="external-links-title"><header class="toolbar"><h2 id="external-links-title">Trazabilidad Git</h2>@if (writable()) { <button mat-stroked-button (click)="create()" [disabled]="loading()"><mat-icon>add_link</mat-icon>Enlace verificado</button> }</header>
    <ocote-feedback [issue]="issue()" />@if (loading()) { <p role="status">Cargando trazabilidad...</p> }
    @for (link of rows(); track link['id']) { <div class="line"><div><strong>{{ link['kind'] }} · {{ link['external_id'] }}</strong><p>{{ projection(link)['title'] || projection(link)['name'] }}</p><p class="meta">Repositorio {{ link['repository_id'] }} · {{ link['deactivated_at'] ? 'Inactivo' : 'Activo' }}</p></div><div class="actions">
      @if (href(link); as destination) { <a mat-icon-button [href]="destination" target="_blank" rel="noopener noreferrer" aria-label="Abrir referencia verificada" matTooltip="Abrir referencia verificada"><mat-icon>open_in_new</mat-icon></a> }
      @if (writable() && !link['deactivated_at']) { <button mat-icon-button aria-label="Desactivar enlace" matTooltip="Desactivar enlace" (click)="deactivate(link)"><mat-icon>link_off</mat-icon></button> }
    </div></div> } @empty { @if (!loading()) { <p>Sin enlaces externos registrados.</p> } }
    <ocote-pager [state]="pagination" [busy]="loading()" (navigate)="load($event)" (sizeChange)="resize($event)" /></section> }`,
})
export class ExternalLinks implements OnDestroy {
  readonly task = input.required<Row>(); readonly refresh = output<void>();
  private readonly api = inject(Api); private readonly dialog = inject(MatDialog);
  private readonly configuration = inject(Configuration); private readonly session = inject(Session);
  readonly rows = signal<Row[]>([]); readonly loading = signal(false); readonly issue = signal<Problem | null>(null);
  readonly pagination = new Pagination(); readonly href = externalLinkHref;
  private epoch = 0; private destroyed = false; private opened?: { close: () => void };
  constructor() { effect(() => { this.task(); this.configuration.value(); this.session.user(); untracked(() => { this.opened?.close(); this.pagination.reset(); void this.load(); }); }); }
  available(): boolean { return !!this.session.user() && this.configuration.enabled('integrations') && this.configuration.enabled('devops'); }
  writable(): boolean { return this.available() && ['admin', 'lider', 'colaborador'].includes(this.session.user()?.role ?? '') && !this.task()['completed_at']; }
  projection(row: Row): Row { return row['safe_projection'] as Row ?? {}; }
  private path(task = this.task()): string { return '/tasks/' + encodeURIComponent(text(task, 'id')); }
  resize(size: number): void { if (this.pagination.resize(size)) void this.load(); }
  async load(cursor = ''): Promise<void> {
    const epoch = ++this.epoch; this.rows.set([]); this.issue.set(null); this.loading.set(true);
    try { if (!this.available()) return;
      const page = await this.api.get<Page>(this.path() + '/external-links', { limit: String(this.pagination.size()), ...(cursor ? { cursor } : {}) });
      if (epoch === this.epoch && !this.destroyed) { this.rows.set(page.items); this.pagination.accept(cursor, page.next_cursor); }
    } catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); }
    finally { if (epoch === this.epoch) this.loading.set(false); }
  }
  async create(): Promise<void> {
    if (!this.writable()) return;
    const epoch = this.epoch, task = this.task();
    try {
      const providers = await this.api.all(this.path(task) + '/external-link-providers');
      if (epoch !== this.epoch || this.destroyed) return;
      const repositories = providers.flatMap(provider => (provider['repositories'] as Row[]).map(repository => ({ provider, repository, id: text(provider, 'id') + ':' + text(repository, 'repository_id') })));
      let selected = '';
      const dialog = this.dialog.open(Editor, { width: '640px', maxWidth: '96vw', data: {
        title: 'Repositorio aprobado', fields: [{ key: 'repository', label: 'Repositorio', type: 'select', required: true, options: repositories.map(item => ({ value: item.id, label: text(item.provider, 'name') + ' · ' + text(item.repository, 'path') })) }],
        submit: async (values: Row) => { selected = String(values['repository']); },
      } }); this.opened = dialog;
      dialog.afterClosed().subscribe(result => { const item = repositories.find(item => item.id === selected); if (result === true && item && !this.destroyed && epoch === this.epoch) this.reference(task, item.provider, item.repository); });
    } catch (error) { this.issue.set(problem(error)); }
  }
  private reference(task: Row, provider: Row, repository: Row): void {
    const kinds = ['issue', provider['provider'] === 'github' ? 'pull_request' : 'merge_request', 'commit', 'branch'];
    const dialog = this.dialog.open(Editor, { width: '640px', maxWidth: '96vw', data: {
      title: 'Enlace verificado: ' + text(repository, 'path'), fields: [
        { key: 'kind', label: 'Referencia', type: 'select', required: true, options: kinds.map(value => ({ value, label: value })) },
        { key: 'external_id', label: 'ID, hash completo o rama exacta', required: true, max: 128, preserveWhitespace: true }, reason(),
      ], submit: (values: Row) => this.api.command(this.path(task) + '/external-links', externalLinkPayload(task, provider, repository, values)),
    } }); this.opened = dialog; this.finished(dialog);
  }
  deactivate(row: Row): void {
    if (!this.writable() || row['deactivated_at']) return;
    const dialog = this.dialog.open(Editor, { width: '560px', maxWidth: '96vw', data: {
      title: 'Desactivar enlace externo', fields: [reason()], submit: (values: Row) => this.api.command(this.path() + '/external-links/' + text(row, 'id') + '/deactivate', { ...values, expected_version: version(row) }),
    } }); this.opened = dialog; this.finished(dialog);
  }
  private finished(dialog: MatDialogRef<Editor>): void {
    dialog.afterClosed().subscribe(result => { if (this.destroyed) return; if (result === 'reload') this.refresh.emit(); else if (result === true) void this.load(); });
  }
  ngOnDestroy(): void { this.destroyed = true; ++this.epoch; this.opened?.close(); this.rows.set([]); }
}