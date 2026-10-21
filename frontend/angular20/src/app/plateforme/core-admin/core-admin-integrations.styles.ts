/*
 * Habillage du Studio d'intégration API : limité aux composants du Studio (encapsulation Angular),
 * variables --bea-* existantes, aucune bibliothèque. Les animations ne retardent aucune action
 * (pas de pointer-events bloqués, durées courtes) et sont coupées par prefers-reduced-motion.
 */
const STUDIO_DESIGN = `
  :host { display: block; }

  /* En-têtes de page */
  .bea-admin-dash__head h1 { letter-spacing: -0.01em; }
  .bea-admin-dash__head p:not(.bea-admin-kicker) { max-width: 62rem; color: var(--bea-ink-muted); }
  .bea-integ-head-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; }

  /* Cartes */
  .bea-admin-panel {
    border: 1px solid var(--bea-line);
    border-radius: 0.9rem;
    box-shadow: 0 1px 2px rgb(15 23 42 / 0.04);
    transition: box-shadow 0.2s ease, border-color 0.2s ease;
    animation: beaIntegRise 0.32s cubic-bezier(0.2, 0.7, 0.2, 1) both;
  }
  .bea-admin-panel:hover { box-shadow: 0 8px 22px rgb(15 23 42 / 0.06); }
  .bea-admin-panel > h2, .bea-admin-users__list-head h2 { position: relative; padding-left: 0.65rem; }
  .bea-admin-panel > h2::before, .bea-admin-users__list-head h2::before {
    content: ''; position: absolute; left: 0; top: 0.18em; bottom: 0.18em; width: 3px;
    border-radius: 3px; background: var(--bea-brand-700);
  }
  .bea-admin-dash > * { animation: beaIntegRise 0.32s cubic-bezier(0.2, 0.7, 0.2, 1) both; }

  /* Indicateurs */
  .bea-admin-kpi { transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease; }
  .bea-admin-kpis > * { animation: beaIntegRise 0.34s ease both; }
  a.bea-admin-kpi:hover { transform: translateY(-2px); box-shadow: 0 10px 24px rgb(26 82 120 / 0.12); }
  .bea-admin-kpi__value { font-variant-numeric: tabular-nums; }

  /* Boutons et focus visible */
  .bea-admin-btn { transition: background-color 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease, transform 0.1s ease; }
  .bea-admin-btn:not(:disabled):hover { box-shadow: 0 2px 8px rgb(15 23 42 / 0.12); }
  .bea-admin-btn:not(:disabled):active { transform: translateY(1px); }
  .bea-admin-btn--ghost:not(:disabled):hover { border-color: #9cc1de; background: #f5f9fc; }
  .bea-admin-btn--danger:not(:disabled):hover { background: #991b1b; border-color: #991b1b; }
  .bea-admin-btn[aria-busy='true'] { cursor: progress; }
  .bea-integ-btn-danger-ghost { background: #fff; color: #b91c1c; border-color: #fecaca; }
  .bea-integ-btn-danger-ghost:not(:disabled):hover { background: #fef2f2; border-color: #f87171; }
  a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible,
  textarea:focus-visible, summary:focus-visible, [tabindex]:focus-visible {
    outline: 2px solid var(--bea-brand-700);
    outline-offset: 2px;
  }

  /* Champs */
  .bea-admin-field input, .bea-admin-field select, .bea-admin-field textarea {
    min-height: 2.35rem;
    border-color: #d5dee8;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
  }
  .bea-admin-field input:hover, .bea-admin-field select:hover, .bea-admin-field textarea:hover { border-color: #b7c7d8; }
  .bea-admin-field input:focus, .bea-admin-field select:focus, .bea-admin-field textarea:focus {
    outline: none;
    border-color: var(--bea-brand-700);
    box-shadow: 0 0 0 3px rgb(40 116 166 / 0.16);
  }
  .bea-admin-field input[type='checkbox'], .bea-admin-field input[type='radio'] { min-height: 0; box-shadow: none; }
  .bea-admin-field input[aria-invalid='true'], .bea-admin-field select[aria-invalid='true'],
  .bea-admin-field textarea[aria-invalid='true'] { border-color: #dc2626; }
  .bea-admin-field input:disabled, .bea-admin-field select:disabled, .bea-admin-field textarea:disabled {
    background: #f1f5f9; color: var(--bea-ink-muted); cursor: not-allowed;
  }
  .bea-admin-field > span:first-child { font-weight: 600; color: var(--bea-ink); }
  .bea-integ-req { color: #b91c1c; text-decoration: none; font-weight: 700; margin-left: 0.15rem; }
  .bea-integ-help { font-size: 0.76rem; line-height: 1.4; color: var(--bea-ink-muted); }
  .bea-integ-error {
    display: flex; gap: 0.3rem; align-items: center;
    font-size: 0.78rem; font-weight: 600; color: #b91c1c;
    animation: beaIntegFade 0.18s ease both;
  }

  /* Formulaires en sections */
  .bea-integ-form { display: grid; gap: 1rem; width: 100%; }
  .bea-integ-fieldset { margin: 0; padding: 1.15rem 1.35rem 1.35rem; min-width: 0; }
  .bea-integ-fieldset__head {
    display: flex; gap: 0.75rem; align-items: center;
    margin: 0 0 1.1rem; padding: 0 0 0.85rem; border-bottom: 1px solid var(--bea-line);
  }
  .bea-integ-fieldset__num {
    flex: 0 0 auto; display: grid; place-items: center; width: 1.8rem; height: 1.8rem;
    border-radius: 999px; background: var(--bea-chip); color: var(--bea-brand-900); font-weight: 700; font-size: 0.85rem;
  }
  .bea-integ-fieldset__head h2 { margin: 0; font-size: 1rem; }
  .bea-integ-fieldset__head p { margin: 0.2rem 0 0; font-size: 0.82rem; color: var(--bea-ink-muted); }
  .bea-integ-grid2, .bea-integ-grid3 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem 1.25rem; align-items: start; }
  .bea-integ-grid3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .bea-integ-grid2 > .bea-integ-full, .bea-integ-grid3 > .bea-integ-full { grid-column: 1 / -1; }
  .bea-admin-field ::ng-deep .bea-org-select {
    min-height: 2.35rem; padding: 0.5rem 0.65rem; border: 1px solid #d5dee8; border-radius: 0.4rem; background: #fff;
  }
  .bea-admin-field ::ng-deep .bea-org-select:focus { border-color: var(--bea-brand-700); box-shadow: 0 0 0 3px rgb(40 116 166 / 0.16); }
  .bea-integ-form-actions {
    position: sticky; bottom: 0; z-index: 2;
    display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; justify-content: flex-end;
    padding: 0.75rem 1rem; border: 1px solid var(--bea-line); border-radius: 0.9rem;
    background: rgb(255 255 255 / 0.94); box-shadow: 0 -6px 18px rgb(15 23 42 / 0.06);
    -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px);
  }
  .bea-integ-form-actions__hint { margin-right: auto; font-size: 0.8rem; color: var(--bea-ink-muted); }
  .bea-integ-form-actions__hint[data-dirty='true'] { color: #b45309; font-weight: 600; }
  .bea-integ-spinner {
    display: inline-block; width: 0.9rem; height: 0.9rem; border-radius: 999px;
    border: 2px solid currentColor; border-right-color: transparent;
    animation: beaIntegSpin 0.7s linear infinite;
  }

  /* Tableaux */
  .bea-admin-table-wrap { border-radius: 0.7rem; }
  .bea-admin-table thead th { position: sticky; top: 0; z-index: 1; background: #f8fafc; white-space: nowrap; }
  .bea-admin-table tbody tr { transition: background-color 0.15s ease; animation: beaIntegFade 0.28s ease both; }
  .bea-admin-table tbody tr:hover { background: #f3f8fc; }
  .bea-admin-table td { overflow-wrap: anywhere; }
  .bea-integ-row-actions { display: flex; gap: 0.25rem; justify-content: flex-end; flex-wrap: nowrap; }
  .bea-integ-icon-btn {
    display: inline-grid; place-items: center; width: 2rem; height: 2rem; padding: 0;
    border: 1px solid transparent; border-radius: 0.5rem; background: transparent; color: var(--bea-brand-900);
    cursor: pointer; text-decoration: none; transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
  }
  .bea-integ-icon-btn:hover:not(:disabled) { background: #eef4f9; border-color: var(--bea-line); }
  .bea-integ-icon-btn[data-tone='danger'] { color: #b91c1c; }
  .bea-integ-icon-btn[data-tone='danger']:hover:not(:disabled) { background: #fef2f2; border-color: #fecaca; }
  .bea-integ-icon-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .bea-integ-list-head { display: flex; flex-wrap: wrap; gap: 0.5rem 1rem; align-items: center; justify-content: space-between; }
  .bea-integ-list-head h2 { margin: 0; }
  .bea-integ-count { font-size: 0.82rem; color: var(--bea-ink-muted); }
  .bea-integ-truncate { display: block; max-width: 28rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  /* Badges */
  .bea-badge { transition: background-color 0.25s ease, color 0.25s ease; animation: beaIntegPop 0.22s ease both; }
  .bea-integ-pill {
    display: inline-flex; align-items: center; gap: 0.25rem; padding: 0.1rem 0.5rem;
    border-radius: 999px; font-size: 0.72rem; font-weight: 700; background: #eef2f7; color: #334155;
  }
  .bea-integ-pill[data-tone='ok'] { background: var(--bea-ok-bg); color: var(--bea-ok-ink); }
  .bea-integ-pill[data-tone='warn'] { background: var(--bea-warn-bg); color: var(--bea-warn-ink); }
  .bea-integ-pill[data-tone='danger'] { background: #fee2e2; color: #991b1b; }
  .bea-integ-pill[data-tone='info'] { background: var(--bea-chip); color: var(--bea-chip-ink); }

  /* États : chargement, vide */
  .bea-integ-skeleton { display: grid; gap: 0.55rem; padding: 0.5rem 0; }
  .bea-integ-skeleton i {
    display: block; height: 0.85rem; border-radius: 0.4rem;
    background: linear-gradient(90deg, #eef2f6 0%, #f8fafc 50%, #eef2f6 100%);
    background-size: 200% 100%;
    animation: beaIntegShimmer 1.2s ease-in-out infinite;
  }
  .bea-integ-skeleton i:nth-child(2) { width: 92%; }
  .bea-integ-skeleton i:nth-child(3) { width: 78%; }
  .bea-integ-skeleton i:nth-child(4) { width: 85%; }
  .bea-integ-empty {
    display: grid; justify-items: center; gap: 0.4rem; padding: 1.75rem 1rem; text-align: center;
    color: var(--bea-ink-muted); animation: beaIntegFade 0.3s ease both;
  }
  .bea-integ-empty strong { color: var(--bea-ink); font-size: 0.95rem; }
  .bea-integ-empty p { margin: 0; max-width: 34rem; font-size: 0.85rem; }

  /* Assistant de test (étapes) */
  .bea-integ-stepper { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0 0 1rem; padding: 0; list-style: none; counter-reset: etape; }
  .bea-integ-stepper li {
    counter-increment: etape;
    display: flex; gap: 0.45rem; align-items: center; flex: 1 1 9rem;
    padding: 0.55rem 0.75rem; border: 1px solid var(--bea-line); border-radius: 0.7rem;
    background: #fff; font-size: 0.82rem; color: var(--bea-ink-muted);
    transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;
  }
  .bea-integ-stepper li::before {
    content: counter(etape);
    display: grid; place-items: center; flex: 0 0 auto; width: 1.45rem; height: 1.45rem;
    border-radius: 999px; background: #eef2f7; color: #475569; font-weight: 700; font-size: 0.75rem;
    transition: background-color 0.2s ease, color 0.2s ease;
  }
  .bea-integ-stepper li[data-etat='courant'] { border-color: var(--bea-brand-700); color: var(--bea-ink); font-weight: 600; background: #f5f9fc; }
  .bea-integ-stepper li[data-etat='courant']::before { background: var(--bea-brand-700); color: #fff; }
  .bea-integ-stepper li[data-etat='fait'] { color: var(--bea-ok-ink); }
  .bea-integ-stepper li[data-etat='fait']::before { content: '✓'; background: var(--bea-ok-bg); color: var(--bea-ok-ink); }
  .bea-integ-step { animation: beaIntegSlide 0.25s ease both; }
  .bea-integ-recap { display: grid; grid-template-columns: max-content 1fr; gap: 0.35rem 1rem; margin: 0; font-size: 0.86rem; }
  .bea-integ-recap dt { color: var(--bea-ink-muted); }
  .bea-integ-recap dd { margin: 0; overflow-wrap: anywhere; }
  .bea-integ-etat {
    display: flex; gap: 0.75rem; align-items: flex-start; padding: 0.9rem 1rem;
    border: 1px solid var(--bea-line); border-left-width: 4px; border-radius: 0.75rem; background: #f8fafc;
    animation: beaIntegPop 0.25s ease both;
  }
  .bea-integ-etat h3 { margin: 0 0 0.2rem; font-size: 0.98rem; }
  .bea-integ-etat p { margin: 0; font-size: 0.86rem; }
  .bea-integ-etat[data-etat='succes'] { border-left-color: #16a34a; background: #f4fbf6; }
  .bea-integ-etat[data-etat='en_cours'] { border-left-color: var(--bea-brand-700); }
  .bea-integ-etat[data-etat='http'] { border-left-color: #dc2626; background: #fef6f6; }
  .bea-integ-etat[data-etat='reseau'] { border-left-color: #c2410c; background: #fffbf5; }
  .bea-integ-etat[data-etat='refus'], .bea-integ-etat[data-etat='secret'],
  .bea-integ-etat[data-etat='quota'], .bea-integ-etat[data-etat='delai'] { border-left-color: #b45309; background: #fffbeb; }

  /* Graphiques CSS/SVG (sans bibliothèque) */
  .bea-integ-charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 22rem), 1fr)); gap: 1rem; margin-bottom: 1rem; }
  .bea-integ-chart { margin: 0; }
  .bea-integ-chart figcaption { font-size: 0.78rem; color: var(--bea-ink-muted); margin-top: 0.4rem; }
  .bea-integ-cols {
    display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); align-items: end;
    gap: 0.3rem; height: 11rem; padding: 0.4rem 0 0; border-bottom: 1px solid var(--bea-line);
  }
  .bea-integ-col { display: grid; grid-template-rows: auto 1fr; justify-items: center; height: 100%; min-width: 0; }
  .bea-integ-col b { font-size: 0.68rem; font-variant-numeric: tabular-nums; color: var(--bea-ink); }
  .bea-integ-col span {
    align-self: end; display: flex; flex-direction: column-reverse; width: min(2.2rem, 100%); min-height: 2px;
    border-radius: 0.35rem 0.35rem 0 0; overflow: hidden; transform-origin: bottom;
    animation: beaIntegGrowY 0.5s cubic-bezier(0.2, 0.7, 0.2, 1) both;
  }
  .bea-integ-col span i { display: block; width: 100%; }
  .bea-integ-col span i[data-k='ok'] { background: var(--bea-brand-700); }
  .bea-integ-col span i[data-k='ko'] { background: #f59e0b; }
  .bea-integ-axe { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); gap: 0.3rem; margin-top: 0.3rem; }
  .bea-integ-axe span { font-size: 0.66rem; text-align: center; color: var(--bea-ink-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .bea-integ-svg { display: block; width: 100%; height: 11rem; overflow: visible; }
  .bea-integ-svg .grille { stroke: var(--bea-line); stroke-width: 1; }
  .bea-integ-svg .courbe { fill: none; stroke: var(--bea-brand-700); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
  .bea-integ-svg .point { fill: #fff; stroke: var(--bea-brand-700); stroke-width: 2; }
  .bea-integ-svg text { font-size: 10px; fill: var(--bea-ink-muted); }
  .bea-integ-legend { display: flex; flex-wrap: wrap; gap: 0.75rem; margin: 0.5rem 0 0; padding: 0; list-style: none; font-size: 0.75rem; color: var(--bea-ink-muted); }
  .bea-integ-legend i { display: inline-block; width: 0.7rem; height: 0.7rem; margin-right: 0.3rem; border-radius: 0.2rem; vertical-align: -0.05rem; }
  .bea-integ-hbars { display: grid; gap: 0.55rem; margin: 0; padding: 0; list-style: none; }
  .bea-integ-hbars li { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.2rem 0.6rem; font-size: 0.82rem; }
  .bea-integ-hbars li > em { grid-column: 1 / -1; display: block; height: 0.5rem; border-radius: 999px; background: #eef2f7; overflow: hidden; font-style: normal; }
  .bea-integ-hbars li > em > i {
    display: block; height: 100%; border-radius: inherit; background: var(--bea-brand-700);
    transform-origin: left; animation: beaIntegGrowX 0.6s cubic-bezier(0.2, 0.7, 0.2, 1) both;
  }
  .bea-integ-hbars li > em > i[data-k='ko'] { background: #f59e0b; }
  .bea-integ-hbars b { font-variant-numeric: tabular-nums; }

  /* Détail en sections */
  .bea-integ-detail { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr)); gap: 1rem; }
  .bea-integ-detail section h3 { margin: 0 0 0.5rem; font-size: 0.9rem; color: var(--bea-brand-900); }
  .bea-integ-timeline { margin: 0; padding: 0; list-style: none; display: grid; gap: 0.5rem; }
  .bea-integ-timeline li { position: relative; padding-left: 1.1rem; font-size: 0.84rem; }
  .bea-integ-timeline li::before {
    content: ''; position: absolute; left: 0.2rem; top: 0.4rem; width: 0.5rem; height: 0.5rem;
    border-radius: 999px; background: var(--bea-brand-700);
  }

  /* Liste de cases à cocher */
  .bea-integ-checklist {
    display: grid; gap: 0.3rem; margin: 0; padding: 0.5rem 0.75rem; max-height: 18rem; overflow: auto;
    border: 1px solid var(--bea-line); border-radius: 0.7rem;
  }
  .bea-integ-checklist legend { padding: 0 0.3rem; font-size: 0.78rem; }
  .bea-integ-checklist label {
    display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; padding: 0.3rem 0.4rem; border-radius: 0.45rem; cursor: pointer;
  }
  .bea-integ-checklist label:hover { background: #f3f8fc; }

  /* Compteurs cliquables (filtre rapide) */
  .bea-integ-kpi-filtres { display: grid; grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr)); gap: 0.6rem; margin: 0 0 1rem; }
  .bea-integ-kpi-filtre {
    display: grid; gap: 0.15rem; padding: 0.7rem 0.85rem; text-align: left; font: inherit; cursor: pointer;
    border: 1px solid var(--bea-line); border-left-width: 4px; border-radius: 0.75rem; background: var(--bea-surface-card, #fff);
    transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
    animation: beaIntegRise 0.3s ease both;
  }
  .bea-integ-kpi-filtre:hover { box-shadow: 0 4px 14px rgb(15 23 42 / 0.07); transform: translateY(-1px); }
  .bea-integ-kpi-filtre[aria-pressed='true'] { border-color: var(--bea-brand-700); box-shadow: 0 0 0 2px rgb(40 116 166 / 0.18); }
  .bea-integ-kpi-filtre span { font-size: 0.76rem; color: var(--bea-ink-muted); }
  .bea-integ-kpi-filtre strong { font-size: 1.35rem; font-variant-numeric: tabular-nums; color: var(--bea-ink); }
  .bea-integ-kpi-filtre[data-tone='danger'] { border-left-color: #dc2626; }
  .bea-integ-kpi-filtre[data-tone='warn'] { border-left-color: #d97706; }
  .bea-integ-kpi-filtre[data-tone='ok'] { border-left-color: #16a34a; }
  .bea-integ-kpi-filtre[data-tone='muted'] { border-left-color: #94a3b8; }

  @keyframes beaIntegRise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
  @keyframes beaIntegFade { from { opacity: 0; } to { opacity: 1; } }
  @keyframes beaIntegPop { from { opacity: 0; transform: scale(0.96); } to { opacity: 1; transform: none; } }
  @keyframes beaIntegSlide { from { opacity: 0; transform: translateX(10px); } to { opacity: 1; transform: none; } }
  @keyframes beaIntegGrowX { from { transform: scaleX(0); } to { transform: scaleX(1); } }
  @keyframes beaIntegGrowY { from { transform: scaleY(0); } to { transform: scaleY(1); } }
  @keyframes beaIntegShimmer { from { background-position: 100% 0; } to { background-position: -100% 0; } }
  @keyframes beaIntegSpin { to { transform: rotate(360deg); } }

  @media (max-width: 900px) {
    .bea-integ-grid2, .bea-integ-grid3 { grid-template-columns: minmax(0, 1fr); }
  }
  @media (max-width: 720px) {
    .bea-integ-fieldset { padding: 1rem; }
    .bea-integ-cards thead { display: none; }
    .bea-integ-cards, .bea-integ-cards tbody, .bea-integ-cards tr, .bea-integ-cards td { display: block; width: 100%; }
    .bea-integ-cards tr { margin: 0 0 0.75rem; padding: 0.6rem 0.75rem; border: 1px solid var(--bea-line); border-radius: 0.75rem; }
    .bea-integ-cards td { display: grid; grid-template-columns: 7.5rem minmax(0, 1fr); gap: 0.5rem; padding: 0.3rem 0; border: 0; }
    .bea-integ-cards td::before { content: attr(data-label); font-size: 0.74rem; font-weight: 600; color: var(--bea-ink-muted); }
    .bea-integ-cards td[data-label=''] { grid-template-columns: minmax(0, 1fr); }
    .bea-integ-cards td[data-label='']::before { display: none; }
    .bea-integ-row-actions { justify-content: flex-start; }
    .bea-integ-form-actions { position: static; justify-content: stretch; }
    .bea-integ-form-actions .bea-admin-btn { flex: 1 1 auto; }
    .bea-integ-truncate { max-width: 100%; white-space: normal; }
  }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      animation-delay: 0ms !important;
      transition-duration: 0.01ms !important;
    }
  }

  /* Thème sombre */
  :host-context(html[data-theme='dark']) .bea-admin-table thead th { background: #1f2329; }
  :host-context(html[data-theme='dark']) .bea-admin-table tbody tr:hover { background: #242a31; }
  :host-context(html[data-theme='dark']) .bea-integ-form-actions { background: rgb(26 26 26 / 0.94); border-color: var(--bea-line); }
  :host-context(html[data-theme='dark']) .bea-integ-stepper li { background: var(--bea-surface-card); }
  :host-context(html[data-theme='dark']) .bea-integ-stepper li[data-etat='courant'] { background: #1f2a35; }
  :host-context(html[data-theme='dark']) .bea-integ-etat,
  :host-context(html[data-theme='dark']) .bea-integ-notice--info { background: #1f2329; }
  :host-context(html[data-theme='dark']) .bea-admin-field input:disabled,
  :host-context(html[data-theme='dark']) .bea-admin-field select:disabled { background: #2a2a2a; }
  :host-context(html[data-theme='dark']) .bea-admin-field ::ng-deep .bea-org-select { background: #1f1f1f; border-color: var(--bea-line); }
  :host-context(html[data-theme='dark']) .bea-integ-skeleton i,
  :host-context(html[data-theme='dark']) .bea-integ-hbars li > em { background: #2a2a2a; }
  :host-context(html[data-theme='dark']) .bea-integ-icon-btn:hover:not(:disabled) { background: #2a3038; }
  :host-context(html[data-theme='dark']) .bea-integ-checklist label:hover { background: #242a31; }
`;

