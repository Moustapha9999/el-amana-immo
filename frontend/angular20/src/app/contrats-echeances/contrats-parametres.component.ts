import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import { HttpErrorResponse } from '@angular/common/http';

interface Param {
  cle: string;
  valeur: string;
  libelle: string | null;
}

interface TypeContrat {
  id: string;
  code: string;
  libelle: string;
  actif: boolean;
}

@Component({
  selector: 'bea-contrats-parametres',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule],
  template: `
    <section class="bea-mg bea-nf bea-ct">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Administration</p>
          <h1>Paramètres contrats</h1>
        </div>
        <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/contrats-echeances/dashboard">Dashboard</a>
      </header>

      @if (erreur()) {
        <p class="bea-stock-page__error">{{ erreur() }}</p>
      }
      @if (msg()) {
        <p class="bea-stock-page__ok">{{ msg() }}</p>
      }

      <form class="bea-mg__panel bea-ct-panel bea-ct-section" (ngSubmit)="ajouterParam()">
        <div class="bea-mg__panel-top"><h2>Nouveau paramètre</h2></div>
        <div class="bea-mg__modal-body bea-ct-grid">
          <label>Libellé <input [(ngModel)]="nouveauParam.libelle" name="pl" /></label>
          <label>Clé <input [(ngModel)]="nouveauParam.cle" name="pc" placeholder="contrats.exemple" /></label>
          <label>Valeur <input [(ngModel)]="nouveauParam.valeur" name="pv" /></label>
        </div>
        <div class="bea-mg__actions" style="padding: 0 1rem 1rem">
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary">Ajouter</button>
        </div>
      </form>

      <div class="bea-mg__panel bea-ct-panel">
        <div class="bea-mg__panel-top"><h2>Délais d’alerte et numérotation</h2></div>
        <div class="bea-mg__table-scroll">
          <table class="bea-mg__table">
            <thead><tr><th>Paramètre</th><th>Valeur</th><th></th></tr></thead>
            <tbody>
              @for (p of params(); track p.cle; let i = $index) {
                <tr class="bea-ct-row" [style.animation-delay.ms]="i * 40">
                  <td>
                    <input [(ngModel)]="p.libelle" [name]="'lib-' + p.cle" />
                    <small>{{ p.cle }}</small>
                  </td>
                  <td><input [(ngModel)]="p.valeur" [name]="'val-' + p.cle" /></td>
                  <td class="bea-mg__actions-cell">
                    <button type="button" class="bea-mg__icon-btn" title="Enregistrer" (click)="save(p)"><mat-icon>save</mat-icon></button>
                    <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" (click)="supprimerParam(p)"><mat-icon>delete</mat-icon></button>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="3">
                    <div class="bea-ct-empty"><mat-icon>tune</mat-icon><p>Aucun paramètre.</p></div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>

      <form class="bea-mg__panel bea-ct-panel bea-ct-section" (ngSubmit)="ajouterType()">
        <div class="bea-mg__panel-top"><h2>Nouveau type</h2></div>
        <div class="bea-mg__modal-body bea-ct-grid">
          <label>Code <input [(ngModel)]="nouveauType.code" name="tc" placeholder="HEBERGEMENT" /></label>
          <label>Libellé <input [(ngModel)]="nouveauType.libelle" name="tl" /></label>
        </div>
        <div class="bea-mg__actions" style="padding: 0 1rem 1rem">
          <button type="submit" class="bea-mg__btn bea-mg__btn--primary">Ajouter</button>
        </div>
      </form>

      <div class="bea-mg__panel bea-ct-panel">
        <div class="bea-mg__panel-top"><h2>Types de contrats</h2></div>
        <div class="bea-mg__table-scroll">
          <table class="bea-mg__table">
            <thead><tr><th>Code</th><th>Libellé</th><th>Actif</th><th></th></tr></thead>
            <tbody>
              @for (t of types(); track t.id; let i = $index) {
                <tr class="bea-ct-row" [style.animation-delay.ms]="i * 35">
                  <td><code class="bea-mg__code">{{ t.code }}</code></td>
                  <td><input [(ngModel)]="t.libelle" [name]="'ty-' + t.id" /></td>
                  <td>
                    <button type="button" class="bea-ct-badge" [attr.data-tone]="t.actif ? 'ACTIF' : 'SUSPENDU'" (click)="basculerType(t)">
                      {{ t.actif ? 'Actif' : 'Inactif' }}
                    </button>
                  </td>
                  <td class="bea-mg__actions-cell">
                    <button type="button" class="bea-mg__icon-btn" title="Enregistrer" (click)="sauverType(t)"><mat-icon>save</mat-icon></button>
                    <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" (click)="supprimerType(t)"><mat-icon>delete</mat-icon></button>
                  </td>
                </tr>
              } @empty {
                <tr><td colspan="4">Aucun type.</td></tr>
              }
            </tbody>
          </table>
        </div>
      </div>
    </section>
  `,
})
export class ContratsParametresComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);
  readonly params = signal<Param[]>([]);
  readonly types = signal<TypeContrat[]>([]);
  readonly erreur = signal<string | null>(null);
  readonly msg = signal<string | null>(null);
  nouveauParam = { cle: '', valeur: '', libelle: '' };
  nouveauType = { code: '', libelle: '' };

  ngOnInit(): void {
    this.api.get<Param[]>('/mg/contrats/parametres').subscribe({
      next: (rows) => this.params.set(rows),
      error: () => this.erreur.set('Paramètres indisponibles.'),
    });
    this.api.get<TypeContrat[]>('/mg/contrats/types').subscribe({
      next: (rows) => this.types.set(rows),
      error: () => undefined,
    });
  }

  save(p: Param): void {
    this.msg.set(null);
    this.api.patch<Param>(`/mg/contrats/parametres/${p.cle}`, { valeur: p.valeur, libelle: p.libelle }).subscribe({
      next: () => this.msg.set('Paramètre enregistré.'),
      error: (e) => this.fail(e),
    });
  }

  ajouterParam(): void {
    if (!this.nouveauParam.cle.trim()) {
      this.erreur.set('La clé est obligatoire.');
      return;
    }
    this.api.post<Param>('/mg/contrats/parametres', this.nouveauParam).subscribe({
      next: () => {
        this.nouveauParam = { cle: '', valeur: '', libelle: '' };
        this.msg.set('Paramètre ajouté.');
        this.reload();
      },
      error: (e) => this.fail(e),
    });
  }

  supprimerParam(p: Param): void {
    this.dialogs.confirmAction('suppression', `Supprimer le paramètre « ${p.libelle || p.cle} » ?`).subscribe((ok) => {
      if (!ok) return;
      this.api.delete(`/mg/contrats/parametres/${p.cle}`).subscribe({
        next: () => this.reload(),
        error: (e) => this.fail(e),
      });
    });
  }

  ajouterType(): void {
    this.api.post<TypeContrat>('/mg/contrats/types', this.nouveauType).subscribe({
      next: () => {
        this.nouveauType = { code: '', libelle: '' };
        this.msg.set('Type ajouté.');
        this.reload();
      },
      error: (e) => this.fail(e),
    });
  }

  sauverType(t: TypeContrat): void {
    this.api.patch<TypeContrat>(`/mg/contrats/types/${t.id}`, { libelle: t.libelle, actif: t.actif }).subscribe({
      next: () => this.msg.set('Type enregistré.'),
      error: (e) => this.fail(e),
    });
  }

  basculerType(t: TypeContrat): void {
    this.api.patch<TypeContrat>(`/mg/contrats/types/${t.id}`, { actif: !t.actif }).subscribe({
      next: () => this.reload(),
      error: (e) => this.fail(e),
    });
  }

  supprimerType(t: TypeContrat): void {
    this.dialogs
      .confirmAction('suppression', `Supprimer le type « ${t.libelle} » ? S’il est déjà utilisé, il sera seulement désactivé.`)
      .subscribe((ok) => {
        if (!ok) return;
        this.api.delete<{ desactive: boolean }>(`/mg/contrats/types/${t.id}`).subscribe({
          next: (r) => {
            this.msg.set(r.desactive ? 'Type utilisé : il a été désactivé.' : 'Type supprimé.');
            this.reload();
          },
          error: (e) => this.fail(e),
        });
      });
  }

  private reload(): void {
    this.ngOnInit();
  }

  private fail(err: unknown): void {
    const detail = err instanceof HttpErrorResponse ? err.error?.detail : null;
    this.erreur.set(typeof detail === 'string' ? detail : 'Opération refusée.');
  }
}
