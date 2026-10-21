import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal, Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Routes } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { of, throwError } from 'rxjs';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthService } from '../../core/services/auth.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIntegrationAlertesComponent } from './core-admin-integration-alertes.component';
import { CoreAdminIntegrationDestinationFormComponent } from './core-admin-integration-destination-form.component';
import { CoreAdminIntegrationDestinationsComponent } from './core-admin-integration-destinations.component';
import { PERMISSIONS_DESTINATIONS, PERMISSIONS_STUDIO, PERMISSIONS_SUPERVISION } from './core-admin-integration-execution.models';
import { CoreAdminIntegrationExecutionsComponent } from './core-admin-integration-executions.component';
import { construireGraphe, courbe } from './core-admin-integration-supervision.component';
import { CoreAdminIntegrationTestComponent } from './core-admin-integration-test.component';
import {
  ariaSort,
  basculerTri,
  BilanSuppression,
  etatExecution,
  IntegrationSuppressionService,
  messageBlocage,
} from './core-admin-integration-ui';

const API = '/api/v1/plateforme/admin/integrations';
const FID = '11111111-1111-4111-8111-111111111111';

function texte(el: HTMLElement): string {
  return (el.textContent ?? '').replace(/\s+/g, ' ');
}

const dialogs = {
  confirm: jasmine.createSpy('confirm').and.resolveTo(true),
  prompt: () => Promise.resolve(null),
  success: jasmine.createSpy('success').and.resolveTo(),
  error: jasmine.createSpy('error').and.resolveTo(),
  info: jasmine.createSpy('info').and.resolveTo(),
  feedback: jasmine.createSpy('feedback').and.resolveTo(),
};