/** Styles du seul bouton de tri (évite d'embarquer toute la feuille du Studio dans ce petit composant). */
export const TRI_STYLES = `
  .bea-integ-tri {
    display: inline-flex; gap: 0.2rem; align-items: center; padding: 0; border: 0; background: none;
    font: inherit; font-weight: inherit; color: inherit; cursor: pointer;
  }
  .bea-integ-tri:hover { color: var(--bea-brand-800); }
  .bea-integ-tri:focus-visible { outline: 2px solid var(--bea-brand-700); outline-offset: 2px; }
  .bea-integ-tri__fleche { font-size: 0.7rem; opacity: 0.35; transition: transform 0.15s ease, opacity 0.15s ease; }
  .bea-integ-tri[data-actif='true'] .bea-integ-tri__fleche { opacity: 1; }
  .bea-integ-tri[data-ordre='asc'] .bea-integ-tri__fleche { transform: rotate(180deg); }
  @media (prefers-reduced-motion: reduce) { .bea-integ-tri__fleche { transition: none; } }
`;

export const INTEGRATIONS_STYLES = `
  .bea-integ-notice {
    display: flex;
    gap: 0.65rem;
    align-items: flex-start;
    margin: 0 0 1rem;
    padding: 0.75rem 0.95rem;
    border: 1px solid #fde68a;
    border-radius: 0.75rem;
    background: #fffbeb;
    color: var(--bea-ink);
    font-size: 0.88rem;
    line-height: 1.45;
  }
  .bea-integ-notice--info {
    border-color: var(--bea-line);
    background: #f8fafc;
  }
  .bea-integ-notice--danger {
    border-color: #fecaca;
    background: #fef2f2;
  }
  .bea-integ-notice p {
    margin: 0;
  }
  .bea-integ-notice ul {
    margin: 0.35rem 0 0;
    padding-left: 1.1rem;
  }
  .bea-integ-method {
    display: inline-block;
    min-width: 3.6rem;
    padding: 0.12rem 0.45rem;
    border-radius: 0.4rem;
    font: 700 0.72rem/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    text-align: center;
    background: #e0f2fe;
    color: #075985;
  }
  .bea-integ-method[data-m='POST'] { background: #dcfce7; color: #166534; }
  .bea-integ-method[data-m='PUT'],
  .bea-integ-method[data-m='PATCH'] { background: #fef3c7; color: #92400e; }
  .bea-integ-method[data-m='DELETE'] { background: #fee2e2; color: #991b1b; }
  .bea-integ-path {
    font: 0.8rem/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    word-break: break-all;
  }
  .bea-integ-muted {
    color: var(--bea-ink-muted);
    font-size: 0.8rem;
  }
  .bea-integ-pre, .bea-integ-result {
    margin: 0;
    max-height: 28rem;
    overflow: auto;
    padding: 0.85rem 1rem;
    border-radius: 0.6rem;
    background: #0f172a;
    color: #e2e8f0;
    font: 0.8rem/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    white-space: pre;
  }
  .bea-integ-tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin: 0 0 0.75rem;
  }
  .bea-integ-tabs button[aria-selected='true'] {
    background: var(--bea-brand-700);
    color: #fff;
  }
  .bea-integ-section {
    margin-bottom: 1rem;
  }
  .bea-integ-section h2 {
    margin: 0 0 0.6rem;
    font-size: 1rem;
  }
  .bea-integ-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
    gap: 0.85rem;
    margin-bottom: 1rem;
  }
  .bea-integ-stats table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.86rem;
  }
  .bea-integ-stats td {
    padding: 0.3rem 0;
    border-bottom: 1px solid var(--bea-line);
  }
  .bea-integ-stats td:last-child {
    text-align: right;
    font-weight: 700;
  }
  .bea-integ-params {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
    gap: 0.75rem 1rem;
    margin-bottom: 0.9rem;
  }
  .bea-integ-kpi-note {
    margin: 0.15rem 0 0;
    color: var(--bea-ink-muted);
    font-size: 0.75rem;
  }
  .bea-integ-filtres {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    align-items: flex-end;
  }
  .bea-integ-filtres .bea-admin-field {
    min-width: 11rem;
    flex: 1 1 11rem;
  }
  .bea-integ-actions-ligne {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
  }
  .bea-integ-result {
    max-height: 16rem;
    padding: 0.75rem 0.9rem;
    font-size: 0.78rem;
    white-space: pre-wrap;
    word-break: break-word;
  }
${STUDIO_DESIGN}`;
