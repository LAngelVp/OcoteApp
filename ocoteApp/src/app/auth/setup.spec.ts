import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { Router } from '@angular/router';
import { SetupPage } from './setup.page';

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
  function credentials() { page.connection.patchValue({ runtime_password: 'synthetic-runtime', migrator_password: 'synthetic-migrator' }); }
  it('tests local roles without downgrade or session storage', async () => {
    credentials(); const pending = page.test(); const request = http.expectOne('/api/v1/setup/connection-tests');
    expect(request.request.body.sslmode).toBe('disable'); expect(request.request.body.runtime_role).toBe('ocote_runtime');
    request.flush({ test_id: 'a'.repeat(32) }); await pending; expect(page.step()).toBe(2); expect(page.connection.controls.runtime_password.value).toBe('');
  });
  it('requires verify-full and CA for external PostgreSQL', async () => {
    credentials(); page.connection.patchValue({ mode: 'managed', host: 'pg.example.invalid', ca_pem: 'synthetic public CA' });
    const pending = page.test(); const request = http.expectOne('/api/v1/setup/connection-tests');
    expect(request.request.body.sslmode).toBe('verify-full'); expect(request.request.body.ca_pem).toBe('synthetic public CA');
    request.flush({ test_id: 'b'.repeat(32) }); await pending; expect(page.step()).toBe(2);
  });
  it('keeps unavailable database blocked from installation', async () => {
    credentials(); const pending = page.test(); http.expectOne('/api/v1/setup/connection-tests').flush({ code: 'SETUP_CONNECTION_UNAVAILABLE', request_id: 'synthetic-request' }, { status: 503, statusText: 'Unavailable' });
    await pending; expect(page.step()).toBe(0); expect(page.issue()?.requestId).toBe('synthetic-request'); await page.install(); http.expectNone('/api/v1/setup/install');
  });
  it('redirects sealed instances and disables irreversible resubmission', async () => {
    const pending = page.ngOnInit(); http.expectOne('/api/v1/setup/status').flush({ code: 'SETUP_SEALED' }, { status: 403, statusText: 'Forbidden' });
    await pending; expect(page.blocked()).toBeTrue(); expect(router.navigateByUrl).toHaveBeenCalledWith('/login', { replaceUrl: true });
    await page.test(); http.expectNone('/api/v1/setup/connection-tests');
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
    http.expectOne('/api/v1/setup/pair').flush({ session_code: 'synthetic-session' }); await pending;
    fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[aria-current="step"]').textContent).toContain('PostgreSQL');
  });
});