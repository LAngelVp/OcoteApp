import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter, Router } from '@angular/router';
import { MatDialog } from '@angular/material/dialog';
import { Subject } from 'rxjs';
import { ExternalIdentities, LoginPage, ssoDestination, SSO_NAVIGATION } from './auth/auth.pages';
import { Api, Row } from './core/api';
import { Configuration } from './core/configuration';
import { Session, SSOProvider, SSOStart, SSOStatus } from './core/session';
import { apiKeyPayload, approvedEntries, integrationPayload, IntegrationSecret, IntegrationsPage, replayPayload, webhookFilters } from './admin/integrations.page';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { Editor } from './shared/editor';
import { ExternalLinks, externalLinkHref, externalLinkPayload } from './operations/external-links';

const transaction = '00000000-0000-4000-8000-000000000011';
const provider: SSOProvider = { id: 'synthetic-provider', name: 'Synthetic directory', provider: 'ldap' };
const start: SSOStart = { transaction_id: transaction, authorization_url: null, expires_at: 'synthetic', state: 's'.repeat(43) };

describe('F11 federated login', () => {
  function page(status?: SSOStatus) {
    const session = {
      user: signal<unknown>(null), restore: jasmine.createSpy('restore').and.resolveTo(),
      ssoProviders: jasmine.createSpy('providers').and.resolveTo({ items: [provider], next_cursor: null }),
      ssoStatus: jasmine.createSpy('status').and.resolveTo(status),
      startSSO: jasmine.createSpy('start').and.resolveTo(start),
      ldapSSO: jasmine.createSpy('ldap').and.resolveTo({ transaction_id: transaction }),
      finishSSO: jasmine.createSpy('finish').and.resolveTo({ passed: true }),
      login: jasmine.createSpy('login').and.resolveTo(),
    };
    const navigate = jasmine.createSpy('external navigation');
    const fixture = TestBed.configureTestingModule({ imports: [LoginPage], providers: [provideRouter([]),
      { provide: Session, useValue: session }, { provide: SSO_NAVIGATION, useValue: navigate },
      { provide: ActivatedRoute, useValue: { snapshot: { queryParamMap: convertToParamMap(status ? { sso_transaction: transaction } : {}) } } },
    ] }).createComponent(LoginPage);
    const router = TestBed.inject(Router);
    spyOn(router, 'navigate').and.resolveTo(true); spyOn(router, 'navigateByUrl').and.resolveTo(true);
    return { fixture, session, router, navigate };
  }
  it('keeps local login available beside only minimal explicitly discovered providers', async () => {
    const { fixture, session } = page(); fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges();
    expect(session.restore).toHaveBeenCalled(); expect(session.ssoProviders).toHaveBeenCalledOnceWith('');
    expect(fixture.nativeElement.textContent).toContain('Synthetic directory');
    expect(fixture.nativeElement.querySelector('input[autocomplete="current-password"]')).not.toBeNull();
    expect(session.startSSO).not.toHaveBeenCalled(); expect(session.finishSSO).not.toHaveBeenCalled();
  });
  it('preserves local probe return without automatically logging in or discarding its purpose', async () => {
    const status: SSOStatus = { transaction_id: transaction, purpose: 'probe', provider_name: 'Synthetic OIDC', expires_at: 'synthetic' };
    const { fixture, session, router } = page(status); session.user.set({ id: 'synthetic-admin' });
    fixture.detectChanges(); await fixture.whenStable();
    expect(router.navigate).toHaveBeenCalledWith([], jasmine.objectContaining({ replaceUrl: true, queryParams: {} }));
    expect(session.restore).toHaveBeenCalled(); expect(router.navigateByUrl).not.toHaveBeenCalled();
    expect(session.finishSSO).not.toHaveBeenCalled();
    await fixture.componentInstance.complete();
    expect(session.finishSSO).toHaveBeenCalledOnceWith(transaction, 'probe');
    expect(router.navigateByUrl).toHaveBeenCalledOnceWith('/administracion/integraciones');
  });
  it('requires explicit login completion and never restores a different cookie session first', async () => {
    const { fixture, session, router } = page({ transaction_id: transaction, purpose: 'login', provider_name: 'Synthetic OIDC', expires_at: 'synthetic' });
    fixture.detectChanges(); await fixture.whenStable();
    expect(session.restore).not.toHaveBeenCalled(); expect(session.finishSSO).not.toHaveBeenCalled();
    await fixture.componentInstance.complete();
    expect(session.finishSSO).toHaveBeenCalledOnceWith(transaction, 'login');
    expect(router.navigateByUrl).toHaveBeenCalledOnceWith('/tareas');
  });
  it('sends a directory password only to its typed command and clears it after rejection', async () => {
    const { fixture, session } = page(); fixture.detectChanges(); await fixture.whenStable();
    await fixture.componentInstance.selectProvider(provider);
    fixture.componentInstance.directoryForm.setValue({ username: 'synthetic', password: 'synthetic-secret' });
    session.ldapSSO.and.rejectWith(new Error('synthetic failure'));
    await fixture.componentInstance.submitDirectory();
    expect(session.ldapSSO).toHaveBeenCalledOnceWith(provider.id, start, 'synthetic', 'synthetic-secret');
    expect(fixture.componentInstance.directoryForm.controls.password.value).toBe('');
    expect(fixture.componentInstance.directory()).toBeNull(); expect(session.finishSSO).not.toHaveBeenCalled();
  });
  it('rejects unsafe authorization destinations before browser navigation', async () => {
    for (const value of ['javascript:alert(1)', 'http://idp.invalid', 'https://user:secret@idp.invalid', 'https://idp.invalid/#fragment', '//idp.invalid']) {
      expect(() => ssoDestination(value)).toThrow();
    }
    const { fixture, session, navigate } = page(); fixture.detectChanges(); await fixture.whenStable();
    session.startSSO.and.resolveTo({ ...start, authorization_url: 'http://idp.invalid/authorize' });
    await fixture.componentInstance.selectProvider({ ...provider, provider: 'oidc' });
    expect(navigate).not.toHaveBeenCalled(); expect(fixture.componentInstance.issue()).not.toBeNull();
  });
});

