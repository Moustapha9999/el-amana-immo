import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting, TestRequest } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { FormControl } from '@angular/forms';
import { ActivatedRoute, convertToParamMap, provideRouter, Router } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIntegrationClientFicheComponent } from './core-admin-integration-client-fiche.component';
import { CoreAdminIntegrationClientFormComponent } from './core-admin-integration-client-form.component';
import { CoreAdminIntegrationClientsComponent } from './core-admin-integration-clients.component';
import {
  clientsParams,
  GRANT_ACTIONS,
  IntegrationClientFiche,
  IntegrationGrant,
  messageErreur,
  PERMISSIONS_CLIENTS,
  sansSecret,
  uneLigne,
} from './core-admin-integration-clients.models';
import { CoreAdminIntegrationClientsService } from './core-admin-integration-clients.service';
import { CORE_ADMIN_NAV, coreAdminNavVisible } from './core-admin-nav';

const BASE = '/api/v1/plateforme/admin/integrations/clients';
const P = PERMISSIONS_CLIENTS;

const FICHE: IntegrationClientFiche = {
  id: 'c1',
  code: 'INT-ABCD1234',
  nom: 'Portail test',
  description: 'Démo',
  entite: null,
  environnement: 'DEV',
  statut: 'en_preparation',
  nb_operations: 1,
  nb_approuvees: 0,
  created_at: '2026-10-20T10:00:00Z',
  updated_at: '2026-10-20T10:00:00Z',
  cree_par: { id: 'u1', nom: 'Agent' },
  modifie_par: { id: 'u1', nom: 'Agent' },
  contact_technique: null,
  finalite: 'Consultation',
  notes: null,
  revision: 3,
  transitions: ['brouillon', 'active'],
  avertissement: 'Une fiche ne permet à aucune application de s’authentifier.',
};

function grant(statut: IntegrationGrant['statut'], extra: Partial<IntegrationGrant> = {}): IntegrationGrant {
  return {
    id: `g-${statut}`,
    operation_id: 'get.x.lire',
    methode: 'GET',
    chemin: '/api/v1/x',
    module: 'x',
    permissions: ['x.read'],
    exigence_permissions: 'x.read',
    statut,
    created_at: '2026-10-20T10:00:00Z',
    updated_at: '2026-10-20T10:00:00Z',
    catalogue_present: true,
    admissible: true,
    ...extra,
  };
}

class DialogStub {
  confirmer = true;
  valeurs: Record<string, string> | null = { motif: '' };
  confirm = jasmine.createSpy('confirm').and.callFake(() => Promise.resolve(this.confirmer));
  prompt = jasmine.createSpy('prompt').and.callFake(() => Promise.resolve(this.valeurs));
  success = jasmine.createSpy('success').and.returnValue(Promise.resolve());
  error = jasmine.createSpy('error').and.returnValue(Promise.resolve());
}

function configurer(codes: string[], opts: { query?: Record<string, string>; params?: Record<string, string>; url?: string } = {}) {
  const dialog = new DialogStub();
  TestBed.configureTestingModule({
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      provideRouter([]),
      { provide: BeaAdminDialogService, useValue: dialog },
      { provide: AuthService, useValue: { user: signal({ is_superuser: false, permission_codes: codes, full_name: 'T' }) } },
      {
        provide: ActivatedRoute,
        useValue: {
          snapshot: { queryParamMap: convertToParamMap(opts.query ?? {}), paramMap: convertToParamMap(opts.params ?? {}) },
        },
      },
    ],
  });
  spyOn(TestBed.inject(Router), 'navigate').and.resolveTo(true);
  return { http: TestBed.inject(HttpTestingController), dialog };
}

function texte(el: HTMLElement): string {
  return (el.textContent ?? '').replace(/\s+/g, ' ');
}

function boutons(el: HTMLElement, libelle: string): HTMLButtonElement[] {
  return Array.from(el.querySelectorAll('button') as NodeListOf<HTMLButtonElement>).filter((b) =>
    (b.textContent ?? '').trim().startsWith(libelle),
  );
}

async function attendre(): Promise<void> {
  for (let i = 0; i < 5; i++) await Promise.resolve();
}

function viderOrg(http: HttpTestingController): void {
  http.match((r) => r.url.includes('/organisation/')).forEach((r: TestRequest) => r.flush({ items: [] }));
}

