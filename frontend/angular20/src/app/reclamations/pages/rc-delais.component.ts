import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ReclamationsUiComponent } from '../reclamations-ui.component';
import { AlertesDelais, HistoriqueRegle, RegleDelai, dateFr, tonePriorite, toneStatut } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';

type Mode = 'creer' | 'modifier' | 'version';

interface BrouillonRegle {
  mode: Mode;
  id: string | null;
  libelle: string;
  type_id: string;
  motif_id: string;
  sous_motif_id: string;
  priorite: string;
  duree: number;
  unite_duree: string;
  point_depart: string;
  point_arrivee: string;
  seuil_alerte: number | null;
  delai_service: number | null;
  destinataires: string[];
  date_effet: string;
  date_fin: string;
  commentaire: string;
}

const TON_ETAT: Record<string, string> = {
  APPLIQUEE: 'ACTIF', PROGRAMMEE: 'INFO', EN_ATTENTE_VALIDATION: 'ATTENTION', REJETEE: 'REJETE',
  INACTIVE: 'SUSPENDU', EXPIREE: 'BROUILLON',
};
const ACTIONS: Record<string, string> = {
  'reclamations.delai.create': 'Création', 'reclamations.delai.update': 'Modification',
  'reclamations.delai.validate': 'Décision de validation', 'reclamations.delai.version': 'Nouvelle version',
};

