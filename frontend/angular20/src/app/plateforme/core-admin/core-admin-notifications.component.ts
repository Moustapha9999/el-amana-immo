import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';
import { CoreAdminIconComponent } from './core-admin-icon.component';
import { CoreAdminNotificationPage, coreAdminOpsError } from './core-admin-ops.models';

@Component({
  selector: 'bea-core-admin-notifications',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, ReactiveFormsModule, RouterLink, CoreAdminIconComponent],
  template: `
    <section class="bea-admin-dash bea-admin-ncenter">
      <header class="bea-admin-dash__head bea-admin-users__head">
        <div>
          <h1>Centre de notifications</h1>
          <p>
            Vue globale des événements notifiés aux utilisateurs — distincte du
            <a routerLink="/admin/audit">journal d’audit</a> et de la cloche personnelle.
          </p>
        </div>
        <a class="bea-admin-btn bea-admin-btn--ghost" routerLink="/admin/audit">Journal d’audit</a>
      </header>

      @if (kpis(); as k) {
        <div class="bea-admin-kpis">
          @for (card of [
            { label: 'Total', value: k.total, icon: 'notifications', tone: 'modules' },
            { label: 'Non lues', value: k.non_lues, icon: 'mark_email_unread', tone: 'alert' },
            { label: 'Lues', value: k.lues, icon: 'mark_email_read', tone: 'actions' },
            { label: 'Alertes', value: k.alertes ?? 0, icon: 'warning', tone: 'alert' },
            { label: 'Critiques', value: k.critiques ?? 0, icon: 'error', tone: 'alert' },
          ]; track card.label; let i = $index) {
            <div class="bea-admin-kpi" [attr.data-tone]="card.tone" [style.animation-delay]="i * 50 + 'ms'">
              <span class="bea-admin-kpi__icon"><bea-admin-icon [name]="card.icon" /></span>
              <div class="bea-admin-kpi__copy">
                <p class="bea-admin-kpi__label">{{ card.label }}</p>
                <p class="bea-admin-kpi__value">{{ card.value }}</p>
              </div>
            </div>
          }
        </div>
      }

      <form class="bea-admin-toolbar bea-admin-ncenter__filters" [formGroup]="filters" (ngSubmit)="search()">
        <label class="bea-admin-field bea-admin-toolbar__search">
          <span>Recherche globale</span>
          <input
            type="search"
            formControlName="search"
            placeholder="Titre, message, utilisateur, module, ID événement…"
          />
        </label>
        <label class="bea-admin-field">
          <span>Statut</span>
          <select formControlName="statut">
            <option value="tous">Tous</option>
            <option value="non_lues">Non lues</option>
            <option value="lues">Lues</option>
            <option value="archivees">Archivées</option>
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Catégorie</span>
          <select formControlName="categorie">
            <option value="">Toutes</option>
            @for (opt of categoryOptions(); track opt.code) {
              <option [value]="opt.code">{{ opt.label }}</option>
            }
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Priorité</span>
          <select formControlName="priorite">
            <option value="">Toutes</option>
            @for (opt of priorityOptions(); track opt.code) {
              <option [value]="opt.code">{{ opt.label }}</option>
            }
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Période</span>
          <select formControlName="periode">
            <option value="tous">Toutes</option>
            <option value="aujourd_hui">Aujourd’hui</option>
            <option value="7j">7 derniers jours</option>
            <option value="30j">30 derniers jours</option>
            <option value="mois">Ce mois</option>
          </select>
        </label>
        <label class="bea-admin-field">
          <span>Module</span>
          <input formControlName="module_code" placeholder="ex. immobilisations" />
        </label>
        <label class="bea-admin-field">
          <span>Département</span>
          <input formControlName="espace_code" placeholder="ex. comptabilite" />
        </label>
        <div class="bea-admin-toolbar__actions">
          <button type="submit" class="bea-admin-btn">Filtrer</button>
          <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="reset()">
            Réinitialiser
          </button>
        </div>
      </form>

      @if (erreur()) {
        <p class="bea-admin-dash__error">{{ erreur() }}</p>
      }
      @if (loading()) {
        <p class="bea-admin-dash__loading">Chargement du centre de notifications…</p>
      } @else {
        <div class="bea-admin-panel bea-admin-ncenter__panel">
          <div class="bea-admin-users__list-head">
            <div>
              <p class="bea-admin-ncenter__kicker">Événements</p>
              <h2>Toutes les notifications</h2>
            </div>
            <p>{{ total() }} résultat(s)</p>
          </div>
          <div class="bea-admin-table-wrap">
            <table class="bea-admin-table bea-admin-ncenter__table">
              <thead>
                <tr>
                  <th>Date / Heure</th>
                  <th>Émetteur</th>
                  <th>Destinataire</th>
                  <th>Titre / Message</th>
                  <th>Catégorie</th>
                  <th>Module</th>
                  <th>Priorité</th>
                  <th>État</th>
                  <th>ID</th>
                </tr>
              </thead>
              <tbody>
                @for (row of rows(); track row.id) {
                  <tr [attr.data-priorite]="row.priorite">
                    <td>{{ row.created_at | date: 'dd/MM/yyyy HH:mm' : 'Africa/Nouakchott' }}</td>
                    <td>
                      <span class="bea-admin-ncenter__emetteur">{{ row.emetteur_label || 'Système' }}</span>
                    </td>
                    <td>
                      @if (row.user_id) {
                        <a class="bea-admin-table__link" [routerLink]="['/admin/users', row.user_id]">
                          {{ row.destinataire_label || row.user_full_name || row.user_email || 'Utilisateur' }}
                        </a>
                      } @else {
                        {{ row.destinataire_label || '—' }}
                      }
                      <div class="bea-admin-sessions__meta">{{ row.destinataire_type || 'utilisateur' }}</div>
                    </td>
                    <td>
                      <strong>{{ row.titre }}</strong>
                      <div class="bea-admin-sessions__meta">{{ row.message }}</div>
                      @if (row.entity) {
                        <div class="bea-admin-sessions__meta">
                          Entité : {{ row.entity }}{{ row.entity_id ? ' · ' + row.entity_id : '' }}
                        </div>
                      }
                    </td>
                    <td>
                      <span class="bea-admin-ncenter__cat">{{ row.categorie_label || row.categorie }}</span>
                    </td>
                    <td>
                      {{ row.module_code || '—' }}
                      @if (row.espace_code) {
                        <div class="bea-admin-sessions__meta">{{ row.espace_code }}</div>
                      }
                    </td>
                    <td>
                      <span class="bea-admin-ncenter__prio" [attr.data-prio]="row.priorite">
                        {{ row.priorite_label || row.priorite }}
                      </span>
                    </td>
                    <td>
                      <span
                        class="bea-badge"
                        [class.bea-badge--actif]="!row.lu && !row.archived"
                        [class.bea-badge--bientot]="row.lu && !row.archived"
                        [class.bea-badge--inactif]="row.archived"
                      >
                        {{ row.archived ? 'Archivée' : row.lu ? 'Lue' : 'Non lue' }}
                      </span>
                    </td>
                    <td class="bea-admin-ncenter__mono">{{ row.event_code || '—' }}</td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="9" class="bea-admin-panel__empty">Aucune notification pour ces filtres.</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
          <div class="bea-admin-pager">
            <span>Page {{ page() }} / {{ totalPages() }}</span>
            <div>
              <button
                type="button"
                class="bea-admin-btn bea-admin-btn--ghost"
                [disabled]="page() <= 1"
                (click)="go(page() - 1)"
              >
                Précédent
              </button>
              <button
                type="button"
                class="bea-admin-btn bea-admin-btn--ghost"
                [disabled]="page() >= totalPages()"
                (click)="go(page() + 1)"
              >
                Suivant
              </button>
            </div>
          </div>
        </div>
      }
    </section>
  `,
})
export class CoreAdminNotificationsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  readonly loading = signal(true);
  readonly erreur = signal('');
  readonly rows = signal<CoreAdminNotificationPage['items']>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly size = 20;
  readonly kpis = signal<CoreAdminNotificationPage['kpis'] | null>(null);
  readonly filters = this.fb.nonNullable.group({
    search: '',
    statut: 'tous',
    categorie: '',
    priorite: '',
    periode: 'tous',
    module_code: '',
    espace_code: '',
  });
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));
  readonly categoryOptions = computed(() => {
    const cats = this.kpis()?.categories ?? {};
    return Object.entries(cats).map(([code, label]) => ({ code, label }));
  });
  readonly priorityOptions = computed(() => {
    const prios = this.kpis()?.priorites ?? {
      info: 'Info',
      attention: 'Attention',
      avertissement: 'Avertissement',
      critique: 'Critique',
    };
    return Object.entries(prios).map(([code, label]) => ({ code, label }));
  });

  ngOnInit(): void {
    this.reload();
  }

  search(): void {
    this.page.set(1);
    this.reload();
  }

  reset(): void {
    this.filters.reset({
      search: '',
      statut: 'tous',
      categorie: '',
      priorite: '',
      periode: 'tous',
      module_code: '',
      espace_code: '',
    });
    this.page.set(1);
    this.reload();
  }

  go(page: number): void {
    this.page.set(page);
    this.reload();
  }

  private reload(): void {
    this.loading.set(true);
    const v = this.filters.getRawValue();
    const params: Record<string, string | number> = {
      page: this.page(),
      size: this.size,
      statut: v.statut,
      periode: v.periode,
    };
    if (v.search.trim()) params['search'] = v.search.trim();
    if (v.categorie) params['categorie'] = v.categorie;
    if (v.priorite) params['priorite'] = v.priorite;
    if (v.module_code.trim()) params['module_code'] = v.module_code.trim();
    if (v.espace_code.trim()) params['espace_code'] = v.espace_code.trim();
    this.api.get<CoreAdminNotificationPage>('/plateforme/admin/notifications', params).subscribe({
      next: (data) => {
        this.rows.set(data.items ?? []);
        this.total.set(data.total ?? 0);
        this.kpis.set(data.kpis ?? null);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.erreur.set(coreAdminOpsError(err, 'Impossible de charger le centre de notifications.'));
      },
    });
  }
}
