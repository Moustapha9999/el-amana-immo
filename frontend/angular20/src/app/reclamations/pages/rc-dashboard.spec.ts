import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { TableauBord } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';
import { RcDashboardComponent } from './rc-dashboard.component';

const TB: TableauBord = {
  total: 5,
  ouvertes: 3,
  suspendues: 1,
  volume_30j: 2,
  volume_30j_precedent: 1,
  cloturees_30j: 1,
  performance: { cloturees: 1, delai_moyen_jours: 4, delai_cloture_jours: 4, delai_cloture_n: 1 },
  liens: {
    total: { date_debut: null, date_fin: null },
    ouvertes: { ouvertes: 'true' },
    suspendues: { statut: 'SUSPENDUE' },
    volume_30j: { date_debut: '2026-09-23' },
    delai_moyen: { indicateur: 'delai_cloture_termines' },
    operations: { indicateur: 'avec_operations' },
  },
  filtres: { client_agence_id: null, date_debut: null, date_fin: null },
  anciennete: [],
  tendance: [],
  resultats: [],
  clients_recurrents: [],
  nb_operations: 2,
  dossiers_avec_operations: 1,
  montant_total: '20',
  devise: 'MRU',
  statuts: [{ code: 'SUSPENDUE', libelle: 'Suspendue', n: 1 }],
  etapes: [],
  priorites: [],
  types: [],
  motifs: [],
  canaux: [],
  agences: [],
  services: [],
  unites_reception: [],
  recents: [],
};

describe('Réclamations — tableau de bord', () => {
  let fixture: ComponentFixture<RcDashboardComponent>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [RcDashboardComponent],
      providers: [
        provideRouter([]),
        { provide: ReclamationsService, useValue: { tableauDeBord: () => of(TB) } },
        {
          provide: ReclamationsStore,
          useValue: { cap: () => false, config: () => ({ agences: [] }), charger: () => undefined },
        },
        { provide: FeedbackService, useValue: { apiError: () => 0 } },
      ],
    });
    fixture = TestBed.createComponent(RcDashboardComponent);
    fixture.detectChanges();
  });

  it('affiche le KPI Suspendues et le relie à la liste filtrée, sans KPI d’échéance', () => {
    const texte = fixture.nativeElement.textContent as string;
    expect(texte).toContain('Suspendues');
    expect(texte).toContain('Ouvertes');
    expect(texte).not.toContain('En retard');
    expect(texte).not.toContain('Échéance proche');
    expect(texte).not.toContain('Sans délai');
    const c = fixture.componentInstance;
    c.data.set(TB);
    expect(c.kpi('suspendues')).toEqual({ statut: 'SUSPENDUE', client_agence_id: null });
    expect(c.kpi('ouvertes')).toEqual({ ouvertes: 'true', client_agence_id: null });
  });
});
