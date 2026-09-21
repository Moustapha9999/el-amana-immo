import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, input, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';

interface Article {
  id: string;
  code: string;
  designation: string;
  stock_actuel: number;
  stock_min: number;
  niveau: string | null;
  uom: string;
}

interface Mouvement {
  id: string;
  reference: string;
  date_mouvement: string;
  type_mouvement: string;
  article_id: string;
  quantite: number;
  motif: string | null;
}

interface Famille {
  id: string;
  code: string;
  libelle: string;
}

interface Agence {
  id: string;
  libelle: string;
}

interface Alerte {
  article_id: string;
  code: string;
  designation: string;
  stock_actuel: number;
  stock_min: number;
  niveau: string;
}

interface Parametre {
  id: string;
  cle: string;
  valeur: string;
  libelle: string | null;
}

interface InventaireLigne {
  id: string;
  article_id: string;
  stock_theorique: number;
  stock_physique: number | null;
  ecart: number | null;
  observation: string | null;
  article_code?: string | null;
  article_designation?: string | null;
}

interface Inventaire {
  id: string;
  reference: string;
  libelle: string;
  date_debut: string;
  date_fin: string | null;
  statut: string;
  observation: string | null;
  lignes: InventaireLigne[];
}

@Component({
  selector: 'bea-stock-etat',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, DecimalPipe],
  template: `
    <section class="bea-stock-page">
      <header class="bea-stock-page__head">
        <div>
          <p class="bea-stock-page__kicker">Stock</p>
          <h1>État du stock</h1>
          <p>Quantités temps réel par article (données base).</p>
        </div>
        <a class="bea-admin-btn" routerLink="/stock-fournitures/alertes">Voir alertes</a>
      </header>
      @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
      <table class="bea-stock-table">
        <thead>
          <tr><th>Code</th><th>Désignation</th><th>Stock</th><th>Min</th><th>Niveau</th></tr>
        </thead>
        <tbody>
          @for (a of articles(); track a.id) {
            <tr>
              <td>{{ a.code }}</td>
              <td>{{ a.designation }}</td>
              <td>{{ a.stock_actuel | number:'1.0-3' }} {{ a.uom }}</td>
              <td>{{ a.stock_min | number:'1.0-3' }}</td>
              <td><span class="bea-stock-badge" [attr.data-niveau]="a.niveau">{{ a.niveau || '—' }}</span></td>
            </tr>
          } @empty {
            <tr><td colspan="5">Aucun article actif.</td></tr>
          }
        </tbody>
      </table>
    </section>
  `,
})
export class StockEtatComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly articles = signal<Article[]>([]);
  readonly erreur = signal<string | null>(null);

  ngOnInit(): void {
    this.api.get<Article[]>('/mg/stock/articles').subscribe({
      next: (rows) => this.articles.set(rows),
      error: () => this.erreur.set('Impossible de charger le stock.'),
    });
  }
}

@Component({
  selector: 'bea-stock-alertes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, DecimalPipe],
  template: `
    <section class="bea-stock-page">
      <header class="bea-stock-page__head">
        <div>
          <p class="bea-stock-page__kicker">Alertes</p>
          <h1>Alertes stock</h1>
          <p>Articles en rupture ou sous le seuil minimum.</p>
        </div>
        <a class="bea-admin-btn" routerLink="/stock-fournitures/stock">État du stock</a>
      </header>
      @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
      <table class="bea-stock-table">
        <thead>
          <tr><th>Niveau</th><th>Code</th><th>Désignation</th><th>Stock</th><th>Minimum</th></tr>
        </thead>
        <tbody>
          @for (a of articles(); track a.article_id) {
            <tr>
              <td><span class="bea-stock-badge" [attr.data-niveau]="a.niveau">{{ a.niveau }}</span></td>
              <td>{{ a.code }}</td>
              <td>{{ a.designation }}</td>
              <td>{{ a.stock_actuel | number:'1.0-3' }}</td>
              <td>{{ a.stock_min | number:'1.0-3' }}</td>
            </tr>
          } @empty {
            <tr><td colspan="5">Aucune alerte pour les critères actuels.</td></tr>
          }
        </tbody>
      </table>
    </section>
  `,
})
export class StockAlertesComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly articles = signal<Alerte[]>([]);
  readonly erreur = signal<string | null>(null);

  ngOnInit(): void {
    this.api.get<Alerte[]>('/mg/stock/alertes').subscribe({
      next: (rows) => this.articles.set(rows),
      error: () => this.erreur.set('Impossible de charger les alertes.'),
    });
  }
}

