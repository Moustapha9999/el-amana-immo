import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';

interface Categorie {
  id: string;
  code: string;
  libelle: string;
  actif: boolean;
  justificatif_obligatoire: boolean;
  plafond: number | null;
}
interface Parametre {
  id: string;
  cle: string;
  valeur: string;
  libelle: string | null;
}

@Component({
  selector: 'bea-notes-parametres',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule],
  template: `
    <section class="bea-mg bea-nf">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Administration</p>
          <h1>Paramètres notes de frais</h1>
        </div>
        <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/notes-frais">Dashboard</a>
      </header>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }
      @if (msg()) {
        <p class="bea-stock-page__ok">{{ msg() }}</p>
      }

      <div class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Catégories</h2></div>
        <div class="bea-mg__table-scroll">
          <table class="bea-mg__table">
            <thead>
              <tr><th>Code</th><th>Libellé</th><th>Actif</th><th>Justif.</th><th>Plafond</th><th></th></tr>
            </thead>
            <tbody>
              @for (c of categories(); track c.id) {
                <tr>
                  <td><code class="bea-mg__code">{{ c.code }}</code></td>
                  <td>{{ c.libelle }}</td>
                  <td>{{ c.actif ? 'Oui' : 'Non' }}</td>
                  <td>{{ c.justificatif_obligatoire ? 'Oui' : 'Non' }}</td>
                  <td>{{ c.plafond ?? '—' }}</td>
                  <td class="bea-mg__actions-cell">
                    @if (c.actif) {
                      <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="deactivate(c.id)">
                        Désactiver
                      </button>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        <form class="bea-mg__modal-body bea-mg__grid" [formGroup]="catForm" (ngSubmit)="addCat()">
          <label>Code <input formControlName="code" /></label>
          <label>Libellé <input formControlName="libelle" /></label>
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="catForm.invalid">
            Ajouter
          </button>
        </form>
      </div>

      <div class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Paramètres</h2></div>
        <div class="bea-mg__table-scroll">
          <table class="bea-mg__table">
            <thead><tr><th>Clé</th><th>Libellé</th><th>Valeur</th><th></th></tr></thead>
            <tbody>
              @for (p of parametres(); track p.id) {
                <tr>
                  <td><code class="bea-mg__code">{{ p.cle }}</code></td>
                  <td>{{ p.libelle || '—' }}</td>
                  <td>
                    <input
                      [value]="p.valeur"
                      (change)="saveParam(p.cle, $any($event.target).value)"
                      style="width:100%;padding:0.35rem;border:1.5px solid #475569;border-radius:0.4rem"
                    />
                  </td>
                  <td></td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>
    </section>
  `,
})
export class NotesParametresComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);

  readonly categories = signal<Categorie[]>([]);
  readonly parametres = signal<Parametre[]>([]);
  readonly erreur = signal('');
  readonly msg = signal('');

  readonly catForm = this.fb.nonNullable.group({
    code: ['', Validators.required],
    libelle: ['', Validators.required],
  });

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.api.get<Categorie[]>('/mg/notes-frais/categories').subscribe({
      next: (c) => this.categories.set(c),
      error: () => this.erreur.set('Chargement catégories impossible (permission settings ?)'),
    });
    this.api.get<Parametre[]>('/mg/notes-frais/parametres').subscribe({
      next: (p) => this.parametres.set(p),
      error: () => undefined,
    });
  }

  addCat(): void {
    if (this.catForm.invalid) return;
    this.api.post('/mg/notes-frais/categories', this.catForm.getRawValue()).subscribe({
      next: () => {
        this.msg.set('Catégorie créée.');
        this.catForm.reset({ code: '', libelle: '' });
        this.reload();
      },
      error: (err) => this.erreur.set(err?.error?.detail || 'Création refusée'),
    });
  }

  deactivate(id: string): void {
    this.api.delete(`/mg/notes-frais/categories/${id}`).subscribe({
      next: () => {
        this.msg.set('Catégorie désactivée.');
        this.reload();
      },
      error: () => this.erreur.set('Désactivation refusée'),
    });
  }

  saveParam(cle: string, valeur: string): void {
    this.api.patch(`/mg/notes-frais/parametres/${cle}`, { valeur }).subscribe({
      next: () => this.msg.set(`Paramètre ${cle} mis à jour.`),
      error: () => this.erreur.set('Mise à jour refusée'),
    });
  }
}
