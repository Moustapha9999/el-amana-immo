// Génère src/theme-dark.css : surcharges « mode sombre » dérivées automatiquement des styles existants.
// Usage : node scripts/generate-dark-theme.mjs   (à relancer après une modification de styles)
//
// Principe : pour chaque règle portant des couleurs, la règle est ré-émise sous html[data-theme='dark']
// avec des couleurs transformées (fonds clairs → sombres, textes sombres → clairs, teintes conservées).
// Toutes les déclarations de couleur d'une règle sont ré-émises pour préserver l'ordre de la cascade.
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as sass from 'sass';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SRC = join(ROOT, 'src');
const OUT = join(SRC, 'theme-dark.css');
const BASE = join(SRC, 'styles', 'theme-dark-base.css');
const DARK = "[data-theme='dark']";
/** Écrans de connexion (identité visuelle bleue conservée) et zones déjà sombres. */
const EXCLUS = /\.auth-|app-auth-screen|\.bea-chrome\b|__side\b|__sidenav\b/;
const DOSSIERS_EXCLUS = [join('src', 'app', 'auth')];

const GLOBAL_SHEETS = [
  'src/app/plateforme/plateforme-ui.css',
  'src/app/achats-appro/achats-ui.css',
  'src/app/achats-appro/achats-apercu.css',
  'src/styles.scss',
];

// ——— Couleurs ———

const COLOR_RE = /#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b|rgba?\([^)]*\)|hsla?\([^)]*\)|\b(?:white|black)\b/g;

function parseColor(s) {
  const t = s.toLowerCase();
  if (t === 'white') return { r: 255, g: 255, b: 255, a: 1 };
  if (t === 'black') return { r: 0, g: 0, b: 0, a: 1 };
  if (t.startsWith('#')) {
    let h = t.slice(1);
    if (h.length <= 4) h = [...h].map((c) => c + c).join('');
    const n = (i) => parseInt(h.slice(i, i + 2), 16);
    return { r: n(0), g: n(2), b: n(4), a: h.length === 8 ? n(6) / 255 : 1 };
  }
  const nums = t.replace(/^[a-z]+\(|\)$/g, '').split(/[\s,/]+/).filter(Boolean);
  const val = (x, max) => (x.endsWith('%') ? (parseFloat(x) / 100) * max : parseFloat(x));
  if (t.startsWith('rgb')) {
    return { r: val(nums[0], 255), g: val(nums[1], 255), b: val(nums[2], 255), a: nums[3] !== undefined ? val(nums[3], 1) : 1 };
  }
  if (t.startsWith('hsl')) {
    const [r, g, b] = hslToRgb(parseFloat(nums[0]) / 360, val(nums[1], 1), val(nums[2], 1));
    return { r, g, b, a: nums[3] !== undefined ? val(nums[3], 1) : 1 };
  }
  return null;
}

