import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { Comparaison } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';
import { RcComparaisonComponent } from './rc-comparaison.component';

const RESULTAT: Comparaison = {
  a: { debut: '2026-08-01', fin: '2026-08-31', jours: 31, valeurs: { recues: 1 } },
  b: { debut: '2026-09-01', fin: '2026-09-30', jours: 30, valeurs: { recues: 2 } },
  avertissements: ['Périodes de durées différentes (31 j contre 30 j).'],
  lignes: [
    {
      code: 'recues', libelle: 'Réclamations reçues', unite: 'dossiers', a: 1, b: 2,
      ecart: 1, variation: 100, favorable: null, sens: null, indicateur: null,
    },
    {
      code: 'taux_reouverture', libelle: 'Taux de réouverture', unite: '%', a: 20, b: 10,
      ecart: -10, variation: -50, favorable: true, sens: 'baisse_favorable', indicateur: 'reouvertes',
    },
  ],
};

describe('Réclamations — comparaison A/B', () => {
  let fixture: ComponentFixture<RcComparaisonComponent>;
  const comparaison = jasmine.createSpy('comparaison').and.returnValue(of(RESULTAT));
  const exportComparaison = jasmine.createSpy('exportComparaison').and.returnValue(of(new Blob(['x'])));
  const warning = jasmine.createSpy('warning');
  const run = jasmine.createSpy('run').and.callFake((fn: () => ReturnType<typeof of>) => fn());

  beforeEach(() => {
    comparaison.calls.reset();
    warning.calls.reset();
    TestBed.configureTestingModule({
      imports: [RcComparaisonComponent],
      providers: [
        provideRouter([]),
        { provide: ReclamationsService, useValue: { comparaison, exportComparaison } },
        { provide: ReclamationsStore, useValue: { cap: () => true } },
        { provide: FeedbackService, useValue: { warning, run } },
      ],
    });
    fixture = TestBed.createComponent(RcComparaisonComponent);
    fixture.componentRef.setInput('filtres', { client_agence_id: 'ag-1' });
    fixture.detectChanges();
  });

  it('refuse des périodes incomplètes ou inversées, puis affiche écart et variation', () => {
    const c = fixture.componentInstance;
    c.aDebut = '';
    c.comparer();
    expect(warning).toHaveBeenCalled();
    expect(comparaison).not.toHaveBeenCalled();
    c.aDebut = '2026-09-01';
    c.aFin = '2026-08-01';
    c.bDebut = '2026-09-01';
    c.bFin = '2026-09-30';
    c.comparer();
    expect(comparaison).not.toHaveBeenCalled();
    c.aDebut = '2026-08-01';
    c.aFin = '2026-08-31';
    c.comparer();
    expect(comparaison).toHaveBeenCalledWith(
      jasmine.objectContaining({ a_debut: '2026-08-01', b_fin: '2026-09-30' }),
      { client_agence_id: 'ag-1' },
    );
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Réclamations reçues');
    expect(fixture.nativeElement.textContent).toContain('durées différentes');
    expect(fixture.nativeElement.textContent).toContain('Favorable');
    expect(c.lien(RESULTAT.lignes[0], '2026-08-01', '2026-08-31')).toEqual({
      client_agence_id: 'ag-1', date_debut: '2026-08-01', date_fin: '2026-08-31',
    });
  });
});