@Component({
  selector: 'bea-stock-flux',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, DecimalPipe],
  template: `
    <section class="bea-stock-page">
      <header class="bea-stock-page__head">
        <div>
          <p class="bea-stock-page__kicker">{{ titre() }}</p>
          <h1>{{ titre() }}</h1>
        </div>
      </header>

      <form class="bea-stock-form" [formGroup]="form" (ngSubmit)="save()">
        <div class="bea-stock-form__grid">
          <label>Article
            <select formControlName="article_id">
              <option value="">—</option>
              @for (a of articles(); track a.id) {
                <option [value]="a.id">{{ a.code }} — {{ a.designation }} ({{ a.stock_actuel }})</option>
              }
            </select>
          </label>
          <label>Quantité <input type="number" formControlName="quantite" min="0.001" step="0.001" /></label>
          <label>Agence
            <select formControlName="agence_id">
              <option value="">—</option>
              @for (a of agences(); track a.id) {
                <option [value]="a.id">{{ a.libelle }}</option>
              }
            </select>
          </label>
          <label>Motif <input formControlName="motif" /></label>
        </div>
        <button type="submit" class="bea-admin-btn" [disabled]="saving()">Enregistrer</button>
        @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
        @if (ok()) { <p class="bea-stock-page__ok">{{ ok() }}</p> }
      </form>

      <h2>Historique récent</h2>
      <table class="bea-stock-table">
        <thead>
          <tr><th>Réf.</th><th>Date</th><th>Qté</th><th>Motif</th></tr>
        </thead>
        <tbody>
          @for (m of mouvements(); track m.id) {
            <tr>
              <td>{{ m.reference }}</td>
              <td>{{ m.date_mouvement }}</td>
              <td>{{ m.quantite | number:'1.0-3' }}</td>
              <td>{{ m.motif || '—' }}</td>
            </tr>
          } @empty {
            <tr><td colspan="4">Aucun mouvement.</td></tr>
          }
        </tbody>
      </table>
    </section>
  `,
})
export class StockFluxComponent implements OnInit {
  /** ENTREE | SORTIE | INVENTAIRE */
  readonly typeMouvement = input.required<string>();
  readonly titre = input.required<string>();

  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly articles = signal<Article[]>([]);
  readonly agences = signal<Agence[]>([]);
  readonly mouvements = signal<Mouvement[]>([]);
  readonly erreur = signal<string | null>(null);
  readonly ok = signal<string | null>(null);
  readonly saving = signal(false);

  readonly form = this.fb.nonNullable.group({
    article_id: ['', Validators.required],
    quantite: [1, [Validators.required, Validators.min(0.001)]],
    agence_id: [''],
    motif: [''],
  });

  ngOnInit(): void {
    this.api.get<Article[]>('/mg/stock/articles').subscribe({
      next: (rows) => this.articles.set(rows),
    });
    this.api.get<Agence[]>('/mg/stock/agences').subscribe({
      next: (rows) => this.agences.set(rows),
    });
    this.reload();
  }

  reload(): void {
    this.api
      .get<Mouvement[]>('/mg/stock/mouvements', { type_mouvement: this.typeMouvement(), limit: 50 })
      .subscribe({
        next: (rows) => this.mouvements.set(rows),
        error: () => this.erreur.set('Chargement impossible.'),
      });
  }

