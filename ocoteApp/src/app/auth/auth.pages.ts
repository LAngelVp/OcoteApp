import { DatePipe } from '@angular/common';
import { Component, effect, inject, InjectionToken, OnDestroy, OnInit, signal, untracked } from '@angular/core';
import { ReactiveFormsModule, FormControl, FormGroup, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Api, Page, Row, text, version } from '../core/api';
import { Configuration } from '../core/configuration';
import { Session, SSOProvider, SSOStart, SSOStatus } from '../core/session';
import { Problem, problem } from '../core/problem';
import { Feedback } from '../shared/feedback';
import { Editor, reason } from '../shared/editor';
import { Pager, Pagination } from '../shared/pager';

export function ssoDestination(value: string): string {
  const destination = new URL(value);
  if (destination.protocol !== 'https:' || destination.username || destination.password || destination.hash) throw new Error('Invalid SSO destination');
  return destination.href;
}
export const SSO_NAVIGATION = new InjectionToken<(url: string) => void>('SSO navigation', {
  providedIn: 'root', factory: () => url => window.location.assign(ssoDestination(url)),
});

@Component({
    imports: [ReactiveFormsModule, MatButtonModule, MatFormFieldModule, MatInputModule, MatIconModule, Feedback],
    template: `<main class="login-page"><div class="login-brand"><img src="/logos/ocote-complete.webp" width="1200" height="660" alt="OCOTE: Sistema de Gestion y Evaluacion" fetchpriority="high">
    <h1 class="sr-only">OCOTE</h1></div>
    <section class="login-form" aria-labelledby="login-title"><h2 id="login-title">Iniciar sesion</h2>
    <ocote-feedback [issue]="issue()" />
    @if (completion(); as transaction) {
      <section class="sso-return" aria-labelledby="sso-title"><h3 id="sso-title">{{ transaction.provider_name }}</h3>
        <p>{{ transaction.purpose === 'probe' ? 'Prueba de identidad pendiente de confirmacion' : transaction.purpose === 'bind' ? 'Vinculo de identidad pendiente de confirmacion' : 'Identidad empresarial verificada' }}</p>
        <button mat-flat-button type="button" (click)="complete()" [disabled]="busy() || (transaction.purpose !== 'login' && !session.user())">
          <mat-icon>verified_user</mat-icon>{{ transaction.purpose === 'probe' ? 'Registrar prueba' : transaction.purpose === 'bind' ? 'Vincular identidad' : 'Continuar' }}</button>
        <button mat-button type="button" (click)="discard()" [disabled]="busy()">Descartar</button>
      </section>
    }
    @if (directory(); as selected) {
      <form [formGroup]="directoryForm" (ngSubmit)="submitDirectory()" [attr.aria-busy]="busy()"><h3>{{ selected.provider.name }}</h3>
        <mat-form-field><mat-label>Usuario del directorio</mat-label><input matInput formControlName="username" autocomplete="username" required><mat-error>Introduce tu usuario.</mat-error></mat-form-field>
        <mat-form-field><mat-label>Contrasena del directorio</mat-label><input matInput type="password" formControlName="password" autocomplete="current-password" required><mat-error>Introduce tu contrasena.</mat-error></mat-form-field>
        <button mat-flat-button type="submit" [disabled]="busy() || directoryForm.invalid"><mat-icon>login</mat-icon>Entrar al directorio</button>
        <button mat-button type="button" (click)="discard()" [disabled]="busy()">Cancelar</button>
      </form>
    }
    @if (!session.user() && !directory()) {
    <form [formGroup]="form" (ngSubmit)="submit()" [attr.aria-busy]="busy()"><h3>Acceso local</h3>
      <mat-form-field><mat-label>Correo electronico</mat-label><input matInput type="email" formControlName="email" autocomplete="username" required>
        <mat-error>Introduce un correo valido.</mat-error></mat-form-field>
      <mat-form-field><mat-label>Contrasena</mat-label><input matInput type="password" formControlName="password" autocomplete="current-password" required>
        <mat-error>Introduce tu contrasena.</mat-error></mat-form-field>
      <button mat-flat-button type="submit" [disabled]="busy() || form.invalid">{{ busy() ? 'Verificando...' : 'Entrar' }}</button>
    </form>
    }
    @if (!completion() && !directory() && (providers().length || providerIssue())) {
      <section class="sso-providers" aria-labelledby="sso-providers-title"><h3 id="sso-providers-title">Acceso empresarial</h3>
        <ocote-feedback [issue]="providerIssue()" />
        @for (provider of providers(); track provider.id) {
          <button mat-stroked-button type="button" (click)="selectProvider(provider)" [disabled]="busy()"><mat-icon>domain</mat-icon>{{ provider.name }}</button>
        }
        @if (nextCursor()) { <button mat-button type="button" (click)="loadProviders()" [disabled]="busy() || loadingProviders()"><mat-icon>expand_more</mat-icon>Mas proveedores</button> }
      </section>
    }
    </section><footer>Entorno local · Acceso restringido</footer></main>`
})
export class LoginPage implements OnInit, OnDestroy {
  readonly session = inject(Session);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly navigateSSO = inject(SSO_NAVIGATION);
  readonly busy = signal(false);
  readonly issue = signal<Problem | null>(null);
  readonly providers = signal<SSOProvider[]>([]);
  readonly nextCursor = signal<string | null>(null);
  readonly providerIssue = signal<Problem | null>(null);
  readonly loadingProviders = signal(false);
  readonly completion = signal<SSOStatus | null>(null);
  readonly directory = signal<{ provider: SSOProvider; start: SSOStart } | null>(null);
  private destroyed = false;
  readonly directoryForm = new FormGroup({
    username: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.maxLength(254)] }),
    password: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.maxLength(16384)] }),
  });
  readonly form = new FormGroup({
    email: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.email, Validators.maxLength(254)] }),
    password: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.maxLength(128)] }),
  });
  async ngOnInit(): Promise<void> {
    const transaction = this.route.snapshot.queryParamMap.get('sso_transaction');
    if (transaction !== null) {
      await this.router.navigate([], { relativeTo: this.route, queryParams: {}, replaceUrl: true });
      this.busy.set(true);
      try {
        if (!/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(transaction)) throw new Error('Invalid SSO transaction');
        const status = await this.session.ssoStatus(transaction);
        if (status.transaction_id !== transaction || !['login', 'bind', 'probe'].includes(status.purpose)) throw new Error('Invalid SSO purpose');
        if (status.purpose !== 'login') await this.session.restore();
        if (!this.destroyed) this.completion.set(status);
      } catch (error) { if (!this.destroyed) this.issue.set(problem(error)); }
      finally { this.busy.set(false); }
      return;
    }
    await this.session.restore();
    if (this.destroyed) return;
    if (this.session.user()) await this.router.navigateByUrl('/tareas');
    else await this.loadProviders();
  }
  async loadProviders(): Promise<void> {
    if (this.loadingProviders()) return;
    this.loadingProviders.set(true); this.providerIssue.set(null);
    try {
      const page = await this.session.ssoProviders(this.nextCursor() ?? '');
      if (!this.destroyed) {
        const known = new Set(this.providers().map(provider => provider.id));
        this.providers.update(rows => [...rows, ...page.items.filter(provider => !known.has(provider.id))]);
        this.nextCursor.set(page.next_cursor);
      }
    } catch (error) { if (!this.destroyed) this.providerIssue.set(problem(error)); }
    finally { this.loadingProviders.set(false); }
  }
  async selectProvider(provider: SSOProvider): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true); this.issue.set(null);
    try {
      const start = await this.session.startSSO(provider.id);
      if (this.destroyed) return;
      if (provider.provider === 'ldap' && start.authorization_url === null && start.state) this.directory.set({ provider, start });
      else if (provider.provider !== 'ldap' && start.authorization_url) this.navigateSSO(ssoDestination(start.authorization_url));
      else throw new Error('Invalid SSO start');
    } catch (error) { this.issue.set(problem(error)); }
    finally { this.busy.set(false); }
  }
  async submitDirectory(): Promise<void> {
    const selected = this.directory();
    if (!selected || this.directoryForm.invalid || this.busy()) return;
    this.busy.set(true); this.issue.set(null);
    const { username, password } = this.directoryForm.getRawValue();
    try {
      await this.session.ldapSSO(selected.provider.id, selected.start, username, password);
      this.directory.set(null);
      await this.session.finishSSO(selected.start.transaction_id, 'login');
      if (!this.destroyed) await this.router.navigateByUrl('/tareas');
    } catch (error) { this.directory.set(null); this.issue.set(problem(error)); }
    finally { this.directoryForm.controls.password.reset(); this.busy.set(false); }
  }
  async complete(): Promise<void> {
    const transaction = this.completion();
    if (!transaction || this.busy() || (transaction.purpose !== 'login' && !this.session.user())) return;
    this.busy.set(true); this.issue.set(null);
    try {
      await this.session.finishSSO(transaction.transaction_id, transaction.purpose);
      this.completion.set(null);
      if (!this.destroyed) await this.router.navigateByUrl(transaction.purpose === 'probe' ? '/administracion/integraciones' : transaction.purpose === 'bind' ? '/perfil' : '/tareas');
    } catch (error) { this.issue.set(problem(error)); }
    finally { this.busy.set(false); }
  }
  discard(): void {
    this.completion.set(null); this.directory.set(null); this.directoryForm.reset(); this.form.controls.password.reset(); this.issue.set(null);
    if (this.session.user()) void this.router.navigateByUrl('/perfil');
    else if (!this.providers().length) void this.loadProviders();
  }
  ngOnDestroy(): void { this.destroyed = true; this.directoryForm.reset(); this.form.controls.password.reset(); this.directory.set(null); this.completion.set(null); }
  async submit(): Promise<void> {
    if (this.form.invalid || this.busy()) return;
    this.busy.set(true); this.issue.set(null);
    const { email, password } = this.form.getRawValue();
    try { await this.session.login(email, password); this.form.controls.password.reset(); if (!this.completion()) await this.router.navigateByUrl('/tareas'); }
    catch (error) { this.form.controls.password.reset(); this.issue.set(problem(error)); }
    finally { this.busy.set(false); }
  }
}

