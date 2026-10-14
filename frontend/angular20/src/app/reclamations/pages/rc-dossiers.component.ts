import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ReclamationsUiComponent } from '../reclamations-ui.component';
import { DossierLigne, Page, dateFr, montantFr, toneStatut, tonePriorite } from '../reclamations.models';
import { Filtres, ReclamationsService, ReclamationsStore } from '../reclamations.service';
import { RcExportComponent } from '../shared/rc-export.component';
import { optionsRestauration, optionsSuppression } from '../shared/rc-suppression';

const ANNULABLES = new Set(['A_QUALIFIER', 'A_AFFECTER', 'REOUVERTE']);

const TAILLE = 25;
const TRIS = new Set(['reference', 'date_reclamation', 'date_premiere_reception', 'date_reception_sr', 'statut', 'priorite', 'client_nom', 'updated_at']);
const CHAMPS = ['q', 'groupe', 'statut', 'etape', 'type_id', 'motif_id', 'canal_id', 'priorite', 'client_categorie',
  'client_agence_id', 'unite_reception_id', 'unite_concernee_id', 'unite_traitement_id', 'date_debut', 'date_fin',
  'indicateur', 'kpi_debut', 'kpi_fin', 'kpi_unite_id'] as const;
const KPI = ['indicateur', 'kpi_debut', 'kpi_fin', 'kpi_unite_id'] as const;

const DELAIS: Record<string, string> = {
  prise_en_charge: 'délai de prise en charge', traitement_service: 'délai de traitement du service',
  reponse_client: 'délai de réponse au client', cloture: 'délai de clôture',
};
const MODES: Record<string, string> = {
  termines: 'mesurés (terminés)', en_cours: 'en cours', anomalies: 'durée négative (anomalie de saisie)',
};
const INDICATEURS: Record<string, string> = {
  clotures: 'Clôturés sur la période', reouvertes: 'Clôturés puis réouverts sur la période',
  service_affectes: 'Affectés au service sur la période', service_en_cours: 'En cours chez le service',
  service_retournes: 'Retournés par le service sur la période',
  avec_operations: 'Dossiers avec opérations contestées',
};

function libelleIndicateur(code: string): string {
  const m = /^delai_(.+)_(termines|en_cours|anomalies)$/.exec(code);
  if (m && DELAIS[m[1]]) return `Dossiers du ${DELAIS[m[1]]} — ${MODES[m[2]]}`;
  return INDICATEURS[code] ?? code;
}
const BOOLEENS = ['ouvertes', 'archivees', 'corbeille'] as const;

interface VueListe {
  titre: string;
  sous: string;
  etape?: string;
  ouvertes?: boolean;
  archivees?: boolean;
}

const VUES: Record<string, VueListe> = {
  'a-traiter': {
    titre: 'Mes dossiers à traiter',
    sous: 'Dossiers transmis à un service, dans votre périmètre.',
    etape: 'TRAITEMENT', ouvertes: true,
  },
  archives: {
    titre: 'Archives & documents',
    sous: 'Dossiers archivés de votre périmètre.',
    archivees: true,
  },
  services: {
    titre: 'Services & affectations',
    sous: 'Dossiers actuellement chez un service destinataire.',
    etape: 'TRAITEMENT',
  },
};

