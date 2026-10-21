import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { AuthService } from '../../core/services/auth.service';
import { appliquerBaseUrl, BASE_URL_EXEMPLE, CoreAdminIntegrationFicheComponent } from './core-admin-integration-fiche.component';
import {
  CoreAdminIntegrationsCatalogueComponent,
  CoreAdminIntegrationsOverviewComponent,
} from './core-admin-integrations.component';
import { CoreAdminIntegrationsConsoleComponent } from './core-admin-integrations-console.component';
import {
  catalogueParams,
  consoleRequete,
  IntegrationCataloguePage,
  IntegrationConsoleOperation,
  IntegrationConsoleOperations,
  integrationErreur,
} from './core-admin-integrations.models';
import { CoreAdminIntegrationsService } from './core-admin-integrations.service';

const BASE = '/api/v1/plateforme/admin/integrations';

const KPIS = {
  total: 3,
  documentees: 1,
  restreintes: 1,
  exclues: 1,
  console: 1,
  par_methode: { GET: 3 },
  par_authentification: { login1: 2, login2: 1 },
  par_permission_statut: { identifiee: 3 },
  par_schema_reponse: { explicite: 3 },
};

function page(items: IntegrationCataloguePage['items'] = []): IntegrationCataloguePage {
  return {
    items,
    total: items.length,
    page: 1,
    size: 25,
    kpis: KPIS,
    filtres: { modules: ['core-admin'], methodes: ['GET'], authentifications: ['login1'] },
    avertissement: 'Le catalogue ne garantit aucune autorisation.',
  };
}

const OP_CONSOLE: IntegrationConsoleOperation = {
  operation_id: 'get.core_admin_catalogue.list_modules',
  nom: 'list_modules',
  methode: 'GET',
  chemin: '/api/v1/plateforme/admin/modules',
  module: 'core-admin',
  permissions: ['core.admin.modules'],
  justification: 'Lecture paginée sans effet de bord.',
  parametres: [
    { nom: 'page', emplacement: 'query', requis: false, type: 'integer', defaut: 1, valeurs: [] },
    { nom: 'search', emplacement: 'query', requis: false, type: 'string', valeurs: [] },
  ],
};

const CONSOLE: IntegrationConsoleOperations = {
  items: [OP_CONSOLE],
  environnement: 'test',
  limites: { methodes: ['GET'], taille_max_octets: 262144, delai_max_secondes: 10 },
  avertissement: 'Lecture seule.',
};

const feedbackStub = {
  run: (action: () => unknown) => action(),
  success: () => 0,
  warning: () => 0,
  error: () => 0,
};

function configurer(queryParams: Record<string, string> = {}, params: Record<string, string> = {}) {
  TestBed.configureTestingModule({
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      provideRouter([]),
      { provide: FeedbackService, useValue: feedbackStub },
      { provide: AuthService, useValue: { user: signal({ is_superuser: false, permission_codes: ['core.admin.integrations.view'], full_name: 'T' }) } },
      {
        provide: ActivatedRoute,
        useValue: {
          snapshot: { queryParamMap: convertToParamMap(queryParams) },
          paramMap: of(convertToParamMap(params)),
        },
      },
    ],
  });
  return TestBed.inject(HttpTestingController);
}

function texte(el: HTMLElement): string {
  return (el.textContent ?? '').replace(/\s+/g, ' ');
}

describe('Studio intégration API — fonctions', () => {
  it('ignore les filtres vides et garde les booléens', () => {
    expect(catalogueParams({ q: '  ', module: 'ged', console: false, permission: undefined }, 2, 25)).toEqual({
      page: 2,
      size: 25,
      module: 'ged',
      console: false,
    });
  });

  it("ne transmet que l'identifiant et des valeurs de paramètres déclarés", () => {
    const req = consoleRequete(OP_CONSOLE, { page: ' 2 ', search: '', url: 'http://evil', inconnu: 'x' });
    expect(req).toEqual({ operation_id: OP_CONSOLE.operation_id, parametres_chemin: {}, parametres_requete: { page: '2' } });
    expect(Object.keys(req)).toEqual(['operation_id', 'parametres_chemin', 'parametres_requete']);
  });

  it('distingue accès refusé et refus console', () => {
    const refus = new HttpErrorResponse({ status: 403, error: { code: 'FORBIDDEN', message: 'Permission requise' } });
    const console = new HttpErrorResponse({
      status: 403,
      error: { code: 'CONSOLE_OPERATION_NON_AUTORISEE', message: 'Hors liste', detail: { code: 'CONSOLE_OPERATION_NON_AUTORISEE', message: 'Hors liste' } },
    });
    expect(integrationErreur(refus, 'x').accesRefuse).toBeTrue();
    expect(integrationErreur(console, 'x')).toEqual({ statut: 403, message: 'Hors liste', accesRefuse: false });
    expect(integrationErreur(new HttpErrorResponse({ status: 401 }), 'x').accesRefuse).toBeTrue();
  });

  it("n'accepte qu'une URL de base http(s) simple dans les exemples", () => {
    const code = `BASE_URL="\${BEA_BASE_URL:-${BASE_URL_EXEMPLE}}"`;
    expect(appliquerBaseUrl(code, 'https://bea.local/')).toContain('https://bea.local}');
    expect(appliquerBaseUrl(code, 'javascript:alert(1)')).toBe(code);
    expect(appliquerBaseUrl(code, 'https://x"; rm -rf /')).toBe(code);
  });
});

