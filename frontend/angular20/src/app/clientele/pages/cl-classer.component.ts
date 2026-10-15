import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { Subscription, timer } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { CL_BASE, dateHeureFr, n } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

type Population = 'TOUS' | 'PP' | 'PM';
type Statut = 'EN_ATTENTE' | 'EN_COURS' | 'TERMINE' | 'TERMINE_ERREURS' | 'INTERROMPU' | 'ECHEC';
interface Perimetre { TOUS: number; PP: number; PM: number; NON_IDENTIFIE: number; }
interface Tache {
  id: string; statut: Statut; population: Population; code_agence: string | null; motif: string;
  total: number; traites: number; pourcentage: number; message: string | null; reprenable: boolean;
  resume: { classes: number; preserves: number; non_classes: number; erreurs: number };
  erreurs: { racine: string; message: string }[];
  created_at: string | null; debut: string | null; fin: string | null; maj_le: string | null;
}

const ACTIFS: readonly Statut[] = ['EN_ATTENTE', 'EN_COURS'];
const LIB_STATUT: Record<Statut, string> = {
  EN_ATTENTE: 'En attente', EN_COURS: 'En cours', TERMINE: 'Classification terminée',
  TERMINE_ERREURS: 'Terminée avec erreurs', INTERROMPU: 'Interrompue', ECHEC: 'Échec technique',
};
const LIB_POPULATION: Record<Population, string> = {
  TOUS: 'tous les clients', PP: 'les personnes physiques (PP)', PM: 'les personnes morales (PM)',
};
const INTERVALLE_SUIVI_MS = 1500;

