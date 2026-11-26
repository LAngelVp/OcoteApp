import { Component, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Session } from './core/session';
import { Configuration } from './core/configuration';
import { Feedback } from './shared/feedback';
import { problem, Problem } from './core/problem';

@Component({
    imports: [RouterLink, RouterLinkActive, RouterOutlet, MatButtonModule, MatIconModule, MatTooltipModule, Feedback],
    template: `<a class="skip-link" href="#contenido">Saltar al contenido</a>
    <header class="app-header"><a class="brand" routerLink="/tareas" aria-label="OCOTE, espacio de trabajo">@if (configuration.logo(); as logo) { <picture><img [src]="logo" width="256" height="256" [alt]="configuration.branding()['organization_name'] || 'OCOTE'" (error)="configuration.logoFailed()"></picture> } @else { <picture><source media="(min-width: 1280px)" srcset="/logos/ocote-text.webp"><img src="/logos/ocote-icon.png" width="256" height="256" alt="OCOTE"></picture> }</a>
      <span class="environment">LOCAL</span><div class="account"><a routerLink="/perfil">{{ session.user()?.display_name }} <small>{{ session.user()?.role }}</small></a>
      <button mat-icon-button aria-label="Cerrar sesion" matTooltip="Cerrar sesion" [disabled]="leaving()" (click)="logout()"><mat-icon>logout</mat-icon></button></div></header>
    <div class="app-layout"><nav class="main-nav" aria-label="Principal"><p class="nav-label">ESPACIO DE TRABAJO</p>
      @if (session.user()?.role !== 'colaborador') { <a routerLink="/planes" routerLinkActive="active" ariaCurrentWhenActive="page"><mat-icon>calendar_month</mat-icon>Planes</a>
      <a routerLink="/objetivos" routerLinkActive="active" ariaCurrentWhenActive="page"><mat-icon>flag</mat-icon>Objetivos</a> }
      <a routerLink="/tareas" routerLinkActive="active" ariaCurrentWhenActive="page"><mat-icon>task_alt</mat-icon>Tareas</a>
      @if (configuration.enabled('kanban')) { <a routerLink="/kanban" routerLinkActive="active" ariaCurrentWhenActive="page"><mat-icon>view_kanban</mat-icon>Kanban</a> }
      @if (configuration.enabled('timeline')) { <a routerLink="/timeline" routerLinkActive="active" ariaCurrentWhenActive="page"><mat-icon>timeline</mat-icon>Timeline</a> }
      @if (session.has('date-requests:create')) { <a routerLink="/solicitudes-fecha" routerLinkActive="active" ariaCurrentWhenActive="page"><mat-icon>event_repeat</mat-icon>Solicitudes de fecha</a> }
      @if (session.has('analytics:read') && configuration.enabled('analytics')) { <a routerLink="/analitica" routerLinkActive="active" ariaCurrentWhenActive="page"><mat-icon>monitoring</mat-icon>Analitica</a> }
      @if (session.has('evaluations:read')) { <a routerLink="/evaluaciones" routerLinkActive="active" ariaCurrentWhenActive="page"><mat-icon>fact_check</mat-icon>Evaluaciones</a> }
      @if (session.has('administration:manage')) { <p class="nav-label">ADMINISTRACION</p>
        @for (item of adminLinks; track item.path) { <a [routerLink]="'/administracion/' + item.path" routerLinkActive="active" ariaCurrentWhenActive="page"><mat-icon>{{ item.icon }}</mat-icon>{{ item.label }}</a> }
      }<a routerLink="/perfil" routerLinkActive="active" ariaCurrentWhenActive="page"><mat-icon>account_circle</mat-icon>Mi perfil</a>
    </nav><main id="contenido" class="workspace" tabindex="-1"><ocote-feedback [issue]="issue()" /><router-outlet (activate)="focusContent()" /></main></div>`
})
export class Shell {
  readonly session = inject(Session);
  readonly configuration = inject(Configuration);
  readonly leaving = signal(false);
  readonly issue = signal<Problem | null>(null);
  readonly adminLinks = [
    { path: 'infraestructura', label: 'Salud y custodia', icon: 'health_and_safety' },
    { path: 'configuracion', label: 'Configuracion', icon: 'tune' },
    { path: 'departamentos', label: 'Departamentos', icon: 'domain' },
    { path: 'usuarios', label: 'Usuarios', icon: 'group' },
    { path: 'etapas', label: 'Etapas', icon: 'account_tree' },
    { path: 'transiciones', label: 'Transiciones', icon: 'sync_alt' },
    { path: 'prioridades', label: 'Prioridades', icon: 'low_priority' },
    { path: 'horizontes', label: 'Horizontes', icon: 'date_range' },
    { path: 'parametros', label: 'Parametros', icon: 'settings' },
    { path: 'auditoria', label: 'Auditoria', icon: 'history' },
    { path: 'releases', label: 'Releases', icon: 'inventory_2' },
  ];
  focusContent(): void { queueMicrotask(() => document.getElementById('contenido')?.focus()); }
  async logout(): Promise<void> {
    this.leaving.set(true); this.issue.set(null);
    try { await this.session.logout(); } catch (error) { this.issue.set(problem(error)); }
    finally { this.leaving.set(false); }
  }
}

@Component({
    imports: [RouterLink, MatButtonModule], template: `<section class="empty-state"><h1>Acceso no disponible</h1><p>Esta ruta no esta disponible para tu cuenta.</p><a mat-stroked-button routerLink="/tareas">Volver a tareas</a></section>`
})
export class UnavailablePage {}