function configurer(codes: string[], routes: Routes = []) {
  for (const s of [dialogs.confirm, dialogs.success, dialogs.error, dialogs.info, dialogs.feedback]) s.calls.reset();
  dialogs.confirm.and.resolveTo(true);
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

async function ouvrir<T>(codes: string[], composant: Type<T>, url: string, chemin = 'page') {
  const http = configurer(codes, [{ path: chemin, component: composant }]);
  const harness = await RouterTestingHarness.create();
  const instance = await harness.navigateByUrl(url, composant);
  harness.detectChanges();
  return { http, harness, instance };
}

const BILAN_OK: BilanSuppression = { supprimable: true, conditions: [], dependances: [], alternative: 'Archiver', revision: 3 };
const BILAN_BLOQUE: BilanSuppression = {
  supprimable: false,
  conditions: ['statut « valide » : seuls brouillon et à valider sont supprimables'],
  dependances: [{ code: 'destinations', libelle: 'Destinations', nombre: 2 }],
  alternative: 'Archiver le fournisseur.',
  revision: 3,
};

describe('Refonte Studio — suppression sûre', () => {
  it('bloquée : dépendances listées, alternative proposée, aucun DELETE', async () => {
    configurer([]);
    const svc = TestBed.inject(IntegrationSuppressionService);
    const supprimer = jasmine.createSpy('supprimer').and.returnValue(of(null));
    const ok = await svc.supprimer({ objet: 'le fournisseur', nom: 'Acme', dependances: () => of(BILAN_BLOQUE), supprimer });
    expect(ok).toBeFalse();
    expect(supprimer).not.toHaveBeenCalled();
    expect(dialogs.confirm).not.toHaveBeenCalled();
    const message = dialogs.feedback.calls.mostRecent().args[0].message as string;
    expect(message).toContain('Destinations : 2');
    expect(message).toContain('Alternative : Archiver le fournisseur.');
  });

  it('confirmation refusée : aucun DELETE', async () => {
    configurer([]);
    dialogs.confirm.and.resolveTo(false);
    const supprimer = jasmine.createSpy('supprimer').and.returnValue(of(null));
    const ok = await TestBed.inject(IntegrationSuppressionService).supprimer({ objet: 'x', nom: 'y', dependances: () => of(BILAN_OK), supprimer });
    expect(ok).toBeFalse();
    expect(supprimer).not.toHaveBeenCalled();
  });

  it('confirmée : DELETE avec la révision du bilan, succès annoncé après la réponse', async () => {
    configurer([]);
    const supprimer = jasmine.createSpy('supprimer').and.returnValue(of(null));
    const ok = await TestBed.inject(IntegrationSuppressionService).supprimer({ objet: 'x', nom: 'y', dependances: () => of(BILAN_OK), supprimer });
    expect(ok).toBeTrue();
    expect(supprimer).toHaveBeenCalledOnceWith(3);
    expect(dialogs.success).toHaveBeenCalled();
  });

  it('refus serveur (409) : erreur affichée, aucun succès, la ligne reste', async () => {
    configurer([]);
    const err = new HttpErrorResponse({ status: 409, error: { code: 'SUPPRESSION_BLOQUEE', message: 'Bloqué' } });
    const ok = await TestBed.inject(IntegrationSuppressionService).supprimer({
      objet: 'x', nom: 'y', dependances: () => of(BILAN_OK), supprimer: () => throwError(() => err),
    });
    expect(ok).toBeFalse();
    expect(dialogs.error).toHaveBeenCalled();
    expect(dialogs.success).not.toHaveBeenCalled();
  });

  it('messageBlocage : une ligne par condition et par dépendance', () => {
    const m = messageBlocage({ objet: 'le fournisseur', nom: 'Acme' }, BILAN_BLOQUE);
    expect(m.split('\n').filter((l) => l.startsWith('•')).length).toBe(2);
  });
});

describe('Refonte Studio — tri', () => {
  it('même colonne = inversion ; nouvelle colonne = ordre initial', () => {
    expect(basculerTri({ tri: 'nom', ordre: 'asc' }, 'nom')).toEqual({ tri: 'nom', ordre: 'desc' });
    expect(basculerTri({ tri: 'nom', ordre: 'asc' }, 'statut', 'desc')).toEqual({ tri: 'statut', ordre: 'desc' });
    expect(ariaSort({ tri: 'nom', ordre: 'asc' }, 'nom')).toBe('ascending');
    expect(ariaSort({ tri: 'nom', ordre: 'asc' }, 'code')).toBe('none');
  });
});

describe('Refonte Studio — destinations', () => {
  const PAGE = {
    items: [{
      id: 'd1', code: 'D1', nom: 'Dest 1', fournisseur_id: FID, fournisseur_nom: 'Acme', environnement: 'TEST',
      statut: 'brouillon', hotes: ['api.example.com'], methodes: ['GET'], updated_at: '2026-10-21T10:00:00Z', nb_operations: 0,
    }],
    total: 1, page: 1, size: 25,
  };

  it('lecture seule : ni modifier ni supprimer ; fournisseur affiché ; aucun test lancé', async () => {
    const { http, harness } = await ouvrir([PERMISSIONS_DESTINATIONS.view], CoreAdminIntegrationDestinationsComponent, '/page');
    http.expectOne((r) => r.url === `${API}/destinations`).flush(PAGE);
    harness.detectChanges();
    const el = harness.routeNativeElement!;
    expect(texte(el)).toContain('Acme');
    expect(el.querySelector('[aria-label="Supprimer Dest 1"]')).toBeNull();
    expect(el.querySelector('[aria-label="Modifier Dest 1"]')).toBeNull();
    http.expectNone((r) => r.url.includes('/tests/'));
  });

  it('tri par en-tête : tri et ordre transmis au serveur', async () => {
    const { http, harness, instance } = await ouvrir([PERMISSIONS_DESTINATIONS.view], CoreAdminIntegrationDestinationsComponent, '/page');
    http.expectOne((r) => r.url === `${API}/destinations`).flush(PAGE);
    harness.detectChanges();
    instance.trier('nom');
    const req = http.expectOne((r) => r.url === `${API}/destinations`);
    expect(req.request.params.get('tri')).toBe('nom');
    expect(req.request.params.get('ordre')).toBe('asc');
    req.flush(PAGE);
  });

  it('gestion : suppression = bilan puis DELETE avec révision, puis rechargement', async () => {
    const { http, harness, instance } = await ouvrir(
      [PERMISSIONS_DESTINATIONS.view, PERMISSIONS_DESTINATIONS.manage],
      CoreAdminIntegrationDestinationsComponent,
      '/page',
    );
    http.expectOne((r) => r.url === `${API}/destinations`).flush(PAGE);
    harness.detectChanges();
    expect(harness.routeNativeElement!.querySelector('[aria-label="Supprimer Dest 1"]')).not.toBeNull();
    const fin = instance.supprimer(PAGE.items[0] as never);
    http.expectOne(`${API}/destinations/d1/dependances`).flush(BILAN_OK);
    await new Promise((r) => setTimeout(r));
    const del = http.expectOne((r) => r.method === 'DELETE');
    expect(del.request.urlWithParams).toContain('/destinations/d1?revision=3');
    del.flush(null, { status: 204, statusText: 'No Content' });
    await fin;
    http.expectOne((r) => r.url === `${API}/destinations`).flush({ ...PAGE, items: [], total: 0 });
    expect(dialogs.success).toHaveBeenCalled();
  });

  it('modification : la restriction d’opérations existante est renvoyée (jamais élargie en silence)', async () => {
    const { http, harness, instance } = await ouvrir(
      [PERMISSIONS_DESTINATIONS.view, PERMISSIONS_DESTINATIONS.manage, PERMISSIONS_STUDIO.fournisseurs],
      CoreAdminIntegrationDestinationFormComponent,
      '/page/d1',
      'page/:id',
    );
    http.expectOne(`${API}/destinations/d1`).flush({
      id: 'd1', code: 'D1', nom: 'Dest 1', fournisseur_id: FID, fournisseur_nom: 'Acme', fournisseur_statut: 'valide',
      environnement: 'TEST', protocole: 'https', statut: 'brouillon', hotes: ['api.example.com'], ports: [443],
      methodes: ['GET'], operations: ['op-1'], revision: 4, modifiable: true, transitions: [], updated_at: '', created_at: '', avertissement: '',
    });
    http.expectOne((r) => r.url === `${API}/fournisseurs/${FID}/operations`).flush({
      items: [{ id: 'op-1', statut: 'active', methode: 'GET', chemin: '/v1/a', origine: 'manuelle', tags: [], deprecie: false, conflit: false, updated_at: '' }],
      total: 1, page: 1, size: 200, avertissement: '',
    });
    harness.detectChanges();
    expect(instance.selection()).toEqual(['op-1']);
    instance.enregistrer();
    const patch = http.expectOne((r) => r.method === 'PATCH');
    expect(patch.request.body.operations).toEqual(['op-1']);
    expect(patch.request.body.revision).toBe(4);
    http.expectNone((r) => r.url.includes('/tests/'));
  });
});

describe('Refonte Studio — historique des exécutions', () => {
  it('recherche et tri transmis ; aucune action de suppression proposée', async () => {
    const { http, harness, instance } = await ouvrir([PERMISSIONS_STUDIO.testsView], CoreAdminIntegrationExecutionsComponent, '/page?q=abc&periode=tout');
    const req = http.expectOne((r) => r.url === `${API}/executions`);
    expect(req.request.params.get('q')).toBe('abc');
    req.flush({
      items: [{ id: 'e1', correlation_id: 'c1', fournisseur_id: FID, operation_id: 'o', destination_id: 'd', methode: 'GET', chemin: '/a', hote: 'h', started_at: '', statut: 'succes' }],
      total: 1, page: 1, size: 25, retention_jours: 90,
    });
    harness.detectChanges();
    expect(texte(harness.routeNativeElement!)).not.toContain('Supprimer');
    instance.trier('duree_ms');
    const tri = http.expectOne((r) => r.url === `${API}/executions`);
    expect(tri.request.params.get('tri')).toBe('duree_ms');
    expect(tri.request.params.get('ordre')).toBe('desc');
    tri.flush({ items: [], total: 0, page: 1, size: 25, retention_jours: 90 });
    http.expectNone((r) => r.method === 'DELETE');
  });
});

describe('Refonte Studio — alertes', () => {
  const RESOLUE = {
    id: 'a2', type: 'latence', statut: 'resolue', message: 'Latence', niveau: 'moyenne', occurences: 1, details: {},
    derniere_le: '2026-10-21T10:00:00Z', created_at: '2026-10-20T10:00:00Z', transitions: ['nouvelle'],
  };

  it('compteurs affichés ; un clic filtre par statut', async () => {
    const { http, harness, instance } = await ouvrir([PERMISSIONS_SUPERVISION.view], CoreAdminIntegrationAlertesComponent, '/page');
    http.expectOne((r) => r.url === `${API}/supervision/alertes`).flush({
      items: [], total: 0, page: 1, size: 25, compteurs: { nouvelle: 2, en_cours: 1, resolue: 4, ignoree: 0 },
    });
    harness.detectChanges();
    const t = texte(harness.routeNativeElement!);
    expect(t).toMatch(/Actives\s*3/);
    expect(t).toMatch(/Résolues\s*4/);
    instance.filtrerStatut('resolue');
    expect(http.expectOne((r) => r.url === `${API}/supervision/alertes`).request.params.get('statut')).toBe('resolue');
  });

  it('rouvrir : transition fournie par le serveur, confirmation puis PATCH ; jamais de DELETE', async () => {
    const { http, harness, instance } = await ouvrir(
      [PERMISSIONS_SUPERVISION.view, PERMISSIONS_SUPERVISION.manage],
      CoreAdminIntegrationAlertesComponent,
      '/page',
    );
    http.expectOne((r) => r.url === `${API}/supervision/alertes`).flush({ items: [RESOLUE], total: 1, page: 1, size: 25 });
    harness.detectChanges();
    const t = texte(harness.routeNativeElement!);
    expect(t).toContain('Rouvrir');
    expect(t).not.toContain('Résoudre');
    await instance.traiter(RESOLUE as never, 'nouvelle');
    expect(dialogs.confirm).toHaveBeenCalled();
    const patch = http.expectOne((r) => r.method === 'PATCH');
    expect(patch.request.body).toEqual({ statut: 'nouvelle' });
    http.expectNone((r) => r.method === 'DELETE');
  });

  it('détail : historique du traitement chargé à l’ouverture', async () => {
    const { http, harness, instance } = await ouvrir([PERMISSIONS_SUPERVISION.view], CoreAdminIntegrationAlertesComponent, '/page');
    http.expectOne((r) => r.url === `${API}/supervision/alertes`).flush({ items: [RESOLUE], total: 1, page: 1, size: 25 });
    instance.basculer('a2');
    http.expectOne(`${API}/supervision/alertes/a2/historique`).flush({
      items: [{ id: 'h1', acteur: { id: 'u', nom: 'Awa' }, created_at: '2026-10-21T10:00:00Z', avant: 'Nouvelle', apres: 'Résolue' }],
    });
    harness.detectChanges();
    expect(texte(harness.routeNativeElement!)).toContain('Awa');
  });
});

describe('Refonte Studio — graphiques de supervision', () => {
  it('aucune donnée : rien de simulé', () => {
    const g = construireGraphe([]);
    expect(g.aDonnees).toBeFalse();
    expect(g.cols.length).toBe(0);
    expect(g.taux.points.length).toBe(0);
  });

  it('une valeur nulle coupe la courbe et ne produit aucun point', () => {
    const c = courbe([1, null, 0.5], 1, ['a', 'b', 'c'], String);
    expect(c.points.length).toBe(2);
    expect(c.d.match(/M/g)?.length).toBe(2);
  });

  it('volume : hauteur proportionnelle, part de succès par jour', () => {
    const g = construireGraphe([
      { jour: '2026-10-20', total: 4, succes: 3, echecs: 1, taux_succes: 0.75, latence_moyenne_ms: 120 },
      { jour: '2026-10-21', total: 2, succes: 2, echecs: 0, taux_succes: 1, latence_moyenne_ms: null },
    ]);
    expect(g.cols[0].h).toBe(100);
    expect(g.cols[1].h).toBe(50);
    expect(g.cols[0].okPct).toBe(75);
    expect(g.latence.points.length).toBe(1);
  });
});

describe('Refonte Studio — assistant de test', () => {
  const OPS = `${API}/fournisseurs/f1/operations`;

  function monter() {
    const http = configurer([PERMISSIONS_STUDIO.testsExecute, PERMISSIONS_STUDIO.fournisseurs, PERMISSIONS_STUDIO.destinations]);
    const fixture = TestBed.createComponent(CoreAdminIntegrationTestComponent);
    fixture.componentInstance.fournisseurId = 'f1';
    fixture.detectChanges();
    http.expectOne((r) => r.url === OPS).flush({
      items: [{ id: 'op1', statut: 'active', methode: 'GET', chemin: '/v1/{id}', origine: 'manuelle', tags: [], deprecie: false, conflit: false, updated_at: '' }],
      total: 1, page: 1, size: 200, avertissement: '',
    });
    http.expectOne((r) => r.url === `${API}/destinations`).flush({
      items: [{ id: 'd1', code: 'D', nom: 'Dest', fournisseur_id: 'f1', environnement: 'TEST', statut: 'active', hotes: ['api.example.com'], methodes: ['GET'], updated_at: '' }],
      total: 1, page: 1, size: 100,
    });
    fixture.detectChanges();
    return { http, fixture };
  }

  it('étapes : sélection → paramètres → aperçu, sans aucun appel /tests/ automatique', () => {
    const { http, fixture } = monter();
    const c = fixture.componentInstance;
    expect(c.etapeCourante()).toBe(1);
    expect(fixture.nativeElement.querySelector('[aria-current="step"]')?.textContent).toContain('Sélection');
    c.form.setValue({ operation_id: 'op1', destination_id: 'd1' });
    http.expectOne(`${OPS}/op1`).flush({ id: 'op1', parametres: [{ nom: 'id', emplacement: 'path', requis: true }], configuration: { mecanisme_auth: 'aucun' } });
    fixture.detectChanges();
    expect(c.etapeCourante()).toBe(2);
    expect(c.raisonBlocage()).toContain('paramètres');
    c.ctrl('p_id').setValue('42');
    expect(c.etapeCourante()).toBe(3);
    expect(c.peutPreparer()).toBeTrue();
    http.expectNone((r) => r.url.includes('/tests/'));
  });

  it('états visuels distincts par résultat', () => {
    expect(etatExecution('succes')).toBe('succes');
    expect(etatExecution('http_erreur')).toBe('http');
    expect(etatExecution('dns')).toBe('reseau');
    expect(etatExecution('timeout')).toBe('delai');
    expect(etatExecution('secret_requis')).toBe('secret');
    expect(etatExecution('quota')).toBe('quota');
    expect(etatExecution('refuse_securite')).toBe('refus');
  });

  it('erreur de quota à l’aperçu : état « Quota atteint »', () => {
    const { http, fixture } = monter();
    const c = fixture.componentInstance;
    c.form.setValue({ operation_id: 'op1', destination_id: 'd1' });
    http.expectOne(`${OPS}/op1`).flush({ id: 'op1', parametres: [], configuration: { mecanisme_auth: 'aucun' } });
    c.preparer();
    http.expectOne(`${API}/tests/apercu`).flush({ code: 'QUOTA', message: 'Quota' }, { status: 429, statusText: 'T' });
    fixture.detectChanges();
    expect(c.etatErreur()).toBe('quota');
    expect(texte(fixture.nativeElement)).toContain('Quota atteint');
    http.expectNone((r) => r.url.includes('/tests/executer'));
  });
});
