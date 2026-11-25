import { Component, inject, signal } from '@angular/core';
import { FormArray, FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { Api, Row, text } from '../core/api';
import { Feedback } from '../shared/feedback';
import { integerValidator, integerValue, reason, textValidator } from '../shared/editor';
import { problem, Problem } from '../core/problem';

export function stageProblem(row: Row): string | null {
  if ((row['is_initial'] || row['kind'] === 'completed') && !row['is_active']) return 'La etapa inicial y la completada deben permanecer activas.';
  if (row['is_initial'] && (row['kind'] !== 'open' || row['requires_reason'] || row['requires_evidence'])) return 'La etapa inicial debe ser abierta y no puede exigir motivo ni evidencia.';
  return null;
}
export function transitionProblem(row: Row, stages: Row[], from = 'from_stage_id', to = 'to_stage_id', identity = 'id'): string | null {
  const allowed = row['allowed_roles'];
  if (!Array.isArray(allowed) || !allowed.length || new Set(allowed).size !== allowed.length || allowed.some(role => !['admin','lider','colaborador'].includes(role)) || (row['is_active'] && !allowed.includes('admin'))) return 'Selecciona roles sin duplicados; una transicion activa debe incluir admin.';
  const source = stages.find(stage => stage[identity] === row[from]), target = stages.find(stage => stage[identity] === row[to]);
  if (!source || !target || source === target) return 'Selecciona etapas distintas de origen y destino.';
  if (source['kind'] === 'completed') return 'Una etapa completada no puede tener salidas.';
  if (row['is_active'] && (!source['is_active'] || !target['is_active'])) return 'Una transicion activa requiere ambas etapas activas.';
  return null;
}
export function workflowProblem(stages: Row[], transitions: Row[]): string | null {
  stages = stages.map(stage => ({ ...stage,code:text(stage,'code').trim() }));
  if (stages.length < 2 || stages.length > 100 || transitions.length < 1 || transitions.length > 1000) return 'El grafo requiere entre 2 y 100 etapas y entre 1 y 1000 transiciones.';
  if (new Set(stages.map(stage => stage['code'])).size !== stages.length) return 'Los codigos de las etapas deben ser unicos.';
  if (new Set(stages.map(stage => integerValue(stage['position']))).size !== stages.length) return 'Las posiciones de las etapas deben ser unicas.';
  for (const stage of stages) { const message = stageProblem(stage); if (message) return message; }
  const active = stages.filter(stage => stage['is_active']), initial = active.filter(stage => stage['is_initial']), terminal = active.filter(stage => stage['kind'] === 'completed');
  if (initial.length !== 1 || terminal.length !== 1) return 'El grafo debe tener una sola etapa inicial activa y una sola completada activa.';
  const pairs = new Set<string>();
  for (const transition of transitions) {
    const message = transitionProblem(transition, stages, 'from_code', 'to_code', 'code'); if (message) return message;
    const pair = JSON.stringify([transition['from_code'], transition['to_code']]);
    if (pairs.has(pair)) return 'No se permiten transiciones duplicadas.';
    pairs.add(pair);
  }
  const reachable = new Set([terminal[0]['code']]), pending = [terminal[0]['code']];
  while (pending.length) {
    const target = pending.pop();
    for (const transition of transitions) if (transition['is_active'] && transition['to_code'] === target && !reachable.has(transition['from_code'])) {
      reachable.add(transition['from_code']); pending.push(transition['from_code']);
    }
  }
  return active.every(stage => reachable.has(stage['code'])) ? null : 'Cada etapa activa necesita un camino a la completada.';
}

@Component({
    imports: [ReactiveFormsModule, MatDialogModule, MatButtonModule, MatIconModule, MatInputModule, MatSelectModule, MatCheckboxModule, Feedback],
    template: `<h2 mat-dialog-title>Grafo de trabajo</h2><form [formGroup]="form" (ngSubmit)="save()"><mat-dialog-content><ocote-feedback [issue]="issue()" />
    <h3>Etapas</h3>@for (group of stages.controls; track group; let index = $index) {
      <section class="workflow-row" [formGroup]="group" [attr.aria-label]="'Etapa ' + (index + 1)"><div class="field-grid">
        <mat-form-field><mat-label>Codigo</mat-label><input matInput formControlName="code" required><mat-error>Codigo requerido: minusculas y guion bajo.</mat-error></mat-form-field>
        <mat-form-field><mat-label>Nombre</mat-label><input matInput formControlName="name" required><mat-error>Nombre requerido.</mat-error></mat-form-field>
        <mat-form-field><mat-label>Clase</mat-label><mat-select formControlName="kind" required><mat-option value="open">Abierta</mat-option><mat-option value="blocked">Bloqueada</mat-option><mat-option value="completed">Completada</mat-option></mat-select><mat-error>Selecciona una clase.</mat-error></mat-form-field>
        <mat-form-field><mat-label>Posicion</mat-label><input matInput formControlName="position" type="number" min="0" max="2147483647" step="1" required><mat-error>Entero entre 0 y 2147483647.</mat-error></mat-form-field>
        <mat-checkbox formControlName="is_active">Activa</mat-checkbox><mat-checkbox formControlName="is_initial">Inicial</mat-checkbox>
        <mat-checkbox formControlName="requires_reason">Requiere motivo</mat-checkbox><mat-checkbox formControlName="requires_evidence">Requiere evidencia</mat-checkbox>
      </div>@if (!group.get('expected_version')?.value) { <button mat-button type="button" (click)="stages.removeAt(index)"><mat-icon>close</mat-icon>Quitar fila</button> }</section>
    }<button mat-stroked-button type="button" (click)="addStage()"><mat-icon>add</mat-icon>Etapa</button>
    <h3 class="detail-section">Transiciones</h3>@for (group of transitions.controls; track group; let index = $index) {
      <section class="workflow-row" [formGroup]="group" [attr.aria-label]="'Transicion ' + (index + 1)"><div class="field-grid">
        <mat-form-field><mat-label>Origen</mat-label><mat-select formControlName="from_code" required>@for (code of codes(); track code) { <mat-option [value]="code">{{ code }}</mat-option> }</mat-select><mat-error>Selecciona origen.</mat-error></mat-form-field>
        <mat-form-field><mat-label>Destino</mat-label><mat-select formControlName="to_code" required>@for (code of codes(); track code) { <mat-option [value]="code">{{ code }}</mat-option> }</mat-select><mat-error>Selecciona destino.</mat-error></mat-form-field>
        <mat-form-field><mat-label>Roles</mat-label><mat-select formControlName="allowed_roles" multiple required>@for (role of roles; track role) { <mat-option [value]="role">{{ role }}</mat-option> }</mat-select><mat-error>Selecciona roles.</mat-error></mat-form-field>
        <mat-checkbox formControlName="is_active">Activa</mat-checkbox>
      </div>@if (!group.get('expected_version')?.value) { <button mat-button type="button" (click)="transitions.removeAt(index)"><mat-icon>close</mat-icon>Quitar fila</button> }</section>
    }<button mat-stroked-button type="button" (click)="addTransition()"><mat-icon>add</mat-icon>Transicion</button>
    <mat-form-field class="detail-section"><mat-label>Motivo del cambio</mat-label><textarea matInput formControlName="reason" minlength="10" maxlength="2000" required></textarea><mat-error>Entre 10 y 2000 caracteres.</mat-error></mat-form-field>
    @if (form.getError('workflow'); as message) { <p class="problem" role="alert">{{ message }}</p> }
    </mat-dialog-content><mat-dialog-actions align="end"><button mat-button type="button" [mat-dialog-close]="false" [disabled]="busy()">Cancelar</button>
      @if (issue()?.conflict) { <button mat-stroked-button type="button" [mat-dialog-close]="'reload'">Descartar cambios y recargar</button> }
      <button mat-flat-button [disabled]="busy() || form.invalid || stages.length < 2 || transitions.length < 1 || !!issue()?.conflict">Guardar grafo</button>
    </mat-dialog-actions></form>`
})
export class WorkflowEditor {
  private readonly data = inject<{ stages: Row[]; transitions: Row[] }>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<WorkflowEditor>);
  private readonly api = inject(Api);
  readonly roles = ['admin', 'lider', 'colaborador'];
  readonly stages = new FormArray<FormGroup>([]);
  readonly transitions = new FormArray<FormGroup>([]);
  readonly form = new FormGroup({ stages: this.stages, transitions: this.transitions, reason: new FormControl('', [Validators.required, textValidator(reason())]) });
  readonly busy = signal(false);
  readonly issue = signal<Problem | null>(null);
  constructor() {
    this.data.stages.forEach(row => this.addStage(row));
    this.data.transitions.forEach(row => this.addTransition({ ...row,
      from_code: this.data.stages.find(stage => stage['id'] === row['from_stage_id'])?.['code'],
      to_code: this.data.stages.find(stage => stage['id'] === row['to_stage_id'])?.['code'],
    }));
    this.form.addValidators(() => {
      const message = workflowProblem(this.stages.getRawValue(), this.transitions.getRawValue());
      return message ? { workflow: message } : null;
    });
    this.form.updateValueAndValidity({ emitEvent: false });
  }
  codes(): string[] { return [...new Set(this.stages.getRawValue().map((row: Row) => text(row, 'code').trim()).filter(Boolean))]; }
  addStage(row: Row = {}): void {
    const existing = !!row['version'];
    this.stages.push(new FormGroup({
      code: new FormControl({ value: text(row, 'code'), disabled: existing }, [Validators.required, textValidator({ key:'code',label:'Codigo',required:true,pattern:'^[a-z][a-z0-9_]*$',max:40 })]),
      name: new FormControl(text(row, 'name'), [Validators.required, textValidator({ key:'name',label:'Nombre',required:true,max:120 })]),
      kind: new FormControl({ value: text(row, 'kind'), disabled: existing }, Validators.required),
      position: new FormControl(integerValue(row['position'] ?? null), [Validators.required, Validators.min(0), Validators.max(2147483647), integerValidator]),
      is_active: new FormControl(!!row['is_active']), is_initial: new FormControl({ value: !!row['is_initial'], disabled: existing }),
      requires_reason: new FormControl(!!row['requires_reason']), requires_evidence: new FormControl(!!row['requires_evidence']),
      expected_version: new FormControl(row['version'] ?? null),
    }));
  }
  addTransition(row: Row = {}): void {
    this.transitions.push(new FormGroup({
      from_code: new FormControl({ value: text(row, 'from_code'), disabled: !!row['version'] }, Validators.required),
      to_code: new FormControl({ value: text(row, 'to_code'), disabled: !!row['version'] }, Validators.required),
      allowed_roles: new FormControl(row['allowed_roles'] ?? [], Validators.required),
      is_active: new FormControl(!!row['is_active']), expected_version: new FormControl(row['version'] ?? null),
    }));
  }
  async save(): Promise<void> {
    if (this.form.invalid || this.busy() || this.issue()?.conflict || this.stages.length < 2 || !this.transitions.length) return;
    this.busy.set(true); this.issue.set(null); this.ref.disableClose = true;
    const values = this.form.getRawValue();
    try {
      const currentReason = values.reason!.trim();
      await this.api.command('/workflow', { stages: values.stages.map((row: Row) => ({ ...row, code:text(row,'code').trim(),name:text(row,'name').trim(),position: integerValue(row['position']), reason: currentReason })), transitions: values.transitions, reason: currentReason });
      this.ref.close(true);
    } catch (error) { this.issue.set(problem(error)); }
    finally { this.busy.set(false); this.ref.disableClose = false; }
  }
}