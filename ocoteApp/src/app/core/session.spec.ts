import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { Session, SESSION_LOCK, SessionLock, sessionInterceptor } from './session';

const user = { id:'synthetic-user',email:'synthetic@example.test',display_name:'Synthetic',role:'lider',department_id:'synthetic-department',permissions:['tasks:manage'] };
const tokens = { access_token:'synthetic-access',csrf_token:'synthetic-csrf',expires_in:600 };
const settle = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };

describe('F4 memory session and same-origin HTTP', () => {
  let session: Session, http: HttpTestingController, client: HttpClient;
  let run: jasmine.Spy;
  beforeEach(() => {
    run = jasmine.createSpy('origin lock').and.callFake((action: () => Promise<unknown>) => action());
    TestBed.configureTestingModule({ providers: [provideRouter([]),provideHttpClient(withInterceptors([sessionInterceptor])),provideHttpClientTesting(),{ provide:SESSION_LOCK,useValue:{ run } as SessionLock }] });
    session = TestBed.inject(Session); http = TestBed.inject(HttpTestingController); client = TestBed.inject(HttpClient);
    spyOn(TestBed.inject(Router),'navigateByUrl').and.resolveTo(true);
  });
  afterEach(() => http.verify());
  async function login(): Promise<void> {
    const pending = session.login('synthetic@example.test','synthetic-password');
    http.expectOne('/api/v1/auth/login').flush(tokens); await settle();
    http.expectOne('/api/v1/auth/me').flush(user); await pending;
  }
  async function rotate(): Promise<void> {
    http.expectOne('/api/v1/auth/csrf').flush({ csrf_token:'fresh-csrf' }); await settle();
    const request = http.expectOne('/api/v1/auth/refresh');
    expect(request.request.headers.get('X-CSRF-Token')).toBe('fresh-csrf');
    expect(request.request.withCredentials).toBeTrue();
    request.flush({ ...tokens,access_token:'rotated-access' }); await settle();
    http.expectOne('/api/v1/auth/me').flush(user); await settle();
  }
  it('keeps access and CSRF in memory, loads effective permissions and never writes web storage', async () => {
    const storage = spyOn(Storage.prototype,'setItem');
    await login();
    expect(session.token()).toBe('synthetic-access'); expect(session.has('tasks:manage')).toBeTrue();
    expect(session.has('administration:manage')).toBeFalse(); expect(storage).not.toHaveBeenCalled();
  });
  it('hydrates through fresh CSRF and one serialized rotation', async () => {
    const first = session.restore(), second = session.restore();
    expect(first).toBe(second); await rotate(); await first;
    expect(run).toHaveBeenCalledTimes(1); expect(session.ready()).toBeTrue(); expect(session.user()?.id).toBe(user.id);
  });
  it('shares an in-flight refresh across concurrent requests', async () => {
    const first = session.refresh(), second = session.refresh(); expect(first).toBe(second);
    await rotate(); await first; expect(run).toHaveBeenCalledTimes(1);
  });
  it('fails closed on absent browser locking without sending cookies', async () => {
    run.and.returnValue(Promise.reject(new Error('unavailable')));
    await expectAsync(session.refresh()).toBeRejected(); expect(session.token()).toBeNull(); http.expectNone('/api/v1/auth/csrf');
  });
  it('finishes SSO under the session lock, then loads permissions without storing provider tokens', async () => {
    const storage = spyOn(Storage.prototype, 'setItem');
    const pending = session.finishSSO('synthetic-transaction', 'login');
    const finish = http.expectOne('/api/v1/auth/sso/finish');
    expect(finish.request.body).toEqual({ transaction_id: 'synthetic-transaction' });
    expect(finish.request.withCredentials).toBeTrue();
    expect(finish.request.headers.has('Authorization')).toBeFalse();
    finish.flush(tokens); await settle();
    http.expectOne('/api/v1/auth/me').flush(user); await pending;
    expect(session.token()).toBe(tokens.access_token); expect(session.user()?.id).toBe(user.id);
    expect(run).toHaveBeenCalledTimes(1); expect(storage).not.toHaveBeenCalled();
  });
  it('keeps the existing local session when finishing an administrative probe', async () => {
    await login(); const pending = session.finishSSO('synthetic-probe', 'probe');
    const finish = http.expectOne('/api/v1/auth/sso/probe/finish');
    expect(finish.request.headers.get('Authorization')).toBe('Bearer synthetic-access');
    expect(finish.request.headers.get('X-CSRF-Token')).toBe('synthetic-csrf');
    finish.flush({ passed: true, is_active: false }); await pending;
    expect(session.token()).toBe('synthetic-access'); expect(session.user()?.id).toBe(user.id);
    http.expectNone('/api/v1/auth/me');
  });
  it('never retries rejected public SSO through a human refresh', async () => {
    const pending = session.finishSSO('synthetic-transaction', 'login');
    const rejected = expectAsync(pending).toBeRejected();
    http.expectOne('/api/v1/auth/sso/finish').flush({}, { status: 401, statusText: 'Unauthorized' });
    await rejected; http.expectNone('/api/v1/auth/csrf'); http.expectNone('/api/v1/auth/refresh');
  });
  it('fails closed on unavailable Web Locks before starting SSO or submitting a directory password', async () => {
    run.and.returnValue(Promise.reject(new Error('unavailable')));
    await expectAsync(session.startSSO('synthetic-provider')).toBeRejected();
    await expectAsync(session.ldapSSO('synthetic-provider', {
      transaction_id: 'synthetic-transaction', authorization_url: null, expires_at: 'synthetic', state: 's'.repeat(43),
    }, 'synthetic-user', 'synthetic-password')).toBeRejected();
    http.expectNone(request => request.url.includes('/auth/sso/'));
  });
  it('sends Bearer and CSRF only to relative API requests', async () => {
    await login(); const pending = firstValueFrom(client.post('/api/v1/tasks', { title:'Synthetic' }));
    const request = http.expectOne('/api/v1/tasks');
    expect(request.request.headers.get('Authorization')).toBe('Bearer synthetic-access');
    expect(request.request.headers.get('X-CSRF-Token')).toBe('synthetic-csrf'); request.flush({}); await pending;
    const external = firstValueFrom(client.get('https://outside.invalid/resource'));
    const outside = http.expectOne('https://outside.invalid/resource');
    expect(outside.request.headers.has('Authorization')).toBeFalse(); expect(outside.request.withCredentials).toBeFalse(); outside.flush({}); await external;
  });
  it('refreshes an expired request once and retries with the new token', async () => {
    await login(); const pending = firstValueFrom(client.get('/api/v1/tasks'));
    http.expectOne('/api/v1/tasks').flush({ code:'TOKEN_EXPIRED' },{ status:401,statusText:'Unauthorized' });
    await rotate(); await settle();
    const retry = http.expectOne('/api/v1/tasks'); expect(retry.request.headers.get('Authorization')).toBe('Bearer rotated-access'); retry.flush({ items:[] }); await pending;
  });
  it('ends the local session when the single retry is also unauthorized', async () => {
    await login(); const pending = firstValueFrom(client.get('/api/v1/tasks')), rejected = expectAsync(pending).toBeRejected();
    http.expectOne('/api/v1/tasks').flush({},{ status:401,statusText:'Unauthorized' });
    await rotate(); await settle();
    http.expectOne('/api/v1/tasks').flush({},{ status:401,statusText:'Unauthorized' });
    await rejected; expect(session.token()).toBeNull(); expect(session.user()).toBeNull();
    http.expectNone('/api/v1/auth/refresh');
  });
  it('never retries a 409 mutation and leaves server versions untouched', async () => {
    await login(); const pending = firstValueFrom(client.post('/api/v1/tasks/id/due-date-changes',{ expected_version:4 }));
    const rejected = expectAsync(pending).toBeRejected();
    http.expectOne('/api/v1/tasks/id/due-date-changes').flush({ code:'VERSION_CONFLICT' },{ status:409,statusText:'Conflict' });
    await rejected; http.expectNone('/api/v1/auth/refresh');
  });
  it('clears memory when a refresh is revoked', async () => {
    await login(); const pending = session.refresh(), rejected = expectAsync(pending).toBeRejected();
    http.expectOne('/api/v1/auth/csrf').flush({},{ status:401,statusText:'Unauthorized' });
    await rejected; expect(session.token()).toBeNull(); expect(session.user()).toBeNull();
  });
  it('obtains current CSRF inside the lock before logout and clears memory', async () => {
    await login(); const pending = session.logout();
    http.expectOne('/api/v1/auth/csrf').flush({ csrf_token:'latest-cookie-csrf' }); await settle();
    const request = http.expectOne('/api/v1/auth/logout'); expect(request.request.headers.get('X-CSRF-Token')).toBe('latest-cookie-csrf');
    request.flush(null); await pending; expect(session.token()).toBeNull(); expect(session.user()).toBeNull();
  });
  it('clears local identity if the cookie session has already expired at logout', async () => {
    await login(); const pending = session.logout(), rejected = expectAsync(pending).toBeRejected();
    http.expectOne('/api/v1/auth/csrf').flush({},{ status:401,statusText:'Unauthorized' });
    await rejected; expect(session.token()).toBeNull(); expect(session.user()).toBeNull();
  });
  it('does not pretend a failed logout revoked the server session', async () => {
    await login(); const pending = session.logout(), rejected = expectAsync(pending).toBeRejected();
    http.expectOne('/api/v1/auth/csrf').flush({},{ status:503,statusText:'Unavailable' });
    await rejected; expect(session.user()).not.toBeNull();
  });
  it('changes password without transmitting confirmation and ends the session', async () => {
    await login(); const pending = session.changePassword('old-synthetic','new-synthetic');
    const request = http.expectOne('/api/v1/auth/change-password');
    expect(request.request.body).toEqual({ current_password:'old-synthetic',new_password:'new-synthetic' });
    request.flush(null); await pending; expect(session.token()).toBeNull();
  });
});