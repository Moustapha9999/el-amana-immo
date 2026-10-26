// Thème appliqué avant le premier rendu (évite le flash clair). Fichier externe : la CSP refuse
// les scripts en ligne. Versions mises à jour par scripts/generate-dark-theme.mjs.
(function () {
  var t = null;
  try { t = localStorage.getItem('bea.theme'); } catch (e) {}
  if (t !== 'dark' && t !== 'light') t = window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  if (t === 'dark') document.write('<link id="bea-theme-dark" rel="stylesheet" href="theme-dark.css?v=479a2e5237">');
  document.documentElement.dataset.theme = t;
  document.documentElement.style.colorScheme = t;
})();