  save(): void {
    if (this.form.invalid) return;
    this.saving.set(true);
    this.erreur.set(null);
    this.ok.set(null);
    const v = this.form.getRawValue();
    const body: Record<string, unknown> = {
      article_id: v.article_id,
      quantite: v.quantite,
      type_mouvement: this.typeMouvement(),
      motif: v.motif || null,
    };
    if (v.agence_id) body['agence_id'] = v.agence_id;
    this.api.post('/mg/stock/mouvements', body).subscribe({
      next: () => {
        this.saving.set(false);
        this.ok.set('Mouvement enregistré.');
        this.form.patchValue({ quantite: 1, motif: '' });
        this.reload();
        this.api.get<Article[]>('/mg/stock/articles').subscribe({ next: (r) => this.articles.set(r) });
      },
      error: (err) => {
        this.saving.set(false);
        this.erreur.set(err?.error?.detail || 'Enregistrement refusé (stock / permission).');
      },
    });
  }
}

@Component({
  selector: 'bea-stock-entrees',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [StockFluxComponent],
  template: `<bea-stock-flux typeMouvement="ENTREE" titre="Entrées de stock" />`,
})
export class StockEntreesComponent {}

@Component({
  selector: 'bea-stock-sorties',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [StockFluxComponent],
  template: `<bea-stock-flux typeMouvement="SORTIE" titre="Sorties de stock" />`,
})
export class StockSortiesComponent {}