describe('F11 personal identities', () => {
  it('uses the own-identity page and sends fresh binding proof without persisting it in profile rows', async () => {
    const binding = { id: 'synthetic-link', version: 3, issuer: 'synthetic-issuer', subject: 'synthetic-subject', revoked_at: null };
    const get = jasmine.createSpy('get').and.resolveTo({ items: [binding], next_cursor: null });
    const startSSO = jasmine.createSpy('start').and.resolveTo({ ...start, authorization_url: 'https://idp.invalid/authorize' });
    const command = jasmine.createSpy('command').and.resolveTo({});
    const closed = new Subject<boolean>(), open = jasmine.createSpy('open').and.returnValue({ afterClosed: () => closed, close: () => undefined });
    const navigate = jasmine.createSpy('navigate');
    const fixture = TestBed.configureTestingModule({ imports: [ExternalIdentities], providers: [
      { provide: Configuration, useValue: { value: signal<Row | null>({ page_sizes: [5, 10, 20, 50] }), enabled: () => true } },
      { provide: Session, useValue: { user: signal({ id: 'synthetic-user' }), startSSO, ssoProviders: jasmine.createSpy('providers').and.resolveTo({ items: [provider], next_cursor: null }) } },
      { provide: Api, useValue: { get, command } }, { provide: MatDialog, useValue: { open } },
      { provide: SSO_NAVIGATION, useValue: navigate },
    ] }).createComponent(ExternalIdentities);
    fixture.detectChanges(); await fixture.whenStable();
    expect(get).toHaveBeenCalledOnceWith('/auth/sso/identities', { limit: '5' });
    fixture.componentInstance.bind({ ...provider, provider: 'oidc' });
    await open.calls.mostRecent().args[1].data.submit({ current_password: 'synthetic-local-password' });
    expect(startSSO).toHaveBeenCalledOnceWith(provider.id, 'bind', 'synthetic-local-password');
    expect(fixture.componentInstance.rows()).toEqual([binding]);
    closed.next(true); expect(navigate).toHaveBeenCalledOnceWith('https://idp.invalid/authorize');
    fixture.componentInstance.revoke(binding);
    await open.calls.mostRecent().args[1].data.submit({ current_password: 'synthetic-local-password', reason: 'Synthetic revoke' });
    expect(command).toHaveBeenCalledOnceWith('/auth/sso/identities/synthetic-link/revoke', {
      current_password: 'synthetic-local-password', reason: 'Synthetic revoke', expected_version: 3,
    });
    expect(binding.revoked_at).toBeNull();
  });
  it('does not request identity lists or discovery while SSO is disabled', async () => {
    const get = jasmine.createSpy('get'), providers = jasmine.createSpy('providers');
    const fixture = TestBed.configureTestingModule({ imports: [ExternalIdentities], providers: [
      { provide: Configuration, useValue: { value: signal<Row | null>({}), enabled: () => false } },
      { provide: Session, useValue: { user: signal({ id: 'synthetic-user' }), ssoProviders: providers } },
      { provide: Api, useValue: { get } },
    ] }).createComponent(ExternalIdentities);
    fixture.detectChanges(); await fixture.whenStable();
    expect(get).not.toHaveBeenCalled(); expect(providers).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent.trim()).toBe('');
  });
});

