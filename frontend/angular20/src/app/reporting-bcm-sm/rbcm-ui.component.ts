import { ChangeDetectionStrategy, Component, ViewEncapsulation } from '@angular/core';

/** Styles partagés Reporting BCM SM — alignés Formation / bea-mg. */
@Component({
  selector: 'bea-rbcm-styles',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
  template: '',
  styles: `
    :host { display: none; }
    bea-rbcm-campagne-documents { display: contents; }
    :host + .bea-rbcm,
    .bea-rbcm {
      --rbcm-gap: 1rem;
      box-sizing: border-box;
      width: 100%;
      max-width: 100%;
      min-width: 0;
    }
    .bea-rbcm *,
    .bea-rbcm *::before,
    .bea-rbcm *::after { box-sizing: border-box; }
    .bea-rbcm .bea-mg__head {
      display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between;
      gap: 0.85rem 1rem; margin-bottom: 1rem;
    }
    .bea-rbcm .bea-mg__head > div { min-width: 0; flex: 1 1 16rem; }
    .bea-rbcm .bea-mg__head h1 { overflow-wrap: anywhere; }
    .bea-rbcm .bea-rbcm-statusline {
      display: flex; flex-wrap: wrap; align-items: center; gap: 0.45rem 0.75rem; margin: 0.4rem 0 0;
    }
    .bea-rbcm .bea-mg__actions {
      display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;
    }
    .bea-rbcm .bea-rbcm-grid {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: var(--rbcm-gap);
      margin-bottom: var(--rbcm-gap);
    }
    .bea-rbcm .bea-rbcm-span4 { grid-column: span 4; }
    .bea-rbcm .bea-rbcm-span5 { grid-column: span 5; }
    .bea-rbcm .bea-rbcm-span6 { grid-column: span 6; }
    .bea-rbcm .bea-rbcm-span7 { grid-column: span 7; }
    .bea-rbcm .bea-rbcm-span8 { grid-column: span 8; }
    .bea-rbcm .bea-rbcm-span12 { grid-column: span 12; }
    @media (max-width: 1100px) {
      .bea-rbcm .bea-rbcm-span4,
      .bea-rbcm .bea-rbcm-span5,
      .bea-rbcm .bea-rbcm-span6,
      .bea-rbcm .bea-rbcm-span7,
      .bea-rbcm .bea-rbcm-span8 { grid-column: span 12; }
    }
    .bea-rbcm .bea-mg__panel {
      animation: bea-rbcm-in 0.35s ease both;
      min-width: 0;
      overflow: hidden;
    }
    bea-rbcm-pager { display: block; width: 100%; min-width: 0; }
    .bea-rbcm .bea-rbcm-grid > .bea-mg__panel { margin-bottom: 0; }
    .bea-rbcm .bea-mg__panel-top {
      display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem 1.25rem;
      margin: 0; padding: 1.2rem 1.5rem 1rem;
    }
    .bea-rbcm .bea-mg__panel-top > div { min-width: 0; flex: 1 1 auto; }
    .bea-rbcm .bea-mg__panel-top h2 {
      margin: 0; font-size: 1rem; line-height: 1.35; overflow-wrap: anywhere;
    }
    .bea-rbcm .bea-mg__panel-top > a {
      color: #1a5278; font-weight: 600; font-size: 0.86rem; text-decoration: none;
      white-space: nowrap; flex: 0 0 auto; padding: 0.15rem 0;
    }
    .bea-rbcm .bea-rbcm-pct {
      flex: 0 0 auto; margin: 0; padding: 0.15rem 0.1rem 0.15rem 0.35rem;
      font-size: 1.15rem; line-height: 1.2; font-variant-numeric: tabular-nums; color: #0f766e;
    }
    .bea-rbcm .bea-mg__panel > :not(.bea-mg__panel-top):not(.bea-mg__table-wrap):not(.bea-mg__table) {
      padding-left: 1.5rem; padding-right: 1.5rem;
    }
    .bea-rbcm .bea-mg__panel > .bea-mg__panel-top + :not(.bea-mg__table-wrap):not(.bea-mg__table) {
      padding-top: 0.35rem;
    }
    .bea-rbcm .bea-mg__panel > :last-child:not(.bea-mg__panel-top):not(.bea-mg__table-wrap):not(.bea-mg__table) {
      padding-bottom: 1.25rem;
    }
    .bea-rbcm .bea-rbcm-sub {
      margin: 0.2rem 0 0; color: #64748b; font-size: 0.88rem; overflow-wrap: anywhere; line-height: 1.35;
    }
    .bea-rbcm .bea-mg__search,
    .bea-rbcm .bea-rbcm-filters,
    .bea-rbcm .bea-rbcm-picker,
    .bea-rbcm .bea-rbcm-period-bar {
      background: none; border: 0; box-shadow: none; border-radius: 0;
    }
    .bea-rbcm .bea-rbcm-filters {
      display: flex; flex-wrap: wrap; gap: 0.65rem 0.75rem; margin: 0 0 1rem;
      align-items: center; padding: 0;
    }
    .bea-rbcm .bea-mg__panel > .bea-rbcm-filters { margin-bottom: 0.85rem; }
    .bea-rbcm .bea-rbcm-filters .bea-mg__field { min-width: min(100%, 11rem); }
    .bea-rbcm .bea-rbcm-pager {
      display: flex; flex-wrap: wrap; gap: 0.65rem 1rem; align-items: center;
      justify-content: space-between; margin-top: 0.85rem;
    }
    .bea-rbcm .bea-rbcm-pager__meta { margin: 0; color: #64748b; font-size: 0.86rem; }
    .bea-rbcm .bea-rbcm-pager__nav { display: flex; flex-wrap: wrap; gap: 0.35rem; align-items: center; }
    .bea-rbcm .bea-rbcm-pager__page {
      min-width: 4.5rem; text-align: center; color: #334155; font-size: 0.86rem;
      font-variant-numeric: tabular-nums;
    }
    .bea-rbcm .bea-fx-sort { min-height: 1.75rem; letter-spacing: inherit; text-transform: inherit; }
    .bea-rbcm .bea-fx-sort:focus-visible { outline: 2px solid #1a5278; outline-offset: 2px; border-radius: 4px; }
    .bea-rbcm .bea-rbcm-empty {
      display: flex; gap: 0.85rem; align-items: flex-start; padding: 1.15rem 0.15rem;
      color: #64748b;
    }
    .bea-rbcm .bea-rbcm-empty--compact { padding: 0.65rem 0; }
    .bea-rbcm .bea-rbcm-empty mat-icon { color: #94a3b8; flex: 0 0 auto; }
    .bea-rbcm .bea-rbcm-empty p { margin: 0.15rem 0 0; }
    .bea-rbcm .bea-rbcm-steps { display: grid; gap: 0.55rem; min-width: 0; }
    .bea-rbcm .bea-rbcm-step {
      display: grid; grid-template-columns: auto minmax(0, 1fr) minmax(0, max-content);
      gap: 0.65rem 0.85rem; align-items: start;
      padding: 0.7rem 0.9rem; border-radius: 10px; background: #f8fafc; border: 1px solid #e2e8f0;
    }
    .bea-rbcm .bea-rbcm-step mat-icon { margin-top: 0.05rem; }
    .bea-rbcm .bea-rbcm-step span { min-width: 0; overflow-wrap: anywhere; font-weight: 600; line-height: 1.3; }
    .bea-rbcm .bea-rbcm-step small {
      color: #64748b; font-size: 0.75rem; line-height: 1.3; text-align: right;
      max-width: 11.5rem; overflow-wrap: anywhere;
    }
    .bea-rbcm .bea-rbcm-step[data-state='done'] { border-color: #bbf7d0; background: #f0fdf4; }
    .bea-rbcm .bea-rbcm-step[data-state='current'] { border-color: #1a5278; background: #eff6ff; box-shadow: inset 3px 0 0 #1a5278; }
    .bea-rbcm .bea-rbcm-step[data-state='wait'] { border-color: #fde68a; background: #fffbeb; }
    .bea-rbcm .bea-rbcm-step[data-state='blocked'] { border-color: #fecaca; background: #fef2f2; }
    .bea-rbcm .bea-rbcm-progress {
      height: 8px; border-radius: 999px; background: #e2e8f0; overflow: hidden;
    }
    .bea-rbcm .bea-rbcm-progress__bar {
      height: 100%; background: #0f766e; transition: width 0.45s ease;
    }
    .bea-rbcm .bea-rbcm-quick {
      display: flex; flex-wrap: wrap; gap: 0.55rem; align-items: center;
    }
    .bea-rbcm .bea-rbcm-list {
      list-style: none; margin: 0; padding: 0; display: grid; gap: 0.35rem;
    }
    .bea-rbcm .bea-rbcm-list li {
      display: flex; gap: 0.65rem; align-items: center; padding: 0.7rem 0.45rem;
      border-bottom: 1px solid #f1f5f9; cursor: pointer; border-radius: 8px;
      min-width: 0; transition: background 0.15s ease;
    }
    .bea-rbcm .bea-rbcm-list li:hover { background: #f8fafc; }
    .bea-rbcm .bea-rbcm-list strong { display: block; }
    .bea-rbcm .bea-rbcm-list small { color: #64748b; }
    .bea-rbcm .bea-rbcm-mono { font-family: ui-monospace, monospace; font-size: 0.85rem; word-break: break-all; }
    .bea-rbcm .bea-rbcm-sha-full {
      background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.55rem 0.7rem;
    }
    .bea-rbcm .bea-rbcm-pre {
      white-space: pre-wrap; background: #f8fafc; border-radius: 8px; padding: 0.75rem;
      max-height: 280px; overflow: auto; font-size: 0.8rem; border: 1px solid #e2e8f0;
    }
    .bea-rbcm .bea-rbcm-hint { color: #64748b; font-size: 0.86rem; margin: 0.35rem 0 0; }
    .bea-rbcm .bea-rbcm-row { cursor: pointer; transition: background 0.15s ease; }
    .bea-rbcm .bea-rbcm-row:hover { background: color-mix(in srgb, #1a5278 6%, transparent); }
    .bea-rbcm .bea-rbcm-ellipsis {
      display: inline-block; max-width: min(28rem, 42vw); overflow: hidden;
      text-overflow: ellipsis; white-space: nowrap; vertical-align: bottom;
    }
    .bea-rbcm .bea-mg__table-wrap {
      width: 100%; max-width: 100%; max-height: none;
      overflow-x: auto; -webkit-overflow-scrolling: touch;
    }
    .bea-rbcm .bea-mg__table-wrap.bea-rbcm-table-scroll {
      max-height: min(52vh, 32rem);
      overflow: auto;
    }
    .bea-rbcm .bea-mg__table-wrap.bea-rbcm-table-scroll thead th {
      position: sticky; top: 0; z-index: 2;
      background: #f8fafc; box-shadow: 0 1px 0 #e2e8f0;
    }
    html[data-theme='dark'] .bea-rbcm .bea-mg__table-wrap.bea-rbcm-table-scroll thead th {
      background: #152332; box-shadow: 0 1px 0 #353b43;
    }
    .bea-rbcm .bea-mg__table-wrap.bea-rbcm-table-scroll thead .bea-rbcm-col-actions {
      z-index: 4;
    }
    .bea-rbcm .bea-mg__table { width: 100%; min-width: 0; }
    .bea-rbcm .bea-mg__table td { overflow-wrap: break-word; }
    .bea-rbcm .bea-mg__table th { white-space: normal; line-height: 1.25; }
    .bea-rbcm .bea-mg__table th:first-child,
    .bea-rbcm .bea-mg__table td:first-child { padding-left: 1.25rem; }
    .bea-rbcm .bea-mg__table th:last-child,
    .bea-rbcm .bea-mg__table td:last-child { padding-right: 1.25rem; }
    .bea-rbcm .bea-rbcm-col-actions {
      position: sticky; right: 0; z-index: 2; width: 1%; white-space: nowrap; text-align: right;
      background: var(--app-surface, #fff); overflow: visible;
    }
    .bea-rbcm .bea-row-menu {
      min-width: 15.5rem; max-width: min(22rem, calc(100vw - 1.5rem)); overflow: visible;
    }
    .bea-rbcm .bea-row-menu button { overflow: visible; }
    .bea-rbcm .bea-mg__table thead .bea-rbcm-col-actions { z-index: 3; background: #f8fafc; }
    html[data-theme='dark'] .bea-rbcm .bea-mg__table thead .bea-rbcm-col-actions { background: #152332; }
    .bea-rbcm .bea-fx-kpis { grid-template-columns: repeat(auto-fit, minmax(min(100%, 11.5rem), 1fr)); }
    .bea-rbcm .bea-fx-kpi { min-width: 0; padding: 1rem 1.15rem 0.95rem 1.2rem; overflow: hidden; }
    .bea-rbcm .bea-fx-kpi p { overflow-wrap: anywhere; }
    .bea-rbcm .bea-fx-kpi strong {
      max-width: 100%; overflow-wrap: anywhere; line-height: 1.2;
      font-size: clamp(1.05rem, 1.5vw, 1.35rem); padding-right: 1.6rem;
    }
    .bea-rbcm bea-rbcm-donut,
    .bea-rbcm bea-rbcm-bars { display: block; min-width: 0; }
    .bea-rbcm .bea-fx-donut,
    .bea-rbcm .bea-rbcm-donut { min-width: 0; align-items: flex-start; }
    .bea-rbcm .bea-fx-donut__legend { flex: 1 1 9rem; min-width: 0; }
    .bea-rbcm .bea-fx-donut__legend li { min-width: 0; overflow-wrap: anywhere; }
    .bea-rbcm .bea-fx-chart { padding: 0.15rem 0.15rem 0.35rem; }
    .bea-rbcm bea-rbcm-campaign-picker { display: block; margin: 0 0 1.15rem; }
    .bea-rbcm .bea-rbcm-picker {
      display: flex; flex-wrap: wrap; gap: 0.65rem 0.85rem; align-items: center;
      padding: 0; margin: 0; min-width: 0;
    }
    .bea-rbcm .bea-rbcm-picker .bea-mg__field { min-width: min(100%, 16rem); flex: 1 1 16rem; }
    .bea-rbcm .bea-rbcm-period-bar {
      display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.75rem 1.25rem;
      margin-bottom: 1.15rem; padding: 0;
    }
    .bea-rbcm .bea-rbcm-period-bar__label {
      display: block; font-size: 0.75rem; color: #64748b; margin-bottom: 0.2rem;
    }
    .bea-rbcm .bea-rbcm-import-kpis { margin-bottom: 1rem; }
    .bea-rbcm .bea-rbcm-form-grid {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); gap: 0.75rem;
    }
    .bea-rbcm .bea-rbcm-form-wide { grid-column: 1 / -1; }
    .bea-rbcm .bea-rbcm-form-textarea {
      align-items: flex-start; min-height: 5rem;
    }
    .bea-rbcm .bea-rbcm-form-textarea textarea {
      flex: 1; border: 0; background: transparent; font: inherit; resize: vertical;
      min-height: 4rem; outline: none; width: 100%;
    }
    .bea-rbcm .bea-rbcm-upload {
      display: grid; gap: 0.65rem; max-width: 28rem;
    }
    .bea-rbcm .bea-rbcm-file {
      position: relative; display: flex; align-items: center; gap: 0.5rem; padding: 0.55rem 0.75rem;
      border: 1px dashed #94a3b8; border-radius: 0.6rem; background: #f8fafc;
      cursor: pointer; color: #334155; min-height: 2.5rem;
    }
    .bea-rbcm .bea-rbcm-file:hover { border-color: #1a5278; background: #fff; }
    .bea-rbcm .bea-rbcm-file input[type='file'] {
      position: absolute; inset: 0; width: 100%; height: 100%;
      opacity: 0; cursor: pointer; font-size: 0;
    }
    .bea-rbcm .bea-rbcm-file span {
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0;
    }
    .bea-rbcm .bea-rbcm-lifecycle {
      margin: 1rem 0 0; padding-left: 1.1rem; color: #64748b; font-size: 0.82rem;
      display: grid; gap: 0.25rem;
    }
    .bea-rbcm .bea-rbcm-sources {
      display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem;
    }
    .bea-rbcm .bea-rbcm-source {
      border: 1px solid #e2e8f0; border-radius: 12px; padding: 0.85rem; background: #fff;
      min-width: 0; display: grid; gap: 0.45rem;
    }
    .bea-rbcm .bea-rbcm-source[data-state='ok'] { border-color: #86efac; background: #f0fdf4; }
    .bea-rbcm .bea-rbcm-source[data-state='ready'] { border-color: #fcd34d; background: #fffbeb; }
    .bea-rbcm .bea-rbcm-source[data-state='missing'] { border-style: dashed; }
    .bea-rbcm .bea-rbcm-source[data-state='error'] { border-color: #fca5a5; background: #fef2f2; }
    .bea-rbcm .bea-rbcm-source header {
      display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;
    }
    .bea-rbcm .bea-rbcm-source__name {
      margin: 0; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .bea-rbcm .bea-rbcm-dl {
      display: grid; gap: 0.25rem; margin: 0; font-size: 0.86rem;
    }
    .bea-rbcm .bea-rbcm-dl > div { display: grid; grid-template-columns: 6.5rem 1fr; gap: 0.35rem; }
    .bea-rbcm .bea-rbcm-dl dt { color: #64748b; margin: 0; }
    .bea-rbcm .bea-rbcm-dl dd { margin: 0; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
    .bea-rbcm .bea-rbcm-doc-card {
      display: grid; gap: 0.75rem; padding: 1rem; border-radius: 12px;
      border: 1px solid #f59e0b; background: #fff;
    }
    .bea-rbcm .bea-rbcm-doc-banner {
      margin: 0; padding: 0.65rem 0.85rem; border-radius: 10px;
      border: 1px solid #f59e0b; background: #fffbeb; color: #92400e;
      font-weight: 700; letter-spacing: 0.02em; font-size: 0.92rem;
    }
    .bea-rbcm .bea-rbcm-doc-head {
      display: flex; align-items: flex-start; justify-content: space-between; gap: 0.75rem;
    }
    .bea-rbcm .bea-rbcm-doc-block { margin-top: 1.1rem; }
    .bea-rbcm .bea-rbcm-doc-block h3 { margin: 0 0 0.4rem; font-size: 0.95rem; }
    .bea-rbcm .bea-rbcm-warn-list {
      margin: 0.35rem 0 0; padding-left: 1.15rem; color: #64748b; font-size: 0.86rem;
      display: grid; gap: 0.28rem;
    }
    .bea-rbcm .bea-rbcm-tech { margin-top: 0.35rem; }
    .bea-rbcm .bea-rbcm-tech summary { cursor: pointer; color: #64748b; font-size: 0.85rem; }
    .bea-rbcm .bea-mg__btn {
      min-height: 2.25rem; white-space: nowrap;
    }
    .bea-rbcm .bea-mg__btn mat-icon {
      font-size: 1.1rem; width: 1.1rem; height: 1.1rem;
    }
    /* Toasts / drawers : rester dans le viewport (évite coupe à droite) */
    :host-context(body) .bea-feedback-host,
    :host-context(body) .bea-toast-stack {
      max-width: min(28rem, calc(100vw - 1.5rem));
    }
    @keyframes bea-rbcm-in {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: none; }
    }
    @media (max-width: 900px) {
      .bea-rbcm .bea-rbcm-period-bar,
      .bea-rbcm .bea-rbcm-sources { grid-template-columns: 1fr; }
      .bea-rbcm .bea-rbcm-upload { max-width: none; }
    }
    @media (max-width: 768px) {
      .bea-rbcm .bea-rbcm-filters .bea-mg__field { flex: 1 1 100%; min-width: 0; }
      .bea-rbcm .bea-rbcm-ellipsis { max-width: 12rem; }
      .bea-rbcm .bea-rbcm-dl > div { grid-template-columns: 1fr; gap: 0.1rem; }
      .bea-rbcm .bea-rbcm-pager { justify-content: flex-start; }
      .bea-rbcm .bea-mg__actions .bea-mg__btn { flex: 1 1 auto; justify-content: center; }
    }
    @media (prefers-reduced-motion: reduce) {
      .bea-rbcm .bea-mg__panel,
      .bea-rbcm .bea-rbcm-list li,
      .bea-rbcm .bea-rbcm-progress__bar,
      .bea-rbcm .bea-rbcm-row { animation: none; transition: none; }
    }
  `,
})
export class RbcmStylesComponent {}