@Component({
  selector: 'bea-stock-inventaires',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, DecimalPipe],
  template: `
    <section class="bea-stock-page">
      <header class="bea-stock-page__head">
        <div>
          <p class="bea-stock-page__kicker">Inventaire</p>
          <h1>Campagnes d’inventaire</h1>
          <p>Comptage physique, écarts, clôture avec ajustement du stock.</p>
        </div>
      </header>

      <form class="bea-stock-form" [formGroup]="createForm" (ngSubmit)="creer()">
        <div class="bea-stock-form__grid">
          <label>Libellé <input formControlName="libelle" placeholder="Inventaire trimestriel" /></label>
          <label>Agence
            <select formControlName="agence_id">
              <option value="">Toutes</option>
              @for (a of agences(); track a.id) {
                <option [value]="a.id">{{ a.libelle }}</option>
              }
            </select>
          </label>
        </div>
        <button type="submit" class="bea-admin-btn" [disabled]="saving()">Nouvelle campagne</button>
      </form>

      @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
      @if (ok()) { <p class="bea-stock-page__ok">{{ ok() }}</p> }

      <table class="bea-stock-table">
        <thead>
          <tr><th>Réf.</th><th>Libellé</th><th>Début</th><th>Statut</th><th></th></tr>
        </thead>
        <tbody>
          @for (inv of inventaires(); track inv.id) {
            <tr>
              <td>{{ inv.reference }}</td>
              <td>{{ inv.libelle }}</td>
              <td>{{ inv.date_debut }}</td>
              <td><span class="bea-stock-badge">{{ inv.statut }}</span></td>
              <td><button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="ouvrir(inv.id)">Ouvrir</button></td>
            </tr>
          } @empty {
            <tr><td colspan="5">Aucune campagne.</td></tr>
          }
        </tbody>
      </table>

      @if (detail(); as d) {
        <div class="bea-stock-panel" style="margin-top:1.25rem">
          <h2>{{ d.reference }} — {{ d.libelle }} ({{ d.statut }})</h2>
          <table class="bea-stock-table">
            <thead>
              <tr>
                <th>Article</th>
                <th>Théorique</th>
                <th>Physique</th>
                <th>Écart</th>
              </tr>
            </thead>
            <tbody>
              @for (l of d.lignes; track l.id) {
                <tr>
                  <td>{{ l.article_code }} — {{ l.article_designation }}</td>
                  <td>{{ l.stock_theorique | number:'1.0-3' }}</td>
                  <td>
                    @if (d.statut === 'CLOTURE') {
                      {{ l.stock_physique | number:'1.0-3' }}
                    } @else {
                      <input
                        type="number"
                        min="0"
                        step="0.001"
                        [value]="physiqueValue(l.id)"
                        (change)="setPhysique(l.id, $event)"
                      />
                    }
                  </td>
                  <td>{{ l.ecart != null ? (l.ecart | number:'1.0-3') : '—' }}</td>
                </tr>
              }
            </tbody>
          </table>
          @if (d.statut !== 'CLOTURE') {
            <div class="bea-stock-fiche__actions">
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="sauverSaisie()" [disabled]="saving()">
                Enregistrer saisie
              </button>
              <button type="button" class="bea-admin-btn" (click)="cloturer()" [disabled]="saving()">
                Clôturer &amp; ajuster stock
              </button>
            </div>
          }
        </div>
      }
    </section>
  `,
})
export class StockInventairesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly agences = signal<Agence[]>([]);
  readonly inventaires = signal<Inventaire[]>([]);
  readonly detail = signal<Inventaire | null>(null);
  readonly physiqueMap = signal<Record<string, number | ''>>({});
  readonly erreur = signal<string | null>(null);
  readonly ok = signal<string | null>(null);
  readonly saving = signal(false);

  readonly createForm = this.fb.nonNullable.group({
    libelle: ['', Validators.required],
    agence_id: [''],
  });

  ngOnInit(): void {
    this.api.get<Agence[]>('/mg/stock/agences').subscribe({ next: (a) => this.agences.set(a) });
    this.reload();
  }

  reload(): void {
    this.api.get<Inventaire[]>('/mg/stock/inventaires').subscribe({
      next: (rows) => this.inventaires.set(rows),
      error: () => this.erreur.set('Chargement inventaires impossible.'),
    });
  }

  creer(): void {
    if (this.createForm.invalid) return;
    this.saving.set(true);
    this.erreur.set(null);
    const v = this.createForm.getRawValue();
    const body: Record<string, unknown> = { libelle: v.libelle };
    if (v.agence_id) body['agence_id'] = v.agence_id;
    this.api.post<Inventaire>('/mg/stock/inventaires', body).subscribe({
      next: (inv) => {
        this.saving.set(false);
        this.ok.set(`Campagne ${inv.reference} créée.`);
        this.createForm.reset({ libelle: '', agence_id: '' });
        this.reload();
        this.ouvrir(inv.id);
      },
      error: (err) => {
        this.saving.set(false);
        this.erreur.set(err?.error?.detail || 'Création refusée.');
      },
    });
  }

  ouvrir(id: string): void {
    this.api.get<Inventaire>(`/mg/stock/inventaires/${id}`).subscribe({
      next: (inv) => {
        this.detail.set(inv);
        const map: Record<string, number | ''> = {};
        for (const l of inv.lignes) {
          map[l.id] = l.stock_physique != null ? Number(l.stock_physique) : '';
        }
        this.physiqueMap.set(map);
      },
      error: () => this.erreur.set('Ouverture impossible.'),
    });
  }

  physiqueValue(id: string): number | '' {
    const v = this.physiqueMap()[id];
    return v === undefined ? '' : v;
  }

  setPhysique(id: string, event: Event): void {
    const raw = (event.target as HTMLInputElement).value;
    const val = raw === '' ? '' : Number(raw);
    this.physiqueMap.update((m) => ({ ...m, [id]: val }));
  }

  sauverSaisie(): void {
    const d = this.detail();
    if (!d) return;
    this.saving.set(true);
    const body = d.lignes
      .filter((l) => {
        const v = this.physiqueMap()[l.id];
        return typeof v === 'number' && !Number.isNaN(v);
      })
      .map((l) => ({ id: l.id, stock_physique: this.physiqueMap()[l.id] as number }));
    this.api.patch<Inventaire>(`/mg/stock/inventaires/${d.id}/saisie`, body).subscribe({
      next: (inv) => {
        this.saving.set(false);
        this.ok.set('Saisie enregistrée.');
        this.detail.set(inv);
        this.reload();
      },
      error: (err) => {
        this.saving.set(false);
        this.erreur.set(err?.error?.detail || 'Saisie refusée.');
      },
    });
  }

  cloturer(): void {
    const d = this.detail();
    if (!d) return;
    this.saving.set(true);
    const body = d.lignes
      .filter((l) => {
        const v = this.physiqueMap()[l.id];
        return typeof v === 'number' && !Number.isNaN(v);
      })
      .map((l) => ({ id: l.id, stock_physique: this.physiqueMap()[l.id] as number }));
    this.api.patch<Inventaire>(`/mg/stock/inventaires/${d.id}/saisie`, body).subscribe({
      next: () => {
        this.api.post<Inventaire>(`/mg/stock/inventaires/${d.id}/cloturer`, {}).subscribe({
          next: (inv) => {
            this.saving.set(false);
            this.ok.set('Inventaire clôturé — stock ajusté.');
            this.detail.set(inv);
            this.reload();
          },
          error: (err) => {
            this.saving.set(false);
            this.erreur.set(err?.error?.detail || 'Clôture refusée.');
          },
        });
      },
      error: (err) => {
        this.saving.set(false);
        this.erreur.set(err?.error?.detail || 'Saisie préalable refusée.');
      },
    });
  }
}