describe('F11 integration administration', () => {
  it('creates only a linked replay command without copying body, secrets or mutable attempt state', () => {
    const row = { id: 'synthetic-delivery', version: 4, body: 'private', signing_secret_id: 'private', lease_token: 'private' };
    const values = { current_password: 'synthetic-local', reason: 'Synthetic linked replay' };
    expect(replayPayload(row, values, 'synthetic-idempotency')).toEqual({ delivery_id: row.id, expected_version: 4, idempotency_key: 'synthetic-idempotency', ...values });
    expect(webhookFilters({ state: 'all', subscription_id: 'all', since: '2026-11-26T08:00' })).toEqual({ since: '2026-11-26T08:00:00.000Z' });
    expect(webhookFilters({ state: 'dead_letter', until: 'invalid' })).toEqual({ state: 'dead_letter' });
  });
  it('updates approved mappings without mutating their original snapshot or allowing an invalid index', () => {
    const mapping = { attribute: 'groups', value: ' exact literal ', role: 'colaborador', department_id: 'synthetic' };
    const original = [mapping], changed = approvedEntries(original, 0, 'change', { ...mapping, role: 'lider' });
    expect(changed[0]['role']).toBe('lider'); expect(original[0].role).toBe('colaborador');
    expect(changed[0]['value']).toBe(' exact literal ');
    expect(() => approvedEntries(original, -1, 'remove', {})).toThrow();
  });
  it('preserves exact literal mapping whitespace through the shared editor', async () => {
    const submit = jasmine.createSpy('submit').and.resolveTo();
    const fixture = TestBed.configureTestingModule({ imports: [Editor], providers: [
      { provide: MAT_DIALOG_DATA, useValue: { title: 'Synthetic mapping', fields: [{ key: 'value', label: 'Literal', required: true, preserveWhitespace: true, value: ' exact literal ' }], submit } },
      { provide: MatDialogRef, useValue: { close: jasmine.createSpy('close'), disableClose: false } },
    ] }).createComponent(Editor);
    fixture.detectChanges(); await fixture.componentInstance.save();
    expect(submit).toHaveBeenCalledOnceWith({ value: ' exact literal ' });
  });
  it('omits empty credentials on connector edits and preserves exact typed repository identities', () => {
    const body = integrationPayload('github', { name: 'Synthetic GitHub', scope_kind: 'organization', access_token: '', webhook_secret: '', web_origin: 'https://github.com', api_endpoint__host: 'api.github.com', api_endpoint__url: 'https://api.github.com', api_endpoint__approved_addresses: '93.184.216.34\n8.8.8.8' }, { version: 3, config: { repositories: [{ repository_id: '123', path: 'synthetic/repository' }] }, ciphertext: 'private' });
    expect(body['expected_version']).toBe(3); expect(body['credential']).toBeUndefined(); expect(body['ciphertext']).toBeUndefined();
    const config = body['config'] as Row;
    expect(config['repositories']).toEqual([{ repository_id: '123', path: 'synthetic/repository' }]);
    expect((config['api_endpoint'] as Row)['approved_addresses']).toEqual(['93.184.216.34', '8.8.8.8']);
    const rotated = integrationPayload('gitlab', { access_token: ' exact-token ', webhook_secret: 'exact-native-secret' });
    expect(JSON.parse(String(rotated['credential']))).toEqual({ access_token: ' exact-token ', webhook_secret: 'exact-native-secret' });
  });
  it('preserves multiline private material exactly and clears it when its editor is destroyed', async () => {
    const value = '  synthetic-private-material\nsecond-line\n', submit = jasmine.createSpy('submit').and.resolveTo();
    const fixture = TestBed.configureTestingModule({ imports: [Editor], providers: [
      { provide: MAT_DIALOG_DATA, useValue: { title: 'Synthetic private key', fields: [{ key: 'credential', label: 'Clave privada', type: 'secret', value, required: true }], submit } },
      { provide: MatDialogRef, useValue: { close: jasmine.createSpy('close'), disableClose: false } },
    ] }).createComponent(Editor);
    fixture.detectChanges(); await fixture.componentInstance.save();
    expect(submit).toHaveBeenCalledOnceWith({ credential: value });
    const control = fixture.componentInstance.form.get('credential'); fixture.destroy(); expect(control?.value).toBeNull();
  });
  it('does not request integration data for a collaborator', async () => {
    const get = jasmine.createSpy('get'), all = jasmine.createSpy('all');
    const fixture = TestBed.configureTestingModule({ imports: [IntegrationsPage], providers: [
      { provide: Configuration, useValue: { value: signal<Row | null>({}), enabled: () => true } },
      { provide: Session, useValue: { user: signal({ id: 'synthetic', role: 'colaborador' }) } },
      { provide: Api, useValue: { get, all } },
    ] }).createComponent(IntegrationsPage);
    fixture.detectChanges(); await fixture.whenStable();
    expect(get).not.toHaveBeenCalled(); expect(all).not.toHaveBeenCalled();
  });
  it('requires explicit UTC expiry and network policy and sends no invented authority', () => {
    const body = apiKeyPayload({ name: 'Synthetic', expires_at: '2026-12-01T10:00', network_policy: 'cidr', allowed_networks: '192.0.2.0/24\n2001:db8::/32', scopes: ['tasks:read'], ciphertext: 'private' }, { version: 4 });
    expect(body['expected_version']).toBe(4); expect(body['expires_at']).toBe('2026-12-01T10:00:00.000Z');
    expect(body['allowed_networks']).toEqual(['192.0.2.0/24', '2001:db8::/32']); expect(body['ciphertext']).toBeUndefined();
    expect(apiKeyPayload({ expires_at: '2026-02-31T10:00' })['expires_at']).toBeNull();
  });
  it('clears a one-time secret when the authenticated identity changes', async () => {
    const user = signal<unknown>({ id: 'synthetic-admin' }), data = { title: 'Synthetic', value: 'synthetic-key' }, close = jasmine.createSpy('close');
    const fixture = TestBed.configureTestingModule({ imports: [IntegrationSecret], providers: [
      { provide: MAT_DIALOG_DATA, useValue: data }, { provide: MatDialogRef, useValue: { close } },
      { provide: Session, useValue: { user } },
    ] }).createComponent(IntegrationSecret);
    fixture.detectChanges(); user.set({ id: 'different-user' }); fixture.detectChanges(); await fixture.whenStable();
    expect(data.value).toBe(''); expect(close).toHaveBeenCalled();
  });
});