describe('Applications clientes — fonctions', () => {
  it('ignore filtres vides et booléens faux', () => {
    expect(clientsParams({ q: ' ', statut: 'active', inclure_archivees: false, tri: 'nom' }, 2, 25)).toEqual({
      page: 2,
      size: 25,
      statut: 'active',
      tri: 'nom',
    });
    expect(clientsParams({ inclure_archivees: true }, 1, 10)['inclure_archivees']).toBeTrue();
  });

  it('refuse les secrets et les retours à la ligne comme le serveur', () => {
    expect(sansSecret(new FormControl('password=Azerty1'))).toEqual({ secret: true });
    expect(sansSecret(new FormControl('Bearer abcdefghijklmnop1234'))).toEqual({ secret: true });
    expect(sansSecret(new FormControl('Consultation des référentiels'))).toBeNull();
    expect(uneLigne(new FormControl('a\nb'))).toEqual({ multiligne: true });
  });

  it('message d’erreur standard avec référence de requête', () => {
    const err = new HttpErrorResponse({
      status: 409,
      error: { code: 'CLIENT_DOUBLON', message: 'Doublon', user_message: 'Une application de même nom existe déjà', request_id: 'REQ-1' },
    });
    expect(messageErreur(err, 'x')).toBe('Une application de même nom existe déjà (réf. REQ-1)');
    expect(messageErreur(new Error('x'), 'repli')).toBe('repli');
  });

  it('approbation uniquement depuis « en attente » et réservée au droit approve', () => {
    const vers = Object.entries(GRANT_ACTIONS).flatMap(([de, actions]) => actions.map((a) => ({ de, ...a })));
    const approb = vers.filter((a) => a.cible === 'approuvee');
    expect(approb.map((a) => a.de)).toEqual(['en_attente']);
    expect(vers.filter((a) => ['approuvee', 'refusee', 'revoquee'].includes(a.cible)).every((a) => a.droit === 'grantsApprove')).toBeTrue();
    expect(vers.filter((a) => ['refusee', 'revoquee'].includes(a.cible)).every((a) => a.motif === 'obligatoire')).toBeTrue();
  });

  it('menu : entrée masquée sans la permission', () => {
    const libelles = (codes: string[], su = false) =>
      coreAdminNavVisible(CORE_ADMIN_NAV, codes, su).flatMap((g) => g.items.map((i) => i.label));
    expect(libelles([])).not.toContain('Applications clientes');
    expect(libelles([])).not.toContain('Catalogue API');
    expect(libelles(['core.admin.integrations.view'])).toContain('Catalogue API');
    expect(libelles([P.clientsView])).toContain('Applications clientes');
    expect(libelles([], true)).toContain('Applications clientes');
  });
});

describe('Applications clientes — service', () => {
  it('appelle les routes attendues avec révision et encodage', () => {
    const { http } = configurer([]);
    const svc = TestBed.inject(CoreAdminIntegrationClientsService);
    svc.modifier('a/b', 4, { statut: 'active' }).subscribe();
    const patch = http.expectOne(`${BASE}/a%2Fb`);
    expect(patch.request.method).toBe('PATCH');
    expect(patch.request.body).toEqual({ statut: 'active', revision: 4 });
    patch.flush(FICHE);
    svc.archiver('c1', 2, 'Fin').subscribe();
    expect(http.expectOne(`${BASE}/c1/archive`).request.body).toEqual({ revision: 2, motif: 'Fin' });
    svc.decider('c1', 'g1', 'refusee', 'Hors finalité').subscribe();
    expect(http.expectOne(`${BASE}/c1/grants/g1`).request.body).toEqual({ statut: 'refusee', motif: 'Hors finalité' });
    svc.demander('c1', ['op1'], null).subscribe();
    expect(http.expectOne(`${BASE}/c1/grants`).request.body).toEqual({ operation_ids: ['op1'], justification: null });
    svc.admissibles('c1', { q: ' lire ', admissibles_seulement: true }).subscribe();
    const adm = http.expectOne((r) => r.url === `${BASE}/c1/operations-admissibles`);
    expect(adm.request.params.get('q')).toBe('lire');
    expect(adm.request.params.get('admissibles_seulement')).toBe('true');
  });
});

