import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { Dossier, ImportAnalyse } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';
import { RcImportComponent } from './rc-import.component';

function analyse(extra: Partial<ImportAnalyse> = {}): ImportAnalyse {
  return {
    id: 'imp-1',
    reclamation_id: 'd1',
    revision: 2,
    nom_fichier: 'ops-test.xlsx',
    statut: 'ANALYSE',
    mode: 'AJOUT',
    nb_lignes: 2,
    nb_valides: 1,
    nb_erreurs: 1,
    nb_avertissements: 0,
    lignes: [],
    clients: [],
    totaux: { nb: 1, nb_erreurs: 0, montant: '10', montant_conteste: null, devise: 'MRU' },
    nb_clients: 1,
    multi_clients: false,
    regroupement_autorise: true,
    justification_requise: false,
    justification_actuelle: null,
    apres_import: { nb: 1, nb_erreurs: 0, montant: '10', montant_conteste: null, devise: 'MRU' },
    nb_conservees: 0,
    document_id: null,
    created_at: null,
    par: null,
    confirme_le: null,
    confirme_par: null,
    ...extra,
  } as ImportAnalyse;
}

describe('Réclamations — import Excel des opérations', () => {
  let fixture: ComponentFixture<RcImportComponent>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [RcImportComponent],
      providers: [
        { provide: ReclamationsService, useValue: { lireImport: () => of(null) } },
        { provide: ReclamationsStore, useValue: { config: () => ({ champs_operation: [] }) } },
        { provide: FeedbackService, useValue: { warning: () => 0, apiError: () => 0, run: () => of(null) } },
      ],
    });
    fixture = TestBed.createComponent(RcImportComponent);
    fixture.componentRef.setInput('dossier', { id: 'd1', revision: 1, imports: [], motif_id: null } as unknown as Dossier);
    fixture.detectChanges();
  });

  it('n’autorise la confirmation que si l’aperçu n’a aucune erreur', () => {
    const c = fixture.componentInstance;
    expect(c.confirmable()).toBeFalse();
    c.analyse.set(analyse());
    fixture.detectChanges();
    expect(c.confirmable()).toBeFalse();
    expect(fixture.nativeElement.textContent).toContain('aucune ligne n’est enregistrée');
    c.analyse.set(analyse({ nb_erreurs: 0, nb_valides: 2, nb_lignes: 2 }));
    fixture.detectChanges();
    expect(c.confirmable()).toBeTrue();
  });

  it('exige une justification pour un regroupement multi-clients', () => {
    const c = fixture.componentInstance;
    c.analyse.set(analyse({
      nb_erreurs: 0, nb_valides: 2, multi_clients: true, justification_requise: true,
    }));
    expect(c.confirmable()).toBeFalse();
    c.justification.set('Meme incident, deux titulaires (test)');
    expect(c.confirmable()).toBeTrue();
  });
});
