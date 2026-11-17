import { routes } from '../app.routes';
import { MODULES_WITH_METIER_SHELL, getModuleRouteContract } from '../plateforme/module-routing.contract';
import { navForModule } from '../layout/shell/shell-nav';
import { placeRowMenu } from '../contrats-echeances/shared/row-menu';
import { rbcmPageWindow } from './rbcm-pager.component';
import { RbcmCampaign, currentGuidedStep, guidedStepState } from './rbcm.models';

describe('Reporting BCM SM — navigation et routes', () => {
  it('enregistre le contrat préfixé et le shell métier', () => {
    const c = getModuleRouteContract('reporting-bcm-sm');
    expect(c?.entryPath).toBe('/reporting-bcm-sm/accueil');
    expect(c?.espacePath).toBe('/comptabilite');
    expect(c?.urlPrefix).toBe('/reporting-bcm-sm');
    expect(MODULES_WITH_METIER_SHELL.has('reporting-bcm-sm')).toBeTrue();
  });

  it('expose les entrées de menu métier T3.4', () => {
    const paths = navForModule('reporting-bcm-sm').map((i) => i.path);
    expect(paths).toContain('/reporting-bcm-sm/accueil');
    expect(paths).toContain('/reporting-bcm-sm/campagnes');
    expect(paths).toContain('/reporting-bcm-sm/imports');
    expect(paths).toContain('/reporting-bcm-sm/bal-det');
    expect(paths).not.toContain('/reporting-bcm-sm/bal-cond');
    expect(paths).toContain('/reporting-bcm-sm/rapprochement');
    expect(paths).toContain('/reporting-bcm-sm/parametres');
    expect(paths).toContain('/reporting-bcm-sm/mapping');
    expect(navForModule('reporting-bcm-sm').find((i) => i.path.includes('rapprochement'))?.label).toBe('Contrôles');
  });

  it('déclare les routes Angular sous reporting-bcm-sm', () => {
    const rbcm = routes.find((r) => r.path === 'reporting-bcm-sm');
    const enfants = (rbcm?.children ?? []).map((c) => c.path);
    expect(enfants).toContain('accueil');
    expect(enfants).toContain('campagnes');
    expect(enfants).toContain('campagnes/nouvelle');
    expect(enfants).toContain('campagnes/:id');
    expect(enfants).toContain('imports');
    expect(enfants).toContain('bal-det');
    // Route archives conservée (hors menu) — pas d’upload COND.
    expect(enfants).toContain('bal-cond');
    expect(enfants).toContain('rapprochement');
    expect(enfants).toContain('parametres');
    expect(enfants).toContain('mapping');
  });

  it('place une SM brouillon à l’étape BAL DET du parcours guidé', () => {
    const c = {
      id: 'x',
      period_year: 2026,
      period_month: 3,
      closing_date: null,
      bank_code: 'BEA',
      status: 'BROUILLON',
      campaign_version: 1,
      reopened_from_id: null,
      preparer_id: 'a',
      notes: null,
      created_at: '',
      updated_at: '',
    } as RbcmCampaign;
    expect(currentGuidedStep(c, null)).toBe(2);
    expect(guidedStepState(1, 2)).toBe('done');
    expect(guidedStepState(2, 2)).toBe('current');
    expect(guidedStepState(5, 2)).toBe('blocked');
  });

  it('place une SM avec DET et contrôles à l’étape informations à compléter', () => {
    const c = {
      id: 'x',
      period_year: 2026,
      period_month: 11,
      closing_date: null,
      bank_code: 'BEA',
      status: 'CALCULEE',
      campaign_version: 1,
      reopened_from_id: null,
      preparer_id: 'a',
      notes: null,
      created_at: '',
      updated_at: '',
    } as RbcmCampaign;
    expect(currentGuidedStep(c, { det_validated: true, last_control_run_id: 'r1' } as never)).toBe(4);
    expect(currentGuidedStep(c, { det_validated: true } as never)).toBe(3);
    expect(guidedStepState(5, 4)).toBe('blocked');
  });

  it('calcule la plage affichée sans charger toute la liste', () => {
    expect(rbcmPageWindow(1, 25, 242)).toEqual({ start: 1, end: 25, pages: 10 });
    expect(rbcmPageWindow(10, 25, 242)).toEqual({ start: 226, end: 242, pages: 10 });
    expect(rbcmPageWindow(1, 100, 0)).toEqual({ start: 0, end: 0, pages: 1 });
    expect(rbcmPageWindow(3, 50, 242).start).toBe(101);
  });

  it('ouvre le menu vers le haut près du bas et le garde dans l’écran', () => {
    const below = placeRowMenu({ top: 200, bottom: 232, right: 900 }, 160, 220, { width: 1200, height: 800 });
    expect(below.top).toBe(236);
    expect(below.left).toBe(680);

    const above = placeRowMenu({ top: 740, bottom: 772, right: 400 }, 160, 220, { width: 1200, height: 800 });
    expect(above.top).toBe(576);

    const edge = placeRowMenu({ top: 100, bottom: 132, right: 40 }, 120, 220, { width: 360, height: 640 });
    expect(edge.left).toBe(8);
    expect(edge.left + 220).toBeLessThanOrEqual(360);

    const nearRight = placeRowMenu({ top: 80, bottom: 112, right: 1188 }, 176, 280, { width: 1200, height: 800 });
    expect(nearRight.left + 280).toBeLessThanOrEqual(1192);
    expect(nearRight.left).toBeGreaterThanOrEqual(8);
  });
});
