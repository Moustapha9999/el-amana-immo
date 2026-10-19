import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { CL_BASE, dateFr, dateHeureFr, telecharger } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';
import { ClBcmReglesComponent, RegleBcm } from './cl-bcm-regles.component';
import { BADGE_SIC, RESULTATS_DEPOT, SicResume } from './cl-sic.component';

interface Controle { code: string; libelle: string; ok: boolean; detail: string; bloquant?: boolean; }
interface SicDetail extends SicResume {
  regles: RegleBcm[]; controles: Controle[]; colonnes: string[];
  controle_fichier: { ok: boolean; controles: Controle[] } | null;
  fichier_sha256: string | null; commentaire_validation: string | null; depot_commentaire: string | null;
  controlee_le: string | null; validee_le: string | null; depot_saisi_le: string | null;
  controlee_par: string | null; validee_par: string | null; generee_par: string | null; depot_par: string | null;
  synthese_anomalies: { gravite: string; champ: string; nombre: number }[];
  nb_incompletes: number;
  actions: { controler: boolean; valider: boolean; generer: boolean; deposer: boolean; telecharger: boolean };
}
interface Anomalie { gravite: string; champ: string; valeur: string | null; motif: string; action: string; }
interface Ligne { racine: string; statut: string; gravite_max: string | null; valeurs: (string | null)[]; anomalies: Anomalie[]; }
interface Lignes { total: number; colonnes: string[]; items: Ligne[]; }

const GRAVITES: Record<string, string> = { BLOQUANTE: 'Bloquante', A_CORRIGER: 'À corriger', AVERTISSEMENT: 'Avertissement' };
const ETAPES = ['BROUILLON', 'A_CORRIGER|CONTROLEE', 'VALIDEE_EXPORT', 'GENEREE', 'DEPOSEE'];
const LIBELLES_ETAPES = ['Brouillon', 'Contrôlée / à corriger', 'Validée pour export', 'Générée', 'Déposée'];

