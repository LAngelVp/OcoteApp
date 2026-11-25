import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
import { Api } from '../core/api';
import { EditData } from '../shared/editor';
import { PlatformPage } from './platform.page';

describe('F7 administrative platform', () => {
  let page: PlatformPage;
  let api: jasmine.SpyObj<Api>;
  let dialog: jasmine.SpyObj<MatDialog>;
  const instance = { id: 'synthetic', version: 3, primary_name: null, primary_contact: null, backup_name: null, backup_contact: null, custody_complete: false };
  beforeEach(async () => {
    api = jasmine.createSpyObj<Api>('Api', ['get', 'command']);
    api.get.and.callFake(async <T>(path: string): Promise<T> => (path === '/admin/health' ? { custody: instance, integrations: [], vault_available: true } : { items: [], keys: [] }) as T);
    api.command.and.resolveTo({});
    dialog = jasmine.createSpyObj<MatDialog>('MatDialog', ['open']);
    dialog.open.and.returnValue({ afterClosed: () => of(false) } as never);
    await TestBed.configureTestingModule({ imports: [PlatformPage], providers: [provideNoopAnimations(), { provide: Api, useValue: api }, { provide: MatDialog, useValue: dialog }] }).compileComponents();
    page = TestBed.runInInjectionContext(() => new PlatformPage());
  });
  const data = (dialog: jasmine.SpyObj<MatDialog>) => dialog.open.calls.mostRecent().args[1]?.data as EditData;
  it('loads health and metadata without a secret read endpoint', async () => {
    await page.load();
    expect(page.custody()?.['custody_complete']).toBeFalse();
    expect(page.secrets()).toEqual([]);
    expect(api.get.calls.allArgs().map(args => args[0])).toEqual(['/admin/health', '/admin/vault']);
  });
  it('replaces an exact secret without prefilling it', async () => {
    page.secret({ owner_id: 'synthetic-owner', purpose: 'backup', version: 2 });
    const edit = data(dialog);
    expect(edit.fields.find(field => field.key === 'value')?.value).toBeUndefined();
    await edit.submit({ value: ' exact synthetic secret ', reason: 'Synthetic replacement' });
    expect(api.command).toHaveBeenCalledWith('/admin/vault/synthetic-owner/backup', { value: ' exact synthetic secret ', reason: 'Synthetic replacement', expected_version: 2 }, 'PUT');
  });
  it('does not prefill local provider defaults', () => {
    page.configure('clamav');
    expect(data(dialog).fields.filter(field => field.key !== 'reason').every(field => field.value === undefined)).toBeTrue();
  });
  it('binds provider tests to the loaded version', async () => {
    page.test({ kind: 'clamav', version: 5 });
    api.command.and.resolveTo({ passed: false });
    await data(dialog).submit({ reason: 'Synthetic failed test' });
    expect(api.command).toHaveBeenCalledWith('/admin/integrations/clamav/test', { reason: 'Synthetic failed test', expected_version: 5 });
    expect(page.notice()).toContain('fallida');
  });
  it('retains explicit null custody instead of inventing operators', async () => {
    await page.load(); page.editCustody();
    await data(dialog).submit({ reason: 'Synthetic incomplete custody' });
    expect(api.command).toHaveBeenCalledWith('/admin/custody', { primary_name: null, primary_contact: null, backup_name: null, backup_contact: null, reason: 'Synthetic incomplete custody', expected_version: 3 }, 'PATCH');
  });
  it('reports an unavailable health request', async () => {
    api.get.and.rejectWith({ status: 503 });
    await page.load();
    expect(page.health()).toBeNull();
    expect(page.issue()).not.toBeNull();
  });
  it('renders the actual standalone template with health and all four tabs', async () => {
    const fixture = TestBed.createComponent(PlatformPage);
    fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('h1').textContent).toContain('Salud y custodia');
    expect(fixture.nativeElement.querySelectorAll('[role=tab]').length).toBe(4);
  });
});