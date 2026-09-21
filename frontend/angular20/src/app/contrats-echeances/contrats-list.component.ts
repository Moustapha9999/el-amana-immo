import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';

interface Contrat {
  id: string;
  reference: string;
  titre: string;
  fournisseur_snapshot: string | null;
  date_debut: string;
  date_fin: string | null;
  prochain_echeance: string | null;
  montant: number | null;
  statut: string;
}

@Component({
  selector: 'bea-contrats-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, DecimalPipe],
  template: `
    <section class="bea-stock-page">
      <header class="bea-stock-page__head">
        <div>
          <p class="bea-stock-page__kicker">Contrats &amp; échéances</p>
          <h1>{{ titre() }}</h1>
        </div>
        <a class="bea-admin-btn" routerLink="/contrats-echeances/nouveau">Nouveau contrat</a>
      </header>

      @if (mode() === 'list') {
        <table class="bea-stock-table">
          <thead>
            <tr><th>Réf.</th><th>Titre</th><th>Fournisseur</th><th>Fin / échéance</th><th>Montant</th><th>Statut</th></tr>
          </thead>
          <tbody>
            @for (c of contrats(); track c.id) {
              <tr>
                <td>{{ c.reference }}</td>
                <td>{{ c.titre }}</td>
                <td>{{ c.fournisseur_snapshot || '—' }}</td>
                <td>{{ c.prochain_echeance || c.date_fin || '—' }}</td>
                <td>{{ c.montant != null ? (c.montant | number:'1.2-2') : '—' }}</td>
                <td>{{ c.statut }}</td>
              </tr>
            }
          </tbody>
        </table>
      } @else {
        <form class="bea-stock-form" [formGroup]="form" (ngSubmit)="save()">
          <div class="bea-stock-form__grid">
            <label>Titre <input formControlName="titre" /></label>
            <label>Fournisseur <input formControlName="fournisseur_snapshot" /></label>
            <label>Début <input type="date" formControlName="date_debut" /></label>
            <label>Fin <input type="date" formControlName="date_fin" /></label>
            <label>Prochaine échéance <input type="date" formControlName="prochain_echeance" /></label>
            <label>Montant <input type="number" formControlName="montant" /></label>
            <label>Périodicité
              <select formControlName="periodicite">
                <option value="MENSUEL">Mensuel</option>
                <option value="TRIMESTRIEL">Trimestriel</option>
                <option value="ANNUEL">Annuel</option>
                <option value="UNIQUE">Unique</option>
              </select>
            </label>
            <label>Alerte (jours) <input type="number" formControlName="alerte_jours" /></label>
          </div>
          <div class="bea-stock-form__actions">
            <button type="submit" class="bea-admin-btn">Enregistrer</button>
            <a routerLink="/contrats-echeances/liste">Retour</a>
          </div>
          @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
        </form>
      }
    </section>
  `,
})
export class ContratsListComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly mode = signal<'list' | 'edit'>('list');
  readonly titre = signal('Contrats');
  readonly contrats = signal<Contrat[]>([]);
  readonly erreur = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    titre: ['', Validators.required],
    fournisseur_snapshot: [''],
    date_debut: ['', Validators.required],
    date_fin: [''],
    prochain_echeance: [''],
    montant: [0 as number | null],
    periodicite: ['ANNUEL'],
    alerte_jours: [30],
  });

  ngOnInit(): void {
    const path = this.route.snapshot.routeConfig?.path ?? '';
    if (path === 'nouveau') {
      this.mode.set('edit');
      this.titre.set('Nouveau contrat');
      this.form.patchValue({ date_debut: new Date().toISOString().slice(0, 10) });
      return;
    }
    const url = path === 'alertes' ? '/mg/contrats/alertes' : '/mg/contrats';
    this.titre.set(path === 'alertes' ? 'Alertes d’échéance' : 'Liste des contrats');
    this.api.get<Contrat[]>(url).subscribe({
      next: (rows) => this.contrats.set(rows),
      error: () => this.erreur.set('Chargement impossible.'),
    });
  }

  save(): void {
    if (this.form.invalid) return;
    const raw = this.form.getRawValue();
    const body = {
      ...raw,
      date_fin: raw.date_fin || null,
      prochain_echeance: raw.prochain_echeance || null,
    };
    this.api.post('/mg/contrats', body).subscribe({
      next: () => void this.router.navigateByUrl('/contrats-echeances/liste'),
      error: () => this.erreur.set('Enregistrement impossible.'),
    });
  }
}
