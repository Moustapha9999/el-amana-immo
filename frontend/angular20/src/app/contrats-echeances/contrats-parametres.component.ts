import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { describeApiErrorAsync } from '../core/feedback/api-error';
import { FeedbackService } from '../core/feedback/feedback.service';
import { ApiService } from '../core/services/api.service';

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

const PARAMS_SYSTEME = new Set([
  'contrats.taux_tva',
  'contrats.alerte_urgent',
  'contrats.alerte_attention',
  'contrats.alerte_info',
  'contrats.echeance_due_jours',
  'contrats.ged_taille_max_mo',
  'contrats.prefixe',
]);

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
          <p class="bea-ct-head__sub">TVA par défaut, seuils d’alerte, fenêtre « due », taille maximale GED, numérotation et types de contrats.</p>
        </div>
        <a class="bea-mg__btn bea-mg__btn--ghost" routerLink="/contrats-echeances/dashboard"><mat-icon>dashboard</mat-icon> Tableau de bord</a>
      </header>

      <div class="bea-ct-dash__grid">
        <div class="bea-mg__panel bea-ct-panel">
          <div class="bea-mg__panel-top"><h2><mat-icon>tune</mat-icon> Paramètres</h2></div>
          <div class="bea-mg__table-scroll">
            <table class="bea-mg__table bea-ct-table">
              <thead><tr><th>Paramètre</th><th>Valeur</th><th class="is-actions"></th></tr></thead>
              <tbody>
                @for (p of params(); track p.cle) {
                  <tr class="bea-ct-row">
                    <td class="is-wide">
                      <input class="bea-ct-cell-input" [(ngModel)]="p.libelle" [name]="'lib-' + p.cle" [attr.aria-label]="'Libellé ' + p.cle" />
                      <small class="bea-ct-sub"><code>{{ p.cle }}</code>@if (systeme(p.cle)) { · système }</small>
                    </td>
                    <td><input class="bea-ct-cell-input" [(ngModel)]="p.valeur" [name]="'val-' + p.cle" [attr.aria-label]="'Valeur ' + p.cle" /></td>
                    <td class="bea-mg__actions-cell is-nowrap">
                      <button type="button" class="bea-mg__icon-btn" title="Enregistrer" [disabled]="busy()" (click)="save(p)"><mat-icon>save</mat-icon></button>
                      @if (!systeme(p.cle)) {
                        <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" [disabled]="busy()" (click)="supprimerParam(p)"><mat-icon>delete</mat-icon></button>
                      }
                    </td>
                  </tr>
                } @empty {
                  <tr><td colspan="3"><div class="bea-ct-empty"><mat-icon>tune</mat-icon><p>Aucun paramètre.</p></div></td></tr>
                }
              </tbody>
            </table>
          </div>
          <form class="bea-ct-grid bea-ct-inline" (ngSubmit)="ajouterParam()">
            <label>Libellé <input [(ngModel)]="nouveauParam.libelle" name="pl" /></label>
            <label>Clé * <input [(ngModel)]="nouveauParam.cle" name="pc" placeholder="contrats.exemple" /></label>
            <label>Valeur <input [(ngModel)]="nouveauParam.valeur" name="pv" /></label>
            <div class="bea-ct-inline__btns">
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || !nouveauParam.cle.trim()"><mat-icon>add</mat-icon> Ajouter</button>
            </div>
          </form>
        </div>

        <div class="bea-mg__panel bea-ct-panel">
          <div class="bea-mg__panel-top"><h2><mat-icon>category</mat-icon> Types de contrats</h2></div>
          <div class="bea-mg__table-scroll">
            <table class="bea-mg__table bea-ct-table">
              <thead><tr><th>Code</th><th>Libellé</th><th>Actif</th><th class="is-actions"></th></tr></thead>
              <tbody>
                @for (t of types(); track t.id) {
                  <tr class="bea-ct-row">
                    <td><code class="bea-mg__code">{{ t.code }}</code></td>
                    <td><input class="bea-ct-cell-input" [(ngModel)]="t.libelle" [name]="'ty-' + t.id" [attr.aria-label]="'Libellé ' + t.code" /></td>
                    <td>
                      <button type="button" class="bea-ct-badge bea-ct-badge--btn" [attr.data-tone]="t.actif ? 'ACTIF' : 'SUSPENDU'" [disabled]="busy()" (click)="basculerType(t)">
                        {{ t.actif ? 'Actif' : 'Inactif' }}
                      </button>
                    </td>
                    <td class="bea-mg__actions-cell is-nowrap">
                      <button type="button" class="bea-mg__icon-btn" title="Enregistrer" [disabled]="busy()" (click)="sauverType(t)"><mat-icon>save</mat-icon></button>
                      <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" [disabled]="busy()" (click)="supprimerType(t)"><mat-icon>delete</mat-icon></button>
                    </td>
                  </tr>
                } @empty {
                  <tr><td colspan="4"><div class="bea-ct-empty"><mat-icon>category</mat-icon><p>Aucun type.</p></div></td></tr>
                }
              </tbody>
            </table>
          </div>
          <form class="bea-ct-grid bea-ct-inline" (ngSubmit)="ajouterType()">
            <label>Code * <input [(ngModel)]="nouveauType.code" name="tc" placeholder="HEBERGEMENT" /></label>
            <label>Libellé * <input [(ngModel)]="nouveauType.libelle" name="tl" /></label>
            <div class="bea-ct-inline__btns">
              <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || !nouveauType.code.trim() || !nouveauType.libelle.trim()"><mat-icon>add</mat-icon> Ajouter</button>
            </div>
          </form>
        </div>
      </div>
    </section>
  `,
})
export class ContratsParametresComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly params = signal<Param[]>([]);
  readonly types = signal<TypeContrat[]>([]);
  readonly busy = signal(false);
  nouveauParam = { cle: '', valeur: '', libelle: '' };
  nouveauType = { code: '', libelle: '' };

  ngOnInit(): void {
    this.reload();
  }

  systeme(cle: string): boolean {
    return PARAMS_SYSTEME.has(cle);
  }

  save(p: Param): void {
    this.feedback
      .run(() => this.api.patch<Param>(`/mg/contrats/parametres/${p.cle}`, { valeur: p.valeur, libelle: p.libelle }), {
        loading: 'Enregistrement…',
        busy: this.busy,
        errorTitle: 'Paramètre refusé',
        success: (r) => ({ title: 'Paramètre enregistré', details: [{ label: r.libelle || r.cle, value: r.valeur }] }),
      })
      .subscribe();
  }

  ajouterParam(): void {
    const body = { cle: this.nouveauParam.cle.trim(), valeur: this.nouveauParam.valeur, libelle: this.nouveauParam.libelle.trim() || null };
    this.feedback
      .run(() => this.api.post<Param>('/mg/contrats/parametres', body), {
        loading: 'Ajout…',
        busy: this.busy,
        idempotent: true,
        errorTitle: 'Ajout impossible',
        success: (r) => ({ title: 'Paramètre ajouté', details: [{ label: 'Clé', value: r.cle }] }),
      })
      .subscribe(() => {
        this.nouveauParam = { cle: '', valeur: '', libelle: '' };
        this.reload();
      });
  }

  supprimerParam(p: Param): void {
    this.feedback
      .run(() => this.api.delete(`/mg/contrats/parametres/${p.cle}`), {
        confirm: { action: 'suppression', message: `Supprimer le paramètre « ${p.libelle || p.cle} » ?` },
        loading: 'Suppression…',
        busy: this.busy,
        errorTitle: 'Suppression impossible',
        success: { title: 'Paramètre supprimé' },
      })
      .subscribe(() => this.reload());
  }

  ajouterType(): void {
    const body = { code: this.nouveauType.code.trim().toUpperCase(), libelle: this.nouveauType.libelle.trim() };
    this.feedback
      .run(() => this.api.post<TypeContrat>('/mg/contrats/types', body), {
        loading: 'Ajout…',
        busy: this.busy,
        idempotent: true,
        errorTitle: 'Ajout impossible',
        success: (t) => ({ title: 'Type ajouté', details: [{ label: t.code, value: t.libelle }] }),
      })
      .subscribe(() => {
        this.nouveauType = { code: '', libelle: '' };
        this.reload();
      });
  }

  sauverType(t: TypeContrat): void {
    this.feedback
      .run(() => this.api.patch<TypeContrat>(`/mg/contrats/types/${t.id}`, { libelle: t.libelle, actif: t.actif }), {
        loading: 'Enregistrement…',
        busy: this.busy,
        errorTitle: 'Enregistrement impossible',
        success: { title: 'Type enregistré' },
      })
      .subscribe();
  }

  basculerType(t: TypeContrat): void {
    this.feedback
      .run(() => this.api.patch<TypeContrat>(`/mg/contrats/types/${t.id}`, { actif: !t.actif }), {
        loading: 'Mise à jour…',
        busy: this.busy,
        errorTitle: 'Mise à jour impossible',
        success: (r) => ({ title: r.actif ? 'Type activé' : 'Type désactivé', details: [{ label: r.code, value: r.libelle }] }),
      })
      .subscribe(() => this.reload());
  }

  supprimerType(t: TypeContrat): void {
    this.feedback
      .run(() => this.api.delete<{ desactive: boolean }>(`/mg/contrats/types/${t.id}`), {
        confirm: { action: 'suppression', message: `Supprimer le type « ${t.libelle} » ?`, hint: 'S’il est déjà utilisé par des contrats, il sera seulement désactivé.' },
        loading: 'Suppression…',
        busy: this.busy,
        errorTitle: 'Suppression impossible',
        success: (r) => ({ title: r.desactive ? 'Type utilisé : désactivé' : 'Type supprimé' }),
      })
      .subscribe(() => this.reload());
  }

  private reload(): void {
    this.api.get<Param[]>('/mg/contrats/parametres').subscribe({
      next: (rows) => this.params.set(rows),
      error: (e) => void describeApiErrorAsync(e).then((info) => this.feedback.apiError(info, 'Paramètres indisponibles')),
    });
    this.api.get<TypeContrat[]>('/mg/contrats/types').subscribe({ next: (rows) => this.types.set(rows), error: () => undefined });
  }
}
