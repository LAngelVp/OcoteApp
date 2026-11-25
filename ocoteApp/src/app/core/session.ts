import { HttpClient, HttpContext, HttpContextToken, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject, Injectable, InjectionToken, OnDestroy, signal } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, firstValueFrom, from, switchMap, throwError } from 'rxjs';

export type Role = 'admin' | 'gerente' | 'lider' | 'colaborador';
export interface User {
  id: string; email: string; display_name: string; role: Role;
  department_id: string | null; permissions: string[];
}
interface Tokens { access_token: string; csrf_token: string; expires_in: number; }
export const NO_SESSION = new HttpContextToken(() => false);
export interface SessionLock { run<T>(action: () => Promise<T>): Promise<T>; }
export const SESSION_LOCK = new InjectionToken<SessionLock>('Same-origin session lock', { providedIn: 'root', factory: () => ({
  run: async action => {
    if (!navigator.locks) throw new HttpErrorResponse({ status:503,error:{ code:'SESSION_COORDINATION_UNAVAILABLE' } });
    return await navigator.locks.request('ocote-auth-session', action);
  },
}) });

@Injectable({ providedIn: 'root' })
export class Session implements OnDestroy {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly sessionLock = inject(SESSION_LOCK);
  private access: string | null = null;
  private csrf: string | null = null;
  private restoration?: Promise<void>;
  private rotation?: Promise<void>;
  private readonly channel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('ocote-session');
  readonly user = signal<User | null>(null);
  readonly ready = signal(false);

  constructor() {
    if (this.channel) this.channel.onmessage = event => {
      if (event.data === 'signed-out') this.expire();
    };
  }
  token(): string | null { return this.access; }
  has(permission: string): boolean { return this.user()?.permissions.includes(permission) ?? false; }
  private options() { return { context: new HttpContext().set(NO_SESSION, true), withCredentials: true }; }
  private lock<T>(action: () => Promise<T>): Promise<T> {
    return this.sessionLock.run(action);
  }
  ngOnDestroy(): void { this.channel?.close(); }
  private accept(tokens: Tokens): void { this.access = tokens.access_token; this.csrf = tokens.csrf_token; }
  private async profile(): Promise<void> {
    const user = await firstValueFrom(this.http.get<User>('/api/v1/auth/me', {
      ...this.options(), headers: { Authorization: 'Bearer ' + this.access },
    }));
    this.user.set(user);
  }
  restore(): Promise<void> {
    return this.restoration ??= this.refresh().catch(() => this.clear()).finally(() => this.ready.set(true));
  }
  async login(email: string, password: string): Promise<void> {
    await this.lock(async () => {
      const tokens = await firstValueFrom(this.http.post<Tokens>('/api/v1/auth/login', { email, password }, this.options()));
      this.accept(tokens);
      try { await this.profile(); } catch (error) { this.clear(); throw error; }
    });
    this.ready.set(true);
  }
  refresh(): Promise<void> {
    return this.rotation ??= this.lock(async () => {
      const csrf = await firstValueFrom(this.http.get<{ csrf_token: string }>('/api/v1/auth/csrf', this.options()));
      const tokens = await firstValueFrom(this.http.post<Tokens>('/api/v1/auth/refresh', {}, {
        ...this.options(), headers: { 'X-CSRF-Token': csrf.csrf_token },
      }));
      this.accept(tokens);
      await this.profile();
    }).catch(error => { this.expire(); throw error; }).finally(() => { this.rotation = undefined; });
  }
  async logout(): Promise<void> {
    await this.lock(async () => {
      try {
        const csrf = await firstValueFrom(this.http.get<{ csrf_token: string }>('/api/v1/auth/csrf', this.options()));
        await firstValueFrom(this.http.post('/api/v1/auth/logout', {}, {
          ...this.options(), headers: { 'X-CSRF-Token': csrf.csrf_token },
        }));
      } catch (error) {
        if (error instanceof HttpErrorResponse && error.status === 401) {
          this.channel?.postMessage('signed-out');
          this.expire();
        }
        throw error;
      }
      this.channel?.postMessage('signed-out');
      this.expire();
    });
  }
  async changePassword(current_password: string, new_password: string): Promise<void> {
    await firstValueFrom(this.http.post('/api/v1/auth/change-password', { current_password, new_password }));
    this.channel?.postMessage('signed-out');
    this.expire();
  }
  headers(): Record<string, string> {
    return { ...(this.access ? { Authorization: 'Bearer ' + this.access } : {}), ...(this.csrf ? { 'X-CSRF-Token': this.csrf } : {}) };
  }
  private clear(): void { this.access = null; this.csrf = null; this.user.set(null); }
  expire(): void {
    this.clear();
    if (this.ready()) void this.router.navigateByUrl('/login');
  }
}

export const sessionInterceptor: HttpInterceptorFn = (request, next) => {
  if (!request.url.startsWith('/api/v1/') || request.context.get(NO_SESSION)) return next(request);
  const session = inject(Session);
  const sentToken = session.token();
  const authorized = () => request.clone({ setHeaders: session.headers(), withCredentials: true });
  return next(authorized()).pipe(catchError(error => {
    if (!(error instanceof HttpErrorResponse) || error.status !== 401) return throwError(() => error);
    const rotation = sentToken && sentToken !== session.token() ? Promise.resolve() : session.refresh();
    return from(rotation).pipe(switchMap(() => next(authorized()).pipe(catchError(retryError => {
      if (retryError instanceof HttpErrorResponse && retryError.status === 401) session.expire();
      return throwError(() => retryError);
    }))));
  }));
};

export const signedIn: CanActivateFn = async () => {
  const session = inject(Session), router = inject(Router);
  await session.restore();
  return !!session.user() || router.parseUrl('/login');
};
export const permitted: CanActivateFn = route => {
  const session = inject(Session), router = inject(Router);
  const permissions = (route.data['permissions'] ?? [route.data['permission']]) as string[];
  return permissions.some(permission => session.has(permission)) || router.parseUrl('/sin-permiso');
};