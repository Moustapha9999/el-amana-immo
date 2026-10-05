import { DOCUMENT } from '@angular/common';
import { Injectable, effect, inject, signal } from '@angular/core';
import { THEME_DARK_VERSION } from './theme-dark.version';

export type BeaTheme = 'light' | 'dark';

const STORAGE_KEY = 'bea.theme';
const DARK_SHEET_ID = 'bea-theme-dark';

/** Thème clair / sombre de BEA DIGITAL : préférence locale, sinon celle du système. */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly doc = inject(DOCUMENT);
  readonly theme = signal<BeaTheme>(this.initial());

  constructor() {
    effect(() => {
      const t = this.theme();
      const root = this.doc.documentElement;
      if (t === 'dark') this.chargerFeuilleSombre();
      root.dataset['theme'] = t;
      root.style.colorScheme = t;
    });
  }

  /** La feuille sombre (bundle non injecté) n'est téléchargée qu'au premier passage en mode sombre. */
  private chargerFeuilleSombre(): void {
    if (this.doc.getElementById(DARK_SHEET_ID)) return;
    const link = this.doc.createElement('link');
    link.id = DARK_SHEET_ID;
    link.rel = 'stylesheet';
    link.href = `theme-dark.css?v=${THEME_DARK_VERSION}`;
    this.doc.head.appendChild(link);
  }

  toggle(): void {
    const next: BeaTheme = this.theme() === 'dark' ? 'light' : 'dark';
    this.theme.set(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* stockage indisponible : le choix vaut pour la session */
    }
  }

  private initial(): BeaTheme {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === 'dark' || saved === 'light') return saved;
    } catch {
      /* stockage indisponible */
    }
    return this.doc.defaultView?.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
}
