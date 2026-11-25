import { Component, inject, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { Api, Row } from '../core/api';
import { Problem, problem } from '../core/problem';
import { Feedback } from './feedback';

@Component({
    selector: 'ocote-export', imports: [MatButtonModule, MatIconModule, MatMenuModule, Feedback],
    template: `<button mat-stroked-button [matMenuTriggerFor]="formats" [disabled]="disabled() || busy()"><mat-icon>download</mat-icon>{{ busy() ? 'Preparando...' : 'Exportar' }}</button>
    <mat-menu #formats="matMenu"><button mat-menu-item (click)="download('csv')"><mat-icon>table_view</mat-icon>CSV</button><button mat-menu-item (click)="download('json')"><mat-icon>data_object</mat-icon>JSON</button></mat-menu><ocote-feedback [issue]="issue()" />`,
    styles: [':host { display:block; min-width:0; max-width:100%; }']
})
export class ExportMenu {
  private readonly api = inject(Api);
  readonly path = input.required<string>();
  readonly filters = input<Row>({});
  readonly disabled = input(false);
  readonly busy = signal(false);
  readonly issue = signal<Problem | null>(null);
  async download(format: 'csv' | 'json'): Promise<void> {
    if (this.busy() || this.disabled()) return;
    this.busy.set(true); this.issue.set(null);
    try {
      const file = await this.api.exportFile(this.path(), { ...this.filters(), format });
      const url = URL.createObjectURL(file), anchor = document.createElement('a');
      anchor.href = url; anchor.download = 'ocote-' + (this.path().includes('/evaluations/') ? 'evaluation' : 'tasks') + '.' + format;
      anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { this.issue.set(problem(error)); }
    finally { this.busy.set(false); }
  }
}