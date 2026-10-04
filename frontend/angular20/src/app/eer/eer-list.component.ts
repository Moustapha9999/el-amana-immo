import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { EerAgence, EerFiltres, EerReferentiel, EerService } from './eer.service';
import { EerDossierLigne, EerPerimetre, STATUTS, TYPES_CLIENT, dateFr, eerTone, libelle } from './eer.models';

const TAILLE = 25;
const COLONNES_TRIABLES = new Set(['reference', 'statut', 'date_eer', 'soumis_le', 'valide_le', 'created_at', 'updated_at']);

@Component({
  selector: 'bea-eer-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule],
  template: `
    <section class="bea-mg bea-nf bea-ct">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">KYC · Gestion des EER</p>
          <h1>{{ mesDossiers() ? 'Mes dossiers à contrôler' : 'Dossiers d’entrée en relation' }}</h1>
          <p class="bea-ct-head__sub">
            Filtres, tri et pagination appliqués par le serveur, dans la limite de votre périmètre.
            @if (perimetre()?.perimetre === 'AGENCE') { <span class="bea-ct-badge" data-tone="ATTENTION">Périmètre : votre agence</span> }
          </p>
        </div>
        <div class="bea-mg__actions">
          @if (perimetre()?.capacites?.['creation']) {
            <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/eer/dossiers/nouveau"><mat-icon>person_add</mat-icon> Nouvelle EER</a>
          }
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" title="Actualiser" (click)="charger()"><mat-icon>refresh</mat-icon></button>
        </div>
      </header>

      <form class="bea-mg__search bea-ct-filters" [formGroup]="filtres" (ngSubmit)="appliquer()">
        <label class="bea-mg__field bea-ct-filters__q">Recherche
          <input formControlName="q" placeholder="Référence, nom du client, racine" maxlength="100" />
        </label>
        <label class="bea-mg__field">Statut
          <select formControlName="statut" (change)="appliquer()">
            <option value="">Tous</option>
            @for (s of statuts; track s[0]) { <option [value]="s[0]">{{ s[1] }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Type de client
          <select formControlName="type_client" (change)="filtres.controls.profil.setValue(''); appliquer()">
            <option value="">Tous</option>
            @for (t of types; track t[0]) { <option [value]="t[0]">{{ t[1] }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Profil
          <select formControlName="profil" (change)="appliquer()">
            <option value="">Tous</option>
            @for (p of profilsFiltres(); track p.code) { <option [value]="p.code">{{ p.libelle }}</option> }
          </select>
        </label>
        <label class="bea-mg__field">Risque
          <select formControlName="risque" (change)="appliquer()">
            <option value="">Tous</option>
            <option value="FAIBLE">Faible</option>
            <option value="MOYEN">Moyen</option>
            <option value="ELEVE">Élevé</option>
          </select>
        </label>
        @if (agences().length > 1) {
          <label class="bea-mg__field">Agence
            <select formControlName="agence_id" (change)="appliquer()">
              <option value="">Toutes</option>
              @for (a of agences(); track a.id) { <option [value]="a.id">{{ a.code }} — {{ a.libelle }}</option> }
            </select>
          </label>
        }
        <label class="bea-mg__field">Du
          <input type="date" formControlName="date_debut" (change)="appliquer()" />
        </label>
        <label class="bea-mg__field">Au
          <input type="date" formControlName="date_fin" (change)="appliquer()" />
        </label>
        <div class="bea-ct-filters__btns">
          <button type="submit" class="bea-mg__btn bea-mg__btn--ghost"><mat-icon>search</mat-icon> Filtrer</button>
          @if (filtresActifs()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="reinitialiser()">Réinitialiser</button>
          }
        </div>
      </form>

      <div class="bea-mg__table-scroll bea-ct-table-wrap">
        <table class="bea-mg__table bea-ct-table">
          <thead>
            <tr>
              <th><button type="button" class="eer-sort" (click)="trier('reference')">Référence {{ fleche('reference') }}</button></th>
              <th>Client</th>
              <th>Type / profil</th>
              <th>Agence</th>
              <th><button type="button" class="eer-sort" (click)="trier('date_eer')">Date EER {{ fleche('date_eer') }}</button></th>
              <th>Analyste</th>
              <th>Risque</th>
              <th><button type="button" class="eer-sort" (click)="trier('statut')">Statut {{ fleche('statut') }}</button></th>
              <th><button type="button" class="eer-sort" (click)="trier('updated_at')">Mis à jour {{ fleche('updated_at') }}</button></th>
              <th class="is-actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            @for (d of lignes(); track d.id; let i = $index) {
              <tr class="bea-ct-row" [style.animation-delay.ms]="i < 20 ? i * 30 : 0">
                <td class="is-nowrap">
                  <a class="bea-ct-link" [routerLink]="['/eer/dossiers', d.id]"><code class="bea-mg__code">{{ d.reference }}</code></a>
                  <small class="bea-ct-sub">v{{ d.version_courante }}{{ d.avis_requis ? ' · avis KYC requis' : '' }}</small>
                </td>
                <td class="is-wide">
                  <strong class="bea-ct-strong">{{ d.client_nom }}</strong>
                  @if (d.racine_client) { <small class="bea-ct-sub">Racine {{ d.racine_client }}</small> }
                </td>
                <td class="is-wide">{{ type(d.type_client) }}<small class="bea-ct-sub">{{ d.profil }}</small></td>
                <td class="is-nowrap">{{ d.agence_code }}<small class="bea-ct-sub">{{ d.agence_libelle }}</small></td>
                <td class="is-nowrap">{{ date(d.date_eer) }}</td>
                <td class="is-wide">{{ d.analyste_nom || '—' }}</td>
                <td class="is-nowrap">{{ d.risque || '—' }}</td>
                <td class="is-nowrap"><span class="bea-ct-badge" [attr.data-tone]="tone(d.statut)">{{ statut(d.statut) }}</span></td>
                <td class="is-nowrap">{{ date(d.updated_at, true) }}</td>
                <td class="bea-mg__actions-cell is-nowrap">
                  <a class="bea-mg__icon-btn" [routerLink]="['/eer/dossiers', d.id]" title="Ouvrir la fiche"><mat-icon>visibility</mat-icon></a>
                </td>
              </tr>
            } @empty {
              <tr><td colspan="10"><div class="bea-ct-empty"><mat-icon>folder_shared</mat-icon>
                <p>{{ chargement() ? 'Chargement…' : filtresActifs() ? 'Aucun dossier ne correspond aux filtres.' : 'Aucun dossier EER dans votre périmètre.' }}</p>
              </div></td></tr>
            }
          </tbody>
        </table>
      </div>

      @if (total() > 0) {
        <div class="eer-pager">
          <p class="bea-ct-count">{{ debut() }}–{{ fin() }} sur {{ total() }} dossier{{ total() > 1 ? 's' : '' }}</p>
          <div class="bea-mg__actions">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() <= 1" (click)="allerPage(page() - 1)"><mat-icon>chevron_left</mat-icon> Précédent</button>
            <span class="eer-pager__num">Page {{ page() }} / {{ pages() }}</span>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() >= pages()" (click)="allerPage(page() + 1)">Suivant <mat-icon>chevron_right</mat-icon></button>
          </div>
        </div>
      }
    </section>
  `,
  styles: [`
    .eer-sort { border: 0; background: none; padding: 0; font: inherit; font-weight: inherit; color: inherit; cursor: pointer; text-transform: inherit; letter-spacing: inherit; }
    .eer-sort:hover { color: #1a5278; }
    .eer-pager { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem; margin-top: 0.75rem; }
    .eer-pager__num { font-size: 0.85rem; color: #475569; font-weight: 600; }
  `],
})
export class EerListComponent implements OnInit {
  private readonly eer = inject(EerService);
  private readonly feedback = inject(FeedbackService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly statuts = Object.entries(STATUTS);
  readonly types = Object.entries(TYPES_CLIENT);
  readonly filtres = this.fb.nonNullable.group({
    q: '',
    statut: '',
    type_client: '',
    profil: '',
    risque: '',
    agence_id: '',
    date_debut: '',
    date_fin: '',
  });

  readonly perimetre = signal<EerPerimetre | null>(null);
  readonly agences = signal<EerAgence[]>([]);
  readonly profils = signal<EerReferentiel[]>([]);
  readonly lignes = signal<EerDossierLigne[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly tri = signal('created_at');
  readonly ordre = signal<'asc' | 'desc'>('desc');
  readonly mesDossiers = signal(false);
  readonly chargement = signal(false);
  private readonly typeChoisi = signal('');

  readonly pages = computed(() => Math.max(1, Math.ceil(this.total() / TAILLE)));
  readonly debut = computed(() => (this.page() - 1) * TAILLE + 1);
  readonly fin = computed(() => Math.min(this.page() * TAILLE, this.total()));
  readonly profilsFiltres = computed(() => {
    const t = this.typeChoisi();
    return t ? this.profils().filter((p) => p.parent_code === t) : this.profils();
  });
  readonly filtresActifs = signal(false);

  ngOnInit(): void {
    this.eer.perimetre().subscribe({ next: (p) => this.perimetre.set(p), error: (e) => this.fail(e) });
    this.eer.agences().subscribe({ next: (a) => this.agences.set(a), error: () => undefined });
    this.eer.referentiels('PROFIL').subscribe({ next: (r) => this.profils.set(r), error: () => undefined });
    this.filtres.controls.type_client.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((t) => this.typeChoisi.set(t));
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((q) => {
      this.filtres.setValue(
        {
          q: q.get('q') ?? '',
          statut: q.get('statut') ?? '',
          type_client: q.get('type_client') ?? '',
          profil: q.get('profil') ?? '',
          risque: q.get('risque') ?? '',
          agence_id: q.get('agence_id') ?? '',
          date_debut: q.get('date_debut') ?? '',
          date_fin: q.get('date_fin') ?? '',
        },
        { emitEvent: false },
      );
      this.typeChoisi.set(q.get('type_client') ?? '');
      this.mesDossiers.set(q.get('mes_dossiers') === 'true');
      this.page.set(Math.max(1, Number(q.get('page')) || 1));
      const tri = q.get('tri') ?? 'created_at';
      this.tri.set(COLONNES_TRIABLES.has(tri) ? tri : 'created_at');
      this.ordre.set(q.get('ordre') === 'asc' ? 'asc' : 'desc');
      this.filtresActifs.set(Object.values(this.filtres.getRawValue()).some(Boolean));
      this.charger();
    });
  }

  charger(): void {
    const raw = this.filtres.getRawValue();
    const f: EerFiltres = {
      ...raw,
      mes_dossiers: this.mesDossiers() || undefined,
      page: this.page(),
      size: TAILLE,
      tri: this.tri(),
      ordre: this.ordre(),
    };
    this.chargement.set(true);
    this.eer.lister(f).subscribe({
      next: (r) => {
        this.lignes.set(r.items);
        this.total.set(r.total);
        this.chargement.set(false);
      },
      error: (e) => {
        this.chargement.set(false);
        this.fail(e);
      },
    });
  }

  appliquer(): void {
    this.naviguer({ ...this.filtres.getRawValue(), page: null });
  }

  reinitialiser(): void {
    this.filtres.reset();
    this.naviguer({ q: null, statut: null, type_client: null, profil: null, risque: null, agence_id: null, date_debut: null, date_fin: null, page: null });
  }

  trier(colonne: string): void {
    const ordre = this.tri() === colonne && this.ordre() === 'desc' ? 'asc' : 'desc';
    this.naviguer({ tri: colonne, ordre, page: null });
  }

  allerPage(p: number): void {
    this.naviguer({ page: p > 1 ? p : null });
  }

  fleche(colonne: string): string {
    if (this.tri() !== colonne) return '';
    return this.ordre() === 'asc' ? '▲' : '▼';
  }

  statut(code: string): string {
    return libelle(STATUTS, code);
  }

  type(code: string): string {
    return libelle(TYPES_CLIENT, code);
  }

  tone(statut: string): string {
    return eerTone(statut);
  }

  date(iso: string | null, heure = false): string {
    return dateFr(iso, heure);
  }

  private naviguer(params: Record<string, string | number | null>): void {
    const nettoyes: Record<string, string | number | null> = {};
    for (const [k, v] of Object.entries(params)) nettoyes[k] = v === '' ? null : v;
    void this.router.navigate([], { relativeTo: this.route, queryParams: nettoyes, queryParamsHandling: 'merge' });
  }

  private fail(err: unknown): void {
    void describeApiErrorAsync(err).then((info) => this.feedback.apiError(info, 'Chargement impossible'));
  }
}