@Component({
  selector: 'ocote-external-identities',
  imports: [DatePipe, MatButtonModule, MatIconModule, MatTooltipModule, Pager, Feedback],
  styles: [`:host{display:block;min-width:0}.identity{padding:16px 0;border-bottom:1px solid var(--ocote-border);display:flex;justify-content:space-between;gap:12px}.identity div{min-width:0;overflow-wrap:anywhere}.providers{display:flex;gap:8px;flex-wrap:wrap}.providers button{height:auto;min-height:44px;white-space:normal;overflow-wrap:anywhere}.meta{color:var(--ocote-text-secondary);font-size:.875rem}`],
  template: `@if (available()) { <section aria-labelledby="identities-title"><h2 id="identities-title">Identidades empresariales</h2><ocote-feedback [issue]="issue()" />
    @if (loading()) { <p role="status">Cargando identidades...</p> }
    @for (binding of rows(); track binding['id']) { <div class="identity"><div><strong>{{ binding['issuer'] }}</strong><p>{{ binding['subject'] }}</p><p class="meta">{{ binding['revoked_at'] ? 'Revocada' : 'Activa' }} · {{ asText(binding, 'last_authenticated_at') | date:'medium' }}</p></div>
      <button mat-icon-button aria-label="Revocar identidad" matTooltip="Revocar identidad" [disabled]="!!binding['revoked_at'] || loading()" (click)="revoke(binding)"><mat-icon>link_off</mat-icon></button></div>
    } @empty { @if (!loading()) { <p>Sin identidades vinculadas.</p> } }
    <ocote-pager [state]="pagination" [busy]="loading()" (navigate)="load($event)" (sizeChange)="resize($event)" />
    <div class="providers">@for (provider of providers(); track provider.id) { <button mat-stroked-button [disabled]="loading()" (click)="bind(provider)"><mat-icon>add_link</mat-icon>{{ provider.name }}</button> }
      @if (nextProvider()) { <button mat-button [disabled]="loading()" (click)="moreProviders()"><mat-icon>expand_more</mat-icon>Mas proveedores</button> }
    </div></section> }`,
})
export class ExternalIdentities implements OnDestroy {
  private readonly api = inject(Api); private readonly dialog = inject(MatDialog);
  private readonly session = inject(Session); private readonly configuration = inject(Configuration);
  private readonly navigateSSO = inject(SSO_NAVIGATION);
  readonly asText = text; readonly pagination = new Pagination();
  readonly rows = signal<Row[]>([]); readonly providers = signal<SSOProvider[]>([]);
  readonly nextProvider = signal<string | null>(null);
  readonly issue = signal<Problem | null>(null); readonly loading = signal(false);
  private epoch = 0; private destroyed = false; private opened?: MatDialogRef<Editor>;
  constructor() { effect(() => { this.configuration.value(); this.session.user(); untracked(() => { this.pagination.reset(); this.providers.set([]); this.nextProvider.set(null); this.opened?.close(); void this.load(); }); }); }
  available(): boolean { return !!this.session.user() && this.configuration.enabled('integrations') && this.configuration.enabled('sso'); }
  async load(cursor = ''): Promise<void> {
    const epoch = ++this.epoch; this.rows.set([]); this.issue.set(null); this.loading.set(true);
    try {
      if (!this.available()) return;
      const page = await this.api.get<Page>('/auth/sso/identities', { limit: String(this.pagination.size()), ...(cursor ? { cursor } : {}) });
      if (epoch !== this.epoch || this.destroyed) return;
      this.rows.set(page.items); this.pagination.accept(cursor, page.next_cursor);
      if (!this.providers().length) await this.moreProviders();
    } catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); }
    finally { if (epoch === this.epoch) this.loading.set(false); }
  }
  resize(size: number): void { if (this.pagination.resize(size)) void this.load(); }
  async moreProviders(): Promise<void> {
    const epoch = this.epoch;
    try {
      const page = await this.session.ssoProviders(this.nextProvider() ?? '');
      if (epoch === this.epoch && !this.destroyed && this.available()) {
        const known = new Set(this.providers().map(provider => provider.id));
        this.providers.update(rows => [...rows, ...page.items.filter(provider => !known.has(provider.id))]); this.nextProvider.set(page.next_cursor);
      }
    } catch (error) { if (epoch === this.epoch) this.issue.set(problem(error)); }
  }
  bind(provider: SSOProvider): void {
    if (!this.available()) return;
    let start: SSOStart | null = null;
    this.opened = this.dialog.open(Editor, { width: '480px', maxWidth: '96vw', data: {
      title: 'Vincular ' + provider.name,
      fields: [{ key: 'current_password', label: 'Contrasena local actual', type: 'password', required: true, min: 1, max: 128 }],
      submit: async (values: Row) => { start = await this.session.startSSO(provider.id, 'bind', String(values['current_password'])); if (start.authorization_url) ssoDestination(start.authorization_url); },
    } });
    this.opened.afterClosed().subscribe(result => {
      if (result !== true || !start || this.destroyed || !this.available()) return;
      if (start.authorization_url) this.navigateSSO(start.authorization_url);
      else if (provider.provider === 'ldap' && start.state) this.bindDirectory(provider, start);
    });
  }
  private bindDirectory(provider: SSOProvider, start: SSOStart): void {
    this.opened = this.dialog.open(Editor, { width: '480px', maxWidth: '96vw', data: {
      title: provider.name, fields: [{ key: 'username', label: 'Usuario del directorio', required: true, max: 254 }, { key: 'password', label: 'Contrasena del directorio', type: 'password', required: true, min: 1, max: 16384 }],
      submit: async (values: Row) => { await this.session.ldapSSO(provider.id, start, String(values['username']), String(values['password'])); await this.session.finishSSO(start.transaction_id, 'bind'); },
    } });
    this.opened.afterClosed().subscribe(result => { if (result === true && !this.destroyed) void this.load(); });
  }
  revoke(binding: Row): void {
    if (!this.available() || binding['revoked_at']) return;
    this.opened = this.dialog.open(Editor, { width: '560px', maxWidth: '96vw', data: {
      title: 'Revocar identidad empresarial', fields: [{ key: 'current_password', label: 'Contrasena local actual', type: 'password', required: true, min: 1, max: 128 }, { ...reason(), max: 1000 }],
      submit: (values: Row) => this.api.command('/auth/sso/identities/' + text(binding, 'id') + '/revoke', { ...values, expected_version: version(binding) }),
    } });
    this.opened.afterClosed().subscribe(result => { if ((result === true || result === 'reload') && !this.destroyed) void this.load(); });
  }
  ngOnDestroy(): void { this.destroyed = true; ++this.epoch; this.opened?.close(); this.rows.set([]); this.providers.set([]); }
}