function rgbToHsl(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h;
  if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
  else if (max === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  return [h / 6, s, l];
}

function hslToRgb(h, s, l) {
  if (s === 0) return [l * 255, l * 255, l * 255];
  const hue = (p, q, t) => {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  return [hue(p, q, h + 1 / 3) * 255, hue(p, q, h) * 255, hue(p, q, h - 1 / 3) * 255];
}

function fmt(h, s, l, a) {
  const [r, g, b] = hslToRgb(h, s, l).map((x) => Math.round(Math.min(255, Math.max(0, x))));
  if (a >= 1) return '#' + [r, g, b].map((x) => x.toString(16).padStart(2, '0')).join('');
  return `rgb(${r} ${g} ${b} / ${+a.toFixed(3)})`;
}

/** Transforme une couleur selon son rôle ; renvoie null si inchangée. */
function transform(role, c) {
  const [h, s, l] = rgbToHsl(c.r, c.g, c.b);
  const a = c.a;
  if (role === 'bg') {
    if (a < 0.6) return l < 0.35 && a <= 0.35 ? fmt(0, 0, 1, Math.min(0.12, a * 1.4)) : null;
    if (l < 0.8) return null;
    // Blanc = surface « élevée » (cartes), quasi-blancs = fond de page : la hiérarchie reste lisible.
    if (l >= 0.995) return fmt(0, 0, 0.122, a);
    return s < 0.3 ? fmt(h, Math.min(s, 0.1), 0.075 + (1 - l) * 0.9, a) : fmt(h, Math.min(s, 0.5), 0.13 + (1 - l) * 0.45, a);
  }
  if (role === 'text') {
    if (l > 0.5 || a < 0.3) return null;
    return s < 0.3 ? fmt(h, Math.min(s, 0.15), 0.93 - l * 0.55, a) : fmt(h, Math.min(s, 0.75), Math.max(0.66, 1 - l * 0.75), a);
  }
  if (role === 'border') {
    if (a < 0.5) return l < 0.35 ? fmt(0, 0, 1, Math.min(0.14, a * 1.4)) : null;
    if (l < 0.7) return null;
    return l > 0.85 || s < 0.3 ? fmt(h, Math.min(s, 0.12), 0.2 + (1 - l) * 0.4, a) : fmt(h, Math.min(s, 0.45), 0.3, a);
  }
  return null;
}

const ROLE = {
  background: 'bg', 'background-color': 'bg', 'background-image': 'bg',
  color: 'text', fill: 'text', stroke: 'text', 'caret-color': 'text', '-webkit-text-fill-color': 'text',
  border: 'border', 'border-color': 'border', 'border-top': 'border', 'border-right': 'border', 'border-bottom': 'border',
  'border-left': 'border', 'border-top-color': 'border', 'border-right-color': 'border', 'border-bottom-color': 'border',
  'border-left-color': 'border', 'border-block': 'border', 'border-inline': 'border', 'border-block-start': 'border',
  'border-block-end': 'border', 'border-inline-start': 'border', 'border-inline-end': 'border', outline: 'border',
  'outline-color': 'border', 'text-decoration-color': 'border', 'column-rule-color': 'border', 'box-shadow': 'border',
};

/** Fond resté clair (non transformé) : le texte de la règle est conservé pour garder le contraste. */
function fondClairConserve(decls) {
  for (const d of decls) {
    if (ROLE[d.prop] !== 'bg') continue;
    for (const m of d.value.match(COLOR_RE) ?? []) {
      const c = parseColor(m);
      if (!c || c.a < 0.6) continue;
      const [, , l] = rgbToHsl(c.r, c.g, c.b);
      if (l >= 0.45 && transform('bg', c) === null) return true;
    }
  }
  return false;
}

function transformDecls(decls) {
  const garderTexte = fondClairConserve(decls);
  const out = [];
  for (const d of decls) {
    const role = ROLE[d.prop];
    if (!role || !COLOR_RE.test(d.value)) continue;
    COLOR_RE.lastIndex = 0;
    let changed = false;
    const value = d.value.replace(COLOR_RE, (m) => {
      if (role === 'text' && garderTexte) return m;
      const c = parseColor(m);
      if (!c) return m;
      const r = role === 'border' && d.prop === 'box-shadow' ? (rgbToHsl(c.r, c.g, c.b)[2] >= 0.7 ? transform('border', c) : null) : transform(role, c);
      if (r === null) return m;
      changed = true;
      return r;
    });
    out.push({ prop: d.prop, value, changed });
  }
  return out.some((d) => d.changed) ? out : [];
}

// ——— Analyse CSS minimale (règles, @media/@supports imbriqués) ———

function parse(css) {
  css = css.replace(/\/\*[\s\S]*?\*\//g, '');
  let i = 0;
  function block() {
    const nodes = [];
    while (i < css.length) {
      while (i < css.length && /\s/.test(css[i])) i++;
      if (i >= css.length || css[i] === '}') { i++; break; }
      const start = i;
      let depthParen = 0, quote = null;
      while (i < css.length) {
        const ch = css[i];
        if (quote) { if (ch === quote && css[i - 1] !== '\\') quote = null; }
        else if (ch === '"' || ch === "'") quote = ch;
        else if (ch === '(') depthParen++;
        else if (ch === ')') depthParen--;
        else if ((ch === '{' || ch === ';') && depthParen === 0) break;
        i++;
      }
      const prelude = css.slice(start, i).trim();
      if (css[i] === ';') { i++; continue; }
      i++;
      if (prelude.startsWith('@')) {
        const name = prelude.split(/[\s(]/)[0];
        if (['@media', '@supports', '@layer', '@container'].includes(name)) nodes.push({ at: prelude, children: block() });
        else skipBlock();
      } else {
        nodes.push({ sel: prelude, decls: declarations() });
      }
    }
    return nodes;
  }
  function skipBlock() {
    let depth = 1;
    while (i < css.length && depth) { if (css[i] === '{') depth++; else if (css[i] === '}') depth--; i++; }
  }
  function declarations() {
    const start = i;
    let depth = 1;
    while (i < css.length && depth) { if (css[i] === '{') depth++; else if (css[i] === '}') depth--; i++; }
    const body = css.slice(start, i - 1);
    return body.split(/;(?![^(]*\))/).map((x) => x.trim()).filter(Boolean).map((x) => {
      const k = x.indexOf(':');
      return k < 0 ? null : { prop: x.slice(0, k).trim().toLowerCase(), value: x.slice(k + 1).trim() };
    }).filter((d) => d && !d.prop.startsWith('--'));
  }
  return block();
}

function splitSelectors(sel) {
  const parts = [];
  let depth = 0, cur = '';
  for (const ch of sel) {
    if (ch === '(') depth++;
    if (ch === ')') depth--;
    if (ch === ',' && depth === 0) { parts.push(cur.trim()); cur = ''; } else cur += ch;
  }
  if (cur.trim()) parts.push(cur.trim());
  return parts;
}

function compounds(sel) {
  return sel.replace(/\([^)]*\)/g, '').split(/\s*[>+~]\s*|\s+/).filter(Boolean).length;
}

function prefixSelector(part, host) {
  let p = part;
  if (host !== null) {
    if (p.includes(':host-context')) return null;
    p = p.replace(/::ng-deep\s*/g, '').replace(/:host\(([^)]*)\)/g, `${host}$1`).replace(/:host\b/g, host).trim();
    if (!p) return null;
  }
  if (/^(:root|html)\b/.test(p)) p = p.replace(/^(:root|html)/, '');
  const boost = host !== null ? compounds(p) + 1 : 1;
  const prefix = 'html' + DARK.repeat(boost);
  if (p.startsWith('[') || p.startsWith(':') || p === '') return prefix + p;
  return `${prefix} ${p}`;
}

function emit(nodes, host, indent = '') {
  let out = '';
  for (const n of nodes) {
    if (n.at) {
      if (/\bprint\b/.test(n.at)) continue;
      const inner = emit(n.children, host, indent + '  ');
      if (inner) out += `${indent}${n.at} {\n${inner}${indent}}\n`;
      continue;
    }
    const decls = transformDecls(n.decls);
    if (!decls.length) continue;
    const sels = splitSelectors(n.sel).filter((s) => !EXCLUS.test(s)).map((s) => prefixSelector(s, host)).filter(Boolean);
    if (!sels.length) continue;
    out += `${indent}${sels.join(',\n' + indent)} {\n${decls.map((d) => `${indent}  ${d.prop}: ${d.value};`).join('\n')}\n${indent}}\n`;
  }
  return out;
}

// ——— Sources ———

function compile(source, file) {
  if (!/\.scss$/.test(file) && !/[$@&]|#\{/.test(source)) return source;
  try {
    return sass.compileString(source, { loadPaths: [dirname(file), SRC], syntax: 'scss', silenceDeprecations: ['import'] }).css;
  } catch (e) {
    console.warn(`! ${relative(ROOT, file)} : ${e.message.split('\n')[0]}`);
    return '';
  }
}

function walk(dir, acc = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, acc);
    else if (p.endsWith('.ts') && !p.endsWith('.spec.ts')) acc.push(p);
  }
  return acc;
}

function componentStyles(file) {
  const ts = readFileSync(file, 'utf8');
  const out = [];
  const re = /@Component\(\{([\s\S]*?)\n\}\)\s*\n?export class/g;
  let m;
  while ((m = re.exec(ts))) {
    const meta = m[1];
    const selector = meta.match(/selector:\s*'([^']+)'/)?.[1]?.split(',')[0].trim() ?? null;
    const global = /ViewEncapsulation\.None/.test(meta);
    const host = global ? null : selector && /^[a-z][\w-]*$/.test(selector) ? selector : null;
    if (!global && host === null) continue;
    const css = [];
    const styles = meta.match(/styles:\s*(\[[\s\S]*?\]|`[\s\S]*?`)\s*,?\s*\n\s*(?:[a-zA-Z]+:|$)/);
    if (styles) for (const s of styles[1].matchAll(/`([\s\S]*?)`/g)) css.push(compile(s[1], file));
    for (const u of meta.matchAll(/styleUrls?:\s*(\[[^\]]*\]|'[^']*')/g)) {
      for (const f of u[1].matchAll(/'([^']+)'/g)) {
        const path = join(dirname(file), f[1]);
        css.push(compile(readFileSync(path, 'utf8'), path));
      }
    }
    if (css.length) out.push({ host, css: css.join('\n') });
  }
  return out;
}