/** Délais & alertes : règles versionnées, validation Conformité, dossiers sans délai, alertes et calendrier. */
@Component({
  selector: 'bea-rc-delais',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, RouterLink, ReclamationsUiComponent],
  template: `
    <bea-rc-styles />
    <section class="bea-mg bea-ct bea-rc">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Management & Qualité · Réclamations</p>
          <h1>Délais & alertes</h1>
          <p class="bea-ct-head__sub">Seules les règles validées par la Conformité calculent une échéance. Une règle en attente n’est jamais appliquée ni présentée comme réglementaire.</p>
        </div>
        <div class="bea-mg__actions">
          @if (store.cap('delais_gerer')) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="appliquerSansDelai()" title="Recalcule les dossiers ouverts sans échéance avec les règles validées">
              <mat-icon>published_with_changes</mat-icon> Appliquer aux dossiers sans délai
            </button>
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="nouvelle()"><mat-icon>add</mat-icon> Nouvelle règle</button>
          }
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger()" title="Actualiser" aria-label="Actualiser"><mat-icon>refresh</mat-icon></button>
        </div>
      </header>

      <div class="bea-rc-note"><mat-icon>gavel</mat-icon>
        <span>Priorité : sous-motif, puis motif, puis type, puis priorité, puis règle générale. Deux règles validées de même portée et de paramètres différents sont en <strong>conflit</strong> : aucune échéance n’est calculée tant que la Conformité n’a pas arbitré. Une échéance déjà calculée n’est jamais recalculée par une nouvelle version. Les alertes ne sont envoyées qu’une fois par niveau (proche, retard).</span>
      </div>

      @if (alertes(); as a) {
        <div class="bea-rc-kpis">
          <a class="bea-rc-kpi" data-tone="danger" routerLink="/reclamations/dossiers" [queryParams]="{ situation_delai: 'EN_RETARD' }"><mat-icon>timer_off</mat-icon><p>En retard</p><strong>{{ a.nb_retards }}</strong></a>
          <a class="bea-rc-kpi" data-tone="warn" routerLink="/reclamations/dossiers" [queryParams]="{ situation_delai: 'ECHEANCE_PROCHE' }"><mat-icon>hourglass_bottom</mat-icon><p>Échéance proche</p><strong>{{ a.nb_alertes }}</strong></a>
          <a class="bea-rc-kpi" routerLink="/reclamations/dossiers" [queryParams]="{ sans_echeance: 'true' }"><mat-icon>schedule</mat-icon><p>Ouverts sans délai</p><strong>{{ a.nb_sans_delai }}</strong></a>
          @for (e of a.sans_delai_par_etat; track e.etat) {
            <a class="bea-rc-kpi" routerLink="/reclamations/dossiers" [queryParams]="{ etat_delai: e.etat, ouvertes: 'true' }"><mat-icon>{{ e.etat === 'CONFLIT' ? 'call_split' : 'help_outline' }}</mat-icon><p>{{ e.libelle }}</p><strong>{{ e.n }}</strong></a>
          }
        </div>

        <div class="bea-rc-grid">
          @for (bloc of blocs(); track bloc.titre) {
            <section class="bea-mg__panel">
              <div class="bea-mg__panel-top"><h2>{{ bloc.titre }} ({{ bloc.n }})</h2></div>
              @if (bloc.items.length) {
                <ul class="bea-rc-mini">
                  @for (d of bloc.items; track d.id) {
                    <li>
                      <a class="bea-rc-mini__row" [routerLink]="['/reclamations/dossiers', d.id]">
                        <code>{{ d.reference }}</code>
                        <span class="bea-rc-mini__obj">{{ d.objet }}</span>
                        @if (bloc.etat) { <span class="bea-ct-badge" data-tone="ATTENTION">{{ d.etat_delai_libelle }}</span> }
                        @else { <span class="bea-ct-badge" [attr.data-tone]="tonePriorite(d.priorite)">{{ d.priorite_libelle }}</span> }
                        <small [class.bea-rc-late]="bloc.late">{{ bloc.etat ? date(d.date_premiere_reception) : date(d.echeance) }}</small>
                      </a>
                    </li>
                  }
                </ul>
              } @else {
                <p class="bea-rc-pad bea-rc-muted">{{ bloc.vide }}</p>
              }
            </section>
          }
        </div>
      }

      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Règles de délai</h2><small class="bea-rc-hint">{{ regles().length }} règle(s)</small></div>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr>
              <th>Libellé</th><th>Portée</th><th>Durée</th><th>Mesure</th><th>Alerte</th><th>Période</th><th>Validation</th><th>État</th><th class="is-num">Dossiers</th><th></th>
            </tr></thead>
            <tbody>
              @for (r of regles(); track r.id) {
                <tr>
                  <td>{{ r.libelle }}
                    @if (r.remplace_id) { <small class="bea-ct-sub">Nouvelle version de « {{ libelleRegle(r.remplace_id) }} »</small> }
                    @if (r.conflits?.length) { <small class="bea-ct-sub bea-rc-late"><mat-icon class="bea-rc-ico-s">call_split</mat-icon> En conflit avec {{ nomsConflits(r) }}</small> }
                  </td>
                  <td>{{ cible(r) }}<small class="bea-ct-sub">Spécificité {{ r.specificite }}</small></td>
                  <td class="is-nowrap">{{ r.duree }} {{ r.unite_duree_libelle }}@if (r.delai_service) { <small class="bea-ct-sub">Service : {{ r.delai_service }}</small> }</td>
                  <td>{{ r.point_depart_libelle }}<small class="bea-ct-sub">→ {{ r.point_arrivee_libelle }}</small></td>
                  <td>{{ r.seuil_alerte ?? '—' }}<small class="bea-ct-sub">{{ r.destinataires_libelles.length ? r.destinataires_libelles.join(', ') : 'SR + service (défaut)' }}</small></td>
                  <td class="is-nowrap">{{ date(r.date_effet) }}<small class="bea-ct-sub">{{ r.date_fin ? 'au ' + date(r.date_fin) : 'sans fin' }}</small></td>
                  <td><span class="bea-ct-badge" [attr.data-tone]="r.reglementaire ? 'ACTIF' : r.statut_validation === 'REJETEE' ? 'REJETE' : 'ATTENTION'">{{ r.statut_validation_libelle }}</span></td>
                  <td><span class="bea-ct-badge" [attr.data-tone]="tonEtat(r.etat_effectif)">{{ r.etat_effectif_libelle }}</span></td>
                  <td class="is-num">
                    @if (r.nb_dossiers) { <span title="Dossiers dont l'échéance a été calculée avec cette règle">{{ r.nb_dossiers }}</span> } @else { 0 }
                  </td>
                  <td class="bea-mg__row-actions is-nowrap">
                    <button type="button" class="bea-mg__icon-btn" title="Historique et versions" (click)="ouvrirHistorique(r)"><mat-icon>history</mat-icon></button>
                    @if (store.cap('delais_gerer')) {
                      @if (!r.nb_dossiers) {
                        <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="editer(r, 'modifier')"><mat-icon>edit</mat-icon></button>
                      }
                      @if (!r.remplacee_par && r.statut_validation !== 'REJETEE') {
                        <button type="button" class="bea-mg__icon-btn" title="Nouvelle version à date d'effet" (click)="editer(r, 'version')"><mat-icon>difference</mat-icon></button>
                      }
                      <button type="button" class="bea-mg__icon-btn" [title]="r.actif ? 'Désactiver' : 'Réactiver'" (click)="basculer(r)">
                        <mat-icon>{{ r.actif ? 'pause' : 'play_arrow' }}</mat-icon>
                      </button>
                    }
                    @if (store.cap('delais_valider') && r.statut_validation !== 'VALIDEE') {
                      <button type="button" class="bea-mg__icon-btn" title="Valider (Conformité)" (click)="valider(r, 'VALIDEE')"><mat-icon>verified</mat-icon></button>
                    }
                    @if (store.cap('delais_valider') && r.statut_validation === 'A_VALIDER') {
                      <button type="button" class="bea-mg__icon-btn" title="Rejeter" (click)="valider(r, 'REJETEE')"><mat-icon>block</mat-icon></button>
                    }
                  </td>
                </tr>
              } @empty {
                <tr><td colspan="10" class="bea-rc-muted">Aucune règle. Tant qu’aucune règle n’est validée, les dossiers restent « Délai non configuré » : aucune échéance n’est inventée.</td></tr>
              }
            </tbody>
          </table>
        </div>
      </section>

      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Jours fériés</h2>
          @if (store.cap('delais_gerer')) {
            <form class="bea-rc-inline" (ngSubmit)="ajouterFerie()">
              <label>Jour <input type="date" [(ngModel)]="ferie.jour" name="ferie_jour" required /></label>
              <label>Libellé <input [(ngModel)]="ferie.libelle" name="ferie_libelle" maxlength="200" required /></label>
              <button type="submit" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()"><mat-icon>add</mat-icon> Ajouter</button>
            </form>
          }
        </div>
        <ul class="bea-rc-feries">
          @for (f of feries(); track f.jour) {
            <li>
              <strong>{{ date(f.jour) }}</strong> {{ f.libelle }}
              @if (store.cap('delais_gerer')) {
                <button type="button" class="bea-mg__icon-btn" title="Retirer" (click)="retirerFerie(f.jour)"><mat-icon>close</mat-icon></button>
              }
            </li>
          } @empty {
            <li class="bea-rc-muted">Aucun jour férié saisi. Les jours ouvrés (lundi–vendredi) ignorent alors seulement les week-ends.</li>
          }
        </ul>
      </section>
    </section>

    @if (brouillon(); as b) {
      <div class="bea-mg__backdrop" (click)="fermer()"></div>
      <form class="bea-mg__modal bea-mg__modal--lg" role="dialog" aria-modal="true" (ngSubmit)="enregistrer()">
        <div class="bea-mg__modal-head">
          <h2>{{ b.mode === 'version' ? 'Nouvelle version de la règle' : b.mode === 'modifier' ? 'Modifier la règle' : 'Nouvelle règle de délai' }}</h2>
          <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermer()"><mat-icon>close</mat-icon></button>
        </div>
        <div class="bea-rc-form">
          @if (b.mode === 'version') {
            <p class="bea-rc-note"><mat-icon>info</mat-icon><span>La version actuelle reste appliquée jusqu’à la veille de la date d’effet, une fois la nouvelle version validée. Les échéances déjà calculées ne changent pas. La portée (type, motif, sous-motif, priorité) est conservée.</span></p>
          }
          <label>Libellé <em>*</em><input [(ngModel)]="b.libelle" name="libelle" maxlength="200" required /></label>
          <div class="bea-rc-row">
            <label>Type
              <select [(ngModel)]="b.type_id" name="type_id" [disabled]="b.mode === 'version'" (ngModelChange)="b.motif_id = ''; b.sous_motif_id = ''">
                <option value="">Tous les types</option>
                @for (t of store.refs('TYPE'); track t.id) { <option [value]="t.id">{{ t.libelle }}</option> }
              </select>
            </label>
            <label>Motif
              <select [(ngModel)]="b.motif_id" name="motif_id" [disabled]="b.mode === 'version'" (ngModelChange)="b.sous_motif_id = ''">
                <option value="">Tous les motifs</option>
                @for (m of b.type_id ? store.enfants('MOTIF', b.type_id) : store.refs('MOTIF'); track m.id) { <option [value]="m.id">{{ m.libelle }}</option> }
              </select>
            </label>
            <label>Sous-motif
              <select [(ngModel)]="b.sous_motif_id" name="sous_motif_id" [disabled]="b.mode === 'version' || !b.motif_id">
                <option value="">Tous les sous-motifs</option>
                @for (s of store.enfants('SOUS_MOTIF', b.motif_id || null); track s.id) { <option [value]="s.id">{{ s.libelle }}</option> }
              </select>
            </label>
            <label>Priorité
              <select [(ngModel)]="b.priorite" name="priorite" [disabled]="b.mode === 'version'">
                <option value="">Toutes</option>
                @for (p of store.libelles('priorites'); track p.code) { <option [value]="p.code">{{ p.libelle }}</option> }
              </select>
            </label>
          </div>
          <div class="bea-rc-row">
            <label>Durée <em>*</em><input type="number" min="1" max="3650" [(ngModel)]="b.duree" name="duree" required /></label>
            <label>Unité
              <select [(ngModel)]="b.unite_duree" name="unite_duree">
                @for (u of store.libelles('unites_duree'); track u.code) { <option [value]="u.code">{{ u.libelle }}</option> }
              </select>
            </label>
            <label>Point de départ
              <select [(ngModel)]="b.point_depart" name="point_depart">
                @for (p of store.libelles('points_depart'); track p.code) { <option [value]="p.code">{{ p.libelle }}</option> }
              </select>
            </label>
            <label>Point d’arrivée
              <select [(ngModel)]="b.point_arrivee" name="point_arrivee">
                @for (p of store.libelles('points_arrivee'); track p.code) { <option [value]="p.code">{{ p.libelle }}</option> }
              </select>
            </label>
          </div>
          <div class="bea-rc-row">
            <label>Seuil d’alerte (même unité, avant l’échéance)<input type="number" min="0" [(ngModel)]="b.seuil_alerte" name="seuil_alerte" /></label>
            <label>Délai du service (même unité)<input type="number" min="1" [(ngModel)]="b.delai_service" name="delai_service" /></label>
          </div>
          <fieldset class="bea-rc-check">
            <legend>Destinataires des alertes</legend>
            @for (d of store.libelles('destinataires_alerte'); track d.code) {
              <label><input type="checkbox" [checked]="b.destinataires.includes(d.code)" (change)="basculerDestinataire(b, d.code)" /> {{ d.libelle }}</label>
            }
            <small class="bea-rc-hint">Aucun coché : Service Réclamations et service destinataire.</small>
          </fieldset>
          <div class="bea-rc-row">
            <label>Date d’effet <em>*</em><input type="date" [(ngModel)]="b.date_effet" name="date_effet" required /></label>
            <label>Date de fin <input type="date" [(ngModel)]="b.date_fin" name="date_fin" /></label>
          </div>
          <label>Commentaire / source (texte réglementaire, décision…) <textarea [(ngModel)]="b.commentaire" name="commentaire" rows="2" maxlength="2000"></textarea></label>
          <p class="bea-rc-hint">Toute création ou modification d’un paramètre de calcul remet la règle « À valider » : elle ne s’applique qu’après validation Conformité.</p>
        </div>
        <div class="bea-mg__modal-foot">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermer()">Annuler</button>
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()"><mat-icon>save</mat-icon> Enregistrer</button>
        </div>
      </form>
    }

    @if (historique(); as h) {
      <div class="bea-mg__backdrop" (click)="historique.set(null)"></div>
      <div class="bea-mg__modal bea-mg__modal--lg" role="dialog" aria-modal="true">
        <div class="bea-mg__modal-head">
          <h2>Historique de la règle</h2>
          <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="historique.set(null)"><mat-icon>close</mat-icon></button>
        </div>
        <div class="bea-rc-form">
          <h3>Versions</h3>
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table">
              <thead><tr><th>Libellé</th><th>Durée</th><th>Période</th><th>Validation</th><th>État</th></tr></thead>
              <tbody>
                @for (v of h.versions; track v.id) {
                  <tr>
                    <td>{{ v.libelle }}</td>
                    <td>{{ v.duree }} {{ v.unite_duree_libelle }}</td>
                    <td>{{ date(v.date_effet) }} → {{ v.date_fin ? date(v.date_fin) : '…' }}</td>
                    <td>{{ v.statut_validation_libelle }}@if (v.valide_le) { <small class="bea-ct-sub">{{ date(v.valide_le) }}</small> }</td>
                    <td><span class="bea-ct-badge" [attr.data-tone]="tonEtat(v.etat_effectif)">{{ v.etat_effectif_libelle }}</span></td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
          <h3>Journal</h3>
          <ul class="bea-rc-mini">
            @for (e of h.evenements; track e.id) {
              <li class="bea-rc-mini__row"><strong>{{ action(e.action) }}</strong><span class="bea-rc-mini__obj">{{ e.auteur || '—' }}</span><small>{{ dateHeure(e.le) }}</small></li>
            } @empty {
              <li class="bea-rc-muted">Aucun événement journalisé.</li>
            }
          </ul>
        </div>
      </div>
    }
  `,
})
export class RcDelaisComponent implements OnInit {
  private readonly rc = inject(ReclamationsService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ReclamationsStore);

