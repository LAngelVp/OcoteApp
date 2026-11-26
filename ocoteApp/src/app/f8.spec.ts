import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { Router } from '@angular/router';
import { of, Subject } from 'rxjs';
import { EnterprisePage } from './admin/enterprise.page';
import { Api, Row } from './core/api';
import { brandingContrast, Configuration, contrast, passesAA } from './core/configuration';
import { Session } from './core/session';
import { Pager, Pagination } from './shared/pager';

describe('F8 institutional contrast', () => {
  it('uses linear sRGB and requires unrounded AA in every state', () => {
    expect(contrast('#000000', '#FFFFFF')).toBe(21);
    expect(contrast('#FFFFFF', '#FFFFFF')).toBe(1);
    expect(contrast('#777777', '#FFFFFF')).toBeLessThan(4.5);
    expect(passesAA(brandingContrast({}))).toBeTrue();
    expect(passesAA(brandingContrast({ primary: '#FFFFFF' }))).toBeFalse();
    expect(passesAA(brandingContrast({ focus: '#AAAAAA' }))).toBeFalse();
    expect(passesAA(brandingContrast({ danger: '#000000' }))).toBeFalse();
    expect(passesAA(brandingContrast({ primary: 'not a color' }))).toBeFalse();
  });
});

describe('F8 configuration contracts', () => {
  it('filters page choices from policy and resets a revoked choice to five', () => {
    const value = signal<Row | null>({ page_sizes: [5, 20] });
    const fixture = TestBed.configureTestingModule({ imports: [Pager], providers: [
      { provide: Configuration, useValue: { value } },
    ] }).createComponent(Pager);
    const state = new Pagination(), sizes: number[] = [];
    fixture.componentRef.setInput('state', state);
    fixture.componentInstance.sizeChange.subscribe(size => sizes.push(size));
    fixture.detectChanges();
    expect(fixture.componentInstance.sizes()).toEqual([5, 20]);
    state.resize(20); value.set({ page_sizes: [5] }); fixture.detectChanges();
    expect(fixture.componentInstance.sizes()).toEqual([5]);
    expect(sizes).toContain(5);
    value.set(null); fixture.detectChanges();
    expect(fixture.componentInstance.sizes()).toEqual([5]);
  });

  it('removes previously applied tokens when configuration fails', async () => {
    const configuration = TestBed.configureTestingModule({ providers: [
      { provide: Api, useValue: { get: async () => { throw Error('Synthetic unavailable'); } } },
      { provide: Session, useValue: { user: () => ({ id: 'synthetic' }) } },
      { provide: Router, useValue: { events: new Subject() } },
    ] }).inject(Configuration);
    document.documentElement.style.setProperty('--ocote-primary', '#000000');
    await configuration.reload();
    expect(configuration.value()).toBeNull();
    expect(document.documentElement.style.getPropertyValue('--ocote-primary')).toBe('');
  });

  it('shows the calendar date returned by the published API contract', async () => {
    let submit: (values: Row) => Promise<unknown> = async () => undefined;
    TestBed.configureTestingModule({ providers: [
      { provide: Configuration, useValue: {} },
      { provide: Api, useValue: { command: async () => ({ date: '2026-12-28' }) } },
      { provide: MatDialog, useValue: { open: (_component: unknown, options: { data: { submit: typeof submit } }) => {
        submit = options.data.submit; return { afterClosed: () => of(false) };
      } } },
    ] });
    const page = TestBed.runInInjectionContext(() => new EnterprisePage());
    page.calculate();
    await submit({ start_date: '2026-12-24', days: 1, mode: 'business' });
    expect(page.calculation()).toBe('Fecha resultante: 2026-12-28');
  });
});