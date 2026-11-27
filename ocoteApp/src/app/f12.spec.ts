import { HttpErrorResponse } from '@angular/common/http';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { FormControl, FormGroup } from '@angular/forms';
import { MatDialog } from '@angular/material/dialog';
import { of } from 'rxjs';
import { Api, Row } from './core/api';
import { AdvancedOperationsPage, retentionPayload } from './admin/advanced.page';
import { Configuration } from './core/configuration';
import { Session } from './core/session';
import { ExecutiveReportsPage, fileContent, importMapping, ImportsPage } from './operations/bulk.page';

describe('F12 import mapping and file bounds', () => {
  it('only accepts distinct allowlisted targets', () => {
    expect(importMapping(['Name', 'End'], { 0: 'title', 1: 'due_date' }, 'task')).toEqual({ Name: 'title', End: 'due_date' });
    for (const target of ['original_due_date', 'completed_at', 'role', 'stage_id']) expect(() => importMapping(['Name'], { 0: target }, 'task')).toThrow();
    expect(() => importMapping(['Name', 'Other'], { 0: 'title', 1: 'title' }, 'task')).toThrow();
    expect(() => importMapping(['Name'], {}, 'task')).toThrow();
  });
  it('bounds local files and keeps the selected bytes unchanged', async () => {
    const file = new File(['title\nSynthetic\n'], 'synthetic.csv', { type: 'text/csv' });
    expect(atob(await fileContent(file))).toBe('title\nSynthetic\n');
    await expectAsync(fileContent(new File(['x'], 'macro.xlsm'))).toBeRejected();
    await expectAsync(fileContent(new File([], 'empty.csv'))).toBeRejected();
    const large = new File(['x'], 'large.xlsx'); Object.defineProperty(large, 'size', { value: 10485761 });
    await expectAsync(fileContent(large)).toBeRejected();
  });
});

describe('F12 fail-closed pages', () => {
  function imports(role = 'admin', enabled = true) {
    const api = { get: jasmine.createSpy('get').and.resolveTo({ items: [], next_cursor: null }), command: jasmine.createSpy('command').and.resolveTo({}) };
    const configuration = { value: signal<Row | null>({ page_sizes: [5, 10, 20, 50] }), enabled: () => enabled };
    const fixture = TestBed.configureTestingModule({ imports: [ImportsPage], providers: [
      { provide: Api, useValue: api }, { provide: Configuration, useValue: configuration },
      { provide: Session, useValue: { user: signal({ id: 'synthetic-actor', role }), has: () => true } },
      { provide: MatDialog, useValue: { open: jasmine.createSpy('open') } },
    ] }).createComponent(ImportsPage);
    return { fixture, api };
  }
  it('does not request imports for a collaborator', async () => {
    const { fixture, api } = imports('colaborador'); fixture.detectChanges(); await fixture.whenStable();
    expect(api.get).not.toHaveBeenCalled(); expect(api.command).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('Importaciones no disponibles');
  });
  it('does not request imports when the module is disabled', async () => {
    const { fixture, api } = imports('admin', false); fixture.detectChanges(); await fixture.whenStable();
    expect(api.get).not.toHaveBeenCalled();
  });
  it('preserves mappings and blocks a second preview after409', async () => {
    const { fixture, api } = imports(); fixture.detectChanges(); await fixture.whenStable();
    const page = fixture.componentInstance;
    page.record.set({ id: 'synthetic-import', version: 2, entity_type: 'task', headers: ['Name'], state: 'previewed' });
    page.mapping = new FormGroup<Record<string, FormControl<string>>>({ 0: new FormControl('title', { nonNullable: true }) });
    page.reason.setValue('Synthetic concurrent preview');
    api.command.and.rejectWith(new HttpErrorResponse({ status: 409, error: { code: 'IMPORT_PREVIEW_STALE' } }));
    await page.preview(); await page.preview();
    expect(api.command).toHaveBeenCalledTimes(1); expect(page.issue()?.conflict).toBeTrue();
    expect(page.mapping.getRawValue()['0']).toBe('title'); expect(page.reason.value).toBe('Synthetic concurrent preview');
  });
  it('keeps executive reports closed without the required flags', async () => {
    const get = jasmine.createSpy('get');
    const fixture = TestBed.configureTestingModule({ imports: [ExecutiveReportsPage], providers: [
      { provide: Api, useValue: { get } },
      { provide: Configuration, useValue: { value: signal(null), enabled: () => false } },
      { provide: Session, useValue: { user: signal({ id: 'synthetic', role: 'lider' }), has: () => true } },
      { provide: MatDialog, useValue: { open: jasmine.createSpy('open') } },
    ] }).createComponent(ExecutiveReportsPage);
    fixture.detectChanges(); await fixture.whenStable();
    expect(get).not.toHaveBeenCalled(); expect(fixture.nativeElement.textContent).toContain('Reportes ejecutivos no disponibles');
  });
});

describe('F12 advanced operations', () => {
  it('only submits retention policy data and version, never a purge flag or path', () => {
    const values: Row = { category: 'evidence', minimum_days: 365, legal_hold: true, responsible_user_id: 'synthetic-user', approval_ref: 'synthetic approval', current_password: 'synthetic-secret', reason: 'Synthetic retention decision', purge: true, path: 'private-path' };
    const body = retentionPayload(values, { version: 4 });
    expect(body['expected_version']).toBe(4); expect(body['legal_hold']).toBeTrue();
    expect(body['purge']).toBeUndefined(); expect(body['path']).toBeUndefined();
  });
  it('uses the existing admin users endpoint for retention owners', async () => {
    const all = jasmine.createSpy('all').and.resolveTo([{ id: 'synthetic-user', display_name: 'Synthetic owner' }]);
    const get = jasmine.createSpy('get').and.resolveTo({ agent: {} });
    const open = jasmine.createSpy('open').and.returnValue({ afterClosed: () => of(false), close: () => undefined });
    const module = TestBed.configureTestingModule({ imports: [AdvancedOperationsPage], providers: [
      { provide: Api, useValue: { all, get } },
      { provide: Configuration, useValue: { value: signal(null), enabled: () => true } },
      { provide: Session, useValue: { user: signal({ id: 'synthetic', role: 'admin' }) } },
      { provide: MatDialog, useValue: { open } },
    ] });
    module.overrideComponent(AdvancedOperationsPage, { add: { providers: [
      { provide: MatDialog, useValue: { open } },
    ] } });
    const fixture = module.createComponent(AdvancedOperationsPage);
    fixture.detectChanges(); await fixture.whenStable();
    await fixture.componentInstance.retention();
    expect(all).toHaveBeenCalledOnceWith('/users'); expect(open).toHaveBeenCalled();
  });
  for (const role of ['gerente', 'lider', 'colaborador']) it('does not request operations for ' + role, async () => {
    const get = jasmine.createSpy('get'), command = jasmine.createSpy('command');
    const fixture = TestBed.configureTestingModule({ imports: [AdvancedOperationsPage], providers: [
      { provide: Api, useValue: { get, command } },
      { provide: Configuration, useValue: { value: signal<Row | null>({}), enabled: () => true } },
      { provide: Session, useValue: { user: signal({ id: 'synthetic', role }), has: () => true } },
      { provide: MatDialog, useValue: { open: jasmine.createSpy('open') } },
    ] }).createComponent(AdvancedOperationsPage);
    fixture.detectChanges(); await fixture.whenStable();
    expect(get).not.toHaveBeenCalled(); expect(command).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('Operaciones avanzadas no disponibles');
  });
});