import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIntegrationDestinationsComponent } from './core-admin-integration-destinations.component';
import {
  PERMISSIONS_DESTINATIONS,
  PERMISSIONS_SUPERVISION,
  PERMISSIONS_TESTS,
  disponibiliteLabel,
  executionStatutLabel,
  hotesDepuisTexte,
} from './core-admin-integration-execution.models';
import { CoreAdminIntegrationSupervisionComponent } from './core-admin-integration-supervision.component';
import { CORE_ADMIN_NAV, coreAdminNavVisible } from './core-admin-nav';

const DEST = '/api/v1/plateforme/admin/integrations/destinations';
const SUP = '/api/v1/plateforme/admin/integrations/supervision';

function configurer(codes: string[], query: Record<string, string> = {}) {
  TestBed.configureTestingModule({
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      provideRouter([]),
      { provide: BeaAdminDialogService, useValue: { confirm: () => Promise.resolve(false), prompt: () => Promise.resolve(null), success: () => Promise.resolve(), error: () => Promise.resolve() } },
      { provide: AuthService, useValue: { user: signal({ is_superuser: false, permission_codes: codes, full_name: 'T' }) } },
      { provide: ActivatedRoute, useValue: { snapshot: { queryParamMap: convertToParamMap(query), paramMap: convertToParamMap({}) } } },
    ],
  });
  return TestBed.inject(HttpTestingController);
}

function texte(el: HTMLElement): string {
  return (el.textContent ?? '').replace(/\s+/g, ' ');
}

describe('Phases 5–6 — fonctions', () => {
  it('hôtes : découpe et ignore le vide', () => {
    expect(hotesDepuisTexte('API.Test.Example\n, localhost ')).toEqual(['api.test.example', 'localhost']);
  });

  it('libellés de disponibilité et d’exécution', () => {
    expect(disponibiliteLabel('inconnue')).toBe('Inconnue');
    expect(disponibiliteLabel('disponible_dernier_test')).toContain('dernier test');
    expect(executionStatutLabel('refuse_securite')).toBe('Refus de sécurité');
  });

  it('menu : destinations et supervision masqués sans permission', () => {
    const libelles = (codes: string[]) =>
      coreAdminNavVisible(CORE_ADMIN_NAV, codes, false)
        .filter((g) => g.label === 'Studio d’intégration API')
        .flatMap((g) => g.items.map((i) => i.label));
    expect(libelles([])).not.toContain('Destinations TEST');
    expect(libelles([])).not.toContain('Alertes');
    expect(libelles([PERMISSIONS_DESTINATIONS.view])).toContain('Destinations TEST');
    expect(libelles([PERMISSIONS_SUPERVISION.view])).toContain('Alertes');
  });
});

describe('Destinations — liste', () => {
  it('n’appelle pas /tests/executer au chargement', () => {
    const http = configurer([PERMISSIONS_DESTINATIONS.view]);
    const fixture = TestBed.createComponent(CoreAdminIntegrationDestinationsComponent);
    fixture.detectChanges();
    const req = http.expectOne((r) => r.url === DEST);
    expect(req.request.method).toBe('GET');
    req.flush({ items: [], total: 0, page: 1, size: 25 });
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Aucune destination');
    http.expectNone((r) => r.url.includes('/tests/'));
  });

  it('affiche l’accès refusé sur 403', () => {
    const http = configurer([PERMISSIONS_DESTINATIONS.view]);
    const fixture = TestBed.createComponent(CoreAdminIntegrationDestinationsComponent);
    fixture.detectChanges();
    http.expectOne((r) => r.url === DEST).flush({ message: 'Permission refusée' }, { status: 403, statusText: 'F' });
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Accès refusé');
  });
});

describe('Supervision', () => {
  it('affiche « Aucune donnée » et n’exécute aucun test', () => {
    const http = configurer([PERMISSIONS_SUPERVISION.view, PERMISSIONS_TESTS.view]);
    const fixture = TestBed.createComponent(CoreAdminIntegrationSupervisionComponent);
    fixture.detectChanges();
    http.expectOne((r) => r.url === SUP).flush({
      periode: { depuis: null, jusqua: null, denominateur: 'exécutions' },
      total: 0, succes: 0, echecs: 0, taux_succes: null, taux_libelle: 'Aucune donnée',
      latence_moyenne_ms: null, latence_mediane_ms: null, erreurs: [],
      sans_mesure: [], destinations_suspendues: [], disponibilite: 'inconnue',
      retention_jours: 90, sondes_automatiques: false,
    });
    http.match((r) => r.url.includes('/executions')).forEach((r) => r.flush({ items: [], total: 0, page: 1, size: 25, retention_jours: 90 }));
    http.match((r) => r.url.includes('/alertes')).forEach((r) => r.flush({ items: [], total: 0, page: 1, size: 25 }));
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Aucune donnée');
    expect(texte(fixture.nativeElement)).toContain('Aucune mesure');
    http.expectNone((r) => r.url.includes('/tests/executer'));
  });
});