@Component({
    imports: [ReactiveFormsModule, MatButtonModule, MatFormFieldModule, MatInputModule, Feedback, ExternalIdentities],
    template: `<header class="page-heading"><div><p class="eyebrow">CUENTA</p><h1>Mi perfil</h1></div></header>
    <section class="profile"><dl><dt>Nombre</dt><dd>{{ session.user()?.display_name }}</dd><dt>Correo</dt><dd>{{ session.user()?.email }}</dd>
      <dt>Rol</dt><dd>{{ session.user()?.role }}</dd></dl>
      <form class="narrow-form" [formGroup]="form" (ngSubmit)="submit()"><h2>Cambiar contrasena</h2><ocote-feedback [issue]="issue()" />
      <mat-form-field><mat-label>Contrasena actual</mat-label><input matInput type="password" formControlName="current_password" autocomplete="current-password" required><mat-error>Campo obligatorio.</mat-error></mat-form-field>
      <mat-form-field><mat-label>Nueva contrasena</mat-label><input matInput type="password" formControlName="new_password" autocomplete="new-password" required><mat-hint>Entre 12 y 128 caracteres.</mat-hint><mat-error>Usa entre 12 y 128 caracteres.</mat-error></mat-form-field>
      <mat-form-field><mat-label>Confirmar nueva contrasena</mat-label><input matInput type="password" formControlName="confirmation" autocomplete="new-password" required><mat-error>Confirma la nueva contrasena.</mat-error></mat-form-field>
      @if (mismatch()) { <p role="alert">Las contrasenas no coinciden.</p> }
      <p>Este cambio cerrara tus sesiones.</p><button mat-flat-button [disabled]="busy() || form.invalid">Cambiar contrasena</button>
    </form></section><ocote-external-identities />`
})
export class ProfilePage {
  readonly session = inject(Session);
  readonly busy = signal(false);
  readonly mismatch = signal(false);
  readonly issue = signal<Problem | null>(null);
  readonly form = new FormGroup({
    current_password: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.maxLength(128)] }),
    new_password: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(12), Validators.maxLength(128)] }),
    confirmation: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
  });
  async submit(): Promise<void> {
    if (this.form.invalid || this.busy()) return;
    const values = this.form.getRawValue();
    this.mismatch.set(values.new_password !== values.confirmation);
    if (this.mismatch()) return;
    this.busy.set(true); this.issue.set(null);
    try { await this.session.changePassword(values.current_password, values.new_password); }
    catch (error) { this.issue.set(problem(error)); }
    finally { this.form.reset(); this.busy.set(false); }
  }
}