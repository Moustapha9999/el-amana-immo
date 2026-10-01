import { HttpErrorResponse } from '@angular/common/http';

export interface CoreAdminRole {
  id: string;
  code: string;
  label: string;
  description?: string | null;
}

export interface CoreAdminRoleChoice {
  role: CoreAdminRole;
  profil: string;
}

export interface CoreAdminRoleGroup {
  key: string;
  title: string;
  espace: string;
  roles: CoreAdminRoleChoice[];
}

const IMMO_ROLE_CODES = new Set([
  'consultation',
  'lecture_seule',
  'creation',
  'modification',
  'validation',
  'comptable',
  'auditeur',
  'administrateur',
]);

const PROFIL_ORDER = [
  'lecteur',
  'lecture_seule',
  'consultation',
  'demandeur',
  'redacteur',
  'creation',
  'acheteur',
  'magasinier',
  'gestionnaire',
  'modification',
  'comptable',
  'valideur',
  'validation',
  'auditeur',
  'admin',
  'administrateur',
];

function roleModuleKey(code: string): string {
  const normalized = code.trim().toLowerCase();
  if (normalized.includes('.')) {
    return normalized.split('.')[0];
  }
  if (IMMO_ROLE_CODES.has(normalized)) {
    return 'immobilisations';
  }
  return `autre:${normalized}`;
}

function roleProfil(label: string): string {
  const parts = label.split(' — ');
  return (parts.length > 1 ? parts.slice(1).join(' — ') : label).trim();
}

function rolePrefix(label: string): string {
  const parts = label.split(' — ');
  return (parts.length > 1 ? parts[0] : '').trim();
}

function profilRank(code: string): number {
  const profil = (code.includes('.') ? code.split('.').pop() : code) || code;
  const index = PROFIL_ORDER.indexOf(profil.toLowerCase());
  return index === -1 ? PROFIL_ORDER.length : index;
}

export function groupAdminRoles(
  roles: CoreAdminRole[],
  catalogue: CoreAdminCatalogueEspace[],
): CoreAdminRoleGroup[] {
  const meta = new Map<string, { title: string; espace: string; order: number }>();
  let order = 0;
  for (const espace of catalogue) {
    for (const mod of espace.modules) {
      meta.set(mod.id, { title: mod.titre, espace: espace.titre, order: order++ });
    }
  }

  const buckets = new Map<string, CoreAdminRole[]>();
  for (const role of roles) {
    const key = roleModuleKey(role.code);
    const list = buckets.get(key) ?? [];
    list.push(role);
    buckets.set(key, list);
  }

  const groups: CoreAdminRoleGroup[] = [];
  for (const [key, items] of buckets) {
    const known = meta.get(key);
    const prefixes = [...new Set(items.map((role) => rolePrefix(role.label)).filter(Boolean))];
    const prefix = prefixes.length === 1 ? prefixes[0] : '';
    const moreSpecific = !!known && !!prefix && prefix !== known.title && prefix.startsWith(known.title);
    const title = moreSpecific ? prefix : known?.title || prefix || items[0]?.label || 'Autres';
    groups.push({
      key,
      title,
      espace: known?.espace ?? '',
      roles: [...items]
        .sort((a, b) => profilRank(a.code) - profilRank(b.code) || a.label.localeCompare(b.label, 'fr'))
        .map((role) => ({ role, profil: roleProfil(role.label) })),
    });
  }

  return groups.sort((a, b) => {
    const ao = meta.get(a.key)?.order ?? 10_000;
    const bo = meta.get(b.key)?.order ?? 10_000;
    if (ao !== bo) {
      return ao - bo;
    }
    return a.title.localeCompare(b.title, 'fr');
  });
}

export interface CoreAdminUserRow {
  id: string;
  email: string;
  full_name: string;
  phone?: string | null;
  is_superuser: boolean;
  is_active: boolean;
  totp_enabled: boolean;
  last_login_at: string | null;
  created_at?: string | null;
  roles: CoreAdminRole[];
  espace_codes: string[];
  module_codes: string[];
  permission_codes?: string[];
}

export interface CoreAdminUserSession {
  id: string;
  kind: string;
  module_code?: string | null;
  ip_address?: string | null;
  user_agent?: string | null;
  created_at?: string | null;
  expires_at?: string | null;
  revoked_at?: string | null;
  active: boolean;
}

export interface CoreAdminUserActivity {
  id: string;
  who: string;
  action: string;
  entity: string;
  entity_id?: string | null;
  module?: string | null;
  created_at?: string | null;
}

export interface CoreAdminUserFiche extends CoreAdminUserRow {
  sessions: CoreAdminUserSession[];
  activite: CoreAdminUserActivity[];
}

export interface CoreAdminCatalogueEspace {
  id: string;
  titre: string;
  statut: string;
  modules: { id: string; titre: string; statut: string }[];
}

export interface CoreAdminUserKpis {
  total: number;
  actifs: number;
  inactifs: number;
  superusers: number;
  totp: number;
  jamais_connectes: number;
}

export interface CoreAdminUserPage {
  items: CoreAdminUserRow[];
  total: number;
  page: number;
  size: number;
  kpis: CoreAdminUserKpis;
}

export function coreAdminApiError(err: unknown, fallback: string): string {
  if (!(err instanceof HttpErrorResponse)) {
    return fallback;
  }
  const detail = err.error?.detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }
  if (detail && typeof detail === 'object' && typeof (detail as { message?: string }).message === 'string') {
    return (detail as { message: string }).message;
  }
  return fallback;
}
