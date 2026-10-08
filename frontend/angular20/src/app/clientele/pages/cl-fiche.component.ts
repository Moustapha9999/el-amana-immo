import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { unsavedChanges } from '../../core/feedback/unsaved-changes.guard';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { CL_BASE, FicheClient, dateFr } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

@Component({
  selector: 'bea-cl-fiche',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, ClienteleUiComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" routerLink="/clientele/situation-pp"><mat-icon>arrow_back</mat-icon> Situations</button>
          <h1>Client {{ f()?.client?.['racine_client'] }}</h1>
          <p class="bea-cl-head__sub">{{ f()?.client?.['raison_sociale'] }}</p>
        </div>
      </header>
      @if (f(); as x) {
        <div class="bea-cl-grid">
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Identité</h2>
              @if (x.situation) { <span class="bea-cl-badge" [attr.data-s]="x.situation.profil_derive">{{ x.situation.profil_derive }}</span> }
            </div>
            <dl class="bea-cl-dl">
              <dt>Racine</dt><dd><code>{{ x.client['racine_client'] }}</code></dd>
              <dt>Nom</dt><dd>{{ x.client['raison_sociale'] }}</dd>
              <dt>Prénoms</dt><dd>{{ x.client['prenoms'] || '—' }}</dd>
              <dt>Nationalité</dt><dd>{{ x.client['nationalite'] || '—' }}</dd>
              <dt>Résident</dt><dd>{{ x.client['statut_resident'] || '—' }}</dd>
              <dt>NNI</dt><dd>{{ x.client['nni'] || '—' }}</dd>
              <dt>NIF</dt><dd>{{ x.client['nif'] || '—' }}</dd>
              <dt>Catégorie</dt><dd>{{ x.client['categorie_juridique'] || '—' }}</dd>
              <dt>Agent éco.</dt><dd>{{ x.client['agent_economique'] || '—' }}</dd>
              <dt>Extraction</dt><dd>{{ dateFr(x.client['date_extraction']) }}</dd>
            </dl>
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Agrégats</h2></div>
            <dl class="bea-cl-dl">
              <dt>État</dt><dd>{{ x.situation?.etat_client || '—' }}</dd>
              <dt>Agence</dt><dd>{{ agenceLib(x.situation?.code_agence, x.situation?.agence) }}</dd>
              <dt>Date ouv.</dt><dd>{{ dateFr(x.situation?.date_ouverture) }}</dd>
              <dt>Comptes</dt><dd>{{ x.situation?.nb_comptes }}</dd>
              <dt>Classe risque</dt>
              <dd>@if (x.classification) { <span class="bea-cl-badge" [attr.data-s]="x.classification.niveau">{{ x.classification.niveau }}</span> } @else { Non classé }</dd>
              <dt>Dernier import</dt><dd>{{ x.dernier_import?.fichier_nom || '—' }}</dd>
            </dl>
          </section>
        </div>
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Classification</h2>
            @if (x.classification) { <span class="bea-cl-badge" [attr.data-s]="x.classification.source">{{ x.classification.source }}</span> }
          </div>
          @if (x.classification) {
            <dl class="bea-cl-dl">
              <dt>Niveau</dt><dd>{{ x.classification.niveau }}</dd>
              <dt>Motif risque</dt><dd>{{ x.classification.motif_risque || '—' }}</dd>
              <dt>Motif classement</dt><dd>{{ x.classification.motif_classement || '—' }}</dd>
            </dl>
            <ul class="bea-cl-anoms">
              @for (m of x.classification.motifs; track $index) {
                <li><mat-icon>flag</mat-icon>{{ m.libelle || m.critere }} — {{ m.motif }}</li>
              }
            </ul>
          } @else {
            <p class="bea-cl-hint" style="padding:0.9rem 1.1rem">Pas encore classé. Une donnée absente n’est jamais Faible. 0 critère exploitable → NON CLASSÉ.</p>
          }
          @if (store.cap().classif_voir) {
            <div class="bea-cl-filters">
              <label>&nbsp;<button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="evaluer()">Recalculer (proposition)</button></label>
            </div>
          }
          @if (evaluation(); as e) {
            <dl class="bea-cl-dl">
              <dt>Score auto</dt><dd>{{ e.score_total }} — {{ e.niveau_final || 'NON CLASSÉ' }}</dd>
              <dt>Motif</dt><dd>{{ e.motif_genere || e.motif_principal || '—' }}</dd>
              <dt>Cohérence</dt><dd>{{ e.coherence }}</dd>
            </dl>
            <ul class="bea-cl-anoms">
              @for (lg of e.lignes; track lg.critere) {
                @if (lg.etat === 'EVALUE' || lg.blocking_propose || lg.divergence) {
                  <li><mat-icon>flag</mat-icon>{{ lg.libelle }} : {{ lg.valeur || '—' }} — {{ lg.poids ?? 0 }} — {{ lg.etat }}</li>
                }
              }
            </ul>
          }
          @if (store.cap().classif_executer) {
            <div class="bea-cl-filters">
              <label>Nouveau niveau
                <select [(ngModel)]="niveau"><option>FAIBLE</option><option>MOYEN</option><option>ELEVE</option><option>INTERDIT</option></select>
              </label>
              <label>Motif classement<input [(ngModel)]="motif" /></label>
              <label>&nbsp;<button type="button" class="bea-mg__btn" (click)="classer()">Enregistrer</button></label>
            </div>
          }
        </section>
        @if (x.alertes_ouvertes.length) {
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Alertes ouvertes</h2></div>
            <ul class="bea-cl-anoms">
              @for (al of x.alertes_ouvertes; track al.id) {
                <li data-n="alerte"><mat-icon>notification_important</mat-icon>
                  <a [routerLink]="['/clientele/filtrage', al.id]">{{ al.motif }} — {{ al.statut }}</a>
                  @if (al.precedent_faux_positif) { (FP antérieur) }
                </li>
              }
            </ul>
          </section>
        }
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Comptes / RIB</h2><span class="bea-mg__count">{{ x.comptes.length }}</span></div>
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table">
              <thead><tr><th>Compte</th><th>RIB</th><th>Agence</th><th>État</th><th>Devise</th><th>Ouverture</th></tr></thead>
              <tbody>
                @for (c of x.comptes; track c.compte) {
                  <tr>
                    <td><code>{{ c.compte }}</code></td>
                    <td><code>{{ c.rib }}</code></td>
                    <td>{{ agenceLib(c.code_agence, c.agence) }}</td>
                    <td><span class="bea-cl-badge" [attr.data-s]="c.etat_compte === 'FERME' ? 'CLOTURE' : 'OUVERT'">{{ c.etat_compte }}</span></td>
                    <td>{{ c.devise }}</td>
                    <td>{{ dateFr(c.date_ouverture) }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </section>
      }
    </div>
  `,
})
export class ClFicheComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  readonly store = inject(ClienteleStore);
  readonly f = signal<FicheClient | null>(null);
  readonly evaluation = signal<{
    score_total: number; niveau_final: string | null; niveau_max: string | null;
    motif_principal: string | null; motif_genere?: string; coherence: string;
    lignes: { critere: string; libelle: string; etat: string; valeur: string | null; poids: number | null; blocking_propose: boolean; divergence: boolean }[];
  } | null>(null);
  readonly dateFr = dateFr;

  agenceLib(code: string | null | undefined, libelle: string | null | undefined): string {
    if (!code) return '—';
    return libelle ? `${code} — ${libelle}` : code;
  }
  niveau = 'MOYEN';
  motif = '';
  readonly hasUnsavedChanges = unsavedChanges(() => !!this.motif.trim());

  ngOnInit(): void {
    this.store.charger();
    this.recharger();
  }

  private recharger(): void {
    const racine = this.route.snapshot.paramMap.get('racine') ?? '';
    this.api.get<FicheClient>(`${CL_BASE}/clients/${racine}`).subscribe({
      next: (d) => this.f.set(d),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Fiche introuvable')),
    });
  }

  classer(): void {
    const racine = this.f()?.client?.['racine_client'];
    if (!racine || !this.motif.trim()) {
      this.feedback.warning({ title: 'Motif obligatoire', message: 'Indiquez le motif de classement.' });
      return;
    }
    this.feedback.run(() => this.api.post(`${CL_BASE}/clients/${racine}/classification`, {
      niveau: this.niveau, motif_classement: this.motif,
    }), {
      confirm: { action: 'validation', title: 'Modifier la classification', message: `Classer ${racine} en ${this.niveau} ?`, hint: 'La racine n’est pas modifiable.' },
      success: { title: 'Classification enregistrée' }, errorTitle: 'Enregistrement refusé',
    }).subscribe(() => { this.motif = ''; this.recharger(); });
  }

  evaluer(): void {
    const racine = this.f()?.client?.['racine_client'];
    if (!racine) return;
    this.feedback.run(() => this.api.post<{
      score_total: number; niveau_final: string | null; niveau_max: string | null;
      motif_principal: string | null; motif_genere?: string; coherence: string;
      lignes: { critere: string; libelle: string; etat: string; valeur: string | null; poids: number | null; blocking_propose: boolean; divergence: boolean }[];
    }>(`${CL_BASE}/classification/evaluer`, {
      racine, persister: true,
    }), {
      loading: 'Évaluation…',
      success: (e) => ({ title: 'Évaluation proposition', message: `Score ${e.score_total} — ${e.niveau_final || 'NON CLASSÉ'}` }),
      errorTitle: 'Évaluation refusée',
    }).subscribe((e) => this.evaluation.set(e));
  }
}
