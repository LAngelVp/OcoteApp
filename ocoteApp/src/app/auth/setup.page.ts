import { HttpClient, HttpContext, HttpErrorResponse } from '@angular/common/http';
import { afterNextRender, Component, inject, Injector, OnDestroy, OnInit, signal, viewChild } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, ValidatorFn, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatStepper, MatStepperModule } from '@angular/material/stepper';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { Problem, problem } from '../core/problem';
import { NO_SESSION } from '../core/session';
import { Feedback } from '../shared/feedback';

export function localPasswordValid(value: string): boolean {
  return value.length >= 14 && value.length <= 128 && !/[\u0000-\u001f\u007f]/.test(value)
    && [/[a-z]/, /[A-Z]/, /[0-9]/, /[^a-zA-Z0-9]/].filter(pattern => pattern.test(value)).length >= 3;
}

@Component({
  imports: [ReactiveFormsModule, MatButtonModule, MatCheckboxModule, MatFormFieldModule,
    MatIconModule, MatInputModule, MatSelectModule, MatStepperModule, Feedback],
  template: `<main class="setup-page"><header><img src="/logos/ocote-complete.webp" width="240" height="132" alt="OCOTE"><h1>Instalacion inicial</h1></header>
    <ocote-feedback [issue]="issue()" />
    @if (blocked()) { <section role="status"><h2>Instalacion no disponible</h2><a mat-button href="/login"><mat-icon>login</mat-icon>Ir a acceso</a></section> }
    @else { <mat-stepper orientation="vertical" [selectedIndex]="step()" linear>
      <mat-step [completed]="step() > 0" [editable]="false"><ng-template matStepLabel>Emparejar equipo</ng-template>
        <form (ngSubmit)="pair()" [formGroup]="pairing"><mat-form-field><mat-label>Capacidad de instalacion</mat-label><input matInput type="password" autocomplete="off" formControlName="code"></mat-form-field>
          <button mat-flat-button type="submit" [disabled]="busy() || pairing.invalid"><mat-icon>link</mat-icon>Emparejar</button></form></mat-step>
      <mat-step [completed]="step() > 1" [editable]="false"><ng-template matStepLabel>PostgreSQL</ng-template>
        <form [formGroup]="connection" (ngSubmit)="test()"><div class="fields">
          <mat-form-field><mat-label>Modalidad</mat-label><mat-select formControlName="mode"><mat-option value="local">Base de datos local (portable integrado)</mat-option><mat-option value="managed">Servidor externo / Nube</mat-option></mat-select></mat-form-field>
          @if (connection.controls.mode.value === 'managed') {
            <mat-form-field><mat-label>Host PostgreSQL</mat-label><input matInput formControlName="host" autocomplete="off"></mat-form-field>
            <mat-form-field><mat-label>IP aprobada</mat-label><input matInput formControlName="approved_address" autocomplete="off"></mat-form-field>
          }
          <mat-form-field><mat-label>Puerto</mat-label><input matInput type="number" formControlName="port" min="1" max="65535"></mat-form-field>
          <mat-form-field><mat-label>Base de datos</mat-label><input id="setup-database" matInput value="ocoteAppDatabase" readonly aria-readonly="true"></mat-form-field>
          @if (connection.controls.mode.value === 'local') {
            <mat-form-field><mat-label>Carpeta de datos (estado privado)</mat-label><input matInput formControlName="data_directory" autocomplete="off"></mat-form-field>
            <mat-form-field><mat-label>Contrasena postgres local</mat-label><input matInput type="password" autocomplete="new-password" formControlName="postgres_password"><mat-hint>Minimo14 caracteres y3 clases.</mat-hint></mat-form-field>
          }
          <mat-form-field><mat-label>Rol runtime</mat-label><input matInput value="ocote_runtime" readonly></mat-form-field>
          <mat-form-field><mat-label>Contrasena runtime</mat-label><input matInput type="password" autocomplete="new-password" formControlName="runtime_password"></mat-form-field>
          <mat-form-field><mat-label>Rol migrador</mat-label><input matInput value="ocote_migrador" readonly></mat-form-field>
          <mat-form-field><mat-label>Contrasena migrador</mat-label><input matInput type="password" autocomplete="new-password" formControlName="migrator_password"></mat-form-field>
        </div>
        @if (connection.controls.mode.value === 'managed') { <p class="tls"><mat-icon>verified_user</mat-icon>TLS verify-full</p><mat-form-field class="wide"><mat-label>Certificado CA PEM</mat-label><textarea matInput formControlName="ca_pem" rows="5" spellcheck="false"></textarea></mat-form-field> }
        @if (connection.controls.mode.value === 'local' && !localAvailable()) { <p role="status">PostgreSQL portable no incluido en este paquete.</p> }
        <button mat-flat-button type="submit" [disabled]="busy() || connection.invalid || (connection.controls.mode.value === 'local' && !localAvailable())"><mat-icon>storage</mat-icon>{{ connection.controls.mode.value === 'local' ? 'Validar instalacion local' : 'Probar conexion y permisos' }}</button></form></mat-step>
      <mat-step [completed]="step() > 2" [editable]="false"><ng-template matStepLabel>Primer administrador</ng-template>
        <form [formGroup]="admin" (ngSubmit)="review()"><div class="fields">
          <mat-form-field><mat-label>Nombre completo</mat-label><input matInput formControlName="display_name" autocomplete="name"></mat-form-field>
          <mat-form-field><mat-label>Correo electronico</mat-label><input matInput type="email" formControlName="email" autocomplete="username"></mat-form-field>
          <mat-form-field><mat-label>Contrasena del administrador</mat-label><input matInput type="password" autocomplete="new-password" formControlName="password"></mat-form-field>
          <mat-form-field><mat-label>Confirmar contrasena</mat-label><input matInput type="password" autocomplete="new-password" formControlName="confirmation"></mat-form-field>
          <mat-form-field><mat-label>Zona IANA</mat-label><input matInput formControlName="timezone" placeholder="America/Mexico_City"></mat-form-field>
          <mat-form-field><mat-label>Motivo</mat-label><textarea matInput formControlName="reason" rows="2"></textarea></mat-form-field>
        </div><button mat-flat-button type="submit" [disabled]="busy() || admin.invalid"><mat-icon>arrow_forward</mat-icon>Revisar instalacion</button></form></mat-step>
      <mat-step [editable]="false"><ng-template matStepLabel>Confirmar y sellar</ng-template>
        <dl><dt>Revision</dt><dd>20261126_0011</dd><dt>Origen HTTPS</dt><dd>{{ origin }}</dd><dt>Estado</dt><dd>Instalacion nueva confirmada</dd></dl>
        <mat-checkbox [formControl]="approval">Confirmo el destino nuevo y el cierre irreversible del asistente</mat-checkbox>
        <div class="actions"><button mat-flat-button type="button" (click)="install()" [disabled]="busy() || !approval.value"><mat-icon>lock</mat-icon>{{ busy() ? 'Instalando...' : connection.controls.mode.value === 'local' ? 'Preparar e instalar' : 'Instalar y sellar' }}</button></div>
      </mat-step>
    </mat-stepper> }
  </main>`,
  styles: [`:host{display:block}.setup-page{max-width:960px;margin:0 auto;padding:24px;box-sizing:border-box}header{border-bottom:1px solid var(--ocote-primary);margin-bottom:24px}header img{display:block;width:200px;height:110px;object-fit:contain}h1{font-size:28px;line-height:1.2}h2{font-size:22px}form{padding-top:16px}.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr));gap:0 16px}mat-form-field{min-width:0;width:100%}button{border-radius:8px;max-width:100%;height:auto;min-height:44px;white-space:normal}.wide{width:100%}.tls{display:flex;align-items:center;gap:8px}.actions{margin-top:24px}dd{margin:0 0 16px;overflow-wrap:anywhere}mat-checkbox{display:block}*{letter-spacing:0}@media(max-width:480px){.setup-page{padding:16px 8px}h1{font-size:24px}}`],
})
export class SetupPage implements OnInit, OnDestroy {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly injector = inject(Injector);
  private readonly wizard = viewChild(MatStepper);
  private code = '';
  private testedConnection: Record<string, unknown> | null = null;
  private testId = '';
  readonly origin = window.location.origin;
  readonly step = signal(0);
  readonly busy = signal(false);
  readonly blocked = signal(false);
  readonly localAvailable = signal(false);
  readonly issue = signal<Problem | null>(null);
  readonly pairing = new FormGroup({ code: new FormControl('', { nonNullable: true, validators: [Validators.required] }) });
  readonly connection = new FormGroup({
    mode: new FormControl('local', { nonNullable: true }), host: new FormControl('127.0.0.1', { nonNullable: true, validators: [Validators.required] }),
    approved_address: new FormControl('127.0.0.1', { nonNullable: true, validators: [Validators.required] }),
    port: new FormControl(5432, { nonNullable: true, validators: [Validators.required, Validators.min(1), Validators.max(65535)] }),
    runtime_password: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
    migrator_password: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
    ca_pem: new FormControl('', { nonNullable: true }),
    data_directory: new FormControl('postgres-data', { nonNullable: true }),
    postgres_password: new FormControl('', { nonNullable: true }),
  });
  readonly admin = new FormGroup({
    display_name: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.maxLength(120)] }),
    email: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.email] }),
    password: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(12), Validators.maxLength(128)] }),
    confirmation: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
    timezone: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
    reason: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(10)] }),
  });
  readonly approval = new FormControl(false, { nonNullable: true });
  private readonly subscription = this.connection.valueChanges.subscribe(() => { this.testId = ''; this.testedConnection = null; });
  private readonly modeSubscription = this.connection.controls.mode.valueChanges.subscribe(() => this.applyMode());
  private applyMode(): void {
    const local = this.connection.controls.mode.value === 'local';
    const strong: ValidatorFn = control => typeof control.value === 'string' && localPasswordValid(control.value) ? null : { strength: true };
    this.connection.controls.postgres_password.setValidators(local ? [Validators.required, strong] : []);
    this.connection.controls.data_directory.setValidators(local ? [Validators.required] : []);
    for (const control of [this.connection.controls.runtime_password, this.connection.controls.migrator_password]) {
      control.setValidators(local ? [Validators.required, strong] : [Validators.required]);
    }
    for (const control of Object.values(this.connection.controls)) control.updateValueAndValidity({ emitEvent: false });
  }
  private options() { return { context: new HttpContext().set(NO_SESSION, true), headers: { 'X-Setup-Code': this.code } }; }
  async ngOnInit(): Promise<void> {
    this.applyMode();
    try { await firstValueFrom(this.http.get('/api/v1/setup/status', this.options())); }
    catch (error) { if (!(error instanceof HttpErrorResponse && error.error?.code === 'SETUP_CAPABILITY_INVALID')) { this.blocked.set(true); await this.fail(error); } }
  }
  async pair(): Promise<void> {
    this.code = this.pairing.controls.code.value;
    this.busy.set(true);
    try { const result = await firstValueFrom(this.http.post<{ session_code: string; local_portable_available?: boolean }>('/api/v1/setup/pair', {}, this.options())); this.code = result.session_code; this.localAvailable.set(result.local_portable_available === true); this.applyMode(); this.pairing.reset(); this.issue.set(null); this.advance(1); }
    catch (error) { this.code = ''; await this.fail(error); }
    finally { this.busy.set(false); }
  }
  async test(): Promise<void> {
    this.applyMode();
    if (this.connection.invalid || this.busy() || this.blocked()) return;
    const values = this.connection.getRawValue();
    if (values.mode === 'local') {
      if (!this.localAvailable()) { this.issue.set({ message: 'PostgreSQL portable no incluido.', conflict: false }); return; }
      if (new Set([values.postgres_password, values.runtime_password, values.migrator_password]).size !== 3) {
        this.issue.set({ message: 'Las tres contrasenas locales deben ser distintas.', conflict: false }); return;
      }
      this.busy.set(true); this.testId = ''; this.testedConnection = null;
      const local = { database: 'ocoteAppDatabase', port: values.port, data_directory: values.data_directory,
        postgres_password: values.postgres_password, migrator_password: values.migrator_password, runtime_password: values.runtime_password };
      try {
        await firstValueFrom(this.http.post('/api/v1/setup/local-checks', local, this.options()));
        this.testedConnection = local;
        this.connection.patchValue({ postgres_password: '', runtime_password: '', migrator_password: '' }, { emitEvent: false });
        this.issue.set(null); this.advance(2);
      } catch (error) { await this.fail(error); }
      finally { this.busy.set(false); }
      return;
    }
    if (values.mode === 'managed' && !values.ca_pem.trim()) { this.issue.set({ message: 'Se requiere certificado CA para TLS verify-full.', conflict: false }); return; }
    this.testId = ''; this.testedConnection = null; this.busy.set(true);
    const body = { mode: values.mode, host: values.host, approved_address: values.approved_address,
      port: values.port, ca_pem: values.ca_pem, runtime_password: values.runtime_password,
      migrator_password: values.migrator_password, sslmode: 'verify-full', database: 'ocoteAppDatabase', runtime_role: 'ocote_runtime', migrator_role: 'ocote_migrador' };
    try {
      const result = await firstValueFrom(this.http.post<{ test_id: string }>('/api/v1/setup/connection-tests', body, this.options()));
      this.testId = result.test_id; this.testedConnection = body;
      this.connection.patchValue({ runtime_password: '', migrator_password: '' }, { emitEvent: false });
      this.issue.set(null); this.advance(2);
    } catch (error) { await this.fail(error); }
    finally { this.busy.set(false); }
  }
  review(): void {
    if (this.admin.invalid || this.admin.controls.password.value !== this.admin.controls.confirmation.value) {
      this.issue.set({ message: 'Revisa los datos y la confirmacion de contrasena.', conflict: false }); return;
    }
    this.issue.set(null); this.advance(3);
  }
  async install(): Promise<void> {
    const local = this.connection.controls.mode.value === 'local';
    if (!this.approval.value || (!local && !this.testId) || !this.testedConnection || this.busy() || this.blocked() || this.admin.invalid) return;
    this.busy.set(true);
    const values = this.admin.getRawValue();
    try {
      const admin = { email: values.email, display_name: values.display_name, password: values.password, role: 'admin', reason: values.reason };
      await firstValueFrom(this.http.post(local ? '/api/v1/setup/local-install' : '/api/v1/setup/install', local ? {
        local: this.testedConnection, organization_timezone: values.timezone, admin,
      } : { connection: this.testedConnection, test_id: this.testId, organization_timezone: values.timezone, admin }, this.options()));
      this.clear(); this.blocked.set(true); await this.router.navigateByUrl('/login', { replaceUrl: true });
    } catch (error) { this.clear(); this.blocked.set(true); await this.fail(error); }
    finally { this.busy.set(false); }
  }
  private async fail(error: unknown): Promise<void> {
    this.issue.set(problem(error));
    const code = error instanceof HttpErrorResponse ? error.error?.code : '';
    if (['SETUP_SEALED', 'SETUP_DATABASE_NOT_EMPTY', 'SETUP_RECOVERY_REQUIRED', 'SETUP_LOCAL_EXISTING_STATE', 'SETUP_LOCAL_RECOVERY_REQUIRED'].includes(code)) {
      this.clear(); this.blocked.set(true);
      if (code === 'SETUP_SEALED') await this.router.navigateByUrl('/login', { replaceUrl: true });
    }
  }
  private advance(index: number): void {
    this.step.set(index);
    afterNextRender(() => { const wizard = this.wizard(); if (wizard && !this.blocked()) wizard.selectedIndex = index; }, { injector: this.injector });
  }
  private clear(): void { this.code = ''; this.testId = ''; this.testedConnection = null; this.pairing.reset(); this.connection.reset(); this.admin.reset(); this.approval.reset(); }
  ngOnDestroy(): void { this.subscription.unsubscribe(); this.modeSubscription.unsubscribe(); this.clear(); }
}