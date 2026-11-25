import { Component, inject, input, OnInit, output, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Api, Page, Row, text } from '../core/api';
import { Session } from '../core/session';
import { problem, Problem } from '../core/problem';
import { Feedback } from '../shared/feedback';
import { instant } from '../shared/presentation';

@Component({
  selector: 'ocote-evidence', standalone: true,
  imports: [MatButtonModule, MatIconModule, MatTooltipModule, Feedback],
  template: `<section class="detail-section"><header class="page-heading"><h2>Evidencias</h2><button mat-icon-button aria-label="Recargar evidencias" matTooltip="Recargar" [disabled]="busy()" (click)="load()"><mat-icon>refresh</mat-icon></button></header>
    <ocote-feedback [issue]="issue()" />@if (busy()) { <p role="status">Procesando archivo...</p> }
    @if (session.has('tasks:transition') && !task()['completed_at']) {
      @if (configured()) { <div class="toolbar"><label>Archivo (PDF, PNG o JPEG; maximo {{ limit() }} bytes)<input #picker type="file" accept="application/pdf,image/png,image/jpeg" [disabled]="busy() || !!issue()?.conflict" (change)="choose($event)"></label>
        <button mat-stroked-button [disabled]="!file() || busy() || !!issue()?.conflict" (click)="upload()"><mat-icon>upload_file</mat-icon>Adjuntar</button></div> }
      @else { <p class="notice" role="status">Almacenamiento y antivirus pendientes de configuracion del operador.</p> }
      @if (invalid()) { <p role="alert">{{ invalid() }}</p> }
      @if (issue()?.conflict) { <button mat-stroked-button [disabled]="busy()" (click)="discard()">Descartar archivo y recargar tarea</button> }
    }
    @if (!rows().length && !busy()) { <p class="muted">Sin evidencias.</p> }
    @for (row of rows(); track row['id']) { <div class="evidence-row"><div><strong>{{ row['original_name'] }}</strong><small>{{ row['size_bytes'] }} bytes · {{ instant(row['created_at']) }} · Actor {{ row['uploaded_by'] }}</small><small class="digest">SHA-256 {{ row['sha256'] }}</small></div><button mat-icon-button aria-label="Descargar evidencia" matTooltip="Descargar adjunto" [disabled]="busy()" (click)="download(row)"><mat-icon>download</mat-icon></button></div> }
    @if (next()) { <button mat-stroked-button [disabled]="busy()" (click)="load(next()!)">Mas evidencias</button> }
  </section>`,
  styles: [`.evidence-row { display:flex; align-items:center; justify-content:space-between; gap:1rem; padding:1rem 4px; border-bottom:1px solid var(--ocote-border); } .evidence-row div { min-width:0; overflow-wrap:anywhere; } small { display:block; } input { display:block; max-width:100%; margin-top:.5rem; } .digest { font-family:monospace; font-size:.75rem; }`],
})
export class Evidence implements OnInit {
  readonly task = input.required<Row>();
  readonly refresh = output<void>();
  readonly session = inject(Session);
  private readonly api = inject(Api);
  readonly rows = signal<Row[]>([]);
  readonly next = signal<string | null>(null);
  readonly issue = signal<Problem | null>(null);
  readonly invalid = signal('');
  readonly busy = signal(false);
  readonly configured = signal(false);
  readonly limit = signal(0);
  readonly file = signal<File | null>(null);
  readonly instant = instant;
  ngOnInit(): void { void this.load(); }
  async load(cursor = ''): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    try {
      const page = await this.api.get<Page & { upload_limit_bytes: number; uploads_configured: boolean }>('/tasks/' + text(this.task(), 'id') + '/evidence', { limit: '50', ...(cursor ? { cursor } : {}) });
      this.rows.set(cursor ? [...this.rows(), ...page.items] : page.items); this.next.set(page.next_cursor ?? null);
      this.limit.set(page.upload_limit_bytes); this.configured.set(page.uploads_configured);
    } catch (error) { this.issue.set(problem(error)); } finally { this.busy.set(false); }
  }
  choose(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    this.invalid.set(''); this.file.set(null);
    if (file && (!file.size || file.size > this.limit())) this.invalid.set('El archivo esta vacio o excede el limite configurado.');
    else if (file && !({ 'application/pdf': /\.pdf$/i, 'image/png': /\.png$/i, 'image/jpeg': /\.jpe?g$/i }[file.type]?.test(file.name))) this.invalid.set('Tipo y extension no admitidos.');
    else this.file.set(file);
    if (!this.file()) input.value = '';
  }
  async upload(): Promise<void> {
    const file = this.file();
    if (!file || this.busy() || this.issue()?.conflict) return;
    this.busy.set(true); this.issue.set(null);
    try { await this.api.upload(this.task(), file); this.file.set(null); this.refresh.emit(); }
    catch (error) { this.issue.set(problem(error)); } finally { this.busy.set(false); }
  }
  discard(): void { this.file.set(null); this.issue.set(null); this.refresh.emit(); }
  async download(row: Row): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    try {
      const blob = await this.api.download(text(row, 'id'));
      const url = URL.createObjectURL(blob), anchor = document.createElement('a');
      try { anchor.href = url; anchor.download = text(row, 'original_name'); anchor.click(); }
      finally { URL.revokeObjectURL(url); }
    } catch (error) { this.issue.set(problem(error)); } finally { this.busy.set(false); }
  }
}