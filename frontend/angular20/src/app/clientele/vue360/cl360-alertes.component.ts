import { ChangeDetectionStrategy, Component, computed, effect, inject, input, output, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { CL_BASE, dateFr, dateHeureFr, n } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';
import { Ouvrir360 } from './cl360-synthese.component';
import {
  Agent, Alerte360, EtatChargement, Filtres360, GROUPES_ALERTE, LIB_PROFIL, PageAlertes360, Synthese360, Vue360, bornesPeriode,
  filtresPopulation, heure, jour,
} from './vue360.models';

@Component({
  selector: 'bea-cl360-alertes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule],
  template: `
    @if (mode() === 'filtrage') {
      <p class="bea-cl-note bea-cl-note--info"><mat-icon>info</mat-icon>Une correspondance potentielle n’est jamais une correspondance confirmée : seule une décision tracée d’un agent habilité la confirme ou l’écarte.</p>
      <div class="bea-cl-stats">
        <button type="button" class="bea-cl-stat" (click)="clients('SANS')">
          <span>Clients sans correspondance</span><strong>{{ v(synthese()?.filtrage?.clients_sans_correspondance) }}</strong><small>clients distincts</small>
        </button>
        @for (g of groupes; track g.code) {
          <button type="button" class="bea-cl-stat" [class.is-on]="filtres().groupe === g.code" (click)="groupe(g.code)">
            <span>{{ g.libelle }}</span><strong>{{ etat() === 'ok' ? n(page_()?.par_groupe?.[g.code]) : '—' }}</strong><small>alertes · {{ g.statuts }}</small>
          </button>
        }
      </div>
      @if (synthese()?.sources_filtrage; as s) {
        <div class="bea-cl-modal__cols">
          <section class="bea-mg__panel" style="padding:1rem">
            <h3>Dernier filtrage</h3>
            <dl class="bea-cl-dl">
              <dt>Exécuté le</dt><dd>{{ s.dernier_scan?.le ? dh(s.dernier_scan!.le) : 'Aucun filtrage tracé' }}</dd>
              <dt>Par</dt><dd>{{ s.dernier_scan?.par || '—' }}</dd>
              <dt>Alertes créées</dt><dd>{{ s.dernier_scan?.alertes_creees ?? '—' }}</dd>
              <dt>Clients créés depuis</dt><dd>{{ s.clients_crees_depuis_scan ?? '—' }} <small class="bea-cl-hint">non encore filtrés</small></dd>
              <dt>Extraction ORION</dt><dd>{{ dateFr(s.orion.date_extraction) }}</dd>
            </dl>
          </section>
          <section class="bea-mg__panel" style="padding:1rem">
            <h3>Codes ORION « Liste d’interdiction »</h3>
            <p class="bea-cl-hint">{{ s.orion.note }}</p>
            <table class="bea-mg__table bea-cl360-table is-souple">
              <thead><tr><th>Code</th><th class="is-num">Clients distincts</th><th class="is-num">Comptes</th></tr></thead>
              <tbody>
                @for (c of s.orion.codes; track c.code) { <tr><td><code>{{ c.code }}</code></td><td class="is-num">{{ n(c.clients) }}</td><td class="is-num">{{ n(c.comptes) }}</td></tr> }
                @empty { <tr><td colspan="3"><div class="bea-cl-empty">Aucun code renseigné.</div></td></tr> }
              </tbody>
            </table>
          </section>
        </div>
      }
    }

    <section class="bea-mg__panel">
      <div class="bea-mg__panel-top">
        <h2>{{ mode() === 'filtrage' ? 'Correspondances' : 'Alertes' }}</h2>
        <span class="bea-mg__count">{{ etat() === 'ok' ? n(page_()?.total) : '—' }}</span>
      </div>
      <div class="bea-cl-filters">
        <label>Statut
          <select [ngModel]="filtres().groupe ?? ''" (ngModelChange)="filtrer({ groupe: $event })">
            <option value="">Tous</option><option value="OUVERTES">Ouvertes (à examiner + en analyse)</option>
            @for (g of groupes; track g.code) { <option [value]="g.code">{{ g.libelle }}</option> }
          </select>
        </label>
        <label>Source
          <select [ngModel]="filtres().source ?? ''" (ngModelChange)="filtrer({ source: $event })">
            <option value="">Toutes</option><option value="ORION">Champ ORION</option><option value="LISTE">Liste interne</option>
          </select>
        </label>
        <label>Attribution
          <select [ngModel]="filtres().assignee ?? ''" (ngModelChange)="filtrer({ assignee: $event })">
            <option value="">Toutes</option><option value="aucun">Non attribuées</option><option value="moi">Mes alertes</option>
            @for (a of agents(); track a.id) { <option [value]="a.id">{{ a.nom }}</option> }
          </select>
        </label>
        <label>Ancienneté
          <select [ngModel]="filtres().anciennete_min ?? ''" (ngModelChange)="filtrer({ anciennete_min: $event })">
            <option value="">Toutes</option><option value="8">&gt; 7 jours</option><option value="31">&gt; 30 jours</option><option value="91">&gt; 90 jours</option>
          </select>
        </label>
        <label>Tri
          <select [ngModel]="filtres().tri ?? ''" (ngModelChange)="filtrer({ tri: $event })">
            <option value="">Plus anciennes d’abord</option><option value="recent">Plus récentes</option><option value="similarite">Similarité décroissante</option>
          </select>
        </label>
        <label class="bea-cl-check" style="flex-direction:row;text-transform:none">
          <input type="checkbox" [ngModel]="!!filtres().periode_alertes" (ngModelChange)="filtrer({ periode_alertes: $event ? '1' : '' })" />
          Créées pendant la période
        </label>
      </div>
      <p class="bea-cl-hint" style="padding:0 1rem 0.6rem">Unité : alerte (un client peut en avoir plusieurs). Priorité et délai cible : non définis dans le référentiel — l’ancienneté est affichée à la place.</p>
      @if (etat() === 'erreur') {
        <div class="bea-cl360-state" data-s="erreur"><mat-icon>cloud_off</mat-icon>{{ erreur() }}
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger()">Réessayer</button></div>
      } @else {
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table bea-cl360-table">
            <colgroup>
              <col /><col style="width:11rem" /><col style="width:8.5rem" /><col style="width:7rem" />
              <col style="width:10.5rem" /><col style="width:7rem" /><col style="width:3rem" />
            </colgroup>
            <thead><tr>
              <th>Client</th><th>Correspondance</th><th>Statut</th><th>Créée le</th><th>Agent</th><th>Dernière action</th>
              <th class="is-act"><span class="bea-sr-only">Dossier</span></th>
            </tr></thead>
            <tbody>
              @for (a of page_()?.items ?? []; track a.id) {
                <tr>
                  <td>
                    <span class="bea-cl360-l1" [title]="a.raison_sociale"><code>{{ a.racine_client }}</code>{{ a.raison_sociale }}</span>
                    <span class="bea-cl360-l2">{{ libProfil[a.profil] || a.profil }} · agence {{ a.code_agence || '—' }}</span>
                  </td>
                  <td>
                    <span class="bea-cl360-l1">{{ a.motif.replaceAll('_', ' ') }}</span>
                    <span class="bea-cl360-l2">{{ a.source === 'ORION' ? 'Champ ORION' : 'Liste interne' }} · similarité {{ a.score }}</span>
                  </td>
                  <td>
                    <span class="bea-cl360-stack">
                      <span class="bea-cl-badge" [attr.data-s]="a.statut">{{ a.statut.replaceAll('_', ' ') }}</span>
                      @if (a.precedent_faux_positif) { <span class="bea-cl-badge" data-s="ANALYSE">FP antérieur</span> }
                    </span>
                  </td>
                  <td>{{ jour(a.created_at) }}<span class="bea-cl360-l2">{{ a.anciennete_jours !== null ? 'ouverte depuis ' + a.anciennete_jours + ' j' : heure(a.created_at) }}</span></td>
                  <td>
                    @if (store.cap().filtrage_decider && a.statut !== 'CLOTUREE') {
                      <select [ngModel]="a.assignee_id ?? ''" (ngModelChange)="attribuer(a, $event)" [disabled]="busy()" [attr.aria-label]="'Attribuer l’alerte du client ' + a.racine_client">
                        <option value="">Non attribuée</option>
                        @for (g of agents(); track g.id) { <option [value]="g.id">{{ g.nom }}</option> }
                      </select>
                    } @else { {{ a.assignee || 'Non attribuée' }} }
                  </td>
                  <td>{{ jour(a.derniere_action) }}<span class="bea-cl360-l2">{{ heure(a.derniere_action) }}</span></td>
                  <td class="is-act"><span class="bea-cl-row-actions"><a [routerLink]="['/clientele/filtrage', a.id]" [attr.aria-label]="'Ouvrir le dossier de l’alerte du client ' + a.racine_client"><mat-icon>open_in_new</mat-icon></a></span></td>
                </tr>
              } @empty {
                <tr><td colspan="7"><div class="bea-cl-empty">{{ etat() === 'chargement' ? 'Chargement…' : 'Aucune alerte ne correspond à ces filtres (zéro résultat).' }}</div></td></tr>
              }
            </tbody>
          </table>
        </div>
        <div class="bea-cl-pager">
          <span>Page {{ page() }} / {{ pages() }} · {{ n(page_()?.total) }} alertes</span>
          <span>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() <= 1" (click)="aller(page() - 1)">Précédente</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page() >= pages()" (click)="aller(page() + 1)">Suivante</button>
          </span>
        </div>
      }
    </section>
  `,
})
export class Cl360AlertesComponent {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ClienteleStore);
  readonly filtres = input.required<Filtres360>();
  readonly mode = input<'filtrage' | 'alertes'>('alertes');
  readonly synthese = input<Synthese360 | null>(null);
  readonly navigation = output<Ouvrir360>();
  readonly page_ = signal<PageAlertes360 | null>(null);
  readonly agents = signal<Agent[]>([]);
  readonly etat = signal<EtatChargement>('chargement');
  readonly erreur = signal('');
  readonly busy = signal(false);
  readonly page = signal(1);
  readonly taille = 50;
  readonly pages = computed(() => Math.max(1, Math.ceil((this.page_()?.total ?? 0) / this.taille)));
  readonly groupes = GROUPES_ALERTE;
  readonly n = n;
  readonly dh = dateHeureFr;
  readonly dateFr = dateFr;
  readonly jour = jour;
  readonly heure = heure;
  readonly libProfil = LIB_PROFIL;

  constructor() {
    this.api.get<Agent[]>(`${CL_BASE}/filtrage/agents`).subscribe({ next: (a) => this.agents.set(a), error: () => this.agents.set([]) });
    effect(() => {
      this.filtres();
      untracked(() => { this.page.set(1); this.charger(); });
    });
  }

  v(x: number | null | undefined): string {
    return x === null || x === undefined ? '—' : n(x);
  }

  charger(): void {
    const f = this.filtres();
    const params: Record<string, string | number> = { ...filtresPopulation(f), page: this.page(), taille: this.taille };
    for (const k of ['groupe', 'source', 'assignee', 'anciennete_min', 'tri'] as const) if (f[k]) params[k] = f[k]!;
    if (f.periode_alertes) {
      const b = bornesPeriode(f);
      if (b) { params['du'] = b.du; params['au'] = b.au; }
    }
    this.etat.set('chargement');
    this.api.get<PageAlertes360>(`${CL_BASE}/filtrage/alertes`, params).subscribe({
      next: (p) => { this.page_.set(p); this.etat.set('ok'); },
      error: (e) => void describeApiErrorAsync(e).then((i) => {
        this.erreur.set(`Alertes indisponibles : ${i.message}${i.requestId ? ` (réf. ${i.requestId})` : ''}`);
        this.etat.set('erreur');
      }),
    });
  }

  aller(p: number): void {
    this.page.set(p);
    this.charger();
  }

  filtrer(patch: Filtres360): void {
    this.navigation.emit({ vue: this.vue(), filtres: patch, fusion: true });
  }

  groupe(code: string): void {
    this.filtrer({ groupe: this.filtres().groupe === code ? '' : code });
  }

  clients(filtrage: string): void {
    this.navigation.emit({ vue: 'profilage', filtres: { filtrage }, fusion: false });
  }

  attribuer(a: Alerte360, assigneeId: string): void {
    const cible = this.agents().find((g) => g.id === assigneeId);
    this.feedback.run(
      () => this.api.post(`${CL_BASE}/filtrage/alertes/${a.id}/attribuer`, { assignee_id: assigneeId || null }),
      {
        confirm: {
          action: 'validation',
          title: assigneeId ? 'Attribuer l’alerte' : 'Retirer l’attribution',
          message: assigneeId ? `Attribuer l’alerte du client ${a.racine_client} à ${cible?.nom ?? 'cet agent'} ?` : `Retirer l’agent de l’alerte du client ${a.racine_client} ?`,
          hint: 'L’action est tracée dans l’historique de l’alerte et le journal d’audit.',
        },
        busy: this.busy,
        success: { title: assigneeId ? 'Alerte attribuée' : 'Attribution retirée' },
        errorTitle: 'Attribution refusée',
      },
    ).subscribe({ next: () => this.charger(), error: () => this.charger() });
  }

  private vue(): Vue360 {
    return this.mode() === 'filtrage' ? 'filtrage' : 'alertes';
  }
}
