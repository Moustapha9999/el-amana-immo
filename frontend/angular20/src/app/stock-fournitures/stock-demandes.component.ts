import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormArray, FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';

interface Agence {
  id: string;
  libelle: string;
}
interface Article {
  id: string;
  code: string;
  designation: string;
}
interface Demande {
  id: string;
  reference: string;
  date_demande: string;
  agence_libelle_snapshot: string | null;
  demandeur_nom: string | null;
  statut: string;
  lignes: {
    id: string;
    designation: string;
    quantite_demandee: number;
    quantite_accordee: number | null;
  }[];
}

@Component({
  selector: 'bea-stock-demandes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink],
  template: `
    <section class="bea-stock-page">
      <header class="bea-stock-page__head">
        <div>
          <h1>Demandes de fournitures</h1>
          <p>Digitalisation de la fiche « Expression de besoin » — visas Agence / MG.</p>
        </div>
        <a class="bea-admin-btn" routerLink="/stock-fournitures/demandes/nouvelle">Nouvelle demande</a>
      </header>

      @if (mode() === 'list') {
        <div class="bea-stock-panel">
          <table class="bea-stock-table">
            <thead>
              <tr>
                <th>Réf.</th>
                <th>Date</th>
                <th>Agence</th>
                <th>Demandeur</th>
                <th>Statut</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (d of demandes(); track d.id) {
                <tr>
                  <td>{{ d.reference }}</td>
                  <td>{{ d.date_demande }}</td>
                  <td>{{ d.agence_libelle_snapshot }}</td>
                  <td>{{ d.demandeur_nom }}</td>
                  <td><span class="bea-stock-pill">{{ d.statut }}</span></td>
                  <td><a [routerLink]="['/stock-fournitures/demandes', d.id]">Ouvrir</a></td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="6">Aucune demande.</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }

      @if (mode() === 'create') {
        <form class="bea-stock-fiche" [formGroup]="form" (ngSubmit)="create()">
          <header class="bea-stock-fiche__banner">
            <img src="/brand/icon-bea-white.png" width="48" height="48" alt="" />
            <div>
              <strong>Banque El Amana</strong>
              <span>Service Moyens Généraux — Expression de besoin</span>
            </div>
          </header>
          <div class="bea-stock-fiche__meta">
            <label>
              Agence
              <select formControlName="agence_id">
                @for (a of agences(); track a.id) {
                  <option [value]="a.id">{{ a.libelle }}</option>
                }
              </select>
            </label>
            <label>Département <input formControlName="departement" /></label>
            <label>Fonction <input formControlName="fonction" /></label>
          </div>
          <table class="bea-stock-table" formArrayName="lignes">
            <thead>
              <tr>
                <th>Désignation</th>
                <th>Qté demandée</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (ctrl of lignes.controls; track $index; let i = $index) {
                <tr [formGroupName]="i">
                  <td><input formControlName="designation" list="articles-list" /></td>
                  <td><input type="number" formControlName="quantite_demandee" min="0.001" step="0.001" /></td>
                  <td>
                    <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="removeLigne(i)">×</button>
                  </td>
                </tr>
              }
            </tbody>
          </table>
          <datalist id="articles-list">
            @for (a of articles(); track a.id) {
              <option [value]="a.designation"></option>
            }
          </datalist>
          <div class="bea-stock-fiche__actions">
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="addLigne()">+ Ligne</button>
            <button type="submit" class="bea-admin-btn" [disabled]="form.invalid || saving()">Enregistrer brouillon</button>
          </div>
        </form>
      }

      @if (mode() === 'detail' && current(); as d) {
        <article class="bea-stock-fiche">
          <header class="bea-stock-fiche__banner">
            <img src="/brand/icon-bea-white.png" width="48" height="48" alt="" />
            <div>
              <strong>{{ d.reference }}</strong>
              <span>{{ d.agence_libelle_snapshot }} — {{ d.statut }}</span>
            </div>
          </header>
          <p>Demandeur : {{ d.demandeur_nom }} — Date : {{ d.date_demande }}</p>
          <table class="bea-stock-table">
            <thead>
              <tr>
                <th>Désignation</th>
                <th>Qté demandée</th>
                <th>Qté accordée</th>
              </tr>
            </thead>
            <tbody>
              @for (l of d.lignes; track l.id) {
                <tr>
                  <td>{{ l.designation }}</td>
                  <td>{{ l.quantite_demandee }}</td>
                  <td>{{ l.quantite_accordee ?? '—' }}</td>
                </tr>
              }
            </tbody>
          </table>
          <div class="bea-stock-fiche__visas">
            <div>Visa Agence concernée</div>
            <div>Visa Sce Moyens Généraux</div>
          </div>
          <div class="bea-stock-fiche__actions">
            @if (d.statut === 'BROUILLON') {
              <button type="button" class="bea-admin-btn" (click)="transition('soumettre')">Soumettre</button>
            }
            @if (d.statut === 'SOUMIS') {
              <button type="button" class="bea-admin-btn" (click)="transition('visa_agence')">Visa agence</button>
            }
            @if (d.statut === 'VISA_AGENCE') {
              <button type="button" class="bea-admin-btn" (click)="transition('visa_mg')">Visa MG + sortie stock</button>
            }
            @if (d.statut !== 'CLOTUREE' && d.statut !== 'ANNULEE' && d.statut !== 'REJETEE') {
              <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="transition('rejeter')">Rejeter</button>
            }
            <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/stock-fournitures/demandes">Retour liste</a>
          </div>
        </article>
      }

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }
    </section>
  `,
})
export class StockDemandesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly mode = signal<'list' | 'create' | 'detail'>('list');
  readonly demandes = signal<Demande[]>([]);
  readonly current = signal<Demande | null>(null);
  readonly agences = signal<Agence[]>([]);
  readonly articles = signal<Article[]>([]);
  readonly saving = signal(false);
  readonly erreur = signal('');

  readonly form = this.fb.nonNullable.group({
    agence_id: ['', Validators.required],
    departement: [''],
    fonction: [''],
    lignes: this.fb.array([this.newLigne()]),
  });

  get lignes(): FormArray {
    return this.form.get('lignes') as FormArray;
  }

  ngOnInit(): void {
    this.api.get<Agence[]>('/mg/stock/agences').subscribe((a) => {
      this.agences.set(a);
      if (a[0]) this.form.patchValue({ agence_id: a[0].id });
    });
    this.api.get<Article[]>('/mg/stock/articles').subscribe((rows) => this.articles.set(rows));

    this.route.paramMap.subscribe((params) => {
      const id = params.get('id');
      if (this.router.url.endsWith('/nouvelle')) {
        this.mode.set('create');
        return;
      }
      if (id) {
        this.mode.set('detail');
        this.loadOne(id);
        return;
      }
      this.mode.set('list');
      this.loadList();
    });
  }

  newLigne() {
    return this.fb.nonNullable.group({
      designation: ['', Validators.required],
      quantite_demandee: [1, Validators.required],
      article_id: [null as string | null],
    });
  }

  addLigne(): void {
    this.lignes.push(this.newLigne());
  }

  removeLigne(i: number): void {
    if (this.lignes.length > 1) this.lignes.removeAt(i);
  }

  loadList(): void {
    this.api.get<Demande[]>('/mg/stock/demandes').subscribe((rows) => this.demandes.set(rows));
  }

  loadOne(id: string): void {
    this.api.get<Demande>(`/mg/stock/demandes/${id}`).subscribe({
      next: (d) => this.current.set(d),
      error: () => this.erreur.set('Demande introuvable'),
    });
  }

  create(): void {
    if (this.form.invalid) return;
    this.saving.set(true);
    const raw = this.form.getRawValue();
    const lignes = raw.lignes.map((l) => {
      const match = this.articles().find((a) => a.designation === l.designation);
      return {
        designation: l.designation,
        quantite_demandee: l.quantite_demandee,
        article_id: match?.id ?? null,
      };
    });
    this.api
      .post<Demande>('/mg/stock/demandes', {
        agence_id: raw.agence_id,
        departement: raw.departement || null,
        fonction: raw.fonction || null,
        lignes,
      })
      .subscribe({
        next: (d) => {
          this.saving.set(false);
          void this.router.navigate(['/stock-fournitures/demandes', d.id]);
        },
        error: (err) => {
          this.erreur.set(err?.error?.detail || 'Création refusée');
          this.saving.set(false);
        },
      });
  }

  transition(action: string): void {
    const d = this.current();
    if (!d) return;
    this.api.post<Demande>(`/mg/stock/demandes/${d.id}/transition`, { action }).subscribe({
      next: (updated) => this.current.set(updated),
      error: (err) => this.erreur.set(err?.error?.detail || 'Transition refusée'),
    });
  }
}
