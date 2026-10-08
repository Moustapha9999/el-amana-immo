import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { ClienteleUiComponent } from '../clientele-ui.component';
import { CL_BASE, dateHeureFr } from '../clientele.models';
import { ClienteleStore } from '../clientele.store';

interface Detail {
  id: string; racine_client: string; statut: string; motif: string; score: number;
  correspondance: Record<string, unknown>; precedent_faux_positif: boolean;
  transitions: string[];
  client: { racine_client: string; raison_sociale: string; prenoms: string | null; nni: string | null; nif: string | null } | null;
  evenements: { statut: string; commentaire: string | null; utilisateur: string | null; date: string | null }[];
  justificatifs: { id: string; nom_fichier: string; date: string | null }[];
}

@Component({
  selector: 'bea-cl-alerte',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule, ClienteleUiComponent],
  template: `
    <bea-cl-styles />
    <div class="bea-mg bea-cl">
      <header class="bea-mg__head bea-cl-head">
        <div>
          <button type="button" class="bea-mg__btn bea-mg__btn--ghost" routerLink="/clientele/filtrage"><mat-icon>arrow_back</mat-icon> Alertes</button>
          <h1>Alerte {{ a()?.motif }}</h1>
          <p class="bea-cl-head__sub">Correspondance potentielle — à confirmer, classer faux positif ou rejeter.</p>
        </div>
        @if (a(); as x) { <span class="bea-cl-badge" [attr.data-s]="x.statut">{{ x.statut }}</span> }
      </header>
      @if (a(); as x) {
        @if (x.precedent_faux_positif) {
          <p class="bea-cl-note"><mat-icon>replay</mat-icon>Occurrence précédente classée faux positif.</p>
        }
        <div class="bea-cl-grid">
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Client</h2></div>
            <dl class="bea-cl-dl">
              <dt>Racine</dt><dd><a [routerLink]="['/clientele/clients', x.racine_client]"><code>{{ x.racine_client }}</code></a></dd>
              <dt>Nom</dt><dd>{{ x.client?.raison_sociale || '—' }}</dd>
              <dt>Prénoms</dt><dd>{{ x.client?.prenoms || '—' }}</dd>
              <dt>NNI / NIF</dt><dd>{{ x.client?.nni || x.client?.nif || '—' }}</dd>
              <dt>Score</dt><dd>{{ x.score }}</dd>
            </dl>
          </section>
          <section class="bea-mg__panel">
            <div class="bea-mg__panel-top"><h2>Correspondance</h2></div>
            <dl class="bea-cl-dl">
              @for (k of cles(x.correspondance); track k) {
                <dt>{{ k }}</dt><dd>{{ txt(x.correspondance[k]) }}</dd>
              }
            </dl>
          </section>
        </div>
        @if (store.cap().filtrage_decider && x.transitions.length) {
          <section class="bea-mg__panel" style="padding:1rem">
            <label class="bea-cl-filters" style="padding:0">Commentaire
              <textarea rows="3" [(ngModel)]="commentaire" style="font:inherit;padding:0.5rem;border:1px solid #dbe3ee;border-radius:0.5rem;width:100%"></textarea>
            </label>
            <div class="bea-mg__actions" style="margin-top:0.7rem">
              @for (t of x.transitions; track t) {
                <button type="button" class="bea-mg__btn" (click)="decider(t)" [disabled]="busy()">{{ t.replaceAll('_',' ') }}</button>
              }
            </div>
            <label class="bea-mg__btn bea-mg__btn--ghost" style="margin-top:0.7rem">
              <mat-icon>attach_file</mat-icon> Justificatif
              <input type="file" hidden (change)="justif($any($event.target))" />
            </label>
          </section>
        }
        <section class="bea-mg__panel">
          <div class="bea-mg__panel-top"><h2>Historique</h2></div>
          <ul class="bea-cl-anoms">
            @for (e of x.evenements; track $index) {
              <li><mat-icon>history</mat-icon><span><strong>{{ e.statut }}</strong> — {{ e.commentaire || '—' }} ({{ e.utilisateur || '—' }}, {{ dh(e.date) }})</span></li>
            }
          </ul>
          @for (j of x.justificatifs; track j.id) {
            <p style="padding:0 1.1rem"><a href="javascript:void(0)" (click)="dl(j.id, j.nom_fichier)">{{ j.nom_fichier }}</a></p>
          }
        </section>
      }
    </div>
  `,
})
export class ClAlerteComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly route = inject(ActivatedRoute);
  readonly store = inject(ClienteleStore);
  readonly a = signal<Detail | null>(null);
  readonly busy = signal(false);
  commentaire = '';
  readonly dh = dateHeureFr;

  ngOnInit(): void {
    this.store.charger();
    this.recharger();
  }

  private recharger(): void {
    const id = this.route.snapshot.paramMap.get('id') ?? '';
    this.api.get<Detail>(`${CL_BASE}/filtrage/alertes/${id}`).subscribe({
      next: (d) => this.a.set(d),
      error: (e) => void describeApiErrorAsync(e).then((i) => this.feedback.apiError(i, 'Alerte introuvable')),
    });
  }

  decider(statut: string): void {
    const a = this.a()!;
    this.feedback.run(() => this.api.post<Detail>(`${CL_BASE}/filtrage/alertes/${a.id}/decision`, {
      statut, commentaire: this.commentaire || null,
    }), {
      confirm: { action: 'validation', title: statut.replaceAll('_', ' '), message: `Passer l’alerte en ${statut.replaceAll('_', ' ')} ?` },
      busy: this.busy, success: { title: 'Décision enregistrée' }, errorTitle: 'Décision refusée',
    }).subscribe((d) => { this.a.set(d); this.commentaire = ''; });
  }

  justif(input: HTMLInputElement): void {
    const f = input.files?.[0];
    input.value = '';
    if (!f) return;
    const fd = new FormData();
    fd.append('fichier', f);
    this.feedback.run(() => this.api.post<Detail>(`${CL_BASE}/filtrage/alertes/${this.a()!.id}/justificatifs`, fd), {
      busy: this.busy, success: { title: 'Justificatif déposé' }, errorTitle: 'Dépôt refusé',
    }).subscribe((d) => this.a.set(d));
  }

  dl(jid: string, nom: string): void {
    this.api.download(`${CL_BASE}/filtrage/alertes/${this.a()!.id}/justificatifs/${jid}`).subscribe({
      next: (b) => {
        const url = URL.createObjectURL(b);
        const a = document.createElement('a');
        a.href = url; a.download = nom; a.click(); URL.revokeObjectURL(url);
      },
    });
  }

  cles(o: Record<string, unknown>): string[] { return Object.keys(o); }
  txt(v: unknown): string { return v == null ? '—' : String(v); }
}
