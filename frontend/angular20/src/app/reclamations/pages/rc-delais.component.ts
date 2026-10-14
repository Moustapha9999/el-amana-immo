import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ReclamationsUiComponent } from '../reclamations-ui.component';
import { DossierLigne, RegleDelai, dateFr, tonePriorite, toneStatut } from '../reclamations.models';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';

interface BrouillonRegle {
  id: string | null;
  libelle: string;
  type_id: string;
  motif_id: string;
  priorite: string;
  duree: number;
  unite_duree: string;
  point_depart: string;
  seuil_alerte: number | null;
  delai_service: number | null;
  neutraliser_suspension: boolean;
  date_effet: string;
  date_fin: string;
  commentaire: string;
}

/** Délais internes : alertes du périmètre, règles paramétrables, jours fériés. Jamais « réglementaire » avant validation Conformité. */
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
          <p class="bea-ct-head__sub">Règles internes de la banque. Une règle n’est présentée comme réglementaire qu’après validation Conformité.</p>
        </div>
        <div class="bea-mg__actions">
          @if (store.cap('delais_gerer')) {
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="nouvelle()"><mat-icon>add</mat-icon> Nouvelle règle</button>
          }
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger()"><mat-icon>refresh</mat-icon></button>
        </div>
      </header>

      <div class="bea-rc-note"><mat-icon>gavel</mat-icon>
        <span>Sans règle active, aucune échéance n’est calculée. Le job quotidien notifie le SR et le service destinataire des dossiers en retard ou proches du seuil.</span>
      </div>

      <div class="bea-rc-grid">
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>En retard ({{ retards().length }})</h2></div>
          @if (retards().length) {
            <ul class="bea-rc-mini">
              @for (d of retards(); track d.id) {
                <li>
                  <a class="bea-rc-mini__row" [routerLink]="['/reclamations/dossiers', d.id]">
                    <code>{{ d.reference }}</code>
                    <span class="bea-rc-mini__obj">{{ d.objet }}</span>
                    <span class="bea-ct-badge" [attr.data-tone]="toneStatut(d.statut)">{{ d.statut_libelle }}</span>
                    <small class="bea-rc-late">{{ date(d.echeance) }}</small>
                  </a>
                </li>
              }
            </ul>
          } @else {
            <p class="bea-rc-pad bea-rc-muted">Aucun retard dans votre périmètre.</p>
          }
        </section>
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Seuil d’alerte ({{ alertes().length }})</h2></div>
          @if (alertes().length) {
            <ul class="bea-rc-mini">
              @for (d of alertes(); track d.id) {
                <li>
                  <a class="bea-rc-mini__row" [routerLink]="['/reclamations/dossiers', d.id]">
                    <code>{{ d.reference }}</code>
                    <span class="bea-rc-mini__obj">{{ d.objet }}</span>
                    <span class="bea-ct-badge" [attr.data-tone]="tonePriorite(d.priorite)">{{ d.priorite_libelle }}</span>
                    <small>{{ date(d.echeance) }}</small>
                  </a>
                </li>
              }
            </ul>
          } @else {
            <p class="bea-rc-pad bea-rc-muted">Aucune échéance proche.</p>
          }
        </section>
      </div>

      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Règles de délai</h2></div>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead><tr>
              <th>Libellé</th><th>Cible</th><th>Durée</th><th>Départ</th><th>Alerte</th><th>Validation</th><th>État</th>
              @if (store.cap('delais_gerer') || store.cap('delais_valider')) { <th></th> }
            </tr></thead>
            <tbody>
              @for (r of regles(); track r.id) {
                <tr>
                  <td>{{ r.libelle }}@if (r.commentaire) { <small class="bea-ct-sub">{{ r.commentaire }}</small> }</td>
                  <td>{{ cible(r) }}</td>
                  <td>{{ r.duree }} {{ r.unite_duree_libelle }}@if (r.delai_service) { <small class="bea-ct-sub">Service : {{ r.delai_service }} j</small> }</td>
                  <td>{{ r.point_depart_libelle }}</td>
                  <td>{{ r.seuil_alerte ?? '—' }}</td>
                  <td>
                    <span class="bea-ct-badge" [attr.data-tone]="r.reglementaire ? 'ACTIF' : 'ATTENTION'">{{ r.statut_validation_libelle }}</span>
                  </td>
                  <td><span class="bea-ct-badge" [attr.data-tone]="r.actif ? 'ACTIF' : 'SUSPENDU'">{{ r.actif ? 'Active' : 'Inactive' }}</span></td>
                  @if (store.cap('delais_gerer') || store.cap('delais_valider')) {
                    <td class="bea-mg__row-actions">
                      @if (store.cap('delais_gerer')) {
                        <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="editer(r)"><mat-icon>edit</mat-icon></button>
                        <button type="button" class="bea-mg__icon-btn" [title]="r.actif ? 'Désactiver' : 'Réactiver'" (click)="basculer(r)">
                          <mat-icon>{{ r.actif ? 'pause' : 'play_arrow' }}</mat-icon>
                        </button>
                      }
                      @if (store.cap('delais_valider') && r.statut_validation !== 'VALIDEE') {
                        <button type="button" class="bea-mg__icon-btn" title="Valider (Conformité)" (click)="valider(r, 'VALIDEE')"><mat-icon>verified</mat-icon></button>
                      }
                      @if (store.cap('delais_valider') && r.statut_validation !== 'REJETEE') {
                        <button type="button" class="bea-mg__icon-btn" title="Rejeter" (click)="valider(r, 'REJETEE')"><mat-icon>block</mat-icon></button>
                      }
                    </td>
                  }
                </tr>
              } @empty {
                <tr><td colspan="8" class="bea-rc-muted">Aucune règle. Tant qu’aucune n’est créée, les dossiers n’ont pas d’échéance.</td></tr>
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
            <li class="bea-rc-muted">Aucun jour férié saisi. Les jours ouvrés ignorent seulement les week-ends.</li>
          }
        </ul>
      </section>
    </section>

    @if (brouillon(); as b) {
      <div class="bea-mg__backdrop" (click)="fermer()"></div>
      <form class="bea-mg__modal bea-mg__modal--lg" role="dialog" aria-modal="true" (ngSubmit)="enregistrer()">
        <div class="bea-mg__modal-head">
          <h2>{{ b.id ? 'Modifier la règle' : 'Nouvelle règle de délai' }}</h2>
          <button type="button" class="bea-ct-view__close" aria-label="Fermer" (click)="fermer()"><mat-icon>close</mat-icon></button>
        </div>
        <div class="bea-rc-form">
          <label>Libellé <em>*</em><input [(ngModel)]="b.libelle" name="libelle" maxlength="200" required /></label>
          <div class="bea-rc-row">
            <label>Type
              <select [(ngModel)]="b.type_id" name="type_id" (ngModelChange)="b.motif_id = ''">
                <option value="">Tous les types</option>
                @for (t of store.refs('TYPE'); track t.id) { <option [value]="t.id">{{ t.libelle }}</option> }
              </select>
            </label>
            <label>Motif
              <select [(ngModel)]="b.motif_id" name="motif_id">
                <option value="">Tous les motifs</option>
                @for (m of store.enfants('MOTIF', b.type_id || null); track m.id) { <option [value]="m.id">{{ m.libelle }}</option> }
              </select>
            </label>
            <label>Priorité
              <select [(ngModel)]="b.priorite" name="priorite">
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
          </div>
          <div class="bea-rc-row">
            <label>Seuil d’alerte (jours)<input type="number" min="0" [(ngModel)]="b.seuil_alerte" name="seuil_alerte" /></label>
            <label>Délai service (jours)<input type="number" min="1" [(ngModel)]="b.delai_service" name="delai_service" /></label>
            <label class="bea-rc-check"><input type="checkbox" [(ngModel)]="b.neutraliser_suspension" name="neutraliser" /> Neutraliser la suspension (décale l’échéance)</label>
          </div>
          <div class="bea-rc-row">
            <label>Date d’effet <em>*</em><input type="date" [(ngModel)]="b.date_effet" name="date_effet" required /></label>
            <label>Date de fin <input type="date" [(ngModel)]="b.date_fin" name="date_fin" /></label>
          </div>
          <label>Commentaire <textarea [(ngModel)]="b.commentaire" name="commentaire" rows="2"></textarea></label>
        </div>
        <div class="bea-mg__modal-foot">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fermer()">Annuler</button>
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy()"><mat-icon>save</mat-icon> Enregistrer</button>
        </div>
      </form>
    }
  `,
})
export class RcDelaisComponent implements OnInit {
  private readonly rc = inject(ReclamationsService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ReclamationsStore);

  readonly toneStatut = toneStatut;
  readonly tonePriorite = tonePriorite;
  readonly retards = signal<DossierLigne[]>([]);
  readonly alertes = signal<DossierLigne[]>([]);
  readonly regles = signal<RegleDelai[]>([]);
  readonly feries = signal<Array<{ jour: string; libelle: string }>>([]);
  readonly brouillon = signal<BrouillonRegle | null>(null);
  readonly busy = signal(false);
  ferie = { jour: '', libelle: '' };

  ngOnInit(): void {
    this.store.charger();
    this.charger();
  }

  charger(): void {
    this.rc.alertes().subscribe({
      next: (a) => {
        this.retards.set(a.retards);
        this.alertes.set(a.alertes);
      },
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
    return [r.type, r.motif, r.priorite_libelle].filter(Boolean).join(' · ') || 'Règle générale';
  }

  date(iso: string | null): string {
    return dateFr(iso);
  }

  nouvelle(): void {
    this.brouillon.set({
      id: null, libelle: '', type_id: '', motif_id: '', priorite: '', duree: 15,
      unite_duree: 'JOURS_CALENDAIRES', point_depart: 'PREMIERE_RECEPTION',
      seuil_alerte: 3, delai_service: null, neutraliser_suspension: true,
      date_effet: new Date().toISOString().slice(0, 10), date_fin: '', commentaire: '',
    });
  }

  editer(r: RegleDelai): void {
    this.brouillon.set({
      id: r.id, libelle: r.libelle, type_id: r.type_id ?? '', motif_id: r.motif_id ?? '',
      priorite: r.priorite ?? '', duree: r.duree, unite_duree: r.unite_duree,
      point_depart: r.point_depart, seuil_alerte: r.seuil_alerte, delai_service: r.delai_service,
      neutraliser_suspension: r.neutraliser_suspension, date_effet: r.date_effet ?? '',
      date_fin: r.date_fin ?? '', commentaire: r.commentaire ?? '',
    });
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
    const corps = {
      libelle: b.libelle.trim(), type_id: b.type_id || null, motif_id: b.motif_id || null,
      priorite: b.priorite || null, duree: Number(b.duree), unite_duree: b.unite_duree,
      point_depart: b.point_depart, seuil_alerte: b.seuil_alerte === null || b.seuil_alerte === undefined ? null : Number(b.seuil_alerte),
      delai_service: b.delai_service ? Number(b.delai_service) : null,
      neutraliser_suspension: b.neutraliser_suspension, date_effet: b.date_effet,
      date_fin: b.date_fin || null, commentaire: b.commentaire.trim() || null,
      detacher_type: !b.type_id, detacher_motif: !b.motif_id, detacher_priorite: !b.priorite,
      detacher_fin: !b.date_fin,
    };
    const appel = b.id ? this.rc.modifierRegle(b.id, corps) : this.rc.creerRegle(corps);
    this.feedback
      .run(() => appel, {
        busy: this.busy, loading: 'Enregistrement…',
        success: () => ({ title: b.id ? 'Règle mise à jour' : 'Règle créée' }),
        errorTitle: 'Enregistrement refusé', retry: false,
      })
      .subscribe((r) => {
        this.regles.update((l) => {
          const i = l.findIndex((x) => x.id === r.id);
          if (i < 0) return [r, ...l];
          const n = [...l];
          n[i] = r;
          return n;
        });
        this.brouillon.set(null);
      });
  }

  basculer(r: RegleDelai): void {
    this.feedback
      .run(() => this.rc.modifierRegle(r.id, { actif: !r.actif }), {
        busy: this.busy,
        success: () => ({ title: r.actif ? 'Règle désactivée' : 'Règle réactivée' }),
        errorTitle: 'Action refusée', retry: false,
      })
      .subscribe((n) => this.regles.update((l) => l.map((x) => (x.id === n.id ? n : x))));
  }

  valider(r: RegleDelai, statut: 'VALIDEE' | 'REJETEE'): void {
    this.feedback
      .run(() => this.rc.validerRegle(r.id, { statut_validation: statut }), {
        confirm: {
          title: statut === 'VALIDEE' ? 'Valider cette règle' : 'Rejeter cette règle',
          message: statut === 'VALIDEE'
            ? 'Après validation, cette règle pourra être présentée comme réglementaire.'
            : 'La règle reste utilisable en interne mais ne sera pas réglementaire.',
          confirmLabel: statut === 'VALIDEE' ? 'Valider' : 'Rejeter',
          tone: statut === 'VALIDEE' ? 'success' : 'warn',
        },
        busy: this.busy,
        success: () => ({ title: statut === 'VALIDEE' ? 'Règle validée' : 'Règle rejetée' }),
        errorTitle: 'Validation refusée', retry: false,
      })
      .subscribe((n) => this.regles.update((l) => l.map((x) => (x.id === n.id ? n : x))));
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
