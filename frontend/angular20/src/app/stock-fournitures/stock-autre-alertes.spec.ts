import { TestBed } from '@angular/core/testing';
import { FormControl } from '@angular/forms';
import { of } from 'rxjs';
import { OrgEntiteLibelleSelectComponent } from '../core/org/org-entite-libelle-select.component';
import { OrgEntiteOption } from '../core/org/org-referentiel.models';
import { OrgReferentielService } from '../core/org/org-referentiel.service';
import { navForModule } from '../layout/shell/shell-nav';
import { AUTRE, corpsOrg, erreurAutre, libelleOrg, nettoyerLibelle } from './org-autre';
import { statutsPossibles } from './stock-alertes.component';

const ENTITES = [
  { id: 'd1', libelle: 'Département Informatique', type_entite: 'DEPARTEMENT', profondeur: 1, alias: ['dsi'] },
  { id: 's1', libelle: 'Service Réseaux', type_entite: 'SERVICE', parent_id: 'd1', profondeur: 2 },
] as unknown as OrgEntiteOption[];

describe('Stock — option « Autre » (département / service)', () => {
  it('nettoie les espaces superflus', () => {
    expect(nettoyerLibelle('  Cellule   Projets  ')).toBe('Cellule Projets');
    expect(nettoyerLibelle(null)).toBe('');
  });

  it('refuse une saisie vide ou un libellé déjà présent dans la liste', () => {
    expect(erreurAutre('   ', 'département', ENTITES)).toContain('Saisissez');
    expect(erreurAutre('departement  informatique', 'département', ENTITES)).toContain('existe déjà');
    expect(erreurAutre('DSI', 'département', ENTITES)).toContain('existe déjà');
    expect(erreurAutre('x'.repeat(121), 'service', ENTITES)).toContain('120');
    expect(erreurAutre('Cellule Projets', 'service', ENTITES)).toBeNull();
  });

  it('envoie l’identifiant du référentiel OU le libellé saisi, jamais les deux', () => {
    expect(corpsOrg({ departement_id: 'd1', departement_autre: '', service_id: 's1', service_autre: '' })).toEqual({
      departement_id: 'd1',
      service_id: 's1',
    });
    expect(corpsOrg({ departement_id: 'd1', departement_autre: '', service_id: AUTRE, service_autre: ' Accueil ' })).toEqual({
      departement_id: 'd1',
      service_autre: 'Accueil',
    });
    expect(
      corpsOrg({ departement_id: AUTRE, departement_autre: ' Projet  X ', service_id: AUTRE, service_autre: 'Cellule' }),
    ).toEqual({ departement_autre: 'Projet X', service_autre: 'Cellule' });
    expect(corpsOrg({ departement_id: AUTRE, departement_autre: 'Projet', service_id: '', service_autre: '' })).toEqual({
      departement_autre: 'Projet',
    });
  });

  it('compose un libellé lisible pour la confirmation', () => {
    expect(libelleOrg({ departement_id: 'd1', departement_autre: '', service_id: 's1', service_autre: '' }, ENTITES, '?')).toBe(
      'Département Informatique › Service Réseaux',
    );
    expect(
      libelleOrg({ departement_id: AUTRE, departement_autre: 'Projet', service_id: AUTRE, service_autre: 'Cellule' }, ENTITES, '?'),
    ).toBe('Projet › Cellule');
  });
});

describe('Sélecteur organigramme avec « Autre » (demandes)', () => {
  function creer() {
    TestBed.configureTestingModule({
      imports: [OrgEntiteLibelleSelectComponent],
      providers: [{ provide: OrgReferentielService, useValue: { entitesActives: () => of(ENTITES) } }],
    });
    const fixture = TestBed.createComponent(OrgEntiteLibelleSelectComponent);
    fixture.componentRef.setInput('autre', true);
    fixture.detectChanges();
    return fixture.componentInstance;
  }

  it('rend la saisie obligatoire quand « Autre » est choisi', () => {
    const c = creer();
    const ctrl = new FormControl<string | null>(null);
    c.choisir(AUTRE);
    expect(c.saisieLibre()).toBeTrue();
    expect(c.validate(ctrl)).toEqual(jasmine.objectContaining({ orgAutre: jasmine.any(String) }));
    c.saisir('  Cellule   Projets ');
    expect(c.value()).toBe('Cellule Projets');
    expect(c.validate(ctrl)).toBeNull();
  });

  it('masque la saisie quand une entité existante est choisie', () => {
    const c = creer();
    c.choisir(AUTRE);
    c.choisir('Département Informatique');
    expect(c.saisieLibre()).toBeFalse();
    expect(c.validate(new FormControl())).toBeNull();
  });

  it('réaffiche une valeur hors référentiel comme saisie « Autre » en modification', () => {
    const c = creer();
    c.writeValue('Projet spécial');
    expect(c.saisieLibre()).toBeTrue();
    expect(c.texteLibre()).toBe('Projet spécial');
  });
});

describe('Alertes stock — transitions de suivi', () => {
  it('ne propose pas « Résolue » tant que le stock reste sous le seuil', () => {
    expect(statutsPossibles({ statut: 'NOUVELLE', episode_ouvert: true })).not.toContain('RESOLUE');
    expect(statutsPossibles({ statut: 'NOUVELLE', episode_ouvert: false })).toContain('RESOLUE');
    expect(statutsPossibles({ statut: 'CLOTUREE', episode_ouvert: false })).toEqual(['EN_COURS']);
  });
});

describe('Notifications par module — menu', () => {
  it('ajoute une entrée Notifications propre au module', () => {
    const paths = navForModule('stock-fournitures').map((i) => i.path);
    expect(paths).toContain('/stock-fournitures/notifications');
    expect(paths.filter((p) => p.endsWith('/notifications')).length).toBe(1);
  });

  it('ne touche pas au menu immobilisations (URLs racine figées)', () => {
    const paths = navForModule('immobilisations').map((i) => i.path);
    expect(paths).not.toContain('/immobilisations/notifications');
  });
});
