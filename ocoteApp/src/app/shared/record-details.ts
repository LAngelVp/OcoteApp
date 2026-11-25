import { Component, computed, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { Row } from '../core/api';
import { instant, label } from './presentation';

interface DetailValue { text: string; tone?: 'good' | 'muted' | 'bad'; code?: boolean; date?: string; }
interface DetailField { key: string; label: string; values: DetailValue[]; }
interface DetailSection { key: string; title: string; fields: DetailField[]; }

const names: Record<string, string> = {
  id: 'Identificador', code: 'C\u00f3digo', name: 'Nombre', title: 'T\u00edtulo', description: 'Descripci\u00f3n',
  display_name: 'Nombre', email: 'Correo electr\u00f3nico', role: 'Rol', department_id: 'Departamento',
  position: 'Posici\u00f3n', kind: 'Clase', is_active: 'Estado', is_initial: 'Etapa inicial',
  requires_reason: 'Requiere motivo', requires_evidence: 'Requiere evidencia', allowed_roles: 'Roles permitidos',
  from_stage_id: 'Etapa de origen', to_stage_id: 'Etapa de destino', key: 'Par\u00e1metro', value: 'Valor',
  organization_name: 'Nombre de la organizaci\u00f3n', organization_timezone: 'Zona horaria',
  evidence_max_bytes: 'L\u00edmite de evidencia (bytes)', export_max_rows: 'L\u00edmite de exportaci\u00f3n (filas)',
  created_at: 'Fecha de creaci\u00f3n', updated_at: '\u00daltima actualizaci\u00f3n', version: 'Versi\u00f3n',
  updated_by: 'Actualizado por', actor_id: 'Actor', event_type: 'Evento', entity_type: 'Entidad',
  entity_id: 'Registro relacionado', outcome: 'Resultado', request_id: 'Referencia de solicitud',
  before_data: 'Estado anterior', after_data: 'Estado posterior', reason: 'Motivo', decision_reason: 'Motivo de la decisi\u00f3n',
  task_id: 'Tarea', subtask_id: 'Subtarea', objective_id: 'Objetivo', annual_plan_id: 'Plan',
  assignee_id: 'Responsable', stage_id: 'Etapa', priority_id: 'Prioridad', evidence_ids: 'Evidencias',
  annual_plan: 'Plan', objective: 'Objetivo', priority: 'Prioridad', status: 'Estado',
  start_date: 'Fecha de inicio', due_date: 'Compromiso vigente', original_due_date: 'Compromiso original',
  completed_at: 'Fecha de cierre', progress_percent: 'Avance (%)', pending_closure: 'Pendiente de cierre',
  punctuality_status: 'Puntualidad vigente', baseline_punctuality_status: 'Puntualidad original',
  is_overdue: 'Vencida', due_date_delta_days: 'Cambio de compromiso (d\u00edas)',
  delay_days: 'Retraso vigente (d\u00edas)', baseline_delay_days: 'Retraso original (d\u00edas)',
  requested_by: 'Solicitante', decided_by: 'Decidido por', decided_at: 'Fecha de decisi\u00f3n',
  previous_due_date: 'Compromiso anterior', proposed_due_date: 'Fecha propuesta',
  application_version: 'Versi\u00f3n de aplicaci\u00f3n', target_revision: 'Revisi\u00f3n de destino',
  source_revision: 'Revisi\u00f3n de origen', result_code: 'Resultado', started_at: 'Inicio',
  finished_at: 'Finalizaci\u00f3n', ended_at: 'Finalizaci\u00f3n', mode: 'Modo',
  horizon_type: 'Horizonte', evidence: 'Evidencias', expected_version: 'Versi\u00f3n esperada',
};
const values: Record<string, string> = {
  admin: 'Administrador', gerente: 'Gerente', lider: 'L\u00edder', colaborador: 'Colaborador',
  success: 'Correcto', denied: 'Denegado', error: 'Error', running: 'En curso',
  departments: 'Departamentos', users: 'Usuarios', workflow_stages: 'Etapas', workflow_transitions: 'Transiciones',
  priorities: 'Prioridades', horizon_types: 'Horizontes', system_settings: 'Par\u00e1metros',
  tasks: 'Tareas', subtasks: 'Subtareas', annual_plans: 'Planes', objectives: 'Objetivos',
  administration_changed: 'Cambio administrativo', task_created: 'Tarea creada',
  task_updated: 'Tarea actualizada', stage_changed: 'Cambio de etapa',
};
const rules = new Set(['is_initial', 'requires_reason', 'requires_evidence', 'allowed_roles']);
const trace = new Set(['id', 'version', 'created_at', 'updated_at', 'updated_by', 'actor_id', 'entity_id', 'request_id']);
const hidden = /password|secret|token/i;
const fieldName = (key: string): string => names[key] ?? key.replace(/_/g, ' ').replace(/^./, initial => initial.toUpperCase());
const readable = (value: string): string => values[value] ?? names[value] ?? label(value);
const isRecord = (value: unknown): value is Row => !!value && typeof value === 'object' && !Array.isArray(value);

function detailValue(key: string, value: unknown): DetailValue {
  if (value == null || typeof value === 'string' && !value.trim()) return { text: 'Sin informaci\u00f3n', tone: 'muted' };
  if (typeof value === 'boolean') return {
    text: key === 'is_active' ? value ? 'Activo' : 'Inactivo' : key === 'is_initial' && value ? 'Inicial' : value ? 'S\u00ed' : 'No',
    tone: value ? 'good' : 'muted',
  };
  if (typeof value === 'number') return { text: value.toLocaleString('es-MX', { maximumFractionDigits: 20 }) };
  const text = String(value);
  if (/_at$/.test(key)) return Number.isNaN(Date.parse(text))
    ? { text: 'Fecha no disponible', tone: 'muted' } : { text: instant(text), date: text };
  if (/_date$/.test(key) && /^\d{4}-\d{2}-\d{2}$/.test(text)) {
    const date = new Date(text + 'T00:00:00Z');
    return Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== text
      ? { text: 'Fecha no disponible', tone: 'muted' }
      : { text: new Intl.DateTimeFormat('es-MX', { dateStyle: 'long', timeZone: 'UTC' }).format(date), date: text };
  }
  if (['role', 'allowed_roles', 'kind', 'status', 'outcome'].includes(key)) return {
    text: readable(text), tone: ['failed', 'error', 'denied', 'rejected'].includes(text) ? 'bad' : ['active', 'succeeded', 'success', 'approved', 'completed'].includes(text) ? 'good' : 'muted',
  };
  return { text: ['key', 'event_type', 'entity_type', 'horizon_type', 'punctuality_status', 'baseline_punctuality_status'].includes(key) ? readable(text) : text,
    code: key === 'id' || /_ids?$/.test(key) || ['code', 'target_revision', 'source_revision', 'result_code'].includes(key) };
}

function sections(record: Row): DetailSection[] {
  const result: DetailSection[] = [];
  const visit = (row: Row, path = '', title = '') => {
    const groups = new Map<string, DetailSection>();
    const children: (() => void)[] = [];
    for (const [key, value] of Object.entries(row)) {
      if (hidden.test(key)) continue;
      const identity = path + key;
      if (isRecord(value) && Object.keys(value).length) {
        children.push(() => visit(value, identity + '.', title ? title + ' / ' + fieldName(key) : fieldName(key)));
        continue;
      }
      if (Array.isArray(value) && value.some(item => isRecord(item) || Array.isArray(item))) {
        value.forEach((item, index) => children.push(() => visit(isRecord(item) ? item : { value: item }, identity + '.' + index + '.', fieldName(key) + ' ' + (index + 1))));
        continue;
      }
      const group = title ? path : rules.has(key) ? 'rules' : trace.has(key) ? 'trace' : 'general';
      if (!groups.has(group)) groups.set(group, { key: path + group, title: title || (group === 'rules' ? 'Reglas y permisos' : group === 'trace' ? 'Fechas y trazabilidad' : 'Informaci\u00f3n general'), fields: [] });
      groups.get(group)!.fields.push({ key: identity, label: fieldName(key), values: Array.isArray(value)
        ? value.length ? value.map(item => detailValue(key, item)) : [{ text: 'Sin elementos', tone: 'muted' }]
        : [detailValue(key, isRecord(value) ? null : value)] });
    }
    result.push(...(title ? [...groups.values()] : ['general', 'rules', 'trace'].flatMap(group => groups.has(group) ? [groups.get(group)!] : [])));
    children.forEach(visitChild => visitChild());
  };
  visit(record);
  return result;
}

@Component({
  selector: 'ocote-record-details', standalone: true, imports: [MatIconModule],
  template: `@if (summary()) {
    <header class="record-summary"><mat-icon aria-hidden="true">description</mat-icon><div><h3>{{ title() }}</h3>
      @if (record()['code']; as code) { <p class="record-code">{{ code }}</p> }
    </div>@if (record()['is_active'] === true || record()['is_active'] === false) { <span class="badge" [class.good]="record()['is_active'] === true">{{ record()['is_active'] ? 'Activo' : 'Inactivo' }}</span> }</header>
  }
  @for (section of sections(); track section.key) {
    <section class="record-section"><h4>{{ section.title }}</h4><dl>
      @for (field of section.fields; track field.key) { <div class="record-field"><dt>{{ field.label }}</dt><dd>
        @for (value of field.values; track $index) {
          @if (value.date) { <time [attr.datetime]="value.date">{{ value.text }}</time> }
          @else { <span [class.badge]="!!value.tone && value.tone !== 'muted' || isFlag(field.key)" [class.good]="value.tone === 'good'" [class.bad]="value.tone === 'bad'" [class.muted-value]="value.tone === 'muted'" [class.record-code]="value.code">{{ value.text }}</span> }
        }
      </dd></div> }
    </dl></section>
  } @empty { <p class="muted-value">Sin informaci&oacute;n registrada.</p> }`,
  styles: [`
    :host { display:block; min-width:0; max-width:100%; }
    .record-summary { display:flex; flex-wrap:wrap; align-items:center; gap:12px; padding:16px; background:var(--ocote-surface-secondary); border-left:3px solid var(--ocote-secondary); }
    .record-summary > mat-icon { flex:0 0 24px; color:var(--ocote-secondary); }
    .record-summary > div { flex:1 1 160px; min-width:0; }
    .record-summary h3 { margin:0; font-size:18px; }
    .record-summary p { margin:4px 0 0; color:var(--ocote-text-secondary); }
    .record-section { padding:20px 0; border-bottom:1px solid var(--ocote-border); }
    .record-section:last-child { border-bottom:0; }
    h4 { margin:0 0 16px; font-size:15px; font-weight:650; color:var(--ocote-secondary); overflow-wrap:anywhere; }
    dl { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr)); gap:20px 28px; margin:0; }
    .record-field, dd { min-width:0; }
    dt { font-size:13px; }
    dd { display:flex; flex-wrap:wrap; align-items:baseline; gap:6px; margin:6px 0 0; font-size:15px; white-space:pre-wrap; overflow-wrap:anywhere; }
    dd > * { min-width:0; max-width:100%; overflow-wrap:anywhere; }
    .badge { display:inline-flex; align-items:center; padding:2px 8px; border:1px solid var(--ocote-border); border-radius:4px; background:var(--ocote-surface-secondary); color:var(--ocote-text-secondary); font-size:13px; font-weight:600; }
    .good { color:var(--ocote-success); }
    .bad { color:var(--ocote-danger); }
    .muted-value { color:var(--ocote-text-secondary); }
    .record-code { font-family:monospace; font-size:13px; overflow-wrap:anywhere; }
  `],
})
export class RecordDetails {
  readonly record = input.required<Row>();
  readonly summary = input(false);
  readonly sections = computed(() => sections(this.record()));
  readonly title = computed(() => {
    const row = this.record();
    for (const key of ['name', 'display_name', 'title', 'key', 'event_type', 'application_version']) {
      if (typeof row[key] === 'string' && row[key]) return ['key', 'event_type'].includes(key) ? readable(row[key] as string) : row[key] as string;
    }
    return 'Registro';
  });
  isFlag(key: string): boolean { return /(^|\.)(is_active|is_initial|requires_reason|requires_evidence|allowed_roles|role|kind|status|outcome|pending_closure|is_overdue)$/.test(key); }
}