@Component({
  selector: 'bea-cl-sic-detail',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, ClienteleUiComponent, ClBcmReglesComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      @if (d(); as x) {
        <header class="bea-mg__head bea-cl-head">
          <div>
            <p class="bea-stock-page__kicker"><a routerLink="/clientele/sic">Déclaration SIC</a></p>
            <h1>SIC {{ x.type }} au {{ dateFr(x.date_reference) }}</h1>
            <p class="bea-cl-head__sub">
              <span class="bea-cl-badge" [attr.data-s]="badge[x.statut]">{{ x.statut_libelle }}</span>
              · Référentiel : {{ x.ref_version ?? 'aucune version active' }}
              · Créée le {{ dateHeureFr(x.created_at) }} par {{ x.cree_par ?? '—' }}
            </p>
          </div>
          <div style="display:flex;gap:0.45rem;flex-wrap:wrap;align-items:flex-start">
            @if (x.actions.controler) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="controler()" [disabled]="busy()"><mat-icon>refresh</mat-icon> Recontrôler</button>
            }
            @if (x.actions.valider) {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="valider()" [disabled]="busy()"><mat-icon>verified</mat-icon> Valider pour export</button>
            }
            @if (x.actions.generer) {
              <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="generer()" [disabled]="busy()"><mat-icon>file_present</mat-icon> Générer le fichier</button>
            }
            @if (x.actions.telecharger) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="telechargerFichier()" [disabled]="busy()"><mat-icon>download</mat-icon> {{ x.fichier_nom }}</button>
            }
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="rapport()" [disabled]="busy()"><mat-icon>report</mat-icon> Rapport d’anomalies</button>
          </div>
        </header>

        <ol class="bea-cl-timeline" style="margin:0 0 1rem 1.2rem">
          @for (e of etapes; track $index) {
            <li [style.opacity]="$index <= etapeCourante() ? 1 : 0.45"><strong>{{ libellesEtapes[$index] }}</strong>
              <span>{{ dateEtape($index) }}</span></li>
          }
        </ol>

        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Synthèse</h2></div>
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table">
              <tbody>
                <tr><th>Clients candidats</th><td>{{ x.nb_candidats }}</td><th>Clients exportés</th><td>{{ x.nb_lignes }}</td><th>Lignes incomplètes</th><td>{{ x.nb_incompletes }}</td></tr>
                <tr><th>Anomalies bloquantes</th><td>{{ x.nb_bloquantes }}</td><th>À corriger</th><td>{{ x.nb_a_corriger }}</td><th>Avertissements</th><td>{{ x.nb_avertissements }}</td></tr>
                <tr><th>Colonnes</th><td colspan="5">{{ x.colonnes.join(' · ') }}</td></tr>
                @if (x.commentaire_validation) {
                  <tr><th>Validation</th><td colspan="5">{{ x.commentaire_validation }} — {{ x.validee_par ?? '—' }}, {{ dateHeureFr(x.validee_le) }}</td></tr>
                }
                @if (x.fichier_nom) {
                  <tr><th>Fichier</th><td colspan="5">{{ x.fichier_nom }} — généré le {{ dateHeureFr(x.generee_le) }} par {{ x.generee_par ?? '—' }}<br /><span class="bea-cl-hint">SHA-256 {{ x.fichier_sha256 }}</span></td></tr>
                }
                @if (x.depot_le) {
                  <tr><th>Dépôt SIC</th><td colspan="5">{{ dateFr(x.depot_le) }} · {{ resultats[x.depot_resultat ?? ''] }}{{ x.depot_commentaire ? ' — ' + x.depot_commentaire : '' }}<br /><span class="bea-cl-hint">Saisi par {{ x.depot_par ?? '—' }} le {{ dateHeureFr(x.depot_saisi_le) }}</span></td></tr>
                }
              </tbody>
            </table>
          </div>
        </section>

        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Contrôles avant génération</h2></div>
          <ul class="bea-cl-anoms" style="margin:0 1.1rem 0.9rem">
            @for (c of x.controles; track c.code) {
              <li [attr.data-n]="c.ok ? 'ok' : (c.bloquant ? 'bloquant' : 'alerte')">
                <mat-icon>{{ c.ok ? 'check_circle' : (c.bloquant ? 'block' : 'warning') }}</mat-icon>
                <strong>{{ c.libelle }}</strong>@if (c.detail) { <span class="bea-cl-hint"> — {{ c.detail }}</span> }
              </li>
            }
          </ul>
        </section>

        @if (x.controle_fichier; as cf) {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Contrôle du fichier généré</h2>
              <span class="bea-cl-badge" [attr.data-s]="cf.ok ? 'VALIDEE' : 'A_CONTROLER'">{{ cf.ok ? 'Conforme' : 'Non conforme' }}</span></div>
            <ul class="bea-cl-anoms" style="margin:0 1.1rem 0.9rem">
              @for (c of cf.controles; track c.code) {
                <li [attr.data-n]="c.ok ? 'ok' : (c.bloquant === false ? 'alerte' : 'bloquant')"><mat-icon>{{ c.ok ? 'check_circle' : (c.bloquant === false ? 'warning' : 'block') }}</mat-icon>
                  <strong>{{ c.libelle }}</strong>@if (c.detail) { <span class="bea-cl-hint"> — {{ c.detail }}</span> }</li>
              }
            </ul>
          </section>
        }

        @if (x.actions.deposer) {
          <form class="bea-mg__panel bea-cl-filters" (submit)="$event.preventDefault(); deposer()">
            <strong style="flex-basis:100%">Enregistrer le dépôt effectué sur la plateforme SIC</strong>
            <p class="bea-cl-hint" style="flex-basis:100%">BEA DIGITAL n’envoie rien à la BCM : saisissez le résultat constaté sur la plateforme SIC.</p>
            <label>Date du dépôt<input type="date" [(ngModel)]="depotLe" name="depot_le" required /></label>
            <label>Résultat
              <select [(ngModel)]="depotResultat" name="depot_resultat">
                @for (r of resultatsListe; track r[0]) { <option [value]="r[0]">{{ r[1] }}</option> }
              </select>
            </label>
            <label style="flex:1 1 20rem">Commentaire (obligatoire si rejet ou acceptation partielle)<input [(ngModel)]="depotCommentaire" name="depot_commentaire" maxlength="2000" /></label>
            <div style="display:flex;align-items:end">
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || !depotLe"><mat-icon>cloud_done</mat-icon> Enregistrer le dépôt</button>
            </div>
          </form>
        }

        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top">
            <h2>Clients et anomalies</h2>
            <span class="bea-cl-hint">{{ lignes()?.total ?? 0 }} client(s)</span>
          </div>
          @if (x.synthese_anomalies.length) {
            <p class="bea-cl-hint" style="padding:0 1.1rem">
              @for (s of x.synthese_anomalies; track s.gravite + s.champ) {
                <button type="button" class="bea-cl-chip" (click)="filtrerChamp(s.champ, s.gravite)">{{ s.champ }} · {{ gravites[s.gravite] }} : {{ s.nombre }}</button>
              }
            </p>
          }
          <form class="bea-cl-filters" (submit)="$event.preventDefault(); page.set(1); chargerLignes()">
            <label>Ligne
              <select [(ngModel)]="fStatut" name="f_statut">
                <option value="">Toutes</option><option value="INCOMPLETE">Incomplètes</option><option value="COMPLETE">Complètes</option>
              </select>
            </label>
            <label>Gravité
              <select [(ngModel)]="fGravite" name="f_gravite">
                <option value="">Toutes</option>
                @for (g of gravitesListe; track g[0]) { <option [value]="g[0]">{{ g[1] }}</option> }
                <option value="AUCUNE">Sans anomalie</option>
              </select>
            </label>
            <label>Champ
              <select [(ngModel)]="fChamp" name="f_champ">
                <option value="">Tous</option>
                @for (c of champs(); track c) { <option [value]="c">{{ c }}</option> }
              </select>
            </label>
            <label>Racine<input [(ngModel)]="fRacine" name="f_racine" maxlength="6" /></label>
            <div style="display:flex;align-items:end;gap:0.4rem">
              <button type="submit" class="bea-mg__btn bea-mg__btn--ghost"><mat-icon>filter_list</mat-icon> Filtrer</button>
            </div>
          </form>
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table">
              <thead><tr><th>Racine</th><th>Ligne</th>@for (c of x.colonnes.slice(1); track c) { <th>{{ c }}</th> }<th>Anomalies</th></tr></thead>
              <tbody>
                @for (l of lignes()?.items ?? []; track l.racine) {
                  <tr>
                    <td><a [routerLink]="['/clientele/clients', l.racine]">{{ l.racine }}</a></td>
                    <td><span class="bea-cl-badge" [attr.data-s]="l.gravite_max === 'BLOQUANTE' ? 'A_CONTROLER' : 'VALIDEE'">{{ l.gravite_max === 'BLOQUANTE' ? 'Incomplète' : 'Complète' }}</span></td>
                    @for (v of l.valeurs.slice(1); track $index) { <td>{{ v ?? '—' }}</td> }
                    <td>
                      <ul class="bea-cl-anoms" style="margin:0">
                        @for (a of l.anomalies; track $index) {
                          <li [attr.data-n]="a.gravite === 'BLOQUANTE' ? 'bloquant' : (a.gravite === 'A_CORRIGER' ? 'alerte' : 'info')">
                            <strong>{{ a.champ }}</strong> ({{ gravites[a.gravite] }}){{ a.valeur ? ' « ' + a.valeur + ' »' : '' }} : {{ a.motif }}
                            <br /><span class="bea-cl-hint">→ {{ a.action }}</span>
                          </li>
                        }
                      </ul>
                    </td>
                  </tr>
                } @empty {
                  <tr><td [attr.colspan]="x.colonnes.length + 2"><div class="bea-cl-empty">Aucun client pour ces filtres.</div></td></tr>
                }
              </tbody>
            </table>
          </div>
          <div class="bea-cl-filters" style="justify-content:flex-end">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() <= 1" (click)="allerPage(page() - 1)"><mat-icon>chevron_left</mat-icon></button>
            <span class="bea-cl-hint" style="align-self:center">Page {{ page() }} / {{ pages() }}</span>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() >= pages()" (click)="allerPage(page() + 1)"><mat-icon>chevron_right</mat-icon></button>
          </div>
        </section>

        <bea-cl-bcm-regles registre="SIC" [appliquees]="x.regles" (decidee)="charger()" />
      } @else {
        <div class="bea-cl-empty">Chargement…</div>
      }
    </div>
  `,
})
export class ClSicDetailComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ClienteleStore);
  private readonly route = inject(ActivatedRoute);
  readonly d = signal<SicDetail | null>(null);
  readonly lignes = signal<Lignes | null>(null);
  readonly page = signal(1);
  readonly busy = signal(false);
  readonly taille = 50;
  readonly pages = computed(() => Math.max(1, Math.ceil((this.lignes()?.total ?? 0) / this.taille)));
  readonly champs = computed(() => [...new Set((this.d()?.synthese_anomalies ?? []).map((s) => s.champ))].sort());
  readonly etapeCourante = computed(() => {
    const s = this.d()?.statut ?? 'BROUILLON';
    return ETAPES.findIndex((e) => e.split('|').includes(s));
  });
  readonly dateFr = dateFr;
  readonly dateHeureFr = dateHeureFr;
  readonly badge = BADGE_SIC;
  readonly resultats = RESULTATS_DEPOT;
  readonly resultatsListe = Object.entries(RESULTATS_DEPOT);
  readonly gravites = GRAVITES;
  readonly gravitesListe = Object.entries(GRAVITES);
  readonly etapes = ETAPES;
  readonly libellesEtapes = LIBELLES_ETAPES;
  fStatut = '';
  fGravite = '';
  fChamp = '';
  fRacine = '';
  depotLe = new Date().toISOString().slice(0, 10);
  depotResultat = 'ACCEPTE';
  depotCommentaire = '';

  ngOnInit(): void {
    this.store.charger();
    this.route.paramMap.subscribe(() => this.charger());
  }

  id(): string {
    return this.route.snapshot.paramMap.get('id') ?? '';
  }

  charger(): void {
    this.api.get<SicDetail>(`${CL_BASE}/sic/${this.id()}`).subscribe({
      next: (d) => {
        this.d.set(d);
        this.chargerLignes();
      },
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Déclaration SIC indisponible')),
    });
  }

  chargerLignes(): void {
    const params: Record<string, string | number> = { page: this.page(), taille: this.taille };
    if (this.fStatut) params['statut'] = this.fStatut;
    if (this.fGravite) params['gravite'] = this.fGravite;
    if (this.fChamp) params['champ'] = this.fChamp;
    if (this.fRacine.trim()) params['racine'] = this.fRacine.trim();
    this.api.get<Lignes>(`${CL_BASE}/sic/${this.id()}/lignes`, params).subscribe({
      next: (l) => this.lignes.set(l),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Lignes indisponibles')),
    });
  }

  allerPage(p: number): void {
    this.page.set(p);
    this.chargerLignes();
  }

  filtrerChamp(champ: string, gravite: string): void {
    this.fChamp = champ;
    this.fGravite = gravite;
    this.fStatut = '';
    this.page.set(1);
    this.chargerLignes();
  }

  dateEtape(i: number): string {
    const x = this.d();
    if (!x) return '';
    const dates = [x.created_at, x.controlee_le, x.validee_le, x.generee_le, x.depot_saisi_le];
    return dates[i] ? dateHeureFr(dates[i]) : '';
  }

  private apres(d: SicDetail): void {
    this.d.set(d);
    this.page.set(1);
    this.chargerLignes();
  }

  controler(): void {
    this.feedback.run(() => this.api.post<SicDetail>(`${CL_BASE}/sic/${this.id()}/controler`, {}), {
      busy: this.busy,
      loading: 'Contrôle des clients…',
      success: (d) => ({ title: 'Contrôle terminé', message: `${d.nb_lignes} client(s) à exporter, dont ${d.nb_incompletes} incomplet(s).` }),
      errorTitle: 'Contrôle impossible',
    }).subscribe((d) => this.apres(d));
  }

  valider(): void {
    const x = this.d()!;
    this.feedback.runWithReason((commentaire) => this.api.post<SicDetail>(`${CL_BASE}/sic/${x.id}/valider`, { commentaire }), {
      reason: {
        title: 'Valider pour export',
        message: x.nb_incompletes
          ? `${x.nb_lignes} client(s) seront exportés, dont ${x.nb_incompletes} avec des cellules vides (listés dans le rapport d’anomalies).`
          : `${x.nb_lignes} client(s) seront exportés.`,
        hint: 'Après validation, les lignes ne sont plus recalculées.',
        reasonLabel: 'Commentaire de validation (facultatif)',
        required: false,
      },
      busy: this.busy,
      loading: 'Validation…',
      success: { title: 'Déclaration validée pour export' },
      errorTitle: 'Validation refusée',
    }).subscribe((d) => this.apres(d));
  }

  generer(): void {
    this.feedback.run(() => this.api.post<SicDetail>(`${CL_BASE}/sic/${this.id()}/generer`, {}), {
      confirm: { action: 'validation', title: 'Générer le fichier SIC', message: 'Le fichier sera généré puis relu et contrôlé (en-têtes, ordre, types, lignes, doublons, valeurs autorisées).' },
      busy: this.busy,
      loading: 'Génération et contrôle du fichier…',
      success: (d) => ({ title: 'Fichier généré et contrôlé', details: [{ label: 'Fichier', value: d.fichier_nom ?? '' }] }),
      errorTitle: 'Génération refusée',
    }).subscribe((d) => this.apres(d));
  }

  deposer(): void {
    const body = { depot_le: this.depotLe, resultat: this.depotResultat, commentaire: this.depotCommentaire || null };
    this.feedback.run(() => this.api.post<SicDetail>(`${CL_BASE}/sic/${this.id()}/depot`, body), {
      confirm: { action: 'enregistrement', title: 'Enregistrer le dépôt SIC', message: `Dépôt du ${dateFr(this.depotLe)} : ${RESULTATS_DEPOT[this.depotResultat]}. Cette saisie est définitive et tracée.` },
      busy: this.busy,
      loading: 'Enregistrement du dépôt…',
      success: { title: 'Dépôt enregistré' },
      errorTitle: 'Enregistrement refusé',
    }).subscribe((d) => this.apres(d));
  }

  telechargerFichier(): void {
    const x = this.d()!;
    this.api.download(`${CL_BASE}/sic/${x.id}/fichier.xlsx`).subscribe({
      next: (b) => telecharger(b, x.fichier_nom ?? 'sic.xlsx'),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Téléchargement impossible')),
    });
  }

  rapport(): void {
    const x = this.d()!;
    this.busy.set(true);
    this.api.download(`${CL_BASE}/sic/${x.id}/anomalies.xlsx`).subscribe({
      next: (b) => {
        this.busy.set(false);
        telecharger(b, `SIC_${x.type}_BEA_${x.date_reference.replaceAll('-', '')}_anomalies.xlsx`);
      },
      error: (e) => {
        this.busy.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Rapport indisponible'));
      },
    });
  }
}