  readonly toneStatut = toneStatut;
  readonly tonePriorite = tonePriorite;
  readonly alertes = signal<AlertesDelais | null>(null);
  readonly regles = signal<RegleDelai[]>([]);
  readonly feries = signal<Array<{ jour: string; libelle: string }>>([]);
  readonly brouillon = signal<BrouillonRegle | null>(null);
  readonly historique = signal<HistoriqueRegle | null>(null);
  readonly busy = signal(false);
  ferie = { jour: '', libelle: '' };

  readonly blocs = computed(() => {
    const a = this.alertes();
    if (!a) return [];
    return [
      { titre: 'En retard', n: a.nb_retards, items: a.retards, late: true, etat: false, vide: 'Aucun retard dans votre périmètre.' },
      { titre: 'Échéance proche', n: a.nb_alertes, items: a.alertes, late: false, etat: false, vide: 'Aucune échéance proche.' },
      { titre: 'Ouverts sans délai', n: a.nb_sans_delai, items: a.sans_delai, late: false, etat: true,
        vide: 'Tous les dossiers ouverts ont une échéance.' },
    ];
  });

  ngOnInit(): void {
    this.store.charger();
    this.charger();
  }

  charger(): void {
    this.rc.alertes().subscribe({
      next: (a) => this.alertes.set(a),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Alertes indisponibles')),
    });
    this.rc.regles().subscribe({
      next: (r) => this.regles.set(r),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Règles indisponibles')),
    });
    this.rc.feries().subscribe({
      next: (f) => this.feries.set(f),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Calendrier indisponible')),
    });
  }