describe('Applications clientes — liste', () => {
  it('reprend les filtres de l’URL, affiche l’état vide, masque la création sans droit', () => {
    const { http } = configurer([P.clientsView], { query: { statut: 'active', environnement: 'TEST' } });
    const fixture = TestBed.createComponent(CoreAdminIntegrationClientsComponent);
    fixture.detectChanges();
    const req = http.expectOne((r) => r.url === BASE);
    expect(req.request.params.get('statut')).toBe('active');
    expect(req.request.params.get('environnement')).toBe('TEST');
    expect(req.request.params.has('inclure_archivees')).toBeFalse();
    req.flush({ items: [], total: 0, page: 1, size: 25, avertissement: '' });
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Aucune application cliente ne correspond');
    expect(texte(fixture.nativeElement)).not.toContain('Nouvelle application');
    expect(texte(fixture.nativeElement)).toContain('ne permet à aucune application de s\'authentifier');
  });

  it('affiche la liste et le bouton de création avec le droit manage', () => {
    const { http } = configurer([P.clientsView, P.clientsManage]);
    const fixture = TestBed.createComponent(CoreAdminIntegrationClientsComponent);
    fixture.detectChanges();
    http.expectOne((r) => r.url === BASE).flush({ items: [FICHE], total: 1, page: 1, size: 25, avertissement: '' });
    fixture.detectChanges();
    const t = texte(fixture.nativeElement);
    expect(t).toContain('Portail test');
    expect(t).toContain('INT-ABCD1234');
    expect(t).toContain('En préparation');
    expect(t).toContain('Nouvelle application');
  });

  it('accès refusé sur 403 et erreur avec Réessayer sur 500', () => {
    let ctx = configurer([]);
    let fixture = TestBed.createComponent(CoreAdminIntegrationClientsComponent);
    fixture.detectChanges();
    ctx.http.expectOne((r) => r.url === BASE).flush({ code: 'PERMISSION_DENIED' }, { status: 403, statusText: 'F' });
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Accès refusé');
    expect(texte(fixture.nativeElement)).toContain(P.clientsView);

    TestBed.resetTestingModule();
    ctx = configurer([P.clientsView]);
    fixture = TestBed.createComponent(CoreAdminIntegrationClientsComponent);
    fixture.detectChanges();
    ctx.http.expectOne((r) => r.url === BASE).flush({ message: 'Erreur interne', request_id: 'REQ-9' }, { status: 500, statusText: 'KO' });
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Erreur interne (réf. REQ-9)');
    expect(texte(fixture.nativeElement)).toContain('Réessayer');
  });
});

describe('Applications clientes — formulaire', () => {
  it('bloque un nom vide ou un secret sans appel serveur', async () => {
    const { http, dialog } = configurer([P.clientsManage]);
    const fixture = TestBed.createComponent(CoreAdminIntegrationClientFormComponent);
    fixture.detectChanges();
    viderOrg(http);
    const c = fixture.componentInstance;
    await c.enregistrer();
    expect(dialog.confirm).not.toHaveBeenCalled();
    c.form.patchValue({ nom: 'Portail', notes: 'token=abc123' });
    c.form.markAllAsTouched();
    await c.enregistrer();
    fixture.detectChanges();
    expect(dialog.confirm).not.toHaveBeenCalled();
    expect(texte(fixture.nativeElement)).toContain('Ne saisissez aucun secret');
    http.expectNone(BASE);
  });

  it('crée après confirmation, sans champ interdit, succès après réponse serveur', async () => {
    const { http, dialog } = configurer([P.clientsManage]);
    const fixture = TestBed.createComponent(CoreAdminIntegrationClientFormComponent);
    fixture.detectChanges();
    viderOrg(http);
    const c = fixture.componentInstance;
    c.form.patchValue({ nom: '  Portail  ', environnement: 'TEST', finalite: ' Lecture ' });
    await c.enregistrer();
    await attendre();
    const req = http.expectOne(BASE);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({
      nom: 'Portail',
      environnement: 'TEST',
      statut: 'brouillon',
      org_entite_id: null,
      contact_technique: null,
      description: null,
      finalite: 'Lecture',
      notes: null,
    });
    expect(dialog.success).not.toHaveBeenCalled();
    req.flush({ ...FICHE, nom: 'Portail' });
    expect(dialog.success).toHaveBeenCalled();
  });

  it('modification : envoie la révision lue et affiche l’erreur serveur', async () => {
    const { http, dialog } = configurer([P.clientsManage], { params: { id: 'c1' } });
    const fixture = TestBed.createComponent(CoreAdminIntegrationClientFormComponent);
    fixture.detectChanges();
    http.expectOne(`${BASE}/c1`).flush(FICHE);
    fixture.detectChanges();
    viderOrg(http);
    const c = fixture.componentInstance;
    expect(c.statutsPossibles()).toEqual(['en_preparation', 'brouillon', 'active']);
    c.form.patchValue({ description: 'Nouvelle' });
    await c.enregistrer();
    await attendre();
    const req = http.expectOne(`${BASE}/c1`);
    expect(req.request.body.revision).toBe(3);
    req.flush({ code: 'CONFLIT_REVISION', message: 'Modifiée entre-temps', request_id: 'REQ-2' }, { status: 409, statusText: 'C' });
    expect(dialog.error).toHaveBeenCalledWith('Modifiée entre-temps (réf. REQ-2)');
  });
});

