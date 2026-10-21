import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal, Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Route, Router, Routes, UrlTree } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { coreAdminGuard } from '../../core/guards/auth.guard';
import { AuthService } from '../../core/services/auth.service';
import { PLATEFORME_ROUTES } from '../plateforme.routes';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIntegrationAlertesComponent } from './core-admin-integration-alertes.component';
import {
  bornesPeriode,
  executionFamille,
  messageTest,
  operationExigeSecret,
  PERMISSIONS_STUDIO,
  sansVides,
} from './core-admin-integration-execution.models';
import { CoreAdminIntegrationExecutionsComponent } from './core-admin-integration-executions.component';
import { CoreAdminIntegrationTestComponent } from './core-admin-integration-test.component';
import { CoreAdminIntegrationTestsPageComponent } from './core-admin-integration-tests-page.component';
import { CoreAdminIntegrationsOverviewComponent } from './core-admin-integrations.component';
import { CORE_ADMIN_NAV, coreAdminNavVisible } from './core-admin-nav';
import { HttpErrorResponse } from '@angular/common/http';

const API = '/api/v1/plateforme/admin/integrations';
const STUDIO_LABELS = [
  'Vue d’ensemble', 'Catalogue API', 'Console (lecture)', 'Applications clientes', 'Fournisseurs externes',
  'Destinations TEST', 'Tests d’intégration', 'Historique des exécutions', 'Supervision', 'Alertes',
];

function studio(codes: string[], superuser = false): string[] {
  const groupe = coreAdminNavVisible(CORE_ADMIN_NAV, codes, superuser).find((g) => g.label === 'Studio d’intégration API');
  return groupe ? groupe.items.map((i) => i.label) : [];
}

function texte(el: HTMLElement): string {
  return (el.textContent ?? '').replace(/\s+/g, ' ');
}

const dialogs = {
  confirm: jasmine.createSpy('confirm').and.resolveTo(false),
  prompt: () => Promise.resolve(null),
  success: () => Promise.resolve(),
  error: () => Promise.resolve(),
  info: jasmine.createSpy('info').and.resolveTo(),
};

function configurer(codes: string[], routes: Routes = []) {
  dialogs.confirm.calls.reset();
  dialogs.info.calls.reset();
  TestBed.configureTestingModule({
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      provideRouter(routes),
      { provide: BeaAdminDialogService, useValue: dialogs },
      { provide: AuthService, useValue: { user: signal({ is_superuser: false, permission_codes: codes, full_name: 'T' }) } },
    ],
  });
  return TestBed.inject(HttpTestingController);
}

async function ouvrir<T>(codes: string[], composant: Type<T>, url: string) {
  const http = configurer(codes, [{ path: 'page', component: composant }]);
  const harness = await RouterTestingHarness.create();
  const instance = await harness.navigateByUrl(url, composant);
  harness.detectChanges();
  return { http, harness, instance };
}

function adminChildren(): Route[] {
  return PLATEFORME_ROUTES.find((r) => r.path === 'admin')?.children ?? [];
}

describe('Studio UX — menu par permission', () => {
  it('aucun groupe Studio sans permission Studio, même avec core.admin.access', () => {
    expect(studio([])).toEqual([]);
    expect(studio(['core.admin.access'])).toEqual([]);
  });

  it('catalogue et console exigent core.admin.integrations.view (aligné sur le serveur)', () => {
    expect(studio([PERMISSIONS_STUDIO.catalogue])).toEqual(['Vue d’ensemble', 'Catalogue API', 'Console (lecture)']);
  });

  it('tests : exécution sans consultation = page de test, pas d’historique', () => {
    const l = studio([PERMISSIONS_STUDIO.testsExecute]);
    expect(l).toContain('Tests d’intégration');
    expect(l).not.toContain('Historique des exécutions');
  });

  it('supervision.view ouvre Supervision et Alertes, rien d’autre que la vue d’ensemble', () => {
    expect(studio([PERMISSIONS_STUDIO.supervision])).toEqual(['Vue d’ensemble', 'Supervision', 'Alertes']);
  });

  it('superutilisateur ou * : les dix entrées réelles, dans l’ordre', () => {
    expect(studio([], true)).toEqual(STUDIO_LABELS);
    expect(studio(['*'])).toEqual(STUDIO_LABELS);
  });

  it('aucune permission générique ni suffixe .admin dans le Studio', () => {
    const groupe = CORE_ADMIN_NAV.find((g) => g.label === 'Studio d’intégration API');
    const codes = (groupe?.items ?? []).flatMap((i) => [i.permission, ...(i.anyPermission ?? [])]).filter(Boolean) as string[];
    expect(codes.length).toBeGreaterThan(0);
    for (const c of codes) {
      expect(c.startsWith('core.admin.integrations.')).toBeTrue();
      expect(c.endsWith('.admin')).toBeFalse();
    }
  });

  it('chaque entrée du Studio correspond à une route déclarée sous /admin', () => {
    const chemins = new Set(adminChildren().map((r) => `/admin/${r.path}`));
    const groupe = CORE_ADMIN_NAV.find((g) => g.label === 'Studio d’intégration API');
    for (const item of groupe?.items ?? []) {
      expect(chemins.has(item.path ?? '')).withContext(item.path ?? '').toBeTrue();
    }
  });

  it('les routes du Studio sont des enfants de /admin, protégée par coreAdminGuard', () => {
    const admin = PLATEFORME_ROUTES.find((r) => r.path === 'admin');
    expect(admin?.canActivate).toContain(coreAdminGuard);
    expect(adminChildren().some((r) => r.path === 'integrations/alertes')).toBeTrue();
  });
});

