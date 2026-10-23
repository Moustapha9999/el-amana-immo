import { routes } from '../app.routes';
import { navForModule } from '../layout/shell/shell-nav';

describe('Réclamations — navigation et routes', () => {
  it('n’a plus de menu ni de route « Délais & alertes »', () => {
    const items = navForModule('reclamations');
    const libelles = items.map((i) => i.label.toLowerCase());
    const paths = items.map((i) => i.path);
    expect(libelles.some((l) => l.includes('délai') || l.includes('alerte'))).toBeFalse();
    expect(paths.some((p) => p.includes('delai') || p.includes('alerte'))).toBeFalse();
    expect(paths).toContain('/reclamations/dashboard');
    expect(paths).toContain('/reclamations/dossiers');
    expect(paths).toContain('/reclamations/parametres');
  });

  it('conserve les URLs métier et n’ajoute pas /reclamations/delais', () => {
    const rc = routes.find((r) => r.path === 'reclamations');
    const enfants = (rc?.children ?? []).map((c) => c.path);
    expect(enfants).toContain('dashboard');
    expect(enfants).toContain('dossiers');
    expect(enfants).toContain('dossiers/:id');
    expect(enfants).toContain('circuit');
    expect(enfants).toContain('rapports');
    expect(enfants).not.toContain('delais');
    expect(enfants).not.toContain('alertes');
  });
});