describe('Applications clientes — fiche', () => {
  function ouvrir(codes: string[], onglet?: string) {
    const ctx = configurer(codes, { params: { id: 'c1' }, query: onglet ? { onglet } : {} });
    const fixture = TestBed.createComponent(CoreAdminIntegrationClientFicheComponent);
    fixture.detectChanges();
    ctx.http.expectOne(`${BASE}/c1`).flush(FICHE);
    fixture.detectChanges();
    return { ...ctx, fixture };
  }

  it('onglets selon les permissions', () => {
    const { fixture } = ouvrir([P.clientsView]);
    const tabs = Array.from(fixture.nativeElement.querySelectorAll('[role="tab"]') as NodeListOf<HTMLElement>).map((b) =>
      (b.textContent ?? '').trim(),
    );
    expect(tabs).toEqual(['Fiche']);
    expect(texte(fixture.nativeElement)).not.toContain('Archiver');
    expect(texte(fixture.nativeElement)).toContain('pas un identifiant d\'authentification');
  });

  it('gestionnaire : pas de bouton Approuver ; approbateur : Approuver et Refuser avec motif obligatoire', async () => {
    let ctx = ouvrir([P.clientsView, P.grantsView, P.grantsManage], 'autorisations');
    ctx.http.expectOne(`${BASE}/c1/grants`).flush({ items: [grant('en_attente')], compteurs: { en_attente: 1 }, avertissement: 'Demandes' });
    ctx.fixture.detectChanges();
    expect(boutons(ctx.fixture.nativeElement, 'Approuver').length).toBe(0);
    expect(boutons(ctx.fixture.nativeElement, 'Retirer').length).toBe(1);

    TestBed.resetTestingModule();
    ctx = ouvrir([P.clientsView, P.grantsView, P.grantsApprove], 'autorisations');
    ctx.http.expectOne(`${BASE}/c1/grants`).flush({ items: [grant('en_attente')], compteurs: { en_attente: 1 }, avertissement: 'Demandes' });
    ctx.fixture.detectChanges();
    expect(boutons(ctx.fixture.nativeElement, 'Approuver').length).toBe(1);
    expect(boutons(ctx.fixture.nativeElement, 'Retirer').length).toBe(0);

    ctx.dialog.valeurs = { motif: 'Hors finalité' };
    boutons(ctx.fixture.nativeElement, 'Refuser')[0].click();
    await attendre();
    const options = ctx.dialog.prompt.calls.mostRecent().args[0];
    expect(options.validate({ motif: ' ' })).toBe('Motif obligatoire.');
    const req = ctx.http.expectOne(`${BASE}/c1/grants/g-en_attente`);
    expect(req.request.body).toEqual({ statut: 'refusee', motif: 'Hors finalité' });
  });

  it('signale une opération devenue indisponible', () => {
    const { http, fixture } = ouvrir([P.clientsView, P.grantsView], 'autorisations');
    http
      .expectOne(`${BASE}/c1/grants`)
      .flush({ items: [grant('approuvee', { admissible: false, motif_inadmissible: 'Module « x » non actif (desactive).' })], compteurs: {}, avertissement: '' });
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Opération indisponible : Module « x » non actif');
  });

  it('opérations : seules les admissibles sont sélectionnables, aperçu avant demande', async () => {
    const { http, fixture, dialog } = ouvrir([P.clientsView, P.grantsManage], 'operations');
    const base = { nom: 'n', module: 'x', permissions: ['x.read'], authentification: 'login2' };
    http.expectOne((r) => r.url === `${BASE}/c1/operations-admissibles`).flush({
      items: [
        { ...base, operation_id: 'ok', methode: 'GET', chemin: '/api/v1/x', admissible: true },
        { ...base, operation_id: 'ko', methode: 'POST', chemin: '/api/v1/x/export', admissible: false, motif_inadmissible: 'Opération sensible' },
        { ...base, operation_id: 'deja', methode: 'GET', chemin: '/api/v1/y', admissible: true, deja_demandee: 'en_attente' },
      ],
      total: 3,
      page: 1,
      size: 25,
      avertissement: '',
    });
    fixture.detectChanges();
    const cases = Array.from(fixture.nativeElement.querySelectorAll('tbody input[type="checkbox"]') as NodeListOf<HTMLInputElement>);
    expect(cases.map((c) => c.disabled)).toEqual([false, true, true]);
    cases[0].click();
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Accès envisagés (1)');
    expect(texte(fixture.nativeElement)).toContain('aucune permission utilisateur ni aucun rôle n\'est modifié');
    boutons(fixture.nativeElement, 'Demander ces opérations')[0].click();
    await attendre();
    expect(dialog.confirm).toHaveBeenCalled();
    const req = http.expectOne(`${BASE}/c1/grants`);
    expect(req.request.body.operation_ids).toEqual(['ok']);
  });

  it('accès refusé sur la fiche', () => {
    const ctx = configurer([], { params: { id: 'c1' } });
    const fixture = TestBed.createComponent(CoreAdminIntegrationClientFicheComponent);
    fixture.detectChanges();
    ctx.http.expectOne(`${BASE}/c1`).flush({ code: 'PERMISSION_DENIED' }, { status: 403, statusText: 'F' });
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Accès refusé');
  });
});