/** Liste des réclamations : filtres, tri, pagination et comptage appliqués par le serveur, dans le périmètre de l'agent. */
@Component({
  selector: 'bea-rc-dossiers',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule, ReclamationsUiComponent, RcExportComponent],
  template: `
    <bea-rc-styles />
    <section class="bea-mg bea-ct bea-rc">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Management & Qualité · Réclamations</p>
          <h1>{{ corbeille() ? 'Corbeille — réclamations supprimées' : vue()?.titre ?? 'Réclamations' }}</h1>
          <p class="bea-ct-head__sub">
            {{ corbeille() ? 'Dossiers retirés des listes, indicateurs et exports. Opérations, pièces et historique sont conservés : un dossier se restaure à l’identique.'
              : vue()?.sous ?? 'Filtres, tri et pagination appliqués par le serveur, dans la limite de votre périmètre.' }}
            @if (store.config()?.acces?.perimetre === 'UNITES') { <span class="bea-ct-badge" data-tone="ATTENTION">Périmètre : vos unités</span> }
            @if (store.config()?.acces?.perimetre === 'PERSONNEL') { <span class="bea-ct-badge" data-tone="ATTENTION">Périmètre : vos saisies</span> }
          </p>
        </div>
        <div class="bea-mg__actions">
          @if (store.cap('creer') && !vue() && !corbeille()) {
            <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/reclamations/dossiers/nouvelle"><mat-icon>add_comment</mat-icon> Nouvelle réclamation</a>
          }
          @if (store.cap('supprimer') && !vue()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [class.is-on]="corbeille()" (click)="basculerCorbeille()">
              <mat-icon>{{ corbeille() ? 'list' : 'delete_sweep' }}</mat-icon> {{ corbeille() ? 'Réclamations actives' : 'Corbeille' }}
            </button>
          }
          @if (!corbeille()) { <bea-rc-export [filtres]="courant()" /> }
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" title="Actualiser" (click)="charger()"><mat-icon>refresh</mat-icon></button>
        </div>
      </header>

      <form class="bea-mg__search bea-ct-filters bea-rc-filters" [formGroup]="filtres" (ngSubmit)="appliquer()">
        <label class="bea-mg__field bea-ct-filters__q">Recherche
          <input formControlName="q" placeholder="Référence, objet, client, racine, compte, opération" maxlength="100" />
        </label>
        <label class="bea-mg__field">Statut simplifié
          <select formControlName="groupe" (change)="filtres.controls.statut.setValue(''); appliquer()">
            <option value="">Tous</option>
            @for (g of store.libelles('groupes'); track g.code) { <option [value]="g.code">{{ g.libelle }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Statut détaillé
          <select formControlName="statut" (change)="filtres.controls.groupe.setValue(''); appliquer()">
            <option value="">Tous</option>
            @for (s of store.libelles('statuts'); track s.code) { <option [value]="s.code">{{ s.libelle }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Étape
          <select formControlName="etape" (change)="appliquer()">
            <option value="">Toutes</option>
            @for (e of store.libelles('etapes'); track e.code) { <option [value]="e.code">{{ e.libelle }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Type
          <select formControlName="type_id" (change)="filtres.controls.motif_id.setValue(''); appliquer()">
            <option value="">Tous</option>
            @for (t of store.refs('TYPE', true); track t.id) { <option [value]="t.id">{{ t.libelle }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Motif
          <select formControlName="motif_id" (change)="appliquer()">
            <option value="">Tous</option>
            @for (m of motifs(); track m.id) { <option [value]="m.id">{{ m.libelle }}</option> }
            <option value="AUTRE">Autre (saisie libre)</option>
          </select>
        </label>
        <label class="bea-mg__field">Canal
          <select formControlName="canal_id" (change)="appliquer()">
            <option value="">Tous</option>
            @for (c of store.refs('CANAL', true); track c.id) { <option [value]="c.id">{{ c.libelle }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Priorité
          <select formControlName="priorite" (change)="appliquer()">
            <option value="">Toutes</option>
            @for (p of store.libelles('priorites'); track p.code) { <option [value]="p.code">{{ p.libelle }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Catégorie client
          <select formControlName="client_categorie" (change)="appliquer()">
            <option value="">Toutes</option>
            @for (c of store.libelles('categories_client'); track c.code) { <option [value]="c.code">{{ c.libelle }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Agence
          <select formControlName="client_agence_id" (change)="appliquer()">
            <option value="">Toutes</option>
            <option value="AUCUNE">Sans agence</option>
            @for (a of store.config()?.agences ?? []; track a.id) { <option [value]="a.id">{{ a.code }} — {{ a.libelle }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Service concerné
          <select formControlName="unite_concernee_id" (change)="appliquer()">
            <option value="">Tous</option>
            @for (u of store.unites(); track u.id) {
              @if (!u.est_service_reclamations) { <option [value]="u.id">{{ u.libelle }}</option> }
            }
          </select>
        </label>
        <label class="bea-mg__field">Unité de réception
          <select formControlName="unite_reception_id" (change)="appliquer()">
            <option value="">Toutes</option>
            @for (u of store.unites(); track u.id) { <option [value]="u.id">{{ u.libelle }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Reçue du
          <input type="date" formControlName="date_debut" (change)="appliquer()" />
        </label>
        <label class="bea-mg__field">au
          <input type="date" formControlName="date_fin" (change)="appliquer()" />
        </label>
        <label class="bea-rc-toggle"><input type="checkbox" formControlName="ouvertes" (change)="appliquer()" /> En cours uniquement</label>
        <div class="bea-ct-filters__btns">
          <button type="submit" class="bea-mg__btn bea-mg__btn--ghost"><mat-icon>search</mat-icon> Filtrer</button>
          @if (filtresActifs()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="reinitialiser()">Réinitialiser</button>
          }
        </div>
      </form>

      @if (indicateur(); as ind) {
        <div class="bea-rc-note"><mat-icon>insights</mat-icon>
          <span>Indicateur : <strong>{{ ind.libelle }}</strong>{{ ind.periode }}{{ nomUnite(ind.uniteId) }}</span>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="retirerIndicateur()"><mat-icon>close</mat-icon> Retirer</button>
        </div>
      }

      @if (erreur()) {
        <div class="bea-ct-empty bea-ct-empty--hero"><mat-icon>cloud_off</mat-icon>
          <p>Impossible de charger les réclamations.</p>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger()"><mat-icon>refresh</mat-icon> Réessayer</button>
        </div>
      } @else {
        <div class="bea-mg__table-scroll bea-ct-table-wrap">
          <table class="bea-mg__table bea-ct-table bea-rc-liste">
            <thead>
              <tr>
                <th><button type="button" class="bea-rc-sort" (click)="trier('reference')">Référence {{ fleche('reference') }}</button></th>
                <th><button type="button" class="bea-rc-sort" (click)="trier('date_reclamation')">Date {{ fleche('date_reclamation') }}</button></th>
                <th><button type="button" class="bea-rc-sort" (click)="trier('client_nom')">Client {{ fleche('client_nom') }}</button></th>
                <th>Objet</th>
                <th>Motif / sous-motif</th>
                <th class="is-num">Opérations</th>
                <th class="is-num">Montant total</th>
                <th>Service</th>
                <th>Étape</th>
                <th><button type="button" class="bea-rc-sort" (click)="trier('statut')">Statut {{ fleche('statut') }}</button></th>
                <th class="is-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (d of lignes(); track d.id; let i = $index) {
                <tr class="bea-ct-row bea-rc-clic" [style.animation-delay.ms]="i < 20 ? i * 30 : 0" (click)="ouvrir(d, $event)">
                  <td class="is-nowrap">
                    <a class="bea-ct-link" [routerLink]="['/reclamations/dossiers', d.id]"><code class="bea-mg__code">{{ d.reference }}</code></a>
                    @if (d.nb_documents) { <small class="bea-ct-sub">{{ d.nb_documents }} pièce{{ d.nb_documents > 1 ? 's' : '' }}</small> }
                    @if (d.supprimee_le) {
                      <small class="bea-ct-sub bea-rc-late" [title]="d.motif_suppression ?? ''">Supprimée le {{ date(d.supprimee_le) }}</small>
                    }
                  </td>
                  <td class="is-nowrap" [title]="d.canal ?? ''">{{ date(d.date_reclamation ?? d.date_premiere_reception) }}</td>
                  <td class="is-wide">
                    <strong class="bea-ct-strong">{{ d.client_nom || '—' }}</strong>
                    @if (d.client_racine) { <small class="bea-ct-sub">Racine {{ d.client_racine }}</small> }
                  </td>
                  <td class="is-wide">{{ d.objet }}<small class="bea-ct-sub">{{ d.type || 'Non qualifiée' }}</small></td>
                  <td class="is-wide">{{ d.motif || '—' }}@if (d.sous_motif) { <small class="bea-ct-sub">{{ d.sous_motif }}</small> }</td>
                  <td class="is-num">{{ d.nb_operations || '—' }}</td>
                  <td class="is-num is-nowrap">{{ d.nb_operations ? montant(d.montant_total, d.devise) : '—' }}</td>
                  <td class="is-wide">{{ d.unite_traitement || d.unite_concernee || '—' }}</td>
                  <td class="is-nowrap">{{ d.etape_libelle }}</td>
                  <td class="is-nowrap">
                    <span class="bea-ct-badge" [attr.data-tone]="toneStatut(d.statut)">{{ d.statut_libelle }}</span>
                    @if (d.priorite !== 'NORMALE') { <span class="bea-ct-badge" [attr.data-tone]="tonePriorite(d.priorite)">{{ d.priorite_libelle }}</span> }
                  </td>
                  <td class="bea-mg__actions-cell is-nowrap">
                    <a class="bea-mg__icon-btn" [routerLink]="['/reclamations/dossiers', d.id]" title="Consulter la fiche" aria-label="Consulter la fiche"><mat-icon>visibility</mat-icon></a>
                    @if (d.supprimee_le) {
                      @if (d.suppression?.restaurable) {
                        <button type="button" class="bea-mg__icon-btn" [disabled]="actionBusy()" (click)="restaurer(d)" title="Restaurer le dossier" aria-label="Restaurer"><mat-icon>restore_from_trash</mat-icon></button>
                      }
                    } @else {
                      @if (peutModifier(d)) {
                        <a class="bea-mg__icon-btn" [routerLink]="['/reclamations/dossiers', d.id]" [queryParams]="{ edition: 1 }" title="Modifier" aria-label="Modifier"><mat-icon>edit</mat-icon></a>
                      }
                      @if (peutAnnuler(d)) {
                        <button type="button" class="bea-mg__icon-btn bea-rc-warn" [disabled]="actionBusy()" (click)="annuler(d)" title="Annuler le dossier (statut « Annulée »)" aria-label="Annuler"><mat-icon>block</mat-icon></button>
                      }
                      @if (d.suppression; as sup) {
                        <button type="button" class="bea-mg__icon-btn bea-rc-danger" [disabled]="actionBusy() || !sup.possible" (click)="supprimer(d)"
                                [title]="sup.possible ? 'Supprimer (corbeille, restaurable)' : 'Suppression impossible : ' + sup.raison" aria-label="Supprimer"><mat-icon>delete</mat-icon></button>
                      }
                    }
                  </td>
                </tr>
              } @empty {
                <tr><td colspan="11"><div class="bea-ct-empty"><mat-icon>forum</mat-icon>
                  <p>{{ chargement() ? 'Chargement…' : corbeille() ? 'La corbeille est vide.' : filtresActifs() ? 'Aucune réclamation ne correspond aux filtres.' : 'Aucune réclamation dans votre périmètre.' }}</p>
                </div></td></tr>
              }
            </tbody>
          </table>
        </div>

        @if (total() > 0) {
          <div class="bea-rc-pager">
            <p class="bea-ct-count">{{ debut() }}–{{ fin() }} sur {{ total() }} réclamation{{ total() > 1 ? 's' : '' }}
              @if (totaux(); as t) { · {{ t.nb_operations }} opération(s) dans {{ t.dossiers_avec_operations }} dossier(s) · {{ montant(t.montant_total, t.devise) }} }
            </p>
            <div class="bea-mg__actions">
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() <= 1" (click)="allerPage(page() - 1)"><mat-icon>chevron_left</mat-icon> Précédent</button>
              <span class="bea-rc-pager__num">Page {{ page() }} / {{ pages() }}</span>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() >= pages()" (click)="allerPage(page() + 1)">Suivant <mat-icon>chevron_right</mat-icon></button>
            </div>
          </div>
        }
      }
    </section>
  `,
})
export class RcDossiersComponent implements OnInit {
  private readonly rc = inject(ReclamationsService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  readonly store = inject(ReclamationsStore);

  readonly toneStatut = toneStatut;
  readonly tonePriorite = tonePriorite;
  readonly filtres = this.fb.nonNullable.group({
    q: '', groupe: '', statut: '', etape: '', type_id: '', motif_id: '', canal_id: '', priorite: '', client_categorie: '',
    client_agence_id: '', unite_reception_id: '', unite_concernee_id: '', unite_traitement_id: '', date_debut: '', date_fin: '',
    indicateur: '', kpi_debut: '', kpi_fin: '', kpi_unite_id: '',
    ouvertes: false, archivees: false, corbeille: false,
  });
  readonly vue = signal<VueListe | null>(null);
  readonly corbeille = signal(false);
  readonly lignes = signal<DossierLigne[]>([]);
  readonly total = signal(0);
  readonly totaux = signal<Page<DossierLigne>['totaux'] | null>(null);
  readonly indicateur = signal<{ libelle: string; periode: string; uniteId: string } | null>(null);
  readonly page = signal(1);
  readonly tri = signal('date_premiere_reception');
  readonly ordre = signal<'asc' | 'desc'>('desc');
  readonly chargement = signal(false);
  readonly erreur = signal(false);
  readonly actionBusy = signal(false);
  readonly courant = signal<Filtres>({});
  readonly filtresActifs = signal(false);
  private readonly typeChoisi = signal('');

  readonly pages = computed(() => Math.max(1, Math.ceil(this.total() / TAILLE)));
  readonly debut = computed(() => (this.page() - 1) * TAILLE + 1);
  readonly fin = computed(() => Math.min(this.page() * TAILLE, this.total()));
  readonly motifs = computed(() => {
    const t = this.typeChoisi();
    const tous = this.store.refs('MOTIF', true);
    return t ? tous.filter((m) => m.parent_id === t) : tous;
  });

  ngOnInit(): void {
    this.store.charger();
    this.filtres.controls.type_id.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((t) => this.typeChoisi.set(t));
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((q) => {
      const preset = VUES[this.route.snapshot.data['vue'] as string] ?? null;
      this.vue.set(preset);
      const valeurs = this.filtres.getRawValue();
      for (const c of CHAMPS) valeurs[c] = q.get(c) ?? '';
      for (const b of BOOLEENS) valeurs[b] = q.get(b) === 'true';
      if (preset) {
        if (!q.get('etape') && preset.etape) valeurs.etape = preset.etape;
        if (q.get('ouvertes') === null && preset.ouvertes) valeurs.ouvertes = true;
        if (q.get('archivees') === null && preset.archivees) valeurs.archivees = true;
      }
      valeurs.corbeille = valeurs.corbeille && !preset;
      this.filtres.setValue(valeurs, { emitEvent: false });
      this.corbeille.set(valeurs.corbeille);
      this.typeChoisi.set(q.get('type_id') ?? '');
      this.page.set(Math.max(1, Number(q.get('page')) || 1));
      const tri = q.get('tri') ?? 'date_premiere_reception';
      this.tri.set(TRIS.has(tri) ? tri : 'date_premiere_reception');
      this.ordre.set(q.get('ordre') === 'asc' ? 'asc' : 'desc');
      const { corbeille: _c, ...autres } = this.filtres.getRawValue();
      this.filtresActifs.set(Object.values(autres).some(Boolean));
      this.indicateur.set(this.decrireIndicateur());
      this.charger();
    });
  }

  charger(): void {
    this.courant.set(this.filtres.getRawValue());
    this.chargement.set(true);
    this.erreur.set(false);
    this.rc.lister({ ...this.filtres.getRawValue(), page: this.page(), taille: TAILLE, tri: this.tri(), ordre: this.ordre() }).subscribe({
      next: (r) => {
        this.lignes.set(r.items);
        this.total.set(r.total);
        this.totaux.set(r.totaux ?? null);
        this.chargement.set(false);
      },
      error: (e) => {
        this.chargement.set(false);
        this.erreur.set(true);
        void describeApiErrorAsync(e).then((info) => this.feedback.apiError(info, 'Chargement impossible'));
      },
    });
  }

  ouvrir(d: DossierLigne, ev: MouseEvent): void {
    if ((ev.target as HTMLElement).closest('a, button')) return;
    void this.router.navigate(['/reclamations/dossiers', d.id]);
  }

  appliquer(): void {
    const v = this.filtres.getRawValue();
    const params: Record<string, string | null> = { page: null };
    for (const c of CHAMPS) params[c] = v[c] || null;
    for (const b of BOOLEENS) params[b] = v[b] ? 'true' : null;
    this.naviguer(params);
  }

  reinitialiser(): void {
    const preset = this.vue();
    const params: Record<string, string | null> = { page: null };
    for (const c of [...CHAMPS, ...BOOLEENS]) params[c] = null;
    if (preset?.etape) params['etape'] = preset.etape;
    if (preset?.ouvertes) params['ouvertes'] = 'true';
    if (preset?.archivees) params['archivees'] = 'true';
    if (this.corbeille()) params['corbeille'] = 'true';
    this.naviguer(params);
  }

  private decrireIndicateur(): { libelle: string; periode: string; uniteId: string } | null {
    const v = this.filtres.getRawValue();
    if (!v.indicateur) return null;
    const periode = v.kpi_debut && v.kpi_fin ? ` du ${dateFr(v.kpi_debut)} au ${dateFr(v.kpi_fin)}`
      : v.kpi_debut ? ` depuis le ${dateFr(v.kpi_debut)}` : v.kpi_fin ? ` jusqu’au ${dateFr(v.kpi_fin)}` : '';
    return { libelle: libelleIndicateur(v.indicateur), periode, uniteId: v.kpi_unite_id };
  }

  nomUnite(id: string): string {
    const u = id ? this.store.unites().find((x) => x.id === id) : null;
    return u ? ` — ${u.libelle}` : '';
  }

  retirerIndicateur(): void {
    const params: Record<string, string | null> = { page: null };
    for (const k of KPI) params[k] = null;
    this.naviguer(params);
  }

  basculerCorbeille(): void {
    this.naviguer({ corbeille: this.corbeille() ? null : 'true', page: null });
  }

  peutModifier(d: DossierLigne): boolean {
    if (d.termine) return false;
    return this.store.cap('modifier') || (this.store.cap('creer') && d.statut === 'A_QUALIFIER');
  }

  peutAnnuler(d: DossierLigne): boolean {
    return this.store.cap('annuler') && ANNULABLES.has(d.statut);
  }

  /** Pas de suppression physique : le dossier passe « Annulée », motif et historique conservés. */
  annuler(d: DossierLigne): void {
    this.feedback
      .runWithReason((motif) => this.rc.action(d.id, 'annuler', { revision: d.revision, motif }), {
        reason: {
          title: `Annuler la réclamation ${d.reference}`,
          message: 'Le dossier passera au statut « Annulée ». Il reste consultable avec tout son historique.',
          hint: 'Utilisez cette action pour une saisie en double ou erronée.',
          confirmLabel: 'Annuler le dossier',
          cancelLabel: 'Retour',
          tone: 'danger',
          icon: 'block',
          reasonLabel: 'Motif de l’annulation',
          reasonPlaceholder: 'Doublon de REC-…, erreur de saisie…',
          maxLength: 4000,
        },
        busy: this.actionBusy,
        loading: 'Annulation…',
        success: (r) => ({ title: 'Réclamation annulée', details: [{ label: 'Référence', value: r.reference }, { label: 'Statut', value: r.statut_libelle }] }),
        errorTitle: 'Annulation refusée',
        retry: false,
      })
      .subscribe(() => this.charger());
  }

  supprimer(d: DossierLigne): void {
    this.feedback
      .runWithReason((motif) => this.rc.supprimer(d.id, { revision: d.revision, motif, confirmation: d.reference }),
        optionsSuppression(d.reference, this.actionBusy))
      .subscribe(() => this.charger());
  }

  restaurer(d: DossierLigne): void {
    this.feedback
      .runWithReason((motif) => this.rc.restaurer(d.id, { revision: d.revision, motif }), optionsRestauration(d.reference, this.actionBusy))
      .subscribe(() => this.charger());
  }

  trier(colonne: string): void {
    const ordre = this.tri() === colonne && this.ordre() === 'desc' ? 'asc' : 'desc';
    this.naviguer({ tri: colonne, ordre, page: null });
  }

  allerPage(p: number): void {
    this.naviguer({ page: p > 1 ? String(p) : null });
  }

  fleche(colonne: string): string {
    if (this.tri() !== colonne) return '';
    return this.ordre() === 'asc' ? '▲' : '▼';
  }

  date(iso: string | null, heure = false): string {
    return dateFr(iso, heure);
  }

  montant(v: string | null, devise: string): string {
    return montantFr(v, devise);
  }

  private naviguer(params: Record<string, string | null>): void {
    void this.router.navigate([], { relativeTo: this.route, queryParams: params, queryParamsHandling: 'merge' });
  }
}
