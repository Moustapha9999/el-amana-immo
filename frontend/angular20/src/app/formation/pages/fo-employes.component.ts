import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router } from '@angular/router';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { FormationUiComponent } from '../formation-ui.component';
import { Employe, FO_BASE, Page, dateFr, initiales, nettoyer } from '../formation.models';
import { FormationStore } from '../formation.store';
import { FoEmployeFormComponent } from '../shared/fo-employe-form.component';

const FILTRES = ['q', 'entite_id', 'perimetre_id', 'fonction_id', 'actif', 'forme'] as const;
type Filtre = (typeof FILTRES)[number];

@Component({
  selector: 'bea-fo-employes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, FormationUiComponent, FoEmployeFormComponent],
  template: `
    <bea-fo-styles />
    <div class="bea-mg bea-fo">
      <header class="bea-mg__head bea-fo-head">
        <div class="bea-fo-head__txt">
          <p class="bea-stock-page__kicker">Formation &amp; Sensibilisation</p>
          <h1>Employés</h1>
          <p class="bea-fo-head__sub">Référentiel des collaborateurs suivis : nom, prénom, fonction, entité et périmètre. Aucun doublon : la création vérifie les noms proches.</p>
        </div>
        <div class="bea-mg__actions">
          @if (store.cap().employes_gerer) {
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="edition.set('nouveau')"><mat-icon>person_add</mat-icon> Nouvel employé</button>
          }
        </div>
      </header>

      <div class="bea-fo-yearbar">
        <button type="button" class="bea-fx-chip" [class.is-active]="!f().forme" (click)="maj('forme', '')"><mat-icon>groups</mat-icon> Tous <strong>{{ !f().forme ? (page()?.total ?? '') : '' }}</strong></button>
        <button type="button" class="bea-fx-chip" [class.is-active]="f().forme === 'oui'" (click)="maj('forme', 'oui')"><mat-icon>verified_user</mat-icon> Formés <strong>{{ f().forme === 'oui' ? (page()?.total ?? '') : '' }}</strong></button>
        <button type="button" class="bea-fx-chip" [class.is-active]="f().forme === 'non'" (click)="maj('forme', 'non')"><mat-icon>person_search</mat-icon> Jamais formés <strong>{{ f().forme === 'non' ? (page()?.total ?? '') : '' }}</strong></button>
      </div>

      <section class="bea-mg__panel">
        <div class="bea-fo-filters">
          <label style="grid-column: span 2">Recherche
            <input type="search" placeholder="Nom, prénom, email, téléphone…" [value]="f().q ?? ''" (input)="saisirQ($any($event.target).value)" />
          </label>
          <label>Périmètre
            <select [value]="f().perimetre_id ?? ''" (change)="maj('perimetre_id', $any($event.target).value)">
              <option value="">Tous</option>
              @for (r of store.refs('PERIMETRE', true); track r.id) { <option [value]="r.id">{{ r.libelle }}</option> }
            </select>
          </label>
          <label>Entité
            <select [value]="f().entite_id ?? ''" (change)="maj('entite_id', $any($event.target).value)">
              <option value="">Toutes</option>
              @for (e of store.entites(); track e.id) { <option [value]="e.id">{{ e.libelle }}</option> }
            </select>
          </label>
          <label>Fonction
            <select [value]="f().fonction_id ?? ''" (change)="maj('fonction_id', $any($event.target).value)">
              <option value="">Toutes</option>
              @for (r of store.refs('FONCTION', true); track r.id) { <option [value]="r.id">{{ r.libelle }}</option> }
            </select>
          </label>
          <label>Statut
            <select [value]="f().actif ?? 'oui'" (change)="maj('actif', $any($event.target).value === 'oui' ? '' : $any($event.target).value)">
              <option value="oui">Actifs</option>
              <option value="non">Désactivés</option>
              <option value="tous">Tous</option>
            </select>
          </label>
        </div>
      </section>

      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Liste des employés</h2><span class="bea-mg__count">{{ page()?.total ?? 0 }} employé(s)</span></div>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table bea-fo-table">
            <thead>
              <tr>
                <th><button type="button" class="bea-fx-sort" (click)="trier('nom')">Nom <mat-icon>{{ icone('nom') }}</mat-icon></button></th>
                <th><button type="button" class="bea-fx-sort" (click)="trier('prenom')">Prénom <mat-icon>{{ icone('prenom') }}</mat-icon></button></th>
                <th>Fonction</th>
                <th>Entité</th>
                <th>Périmètre</th>
                <th class="is-num"><button type="button" class="bea-fx-sort" (click)="trier('formations')">Formations suivies <mat-icon>{{ icone('formations') }}</mat-icon></button></th>
                <th><button type="button" class="bea-fx-sort" (click)="trier('derniere')">Dernière <mat-icon>{{ icone('derniere') }}</mat-icon></button></th>
                @if (store.cap().employes_gerer || store.cap().admin) { <th></th> }
              </tr>
            </thead>
            <tbody>
              @if (charge()) {
                @for (i of [1, 2, 3, 4, 5, 6]; track i) { <tr>@for (j of [1, 2, 3, 4, 5, 6, 7]; track j) { <td><span class="bea-fx-skel"></span></td> }</tr> }
              } @else {
                @for (e of page()?.items ?? []; track e.id; let i = $index) {
                  <tr class="is-click bea-fx-row-in" [style.--i]="i" [class.is-muted]="!e.actif" (click)="ouvrir(e)">
                    <td>
                      <span class="bea-fo-person">
                        <span class="bea-fo-avatar">{{ ini(e.nom_complet) }}</span>
                        <span><strong>{{ e.nom }}</strong>@if (!e.actif) {<small>désactivé</small>}</span>
                      </span>
                    </td>
                    <td>{{ e.prenom || '—' }}</td>
                    <td>{{ e.fonction || '—' }}</td>
                    <td>{{ e.entite || '—' }}</td>
                    <td>{{ e.perimetre || '—' }}</td>
                    <td class="is-num">
                      <strong>{{ e.nb_presents }}</strong>
                      @if (e.nb_absents) { <small>{{ e.nb_absents }} absence(s)</small> }
                    </td>
                    <td>{{ dateFr(e.derniere_formation) }}</td>
                    @if (store.cap().employes_gerer || store.cap().admin) {
                      <td class="is-c" (click)="$event.stopPropagation()">
                        <span style="display:inline-flex;gap:0.3rem">
                          @if (store.cap().employes_gerer) {
                            <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="edition.set(e)"><mat-icon>edit</mat-icon></button>
                          }
                          @if (store.cap().admin) {
                            <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer définitivement" (click)="supprimer(e)" [disabled]="busy()"><mat-icon>delete</mat-icon></button>
                          }
                        </span>
                      </td>
                    }
                  </tr>
                } @empty {
                  <tr><td colspan="8"><div class="bea-fo-empty"><mat-icon>person_off</mat-icon><strong>Aucun employé</strong>Modifiez les filtres ou importez le fichier Excel de suivi.</div></td></tr>
                }
              }
            </tbody>
          </table>
        </div>
        @if ((page()?.total ?? 0) > taille) {
          <div class="bea-fx-pager">
            <button type="button" class="bea-mg__icon-btn" [disabled]="pageNo() <= 1" (click)="allerPage(pageNo() - 1)"><mat-icon>chevron_left</mat-icon></button>
            <span>Page {{ pageNo() }} / {{ nbPages() }}</span>
            <button type="button" class="bea-mg__icon-btn" [disabled]="pageNo() >= nbPages()" (click)="allerPage(pageNo() + 1)"><mat-icon>chevron_right</mat-icon></button>
          </div>
        }
      </section>
    </div>
    @if (edition(); as ed) {
      <bea-fo-employe-form [employe]="ed === 'nouveau' ? null : ed" (fermer)="edition.set(null)" (enregistre)="enregistre($event)" (choisirExistant)="ouvrir($event)" />
    }
  `,
})
export class FoEmployesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly store = inject(FormationStore);

  readonly taille = 30;
  readonly dateFr = dateFr;
  readonly ini = initiales;
  readonly f = signal<Partial<Record<Filtre, string>>>({});
  readonly tri = signal('nom');
  readonly sens = signal<'asc' | 'desc'>('asc');
  readonly pageNo = signal(1);
  readonly page = signal<Page<Employe> | null>(null);
  readonly charge = signal(true);
  readonly edition = signal<Employe | 'nouveau' | null>(null);
  readonly busy = signal(false);
  private minuteur: ReturnType<typeof setTimeout> | null = null;

  readonly nbPages = computed(() => Math.max(1, Math.ceil((this.page()?.total ?? 0) / this.taille)));

  supprimer(e: Employe): void {
    const n = e.nb_formations ?? 0;
    this.feedback
      .runWithReason((motif) => this.api.post<void>(`${FO_BASE}/employes/${e.id}/supprimer`, { motif }), {
        reason: {
          title: 'Supprimer définitivement l’employé',
          message: n ? `${e.nom_complet} et ses ${n} participation(s), présences comprises.` : e.nom_complet,
          hint: 'Suppression irréversible, retirée du reporting. Le détail est conservé dans le journal d’audit.',
          reasonLabel: 'Motif de la suppression', required: true, maxLength: 1000, tone: 'danger', confirmLabel: 'Supprimer',
        },
        busy: this.busy,
        loading: 'Suppression…',
        success: { title: 'Employé supprimé', message: e.nom_complet },
        errorTitle: 'Suppression impossible',
      })
      .subscribe(() => this.charger());
  }

  ngOnInit(): void {
    this.store.charger();
    const qp = this.route.snapshot.queryParamMap;
    const f: Partial<Record<Filtre, string>> = {};
    for (const k of FILTRES) {
      const v = qp.get(k);
      if (v) f[k] = v;
    }
    this.f.set(f);
    this.charger();
  }

  saisirQ(v: string): void {
    if (this.minuteur) clearTimeout(this.minuteur);
    this.minuteur = setTimeout(() => this.maj('q', v.trim()), 300);
  }

  maj(cle: Filtre, v: string): void {
    this.f.set({ ...this.f(), [cle]: v || undefined });
    this.pageNo.set(1);
    void this.router.navigate([], { relativeTo: this.route, queryParams: nettoyer(this.f()), replaceUrl: true });
    this.charger();
  }

  trier(col: string): void {
    if (this.tri() === col) this.sens.set(this.sens() === 'asc' ? 'desc' : 'asc');
    else {
      this.tri.set(col);
      this.sens.set(col === 'formations' || col === 'derniere' ? 'desc' : 'asc');
    }
    this.charger();
  }

  icone(col: string): string {
    return this.tri() !== col ? 'unfold_more' : this.sens() === 'asc' ? 'arrow_upward' : 'arrow_downward';
  }

  allerPage(n: number): void {
    this.pageNo.set(n);
    this.charger();
  }

  ouvrir(e: Employe): void {
    this.edition.set(null);
    void this.router.navigate(['/formation/employes', e.id]);
  }

  enregistre(e: Employe): void {
    const nouveau = this.edition() === 'nouveau';
    this.edition.set(null);
    if (nouveau) void this.router.navigate(['/formation/employes', e.id]);
    else this.charger();
  }

  private charger(): void {
    this.charge.set(true);
    const params = nettoyer({ ...this.f(), actif: this.f().actif ?? 'oui', tri: this.tri(), sens: this.sens(), page: this.pageNo(), taille: this.taille });
    this.api.get<Page<Employe>>(`${FO_BASE}/employes`, params).subscribe({
      next: (p) => {
        this.page.set(p);
        this.charge.set(false);
      },
      error: (e) => {
        this.charge.set(false);
        void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Liste des employés indisponible'));
      },
    });
  }
}
