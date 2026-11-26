import { Component, computed, effect, inject, input, output, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Configuration } from '../core/configuration';

export const pageSizes = [5, 10, 20, 50];

export class Pagination {
  readonly size = signal(5);
  readonly cursor = signal('');
  readonly next = signal<string | null>(null);
  private readonly trail = signal<string[]>([]);
  readonly previous = computed(() => this.trail().at(-1) ?? null);
  readonly number = computed(() => this.trail().length + 1);

  accept(cursor: string, next?: string | null): void {
    if (!cursor) this.trail.set([]);
    else if (cursor !== this.cursor()) {
      const index = this.trail().indexOf(cursor);
      this.trail.set(index < 0 ? [...this.trail(), this.cursor()] : this.trail().slice(0, index));
    }
    this.cursor.set(cursor); this.next.set(next ?? null);
  }
  resize(size: number): boolean {
    if (!pageSizes.includes(size) || size === this.size()) return false;
    this.size.set(size); this.reset(); return true;
  }
  reset(): void { this.trail.set([]); this.cursor.set(''); this.next.set(null); }
}

@Component({
    selector: 'ocote-pager',
    imports: [MatButtonModule, MatIconModule, MatSelectModule, MatTooltipModule],
    template: `<nav aria-label="Paginaci&oacute;n">
    <mat-form-field subscriptSizing="dynamic"><mat-label>Filas por p&aacute;gina</mat-label><mat-select [value]="state().size()" [disabled]="busy()" (selectionChange)="sizeChange.emit($event.value)">
      @for (size of sizes(); track size) { <mat-option [value]="size">{{ size }}</mat-option> }
    </mat-select></mat-form-field>
    <span role="status" aria-live="polite" aria-atomic="true">P&aacute;gina {{ state().number() }}</span>
    <div class="page-actions">
      <button mat-icon-button aria-label="Primera p&aacute;gina" matTooltip="Primera p&aacute;gina" [disabled]="busy() || !state().cursor()" (click)="navigate.emit('')"><mat-icon>first_page</mat-icon></button>
      <button mat-icon-button aria-label="P&aacute;gina anterior" matTooltip="P&aacute;gina anterior" [disabled]="busy() || state().previous() === null" (click)="navigate.emit(state().previous()!)"><mat-icon>chevron_left</mat-icon></button>
      <button mat-icon-button aria-label="P&aacute;gina siguiente" matTooltip="P&aacute;gina siguiente" [disabled]="busy() || !state().next()" (click)="navigate.emit(state().next()!)"><mat-icon>chevron_right</mat-icon></button>
    </div>
  </nav>`,
    styles: [`:host { display:block; min-width:0; max-width:100%; } nav { display:flex; flex-wrap:wrap; align-items:center; justify-content:flex-end; gap:12px; padding:16px 0; } mat-form-field { width:176px; max-width:100%; } nav > span { font-size:14px; } .page-actions { display:flex; flex:0 0 auto; } @media(max-width:480px) { nav { justify-content:flex-start; } }`]
})
export class Pager {
  readonly state = input.required<Pagination>();
  readonly busy = input(false);
  readonly navigate = output<string>();
  readonly sizeChange = output<number>();
  private readonly configuration = inject(Configuration);
  readonly sizes = computed(() => {
    const enabled = this.configuration.value()?.['page_sizes'];
    return Array.isArray(enabled) ? pageSizes.filter(size => enabled.includes(size)) : [5];
  });
  constructor() {
    effect(() => { if (!this.sizes().includes(this.state().size())) this.sizeChange.emit(5); });
  }
}