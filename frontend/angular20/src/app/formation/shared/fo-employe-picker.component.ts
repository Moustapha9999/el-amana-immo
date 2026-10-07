import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, model, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { EMPTY, expand, map, reduce } from 'rxjs';
import { ApiService } from '../../core/services/api.service';
import { Employe, FO_BASE, Page, correspond, initiales } from '../formation.models';
import { FormationStore } from '../formation.store';
import { FoEmployeFormComponent } from './fo-employe-form.component';

/** Sélection multiple d'employés actifs (filtres entité / périmètre / fonction, ajout groupé). Aucun présent par défaut. */
@Component({
  selector: 'bea-fo-employe-picker',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatIconModule, FoEmployeFormComponent],
  template: `
    <div class="bea-fo-picker">
      <section class="bea-fo-picker__pane">
        <header class="bea-fo-picker__head">
          <h3><mat-icon>groups</mat-icon> Employés disponibles <span class="bea-fx-count">{{ disponibles().length }}</span></h3>
          @if (store.cap().employes_gerer) {
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="creation.set(true)"><mat-icon>person_add</mat-icon> Nouvel employé</button>
          }
        </header>
        <div class="bea-fo-picker__filters">
          <input type="search" placeholder="Nom, prénom…" [value]="q()" (input)="q.set($any($event.target).value)" />
          <select [value]="perimetre()" (change)="perimetre.set($any($event.target).value); entite.set('')">
            <option value="">Tous périmètres</option>
            @for (p of store.refs('PERIMETRE'); track p.id) { <option [value]="p.id">{{ p.libelle }}</option> }
          </select>
          <select [value]="entite()" (change)="entite.set($any($event.target).value)">
            <option value="">Toutes entités</option>
            @for (e of entitesFiltrees(); track e.id) { <option [value]="e.id">{{ e.libelle }}</option> }
          </select>
        </div>
        <ul class="bea-fo-picker__list">
          @if (charge()) {
            @for (i of [1, 2, 3, 4, 5]; track i) { <li><span class="bea-fx-skel bea-fx-skel--line" style="flex:1"></span></li> }
          } @else {
            @for (e of disponibles().slice(0, 300); track e.id) {
              <li [class.is-on]="choisis().has(e.id)" (click)="basculer(e.id)">
                <input type="checkbox" [checked]="choisis().has(e.id)" tabindex="-1" (click)="$event.preventDefault()" />
                <span class="bea-fo-person">
                  <span class="bea-fo-avatar">{{ ini(e.nom_complet) }}</span>
                  <span><strong>{{ e.nom_complet }}</strong><small>{{ e.fonction || '—' }} · {{ e.entite || 'Entité non renseignée' }}</small></span>
                </span>
              </li>
            } @empty {
              <li class="is-off"><span class="bea-fo-hint">Aucun employé ne correspond aux filtres.</span></li>
            }
          }
        </ul>
        <footer class="bea-fo-picker__foot">
          <span>{{ disponibles().length > 300 ? '300 premiers affichés — affinez la recherche' : '' }}</span>
          <button type="button" class="bea-fo-linkbtn" [disabled]="!nonChoisis().length" (click)="toutAjouter()">
            Ajouter les {{ nonChoisis().length }} affiché(s)
          </button>
        </footer>
      </section>

      <section class="bea-fo-picker__pane">
        <header class="bea-fo-picker__head">
          <h3><mat-icon>how_to_reg</mat-icon> Participants sélectionnés <span class="bea-fx-count">{{ selection().length }}</span></h3>
          @if (selection().length) {
            <button type="button" class="bea-fo-linkbtn bea-fo-linkbtn--danger" (click)="selection.set([])">Tout retirer</button>
          }
        </header>
        <ul class="bea-fo-picker__list">
          @for (e of selectionnes(); track e.id; let i = $index) {
            <li class="bea-fx-row-in" [style.--i]="i < 20 ? i : 0">
              <span class="bea-fo-hint" style="width:1.6rem;text-align:right">{{ i + 1 }}</span>
              <span class="bea-fo-person">
                <span class="bea-fo-avatar">{{ ini(e.nom_complet) }}</span>
                <span><strong>{{ e.nom_complet }}</strong><small>{{ e.entite || 'Entité non renseignée' }}{{ e.perimetre ? ' · ' + e.perimetre : '' }}</small></span>
              </span>
              <button type="button" title="Retirer" (click)="basculer(e.id)"><mat-icon>close</mat-icon></button>
            </li>
          } @empty {
            <li class="is-off" style="justify-content:center;padding:2rem 0.5rem">
              <span class="bea-fo-hint">Cochez les employés à gauche. Aucun participant n’est marqué présent par défaut : la présence se saisit après la formation.</span>
            </li>
          }
        </ul>
        @if (exclus().length) {
          <footer class="bea-fo-picker__foot"><span>{{ exclus().length }} déjà inscrit(s) à cette formation, masqué(s) de la liste.</span></footer>
        }
      </section>
    </div>
    @if (creation()) {
      <bea-fo-employe-form [dessus]="true" (fermer)="creation.set(false)" (enregistre)="cree($event)" (choisirExistant)="existant($event)" />
    }
  `,
})
export class FoEmployePickerComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly store = inject(FormationStore);

  readonly selection = model<string[]>([]);
  readonly exclus = input<string[]>([]);
  readonly connus = input<Employe[]>([]);

  readonly tous = signal<Employe[]>([]);
  readonly charge = signal(true);
  readonly creation = signal(false);
  readonly q = signal('');
  readonly entite = signal('');
  readonly perimetre = signal('');

  readonly ini = initiales;
  readonly choisis = computed(() => new Set(this.selection()));
  private readonly parId = computed(() => {
    const m = new Map<string, Employe>();
    for (const e of this.connus()) m.set(e.id, e);
    for (const e of this.tous()) m.set(e.id, e);
    return m;
  });
  readonly entitesFiltrees = computed(() => {
    const p = this.perimetre();
    return this.store.entitesActives().filter((e) => !p || e.perimetre_id === p);
  });
  readonly disponibles = computed(() => {
    const ex = new Set(this.exclus());
    const q = this.q().trim();
    const ent = this.entite();
    const per = this.perimetre();
    return this.tous().filter(
      (e) => !ex.has(e.id) && (!ent || e.entite_id === ent) && (!per || e.perimetre_id === per) && (!q || correspond(`${e.nom_complet} ${e.fonction ?? ''}`, q)),
    );
  });
  readonly nonChoisis = computed(() => this.disponibles().slice(0, 300).filter((e) => !this.choisis().has(e.id)));
  readonly selectionnes = computed(() => this.selection().map((id) => this.parId().get(id)).filter((e): e is Employe => !!e));

  ngOnInit(): void {
    const taille = 500;
    this.api
      .get<Page<Employe>>(`${FO_BASE}/employes`, { actif: 'oui', taille, page: 1 })
      .pipe(
        expand((p) => (p.page * taille < p.total ? this.api.get<Page<Employe>>(`${FO_BASE}/employes`, { actif: 'oui', taille, page: p.page + 1 }) : EMPTY)),
        map((p) => p.items),
        reduce((acc, items) => acc.concat(items), [] as Employe[]),
      )
      .subscribe({
        next: (items) => {
          this.tous.set(items);
          this.charge.set(false);
        },
        error: () => this.charge.set(false),
      });
  }

  basculer(id: string): void {
    const s = this.selection();
    this.selection.set(s.includes(id) ? s.filter((x) => x !== id) : [...s, id]);
  }

  toutAjouter(): void {
    this.selection.set([...this.selection(), ...this.nonChoisis().map((e) => e.id)]);
  }

  cree(e: Employe): void {
    this.creation.set(false);
    this.tous.set([...this.tous(), e].sort((a, b) => a.nom_complet.localeCompare(b.nom_complet, 'fr')));
    if (!this.selection().includes(e.id)) this.selection.set([...this.selection(), e.id]);
  }

  existant(e: Employe): void {
    this.creation.set(false);
    if (e.actif && !this.selection().includes(e.id) && !this.exclus().includes(e.id)) this.selection.set([...this.selection(), e.id]);
  }
}
