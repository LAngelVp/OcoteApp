import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { provideRouter } from '@angular/router';
import { Api, Row } from './core/api';
import { Configuration } from './core/configuration';
import { Session } from './core/session';
import { FeedCapability, NotificationsPage, preferencesPayload } from './operations/notifications.page';
import { Editor } from './shared/editor';
import { connectorPayload, NotificationsAdminPage, rulePayload } from './admin/notifications.page';

describe('F10 personal activity', () => {
  it('does not request unconfigured modules', async () => {
    const get = jasmine.createSpy('get'), all = jasmine.createSpy('all');
    const fixture = TestBed.configureTestingModule({ imports: [NotificationsPage], providers: [provideRouter([]),
      { provide: Configuration, useValue: { value: signal<Row | null>({}), enabled: () => false } },
      { provide: Session, useValue: { user: signal({ id: 'synthetic', role: 'colaborador' }) } },
      { provide: Api, useValue: { get, all } },
    ] }).createComponent(NotificationsPage);
    fixture.detectChanges(); await fixture.whenStable();
    expect(get).not.toHaveBeenCalled(); expect(all).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('Actividad personal no disponible');
  });
  it('preserves explicit opt-out and version without inventing timezone or channels', () => {
    const values = { opt_in: false, channels: ['email'], quiet_start: '', quiet_end: '', timezone: 'America/Mexico_City', reason: 'Synthetic preference' };
    expect(preferencesPayload(values, { version: 3 })).toEqual({ ...values, expected_version: 3, quiet_start: null, quiet_end: null });
  });
  it('omits empty credentials on edit and never echoes ciphertext into a command', () => {
    const body = connectorPayload('slack', { name: 'Synthetic', scope_kind: 'organization', approved_addresses: '93.184.216.34\n8.8.8.8', credential: '', current_password: 'synthetic', reason: 'Synthetic edit' }, { version: 4, ciphertext: 'private' });
    expect(body['expected_version']).toBe(4); expect(body['credential']).toBeUndefined();
    expect(body['ciphertext']).toBeUndefined(); expect((body['config'] as Row)['approved_addresses']).toEqual(['93.184.216.34', '8.8.8.8']);
    expect(rulePayload({ trigger: 'assignment', threshold_days: 9 })['threshold_days']).toBeNull();
  });
  it('does not request administration data for a collaborator', async () => {
    const all = jasmine.createSpy('all');
    const fixture = TestBed.configureTestingModule({ imports: [NotificationsAdminPage], providers: [
      { provide: Configuration, useValue: { value: signal<Row | null>({}), enabled: () => true } },
      { provide: Session, useValue: { user: signal({ id: 'synthetic', role: 'colaborador' }) } },
      { provide: Api, useValue: { all } },
    ] }).createComponent(NotificationsAdminPage);
    fixture.detectChanges(); await fixture.whenStable();
    expect(all).not.toHaveBeenCalled();
  });
  it('preserves conflicts, blocks resubmission and clears passwords on discard', async () => {
    const submit = jasmine.createSpy('submit').and.rejectWith(new HttpErrorResponse({ status: 409, error: { code: 'VERSION_CONFLICT' } }));
    const fixture = TestBed.configureTestingModule({ imports: [Editor], providers: [
      { provide: MAT_DIALOG_DATA, useValue: { title: 'Synthetic connector', fields: [{ key: 'name', label: 'Nombre', value: 'Preserved name', required: true }, { key: 'credential', label: 'Credencial', type: 'password', value: 'synthetic secret' }], submit } },
      { provide: MatDialogRef, useValue: { close: jasmine.createSpy('close'), disableClose: false } },
    ] }).createComponent(Editor);
    fixture.detectChanges(); await fixture.componentInstance.save(); fixture.detectChanges();
    expect(fixture.componentInstance.issue()?.conflict).toBeTrue();
    expect(fixture.componentInstance.form.get('name')?.value).toBe('Preserved name');
    await fixture.componentInstance.save(); expect(submit).toHaveBeenCalledTimes(1);
    const control = fixture.componentInstance.form.get('credential'); fixture.destroy();
    expect(control?.value).toBeNull();
  });
  it('clears a one-time capability when the session is lost', async () => {
    const user = signal<unknown>({ id: 'synthetic' }), data = { url: 'https://localhost/synthetic-capability' };
    const close = jasmine.createSpy('close');
    const fixture = TestBed.configureTestingModule({ imports: [FeedCapability], providers: [
      { provide: MAT_DIALOG_DATA, useValue: data }, { provide: MatDialogRef, useValue: { close } },
      { provide: Session, useValue: { user } },
    ] }).createComponent(FeedCapability);
    fixture.detectChanges(); user.set(null); fixture.detectChanges(); await fixture.whenStable();
    expect(data.url).toBe(''); expect(close).toHaveBeenCalled();
  });
});