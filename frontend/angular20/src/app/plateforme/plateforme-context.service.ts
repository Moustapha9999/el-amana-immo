import { Injectable, computed, signal } from '@angular/core';
import {
  LEGACY_ROOT_MODULE_CODE,
  resolveEspacePathForModule,
  resolveModuleEntryPath,
} from './module-routing.contract';

const STORAGE_KEY = 'bea_module_nav_context';

export interface ModuleNavContext {
  moduleCode: string;
  moduleTitre: string;
  entryPath: string;
  espaceRoute: string;
  espaceTitre: string;
}

const DEFAULT_IMMO: ModuleNavContext = {
  moduleCode: LEGACY_ROOT_MODULE_CODE,
  moduleTitre: 'Immobilisations & Amortissements',
  entryPath: '/dashboard',
  espaceRoute: '/comptabilite',
  espaceTitre: 'Comptabilité',
};

function readStored(): ModuleNavContext | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as ModuleNavContext;
    if (!parsed?.moduleCode || !parsed?.espaceRoute) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

/**
 * Contexte navigation module (espace + titres) — alimenté par l’API Login 2.
 * Sert au logout module et au fil d’Ariane (plus de /comptabilite hardcodé hors contrat).
 */
@Injectable({ providedIn: 'root' })
export class PlateformeContextService {
  private readonly ctx = signal<ModuleNavContext | null>(readStored());

  readonly context = this.ctx.asReadonly();
  readonly espaceRoute = computed(() => this.ctx()?.espaceRoute ?? '/accueil');
  readonly espaceTitre = computed(() => this.ctx()?.espaceTitre ?? 'BEA DIGITAL');
  readonly moduleTitre = computed(() => this.ctx()?.moduleTitre ?? 'Module');
  readonly entryPath = computed(() => this.ctx()?.entryPath ?? '/accueil');

  setFromModuleInfo(info: {
    moduleCode: string;
    titre?: string | null;
    entry_path?: string | null;
    espace_route?: string | null;
    espace_titre?: string | null;
  }): void {
    const next: ModuleNavContext = {
      moduleCode: info.moduleCode,
      moduleTitre:
        (info.titre || '').trim() ||
        (info.moduleCode === LEGACY_ROOT_MODULE_CODE
          ? DEFAULT_IMMO.moduleTitre
          : info.moduleCode),
      entryPath:
        (info.entry_path || '').trim() ||
        resolveModuleEntryPath(info.moduleCode),
      espaceRoute:
        (info.espace_route || '').trim() ||
        resolveEspacePathForModule(info.moduleCode),
      espaceTitre:
        (info.espace_titre || '').trim() ||
        (info.moduleCode === LEGACY_ROOT_MODULE_CODE ? DEFAULT_IMMO.espaceTitre : 'Département'),
    };
    this.ctx.set(next);
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }

  /** Chemin retour après déconnexion module (jamais /login). */
  espacePathFor(moduleCode: string | null): string {
    const current = this.ctx();
    if (moduleCode && current?.moduleCode === moduleCode && current.espaceRoute) {
      return current.espaceRoute;
    }
    return resolveEspacePathForModule(moduleCode);
  }

  clear(): void {
    this.ctx.set(null);
    sessionStorage.removeItem(STORAGE_KEY);
  }

  /** Contexte pour le shell immo (legacy-root) si pas encore hydraté. */
  ensureLegacyImmoDefaults(): ModuleNavContext {
    const current = this.ctx();
    if (current?.moduleCode === LEGACY_ROOT_MODULE_CODE) {
      return current;
    }
    if (!current) {
      this.ctx.set(DEFAULT_IMMO);
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(DEFAULT_IMMO));
      return DEFAULT_IMMO;
    }
    return current;
  }
}
