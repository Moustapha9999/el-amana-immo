import { libellePeriode } from './stock-mouvement-edit.component';
import { DatesSaisie, corpsDate, dateMin, erreurDate, estRetroactive, periodePourDate } from './stock-date-mouvement';

const REF: DatesSaisie = {
  date_du_jour: '2026-11-02',
  peut_regulariser: true,
  periodes_saisie: [
    { id: 'p9', libelle: 'Septembre 2026', statut: 'ROUVERTE', date_debut: '2026-09-01', date_fin: '2026-09-30' },
    { id: 'p11', libelle: 'Novembre 2026', statut: 'OUVERTE', date_debut: '2026-11-01', date_fin: '2026-11-30' },
  ],
};

describe('Date du mouvement (saisie rétroactive)', () => {
  it('borne la saisie à la première période ouverte ou rouverte', () => {
    expect(dateMin(REF)).toBe('2026-09-01');
    expect(dateMin(null)).toBeNull();
  });

  it('aujourd’hui = date serveur (null), jour passé = midi UTC', () => {
    expect(corpsDate(REF, '2026-11-02')).toBeNull();
    expect(corpsDate(REF, '2026-09-15')).toBe('2026-09-15T12:00:00Z');
    expect(estRetroactive(REF, '2026-09-15')).toBeTrue();
    expect(estRetroactive(REF, '2026-11-02')).toBeFalse();
  });

  it('refuse le futur et les périodes clôturées', () => {
    expect(erreurDate(REF, '2026-11-03')).toContain('postérieure');
    expect(erreurDate(REF, '2026-10-10')).toContain('période clôturée');
    expect(erreurDate({ ...REF, peut_regulariser: false }, '2026-10-10')).toContain('administrateur');
    expect(erreurDate(REF, '2026-09-15')).toBeNull();
    expect(periodePourDate(REF, '2026-09-15')?.statut).toBe('ROUVERTE');
  });

  it('libellé de période d’un mouvement', () => {
    const base = { id: '', reference: '', date_mouvement: '', type_mouvement: 'ENTREE', article_id: '', quantite: 1,
                   agence_id: null, motif: null, observation: null };
    expect(libellePeriode({ ...base, periode_statut: 'ROUVERTE' })).toBe('Rouverte (régularisation)');
    expect(libellePeriode({ ...base, periode_statut: 'CLOTUREE', periode_cloturee: true })).toBe('Clôturée');
    expect(libellePeriode({ ...base, periode_statut: 'OUVERTE' })).toBe('Ouverte');
  });
});
