import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { ApiService } from '../../core/services/api.service';
import { CL_BASE, n } from '../clientele.models';
import { EtatChargement, Filtres360, bornesPeriode, heure, jour } from './vue360.models';

interface Journal {
  total: number; page: number; taille: number; note: string;
  actions: { action: string; n: number }[];
  items: { id: string; action: string; objet: string; objet_id: string | null; le: string | null; utilisateur: string | null }[];
}

@Component({
  selector: 'bea-cl360-journal',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, MatIconModule],
  template: `
    <section class="bea-mg__panel">
      <div class="bea-mg__panel-top"><h2>Journal d’audit Clientèle</h2><span class="bea-mg__count">{{ etat() === 'ok' ? n(data()?.total) : '—' }}</span></div>
      @if (refuse()) {
        <div class="bea-cl360-state"><mat-icon>lock</mat-icon>Le journal d’audit est réservé aux profils de supervision (administration Clientèle, administration du profilage ou décision sur les alertes).</div>
      } @else {
        <form class="bea-cl-filters" (submit)="$event.preventDefault(); page.set(1); charger()">
          <label>Action
            <select [(ngModel)]="action" name="action" (ngModelChange)="page.set(1); charger()">
              <option value="">Toutes</option>
              @for (a of data()?.actions ?? []; track a.action) { <option [value]="a.action">{{ a.action }} ({{ n(a.n) }})</option> }
            </select>
          </label>
          <label>Identifiant d’objet<input [(ngModel)]="objetId" name="objet" maxlength="80" placeholder="racine, id d’alerte…" /></label>
          <label class="bea-cl-check" style="flex-direction:row;text-transform:none">
            <input type="checkbox" [(ngModel)]="surPeriode" name="per" (ngModelChange)="page.set(1); charger()" /> Limiter à la période
          </label>
          <label>&nbsp;<button type="submit" class="bea-mg__btn bea-mg__btn--ghost"><mat-icon>search</mat-icon> Filtrer</button></label>
        </form>
        <p class="bea-cl-hint" style="padding:0 1rem 0.6rem">{{ data()?.note }} Unité : événement d’audit.</p>
        @if (etat() === 'erreur') {
          <div class="bea-cl360-state" data-s="erreur"><mat-icon>cloud_off</mat-icon>{{ erreur() }}
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" (click)="charger()">Réessayer</button></div>
        } @else {
          <div class="bea-mg__table-wrap">
            <table class="bea-mg__table bea-cl360-table">
              <colgroup><col style="width:7.5rem" /><col style="width:20%" /><col /><col style="width:22%" /><col style="width:9rem" /></colgroup>
              <thead><tr><th>Date</th><th>Utilisateur</th><th>Action</th><th>Objet</th><th>Identifiant</th></tr></thead>
              <tbody>
                @for (j of data()?.items ?? []; track j.id) {
                  <tr>
                    <td>{{ jour(j.le) }}<span class="bea-cl360-l2">{{ heure(j.le) }}</span></td><td>{{ j.utilisateur || 'Système' }}</td><td><code>{{ j.action }}</code></td><td>{{ j.objet }}</td>
                    <td>
                      @if (j.objet === 'clientele_alerte' && j.objet_id) { <a [routerLink]="['/clientele/filtrage', j.objet_id]"><code>{{ court(j.objet_id) }}</code></a> }
                      @else if (j.objet_id && racine(j.objet_id)) { <a [routerLink]="['/clientele/clients', j.objet_id]"><code>{{ j.objet_id }}</code></a> }
                      @else { <code>{{ j.objet_id ? court(j.objet_id) : '—' }}</code> }
                    </td>
                  </tr>
                } @empty {
                  <tr><td colspan="5"><div class="bea-cl-empty">{{ etat() === 'chargement' ? 'Chargement…' : 'Aucun événement (zéro résultat).' }}</div></td></tr>
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
      }
    </section>
  `,
})
export class Cl360JournalComponent {
  private readonly api = inject(ApiService);
  readonly filtres = input.required<Filtres360>();
  readonly data = signal<Journal | null>(null);
  readonly etat = signal<EtatChargement>('chargement');
  readonly erreur = signal('');
  readonly refuse = signal(false);
  readonly page = signal(1);
  readonly pages = computed(() => Math.max(1, Math.ceil((this.data()?.total ?? 0) / (this.data()?.taille || 50))));
  action = '';
  objetId = '';
  surPeriode = false;
  readonly n = n;
  readonly jour = jour;
  readonly heure = heure;

  constructor() {
    effect(() => {
      this.filtres();
      untracked(() => { this.page.set(1); this.charger(); });
    });
  }

  charger(): void {
    const params: Record<string, string | number> = { page: this.page(), taille: 50 };
    if (this.action) params['action'] = this.action;
    if (this.objetId.trim()) params['objet_id'] = this.objetId.trim();
    if (this.surPeriode) {
      const b = bornesPeriode(this.filtres());
      if (b) { params['du'] = b.du; params['au'] = b.au; }
    }
    this.etat.set('chargement');
    this.api.get<Journal>(`${CL_BASE}/vue360/journal`, params).subscribe({
      next: (d) => { this.data.set(d); this.etat.set('ok'); },
      error: (e) => void describeApiErrorAsync(e).then((i) => {
        if (i.status === 403) { this.refuse.set(true); return; }
        this.erreur.set(`Journal indisponible : ${i.message}${i.requestId ? ` (réf. ${i.requestId})` : ''}`);
        this.etat.set('erreur');
      }),
    });
  }

  aller(p: number): void {
    this.page.set(p);
    this.charger();
  }

  racine(id: string): boolean {
    return /^\d{6}$/.test(id);
  }

  court(id: string): string {
    return id.length > 13 ? `${id.slice(0, 8)}…` : id;
  }
}