describe('Studio UX — garde CORE ADMIN', () => {
  function garde(auth: Partial<AuthService>): UrlTree | boolean {
    TestBed.configureTestingModule({ providers: [provideRouter([]), { provide: AuthService, useValue: auth }] });
    return TestBed.runInInjectionContext(() => coreAdminGuard({} as never, {} as never)) as UrlTree | boolean;
  }

  it('Login 2 seul (pas de jeton plateforme) : renvoyé vers /login, jamais au Studio', () => {
    const r = garde({ isAuthenticated: () => false, user: signal(null) } as unknown as Partial<AuthService>);
    expect(TestBed.inject(Router).serializeUrl(r as UrlTree)).toBe('/login');
  });

  it('Login 1 sans core.admin.access : renvoyé vers /accueil', () => {
    const r = garde({
      isAuthenticated: () => true,
      user: signal({ is_superuser: false, permission_codes: [PERMISSIONS_STUDIO.catalogue] }),
      canAccessCoreAdmin: signal(false),
    } as unknown as Partial<AuthService>);
    expect(TestBed.inject(Router).serializeUrl(r as UrlTree)).toBe('/accueil');
  });
});

describe('Studio UX — fonctions', () => {
  it('période : bornes calculées, personnalisée lue depuis la saisie, « tout » sans borne', () => {
    const maintenant = new Date('2026-10-21T12:00:00Z');
    expect(bornesPeriode('24h', '', '', maintenant).depuis).toBe('2026-10-20T12:00:00.000Z');
    expect(bornesPeriode('tout', '', '', maintenant)).toEqual({});
    expect(Object.keys(bornesPeriode('perso', '2026-10-01T08:00', '', maintenant))).toEqual(['depuis']);
  });

  it('sansVides retire les champs vides', () => {
    expect(sansVides({ a: '', b: ' x ', c: null, d: undefined })).toEqual({ b: 'x' });
  });

  it('familles : fournisseur, connectivité, refus local', () => {
    expect(executionFamille('http_erreur')).toBe('fournisseur');
    expect(executionFamille('timeout')).toBe('reseau');
    expect(executionFamille('secret_requis')).toBe('refus');
    expect(executionFamille('quota')).toBe('refus');
  });

  it('secret requis : seul le mécanisme « aucun » est testable', () => {
    expect(operationExigeSecret({ configuration: { mecanisme_auth: 'aucun' } })).toBeFalse();
    expect(operationExigeSecret({ configuration: { mecanisme_auth: 'http_bearer' } })).toBeTrue();
    expect(operationExigeSecret({ configuration: null })).toBeTrue();
  });

  it('messages explicites : quota, secret requis, délai', () => {
    const err = (code: string, status: number) => new HttpErrorResponse({ status, error: { code, message: 'x' } });
    expect(messageTest(err('QUOTA', 429), 'f')).toContain('Quota');
    expect(messageTest(err('SECRET_REQUIS', 422), 'f')).toContain('coffre de secrets');
    expect(messageTest(err('TIMEOUT', 504), 'f')).toContain('Délai dépassé');
    expect(messageTest(err('INCONNU', 422), 'f')).toBe('x');
  });
});

