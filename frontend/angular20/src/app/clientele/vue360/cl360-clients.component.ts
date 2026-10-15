import { ChangeDetectionStrategy, Component, effect, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { ApiService } from '../../core/services/api.service';
import { CL_BASE, MODES_DECISION, n } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';
import { Cl360FicheComponent } from './cl360-fiche.component';
import { Ouvrir360 } from './cl360-synthese.component';
import {
  FILTRAGES, Filtres360, LIB_MOTIF_CHAMP, LIB_NIVEAU, LIB_PROFIL, PROFILAGES, PageClients360, Vue360, filtresPopulation, heure, jour,
} from './vue360.models';

@Component({
  selector: 'bea-cl360-clients',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule, Cl360FicheComponent],
  template: `
    @if (mode() === 'recherche') {
      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Recherche transversale</h2></div>
        <form class="bea-cl-filters" (submit)="$event.preventDefault(); rechercher()">
          <label style="grid-column:span 2">Racine, nom / raison sociale, NNI, NIF, compte ou RIB
            <input [(ngModel)]="saisie" name="q" maxlength="80" placeholder="ex. 000667, NNI, 11 chiffres du compte…" />
          </label>
          <label>&nbsp;<button type="submit" class="bea-mg__btn bea-mg__btn--primary"><mat-icon>search</mat-icon> Rechercher</button></label>
        </form>
        <p class="bea-cl-hint" style="padding:0 1rem 0.85rem">Un client = une racine ORION : ses comptes sont regroupés, jamais fusionnés sur une ressemblance de nom. Un compte ou un RIB doit être saisi en entier.</p>
      </section>
    }
    @if (mode() === 'profilage') {
      <section class="bea-mg__panel">
        <div class="bea-mg__panel-top"><h2>Filtres de profilage</h2></div>
        <div class="bea-cl-filters">
          <label>Statut du profilage
            <select [ngModel]="filtres().profilage ?? ''" (ngModelChange)="filtrer({ profilage: $event })">
              <option value="">Tous</option>
              @for (p of profilages; track p.code) { <option [value]="p.code">{{ p.libelle }}</option> }
            </select>
          </label>
          <label>Cohérence
            <select [ngModel]="filtres().coherence ?? ''" (ngModelChange)="filtrer({ coherence: $event })">
              <option value="">Toutes</option><option value="OK">Aucun contrôle en écart</option><option value="A_VERIFIER">À vérifier</option>
            </select>
          </label>
          <label>Complétude
            <select [ngModel]="filtres().completude ?? ''" (ngModelChange)="filtrer({ completude: $event })">
              <option value="">Toutes</option><option value="COMPLET">Complet</option><option value="INCOMPLET">Incomplet</option>
            </select>
          </label>
          <label>Filtrage
            <select [ngModel]="filtres().filtrage ?? ''" (ngModelChange)="filtrer({ filtrage: $event })">
              <option value="">Tous</option>
              @for (x of filtrages; track x.code) { <option [value]="x.code">{{ x.libelle }}</option> }
            </select>
          </label>
          <label class="bea-cl-check" style="flex-direction:row;text-transform:none">
            <input type="checkbox" [ngModel]="!!filtres().classe_periode" (ngModelChange)="filtrer({ classe_periode: $event ? '1' : '' })" />
            Classés pendant la période
          </label>
        </div>
      </section>
    }

    <section class="bea-mg__panel">
      <div class="bea-mg__panel-top">
        <h2>{{ mode() === 'recherche' ? 'Résultats' : 'Clients' }}</h2>
        <span style="display:flex;gap:0.5rem;align-items:center">
          <label class="bea-cl-hint">Tri
            <select [(ngModel)]="tri" (ngModelChange)="page = 1; charger()" style="font:inherit;font-size:0.8rem">
              <option value="">Racine</option><option value="nom">Nom</option><option value="score">Score enregistré</option>
              <option value="classement">Date de classement</option><option value="alertes">Alertes ouvertes</option>
            </select>
          </label>
          <span class="bea-mg__count">{{ etat() === 'ok' ? n(page_()?.total) : '—' }}</span>
        </span>
      </div>
      @if (etat() === 'erreur') {
        <div class="bea-cl360-state" data-s="erreur"><mat-icon>cloud_off</mat-icon>{{ erreur() }}
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger()">Réessayer</button></div>
      } @else if (mode() === 'recherche' && !filtres().q) {
        <div class="bea-cl360-state"><mat-icon>person_search</mat-icon>Saisissez un critère pour rechercher un client.</div>
      } @else {
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table bea-cl360-table" [class.is-souple]="!voitClassif()">
            <colgroup>
              <col style="width:26%" />
              @if (voitClassif()) {
                <col style="width:5.5rem" /><col style="width:6.5rem" /><col /><col style="width:6.5rem" />
              }
              <col style="width:7rem" /><col style="width:7rem" /><col style="width:3rem" />
            </colgroup>
            <thead><tr>
              <th>Client</th>
              @if (voitClassif()) { <th class="is-num">Score enregistré</th><th>Niveau enregistré</th><th>Motif enregistré</th><th>Classé le</th> }
              <th>Contrôles</th><th>Alertes</th><th class="is-act"><span class="bea-sr-only">Fiche</span></th>
            </tr></thead>
            <tbody>
              @for (c of page_()?.items ?? []; track c.racine_client) {
                <tr class="is-click" (click)="ouvrirFiche(c.racine_client)">
                  <td>
                    <span class="bea-cl360-l1" [title]="c.nom + (c.prenoms ? ' ' + c.prenoms : '')"><code>{{ c.racine_client }}</code>{{ c.nom }}@if (c.prenoms) { {{ ' ' + c.prenoms }} }</span>
                    <span class="bea-cl360-l2">{{ libProfil[c.profil] || c.profil }} · agence {{ c.code_agence || '—' }} · {{ c.nb_comptes }} compte(s)</span>
                  </td>
                  @if (voitClassif()) {
                    @if (c.classification; as k) {
                      <td class="is-num">{{ k.score_enregistre !== null ? n(k.score_enregistre) : '—' }}</td>
                      <td>@if (k.niveau) { <span class="bea-cl-badge" [attr.data-s]="k.niveau">{{ libNiveau[k.niveau] || k.niveau }}</span> } @else { <span class="bea-cl-badge">Non évalué</span> }</td>
                      <td class="bea-cl360-motif" [title]="k.motif_enregistre || ''">
                        <span class="bea-cl360-clamp">{{ k.motif_enregistre || '—' }}</span>
                        @if (k.motif_champ) { <small>enregistré · {{ libChamp[k.motif_champ] }} · {{ modes[k.mode_decision || ''] || k.source }}</small> }
                      </td>
                      <td>{{ jour(k.classifie_le) }}<span class="bea-cl360-l2">{{ heure(k.classifie_le) }}</span></td>
                    } @else { <td class="is-num">—</td><td><span class="bea-cl-badge">Non évalué</span></td><td>—</td><td>—</td> }
                  }
                  <td>
                    <span class="bea-cl360-stack">
                      <span class="bea-cl-badge" [attr.data-s]="c.completude === 'COMPLET' ? 'OK' : 'A_VERIFIER'">{{ c.completude === 'COMPLET' ? 'Complet' : 'Incomplet' }}</span>
                      @if (voitClassif()) {
                        <span class="bea-cl-badge" [attr.data-s]="c.coherence === 'OK' ? 'OK' : (c.coherence === 'A_VERIFIER' ? 'A_VERIFIER' : 'ABSENT')" [title]="c.anomalies.join(', ')">{{ libCoherence[c.coherence || ''] }}</span>
                      }
                    </span>
                  </td>
                  <td>@if (c.alertes.a_examiner + c.alertes.en_analyse) { <span class="bea-cl-chip">{{ c.alertes.a_examiner + c.alertes.en_analyse }} ouverte(s)</span> } @else { {{ c.alertes.total ? c.alertes.total + ' traitée(s)' : '—' }} }</td>
                  <td class="is-act"><span class="bea-cl-row-actions"><button type="button" (click)="$event.stopPropagation(); ouvrirFiche(c.racine_client)" [attr.aria-label]="'Fiche 360° du client ' + c.racine_client"><mat-icon>open_in_new</mat-icon></button></span></td>
                </tr>
              } @empty {
                <tr><td [attr.colspan]="voitClassif() ? 8 : 4"><div class="bea-cl-empty">{{ etat() === 'chargement' ? 'Chargement…' : 'Aucun client ne correspond à ces filtres (zéro résultat).' }}</div></td></tr>
              }
            </tbody>
          </table>
        </div>
        <div class="bea-cl-pager">
          <span>Page {{ page }} / {{ pages() }} · {{ n(page_()?.total) }} clients</span>
          <span>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page <= 1" (click)="aller(page - 1)">Précédente</button>
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="page >= pages()" (click)="aller(page + 1)">Suivante</button>
          </span>
        </div>
      }
    </section>

    @if (fiche(); as r) { <bea-cl360-fiche [racine]="r" (fermer)="fiche.set(null)" /> }
  `,
})
export class Cl360ClientsComponent {
  private readonly api = inject(ApiService);
  readonly store = inject(ClienteleStore);
  readonly filtres = input.required<Filtres360>();
  readonly mode = input<'profilage' | 'recherche'>('profilage');
  readonly navigation = output<Ouvrir360>();
  readonly page_ = signal<PageClients360 | null>(null);
  readonly etat = signal<'chargement' | 'ok' | 'erreur'>('chargement');
  readonly erreur = signal('');
  readonly fiche = signal<string | null>(null);
  readonly voitClassif = () => this.store.cap().classif_voir;
  readonly n = n;
  readonly jour = jour;
  readonly heure = heure;
  readonly libProfil = LIB_PROFIL;
  readonly modes = MODES_DECISION;
  readonly libNiveau = LIB_NIVEAU;
  readonly libChamp = LIB_MOTIF_CHAMP;
  readonly profilages = PROFILAGES;
  readonly filtrages = FILTRAGES;
  readonly libCoherence: Record<string, string> = { OK: 'OK', A_VERIFIER: 'À vérifier', NON_EVALUE: 'Non évalué', '': '—' };
  page = 1;
  readonly taille = 50;
  tri = '';
  saisie = '';