  cible(r: RegleDelai): string {
    return [r.type, r.motif, r.sous_motif, r.priorite_libelle].filter(Boolean).join(' · ') || 'Règle générale';
  }

  tonEtat(etat: string): string {
    return TON_ETAT[etat] ?? 'INFO';
  }

  libelleRegle(id: string): string {
    return this.regles().find((g) => g.id === id)?.libelle ?? 'règle précédente';
  }

  nomsConflits(r: RegleDelai): string {
    return (r.conflits ?? []).map((id) => `« ${this.libelleRegle(id)} »`).join(', ');
  }

  action(code: string): string {
    return ACTIONS[code] ?? code;
  }

  date(iso: string | null): string {
    return dateFr(iso);
  }

  dateHeure(iso: string | null): string {
    return dateFr(iso, true);
  }

  nouvelle(): void {
    this.brouillon.set({
      mode: 'creer', id: null, libelle: '', type_id: '', motif_id: '', sous_motif_id: '', priorite: '', duree: 15,
      unite_duree: 'JOURS_CALENDAIRES', point_depart: 'PREMIERE_RECEPTION', point_arrivee: 'CLOTURE',
      seuil_alerte: null, delai_service: null, destinataires: [],
      date_effet: new Date().toISOString().slice(0, 10), date_fin: '', commentaire: '',
    });
  }

