import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { MatSelect } from '@angular/material/select';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { Router } from '@angular/router';
import { localPasswordValid, SetupPage } from './setup.page';

describe('First-run setup', () => {
  let page: SetupPage;
  let http: HttpTestingController;
  let router: jasmine.SpyObj<Router>;
  beforeEach(() => {
    router = jasmine.createSpyObj('Router', ['navigateByUrl']); router.navigateByUrl.and.resolveTo(true);
    TestBed.configureTestingModule({ imports: [SetupPage], providers: [provideHttpClient(), provideHttpClientTesting(), provideNoopAnimations(), { provide: Router, useValue: router }] });
    const fixture = TestBed.createComponent(SetupPage); page = fixture.componentInstance; http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => { http.verify(); });
  function credentials() { page.localAvailable.set(true); page.connection.patchValue({ postgres_password: 'Synthetic-Postgres-2026!', runtime_password: 'Synthetic-Runtime-2026!', migrator_password: 'Synthetic-Migrator-2026!' }); }
  it('validates integrated local settings without manual SQL roles or host fields', async () => {
    credentials(); const pending = page.test(); const request = http.expectOne('/api/v1/setup/local-checks');
    expect(request.request.body.database).toBe('ocoteAppDatabase'); expect(request.request.body.port).toBe(5432);
    expect(request.request.body.data_directory).toBe('postgres-data'); expect(request.request.body.host).toBeUndefined();
    request.flush({ portable_verified: true }); await pending; expect(page.step()).toBe(2); expect(page.connection.controls.postgres_password.value).toBe(''); expect(page.connection.controls.runtime_password.value).toBe('');
  });
  it('requires verify-full and CA for external PostgreSQL', async () => {
    credentials(); page.connection.patchValue({ mode: 'managed', host: 'pg.example.invalid', ca_pem: 'synthetic public CA' });
    const pending = page.test(); const request = http.expectOne('/api/v1/setup/connection-tests');
    expect(request.request.body.sslmode).toBe('verify-full'); expect(request.request.body.ca_pem).toBe('synthetic public CA');
    expect(request.request.body.postgres_password).toBeUndefined(); expect(request.request.body.data_directory).toBeUndefined();
    request.flush({ test_id: 'b'.repeat(32) }); await pending; expect(page.step()).toBe(2);
  });
  it('keeps unavailable database blocked from installation', async () => {
    credentials(); const pending = page.test(); http.expectOne('/api/v1/setup/local-checks').flush({ code: 'SETUP_LOCAL_PORT_IN_USE', request_id: 'synthetic-request' }, { status: 409, statusText: 'Conflict' });
    await pending; expect(page.step()).toBe(0); expect(page.issue()?.requestId).toBe('synthetic-request'); await page.install(); http.expectNone('/api/v1/setup/local-install');
  });
  it('redirects sealed instances and disables irreversible resubmission', async () => {
    const pending = page.ngOnInit(); http.expectOne('/api/v1/setup/status').flush({ code: 'SETUP_SEALED' }, { status: 403, statusText: 'Forbidden' });
    await pending; expect(page.blocked()).toBeTrue(); expect(router.navigateByUrl).toHaveBeenCalledWith('/login', { replaceUrl: true });
    await page.test(); http.expectNone('/api/v1/setup/connection-tests'); http.expectNone('/api/v1/setup/local-checks');
  });
  it('does not send external secrets without CA', async () => {
    credentials(); page.connection.controls.mode.setValue('managed'); await page.test(); http.expectNone('/api/v1/setup/connection-tests'); expect(page.issue()).not.toBeNull();
  });
  it('moves the rendered linear stepper after successful pairing', async () => {
    const fixture = TestBed.createComponent(SetupPage);
    const component = fixture.componentInstance;
    fixture.detectChanges();
    http.expectOne('/api/v1/setup/status').flush({ code: 'SETUP_CAPABILITY_INVALID' }, { status: 403, statusText: 'Forbidden' });
    component.pairing.controls.code.setValue('synthetic-capability');
    const pending = component.pair();
    http.expectOne('/api/v1/setup/pair').flush({ session_code: 'synthetic-session', local_portable_available: true }); await pending;
    fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[aria-current="step"]').textContent).toContain('PostgreSQL');
  });
  it('renders exactly Local versus Nube and keeps database readonly in both modes', async () => {
    const fixture = TestBed.createComponent(SetupPage); const component = fixture.componentInstance;
    fixture.detectChanges(); http.expectOne('/api/v1/setup/status').flush({ code: 'SETUP_CAPABILITY_INVALID' }, { status: 403, statusText: 'Forbidden' });
    fixture.detectChanges(); await fixture.whenStable();
    const select: MatSelect = fixture.debugElement.query(By.directive(MatSelect)).componentInstance;
    expect(select.options.map(option => option.value)).toEqual(['local', 'managed']);
    for (const mode of ['local', 'managed']) {
      component.connection.controls.mode.setValue(mode); fixture.detectChanges();
      const database: HTMLInputElement = fixture.nativeElement.querySelector('#setup-database');
      expect(database.readOnly).toBeTrue(); expect(database.value).toBe('ocoteAppDatabase');
      expect(!!fixture.nativeElement.querySelector('[formcontrolname="postgres_password"]')).toBe(mode === 'local');
      expect(!!fixture.nativeElement.querySelector('[formcontrolname="host"]')).toBe(mode === 'managed');
    }
  });
  it('rejects weak passwords repeated passwords and invalid local port before HTTP', async () => {
    credentials(); page.connection.controls.postgres_password.setValue('weak'); await page.test(); http.expectNone('/api/v1/setup/local-checks');
    expect(localPasswordValid('aaaaaaaaaaaaaaaa')).toBeFalse(); expect(localPasswordValid('Synthetic-Postgres-2026!')).toBeTrue();
    credentials(); page.connection.controls.port.setValue(0); await page.test(); http.expectNone('/api/v1/setup/local-checks');
    credentials(); page.connection.controls.port.setValue(5432); page.connection.controls.runtime_password.setValue(page.connection.controls.migrator_password.value);
    await page.test(); http.expectNone('/api/v1/setup/local-checks'); expect(page.issue()).not.toBeNull();
  });
  it('prepares and installs local cluster together with the explicit administrator', async () => {
    credentials(); let pending = page.test(); http.expectOne('/api/v1/setup/local-checks').flush({ portable_verified: true }); await pending;
    page.admin.patchValue({ display_name: 'Synthetic operator', email: 'synthetic@example.invalid', password: 'Synthetic-Admin-2026!', confirmation: 'Synthetic-Admin-2026!', timezone: 'America/Mexico_City', reason: 'Explicit synthetic installation' });
    page.review(); page.approval.setValue(true); pending = page.install(); const request = http.expectOne('/api/v1/setup/local-install');
    expect(request.request.body.local.database).toBe('ocoteAppDatabase'); expect(request.request.body.admin.role).toBe('admin'); expect(request.request.body.test_id).toBeUndefined();
    request.flush({ state: 'sealed' }); await pending; expect(router.navigateByUrl).toHaveBeenCalledWith('/login', { replaceUrl: true }); expect(page.blocked()).toBeTrue();
  });
});