@Component({
  selector: 'bea-stock-parametres',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule],
  template: `
    <section class="bea-stock-page">
      <header class="bea-stock-page__head">
        <div>
          <p class="bea-stock-page__kicker">Paramètres</p>
          <h1>Référentiels &amp; numérotation</h1>
          <p>Familles d’articles et préfixes de documents.</p>
        </div>
      </header>
      @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
      @if (ok()) { <p class="bea-stock-page__ok">{{ ok() }}</p> }

      <div class="bea-stock-charts">
        <section class="bea-stock-panel">
          <h2>Familles</h2>
          <table class="bea-stock-table">
            <thead><tr><th>Code</th><th>Libellé</th></tr></thead>
            <tbody>
              @for (f of familles(); track f.id) {
                <tr><td>{{ f.code }}</td><td>{{ f.libelle }}</td></tr>
              } @empty {
                <tr><td colspan="2">Aucune famille.</td></tr>
              }
            </tbody>
          </table>
        </section>
        <section class="bea-stock-panel">
          <h2>Paramètres module</h2>
          <table class="bea-stock-table">
            <thead><tr><th>Clé</th><th>Libellé</th><th>Valeur</th><th></th></tr></thead>
            <tbody>
              @for (p of parametres(); track p.cle) {
                <tr>
                  <td>{{ p.cle }}</td>
                  <td>{{ p.libelle || '—' }}</td>
                  <td>
                    <input
                      [value]="editValue(p)"
                      (input)="setEdit(p.cle, $event)"
                    />
                  </td>
                  <td>
                    <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="sauver(p.cle)">
                      Sauver
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr><td colspan="4">Aucun paramètre (migration v2 ?).</td></tr>
              }
            </tbody>
          </table>
        </section>
      </div>
    </section>
  `,
})
export class StockParametresComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly familles = signal<Famille[]>([]);
  readonly parametres = signal<Parametre[]>([]);
  readonly editMap = signal<Record<string, string>>({});
  readonly erreur = signal<string | null>(null);
  readonly ok = signal<string | null>(null);

  ngOnInit(): void {
    this.api.get<Famille[]>('/mg/stock/familles').subscribe({
      next: (rows) => this.familles.set(rows),
      error: () => this.erreur.set('Chargement familles impossible.'),
    });
    this.api.get<Parametre[]>('/mg/stock/parametres').subscribe({
      next: (rows) => this.parametres.set(rows),
      error: () => {
        /* permission ou migration absente */
      },
    });
  }

  setEdit(cle: string, event: Event): void {
    const val = (event.target as HTMLInputElement).value;
    this.editMap.update((m) => ({ ...m, [cle]: val }));
  }

  editValue(p: Parametre): string {
    return this.editMap()[p.cle] !== undefined ? this.editMap()[p.cle] : p.valeur;
  }

  sauver(cle: string): void {
    const valeur = this.editMap()[cle] ?? this.parametres().find((p) => p.cle === cle)?.valeur;
    if (!valeur) return;
    this.api.patch<Parametre>(`/mg/stock/parametres/${cle}`, { valeur }).subscribe({
      next: (row) => {
        this.ok.set(`Paramètre ${cle} mis à jour.`);
        this.parametres.update((rows) => rows.map((p) => (p.cle === cle ? row : p)));
      },
      error: (err) => this.erreur.set(err?.error?.detail || 'Mise à jour refusée.'),
    });
  }
}