  editer(r: RegleDelai, mode: Mode): void {
    this.brouillon.set({
      mode, id: r.id, libelle: r.libelle, type_id: r.type_id ?? '', motif_id: r.motif_id ?? '',
      sous_motif_id: r.sous_motif_id ?? '', priorite: r.priorite ?? '', duree: r.duree, unite_duree: r.unite_duree,
      point_depart: r.point_depart, point_arrivee: r.point_arrivee, seuil_alerte: r.seuil_alerte,
      delai_service: r.delai_service, destinataires: [...r.destinataires],
      date_effet: mode === 'version' ? '' : r.date_effet ?? '', date_fin: mode === 'version' ? '' : r.date_fin ?? '',
      commentaire: mode === 'version' ? '' : r.commentaire ?? '',
    });
  }

  basculerDestinataire(b: BrouillonRegle, code: string): void {
    b.destinataires = b.destinataires.includes(code) ? b.destinataires.filter((d) => d !== code) : [...b.destinataires, code];
  }

  fermer(): void {
    this.brouillon.set(null);
  }

  enregistrer(): void {
    const b = this.brouillon();
    if (!b || !b.libelle.trim() || !b.date_effet || !b.duree) {
      this.feedback.warning({ title: 'Champs obligatoires', message: 'Libellé, durée et date d’effet sont requis.' });
      return;
    }
    const nombre = (v: number | null | undefined) => (v === null || v === undefined || (v as unknown) === '' ? null : Number(v));
    const seuil = nombre(b.seuil_alerte);
    if (seuil !== null && seuil >= Number(b.duree)) {
      this.feedback.warning({ title: 'Seuil d’alerte invalide', message: 'Le seuil doit être inférieur à la durée du délai.' });
      return;
    }
    const corps: Record<string, unknown> = {
      libelle: b.libelle.trim(), duree: Number(b.duree), unite_duree: b.unite_duree,
      point_depart: b.point_depart, point_arrivee: b.point_arrivee, seuil_alerte: seuil,
      delai_service: nombre(b.delai_service), destinataires: b.destinataires,
      date_effet: b.date_effet, date_fin: b.date_fin || null, commentaire: b.commentaire.trim() || null,
    };
    if (b.mode === 'version') {
      Object.assign(corps, { detacher_seuil: seuil === null, detacher_delai_service: !b.delai_service });
    } else {
      Object.assign(corps, {
        type_id: b.type_id || null, motif_id: b.motif_id || null, sous_motif_id: b.sous_motif_id || null,
        priorite: b.priorite || null,
      });
    }
    if (b.mode === 'modifier') {
      Object.assign(corps, {
        detacher_type: !b.type_id, detacher_motif: !b.motif_id, detacher_sous_motif: !b.sous_motif_id,
        detacher_priorite: !b.priorite, detacher_fin: !b.date_fin, detacher_seuil: seuil === null,
        detacher_delai_service: !b.delai_service,
      });
    }
    const appel = b.mode === 'version' && b.id ? this.rc.versionnerRegle(b.id, corps)
      : b.mode === 'modifier' && b.id ? this.rc.modifierRegle(b.id, corps) : this.rc.creerRegle(corps);
    this.feedback
      .run(() => appel, {
        busy: this.busy, loading: 'Enregistrement…',
        success: (r) => ({
          title: b.mode === 'version' ? 'Nouvelle version créée' : b.mode === 'modifier' ? 'Règle mise à jour' : 'Règle créée',
          message: r.reglementaire ? undefined : 'En attente de validation Conformité : aucune échéance n’est calculée avec cette règle pour l’instant.',
        }),
        errorTitle: 'Enregistrement refusé', retry: false,
      })
      .subscribe(() => {
        this.brouillon.set(null);
        this.chargerRegles();
      });
  }

