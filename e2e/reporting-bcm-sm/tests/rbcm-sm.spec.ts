import { expect, test, type Page } from '@playwright/test';

const EMAIL = process.env.RBCM_E2E_EMAIL || 'admin@el-amana.mr';
const PASSWORD = process.env.RBCM_E2E_PASSWORD || 'Admin@2026';

async function login1(page: Page): Promise<void> {
  await page.goto('/login');
  await page.getByPlaceholder('Email').fill(EMAIL);
  await page.getByPlaceholder('Mot de passe').fill(PASSWORD);
  await page.getByRole('button', { name: /^CONNEXION$/i }).click();
  await page.waitForURL(/\/accueil(\?|$)/, { timeout: 45_000 });
}

async function ensureModule(page: Page): Promise<void> {
  if (/\/reporting-bcm-sm\//.test(page.url()) && !(await page.locator('button.bea-module-acces__submit').count())) {
    return;
  }
  await page.goto('/modules/reporting-bcm-sm/acces?returnUrl=%2Freporting-bcm-sm%2Faccueil');
  await page.waitForLoadState('domcontentloaded');
  if (await page.locator('button.bea-module-acces__submit').count()) {
    await page.getByRole('textbox', { name: /Identifiant/i }).fill(EMAIL);
    await page.getByRole('textbox', { name: /Mot de passe/i }).fill(PASSWORD);
    await page.locator('button.bea-module-acces__submit').click();
  }
  await page.waitForURL(/\/reporting-bcm-sm\//, { timeout: 60_000 });
}

async function openModulePath(page: Page, path: string): Promise<void> {
  await ensureModule(page);
  await page.goto(path);
  if (await page.locator('button.bea-module-acces__submit').count()) {
    await ensureModule(page);
    await page.goto(path);
  }
}

test.describe('Reporting BCM SM — T3.4-C', () => {
  test.beforeEach(async ({ page }) => {
    await login1(page);
    await ensureModule(page);
  });

  test('accès Accueil et terminologie SM', async ({ page }) => {
    await openModulePath(page, '/reporting-bcm-sm/accueil');
    await expect(page.getByRole('heading', { name: /Reporting BCM/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Situations mensuelles/i }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /Nouvelle SM/i }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /Archives BAL COND/i })).toBeVisible();
    const body = await page.locator('body').innerText();
    expect(body).not.toMatch(/\bNouvelle campagne\b/);
    expect(body).not.toMatch(/\bFiche campagne\b/);
  });

  test('navigation Situations mensuelles + filtres', async ({ page }) => {
    await openModulePath(page, '/reporting-bcm-sm/campagnes');
    await expect(page.getByRole('heading', { name: /Situations mensuelles/i })).toBeVisible();
    await page.getByPlaceholder(/Recherche/i).fill('2026');
    await page.waitForTimeout(450);
    await expect(page.locator('.bea-mg__table, .bea-rbcm-empty').first()).toBeVisible();
  });

  test('fiche SM + bloc D01/D02', async ({ page }) => {
    await openModulePath(page, '/reporting-bcm-sm/campagnes');
    const link = page.locator('a[href*="/reporting-bcm-sm/campagnes/"]').filter({ hasNotText: /nouvelle/i }).first();
    if (await link.count()) {
      await link.click();
      await expect(page.getByRole('heading', { name: /^SM / })).toBeVisible({ timeout: 20_000 });
      await expect(page.getByText(/D01/)).toBeVisible();
      await expect(page.getByText(/D02/)).toBeVisible();
    }
  });

  test('Imports BAL DET — drawer prévisualisation', async ({ page }) => {
    await openModulePath(page, '/reporting-bcm-sm/imports');
    await expect(page.getByRole('heading', { name: /Imports/i })).toBeVisible();
    const voir = page.getByRole('button', { name: /^Voir$/ }).first();
    if (await voir.count()) {
      await voir.click();
      await expect(page.getByText(/Informations fichier|SHA-256|Structure/i).first()).toBeVisible();
      await page.keyboard.press('Escape');
    }
  });

  test('BAL DET lecture seule', async ({ page }) => {
    await openModulePath(page, '/reporting-bcm-sm/bal-det');
    await expect(page.getByRole('heading', { name: /BAL DET/i })).toBeVisible();
    await expect(page.getByText(/Lecture seule/i)).toBeVisible();
  });

  test('Contrôles — anomalies', async ({ page }) => {
    await openModulePath(page, '/reporting-bcm-sm/rapprochement');
    await expect(page.getByRole('heading', { name: /Contrôles BAL DET/i })).toBeVisible();
  });

  test('Paramètres et Correspondances', async ({ page }) => {
    await openModulePath(page, '/reporting-bcm-sm/parametres');
    await expect(page.getByRole('heading', { name: /Paramètres/i })).toBeVisible();
    await openModulePath(page, '/reporting-bcm-sm/mapping');
    await expect(page.getByRole('heading', { name: /Correspondance/i })).toBeVisible();
  });

  test('Archives BAL COND', async ({ page }) => {
    await openModulePath(page, '/reporting-bcm-sm/bal-cond');
    await expect(page.locator('body')).toContainText(/BAL COND|Archives|historique/i);
  });

  test('notifications module', async ({ page }) => {
    await openModulePath(page, '/reporting-bcm-sm/notifications');
    await expect(page.locator('body')).toBeVisible();
  });
});

test.describe('Responsive Reporting BCM SM', () => {
  const viewports = [
    { w: 1920, h: 1080 },
    { w: 1571, h: 952 },
    { w: 1366, h: 768 },
    { w: 1024, h: 768 },
    { w: 768, h: 1024 },
  ];

  for (const vp of viewports) {
    test(`accueil ${vp.w}x${vp.h}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.w, height: vp.h });
      await login1(page);
      await ensureModule(page);
      await openModulePath(page, '/reporting-bcm-sm/accueil');
      const overflow = await page.evaluate(() => {
        const el = document.scrollingElement || document.documentElement;
        return el.scrollWidth - el.clientWidth;
      });
      expect(overflow).toBeLessThan(48);
      await expect(page.getByRole('heading', { name: /Reporting BCM/i })).toBeVisible();
    });
  }
});