describe('Studio intégration API — service', () => {
  it('encode les identifiants et appelle les routes du Studio', () => {
    const http = configurer();
    const svc = TestBed.inject(CoreAdminIntegrationsService);
    svc.fiche('get.a/b').subscribe();
    http.expectOne(`${BASE}/catalogue/get.a%2Fb`).flush({});
    svc.executer({ operation_id: 'x', parametres_chemin: {}, parametres_requete: {} }).subscribe();
    const req = http.expectOne(`${BASE}/console/executer`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ operation_id: 'x', parametres_chemin: {}, parametres_requete: {} });
    http.verify();
  });
});

describe('Studio intégration API — pages', () => {
  it("vue d'ensemble : affiche les indicateurs", () => {
    const http = configurer();
    const fixture = TestBed.createComponent(CoreAdminIntegrationsOverviewComponent);
    fixture.detectChanges();
    http.expectOne((r) => r.url === `${BASE}/catalogue`).flush(page());
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Opérations découvertes');
    expect(texte(fixture.nativeElement)).toContain('Le catalogue ne garantit aucune autorisation.');
  });

  it("vue d'ensemble : état accès refusé sur 403", () => {
    const http = configurer();
    const fixture = TestBed.createComponent(CoreAdminIntegrationsOverviewComponent);
    fixture.detectChanges();
    http.expectOne((r) => r.url === `${BASE}/catalogue`).flush({ code: 'FORBIDDEN', message: 'Permission requise' }, { status: 403, statusText: 'Forbidden' });
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Accès refusé');
    expect(texte(fixture.nativeElement)).toContain('core.admin.integrations.view');
  });

  it('catalogue : reprend les filtres de l’URL et affiche l’état vide', () => {
    const http = configurer({ disponibilite: 'restreinte', q: 'ged' });
    const fixture = TestBed.createComponent(CoreAdminIntegrationsCatalogueComponent);
    fixture.detectChanges();
    const req = http.expectOne((r) => r.url === `${BASE}/catalogue`);
    expect(req.request.params.get('disponibilite')).toBe('restreinte');
    expect(req.request.params.get('q')).toBe('ged');
    expect(req.request.params.has('module')).toBeFalse();
    req.flush(page());
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Aucune opération ne correspond');
  });

  it('catalogue : erreur serveur affichée avec bouton Réessayer', () => {
    const http = configurer();
    const fixture = TestBed.createComponent(CoreAdminIntegrationsCatalogueComponent);
    fixture.detectChanges();
    http.expectOne((r) => r.url === `${BASE}/catalogue`).flush({ message: 'Erreur interne' }, { status: 500, statusText: 'KO' });
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Erreur interne');
    expect(texte(fixture.nativeElement)).toContain('Réessayer');
  });

  it('fiche : opération introuvable', () => {
    const http = configurer({}, { operationId: 'get.inconnu.x' });
    const fixture = TestBed.createComponent(CoreAdminIntegrationFicheComponent);
    fixture.detectChanges();
    http.expectOne(`${BASE}/catalogue/get.inconnu.x`).flush({ code: 'OPERATION_INTROUVABLE' }, { status: 404, statusText: 'NF' });
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Opération introuvable');
    http.verify();
  });

  it('console : aucune exécution automatique, POST uniquement après clic', () => {
    const http = configurer({ operation: OP_CONSOLE.operation_id });
    const fixture = TestBed.createComponent(CoreAdminIntegrationsConsoleComponent);
    fixture.detectChanges();
    http.expectOne(`${BASE}/console/operations`).flush(CONSOLE);
    fixture.detectChanges();
    http.expectNone(`${BASE}/console/executer`);
    expect(texte(fixture.nativeElement)).toContain('Environnement cible : test');

    const bouton = Array.from(fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>).find((b) =>
      b.textContent?.includes('Exécuter'),
    )!;
    bouton.click();
    const req = http.expectOne(`${BASE}/console/executer`);
    expect(req.request.body.operation_id).toBe(OP_CONSOLE.operation_id);
    expect(Object.keys(req.request.body)).not.toContain('url');
    req.flush({
      operation_id: OP_CONSOLE.operation_id,
      methode: 'GET',
      chemin: OP_CONSOLE.chemin,
      statut_http: 200,
      duree_ms: 12,
      taille_octets: 40,
      tronquee: false,
      corps: { items: [], token: '•••• (masqué)' },
      champs_masques: 1,
      request_id: 'req-1',
      environnement: 'test',
    });
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Champs masqués');
    expect(texte(fixture.nativeElement)).toContain('•••• (masqué)');
    http.verify();
  });

  it('console : état vide quand aucune opération n’est admissible', () => {
    const http = configurer();
    const fixture = TestBed.createComponent(CoreAdminIntegrationsConsoleComponent);
    fixture.detectChanges();
    http.expectOne(`${BASE}/console/operations`).flush({ ...CONSOLE, items: [] });
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain("Aucune opération n'est actuellement admissible");
  });
});
