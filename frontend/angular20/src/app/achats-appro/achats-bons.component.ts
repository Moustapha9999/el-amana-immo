import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormArray, FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';

interface Bon {
  id: string;
  reference: string;
  date_bc: string;
  fournisseur_raison_sociale: string | null;
  statut: string;
  total_ht: number;
  lignes?: { description: string; quantite: number; prix_unitaire: number; uom: string }[];
}

@Component({
  selector: 'bea-achats-bons',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, DecimalPipe, MgGedPanelComponent],
  template: `
    <section class="bea-stock-page">
      <header class="bea-stock-page__head">
        <div>
          <p class="bea-stock-page__kicker">Achats &amp; Approvisionnements</p>
          <h1>Bons de commande</h1>
        </div>
        <a class="bea-admin-btn" routerLink="/achats-appro/nouveau">Nouveau BC</a>
      </header>

      @if (mode() === 'list') {
        @if (erreur()) {
          <p class="bea-stock-page__error">{{ erreur() }}</p>
        }
        <table class="bea-stock-table">
          <thead>
            <tr><th>Réf.</th><th>Date</th><th>Fournisseur</th><th>Total HT</th><th>Statut</th><th></th></tr>
          </thead>
          <tbody>
            @for (b of bons(); track b.id) {
              <tr>
                <td>{{ b.reference }}</td>
                <td>{{ b.date_bc }}</td>
                <td>{{ b.fournisseur_raison_sociale || '—' }}</td>
                <td>{{ b.total_ht | number:'1.2-2' }}</td>
                <td>{{ b.statut }}</td>
                <td><a [routerLink]="['/achats-appro/bons', b.id]">Ouvrir</a></td>
              </tr>
            }
          </tbody>
        </table>
      } @else {
        <form class="bea-stock-form" [formGroup]="form" (ngSubmit)="save()">
          <div class="bea-stock-form__grid">
            <label>Date <input type="date" formControlName="date_bc" /></label>
            <label>Fournisseur <input formControlName="fournisseur_raison_sociale" /></label>
            <label>NIF <input formControlName="fournisseur_nif" /></label>
            <label>Téléphone <input formControlName="fournisseur_telephone" /></label>
            <label>Département <input formControlName="departement" /></label>
            <label>Acheteur <input formControlName="acheteur_nom" /></label>
            <label>Adresse facturation <input formControlName="adresse_facturation" /></label>
            <label>Adresse livraison <input formControlName="adresse_livraison" /></label>
          </div>
          <h2>Lignes</h2>
          <div formArrayName="lignes">
            @for (ctrl of lignes.controls; track $index; let i = $index) {
              <div class="bea-stock-form__grid" [formGroupName]="i">
                <label>Description <input formControlName="description" /></label>
                <label>Qté <input type="number" formControlName="quantite" /></label>
                <label>PU <input type="number" formControlName="prix_unitaire" /></label>
                <label>UOM <input formControlName="uom" /></label>
              </div>
            }
          </div>
          <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="addLigne()">+ Ligne</button>
          <div class="bea-stock-form__actions">
            <button type="submit" class="bea-admin-btn">Enregistrer</button>
            @if (bonId()) {
              <button type="button" class="bea-admin-btn" (click)="transition('soumettre')">Soumettre</button>
              <button type="button" class="bea-admin-btn" (click)="transition('visa_mg')">Visa MG</button>
              <button type="button" class="bea-admin-btn" (click)="transition('visa_dr')">Visa DR</button>
              <button type="button" class="bea-admin-btn" (click)="transition('valider')">Valider</button>
            }
            @if (bonStatut() === 'VALIDE' || bonStatut() === 'PARTIEL') {
              <a class="bea-admin-btn" routerLink="/stock-fournitures/entrees">Réception stock</a>
            }
            <a routerLink="/achats-appro/bons">Retour</a>
          </div>
          @if (bonId(); as id) {
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="downloadPdf()">PDF</button>
            <bea-mg-ged moduleCode="achats-appro" entity="bon_commande" [entityId]="id" />
          }
          @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
        </form>
      }
    </section>
  `,
})
export class AchatsBonsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly mode = signal<'list' | 'edit'>('list');
  readonly bons = signal<Bon[]>([]);
  readonly bonId = signal<string | null>(null);
  readonly bonStatut = signal<string | null>(null);
  readonly erreur = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    date_bc: ['', Validators.required],
    fournisseur_raison_sociale: [''],
    fournisseur_nif: [''],
    fournisseur_telephone: [''],
    departement: ['Siege'],
    acheteur_nom: [''],
    adresse_facturation: ['Banque El Amana - Siège Central'],
    adresse_livraison: ['SIEGE'],
    lignes: this.fb.array([this.newLigne()]),
  });

  get lignes(): FormArray {
    return this.form.get('lignes') as FormArray;
  }

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    const path = this.route.snapshot.routeConfig?.path ?? '';
    if (path === 'nouveau' || id) {
      this.mode.set('edit');
      this.bonId.set(id);
      if (id) this.loadOne(id);
      else this.form.patchValue({ date_bc: new Date().toISOString().slice(0, 10) });
    } else {
      this.loadList();
    }
  }

  newLigne() {
    return this.fb.nonNullable.group({
      description: ['', Validators.required],
      quantite: [1, Validators.required],
      prix_unitaire: [0, Validators.required],
      uom: ['U'],
    });
  }

  addLigne(): void {
    this.lignes.push(this.newLigne());
  }

  loadList(): void {
    this.api.get<Bon[]>('/mg/achats/bons').subscribe({
      next: (rows) => this.bons.set(rows),
      error: () => this.erreur.set('Impossible de charger les bons.'),
    });
  }

  loadOne(id: string): void {
    this.api.get<Bon>(`/mg/achats/bons/${id}`).subscribe({
      next: (b) => {
        this.bonStatut.set(b.statut);
        this.form.patchValue({
          date_bc: b.date_bc,
          fournisseur_raison_sociale: b.fournisseur_raison_sociale ?? '',
        });
      },
      error: () => this.erreur.set('Bon introuvable.'),
    });
  }

  save(): void {
    if (this.form.invalid) return;
    const body = this.form.getRawValue();
    const req = this.bonId()
      ? this.api.patch<Bon>(`/mg/achats/bons/${this.bonId()}`, body)
      : this.api.post<Bon>('/mg/achats/bons', body);
    req.subscribe({
      next: (b) => void this.router.navigateByUrl(`/achats-appro/bons/${b.id}`),
      error: () => this.erreur.set('Enregistrement impossible.'),
    });
  }

  transition(action: string): void {
    const id = this.bonId();
    if (!id) return;
    this.api.post(`/mg/achats/bons/${id}/transition`, { action }).subscribe({
      next: () => this.loadOne(id),
      error: () => this.erreur.set('Transition refusée.'),
    });
  }

  downloadPdf(): void {
    const id = this.bonId();
    if (!id) return;
    this.api.download(`/mg/achats/bons/${id}/pdf`).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `bc-${id}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set('Export PDF impossible.'),
    });
  }
}