describe('Studio UX — vue d’ensemble', () => {
  it('sans aucune permission Studio : accès refusé explicite et aucun appel réseau', async () => {
    const { http, harness } = await ouvrir([], CoreAdminIntegrationsOverviewComponent, '/page');
    expect(texte(harness.routeNativeElement!)).toContain('Accès refusé');
    http.expectNone(() => true);
  });

  it('supervision seule : alertes chargées, autres indicateurs « Permission requise » sans appel', async () => {
    const { http, harness } = await ouvrir([PERMISSIONS_STUDIO.supervision], CoreAdminIntegrationsOverviewComponent, '/page');
    const reqs = http.match((r) => r.url === `${API}/supervision/alertes`);
    expect(reqs.length).toBe(2);
    reqs.forEach((r) => r.flush({ items: [], total: 0, page: 1, size: 1 }));
    http.expectNone((r) => r.url.includes('/fournisseurs') || r.url.includes('/destinations') || r.url.includes('/executions'));
    http.expectNone((r) => r.url === `${API}/supervision`);
    harness.detectChanges();
    const t = texte(harness.routeNativeElement!);
    expect(t).toContain('Permission requise : core.admin.integrations.fournisseurs.view');
    expect(t).toContain('Alertes actives');
    expect(t).toContain('Aucune');
  });

  it('exécutions : « Aucune donnée » quand rien n’a été testé, aucun /tests/executer', async () => {
    const { http, harness } = await ouvrir([PERMISSIONS_STUDIO.testsView], CoreAdminIntegrationsOverviewComponent, '/page');
    http.match((r) => r.url === `${API}/executions`).forEach((r) => r.flush({ items: [], total: 0, page: 1, size: 5, retention_jours: 90 }));
    harness.detectChanges();
    expect(texte(harness.routeNativeElement!)).toContain('Aucune donnée');
    http.expectNone((r) => r.url.includes('/tests/'));
  });
});

describe('Studio UX — page Tests', () => {
  it('sans permission de test : accès refusé, aucun appel', async () => {
    const { http, harness } = await ouvrir([PERMISSIONS_STUDIO.fournisseurs], CoreAdminIntegrationTestsPageComponent, '/page');
    expect(texte(harness.routeNativeElement!)).toContain('Accès refusé');
    http.expectNone(() => true);
  });

  it('exécution sans consultation des fournisseurs/destinations : prérequis listés, aucun appel', async () => {
    const { http, harness } = await ouvrir([PERMISSIONS_STUDIO.testsExecute], CoreAdminIntegrationTestsPageComponent, '/page');
    const t = texte(harness.routeNativeElement!);
    expect(t).toContain(PERMISSIONS_STUDIO.fournisseurs);
    expect(t).toContain(PERMISSIONS_STUDIO.destinations);
    http.expectNone(() => true);
  });

  it('liste les fournisseurs validés TEST ; état vide explicite ; aucun test lancé', async () => {
    const { http, harness } = await ouvrir(
      [PERMISSIONS_STUDIO.testsExecute, PERMISSIONS_STUDIO.fournisseurs, PERMISSIONS_STUDIO.destinations],
      CoreAdminIntegrationTestsPageComponent,
      '/page',
    );
    const req = http.expectOne((r) => r.url === `${API}/fournisseurs`);
    expect(req.request.params.get('statut')).toBe('valide');
    expect(req.request.params.get('environnement')).toBe('TEST');
    req.flush({ items: [], total: 0, page: 1, size: 100, avertissement: '' });
    harness.detectChanges();
    expect(texte(harness.routeNativeElement!)).toContain('Aucun fournisseur validé en TEST');
    http.expectNone((r) => r.url.includes('/tests/'));
  });
});

