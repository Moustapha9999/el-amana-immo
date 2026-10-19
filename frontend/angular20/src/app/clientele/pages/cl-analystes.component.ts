import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { AnalysteKyc, CL_BASE, dateHeureFr } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

interface Utilisateur { id: string; full_name: string | null; email: string | null }
interface Liste { items: AnalysteKyc[]; candidats: string[] }

@Component({
  selector: 'bea-cl-analystes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, MatIconModule],
  styles: `
    .bea-an-form { display: flex; gap: 0.75rem; align-items: end; flex-wrap: wrap; padding: 0 1.1rem 0.9rem; }
    .bea-an-form label { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.72rem; font-weight: 700; color: #64748b; text-transform: uppercase; }
    .bea-an-form input, .bea-an-form select, td input, td select { font: inherit; font-size: 0.86rem; text-transform: none; padding: 0.4rem 0.55rem; border: 1px solid #cbd5e1; border-radius: 0.5rem; min-width: 13rem; }
    .bea-an-cand { display: flex; gap: 0.35rem; flex-wrap: wrap; padding: 0 1.1rem 0.9rem; }
    .bea-an-cand button { font: inherit; font-size: 0.78rem; padding: 0.3rem 0.65rem; border-radius: 999px; border: 1px dashed #94a3b8; background: #fff; cursor: pointer; }
    tr.is-off td { color: #94a3b8; }
  `,
  template: `
    <section class="bea-mg__panel">
      <div class="bea-mg__panel-top"><h2>Analystes KYC</h2><span class="bea-mg__count">{{ actifs() }} actif(s)</span></div>
      <p class="bea-cl-hint" style="padding:0 1.1rem 0.6rem">Référentiel des analystes reconnus dans l’import hebdomadaire et les décisions de classification. Un nom absent de ce référentiel est signalé comme « inconnu », jamais remplacé par une valeur par défaut. Le lien vers un compte utilisateur est facultatif.</p>
      @if (!items().length) {
        <div class="bea-cl-note bea-cl-note--warn" style="margin:0 1.1rem 0.8rem"><mat-icon>warning</mat-icon>
          <span>Référentiel vide : aucune décision manuelle ni intégration ne peut être enregistrée tant qu’au moins un analyste n’est pas ajouté.</span>
        </div>
      }
      @if (admin()) {
        <div class="bea-an-form">
          <label>Nom de l’analyste <input [(ngModel)]="nom" maxlength="120" placeholder="Prénom Nom" /></label>
          <label>Compte utilisateur (facultatif)
            <input [(ngModel)]="rechercheUser" (keyup)="chercherUtilisateurs()" placeholder="Rechercher un compte…" />
          </label>
          <label>&nbsp;
            <select [(ngModel)]="userId" aria-label="Compte utilisateur">
              <option value="">Aucun compte</option>
              @for (u of utilisateurs(); track u.id) { <option [value]="u.id">{{ u.full_name || u.email }} ({{ u.email }})</option> }
            </select>
          </label>
          <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="ajouter()" [disabled]="busy() || !nom.trim()"><mat-icon>person_add</mat-icon> Ajouter</button>
        </div>
        @if (candidats().length) {
          <p class="bea-cl-hint" style="padding:0 1.1rem 0.35rem">Noms déjà rencontrés (fichiers, décisions) absents du référentiel — cliquer pour préremplir :</p>
          <div class="bea-an-cand">
            @for (c of candidats(); track c) { <button type="button" (click)="nom = c">{{ c }}</button> }
          </div>
        }
      }
      <div class="bea-mg__table-wrap">
        <table class="bea-mg__table">
          <thead><tr><th>Nom</th><th>Compte relié</th><th>Statut</th><th>Créé le</th>@if (admin()) { <th></th> }</tr></thead>
          <tbody>
            @for (a of items(); track a.id) {
              <tr [class.is-off]="!a.actif">
                @if (edition() === a.id) {
                  <td><input [(ngModel)]="nomEdition" maxlength="120" aria-label="Nom" /></td>
                  <td>
                    <select [(ngModel)]="userEdition" aria-label="Compte relié">
                      <option value="">Aucun compte</option>
                      @if (a.user_id) { <option [value]="a.user_id">{{ a.utilisateur || a.email }}</option> }
                      @for (u of utilisateurs(); track u.id) { @if (u.id !== a.user_id) { <option [value]="u.id">{{ u.full_name || u.email }} ({{ u.email }})</option> } }
                    </select>
                  </td>
                } @else {
                  <td><strong>{{ a.nom }}</strong></td>
                  <td>{{ a.utilisateur || a.email || '—' }}</td>
                }
                <td><span class="bea-cl-badge" [attr.data-s]="a.actif ? 'OK' : 'ANCIEN_CIRCUIT'">{{ a.actif ? 'Actif' : 'Inactif' }}</span></td>
                <td>{{ dh(a.created_at) }}</td>
                @if (admin()) {
                  <td style="white-space:nowrap">
                    @if (edition() === a.id) {
                      <button type="button" class="bea-mg__btn bea-mg__btn--primary" (click)="enregistrer(a)" [disabled]="busy() || !nomEdition.trim()"><mat-icon>save</mat-icon></button>
                      <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="edition.set(null)"><mat-icon>close</mat-icon></button>
                    } @else {
                      <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="editer(a)" title="Modifier"><mat-icon>edit</mat-icon></button>
                      <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="basculer(a)" [disabled]="busy()" [title]="a.actif ? 'Désactiver' : 'Réactiver'"><mat-icon>{{ a.actif ? 'person_off' : 'person' }}</mat-icon></button>
                    }
                  </td>
                }
              </tr>
            } @empty {
              <tr><td [attr.colspan]="admin() ? 5 : 4"><div class="bea-cl-empty">Aucun analyste dans le référentiel.</div></td></tr>
            }
          </tbody>
        </table>
      </div>
    </section>
  `,
})
export class ClAnalystesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  readonly store = inject(ClienteleStore);
  readonly items = signal<AnalysteKyc[]>([]);
  readonly candidats = signal<string[]>([]);
  readonly utilisateurs = signal<Utilisateur[]>([]);
  readonly edition = signal<string | null>(null);
  readonly busy = signal(false);
  readonly admin = computed(() => !!this.store.cap().classif_admin);
  readonly actifs = computed(() => this.items().filter((a) => a.actif).length);
  readonly dh = dateHeureFr;
  nom = '';
  userId = '';
  rechercheUser = '';
  nomEdition = '';
  userEdition = '';
  private minuterie: ReturnType<typeof setTimeout> | null = null;

  ngOnInit(): void {
    this.charger();
  }

  private appliquer(r: Liste): void {
    this.items.set(r.items || []);
    this.candidats.set(r.candidats || []);
  }

  charger(): void {
    this.api.get<Liste>(`${CL_BASE}/analystes`).subscribe({
      next: (r) => this.appliquer(r),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Référentiel indisponible')),
    });
  }

  chercherUtilisateurs(): void {
    if (this.minuterie) clearTimeout(this.minuterie);
    this.minuterie = setTimeout(() => {
      this.api.get<Utilisateur[]>(`${CL_BASE}/analystes/utilisateurs`, this.rechercheUser.trim() ? { q: this.rechercheUser.trim() } : {}).subscribe({
        next: (u) => this.utilisateurs.set(u), error: () => this.utilisateurs.set([]),
      });
    }, 250);
  }

  ajouter(): void {
    const nom = this.nom.trim();
    this.feedback.run(() => this.api.post<Liste>(`${CL_BASE}/analystes`, { nom, user_id: this.userId || null }), {
      busy: this.busy, loading: 'Ajout…', success: { title: 'Analyste ajouté', message: nom }, errorTitle: 'Ajout refusé', retry: false,
    }).subscribe((r) => {
      this.appliquer(r);
      this.nom = '';
      this.userId = '';
    });
  }

  editer(a: AnalysteKyc): void {
    this.edition.set(a.id);
    this.nomEdition = a.nom;
    this.userEdition = a.user_id || '';
    if (!this.utilisateurs().length) this.chercherUtilisateurs();
  }

  enregistrer(a: AnalysteKyc): void {
    this.feedback.run(() => this.api.patch<Liste>(`${CL_BASE}/analystes/${a.id}`, {
      nom: this.nomEdition.trim(), user_id: this.userEdition || null,
    }), {
      busy: this.busy, loading: 'Enregistrement…', success: { title: 'Analyste modifié' }, errorTitle: 'Modification refusée', retry: false,
    }).subscribe((r) => {
      this.appliquer(r);
      this.edition.set(null);
    });
  }

  basculer(a: AnalysteKyc): void {
    this.feedback.run(() => this.api.patch<Liste>(`${CL_BASE}/analystes/${a.id}`, { actif: !a.actif }), {
      confirm: {
        action: 'validation', title: a.actif ? 'Désactiver l’analyste' : 'Réactiver l’analyste',
        message: `${a.actif ? 'Désactiver' : 'Réactiver'} « ${a.nom} » ?`,
        hint: a.actif ? 'Son nom ne sera plus accepté pour de nouvelles décisions ; l’historique existant est conservé.' : 'Son nom sera de nouveau accepté.',
      },
      busy: this.busy, success: { title: a.actif ? 'Analyste désactivé' : 'Analyste réactivé' }, errorTitle: 'Modification refusée', retry: false,
    }).subscribe((r) => this.appliquer(r));
  }
}
