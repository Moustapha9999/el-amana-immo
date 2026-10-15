import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { CL_BASE, dateFr, dateHeureFr, n } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';
import { EtatChargement, Synthese360 } from './vue360.models';

interface Liste { id: string; code: string; libelle: string; source: string; actif: boolean; nb_entrees: number; }
interface Entree {
  id: string; nom: string | null; prenom: string | null; raison_sociale: string | null; date_naissance: string | null;
  nationalite: string | null; identifiant: string | null; type_identifiant: string | null; actif: boolean;
}

@Component({
  selector: 'bea-cl360-listes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule],
  template: `
    @if (synthese()?.sources_filtrage; as s) {
      <p class="bea-cl-note bea-cl-note--warn"><mat-icon>warning</mat-icon>{{ s.note_listes }}</p>
    }
    <section class="bea-mg__panel">
      <div class="bea-mg__panel-top"><h2>Listes de référence</h2><span class="bea-mg__count">{{ listes().length }}</span></div>
      <div class="bea-mg__table-wrap">
        <table class="bea-mg__table bea-cl360-table">
          <colgroup>
            <col style="width:9rem" /><col /><col style="width:7rem" /><col style="width:6.5rem" />
            <col style="width:7rem" /><col style="width:7.5rem" /><col style="width:9rem" /><col style="width:3rem" />
          </colgroup>
          <thead><tr><th>Code</th><th>Libellé</th><th>Source</th><th>État</th><th class="is-num">Entrées actives</th><th>Dernière entrée</th><th>Journal d’import</th><th class="is-act"><span class="bea-sr-only">Ouvrir</span></th></tr></thead>
          <tbody>
            @for (l of listes(); track l.id) {
              <tr class="is-click" [class.is-on]="liste()?.id === l.id" (click)="choisir(l)">
                <td><code>{{ l.code }}</code></td><td>{{ l.libelle }}</td><td>{{ l.source }}</td>
                <td><span class="bea-cl-badge" [attr.data-s]="l.actif ? 'OK' : 'ABSENT'">{{ l.actif ? 'Active' : 'Inactive' }}</span></td>
                <td class="is-num">{{ n(l.nb_entrees) }}</td>
                <td>{{ dateFr(meta(l.id)?.derniere_entree) }}</td>
                <td>{{ meta(l.id)?.preuve_import ? 'Oui' : 'Aucun import tracé' }}</td>
                <td class="is-act"><mat-icon>chevron_right</mat-icon></td>
              </tr>
            } @empty {
              <tr><td colspan="8"><div class="bea-cl-empty">{{ etatListes() === 'chargement' ? 'Chargement…' : 'Aucune liste configurée.' }}</div></td></tr>
            }
          </tbody>
        </table>
      </div>
    </section>

    @if (liste(); as l) {
      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Entrées · {{ l.libelle }}</h2><span class="bea-mg__count">{{ etat() === 'ok' ? n(total()) : '—' }}</span></div>
        <form class="bea-cl-filters" (submit)="$event.preventDefault(); page.set(1); charger()">
          <label style="grid-column:span 2">Nom, raison sociale ou identifiant<input [(ngModel)]="q" name="q" maxlength="80" /></label>
          <label>&nbsp;<button type="submit" class="bea-mg__btn bea-mg__btn--ghost"><mat-icon>search</mat-icon> Rechercher</button></label>
        </form>
        @if (etat() === 'erreur') {
          <div class="bea-cl360-state" data-s="erreur"><mat-icon>cloud_off</mat-icon>{{ erreur() }}</div>
        } @else {
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table bea-cl360-table">
              <colgroup><col /><col style="width:16%" /><col style="width:7.5rem" /><col style="width:9rem" /><col style="width:12rem" /><col style="width:6.5rem" /></colgroup>
              <thead><tr><th>Nom / raison sociale</th><th>Prénom</th><th>Naissance</th><th>Nationalité</th><th>Identifiant</th><th>État</th></tr></thead>
              <tbody>
                @for (e of entrees(); track e.id) {
                  <tr>
                    <td>{{ e.raison_sociale || e.nom || '—' }}</td><td>{{ e.prenom || '—' }}</td><td>{{ dateFr(e.date_naissance) }}</td>
                    <td>{{ e.nationalite || '—' }}</td><td>{{ e.identifiant ? (e.type_identifiant ? e.type_identifiant + ' ' : '') + e.identifiant : '—' }}</td>
                    <td><span class="bea-cl-badge" [attr.data-s]="e.actif ? 'OK' : 'ABSENT'">{{ e.actif ? 'Active' : 'Inactive' }}</span></td>
                  </tr>
                } @empty {
                  <tr><td colspan="6"><div class="bea-cl-empty">{{ etat() === 'chargement' ? 'Chargement…' : 'Aucune entrée (zéro résultat).' }}</div></td></tr>
                }
              </tbody>
            </table>
          </div>
          <div class="bea-cl-pager">
            <span>Page {{ page() }} / {{ pages() }}</span>
            <span>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() <= 1" (click)="aller(page() - 1)">Précédente</button>
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() >= pages()" (click)="aller(page() + 1)">Suivante</button>
            </span>
          </div>
        }
        @if (store.cap().filtrage_executer) {
          <form class="bea-cl-filters" (submit)="$event.preventDefault(); ajouter()" style="border-top:1px solid var(--bea-border, #e5e7eb)">
            <label>Raison sociale / nom<input [(ngModel)]="entree.raison_sociale" name="rs" maxlength="255" /></label>
            <label>Prénom<input [(ngModel)]="entree.prenom" name="pr" maxlength="160" /></label>
            <label>Identifiant<input [(ngModel)]="entree.identifiant" name="id" maxlength="80" /></label>
            <label>Nationalité<input [(ngModel)]="entree.nationalite" name="nat" maxlength="80" /></label>
            <label>&nbsp;<button type="submit" class="bea-mg__btn bea-mg__btn--primary" [disabled]="busy() || (!entree.raison_sociale.trim() && !entree.identifiant.trim())">Ajouter une entrée</button></label>
          </form>
          <p class="bea-cl-hint" style="padding:0 1rem 0.85rem">L’ajout est tracé dans le journal d’audit. Les clients concernés ne seront rapprochés qu’au prochain filtrage.</p>
        }
      </section>
    }
  `,
})
export class Cl360ListesComponent {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ClienteleStore);
  readonly synthese = input<Synthese360 | null>(null);
  readonly listes = signal<Liste[]>([]);
  readonly etatListes = signal<EtatChargement>('chargement');
  readonly liste = signal<Liste | null>(null);
  readonly entrees = signal<Entree[]>([]);
  readonly total = signal(0);
  readonly etat = signal<EtatChargement>('chargement');
  readonly erreur = signal('');
  readonly busy = signal(false);
  readonly page = signal(1);
  readonly taille = 50;
  readonly pages = computed(() => Math.max(1, Math.ceil(this.total() / this.taille)));
  q = '';
  entree = { raison_sociale: '', prenom: '', identifiant: '', nationalite: '' };
  readonly n = n;
  readonly dateFr = dateFr;
  readonly dh = dateHeureFr;

  constructor() {
    this.chargerListes();
  }

  meta(id: string) {
    return this.synthese()?.sources_filtrage.listes.find((x) => x.id === id) ?? null;
  }

  chargerListes(): void {
    this.api.get<Liste[]>(`${CL_BASE}/filtrage/listes`).subscribe({
      next: (r) => {
        this.listes.set(r);
        this.etatListes.set('ok');
        const courante = this.liste();
        if (!courante && r[0]) this.choisir(r[0]);
        else if (courante) this.liste.set(r.find((x) => x.id === courante.id) ?? null);
      },
      error: (e) => void describeApiErrorAsync(e).then((i) => { this.etatListes.set('erreur'); this.feedback.apiError(i, 'Listes indisponibles'); }),
    });
  }

  choisir(l: Liste): void {
    this.liste.set(l);
    this.q = '';
    this.page.set(1);
    this.charger();
  }

  charger(): void {
    const l = this.liste();
    if (!l) return;
    const params: Record<string, string | number> = { page: this.page(), taille: this.taille };
    if (this.q.trim()) params['q'] = this.q.trim();
    this.etat.set('chargement');
    this.api.get<{ total: number; items: Entree[] }>(`${CL_BASE}/filtrage/listes/${l.id}/entrees`, params).subscribe({
      next: (p) => { this.entrees.set(p.items); this.total.set(p.total); this.etat.set('ok'); },
      error: (e) => void describeApiErrorAsync(e).then((i) => {
        this.erreur.set(`Entrées indisponibles : ${i.message}${i.requestId ? ` (réf. ${i.requestId})` : ''}`);
        this.etat.set('erreur');
      }),
    });
  }

  aller(p: number): void {
    this.page.set(p);
    this.charger();
  }

  ajouter(): void {
    const l = this.liste();
    if (!l) return;
    const corps = Object.fromEntries(Object.entries(this.entree).map(([k, v]) => [k, v.trim() || null]));
    this.feedback.run(() => this.api.post(`${CL_BASE}/filtrage/listes/${l.id}/entrees`, corps), {
      confirm: { action: 'validation', title: 'Ajouter une entrée', message: `Ajouter « ${this.entree.raison_sociale || this.entree.identifiant} » à la liste ${l.libelle} ?`, hint: 'Action tracée. Aucun client n’est marqué tant que le filtrage n’a pas été relancé et l’alerte analysée.' },
      busy: this.busy, success: { title: 'Entrée ajoutée' }, errorTitle: 'Ajout refusé',
    }).subscribe(() => {
      this.entree = { raison_sociale: '', prenom: '', identifiant: '', nationalite: '' };
      this.chargerListes();
      this.charger();
    });
  }
}