@Component({
  selector: 'bea-cl-classer',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule],
  styles: [`
    :host { display: block; padding: 0 1.1rem 0.9rem; }
    .cls-bar { display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap;
      padding: 0.85rem 1rem; border: 1px solid #dbe3ee; border-radius: 0.9rem; background: linear-gradient(135deg, #f8fbff, #eef5fb); }
    .cls-bar h3 { margin: 0; font-size: 0.98rem; color: #0f172a; }
    .cls-bar p { margin: 0.2rem 0 0; font-size: 0.8rem; color: #64748b; max-width: 44rem; }
    .cls-go { display: inline-flex; align-items: center; gap: 0.45rem; padding: 0.7rem 1.5rem; border: 0; border-radius: 0.7rem;
      background: #1a5278; color: #fff; font: inherit; font-size: 0.95rem; font-weight: 700; cursor: pointer;
      box-shadow: 0 6px 16px rgba(26, 82, 120, 0.25); transition: background 0.15s, transform 0.15s, box-shadow 0.15s; }
    .cls-go:hover:not(:disabled) { background: #123d5b; transform: translateY(-1px); box-shadow: 0 8px 20px rgba(26, 82, 120, 0.3); }
    .cls-go:focus-visible { outline: 3px solid rgba(26, 82, 120, 0.35); outline-offset: 2px; }
    .cls-go:disabled { background: #94a3b8; box-shadow: none; cursor: not-allowed; }
    .cls-go mat-icon { font-size: 1.25rem; width: 1.25rem; height: 1.25rem; }
    .cls-go.is-spin mat-icon { animation: cls-spin 1.1s linear infinite; }
    @keyframes cls-spin { to { transform: rotate(360deg); } }
    .cls-panel { margin-top: 0.7rem; padding: 0.9rem 1rem; border: 1px solid #dbe3ee; border-radius: 0.9rem; background: #fff; }
    .cls-panel h4 { margin: 0 0 0.6rem; font-size: 0.85rem; color: #0f172a; }
    .cls-choix { display: grid; grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr)); gap: 0.6rem; margin: 0; padding: 0; border: 0; }
    .cls-carte { position: relative; display: flex; gap: 0.6rem; align-items: flex-start; padding: 0.75rem 0.85rem; border: 1.5px solid #dbe3ee;
      border-radius: 0.8rem; cursor: pointer; background: #f8fafc; transition: border-color 0.15s, background 0.15s; }
    .cls-carte:hover { border-color: #93b4cf; }
    .cls-carte.is-on { border-color: #1a5278; background: #eef5fb; box-shadow: 0 0 0 2px rgba(26, 82, 120, 0.12); }
    .cls-carte input { position: absolute; opacity: 0; pointer-events: none; }
    .cls-carte:has(input:focus-visible) { outline: 3px solid rgba(26, 82, 120, 0.35); outline-offset: 2px; }
    .cls-carte mat-icon { color: #1a5278; flex: 0 0 auto; }
    .cls-carte strong { display: block; font-size: 0.88rem; color: #0f172a; }
    .cls-carte small { display: block; margin-top: 0.15rem; font-size: 0.76rem; color: #64748b; }
    .cls-carte em { display: block; margin-top: 0.3rem; font-style: normal; font-size: 0.95rem; font-weight: 700; color: #1a5278; font-variant-numeric: tabular-nums; }
    .cls-actions { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 0.8rem; margin-top: 0.8rem; }
    .cls-actions label { display: grid; gap: 0.25rem; font-size: 0.75rem; font-weight: 700; color: #475569; }
    .cls-actions select { font: inherit; font-weight: 400; padding: 0.4rem 0.5rem; border: 1px solid #cbd5e1; border-radius: 0.5rem; min-width: 14rem; }
    .cls-aide { margin: 0.7rem 0 0; font-size: 0.76rem; color: #64748b; line-height: 1.45; }
    .cls-suivi { margin-top: 0.7rem; padding: 0.85rem 1rem; border: 1px solid #dbe3ee; border-radius: 0.9rem; background: #fff; }
    .cls-suivi[data-s='TERMINE'] { border-color: #86efac; background: #f0fdf4; }
    .cls-suivi[data-s='TERMINE_ERREURS'], .cls-suivi[data-s='INTERROMPU'] { border-color: #fdba74; background: #fff7ed; }
    .cls-suivi[data-s='ECHEC'] { border-color: #fca5a5; background: #fef2f2; }
    .cls-ligne { display: flex; align-items: center; justify-content: space-between; gap: 0.8rem; flex-wrap: wrap; font-size: 0.82rem; color: #334155; }
    .cls-ligne strong { font-size: 1.05rem; color: #0f172a; font-variant-numeric: tabular-nums; }
    .cls-etat { display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.2rem 0.6rem; border-radius: 999px; font-size: 0.74rem; font-weight: 700;
      background: #e2e8f0; color: #334155; }
    .cls-etat mat-icon { font-size: 1rem; width: 1rem; height: 1rem; }
    .cls-etat[data-s='EN_COURS'] { background: #dbeafe; color: #1e40af; }
    .cls-etat[data-s='TERMINE'] { background: #dcfce7; color: #166534; }
    .cls-etat[data-s='TERMINE_ERREURS'], .cls-etat[data-s='INTERROMPU'] { background: #ffedd5; color: #9a3412; }
    .cls-etat[data-s='ECHEC'] { background: #fee2e2; color: #991b1b; }
    .cls-piste { position: relative; height: 0.75rem; margin: 0.55rem 0; border-radius: 999px; background: #e2e8f0; overflow: hidden; }
    .cls-jauge { height: 100%; border-radius: inherit; background: #1a5278; transition: width 0.6s ease; }
    .cls-piste.is-actif .cls-jauge { background-image: linear-gradient(45deg, rgba(255,255,255,.18) 25%, transparent 25%, transparent 50%,
      rgba(255,255,255,.18) 50%, rgba(255,255,255,.18) 75%, transparent 75%); background-size: 1rem 1rem; animation: cls-raies 1s linear infinite; }
    @keyframes cls-raies { to { background-position: 1rem 0; } }
    .cls-suivi[data-s='TERMINE'] .cls-jauge { background: #16a34a; }
    .cls-suivi[data-s='TERMINE_ERREURS'] .cls-jauge, .cls-suivi[data-s='INTERROMPU'] .cls-jauge { background: #ea580c; }
    .cls-suivi[data-s='ECHEC'] .cls-jauge { background: #dc2626; }
    .cls-bilan { display: grid; grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr)); gap: 0.5rem; margin-top: 0.7rem; }
    .cls-bilan div { padding: 0.5rem 0.65rem; border-radius: 0.65rem; background: rgba(255, 255, 255, 0.75); border: 1px solid #e2e8f0; }
    .cls-bilan span { display: block; font-size: 0.68rem; font-weight: 700; text-transform: uppercase; color: #64748b; }
    .cls-bilan strong { font-size: 1.1rem; color: #0f172a; font-variant-numeric: tabular-nums; }
    .cls-bilan [data-t='ok'] strong { color: #15803d; }
    .cls-bilan [data-t='warn'] strong { color: #c2410c; }
    .cls-bilan [data-t='ko'] strong { color: #b91c1c; }
    .cls-msg { display: flex; gap: 0.45rem; align-items: flex-start; margin: 0.6rem 0 0; font-size: 0.8rem; color: #9a3412; }
    .cls-msg mat-icon { flex: 0 0 auto; font-size: 1.1rem; width: 1.1rem; height: 1.1rem; }
    .cls-verrou { padding: 0.6rem 0.8rem; border: 1px solid #fed7aa; border-radius: 0.7rem; background: #fff7ed; }
    .cls-err { margin: 0.4rem 0 0; padding-left: 1.2rem; font-size: 0.76rem; color: #7f1d1d; max-height: 8rem; overflow: auto; }
    .cls-meta { margin: 0.5rem 0 0; font-size: 0.74rem; color: #64748b; }
    .cls-meta button { margin-left: 0.5rem; }
  `],
  template: `
    <div class="cls-bar">
      <div>
        <h3>Classement par le moteur SCORE</h3>
        <p>Calcule le niveau de risque des clients choisis. Décisions manuelles et classes issues d’un fichier jamais écrasées (réexamen ouvert en cas d’écart). Seuls les résultats admissibles sont enregistrés.</p>
      </div>
      <button type="button" class="cls-go" [class.is-spin]="actif()" (click)="basculer()" [disabled]="actif() || busy() || !autorise()"
              [attr.aria-expanded]="ouvert()" [title]="!autorise() ? 'Classement de masse suspendu côté serveur' : actif() ? 'Une classification est en cours' : 'Choisir les clients à classer'">
        <mat-icon>{{ !autorise() ? 'lock' : actif() ? 'autorenew' : 'play_circle' }}</mat-icon>{{ actif() ? 'Classification en cours…' : 'Classer' }}
      </button>
    </div>
    @if (verrou(); as v) {
      @if (!v.actif) { <p class="cls-msg cls-verrou"><mat-icon>lock</mat-icon>{{ v.message }}</p> }
    }

    @if (ouvert() && !actif()) {
      <div class="cls-panel">
        <h4>Choisir les clients à classer</h4>
        <fieldset class="cls-choix" role="radiogroup" aria-label="Clients à classer">
          @for (c of choix; track c.code) {
            <label class="cls-carte" [class.is-on]="population() === c.code">
              <input type="radio" name="cls-population" [value]="c.code" [checked]="population() === c.code" (change)="population.set(c.code)" />
              <mat-icon>{{ c.icon }}</mat-icon>
              <span>
                <strong>{{ c.libelle }}</strong>
                <small>{{ c.aide }}</small>
                <em>{{ perimetre() ? n(perimetre()![c.code]) + ' client(s)' : '…' }}</em>
              </span>
            </label>
          }
        </fieldset>
        @if (population() === 'TOUS' && perimetre()?.NON_IDENTIFIE) {
          <p class="cls-aide">« Tous les clients » inclut aussi {{ n(perimetre()!.NON_IDENTIFIE) }} client(s) dont le profil PP / PM n’est pas encore identifié.</p>
        }
        <div class="cls-actions">
          <label>Agence (optionnel)
            <select [(ngModel)]="agence">
              <option value="">Toutes les agences</option>
              @for (a of store.agences(); track a.code) { <option [value]="a.code">{{ a.code }} — {{ a.libelle }}</option> }
            </select>
          </label>
          <span style="display:flex;gap:0.5rem">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="ouvert.set(false)">Annuler</button>
            <button type="button" class="cls-go" (click)="lancer()" [disabled]="busy()"><mat-icon>play_arrow</mat-icon>Lancer la classification</button>
          </span>
        </div>
        <p class="cls-aide">Le traitement s’exécute sur le serveur : vous pouvez quitter ou rafraîchir la page, la progression est conservée. Une seule classification à la fois.</p>
      </div>
    }

    @if (tache(); as t) {
      <div class="cls-suivi" [attr.data-s]="t.statut" role="status" aria-live="polite">
        <div class="cls-ligne">
          <span class="cls-etat" [attr.data-s]="t.statut"><mat-icon>{{ icone(t.statut) }}</mat-icon>{{ libStatut[t.statut] }}</span>
          <span>{{ libPopulation[t.population] }}@if (t.code_agence) { · agence {{ t.code_agence }}}</span>
          <strong>{{ pourcent(t) }} %</strong>
        </div>
        <div class="cls-piste" [class.is-actif]="t.statut === 'EN_COURS'" role="progressbar" aria-valuemin="0" aria-valuemax="100" [attr.aria-valuenow]="pourcent(t)">
          <div class="cls-jauge" [style.width.%]="pourcent(t)"></div>
        </div>
        <div class="cls-ligne">
          <span><strong>{{ n(t.traites) }}</strong> client(s) traité(s) sur {{ n(t.total) }}</span>
          @if (t.statut === 'EN_COURS' && restant(t); as r) { <span>Temps restant estimé : {{ r }}</span> }
        </div>
        @if (!enCours(t.statut) || t.traites > 0) {
          <div class="cls-bilan">
            <div data-t="ok"><span>Classés</span><strong>{{ n(t.resume.classes) }}</strong></div>
            <div><span>Préservés (manuel / fichier)</span><strong>{{ n(t.resume.preserves) }}</strong></div>
            <div data-t="warn"><span>Non classés</span><strong>{{ n(t.resume.non_classes) }}</strong></div>
            <div [attr.data-t]="t.resume.erreurs ? 'ko' : null"><span>En erreur</span><strong>{{ n(t.resume.erreurs) }}</strong></div>
          </div>
        }
        @if (t.message) { <p class="cls-msg"><mat-icon>error_outline</mat-icon>{{ t.message }}</p> }
        @if (suiviPerdu()) { <p class="cls-msg"><mat-icon>wifi_off</mat-icon>Suivi momentanément indisponible ({{ suiviPerdu() }}). Le traitement continue sur le serveur ; nouvelle tentative automatique.</p> }
        @if (t.erreurs.length) {
          <ul class="cls-err">@for (e of t.erreurs; track e.racine) { <li><code>{{ e.racine }}</code> : {{ e.message }}</li> }</ul>
        }
        <p class="cls-meta">
          Non classés = aucun critère évaluable (NON CLASSÉ) ou résultat non admissible, rien n’est écrit.
          Lancée le {{ dh(t.created_at) }}@if (t.fin) { · terminée le {{ dh(t.fin) }}}.
          @if (t.reprenable && store.cap().classif_executer && autorise()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="reprendre(t)" [disabled]="busy()"><mat-icon>replay</mat-icon> Reprendre</button>
          }
        </p>
      </div>
    }
  `,
})
export class ClClasserComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ClienteleStore);
  readonly termine = output<void>();

  readonly choix: { code: Population; libelle: string; aide: string; icon: string }[] = [
    { code: 'TOUS', libelle: 'Tous les clients', aide: 'Personnes physiques et morales', icon: 'groups' },
    { code: 'PP', libelle: 'Personnes physiques (PP)', aide: 'Uniquement les particuliers', icon: 'person' },
    { code: 'PM', libelle: 'Personnes morales (PM)', aide: 'Uniquement les entreprises et entités', icon: 'business' },
  ];
  readonly libStatut = LIB_STATUT;
  readonly libPopulation = LIB_POPULATION;
  readonly n = n;
  readonly dh = dateHeureFr;
  readonly ouvert = signal(false);
  readonly busy = signal(false);
  readonly population = signal<Population>('TOUS');
  readonly perimetre = signal<Perimetre | null>(null);
  readonly tache = signal<Tache | null>(null);
  readonly suiviPerdu = signal('');
  readonly actif = computed(() => !!this.tache() && this.enCours(this.tache()!.statut));
  readonly verrou = signal<{ actif: boolean; message: string | null } | null>(null);
  readonly autorise = computed(() => !!this.verrou()?.actif);
  agence = '';
  private suivi?: Subscription;
  private detruit = false;

  constructor() {
    inject(DestroyRef).onDestroy(() => { this.detruit = true; this.suivi?.unsubscribe(); });
  }

  ngOnInit(): void {
    this.api.get<{ actif: boolean; message: string | null }>(`${CL_BASE}/classification/taches/autorisation`).subscribe({
      next: (v) => this.verrou.set(v),
      error: () => this.verrou.set({ actif: false, message: 'Autorisation du classement de masse indisponible : lancement désactivé.' }),
    });
    this.api.get<Tache | null>(`${CL_BASE}/classification/taches/courante`).subscribe({
      next: (t) => { this.tache.set(t); if (t && this.enCours(t.statut)) this.suivre(t.id); },
      error: () => this.tache.set(null),
    });
  }

  enCours(s: Statut): boolean { return ACTIFS.includes(s); }

  pourcent(t: Tache): number {
    if (t.statut === 'TERMINE' || t.statut === 'TERMINE_ERREURS') return 100;
    return Math.min(100, Math.floor(t.pourcentage));
  }

  icone(s: Statut): string {
    return { EN_ATTENTE: 'schedule', EN_COURS: 'autorenew', TERMINE: 'check_circle', TERMINE_ERREURS: 'warning',
      INTERROMPU: 'pause_circle', ECHEC: 'error' }[s];
  }

  restant(t: Tache): string | null {
    if (!t.debut || !t.maj_le || t.traites < 1 || t.traites >= t.total) return null;
    const ecoule = (Date.parse(t.maj_le) - Date.parse(t.debut)) / 1000;
    if (ecoule <= 0) return null;
    const s = Math.round(((t.total - t.traites) * ecoule) / t.traites);
    return s < 60 ? 'moins d’une minute' : s < 3600 ? `${Math.round(s / 60)} min` : `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min`;
  }

  basculer(): void {
    this.ouvert.set(!this.ouvert());
    if (this.ouvert()) {
      this.api.get<Perimetre>(`${CL_BASE}/classification/taches/perimetre`).subscribe({
        next: (p) => this.perimetre.set(p),
        error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Effectifs indisponibles')),
      });
    }
  }

  lancer(): void {
    const population = this.population();
    const agence = this.agence || null;
    const effectif = this.perimetre()?.[population];
    const cible = `${LIB_POPULATION[population]}${agence ? ` de l’agence ${agence}` : ''}`;
    this.feedback.runWithReason(
      (motif) => this.api.post<Tache>(`${CL_BASE}/classification/taches`, { motif, population, code_agence: agence }),
      {
        reason: {
          title: 'Classer les clients',
          message: `Lancer le moteur SCORE sur ${cible}${effectif !== undefined && !agence ? ` (${n(effectif)} client(s))` : ''} ?`,
          hint: 'Résultats admissibles uniquement. Décisions manuelles et classes de fichier préservées (réexamen si écart). Chaque évaluation est tracée.',
          reasonLabel: 'Motif de classement', reasonPlaceholder: 'Ex. classification hebdomadaire moteur CDC', maxLength: 500,
          confirmLabel: 'Classer', tone: 'primary',
        },
        busy: this.busy, loading: 'Lancement…',
        success: (t) => ({ title: 'Classification lancée', message: `${n(t.total)} client(s) à traiter. Suivez la progression sous le bouton « Classer ».` }),
        errorTitle: 'Classification non lancée', retry: false,
      },
    ).subscribe((t) => {
      this.ouvert.set(false);
      this.tache.set(t);
      this.suivre(t.id);
    });
  }

  reprendre(t: Tache): void {
    this.feedback.run(() => this.api.post<Tache>(`${CL_BASE}/classification/taches/${t.id}/reprendre`, {}), {
      confirm: { action: 'validation', title: 'Reprendre la classification', message: `Reprendre après les ${n(t.traites)} client(s) déjà traité(s) ?`, hint: 'Les clients déjà traités ne sont pas recalculés.' },
      busy: this.busy, loading: 'Reprise…', success: { title: 'Classification reprise' },
      errorTitle: 'Reprise refusée', retry: false,
    }).subscribe((r) => { this.tache.set(r); this.suivre(r.id); });
  }

  private suivre(id: string): void {
    this.suivi?.unsubscribe();
    if (this.detruit) return;
    this.suiviPerdu.set('');
    this.suivi = timer(INTERVALLE_SUIVI_MS, INTERVALLE_SUIVI_MS)
      .pipe(switchMap(() => this.api.get<Tache>(`${CL_BASE}/classification/taches/${id}`)))
      .subscribe({
        next: (t) => {
          this.suiviPerdu.set('');
          this.tache.set(t);
          if (this.enCours(t.statut)) return;
          this.suivi?.unsubscribe();
          this.terminer(t);
        },
        error: (e) => void describeApiErrorAsync(e).then((i) => {
          this.suiviPerdu.set(i.message || 'erreur réseau');
          setTimeout(() => this.suivre(id), INTERVALLE_SUIVI_MS * 4);
        }),
      });
  }

  private terminer(t: Tache): void {
    if (t.statut === 'TERMINE' || t.statut === 'TERMINE_ERREURS') {
      const details = [
        { label: 'Traités', value: n(t.traites) },
        { label: 'Classés', value: n(t.resume.classes) },
        { label: 'Préservés', value: n(t.resume.preserves) },
        { label: 'Non classés', value: n(t.resume.non_classes) },
        { label: 'En erreur', value: n(t.resume.erreurs) },
      ];
      if (t.statut === 'TERMINE') this.feedback.success({ title: 'Classification terminée', details });
      else this.feedback.warning({ title: 'Classification terminée avec erreurs', details });
    } else {
      this.feedback.error({ title: LIB_STATUT[t.statut], message: t.message || 'Le traitement s’est arrêté. « Reprendre » continue après le dernier client traité.' });
    }
    this.termine.emit();
  }
}
