import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting, TestRequest } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { FormControl } from '@angular/forms';
import { ActivatedRoute, convertToParamMap, provideRouter, Router } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { BeaAdminDialogService } from './core-admin-dialog.service';
import { CoreAdminIntegrationFournisseurFicheComponent, detailsEvenement } from './core-admin-integration-fournisseur-fiche.component';
import { CoreAdminIntegrationFournisseurFormComponent } from './core-admin-integration-fournisseur-form.component';
import { CoreAdminIntegrationFournisseurOperationFormComponent } from './core-admin-integration-fournisseur-operation-form.component';
import { CoreAdminIntegrationFournisseurOperationComponent } from './core-admin-integration-fournisseur-operation.component';
import { CoreAdminIntegrationFournisseursComponent } from './core-admin-integration-fournisseurs.component';
import {
  AnalyseSpec,
  AUCUN_APPEL,
  cheminValide,
  codesReponse,
  extensionAcceptee,
  FournisseurFiche,
  lireSchema,
  OperationDetail,
  PERMISSIONS_FOURNISSEURS,
  TRANSITIONS_FOURNISSEUR,
  urlBaseValide,
} from './core-admin-integration-fournisseurs.models';
import { CoreAdminIntegrationFournisseursService } from './core-admin-integration-fournisseurs.service';
import { CORE_ADMIN_NAV, coreAdminNavVisible } from './core-admin-nav';

const BASE = '/api/v1/plateforme/admin/integrations/fournisseurs';
const P = PERMISSIONS_FOURNISSEURS;
const EMPREINTE = 'a'.repeat(64);

const FICHE: FournisseurFiche = {
  id: 'f1',
  code: 'EXT-ABCD1234',
  nom: 'Bureau de crédit',
  description: null,
  entite: null,
  environnement: 'DEV',
  statut: 'a_valider',
  url_base: 'https://api.exemple.invalid/v1',
  version_courante: 1,
  nb_operations: 2,
  created_at: '2026-10-21T10:00:00Z',
  updated_at: '2026-10-21T10:00:00Z',
  revision: 4,
  modifiable: true,
  transitions: ['brouillon', 'valide'],
  avertissement: 'Configuration seulement.',
};

const ANALYSE: AnalyseSpec = {
  valide: true,
  nom_fichier: 'api.yaml',
  taille: 1200,
  empreinte: EMPREINTE,
  format: 'yaml',
  openapi_version: '3.1.0',
  titre: 'API test',
  version_api: '1.0',
  serveurs: [{ url: 'https://api.exemple.invalid' }],
  securite: [{ nom: 'cle', type: 'apiKey', emplacement: 'header', nom_parametre: 'X-API-Key' }],
  nb_operations: 1,
  operations: [{ cle: 'GET /a', methode: 'GET', chemin: '/a', deprecie: false }],
  erreurs: [],
  avertissements: [{ niveau: 'avertissement', code: 'REFERENCE_EXTERNE', message: 'Référence externe jamais chargée' }],
  version_courante: 1,
  deja_importee: null,
  diff: { ajoutees: ['GET /a'], supprimees: [], modifiees: [], inchangees: 1 },
  conflits: ['GET /a'],
  avertissement: 'Analyse locale.',
};