  private chargerRegles(): void {
    this.rc.regles().subscribe({
      next: (r) => this.regles.set(r),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Règles indisponibles')),
    });
  }

  ouvrirHistorique(r: RegleDelai): void {
    this.feedback
      .run(() => this.rc.historiqueRegle(r.id), { busy: this.busy, success: () => null, errorTitle: 'Historique indisponible', retry: false })
      .subscribe((h) => this.historique.set(h));
  }

  basculer(r: RegleDelai): void {
    this.feedback
      .run(() => this.rc.modifierRegle(r.id, { actif: !r.actif }), {
        busy: this.busy,
        success: () => ({ title: r.actif ? 'Règle désactivée' : 'Règle réactivée' }),
        errorTitle: 'Action refusée', retry: false,
      })
      .subscribe(() => this.chargerRegles());
  }

  valider(r: RegleDelai, statut: 'VALIDEE' | 'REJETEE'): void {
    this.feedback
      .run(() => this.rc.validerRegle(r.id, { statut_validation: statut }), {
        confirm: {
          title: statut === 'VALIDEE' ? 'Valider cette règle' : 'Rejeter cette règle',
          message: statut === 'VALIDEE'
            ? 'Après validation, la règle calcule les échéances des nouveaux dossiers à partir de sa date d’effet. Les dossiers déjà ouverts sans délai ne sont mis à jour que par l’action « Appliquer aux dossiers sans délai ».'
            : 'La règle rejetée ne sera jamais appliquée. Elle reste visible dans l’historique.',
          confirmLabel: statut === 'VALIDEE' ? 'Valider' : 'Rejeter',
          tone: statut === 'VALIDEE' ? 'success' : 'warn',
        },
        busy: this.busy,
        success: () => ({ title: statut === 'VALIDEE' ? 'Règle validée' : 'Règle rejetée' }),
        errorTitle: 'Validation refusée', retry: false,
      })
      .subscribe(() => this.chargerRegles());
  }

