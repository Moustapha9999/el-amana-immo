import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { Dossier } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';
import { RcActionsComponent } from './rc-actions.component';

function dossier(actions: Record<string, boolean>, extra: Partial<Dossier> = {}): Dossier {
  return {
    id: 'd1',
    reference: 'REC-2026-000001',
    objet: 'Prélèvement contesté (test)',
    statut: 'A_QUALIFIER',
    statut_libelle: 'À qualifier',
    revision: 1,
    actions,
    suspension: null,
    ...extra,
  } as Dossier;
}

describe('Réclamations — actions du circuit', () => {
  let fixture: ComponentFixture<RcActionsComponent>;
  let component: RcActionsComponent;
  const action = jasmine.createSpy('action').and.returnValue(of({ reference: 'REC-2026-000001', statut_libelle: 'Suspendue' }));
  const warning = jasmine.createSpy('warning');
  const run = jasmine.createSpy('run').and.callFake((fn: () => unknown) => of((fn as () => unknown)()));

  beforeEach(() => {
    action.calls.reset();
    warning.calls.reset();
    run.calls.reset();
    TestBed.configureTestingModule({
      imports: [RcActionsComponent],
      providers: [
        { provide: ReclamationsService, useValue: { action } },
        { provide: ReclamationsStore, useValue: { unitesActives: () => [], libelles: () => [] } },
        { provide: FeedbackService, useValue: { warning, run } },
      ],
    });
    fixture = TestBed.createComponent(RcActionsComponent);
    component = fixture.componentInstance;
  });

  it('n’affiche que les boutons autorisés par le backend (dont clôture réservée au SR)', () => {
    fixture.componentRef.setInput('dossier', dossier({ cloturer: false, affecter: true, suspendre: true }, { statut: 'A_CLOTURER' }));
    fixture.detectChanges();
    const libelles = component.visibles().map((b) => b.code);
    expect(libelles).toEqual(['affecter', 'suspendre']);
    expect(fixture.nativeElement.textContent).toContain('La clôture est réservée au Service Réclamations central.');
  });

  it('affiche Clôturer seulement si le backend l’autorise', () => {
    fixture.componentRef.setInput('dossier', dossier({ cloturer: true }, { statut: 'A_CLOTURER' }));
    fixture.detectChanges();
    expect(component.visibles().map((b) => b.code)).toEqual(['cloturer']);
    expect(fixture.nativeElement.textContent).not.toContain('La clôture est réservée');
  });

  it('propose Rouvrir sur un dossier clôturé, sans le confondre avec Suspendre', () => {
    fixture.componentRef.setInput('dossier', dossier({ rouvrir: true, archiver: true, suspendre: false }, { statut: 'CLOTUREE' }));
    fixture.detectChanges();
    expect(component.visibles().map((b) => b.code)).toEqual(['rouvrir', 'archiver']);
  });

  it('propose Suspendre et exige un motif ; Reprendre restaure le circuit', () => {
    fixture.componentRef.setInput('dossier', dossier({ suspendre: true }));
    fixture.detectChanges();
    const suspendre = component.visibles().find((b) => b.code === 'suspendre')!;
    expect(suspendre.motif).toBeTrue();
    component.ouvrir(suspendre);
    component.confirmer();
    expect(warning).toHaveBeenCalled();
    expect(action).not.toHaveBeenCalled();
    component.f.motif = 'Piece attendue';
    component.confirmer();
    expect(action).toHaveBeenCalledWith('d1', 'suspendre', jasmine.objectContaining({ revision: 1, motif: 'Piece attendue' }));

    fixture.componentRef.setInput(
      'dossier',
      dossier({ reprendre: true, affecter: false }, {
        statut: 'SUSPENDUE',
        suspension: { depuis: '2026-10-23T10:00:00Z', motif: 'Piece attendue', statut_avant: 'A_QUALIFIER', statut_avant_libelle: 'À qualifier' },
      }),
    );
    fixture.detectChanges();
    expect(component.visibles().map((b) => b.code)).toEqual(['reprendre']);
    expect(fixture.nativeElement.textContent).toContain('Dossier suspendu');
    const reprendre = component.visibles()[0];
    component.ouvrir(reprendre);
    component.confirmer();
    expect(action).toHaveBeenCalledWith('d1', 'reprendre', jasmine.objectContaining({ revision: 1 }));
  });
});
