import { Component, inject, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, ValidatorFn, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { Row } from '../core/api';
import { problem, Problem } from '../core/problem';
import { Feedback } from './feedback';

export interface Option { value: string; label: string; disabled?: boolean; }
export interface Field {
  key: string; label: string; type?: 'text' | 'textarea' | 'date' | 'number' | 'password' | 'email' | 'select' | 'multi' | 'check';
  required?: boolean; min?: number; max?: number; pattern?: string; options?: Option[]; value?: unknown; hint?: string;
  requiredWhen?: { key: string; values: string[] };
}
export interface EditData { title: string; fields: Field[]; confirm?: string; submit: (values: Row) => Promise<unknown>; }
export function reason(): Field { return { key: 'reason', label: 'Motivo', type: 'textarea', required: true, min: 10, max: 2000 }; }
export function options(rows: Row[], label = 'name', value = 'id'): Option[] {
  return rows.map(row => ({ value: String(row[value] ?? ''), label: String(row[label] ?? row[value] ?? '') }));
}

@Component({
  standalone: true, imports: [ReactiveFormsModule, MatDialogModule, MatButtonModule, MatInputModule, MatSelectModule, MatCheckboxModule, Feedback],
  template: `<h2 mat-dialog-title>{{ data.title }}</h2><form [formGroup]="form" (ngSubmit)="save()" [attr.aria-busy]="busy()">
    <mat-dialog-content><ocote-feedback [issue]="issue()" /><div class="field-grid">
      @for (field of data.fields; track field.key) {
        @if (field.type === 'check') { <mat-checkbox [formControlName]="field.key">{{ field.label }}</mat-checkbox> }
        @else { <mat-form-field [class.wide]="field.type === 'textarea'">
          <mat-label>{{ field.label }}</mat-label>
          @if (field.type === 'select' || field.type === 'multi') {
            <mat-select [formControlName]="field.key" [multiple]="field.type === 'multi'" [required]="required(field)">
              @if (!required(field) && field.type !== 'multi') { <mat-option [value]="null">Sin departamento</mat-option> }
              @for (option of field.options; track option.value) { <mat-option [value]="option.value" [disabled]="!!option.disabled">{{ option.label }}</mat-option> }
            </mat-select>
          } @else if (field.type === 'textarea') { <textarea matInput [formControlName]="field.key" rows="3" [required]="!!field.required" [maxlength]="field.max ?? 10000"></textarea> }
          @else { <input matInput [type]="field.type ?? 'text'" [formControlName]="field.key" [required]="!!field.required"
              [attr.min]="field.type === 'number' ? field.min : null" [attr.max]="field.type === 'number' ? field.max : null"
              [attr.maxlength]="field.type !== 'number' ? field.max : null" [attr.autocomplete]="field.type === 'password' ? 'new-password' : 'off'"> }
          @if (field.hint) { <mat-hint>{{ field.hint }}</mat-hint> }
          <mat-error>Revisa {{ field.label.toLowerCase() }}{{ field.type === 'number' ? ' (numero entero)' : '' }}{{ field.min && field.type !== 'number' ? ' (minimo ' + field.min + ' caracteres)' : '' }}.</mat-error>
        </mat-form-field> }
      }
    </div>@if (form.hasError('period')) { <p role="alert">El inicio no puede ser posterior al fin del periodo.</p> }</mat-dialog-content><mat-dialog-actions align="end">
      <button mat-button type="button" [mat-dialog-close]="false" [disabled]="busy()">Cancelar</button>
      @if (issue()?.conflict) { <button mat-stroked-button type="button" [mat-dialog-close]="'reload'">Descartar cambios y recargar</button> }
      <button mat-flat-button type="submit" [disabled]="busy() || form.invalid || !!issue()?.conflict">{{ busy() ? 'Procesando...' : data.confirm ?? 'Guardar' }}</button>
    </mat-dialog-actions></form>`,
})
export class Editor {
  readonly data = inject<EditData>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<Editor>);
  readonly busy = signal(false);
  readonly issue = signal<Problem | null>(null);
  readonly form = new FormGroup<Record<string, FormControl>>({});
  constructor() {
    for (const field of this.data.fields) {
      const validators: ValidatorFn[] = [];
      if (field.required) validators.push(Validators.required);
      if (field.requiredWhen) validators.push(control => this.required(field) && !control.value ? { required: true } : null);
      if (field.type === 'number') {
        validators.push(control => control.value === null || Number.isInteger(control.value) ? null : { integer: true });
        if (field.min !== undefined) validators.push(Validators.min(field.min));
        if (field.max !== undefined) validators.push(Validators.max(field.max));
      } else {
        if (field.min !== undefined) validators.push(Validators.minLength(field.min));
        if (field.max !== undefined) validators.push(Validators.maxLength(field.max));
      }
      if (field.type === 'email') validators.push(Validators.email);
      if (field.pattern) validators.push(Validators.pattern(field.pattern));
      if (field.type === 'date') validators.push(control => {
        const value = control.value;
        if (!value) return null;
        const timestamp = Date.parse(value + 'T00:00:00Z');
        return /^\d{4}-\d{2}-\d{2}$/.test(value) && value >= '0001-01-01' && Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0,10) === value ? null : { civilDate: true };
      });
      this.form.addControl(field.key, new FormControl(field.value ?? (field.type === 'check' ? false : field.type === 'multi' ? [] : null), validators));
    }
    this.form.addValidators(group => {
      const start = group.get('start_date')?.value, due = group.get('due_date')?.value;
      return start && due && start > due ? { period: true } : null;
    });
    this.form.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => {
      for (const field of this.data.fields.filter(field => field.requiredWhen)) this.form.controls[field.key].updateValueAndValidity({ emitEvent: false });
    });
  }
  required(field: Field): boolean {
    return !!field.required || !!field.requiredWhen?.values.includes(String(this.form.get(field.requiredWhen.key)?.value));
  }
  async save(): Promise<void> {
    if (this.busy() || this.form.invalid || this.issue()?.conflict) return;
    this.busy.set(true); this.issue.set(null); this.ref.disableClose = true;
    try { await this.data.submit(this.form.getRawValue()); this.ref.close(true); }
    catch (error) { this.issue.set(problem(error)); }
    finally { this.busy.set(false); this.ref.disableClose = false; }
  }
}