function operation(extra: Partial<OperationDetail> = {}): OperationDetail {
  return {
    id: 'o1',
    origine: 'openapi',
    statut: 'active',
    methode: 'GET',
    chemin: '/clients/{id}',
    operation_id: 'lireClient',
    nom: 'Lire un client',
    tags: [],
    deprecie: false,
    spec_numero: 1,
    conflit: false,
    updated_at: '2026-10-21T10:00:00Z',
    parametres: [{ nom: 'id', emplacement: 'path', requis: true, schema: { type: 'string' } }],
    entetes: [],
    corps: null,
    reponses: [{ code: '200', contenus: [] }],
    authentification: [],
    mecanismes: [],
    revision: 1,
    source: 'Spécification importée v1 (version courante) — déclarée par le fournisseur, non vérifiée.',
    avertissements: ['Exemple non testé.'],
    elements_declares: ['Méthode et chemin'],
    elements_verifies: [],
    exemples: [{ langage: 'curl', libelle: 'cURL', code: 'curl "$EXTERNAL_API_BASE_URL/clients/<id>"' }],
    created_at: '2026-10-21T10:00:00Z',
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

function configurer(codes: string[], opts: { query?: Record<string, string>; params?: Record<string, string> } = {}) {
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

describe('API externes — fonctions', () => {
  it('URL de base : forme seulement, sans identifiant, paramètre ni fragment', () => {
    expect(urlBaseValide(new FormControl('https://api.exemple.invalid/v1'))).toBeNull();
    expect(urlBaseValide(new FormControl(''))).toBeNull();
    expect(urlBaseValide(new FormControl('https://user:mdp@api.exemple.invalid'))).toEqual({ urlIdentifiants: true });
    expect(urlBaseValide(new FormControl('https://api.exemple.invalid/?k=v'))).toEqual({ url: true });
    expect(urlBaseValide(new FormControl('ftp://api.exemple.invalid'))).toEqual({ url: true });
    expect(urlBaseValide(new FormControl('javascript:alert(1)'))).toEqual({ url: true });
  });

  it('chemin relatif, codes HTTP, schéma JSON, extensions', () => {
    expect(cheminValide(new FormControl('/clients/{id}'))).toBeNull();
    for (const mauvais of ['clients', '/a b', '/a?x=1', '/a/../b', '//a', "/a'b"]) {
      expect(cheminValide(new FormControl(mauvais))).withContext(mauvais).toEqual({ chemin: true });
    }
    expect(codesReponse('404, 200 200')).toEqual([200, 404]);
    expect(codesReponse('200, 99')).toBeNull();
    expect(codesReponse('')).toBeNull();
    expect(lireSchema('').valeur).toBeNull();
    expect(lireSchema('{"type":"object"}').valeur).toEqual({ type: 'object' });
    expect(lireSchema('[1]').erreur).toContain('objet');
    expect(lireSchema('{"$ref":"#/x"}').erreur).toContain('$ref');
    expect(extensionAcceptee('api.YAML')).toBeTrue();
    expect(extensionAcceptee('api.txt')).toBeFalse();
  });

  it('validation et suspension réservées au droit validate, suspension avec motif', () => {
    expect(TRANSITIONS_FOURNISSEUR.valide?.droit).toBe('validate');
    expect(TRANSITIONS_FOURNISSEUR.suspendu?.droit).toBe('validate');
    expect(TRANSITIONS_FOURNISSEUR.suspendu?.motif).toBe('obligatoire');
    expect(TRANSITIONS_FOURNISSEUR.a_valider?.droit).toBe('manage');
    expect(TRANSITIONS_FOURNISSEUR.archive).toBeUndefined();
  });

  it('historique : seuls les champs modifiés', () => {
    const e = {
      id: 'e1',
      action: 'x',
      libelle: 'x',
      created_at: '',
      details: { avant: { statut: 'brouillon', nom: 'A' }, apres: { statut: 'a_valider', nom: 'A' } },
    };
    expect(detailsEvenement(e)).toBe('statut : brouillon → a_valider');
  });

  it('menu : « Fournisseurs externes » masqué sans la permission', () => {
    const libelles = (codes: string[], su = false) =>
      coreAdminNavVisible(CORE_ADMIN_NAV, codes, su).flatMap((g) => g.items.map((i) => i.label));
    expect(libelles([])).not.toContain('Fournisseurs externes');
    expect(libelles([P.view])).toContain('Fournisseurs externes');
    expect(libelles([], true)).toContain('Fournisseurs externes');
  });
});

describe('API externes — service', () => {
  it('routes, révision, envoi du fichier en multipart sans URL distante', () => {
    const { http } = configurer([]);
    const svc = TestBed.inject(CoreAdminIntegrationFournisseursService);
    svc.changerStatut('f/1', 4, 'suspendu', 'Incident').subscribe();
    const statut = http.expectOne(`${BASE}/f%2F1/statut`);
    expect(statut.request.body).toEqual({ revision: 4, statut: 'suspendu', motif: 'Incident' });

    const fichier = new File(['openapi: 3.1.0'], 'api.yaml', { type: 'application/yaml' });
    svc.analyser('f1', fichier).subscribe();
    const analyse = http.expectOne(`${BASE}/f1/specs/analyse`);
    expect(analyse.request.body instanceof FormData).toBeTrue();
    expect((analyse.request.body as FormData).get('file')).toBe(fichier);

    svc.importer('f1', fichier, EMPREINTE, 1, true).subscribe();
    const imp = http.expectOne(`${BASE}/f1/specs`);
    const corps = imp.request.body as FormData;
    expect(corps.get('empreinte')).toBe(EMPREINTE);
    expect(corps.get('version_courante')).toBe('1');
    expect(corps.get('accepter_conflits')).toBe('true');

    svc.operations('f1', { q: ' client ', origine: 'manuelle' }).subscribe();
    const ops = http.expectOne((r) => r.url === `${BASE}/f1/operations`);
    expect(ops.request.params.get('q')).toBe('client');
    expect(ops.request.params.get('origine')).toBe('manuelle');
    expect(ops.request.params.has('methode')).toBeFalse();
    http.verify();
  });
});

describe('API externes — liste', () => {
  it('bandeau « aucun appel externe », pas de création sans droit manage', () => {
    const { http } = configurer([P.view], { query: { statut: 'valide' } });
    const fixture = TestBed.createComponent(CoreAdminIntegrationFournisseursComponent);
    fixture.detectChanges();
    const req = http.expectOne((r) => r.url === BASE);
    expect(req.request.params.get('statut')).toBe('valide');
    req.flush({ items: [], total: 0, page: 1, size: 25, avertissement: '' });
    fixture.detectChanges();
    const t = texte(fixture.nativeElement);
    expect(t).toContain(AUCUN_APPEL);
    expect(t).toContain('Aucun fournisseur d\'API ne correspond');
    expect(t).not.toContain('Nouveau fournisseur');
  });

  it('liste et accès refusé', () => {
    let ctx = configurer([P.view, P.manage]);
    let fixture = TestBed.createComponent(CoreAdminIntegrationFournisseursComponent);
    fixture.detectChanges();
    ctx.http.expectOne((r) => r.url === BASE).flush({ items: [FICHE], total: 1, page: 1, size: 25, avertissement: '' });
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('EXT-ABCD1234');
    expect(texte(fixture.nativeElement)).toContain('À valider');
    expect(texte(fixture.nativeElement)).toContain('Nouveau fournisseur');

    TestBed.resetTestingModule();
    ctx = configurer([]);
    fixture = TestBed.createComponent(CoreAdminIntegrationFournisseursComponent);
    fixture.detectChanges();
    ctx.http.expectOne((r) => r.url === BASE).flush({ code: 'PERMISSION_DENIED' }, { status: 403, statusText: 'F' });
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Accès refusé');
    expect(texte(fixture.nativeElement)).toContain(P.view);
  });
});

describe('API externes — formulaire fournisseur', () => {
  it('refuse une URL avec identifiants et un secret, sans appel serveur', async () => {
    const { http, dialog } = configurer([P.manage]);
    const fixture = TestBed.createComponent(CoreAdminIntegrationFournisseurFormComponent);
    fixture.detectChanges();
    viderOrg(http);
    const c = fixture.componentInstance;
    c.form.patchValue({ nom: 'Bureau', url_base: 'https://admin:secret@api.exemple.invalid' });
    c.form.markAllAsTouched();
    await c.enregistrer();
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Aucun identifiant ni mot de passe dans l’URL');
    c.form.patchValue({ url_base: '', notes: 'password=Azerty1' });
    await c.enregistrer();
    expect(dialog.confirm).not.toHaveBeenCalled();
    http.expectNone(BASE);
  });

  it('crée après confirmation ; succès seulement après réponse serveur', async () => {
    const { http, dialog } = configurer([P.manage]);
    const fixture = TestBed.createComponent(CoreAdminIntegrationFournisseurFormComponent);
    fixture.detectChanges();
    viderOrg(http);
    const c = fixture.componentInstance;
    c.form.patchValue({ nom: ' Bureau ', environnement: 'TEST', url_base: 'https://api.exemple.invalid/' });
    await c.enregistrer();
    await attendre();
    const req = http.expectOne(BASE);
    expect(req.request.body).toEqual({
      nom: 'Bureau',
      environnement: 'TEST',
      org_entite_id: null,
      responsable_interne: null,
      contact_technique: null,
      url_base: 'https://api.exemple.invalid/',
      description: null,
      documentation: null,
      notes: null,
    });
    expect('statut' in req.request.body).toBeFalse();
    expect(dialog.success).not.toHaveBeenCalled();
    req.flush(FICHE);
    expect(dialog.success.calls.mostRecent().args[0]).toContain(AUCUN_APPEL);
  });
});

describe('API externes — fiche fournisseur', () => {
  function ouvrir(codes: string[], onglet?: string, fiche: FournisseurFiche = FICHE) {
    const ctx = configurer(codes, { params: { id: 'f1' }, query: onglet ? { onglet } : {} });
    const fixture = TestBed.createComponent(CoreAdminIntegrationFournisseurFicheComponent);
    fixture.detectChanges();
    ctx.http.expectOne(`${BASE}/f1`).flush(fiche);
    fixture.detectChanges();
    return { ...ctx, fixture };
  }

  it('lecture seule : pas d’onglet import ni d’action', () => {
    const { fixture } = ouvrir([P.view]);
    const tabs = Array.from(fixture.nativeElement.querySelectorAll('[role="tab"]') as NodeListOf<HTMLElement>).map((b) =>
      (b.textContent ?? '').trim(),
    );
    expect(tabs).toEqual(['Fiche', 'Opérations', 'Versions', 'Historique']);
    expect(boutons(fixture.nativeElement, 'Archiver').length).toBe(0);
    expect(texte(fixture.nativeElement)).toContain(AUCUN_APPEL);
  });

  it('gestionnaire ne voit pas « Valider » ; validateur oui', () => {
    let ctx = ouvrir([P.view, P.manage]);
    expect(boutons(ctx.fixture.nativeElement, 'Valider la configuration').length).toBe(0);
    expect(boutons(ctx.fixture.nativeElement, 'Revenir en brouillon').length).toBe(1);

    TestBed.resetTestingModule();
    ctx = ouvrir([P.view, P.validate]);
    expect(boutons(ctx.fixture.nativeElement, 'Valider la configuration').length).toBe(1);
    expect(boutons(ctx.fixture.nativeElement, 'Revenir en brouillon').length).toBe(0);
  });

  it('import : aperçu, conflits à accepter, puis envoi avec empreinte et version lues', async () => {
    const { http, fixture, dialog } = ouvrir([P.view, P.manage], 'import');
    const c = fixture.componentInstance;
    const fichier = new File(['openapi: 3.1.0'], 'api.yaml');
    c.fichier.set(fichier);
    c.analyser();
    http.expectOne(`${BASE}/f1/specs/analyse`).flush(ANALYSE);
    fixture.detectChanges();
    const t = texte(fixture.nativeElement);
    expect(t).toContain('REFERENCE_EXTERNE');
    expect(t).toContain('1 ajoutée(s)');
    expect(t).toContain('(non contacté)');
    expect(t).toContain('Conflit avec des opérations manuelles');
    expect(c.importable()).toBeFalse();
    await c.importer();
    expect(dialog.confirm).not.toHaveBeenCalled();

    c.accepterConflits.set(true);
    await c.importer();
    await attendre();
    const req = http.expectOne(`${BASE}/f1/specs`);
    const corps = req.request.body as FormData;
    expect(corps.get('empreinte')).toBe(EMPREINTE);
    expect(corps.get('version_courante')).toBe('1');
    expect(corps.get('accepter_conflits')).toBe('true');
    expect(dialog.success).not.toHaveBeenCalled();
    req.flush({ ...ANALYSE, id: 's2', numero: 2, courante: true, nb_avertissements: 1, avertissements: [] });
    http.expectOne(`${BASE}/f1`).flush(FICHE);
    expect(dialog.success.calls.mostRecent().args[0]).toContain('v2');
    expect(c.analyse()).toBeNull();
  });

  it('import : spécification refusée ou déjà importée non confirmable', () => {
    const { http, fixture } = ouvrir([P.view, P.manage], 'import');
    const c = fixture.componentInstance;
    c.fichier.set(new File(['x'], 'api.json'));
    c.analyser();
    http.expectOne(`${BASE}/f1/specs/analyse`).flush({
      ...ANALYSE,
      valide: false,
      conflits: [],
      erreurs: [{ niveau: 'erreur', code: 'SECRET_SUSPECT', message: 'Valeur ressemblant à un secret' }],
    });
    fixture.detectChanges();
    expect(texte(fixture.nativeElement)).toContain('Spécification refusée');
    expect(c.importable()).toBeFalse();
    c.analyser();
    http.expectOne(`${BASE}/f1/specs/analyse`).flush({ ...ANALYSE, conflits: [], deja_importee: 1 });
    expect(c.importable()).toBeFalse();
  });

  it('fichier d’extension inattendue refusé localement', () => {
    const { fixture, http } = ouvrir([P.view, P.manage], 'import');
    const c = fixture.componentInstance;
    const input = document.createElement('input');
    Object.defineProperty(input, 'files', { value: [new File(['x'], 'api.txt')] });
    c.choisirFichier({ target: input } as unknown as Event);
    expect(c.fichier()).toBeNull();
    expect(c.fichierErreur()).toContain('.json');
    http.expectNone(`${BASE}/f1/specs/analyse`);
  });
});

describe('API externes — opération', () => {
  function ouvrir(codes: string[], op: OperationDetail) {
    const ctx = configurer(codes, { params: { id: 'f1', opId: 'o1' } });
    const fixture = TestBed.createComponent(CoreAdminIntegrationFournisseurOperationComponent);
    fixture.detectChanges();
    ctx.http.expectOne(`${BASE}/f1`).flush(FICHE);
    ctx.http.expectOne(`${BASE}/f1/operations/o1`).flush(op);
    fixture.detectChanges();
    return { ...ctx, fixture };
  }

  it('exemples marqués non testés, rien de vérifié, pas d’action sur une opération importée', () => {
    const { fixture } = ouvrir([P.view, P.manage], operation());
    const t = texte(fixture.nativeElement);
    expect(t).toContain('Non testé');
    expect(t).toContain('rien n\'a été vérifié auprès du fournisseur');
    expect(t).toContain('$EXTERNAL_API_BASE_URL');
    expect(t).toContain('non vérifiée');
    expect(boutons(fixture.nativeElement, 'Archiver').length).toBe(0);
  });

  it('opération manuelle active : archivage avec révision', async () => {
    const { fixture, http, dialog } = ouvrir([P.view, P.manage], operation({ origine: 'manuelle', spec_numero: null, revision: 3 }));
    boutons(fixture.nativeElement, 'Archiver')[0].click();
    await attendre();
    expect(dialog.confirm).toHaveBeenCalled();
    const req = http.expectOne(`${BASE}/f1/operations/o1/archive`);
    expect(req.request.body).toEqual({ revision: 3 });
  });
});

describe('API externes — opération manuelle', () => {
  it('bloque secret, en-tête réservé et paramètre de chemin non déclaré', async () => {
    const { http, dialog } = configurer([P.manage], { params: { id: 'f1' } });
    const fixture = TestBed.createComponent(CoreAdminIntegrationFournisseurOperationFormComponent);
    fixture.detectChanges();
    const c = fixture.componentInstance;
    c.form.patchValue({ nom: 'Lire', chemin: '/clients/{id}', description: 'token=abcdef123' });
    await c.enregistrer();
    expect(dialog.confirm).not.toHaveBeenCalled();

    c.form.patchValue({ description: '' });
    c.ajouterEntete();
    c.entetes.at(0).patchValue({ nom: 'Authorization' });
    await c.enregistrer();
    expect(c.entetes.at(0).get('nom')?.errors?.['reserve']).toBeTrue();
    expect(dialog.confirm).not.toHaveBeenCalled();

    c.entetes.removeAt(0);
    await c.enregistrer();
    expect(c.erreurCoherence()).toContain('doit être déclaré');
    expect(dialog.confirm).not.toHaveBeenCalled();
    http.expectNone(`${BASE}/f1/operations`);
  });

  it('crée une opération cohérente ; aucun champ de secret envoyé', async () => {
    const { http, dialog } = configurer([P.manage], { params: { id: 'f1' } });
    const fixture = TestBed.createComponent(CoreAdminIntegrationFournisseurOperationFormComponent);
    fixture.detectChanges();
    const c = fixture.componentInstance;
    c.form.patchValue({
      nom: 'Lire',
      methode: 'GET',
      chemin: '/clients/{id}',
      codes: '200, 404',
      mecanisme_auth: 'api_key_header',
      nom_cle_api: 'X-API-Key',
      corps_schema: '{"type":"object"}',
      reponse_schema: '{"type":"object"}',
    });
    c.ajouterParametre();
    c.parametres.at(0).patchValue({ nom: 'id', emplacement: 'path' });
    await c.enregistrer();
    await attendre();
    const req = http.expectOne(`${BASE}/f1/operations`);
    expect(req.request.body).toEqual({
      nom: 'Lire',
      description: null,
      methode: 'GET',
      chemin: '/clients/{id}',
      parametres: [{ nom: 'id', emplacement: 'path', requis: true, type: 'string', description: null }],
      entetes: [],
      corps_schema: null,
      reponse_schema: { type: 'object' },
      mecanisme_auth: 'api_key_header',
      nom_cle_api: 'X-API-Key',
      codes_reponse: [200, 404],
      notes: null,
    });
    expect(dialog.success).not.toHaveBeenCalled();
    req.flush(operation({ origine: 'manuelle' }));
    expect(dialog.success.calls.mostRecent().args[0]).toContain(AUCUN_APPEL);
  });
});