describe('F11 task traceability', () => {
  it('does not request providers or links when the DevOps module is disabled', async () => {
    const get = jasmine.createSpy('get'), all = jasmine.createSpy('all');
    const fixture = TestBed.configureTestingModule({ imports: [ExternalLinks], providers: [
      { provide: Configuration, useValue: { value: signal<Row | null>({}), enabled: () => false } },
      { provide: Session, useValue: { user: signal({ id: 'synthetic', role: 'colaborador' }) } },
      { provide: Api, useValue: { get, all } },
    ] }).createComponent(ExternalLinks);
    fixture.componentRef.setInput('task', { id: 'synthetic-task', version: 4 }); fixture.detectChanges(); await fixture.whenStable();
    expect(get).not.toHaveBeenCalled(); expect(all).not.toHaveBeenCalled();
  });
  it('sends exact branch identity and task version without a fabricated URL or task facts', () => {
    expect(externalLinkPayload({ id: 'task', version: 4, completed_at: 'private' }, { id: 'connector' }, { repository_id: '123' }, { kind: 'branch', external_id: 'feature/login', reason: 'Synthetic link', canonical_url: 'https://unapproved.invalid' })).toEqual({ expected_version: 4, integration_id: 'connector', repository_id: '123', kind: 'branch', external_id: 'feature/login', reason: 'Synthetic link' });
    expect(externalLinkHref({ canonical_url: 'javascript:alert(1)' })).toBeNull();
    expect(externalLinkHref({ canonical_url: 'https://user:secret@example.invalid' })).toBeNull();
    expect(externalLinkHref({ canonical_url: 'https://github.com/synthetic/repository/tree/feature%2Flogin' })).toContain('feature%2Flogin');
  });
});