let body = '';
for (const rel of GLOBAL_SHEETS) {
  const file = join(ROOT, rel);
  const css = compile(readFileSync(file, 'utf8'), file);
  const part = emit(parse(css), null);
  if (part) body += `/* ${rel} */\n${part}`;
}
for (const file of walk(join(SRC, 'app')).filter((f) => !DOSSIERS_EXCLUS.some((d) => relative(ROOT, f).startsWith(d)))) {
  for (const { host, css } of componentStyles(file)) {
    const part = emit(parse(css), host);
    if (part) body += `/* ${relative(ROOT, file).replace(/\\/g, '/')} */\n${part}`;
  }
}

const header = '/* Fichier généré par scripts/generate-dark-theme.mjs — ne pas modifier à la main. */\n';
const contenu = header + body + '\n/* Corrections manuelles */\n' + readFileSync(BASE, 'utf8');
writeFileSync(OUT, contenu);

// Le bundle non injecté n'est pas haché : version dans l'URL pour invalider le cache navigateur.
const version = createHash('sha256').update(contenu).digest('hex').slice(0, 10);
const INDEX = join(SRC, 'index.html');
writeFileSync(INDEX, readFileSync(INDEX, 'utf8').replace(/theme-dark\.css(\?v=[0-9a-f]*)?/g, `theme-dark.css?v=${version}`));
writeFileSync(
  join(SRC, 'app', 'core', 'services', 'theme-dark.version.ts'),
  `// Généré par scripts/generate-dark-theme.mjs.\nexport const THEME_DARK_VERSION = '${version}';\n`,
);
console.log(`theme-dark.css : ${(Buffer.byteLength(header + body) / 1024).toFixed(0)} Ko générés`);
