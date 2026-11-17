# Playwright — Reporting BCM SM (DEV)

Environnement cible : **http://localhost** (compose BEA DIGITAL).  
Aucun test contre la production.

## Installation

```powershell
cd e2e\reporting-bcm-sm
npm install
npm run install:browsers
```

## Exécution

```powershell
$env:RBCM_E2E_EMAIL="admin@el-amana.mr"
$env:RBCM_E2E_PASSWORD="Admin@2026"
npm test
```

Les scénarios couvrent navigation SM, terminologie (absence de « Campagne » métier), imports, BAL DET, contrôles, paramètres, correspondances, archives COND et viewports responsive.