describe('Studio UX — composant de test', () => {
  const OPS = `${API}/fournisseurs/f1/operations`;
  const DEST = `${API}/destinations`;

  function monter(codes: string[]) {
    const http = configurer(codes);
    const fixture = TestBed.createComponent(CoreAdminIntegrationTestComponent);
    fixture.componentInstance.fournisseurId = 'f1';
    fixture.detectChanges();
    http.expectOne((r) => r.url === OPS).flush({
      items: [
        { id: 'op1', statut: 'active', methode: 'GET', chemin: '/v1/status', origine: 'manuelle', tags: [], deprecie: false, conflit: false, updated_at: '' },
        { id: 'op2', statut: 'active', methode: 'POST', chemin: '/v1/x', origine: 'manuelle', tags: [], deprecie: false, conflit: false, updated_at: '' },
      ],
      total: 2, page: 1, size: 200, avertissement: '',
    });
    http.expectOne((r) => r.url === DEST).flush({
      items: [{ id: 'd1', code: 'D', nom: 'Dest', fournisseur_id: 'f1', environnement: 'TEST', statut: 'active', hotes: ['api.example.com'], methodes: ['GET'], updated_at: '' }],
      total: 1, page: 1, size: 100,
    });
    fixture.detectChanges();
    return { http, fixture };
  }

  it('ne propose que GET/HEAD et ne lance aucun appel sans action', () => {
    const { http, fixture } = monter([PERMISSIONS_STUDIO.testsExecute, PERMISSIONS_STUDIO.fournisseurs, PERMISSIONS_STUDIO.destinations]);
    const options = Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('option')).map((o) => o.textContent ?? '');
    expect(options.some((o) => o.includes('/v1/status'))).toBeTrue();
    expect(options.some((o) => o.includes('POST'))).toBeFalse();
    http.expectNone((r) => r.url.includes('/tests/'));
  });

  it('opération authentifiée : message « secret requis » et aperçu désactivé', () => {
    const { http, fixture } = monter([PERMISSIONS_STUDIO.testsExecute, PERMISSIONS_STUDIO.fournisseurs, PERMISSIONS_STUDIO.destinations]);
    const c = fixture.componentInstance;
    c.form.setValue({ operation_id: 'op1', destination_id: 'd1' });
    http.expectOne((r) => r.url === `${OPS}/op1`).flush({ id: 'op1', parametres: [], configuration: { mecanisme_auth: 'http_bearer' } });
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Test bloqué');
    expect(c.peutPreparer()).toBeFalse();
    http.expectNone((r) => r.url.includes('/tests/'));
  });

  it('aperçu puis modification : l’aperçu est invalidé ; l’exécution exige une confirmation', async () => {
    const { http, fixture } = monter([PERMISSIONS_STUDIO.testsExecute, PERMISSIONS_STUDIO.fournisseurs, PERMISSIONS_STUDIO.destinations]);
    const c = fixture.componentInstance;
    c.form.setValue({ operation_id: 'op1', destination_id: 'd1' });
    http.expectOne((r) => r.url === `${OPS}/op1`).flush({
      id: 'op1', parametres: [{ nom: 'q', emplacement: 'query', requis: false }], configuration: { mecanisme_auth: 'aucun' },
    });
    fixture.detectChanges();
    expect(c.peutPreparer()).toBeTrue();
    c.preparer();
    const apercu = http.expectOne((r) => r.url === `${API}/tests/apercu`);
    expect(apercu.request.body.url).toBeUndefined();
    apercu.flush({ methode: 'GET', url: 'https://api.example.com/v1/status', entetes_envoyes: [], authentification: 'aucune', redirections: 'refusées', environnement: 'TEST', avertissement: '' });
    fixture.detectChanges();
    expect(c.apercu()).not.toBeNull();
    await c.executer();
    expect(dialogs.confirm).toHaveBeenCalled();
    http.expectNone((r) => r.url.includes('/tests/executer'));
    c.ctrl('q_q').setValue('autre');
    expect(c.apercu()).toBeNull();
  });

  it('erreur de quota : message explicite', () => {
    const { http, fixture } = monter([PERMISSIONS_STUDIO.testsExecute, PERMISSIONS_STUDIO.fournisseurs, PERMISSIONS_STUDIO.destinations]);
    const c = fixture.componentInstance;
    c.form.setValue({ operation_id: 'op1', destination_id: 'd1' });
    http.expectOne((r) => r.url === `${OPS}/op1`).flush({ id: 'op1', parametres: [], configuration: { mecanisme_auth: 'aucun' } });
    c.preparer();
    http.expectOne((r) => r.url === `${API}/tests/apercu`).flush({ code: 'QUOTA', message: 'Quota' }, { status: 429, statusText: 'T' });
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Quota de tests atteint');
  });
});