  appliquerSansDelai(): void {
    this.feedback
      .run(() => this.rc.appliquerDelais(), {
        confirm: {
          title: 'Appliquer les règles validées',
          message: 'Les dossiers ouverts sans échéance seront recalculés avec les règles validées en vigueur. Les échéances existantes ne sont pas modifiées.',
          confirmLabel: 'Appliquer', tone: 'success',
        },
        busy: this.busy, loading: 'Calcul des échéances…',
        success: (r) => ({
          title: `${r.calcules} échéance(s) calculée(s)`,
          message: `${r.examines} dossier(s) examiné(s), ${r.restants} toujours sans délai.`,
        }),
        errorTitle: 'Calcul refusé', retry: false,
      })
      .subscribe(() => this.charger());
  }

  ajouterFerie(): void {
    if (!this.ferie.jour || !this.ferie.libelle.trim()) {
      this.feedback.warning({ title: 'Jour et libellé obligatoires', message: 'Indiquez la date et le nom du jour férié.' });
      return;
    }
    this.feedback
      .run(() => this.rc.ajouterFerie(this.ferie.jour, this.ferie.libelle.trim()), {
        busy: this.busy, success: () => ({ title: 'Jour férié ajouté' }),
        errorTitle: 'Ajout refusé', retry: false,
      })
      .subscribe((l) => {
        this.feries.set(l);
        this.ferie = { jour: '', libelle: '' };
      });
  }

  retirerFerie(jour: string): void {
    this.feedback
      .run(() => this.rc.retirerFerie(jour), {
        confirm: { title: 'Retirer ce jour férié', message: dateFr(jour), confirmLabel: 'Retirer', tone: 'warn' },
        busy: this.busy, success: () => ({ title: 'Jour férié retiré' }),
        errorTitle: 'Retrait refusé', retry: false,
      })
      .subscribe(() => this.feries.update((l) => l.filter((f) => f.jour !== jour)));
  }
}
