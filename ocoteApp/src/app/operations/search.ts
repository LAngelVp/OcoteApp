import { Component, effect, inject, output, signal, untracked } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Api, Page, Row, text, version } from '../core/api';
import { Configuration } from '../core/configuration';
import { problem, Problem } from '../core/problem';
import { Session } from '../core/session';
import { Editor, Field, options, reason } from '../shared/editor';
import { Feedback } from '../shared/feedback';
import { Pager, Pagination } from '../shared/pager';
import { metadataFields } from './collaboration';

@Component({
  selector: 'ocote-search',
  imports: [RouterLink, MatButtonModule, MatIconModule, MatInputModule, MatSelectModule, MatTooltipModule, Feedback, Pager],
  styles: [`:host{display:block;min-width:0}section{border-bottom:1px solid var(--ocote-border);padding:16px 0 24px;margin-bottom:16px}.search-form{display:flex;flex-wrap:wrap;gap:12px;align-items:center}.term{flex:1 1 240px}.kind{width:180px;max-width:100%}.results{list-style:none;padding:0}.results li{border-bottom:1px solid var(--ocote-border);padding:12px 0;overflow-wrap:anywhere}.results p{margin:4px 0;white-space:pre-wrap}h2{font-size:1.125rem;margin:0 0 12px}.saved{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.saved mat-form-field{max-width:100%;width:320px}`],
  template: `@if (configuration.enabled('search')) { <section aria-label="Busqueda"><h2>Busqueda</h2><ocote-feedback [issue]="issue()" /><form class="search-form" (submit)="$event.preventDefault();search()"><mat-form-field class="term"><mat-label>Buscar</mat-label><input matInput [value]="query()" maxlength="200" (input)="query.set($any($event.target).value)"></mat-form-field><mat-form-field class="kind"><mat-label>Recurso</mat-label><mat-select [value]="kind()" (selectionChange)="kind.set($event.value)">@for (option of kinds; track option.value) { <mat-option [value]="option.value">{{ option.label }}</mat-option> }</mat-select></mat-form-field><button mat-icon-button type="submit" aria-label="Ejecutar busqueda" matTooltip="Buscar" [disabled]="busy()"><mat-icon>search</mat-icon></button><button mat-icon-button type="button" aria-label="Filtros de busqueda" matTooltip="Filtros" (click)="advanced()"><mat-icon>tune</mat-icon></button><button mat-icon-button type="button" aria-label="Aplicar filtro a la vista" matTooltip="Aplicar a la vista" [disabled]="kind() !== 'task'" (click)="apply.emit(filters())"><mat-icon>filter_alt</mat-icon></button>@if (configuration.enabled('saved_views')) { <button mat-icon-button type="button" aria-label="Guardar vista" matTooltip="Guardar vista" (click)="save()"><mat-icon>bookmark_add</mat-icon></button> }</form>
    @if (configuration.enabled('saved_views')) { <div class="saved"><mat-form-field><mat-label>Vistas guardadas</mat-label><mat-select [value]="selected()?.['id'] ?? ''" (selectionChange)="choose($event.value)">@for (view of views(); track view['id']) { <mat-option [value]="view['id']">{{ view['name'] }} · {{ view['scope_kind'] }}</mat-option> }</mat-select></mat-form-field>@if (selected(); as view) { @if (view['owner_id'] === session.user()?.id || session.user()?.role === 'admin') { <button mat-icon-button aria-label="Editar vista" matTooltip="Editar vista" (click)="save(view)"><mat-icon>edit</mat-icon></button><button mat-icon-button aria-label="Archivar vista" matTooltip="Archivar vista" (click)="save(view,true)"><mat-icon>archive</mat-icon></button> } }</div> }
    @if (busy()) { <p role="status">Buscando...</p> }@if (searched()) { <p role="status">{{ count() }} resultados autorizados</p><ul class="results">@for (row of rows(); track row['entity_type'] + ':' + row['id']) { <li><a [routerLink]="link(row)">{{ row['entity_type'] }} · {{ row['snippet'] }}</a></li> } @empty { <li>Sin resultados.</li> }</ul><ocote-pager [state]="pagination" [busy]="busy()" (navigate)="search($event)" (sizeChange)="resize($event)" /> }</section> }`,
})
export class Search {
  private readonly api = inject(Api);
  private readonly dialog = inject(MatDialog);
  readonly configuration = inject(Configuration);
  readonly session = inject(Session);
  readonly apply = output<Row>();
  readonly query = signal('');
  readonly kind = signal('task');
  readonly extra = signal<Row>({});
  readonly views = signal<Row[]>([]);
  readonly selected = signal<Row | null>(null);
  readonly rows = signal<Row[]>([]);
  readonly busy = signal(false);
  readonly searched = signal(false);
  readonly count = signal(0);
  readonly issue = signal<Problem | null>(null);
  readonly pagination = new Pagination();
  readonly kinds = [{ value: 'task', label: 'Tareas' }, { value: 'comment', label: 'Comentarios' },
    ...(this.session.user()?.role === 'colaborador' ? [] : [{ value: 'plan', label: 'Planes' }, { value: 'objective', label: 'Objetivos' }])];
  private epoch = 0;
  constructor() { effect(() => { if (this.configuration.enabled('saved_views')) untracked(() => void this.loadViews()); }); }
  filters(): Row { return { ...this.extra(), q: this.query(), entity_type: this.kind() }; }
  link(row: Row): string[] { return row['task_id'] ? ['/tareas', text(row, 'task_id')] : row['objective_id'] ? ['/objetivos', text(row, 'objective_id')] : ['/planes', text(row, 'id')]; }
  async loadViews(): Promise<void> { try { this.views.set(await this.api.all('/collaboration/saved-views')); } catch (error) { this.issue.set(problem(error)); } }
  async search(cursor = ''): Promise<void> {
    if (this.busy()) return;
    const epoch = ++this.epoch;
    this.busy.set(true); this.issue.set(null);
    try { const page = await this.api.command<Page & { counts: Record<string, number> }>('/collaboration/search?limit=' + this.pagination.size() + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), this.filters());
      if (epoch === this.epoch) { this.rows.set(page.items); this.count.set(Object.values(page.counts).reduce((total, count) => total + count, 0)); this.searched.set(true); this.pagination.accept(cursor, page.next_cursor); }
    } catch (error) { this.issue.set(problem(error)); } finally { this.busy.set(false); }
  }
  resize(size: number): void { if (this.pagination.resize(size)) void this.search(); }
  async choose(identity: string): Promise<void> {
    const view = this.views().find(row => row['id'] === identity); if (!view) return;
    this.selected.set(view); const filters = view['filters'] as Row;
    this.kind.set(text(filters, 'entity_type')); this.query.set(text(filters, 'q'));
    this.extra.set(Object.fromEntries(Object.entries(filters).filter(([key]) => !['q', 'entity_type'].includes(key))));
    await this.search();
  }
  async save(row?: Row, archive = false): Promise<void> {
    const role = this.session.user()?.role;
    const scopes = ['personal', ...(role === 'admin' || role === 'lider' ? ['department'] : []), ...(role === 'admin' || role === 'gerente' ? ['organization'] : [])];
    try {
    const departments = role === 'admin' && !archive ? await this.api.all('/catalogs/departments') : [];
    this.dialog.open(Editor, { width: '600px', maxWidth: '96vw', data: {
      title: archive ? 'Archivar vista' : row ? 'Editar vista' : 'Guardar vista', fields: archive ? [reason()] : [{ key: 'name', label: 'Nombre', required: true, max: 120, value: row?.['name'] }, { key: 'scope_kind', label: 'Alcance', type: 'select', required: true, value: row?.['scope_kind'], options: scopes.map(value => ({ value, label: value })) }, ...(role === 'admin' ? [{ key: 'department_id', label: 'Departamento', type: 'select', options: options(departments), value: row?.['department_id'], requiredWhen: { key: 'scope_kind', values: ['department'] } }] : []), ...(row ? [{ key: 'replace_filters', label: 'Actualizar filtros de esta vista', type: 'check' as const }] : []), reason()],
      submit: (values: Row) => this.api.command('/collaboration/saved-views/' + (row ? text(row, 'id') : crypto.randomUUID()), {
        name: values['name'] ?? row?.['name'], entity_type: row?.['entity_type'] ?? this.kind(), scope_kind: values['scope_kind'] ?? row?.['scope_kind'], department_id: (values['scope_kind'] ?? row?.['scope_kind']) === 'department' ? values['department_id'] ?? row?.['department_id'] ?? this.session.user()?.department_id : null,
        filters: row && (archive || !values['replace_filters']) ? row['filters'] : { ...this.filters(), entity_type: row?.['entity_type'] ?? this.kind() }, active: !archive, expected_version: row ? version(row) : 0, reason: values['reason'],
      }, 'PUT'),
    } }).afterClosed().subscribe(result => { if (result) { this.selected.set(null); void this.loadViews(); } });
    } catch (error) { this.issue.set(problem(error)); }
  }
  async advanced(): Promise<void> {
    try {
      const definitions = this.configuration.enabled('custom_fields') && this.session.user()?.role !== 'colaborador' ? (await this.api.all('/collaboration/custom-fields')).filter(row => row['entity_type'] === this.kind() && row['active']) : [];
      const tags = this.configuration.enabled('tags') && this.session.user()?.role !== 'colaborador' ? await this.api.all('/collaboration/tags') : [];
      this.dialog.open(Editor, { width: '600px', maxWidth: '96vw', data: { title: 'Filtros de busqueda', fields: [
        ...(tags.length ? [{ key: 'tag_ids', label: 'Etiquetas', type: 'multi', options: options(tags, 'label'), value: this.extra()['tag_ids'] }] : []),
        ...(this.kind() === 'task' && this.configuration.enabled('impediments') ? [{ key: 'blocked', label: 'Impedimentos abiertos', type: 'select', options: [{ value: 'true', label: 'Con impedimentos' }, { value: 'false', label: 'Sin impedimentos' }] }] : []),
        ...(definitions.length ? [{ key: 'definition_id', label: 'Campo', type: 'select', options: options(definitions, 'label') }] : []),
      ], submit: async (values: Row) => {
        this.extra.set({ ...(values['tag_ids'] ? { tag_ids: values['tag_ids'] } : {}), ...(values['blocked'] ? { blocked: values['blocked'] === 'true' } : {}) });
        const definition = definitions.find(row => row['id'] === values['definition_id']);
        if (definition) queueMicrotask(() => this.fieldFilter(definition));
      } } }).afterClosed().subscribe(result => { if (result) this.searched.set(false); });
    } catch (error) { this.issue.set(problem(error)); }
  }
  private fieldFilter(definition: Row): void {
    const field = metadataFields({ fields: [definition], values: [] })[0];
    const operators = ['eq', ...(['number', 'date'].includes(text(definition, 'data_type')) ? ['gte', 'lte'] : ['text', 'multi_select'].includes(text(definition, 'data_type')) ? ['contains'] : [])];
    this.dialog.open(Editor, { width: '600px', maxWidth: '96vw', data: { title: text(definition, 'label'), fields: [{ ...field, key: 'value', required: true }, { key: 'operator', label: 'Operador', type: 'select', required: true, options: operators.map(value => ({ value, label: value })) }], submit: async (values: Row) => { this.extra.update(filters => ({ ...filters, custom_fields: [{ definition_id: definition['id'], value: values['value'], operator: values['operator'] }] })); } } });
  }
}