describe('Studio UX — historique', () => {
  it('sans tests.view : accès refusé, aucun appel', async () => {
    const { http, harness } = await ouvrir([PERMISSIONS_STUDIO.supervision], CoreAdminIntegrationExecutionsComponent, '/page');
    expect(texte(harness.routeNativeElement!)).toContain('Accès refusé');
    http.expectNone(() => true);
  });

  it('filtres de l’URL appliqués (accès direct / rafraîchissement), pagination et état vide', async () => {
    const { http, harness } = await ouvrir([PERMISSIONS_STUDIO.testsView], CoreAdminIntegrationExecutionsComponent, '/page?statut=timeout&periode=tout&page=2');
    const req = http.expectOne((r) => r.url === `${API}/executions`);
    expect(req.request.params.get('statut')).toBe('timeout');
    expect(req.request.params.get('page')).toBe('2');
    expect(req.request.params.has('depuis')).toBeFalse();
    req.flush({ items: [], total: 0, page: 2, size: 25, retention_jours: 90 });
    harness.detectChanges();
    expect(texte(harness.routeNativeElement!)).toContain('Aucune donnée');
    http.expectNone((r) => r.url.includes('/fournisseurs') || r.url.includes('/destinations'));
  });

  it('export vide : informe sans appeler le serveur', async () => {
    const { http, harness, instance } = await ouvrir(
      [PERMISSIONS_STUDIO.testsView, PERMISSIONS_STUDIO.supervisionExport],
      CoreAdminIntegrationExecutionsComponent,
      '/page',
    );
    http.expectOne((r) => r.url === `${API}/executions`).flush({ items: [], total: 0, page: 1, size: 25, retention_jours: 90 });
    harness.detectChanges();
    await instance.exporter();
    expect(dialogs.info).toHaveBeenCalled();
    http.expectNone((r) => r.url.includes('/export'));
  });

  it('export : transmet les mêmes filtres que la liste', async () => {
    const { http, harness, instance } = await ouvrir(
      [PERMISSIONS_STUDIO.testsView, PERMISSIONS_STUDIO.supervisionExport],
      CoreAdminIntegrationExecutionsComponent,
      '/page?statut=succes&periode=tout',
    );
    http.expectOne((r) => r.url === `${API}/executions`).flush({ items: [], total: 3, page: 1, size: 25, retention_jours: 90 });
    harness.detectChanges();
    void instance.exporter();
    const exp = http.expectOne((r) => r.url === `${API}/supervision/export`);
    expect(exp.request.params.get('statut')).toBe('succes');
    exp.flush(new Blob(['a;b']));
  });
});

describe('Studio UX — alertes', () => {
  const ALERTE = {
    id: 'a1', type: 'latence', statut: 'nouvelle', message: 'Latence 6000 ms', niveau: 'moyenne',
    regle: 'Durée d’un test supérieure ou égale à 5000 ms.', occurences: 2, details: { duree_ms: 6000 },
    derniere_le: '2026-10-21T10:00:00Z', created_at: '2026-10-20T10:00:00Z',
  };

  it('filtres niveau/type/statut transmis ; détail de la règle affiché', async () => {
    const { http, harness, instance } = await ouvrir(
      [PERMISSIONS_STUDIO.supervision],
      CoreAdminIntegrationAlertesComponent,
      '/page?niveau=moyenne&type=latence&statut=nouvelle',
    );
    const req = http.expectOne((r) => r.url === `${API}/supervision/alertes`);
    expect(req.request.params.get('niveau')).toBe('moyenne');
    expect(req.request.params.get('type')).toBe('latence');
    expect(req.request.params.get('statut')).toBe('nouvelle');
    req.flush({ items: [ALERTE], total: 1, page: 1, size: 25 });
    harness.detectChanges();
    instance.basculer('a1');
    harness.detectChanges();
    const t = texte(harness.routeNativeElement!);
    expect(t).toContain('Moyen');
    expect(t).toContain('5000 ms');
    expect(t).toContain('Consultation seule');
    expect(t).not.toContain('Résoudre');
  });

  it('traitement : confirmation obligatoire, rien n’est envoyé si refusée', async () => {
    const { http, harness, instance } = await ouvrir(
      [PERMISSIONS_STUDIO.supervision, 'core.admin.integrations.supervision.manage'],
      CoreAdminIntegrationAlertesComponent,
      '/page',
    );
    http.expectOne((r) => r.url === `${API}/supervision/alertes`).flush({ items: [ALERTE], total: 1, page: 1, size: 25 });
    harness.detectChanges();
    expect(texte(harness.routeNativeElement!)).toContain('Résoudre');
    await instance.traiter(ALERTE as never, 'resolue');
    expect(dialogs.confirm).toHaveBeenCalled();
    http.expectNone((r) => r.method === 'PATCH');
  });
});
