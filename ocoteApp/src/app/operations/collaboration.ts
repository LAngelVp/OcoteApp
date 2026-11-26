import { Component, effect, inject, input, output, signal, untracked } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Api, Page, Row, text, version } from '../core/api';
import { Configuration } from '../core/configuration';
import { Problem, problem } from '../core/problem';
import { Session } from '../core/session';
import { Editor, Field, options, reason } from '../shared/editor';
import { Feedback } from '../shared/feedback';
import { instant, nested } from '../shared/presentation';

export function metadataFields(metadata: Row, creating = false, stageId?: string): Field[] {
  const values = metadata['values'] as Row[] ?? [];
  const fields = (metadata['fields'] as Row[] ?? []).filter(row => row['active']).map(row => {
    const kind = text(row, 'data_type'), constraints = row['constraints'] as Row ?? {};
    const value = values.find(value => value['definition_id'] === row['id'])?.['value'];
    const choices = row['options'] as Row[] ?? [];
    return { key: text(row, 'id'), label: text(row, 'label') + ' · ' + kind,
      required: creating && !!row['required_on_create'] || !!stageId && (row['required_stage_ids'] as string[] ?? []).includes(stageId),
      type: kind === 'boolean' ? 'check' : kind === 'number' ? 'decimal' : kind === 'date' ? 'date'
        : kind === 'select' ? 'select' : kind === 'multi_select' ? 'multi' : 'text', value,
      min: kind === 'text' ? Number(constraints['min_length'] ?? 0) : constraints['min'] as number | undefined,
      max: kind === 'text' ? Number(constraints['max_length'] ?? 2000) : kind === 'url' ? 2048 : constraints['max'] as number | undefined,
      pattern: kind === 'url' ? '^https://[^\\s]+$' : undefined,
      options: choices.map(choice => ({ value: text(choice, 'id'), label: text(choice, 'label'), disabled: !choice['is_active'] })),
    } as Field;
  });
  return fields;
}

export function metadataPayload(values: Row, fields: Field[]): Row {
  return { ...(fields.some(field => field.key !== 'tag_ids') ? { custom_fields: Object.fromEntries(fields.filter(field => field.key !== 'tag_ids'
    && values[field.key] != null && values[field.key] !== '' && (!Array.isArray(values[field.key]) || (values[field.key] as unknown[]).length > 0)).map(field => [field.key, values[field.key]])) } : {}),
    ...(fields.some(field => field.key === 'tag_ids') ? { tag_ids: values['tag_ids'] ?? [] } : {}) };
}

export function metadataChanges(values: Row, fields: Field[]): Row {
  return Object.fromEntries(fields.filter(field => field.value == null && field.type === 'check'
    || JSON.stringify(values[field.key]) !== JSON.stringify(field.value ?? (field.type === 'multi' ? [] : null)))
    .map(field => [field.key, values[field.key] === '' || Array.isArray(values[field.key]) && !(values[field.key] as unknown[]).length ? null : values[field.key]]));
}

export function commentPayload(body: unknown, selected: unknown, readers: Row[]): Row {
  const mention_ids = Array.isArray(selected) ? selected : [];
  let content = String(body ?? '');
  for (const reader of readers.filter(reader => mention_ids.includes(reader['id']))) {
    const mention = '@' + text(reader, 'display_name');
    if (!content.includes(mention)) content += '\n' + mention;
  }
  return { body: content, mention_ids };
}

export async function creationMetadata(api: Api, kind: string, department?: string): Promise<Field[]> {
  const config = await api.get('/configuration');
  const flags = config['flags'] as Row ?? {};
  if (!flags['custom_fields'] && !flags['tags']) return [];
  const schema = await api.get('/collaboration/metadata-schema/' + kind, department ? { department_id: department } : {});
  return [...metadataFields(schema, true), ...(flags['tags'] ? [{ key: 'tag_ids', label: 'Etiquetas', type: 'multi', options: options(schema['tags'] as Row[], 'label') } as Field] : [])];
}

