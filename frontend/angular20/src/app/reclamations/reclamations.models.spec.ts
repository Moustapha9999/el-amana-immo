import { toneStatut } from './reclamations.models';

describe('Réclamations — teintes de statut', () => {
  it('distingue Suspendue de clôturé, rejeté, annulé et en traitement', () => {
    expect(toneStatut('SUSPENDUE')).toBe('SUSPENDU');
    expect(toneStatut('CLOTUREE')).toBe('ACTIF');
    expect(toneStatut('REJETEE')).toBe('REJETE');
    expect(toneStatut('ANNULEE')).toBe('ANNULEE');
    expect(toneStatut('EN_TRAITEMENT')).toBe('EN_PREPARATION');
    expect(toneStatut('A_QUALIFIER')).toBe('INFO');
    expect(toneStatut('REOUVERTE')).toBe('ATTENTION');
  });
});
