import { Component, inject, OnInit, signal } from '@angular/core';
import { ReactiveFormsModule, FormControl, FormGroup, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { Session } from '../core/session';
import { Problem, problem } from '../core/problem';
import { Feedback } from '../shared/feedback';

@Component({
    imports: [ReactiveFormsModule, MatButtonModule, MatFormFieldModule, MatInputModule, Feedback],
    template: `<main class="login-page"><div class="login-brand"><img src="/logos/ocote-complete.webp" width="1200" height="660" alt="OCOTE: Sistema de Gestion y Evaluacion" fetchpriority="high">
    <h1 class="sr-only">OCOTE</h1></div>
    <section class="login-form" aria-labelledby="login-title"><h2 id="login-title">Iniciar sesion</h2>
    <ocote-feedback [issue]="issue()" />
    <form [formGroup]="form" (ngSubmit)="submit()" [attr.aria-busy]="busy()">
      <mat-form-field><mat-label>Correo electronico</mat-label><input matInput type="email" formControlName="email" autocomplete="username" required>
        <mat-error>Introduce un correo valido.</mat-error></mat-form-field>
      <mat-form-field><mat-label>Contrasena</mat-label><input matInput type="password" formControlName="password" autocomplete="current-password" required>
        <mat-error>Introduce tu contrasena.</mat-error></mat-form-field>
      <button mat-flat-button type="submit" [disabled]="busy() || form.invalid">{{ busy() ? 'Verificando...' : 'Entrar' }}</button>
    </form></section><footer>Entorno local · Acceso restringido</footer></main>`
})
export class LoginPage implements OnInit {
  readonly session = inject(Session);
  private readonly router = inject(Router);
  readonly busy = signal(false);
  readonly issue = signal<Problem | null>(null);
  readonly form = new FormGroup({
    email: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.email, Validators.maxLength(254)] }),
    password: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.maxLength(128)] }),
  });
  async ngOnInit(): Promise<void> { await this.session.restore(); if (this.session.user()) await this.router.navigateByUrl('/tareas'); }
  async submit(): Promise<void> {
    if (this.form.invalid || this.busy()) return;
    this.busy.set(true); this.issue.set(null);
    const { email, password } = this.form.getRawValue();
    try { await this.session.login(email, password); this.form.controls.password.reset(); await this.router.navigateByUrl('/tareas'); }
    catch (error) { this.form.controls.password.reset(); this.issue.set(problem(error)); }
    finally { this.busy.set(false); }
  }
}

@Component({
    imports: [ReactiveFormsModule, MatButtonModule, MatFormFieldModule, MatInputModule, Feedback],
    template: `<header class="page-heading"><div><p class="eyebrow">CUENTA</p><h1>Mi perfil</h1></div></header>
    <section class="profile"><dl><dt>Nombre</dt><dd>{{ session.user()?.display_name }}</dd><dt>Correo</dt><dd>{{ session.user()?.email }}</dd>
      <dt>Rol</dt><dd>{{ session.user()?.role }}</dd></dl>
      <form class="narrow-form" [formGroup]="form" (ngSubmit)="submit()"><h2>Cambiar contrasena</h2><ocote-feedback [issue]="issue()" />
      <mat-form-field><mat-label>Contrasena actual</mat-label><input matInput type="password" formControlName="current_password" autocomplete="current-password" required><mat-error>Campo obligatorio.</mat-error></mat-form-field>
      <mat-form-field><mat-label>Nueva contrasena</mat-label><input matInput type="password" formControlName="new_password" autocomplete="new-password" required><mat-hint>Entre 12 y 128 caracteres.</mat-hint><mat-error>Usa entre 12 y 128 caracteres.</mat-error></mat-form-field>
      <mat-form-field><mat-label>Confirmar nueva contrasena</mat-label><input matInput type="password" formControlName="confirmation" autocomplete="new-password" required><mat-error>Confirma la nueva contrasena.</mat-error></mat-form-field>
      @if (mismatch()) { <p role="alert">Las contrasenas no coinciden.</p> }
      <p>Este cambio cerrara tus sesiones.</p><button mat-flat-button [disabled]="busy() || form.invalid">Cambiar contrasena</button>
    </form></section>`
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