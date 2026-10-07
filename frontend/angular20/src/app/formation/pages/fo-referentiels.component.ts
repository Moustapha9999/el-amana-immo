import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router } from '@angular/router';
import { Observable } from 'rxjs';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { FormationUiComponent } from '../formation-ui.component';
import { DOMAINES, Domaine, Entite, FO_BASE, RefItem, correspond } from '../formation.models';
import { FormationStore } from '../formation.store';

type Onglet = Domaine | 'ENTITE';

interface Edition {
  id: string | null;
  libelle: string;
  description: string;
  ordre: number | null;
  perimetre_id: string;
  lieu_id: string;
}

@Component({
  selector: 'bea-fo-referentiels',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, FormationUiComponent],
  template: `
    <bea-fo-styles />
    <div class="bea-mg bea-fo">
      <header class="bea-mg__head bea-fo-head">
        <div class="bea-fo-head__txt">
          <p class="bea-stock-page__kicker">Formation &amp; Sensibilisation</p>
          <h1>Référentiels</h1>
          <p class="bea-fo-head__sub">Toutes les listes de choix du module. Une valeur utilisée ne se supprime pas : désactivez-la ou fusionnez-la avec une autre.</p>
        </div>
        <div class="bea-mg__actions">
          @if (gerer()) {
            <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="nouveau()"><mat-icon>add</mat-icon> Ajouter {{ domaine().label.toLowerCase() }}</button>
          }
        </div>
      </header>

      <nav class="bea-ct-tabs" style="margin-bottom:0.9rem">
        @for (d of domaines; track d.code) {
          <button type="button" [class.is-on]="onglet() === d.code" (click)="choisir(d.code)">
            <mat-icon>{{ d.icon }}</mat-icon> {{ d.pluriel }} <span class="bea-fx-count">{{ compte(d.code) }}</span>
          </button>
        }
      </nav>

      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top">
          <div><h2>{{ domaine().pluriel }}</h2>
            <p class="bea-fo-panel-sub">{{ onglet() === 'ENTITE' ? 'Chaque entité est rattachée à un périmètre (déduit automatiquement pour les employés) et à un lieu par défaut.' : 'Utilisation = nombre de formations ou d’employés qui y font référence.' }}</p></div>
          <div class="bea-fo-panel-top-actions">
            <label class="bea-mg__field" style="min-width:14rem"><mat-icon>search</mat-icon><input type="search" placeholder="Filtrer…" [(ngModel)]="q" /></label>
            <label class="bea-fo-check" style="font-size:0.8rem"><input type="checkbox" [(ngModel)]="inactifs" /> Afficher les inactifs</label>
          </div>
        </div>
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table bea-fo-table">
            <thead>
              <tr>
                <th>Libellé</th>
                @if (onglet() === 'ENTITE') { <th>Périmètre</th><th>Lieu par défaut</th> } @else { <th>Description</th> }
                <th class="is-num">Utilisation</th>
                <th>Statut</th>
                @if (gerer()) { <th style="width:11rem"></th> }
              </tr>
            </thead>
            <tbody>
              @if (!store.config()) {
                @for (i of [1, 2, 3, 4]; track i) { <tr>@for (j of [1, 2, 3, 4, 5]; track j) { <td><span class="bea-fx-skel"></span></td> }</tr> }
              } @else if (onglet() === 'ENTITE') {
                @for (e of entites(); track e.id; let i = $index) {
                  <tr class="bea-fx-row-in" [style.--i]="i < 30 ? i : 0" [class.is-muted]="!e.actif">
                    <td><strong>{{ e.libelle }}</strong></td>
                    <td><span class="bea-fo-tag">{{ e.perimetre || '—' }}</span></td>
                    <td>{{ e.lieu || '—' }}</td>
                    <td class="is-num">{{ e.usage ?? 0 }}</td>
                    <td><span class="bea-fo-badge" [attr.data-s]="e.actif ? 'ACTIF' : 'INACTIF'">{{ e.actif ? 'Actif' : 'Inactif' }}</span></td>
                    @if (gerer()) {
                      <td class="is-c">
                        <span class="bea-row-actions" style="display:inline-flex;gap:0.3rem">
                          <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="editerEntite(e)"><mat-icon>edit</mat-icon></button>
                          <button type="button" class="bea-mg__icon-btn" [title]="e.actif ? 'Désactiver' : 'Réactiver'" (click)="basculerEntite(e)"><mat-icon>{{ e.actif ? 'toggle_on' : 'toggle_off' }}</mat-icon></button>
                          @if (!e.usage) { <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" (click)="supprimerEntite(e)"><mat-icon>delete</mat-icon></button> }
                        </span>
                      </td>
                    }
                  </tr>
                } @empty {
                  <tr><td colspan="6"><div class="bea-fo-empty"><mat-icon>account_tree</mat-icon>Aucune entité</div></td></tr>
                }
              } @else {
                @for (r of refs(); track r.id; let i = $index) {
                  <tr class="bea-fx-row-in" [style.--i]="i < 30 ? i : 0" [class.is-muted]="!r.actif">
                    <td><strong>{{ r.libelle }}</strong></td>
                    <td>{{ r.description || '—' }}</td>
                    <td class="is-num">{{ r.usage }}</td>
                    <td><span class="bea-fo-badge" [attr.data-s]="r.actif ? 'ACTIF' : 'INACTIF'">{{ r.actif ? 'Actif' : 'Inactif' }}</span></td>
                    @if (gerer()) {
                      <td class="is-c">
                        <span class="bea-row-actions" style="display:inline-flex;gap:0.3rem">
                          <button type="button" class="bea-mg__icon-btn" title="Modifier" (click)="editer(r)"><mat-icon>edit</mat-icon></button>
                          <button type="button" class="bea-mg__icon-btn" [title]="r.actif ? 'Désactiver' : 'Réactiver'" (click)="basculer(r)"><mat-icon>{{ r.actif ? 'toggle_on' : 'toggle_off' }}</mat-icon></button>
                          <button type="button" class="bea-mg__icon-btn" title="Fusionner avec une autre valeur" (click)="fusion.set(r); cible = ''"><mat-icon>merge</mat-icon></button>
                          @if (!r.usage) { <button type="button" class="bea-mg__icon-btn bea-mg__icon-btn--danger" title="Supprimer" (click)="supprimer(r)"><mat-icon>delete</mat-icon></button> }
                        </span>
                      </td>
                    }
                  </tr>
                } @empty {
                  <tr><td colspan="5"><div class="bea-fo-empty"><mat-icon>label_off</mat-icon>Aucune valeur</div></td></tr>
                }
              }
            </tbody>
          </table>
        </div>
      </section>
    </div>

    @if (edition(); as ed) {
      <div class="bea-mg__backdrop" (click)="edition.set(null)"></div>
      <div class="bea-mg__modal bea-ct-modal" role="dialog" aria-modal="true">
        <header class="bea-ct-modal__head">
          <h2><mat-icon>{{ ed.id ? 'edit' : 'add_circle' }}</mat-icon> {{ ed.id ? 'Modifier' : 'Ajouter' }} — {{ domaine().label }}</h2>
          <button type="button" class="bea-ct-view__close" (click)="edition.set(null)" aria-label="Fermer"><mat-icon>close</mat-icon></button>
        </header>
        <form class="bea-ct-modal__body bea-fo-form" (ngSubmit)="enregistrer(ed)">
          <label>Libellé <em>*</em><input name="libelle" [(ngModel)]="ed.libelle" maxlength="200" required autofocus /></label>
          @if (onglet() === 'ENTITE') {
            <label>Périmètre <em>*</em>
              <select name="perimetre_id" [(ngModel)]="ed.perimetre_id" required>
                <option value="">— Choisir —</option>
                @for (p of store.refs('PERIMETRE'); track p.id) { <option [value]="p.id">{{ p.libelle }}</option> }
              </select>
            </label>
            <label>Lieu par défaut
              <select name="lieu_id" [(ngModel)]="ed.lieu_id">
                <option value="">— Aucun —</option>
                @for (l of store.refs('LIEU'); track l.id) { <option [value]="l.id">{{ l.libelle }}</option> }
              </select>
            </label>
          } @else {
            <label>Description<textarea name="description" [(ngModel)]="ed.description" maxlength="2000" rows="3"></textarea></label>
            @if (ed.id) { <label>Ordre d’affichage<input type="number" name="ordre" [(ngModel)]="ed.ordre" min="0" /></label> }
          }
          @if (ed.id && onglet() !== 'ENTITE') {
            <p class="bea-fo-hint">Le nouveau libellé s’applique à toutes les formations et à tous les rapports existants.</p>
          }
          <footer class="bea-ct-modal__foot">
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="edition.set(null)">Annuler</button>
            <button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || !ed.libelle.trim() || (onglet() === 'ENTITE' && !ed.perimetre_id)"><mat-icon>save</mat-icon> Enregistrer</button>
          </footer>
        </form>
      </div>
    }

    @if (fusion(); as src) {
      <div class="bea-mg__backdrop" (click)="fusion.set(null)"></div>
      <div class="bea-mg__modal bea-ct-modal" role="dialog" aria-modal="true">
        <header class="bea-ct-modal__head">
          <h2><mat-icon>merge</mat-icon> Fusionner « {{ src.libelle }} »</h2>
          <button type="button" class="bea-ct-view__close" (click)="fusion.set(null)" aria-label="Fermer"><mat-icon>close</mat-icon></button>
        </header>
        <div class="bea-ct-modal__body bea-fo-form">
          <p class="bea-fo-hint" style="font-size:0.85rem">Les {{ src.usage }} utilisation(s) de « {{ src.libelle }} » seront reportées sur la valeur choisie, puis « {{ src.libelle }} » sera supprimée. Utile pour corriger les doublons d’orthographe issus de l’Excel.</p>
          <label>Fusionner dans <em>*</em>
            <select [(ngModel)]="cible" name="cible">
              <option value="">— Choisir la valeur à conserver —</option>
              @for (r of autres(src); track r.id) { <option [value]="r.id">{{ r.libelle }}{{ r.actif ? '' : ' (inactif)' }}</option> }
            </select>
          </label>
        </div>
        <footer class="bea-ct-modal__foot">
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="fusion.set(null)">Annuler</button>
          <button type="button" class="bea-mg__btn bea-mg__btn--primary" [disabled]="!cible || busy()" (click)="fusionner(src)"><mat-icon>merge</mat-icon> Fusionner</button>
        </footer>
      </div>
    }
  `,
})
export class FoReferentielsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly store = inject(FormationStore);

  readonly domaines = DOMAINES;
  readonly onglet = signal<Onglet>('THEME');
  readonly edition = signal<Edition | null>(null);
  readonly fusion = signal<RefItem | null>(null);
  readonly busy = signal(false);
  private readonly qS = signal('');
  private readonly inactifsS = signal(true);
  cible = '';

  get q(): string { return this.qS(); }
  set q(v: string) { this.qS.set(v); }
  get inactifs(): boolean { return this.inactifsS(); }
  set inactifs(v: boolean) { this.inactifsS.set(v); }

  readonly gerer = computed(() => this.store.cap().referentiels_gerer);
  readonly domaine = computed(() => DOMAINES.find((d) => d.code === this.onglet())!);
  readonly refs = computed(() => {
    const o = this.onglet();
    if (o === 'ENTITE') return [];
    return this.store.refs(o, true).filter((r) => (this.inactifsS() || r.actif) && (!this.qS() || correspond(`${r.libelle} ${r.description ?? ''}`, this.qS())));
  });
  readonly entites = computed(() =>
    this.store.entites().filter((e) => (this.inactifsS() || e.actif) && (!this.qS() || correspond(`${e.libelle} ${e.perimetre ?? ''} ${e.lieu ?? ''}`, this.qS()))),
  );

  ngOnInit(): void {
    this.store.charger();
    this.route.queryParamMap.subscribe((qp) => {
      const o = qp.get('onglet') as Onglet | null;
      if (o && DOMAINES.some((d) => d.code === o)) this.onglet.set(o);
    });
  }

  compte(o: Onglet): number {
    return o === 'ENTITE' ? this.store.entites().length : this.store.refs(o, true).length;
  }

  choisir(o: Onglet): void {
    this.qS.set('');
    void this.router.navigate([], { relativeTo: this.route, queryParams: { onglet: o }, replaceUrl: true });
  }

  autres(src: RefItem): RefItem[] {
    return this.store.refs(src.domaine, true).filter((r) => r.id !== src.id);
  }

  nouveau(): void {
    this.edition.set({ id: null, libelle: '', description: '', ordre: null, perimetre_id: '', lieu_id: '' });
  }

  editer(r: RefItem): void {
    this.edition.set({ id: r.id, libelle: r.libelle, description: r.description ?? '', ordre: r.ordre, perimetre_id: '', lieu_id: '' });
  }

  editerEntite(e: Entite): void {
    this.edition.set({ id: e.id, libelle: e.libelle, description: '', ordre: null, perimetre_id: e.perimetre_id, lieu_id: e.lieu_id ?? '' });
  }

  private apres<T>(flux: Observable<T>, fin?: () => void): void {
    flux.subscribe(() => {
      fin?.();
      this.store.recharger$().subscribe();
    });
  }

  enregistrer(ed: Edition): void {
    const o = this.onglet();
    const libelle = ed.libelle.trim();
    let appel: () => Observable<unknown>;
    if (o === 'ENTITE') {
      const corps = { libelle, perimetre_id: ed.perimetre_id, lieu_id: ed.lieu_id || null };
      appel = () => (ed.id ? this.api.patch(`${FO_BASE}/entites/${ed.id}`, corps) : this.api.post(`${FO_BASE}/entites`, corps));
    } else {
      appel = ed.id
        ? () => this.api.patch(`${FO_BASE}/referentiels/${ed.id}`, { libelle, description: ed.description.trim() || null, ...(ed.ordre !== null ? { ordre: ed.ordre } : {}) })
        : () => this.api.post(`${FO_BASE}/referentiels`, { domaine: o, libelle, description: ed.description.trim() || null });
    }
    this.apres(
      this.feedback.run(appel, {
        busy: this.busy,
        loading: 'Enregistrement…',
        success: { title: ed.id ? 'Valeur modifiée' : 'Valeur ajoutée', message: libelle },
        errorTitle: "Échec de l'enregistrement",
        errorHint: 'Votre saisie est conservée.',
        idempotent: !ed.id,
      }),
      () => this.edition.set(null),
    );
  }

  basculer(r: RefItem): void {
    this.apres(
      this.feedback.run(() => this.api.patch(`${FO_BASE}/referentiels/${r.id}`, { actif: !r.actif }), {
        confirm: r.actif
          ? { action: 'archivage', title: 'Désactiver la valeur', message: `« ${r.libelle} » ne sera plus proposée dans les listes.`, hint: 'Les formations existantes ne changent pas.' }
          : { action: 'restauration', title: 'Réactiver la valeur', message: `« ${r.libelle} » sera de nouveau proposée.` },
        busy: this.busy,
        success: { title: r.actif ? 'Valeur désactivée' : 'Valeur réactivée', message: r.libelle },
        errorTitle: 'Action impossible',
      }),
    );
  }

  supprimer(r: RefItem): void {
    this.apres(
      this.feedback.run(() => this.api.delete(`${FO_BASE}/referentiels/${r.id}`), {
        confirm: { action: 'suppression', message: `Supprimer « ${r.libelle} » ? Elle n’est utilisée nulle part.` },
        busy: this.busy,
        success: { title: 'Valeur supprimée', message: r.libelle },
        errorTitle: 'Suppression impossible',
      }),
    );
  }

  fusionner(src: RefItem): void {
    const cible = this.store.refs(src.domaine, true).find((r) => r.id === this.cible);
    if (!cible) return;
    this.apres(
      this.feedback.run(() => this.api.post(`${FO_BASE}/referentiels/fusion`, { source_id: src.id, cible_id: cible.id }), {
        confirm: { action: 'modification', title: 'Confirmer la fusion', message: `« ${src.libelle} » → « ${cible.libelle} »`, hint: 'Opération irréversible, tracée dans le journal.' },
        busy: this.busy,
        loading: 'Fusion…',
        success: { title: 'Valeurs fusionnées', message: `${src.libelle} → ${cible.libelle}` },
        errorTitle: 'Fusion impossible',
      }),
      () => this.fusion.set(null),
    );
  }

  basculerEntite(e: Entite): void {
    this.apres(
      this.feedback.run(() => this.api.patch(`${FO_BASE}/entites/${e.id}`, { actif: !e.actif }), {
        confirm: e.actif
          ? { action: 'archivage', title: 'Désactiver l’entité', message: `« ${e.libelle} » ne sera plus proposée.` }
          : { action: 'restauration', title: 'Réactiver l’entité', message: `« ${e.libelle} » sera de nouveau proposée.` },
        busy: this.busy,
        success: { title: e.actif ? 'Entité désactivée' : 'Entité réactivée', message: e.libelle },
        errorTitle: 'Action impossible',
      }),
    );
  }

  supprimerEntite(e: Entite): void {
    this.apres(
      this.feedback.run(() => this.api.delete(`${FO_BASE}/entites/${e.id}`), {
        confirm: { action: 'suppression', message: `Supprimer l’entité « ${e.libelle} » ?` },
        busy: this.busy,
        success: { title: 'Entité supprimée', message: e.libelle },
        errorTitle: 'Suppression impossible',
      }),
    );
  }
}
