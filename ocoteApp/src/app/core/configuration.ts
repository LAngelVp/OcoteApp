import { DestroyRef, effect, inject, Injectable, signal, untracked } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { Api, Row } from './api';
import { Session } from './session';

export const BRAND_TOKENS: Record<string, string> = {
  primary: '#B85A1E', 'primary-dark': '#7A3810', 'on-primary': '#FFFFFF', focus: '#2B5B84',
};
export function luminance(color: string): number {
  if (!/^#[0-9a-f]{6}$/i.test(color)) return NaN;
  const channels = [1, 3, 5].map(offset => parseInt(color.slice(offset, offset + 2), 16) / 255)
    .map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
  return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
}
export function contrast(foreground: string, background: string): number {
  const values = [luminance(foreground), luminance(background)];
  return (Math.max(...values) + .05) / (Math.min(...values) + .05);
}
export function brandingContrast(overrides: Row): Record<string, number> {
  const palette = { ...BRAND_TOKENS, ...overrides } as Record<string, string>;
  if (Object.keys(overrides).some(key => !(key in BRAND_TOKENS))) return { invalid: NaN };
  return { normal: contrast(palette['on-primary'], palette['primary']),
    hover: contrast(palette['on-primary'], palette['primary-dark']),
    outline: contrast(palette['primary-dark'], '#FFFFFF'),
    focus_surface: contrast(palette['focus'], '#FFFFFF'), focus_background: contrast(palette['focus'], '#F6F4F0'),
    error: contrast('#B83227', '#FFFFFF') };
}
export const passesAA = (values: Record<string, number>): boolean => Object.values(values).every(value => Number.isFinite(value) && value >= 4.5);

@Injectable({ providedIn: 'root' })
export class Configuration {
  private readonly api = inject(Api);
  private readonly session = inject(Session);
  private readonly destroy = inject(DestroyRef);
  readonly value = signal<Row | null>(null);
  readonly logo = signal<string | null>(null);
  private epoch = 0;
  constructor() {
    effect(() => { const user=this.session.user(); untracked(() => { if (user) void this.reload(); else this.clear(); }); });
    inject(Router).events.pipe(takeUntilDestroyed()).subscribe(event => {
      if (event instanceof NavigationEnd && this.session.user()) void this.reload();
    });
    this.destroy.onDestroy(() => this.clear());
  }
  enabled(code: string): boolean { return (this.value()?.['flags'] as Row | undefined)?.[code] === true; }
  branding(): Row { return this.value()?.['branding'] as Row ?? {}; }
  logoFailed(): void { this.clearLogo(); }
  private clearLogo(): void { const current = this.logo(); if (current) URL.revokeObjectURL(current); this.logo.set(null); }
  clear(): void {
    ++this.epoch; this.value.set(null); this.clearLogo();
    for (const token of Object.keys(BRAND_TOKENS)) document.documentElement.style.removeProperty('--ocote-' + token);
  }
  async reload(): Promise<void> {
    const epoch = ++this.epoch;
    try {
      const value = await this.api.get('/configuration');
      if (epoch !== this.epoch || !this.session.user()) return;
      this.value.set(value); this.clearLogo();
      const branding = value['branding'] as Row | undefined;
      const overrides = branding?.['token_overrides'] as Row ?? {};
      for (const token of Object.keys(BRAND_TOKENS)) document.documentElement.style.removeProperty('--ocote-' + token);
      if (passesAA(brandingContrast(overrides))) for (const [token, color] of Object.entries(overrides)) document.documentElement.style.setProperty('--ocote-' + token, String(color));
      const identity = branding?.['logo_asset_id'];
      if (identity) {
        const content = await this.api.logo(String(identity));
        if (epoch === this.epoch && this.session.user() && ['image/png', 'image/jpeg'].includes(content.type) && content.size <= 1048576) this.logo.set(URL.createObjectURL(content));
      }
    } catch { if (epoch === this.epoch) this.clear(); }
  }
}