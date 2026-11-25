import { Component, ElementRef, inject, Input, OnChanges } from '@angular/core';
import { Problem } from '../core/problem';

@Component({
  selector: 'ocote-feedback', standalone: true,
  template: `@if (issue) { <section class="problem" role="alert" tabindex="-1">
    <strong>{{ issue.message }}</strong>
    @if (issue.requestId) { <small>Referencia: {{ issue.requestId }}</small> }
  </section> }`,
})
export class Feedback implements OnChanges {
  @Input() issue: Problem | null = null;
  private readonly element = inject<ElementRef<HTMLElement>>(ElementRef);
  ngOnChanges(): void { if (this.issue) queueMicrotask(() => this.element.nativeElement.querySelector<HTMLElement>('[role="alert"]')?.focus()); }
}