  constructor() {
    effect(() => {
      const f = this.filtres();
      this.saisie = f.q ?? '';
      this.page = 1;
      this.charger();
    });
  }

  pages(): number {
    return Math.max(1, Math.ceil((this.page_()?.total ?? 0) / this.taille));
  }

  charger(): void {
    const f = this.filtres();
    if (this.mode() === 'recherche' && !f.q) { this.page_.set(null); this.etat.set('ok'); return; }
    const params: Record<string, string | number> = { ...filtresPopulation(f), page: this.page, taille: this.taille };
    for (const k of ['periode', 'du', 'au'] as const) if (f[k]) params[k] = f[k]!;
    if (f.classe_periode) params['classe_periode'] = 'true';
    if (this.tri) params['tri'] = this.tri;
    this.etat.set('chargement');
    this.api.get<PageClients360>(`${CL_BASE}/vue360/clients`, params).subscribe({
      next: (p) => {
        this.page_.set(p);
        this.etat.set('ok');
        if (this.mode() === 'recherche' && p.total === 1) this.fiche.set(p.items[0].racine_client);
      },
      error: (e) => void describeApiErrorAsync(e).then((i) => {
        this.erreur.set(`Liste indisponible : ${i.message}${i.requestId ? ` (réf. ${i.requestId})` : ''}`);
        this.etat.set('erreur');
      }),
    });
  }

  aller(p: number): void {
    this.page = p;
    this.charger();
  }

  rechercher(): void {
    this.filtrer({ q: this.saisie.trim() });
  }

  filtrer(patch: Filtres360): void {
    const vue: Vue360 = this.mode() === 'recherche' ? 'recherche' : 'profilage';
    this.navigation.emit({ vue, filtres: patch, fusion: true });
  }

  ouvrirFiche(racine: string): void {
    this.fiche.set(racine);
  }

}