type Metadata = Row & { fields: Row[]; values: Row[]; tags: Row[]; tag_ids: string[] };

@Component({
  selector: 'ocote-collaboration-indicators',
  imports: [MatIconModule, MatTooltipModule],
  template: `<span class="indicators">@if (metrics()['open_impediments']) { <span class="status bad"><mat-icon aria-hidden="true">block</mat-icon>{{ metrics()['open_impediments'] }} impedimentos</span> }@if (metrics()['pending_predecessors']) { <span class="status warn"><mat-icon aria-hidden="true">account_tree</mat-icon>{{ metrics()['pending_predecessors'] }} predecesoras pendientes</span> }@if (record()['template_version_id']) { <mat-icon matTooltip="Generada desde plantilla" aria-label="Generada desde plantilla">content_copy</mat-icon> }</span>`,
  styles: [`.indicators{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:.875rem}.status{display:inline-flex;gap:4px;align-items:center}.status mat-icon{width:18px;height:18px;font-size:18px}`],
})
export class CollaborationIndicators {
  readonly record = input.required<Row>();
  metrics(): Row { return nested(this.record(), 'collaboration'); }
}

@Component({
  selector: 'ocote-collaboration',
  imports: [RouterLink, MatButtonModule, MatIconModule, MatInputModule, MatTooltipModule, Feedback],
  styles: [`:host{display:block;min-width:0}section{border-bottom:1px solid var(--ocote-border);padding:24px 0}h2{font-size:1.25rem}.toolbar,.line{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}.line{padding:10px 0;border-bottom:1px solid var(--ocote-border)}.line p{margin:0;min-width:0}.thread{border-left:2px solid var(--ocote-border);padding:12px 0 12px 12px;margin:12px 0;overflow-wrap:anywhere}.body{white-space:pre-wrap;overflow-wrap:anywhere}.tags{display:flex;gap:8px;flex-wrap:wrap}.tag{display:inline-flex;align-items:center;gap:6px;color:var(--ocote-text);border:1px solid var(--ocote-border);border-radius:8px;padding:4px 8px;overflow-wrap:anywhere}.swatch{width:12px;height:12px;flex:0 0 12px;background:var(--ocote-text)}.forest{background:var(--ocote-secondary)}.rust{background:var(--ocote-primary-dark)}.danger{background:var(--ocote-danger)}.mentions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.mentions mat-form-field{max-width:100%;width:260px}dd{overflow-wrap:anywhere}button{flex-shrink:0}@media(max-width:600px){section{padding:18px 0}.thread{padding-left:8px}.toolbar{align-items:flex-start}}`],
  template: `<ocote-feedback [issue]="issue()" />@if (loading()) { <p role="status">Cargando colaboracion...</p> }
    @if (kind() === 'task' && configuration.enabled('dependencies')) { <section><header class="toolbar"><h2>Dependencias</h2>@if (manage() && !closed()) { <button mat-stroked-button (click)="dependency()"><mat-icon>add_link</mat-icon>Predecesora</button> }</header>
      @for (row of dependencies(); track row['id']) { <div class="line"><p>{{ row['active'] ? 'Activa' : 'Retirada' }} · <a [routerLink]="['/tareas',otherTask(row)]">{{ row['predecessor_task_id'] === record()['id'] ? 'Sucesora' : 'Predecesora' }} {{ otherTask(row) }}</a></p>@if (manage() && !closed() && row['active'] && row['successor_task_id'] === record()['id']) { <button mat-icon-button aria-label="Retirar dependencia" matTooltip="Retirar dependencia" (click)="dependency(row)"><mat-icon>link_off</mat-icon></button> }</div> } @empty { <p class="muted">Sin dependencias visibles.</p> }
      @if (dependencyNext()) { <button mat-button [disabled]="loading()" (click)="more('dependencies')">Mas dependencias</button> }
    </section> }
    @if (kind() === 'task' && configuration.enabled('impediments')) { <section><header class="toolbar"><h2>Impedimentos</h2>@if (canImpediment() && !closed()) { <button mat-stroked-button (click)="impediment()"><mat-icon>add</mat-icon>Abrir impedimento</button> }</header>
      @for (row of impediments(); track row['id']) { <div class="line"><div><strong>{{ row['closed_at'] ? 'Resuelto' : 'Abierto' }} · {{ row['severity'] }}</strong><p class="body">{{ row['reason'] }}</p><small>{{ instant(row['opened_at']) }}@if (row['closed_at']) { · {{ instant(row['closed_at']) }} }</small>@if (row['resolution']) { <p>{{ row['resolution'] }}</p> }</div>@if (!row['closed_at'] && !closed() && (manage() || row['owner_user_id'] === session.user()?.id)) { <button mat-icon-button aria-label="Resolver impedimento" matTooltip="Resolver" (click)="resolve(row)"><mat-icon>check_circle</mat-icon></button> }</div> } @empty { <p class="muted">Sin impedimentos.</p> }
      @if (impedimentNext()) { <button mat-button [disabled]="loading()" (click)="more('impediments')">Mas impedimentos</button> }
    </section> }
    @if (configuration.enabled('custom_fields') || configuration.enabled('tags')) { <section><header class="toolbar"><h2>Campos y etiquetas</h2>@if (manage() && !closed()) { <button mat-stroked-button (click)="editMetadata()"><mat-icon>edit</mat-icon>Editar valores</button> }</header><dl class="facts">@for (field of metadata()['fields']; track fieldId(field)) { <div><dt>{{ fieldLabel(field) }}</dt><dd>{{ fieldValue(field) }}</dd></div> }</dl><div class="tags">@for (tag of assignedTags(); track tag['id']) { <span class="tag"><span class="swatch" [class.forest]="tag['color_code'] === 'forest'" [class.rust]="tag['color_code'] === 'rust'" [class.danger]="tag['color_code'] === 'danger'"></span>{{ tag['label'] }}</span> }</div></section> }
    @if (kind() !== 'plan' && configuration.enabled('comments')) { <section><header class="toolbar"><h2>Comentarios</h2>@if (!closed()) { <button mat-stroked-button (click)="comment()"><mat-icon>add_comment</mat-icon>Comentar</button> }</header>
      @if (!closed()) { <div class="mentions"><mat-form-field><mat-label>Mencionar usuario</mat-label><input matInput [value]="mentionTerm()" maxlength="120" (input)="mentionTerm.set($any($event.target).value)"></mat-form-field><button mat-icon-button aria-label="Buscar lectores para mencionar" matTooltip="Buscar usuarios" [disabled]="!mentionTerm().trim()" (click)="findMentions()"><mat-icon>person_search</mat-icon></button>@for (user of mentionChoices(); track user['id']) { <span>{{ '@' + user['display_name'] }}</span> }</div> }
      @for (row of comments(); track row['id']) { <article class="thread"><small>{{ instant(row['created_at']) }} · Revision {{ row['current_revision'] }}</small>@if (row['parent_comment_id']) { <p class="muted">Respuesta a {{ row['parent_comment_id'] }}</p> }<p class="body">{{ row['annulled_at'] ? 'Comentario anulado' : row['body'] }}</p><div class="actions"><button mat-icon-button aria-label="Historial de comentario" matTooltip="Revisiones" (click)="showRevisions(row)"><mat-icon>history</mat-icon></button>@if (!closed()) { <button mat-icon-button aria-label="Responder comentario" matTooltip="Responder" (click)="comment(undefined,row)"><mat-icon>reply</mat-icon></button>@if (row['can_edit']) { <button mat-icon-button aria-label="Editar comentario" matTooltip="Editar" (click)="comment(row)"><mat-icon>edit</mat-icon></button><button mat-icon-button aria-label="Anular comentario" matTooltip="Anular" (click)="comment(row,undefined,true)"><mat-icon>remove_circle_outline</mat-icon></button> } }</div>
        @if (revisionComment() === row['id']) { <section aria-label="Revisiones del comentario">@if (revisionBusy()) { <p role="status">Cargando revisiones...</p> }@for (revision of revisions(); track revision['id']) { <article><small>Revision {{ revision['revision_no'] }} · {{ instant(revision['created_at']) }}@if (revision['annulment']) { · Anulacion }</small><p class="body">{{ revision['body'] }}</p><p>{{ revision['reason'] }}</p></article> }@if (revisionNext()) { <button mat-button [disabled]="revisionBusy()" (click)="showRevisions(row,true)">Mas revisiones</button> }</section> }
      </article> } @empty { <p class="muted">Sin comentarios.</p> }
      @if (commentNext()) { <button mat-button [disabled]="loading()" (click)="more('comments')">Mas comentarios</button> }
    </section> }`,
})
export class Collaboration {
  private readonly api = inject(Api);
  private readonly dialog = inject(MatDialog);
  readonly configuration = inject(Configuration);
  readonly session = inject(Session);
  readonly record = input.required<Row>();
  readonly kind = input<'plan' | 'objective' | 'task'>('task');
  readonly readonlyResource = input(false);
  readonly refresh = output<void>();
  readonly metadata = signal<Metadata>({ fields: [], values: [], tags: [], tag_ids: [] });
  readonly dependencies = signal<Row[]>([]);
  readonly impediments = signal<Row[]>([]);
  readonly comments = signal<Row[]>([]);
  readonly revisionComment = signal<string | null>(null);
  readonly revisions = signal<Row[]>([]);
  readonly revisionNext = signal<string | null>(null);
  readonly revisionBusy = signal(false);
  readonly dependencyNext = signal<string | null>(null);
  readonly impedimentNext = signal<string | null>(null);
  readonly commentNext = signal<string | null>(null);
  readonly mentionTerm = signal('');
  readonly mentionChoices = signal<Row[]>([]);
  readonly loading = signal(false);
  readonly issue = signal<Problem | null>(null);
  readonly instant = instant;
  private planVersion = 0;
  private epoch = 0;
  constructor() {
    effect(() => { this.record(); this.kind(); this.configuration.value(); untracked(() => void this.load()); });
  }
  closed(): boolean { return this.readonlyResource() || !!this.record()['completed_at'] || this.record()['status'] === 'closed'; }
  manage(): boolean { return this.kind() === 'task' ? this.session.has('tasks:manage') : this.session.has('planning:manage'); }
  canImpediment(): boolean { return this.session.user()?.role !== 'gerente'; }
  private path(suffix: string): string { return '/collaboration/' + this.kind() + '/' + text(this.record(), 'id') + '/' + suffix; }
  private taskPath(suffix: string): string { return '/tasks/' + text(this.record(), 'id') + '/' + suffix; }
  fieldId(field: unknown): string { return text(field as Row, 'id'); }
  fieldLabel(field: unknown): string { return text(field as Row, 'label'); }
  fieldValue(field: unknown): string {
    const definition = field as Row;
    const value = (this.metadata()['values'] as Row[]).find(row => row['definition_id'] === definition['id'])?.['value'];
    if (value == null) return 'Sin valor';
    if (typeof value === 'boolean') return value ? 'Si' : 'No';
    if (['select', 'multi_select'].includes(text(definition, 'data_type'))) return (Array.isArray(value) ? value : [value]).map(identity => text((definition['options'] as Row[]).find(row => row['id'] === identity) ?? {}, 'label')).join(', ');
    return String(value);
  }
  assignedTags(): Row[] { return (this.metadata()['tags'] as Row[]).filter(row => (this.metadata()['tag_ids'] as string[]).includes(text(row, 'id'))); }
  otherTask(row: Row): string { return text(row, row['predecessor_task_id'] === this.record()['id'] ? 'successor_task_id' : 'predecessor_task_id'); }
  async load(): Promise<void> {
    const epoch = ++this.epoch;
    this.loading.set(true); this.issue.set(null);
    try {
      const jobs: Promise<void>[] = [];
      if (this.configuration.enabled('custom_fields') || this.configuration.enabled('tags')) jobs.push(this.api.get<Metadata>(this.path('metadata')).then(data => { if (epoch === this.epoch) this.metadata.set(data); }));
      for (const kind of ['dependencies', 'impediments', 'comments'] as const) {
        if (this.configuration.enabled(kind) && (this.kind() === 'task' || kind === 'comments' && this.kind() === 'objective')) jobs.push(this.loadPage(kind, '', epoch));
      }
      await Promise.all(jobs);
    } catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); }
    finally { if (epoch === this.epoch) this.loading.set(false); }
  }
  private async loadPage(kind: 'dependencies' | 'impediments' | 'comments', cursor: string, epoch: number): Promise<void> {
    const page = await this.api.get<Page & { plan_version?: number }>(kind === 'comments' ? this.path(kind) : this.taskPath(kind), { limit: '5', ...(cursor ? { cursor } : {}) });
    if (epoch !== this.epoch) return;
    const rows = kind === 'comments' ? this.comments : kind === 'dependencies' ? this.dependencies : this.impediments;
    const next = kind === 'comments' ? this.commentNext : kind === 'dependencies' ? this.dependencyNext : this.impedimentNext;
    rows.set(cursor ? [...rows(), ...page.items] : page.items); next.set(page.next_cursor ?? null);
    if (page.plan_version) this.planVersion = page.plan_version;
  }
  async more(kind: 'dependencies' | 'impediments' | 'comments'): Promise<void> {
    const cursor = (kind === 'comments' ? this.commentNext : kind === 'dependencies' ? this.dependencyNext : this.impedimentNext)();
    if (!cursor || this.loading()) return;
    this.loading.set(true);
    try { await this.loadPage(kind, cursor, this.epoch); } catch (error) { this.issue.set(problem(error)); } finally { this.loading.set(false); }
  }
  private open(title: string, fields: Field[], submit: (values: Row) => Promise<unknown>): void {
    this.dialog.open(Editor, { width: '680px', maxWidth: '96vw', data: { title, fields: [...fields, reason()], submit } }).afterClosed().subscribe(result => { if (result) this.refresh.emit(); });
  }
  async dependency(row?: Row): Promise<void> {
    try {
      const predecessor = row ? await this.api.get('/tasks/' + text(row, 'predecessor_task_id')) : null;
      const candidates = predecessor ? [predecessor] : (await this.api.all('/tasks', { annual_plan_id: text(nested(this.record(), 'annual_plan'), 'id') })).filter(task => task['id'] !== this.record()['id'] && !task['completed_at']);
      this.open(row ? 'Retirar dependencia' : 'Agregar predecesora', row ? [] : [{ key: 'predecessor_task_id', label: 'Predecesora', type: 'select', required: true, options: options(candidates, 'title') }], values => {
        const selected = predecessor ?? candidates.find(task => task['id'] === values['predecessor_task_id'])!;
        return this.api.command(this.taskPath('dependencies'), { predecessor_task_id: selected['id'], expected_version: version(this.record()), expected_predecessor_version: version(selected), expected_plan_version: this.planVersion, active: !row, reason: values['reason'] }, 'PUT');
      });
    } catch (error) { this.issue.set(problem(error)); }
  }
  async impediment(): Promise<void> {
    try {
      const users = await this.api.all('/catalogs/assignees');
      this.open('Abrir impedimento', [{ key: 'owner_user_id', label: 'Responsable del impedimento', type: 'select', required: true, options: options(users, 'display_name') },
        { key: 'severity', label: 'Severidad', type: 'select', required: true, options: options(['low', 'medium', 'high', 'critical'].map(value => ({ id: value, name: value }))) },
        { key: 'kind', label: 'Tipo', type: 'select', required: true, options: options(['internal', 'external', 'resource', 'decision'].map(value => ({ id: value, name: value }))) },
        { key: 'required_area', label: 'Area requerida', max: 120 }], values => this.api.command(this.taskPath('impediments'), { ...values, required_area: values['required_area'] || null, expected_version: version(this.record()) }));
    } catch (error) { this.issue.set(problem(error)); }
  }
  resolve(row: Row): void {
    this.open('Resolver impedimento', [{ key: 'resolution', label: 'Resolucion', type: 'textarea', required: true, min: 10, max: 2000 }], values => this.api.command(this.taskPath('impediments/' + text(row, 'id') + '/resolution'), { ...values, expected_version: version(row), expected_task_version: version(this.record()) }));
  }
  editMetadata(): void {
    const metadata = this.metadata(), definitions = metadataFields(metadata, false, text(this.record(), 'stage_id'));
    const tags: Field[] = this.configuration.enabled('tags') ? [{ key: 'tag_ids', label: 'Etiquetas', type: 'multi', value: metadata['tag_ids'], options: options((metadata['tags'] as Row[]).filter(row => row['is_active']), 'label') }] : [];
    this.open('Campos y etiquetas', [...definitions, ...tags], values => {
      const custom_fields = metadataChanges(values, definitions);
      return this.api.command(this.path('metadata'), { expected_version: version(this.record()), reason: values['reason'], ...(this.configuration.enabled('custom_fields') ? { custom_fields } : {}), ...(tags.length ? { tag_ids: values['tag_ids'] } : {}) }, 'PUT');
    });
  }
  async showRevisions(row: Row, more = false): Promise<void> {
    if (this.revisionBusy()) return;
    const identity = text(row, 'id'), cursor = more ? this.revisionNext() : null, epoch = this.epoch;
    this.revisionBusy.set(true); this.issue.set(null);
    if (!more) { this.revisionComment.set(identity); this.revisions.set([]); this.revisionNext.set(null); }
    try { const page = await this.api.get<Page>(this.path('comments/' + identity + '/revisions'), { limit: '5', ...(cursor ? { cursor } : {}) });
      if (epoch === this.epoch && this.revisionComment() === identity) { this.revisions.set(more ? [...this.revisions(), ...page.items] : page.items); this.revisionNext.set(page.next_cursor ?? null); }
    } catch (error) { this.issue.set(problem(error)); } finally { this.revisionBusy.set(false); }
  }
  async findMentions(): Promise<void> {
    try { const page = await this.api.get<Page>(this.path('mentions'), { q: this.mentionTerm().trim(), limit: '5' }); this.mentionChoices.set(page.items); } catch (error) { this.issue.set(problem(error)); }
  }
  comment(row?: Row, parent?: Row, annulled = false): void {
    const readers = [...new Map([...this.mentionChoices(), ...row?.['mentions'] as Row[] ?? []].map(reader => [reader['id'], reader])).values()];
    const fields: Field[] = annulled ? [] : [{ key: 'body', label: 'Comentario', type: 'textarea', required: true, min: 1, max: 10000, value: row?.['body'] }, { key: 'mention_ids', label: 'Menciones', type: 'multi', options: options(readers, 'display_name'), value: row?.['mention_ids'] ?? [] }];
    this.open(annulled ? 'Anular comentario' : row ? 'Editar comentario' : 'Nuevo comentario', fields, values => this.api.command(this.path('comments') + (row ? '/' + text(row, 'id') : ''), {
      ...values, ...commentPayload(annulled ? row!['body'] : values['body'], annulled ? [] : values['mention_ids'], readers), parent_comment_id: row?.['parent_comment_id'] ?? parent?.['id'] ?? null,
      expected_version: row ? version(row) : 0, expected_resource_version: version(this.record()), annulled,
    }, row ? 'PUT' : 'POST'));
  }
}