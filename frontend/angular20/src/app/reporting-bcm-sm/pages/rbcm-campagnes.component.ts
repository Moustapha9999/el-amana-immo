import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  OnDestroy,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Subject, debounceTime, distinctUntilChanged } from 'rxjs';
import { DetailDrawerComponent } from '../../contrats-echeances/shared/detail-drawer.component';
import { RowMenu, RowMenuComponent, RowMenuItem } from '../../contrats-echeances/shared/row-menu';
import { describeApiErrorAsync } from '../../core/feedback/api-error';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ApiService } from '../../core/services/api.service';
import { RbcmContextService } from '../rbcm-context.service';
import { RbcmPagerComponent } from '../rbcm-pager.component';
import { RbcmStylesComponent } from '../rbcm-ui.component';
import {
  RBCM_API,
  RbcmCampaign,
  RbcmCampaignList,
  RbcmDeleteCheck,
  RbcmProgress,
  STATUS_LABELS,
  deleteCampaignConfirm,
  periodLabel,
  statusTone,
} from '../rbcm.models';

@Component({
  selector: 'bea-rbcm-campagnes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormsModule,
    MatIconModule,
    RouterLink,
    DetailDrawerComponent,
    DatePipe,
    RbcmStylesComponent,
    RbcmPagerComponent,
    RowMenuComponent,
  ],
  template: `
    <bea-rbcm-styles />
    <div class="bea-mg bea-rbcm">
      <header class="bea-mg__head">
        <div>
          <p class="bea-stock-page__kicker">Reporting BCM SM</p>
          <h1>Situations mensuelles</h1>
          <p class="bea-rbcm-sub">{{ total() }} SM — liste, filtres, actions CRUD contrôlées.</p>
        </div>
        <a class="bea-mg__btn bea-mg__btn--primary" routerLink="/reporting-bcm-sm/campagnes/nouvelle">
          <mat-icon>add</mat-icon> Nouvelle
        </a>
      </header>

      <div class="bea-rbcm-filters">
        <label class="bea-mg__field bea-mg__field--grow">
          <mat-icon>search</mat-icon>
          <input type="search" placeholder="Recherche…" [ngModel]="search()" (ngModelChange)="onSearch($event)" />
        </label>
        <label class="bea-mg__field">
          <mat-icon>flag</mat-icon>
          <select [ngModel]="status()" (ngModelChange)="status.set($event); page.set(1); load()" aria-label="Statut">
            <option value="">Tous les statuts</option>
            @for (s of statuses; track s) {
              <option [value]="s">{{ STATUS_LABELS[s] || s }}</option>
            }
          </select>
        </label>
        <label class="bea-mg__field">
          <mat-icon>view_list</mat-icon>
          <select [ngModel]="pageSize()" (ngModelChange)="pageSize.set(+$event); page.set(1); load()" aria-label="Taille de page">
            <option [ngValue]="10">10 / page</option>
            <option [ngValue]="25">25 / page</option>
            <option [ngValue]="50">50 / page</option>
            <option [ngValue]="100">100 / page</option>
          </select>
        </label>
      </div>

      @if (loading()) {
        <div class="bea-rbcm-empty"><mat-icon>hourglass_top</mat-icon><p>Chargement…</p></div>
      } @else if (!items().length) {
        <section class="bea-mg__panel">
          <div class="bea-rbcm-empty">
            <mat-icon>inbox</mat-icon>
            <div><strong>Aucun résultat</strong><p>Aucune SM ne correspond aux filtres.</p></div>
          </div>
        </section>
      } @else {
        <div class="bea-mg__table-wrap">
          <table class="bea-mg__table">
            <thead>
              <tr>
                <th>Période</th>
                <th>Banque</th>
                <th>Libellé / notes</th>
                <th>Responsable</th>
                <th>Statut</th>
                <th>Créée</th>
                <th class="bea-rbcm-col-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              @for (c of items(); track c.id) {
                <tr class="bea-rbcm-row" (click)="openDrawer(c)">
                  <td><strong>{{ periodLabel(c) }}</strong></td>
                  <td>{{ c.bank_code }}</td>
                  <td>{{ labelOf(c) }}</td>
                  <td>{{ c.reporting_owner_name || '—' }}</td>
                  <td>
                    <span class="bea-ct-badge" [attr.data-tone]="statusTone(c.status)">
                      {{ STATUS_LABELS[c.status] || c.status }}
                    </span>
                  </td>
                  <td>{{ c.created_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                  <td class="bea-rbcm-col-actions" (click)="$event.stopPropagation()">
                    <button
                      type="button"
                      class="bea-mg__icon-btn"
                      aria-label="Actions"
                      aria-haspopup="menu"
                      [attr.aria-expanded]="menuCampagne() === c.id && !!rowMenu.ouvert()"
                      (click)="openMenu($event, c)"
                    >
                      <mat-icon>more_vert</mat-icon>
                    </button>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        <bea-rbcm-pager
          [page]="page()"
          [pageSize]="pageSize()"
          [total]="total()"
          label="Pagination des situations mensuelles"
          noun="SM"
          (go)="go($event)"
        />
      }
      <bea-row-menu [menu]="rowMenu" />

      @if (drawer(); as d) {
        <bea-detail-drawer
          [titre]="periodLabel(d)"
          kicker="SM"
          [sousTitre]="d.bank_code + ' · ' + (STATUS_LABELS[d.status] || d.status)"
          [chargement]="drawerLoading()"
          [kpis]="drawerKpis()"
          [onglets]="drawerTabs"
          [(onglet)]="drawerTab"
          (fermer)="closeDrawer()"
          (reessayer)="openDrawer(d)"
          [large]="true"
        >
          <div drawerActions class="bea-rbcm-quick">
            <a class="bea-mg__btn bea-mg__btn--primary" [routerLink]="['/reporting-bcm-sm/campagnes', d.id]">Fiche</a>
            @if (d.status !== 'APPROUVEE' && d.status !== 'CLOTUREE') {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="editNotes(d)">Modifier</button>
            }
            <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="supprimer(d)">Supprimer</button>
            @if (deleteCheck()?.can_archive) {
              <button type="button" class="bea-mg__btn bea-mg__btn--ghost" [disabled]="busy()" (click)="archiver(d)">Archiver</button>
            }
          </div>

          @if (drawerTab() === 'resume') {
            <section>
              <h3>Informations générales</h3>
              <p><strong>Période :</strong> {{ periodLabel(d) }}</p>
              <p><strong>Créateur :</strong> {{ d.preparer_name || '—' }}</p>
              <p><strong>Responsable :</strong> {{ d.reporting_owner_name || '—' }}</p>
              <p><strong>Date de référence :</strong> {{ d.closing_date || '—' }}</p>
              <p><strong>Notes :</strong> {{ d.notes || '—' }}</p>
              <p><strong>Créée :</strong> {{ d.created_at | date: 'dd/MM/yyyy HH:mm' }}</p>
              <h3>Suppression</h3>
              <p class="bea-rbcm-hint">Vous pouvez supprimer cette SM quel que soit son statut. Tous les imports, paramètres, calculs, contrôles et documents liés seront définitivement retirés.</p>
            </section>
          }
          @if (drawerTab() === 'progression' && progress(); as p) {
            <section>
              <div class="bea-rbcm-progress"><div class="bea-rbcm-progress__bar" [style.width.%]="p.pct"></div></div>
              <p>{{ p.pct }}&nbsp;% — DET {{ p.det_validated ? 'OK' : '—' }} · Contrôles {{ p.det_validated ? 'OK' : '—' }} · Params {{ p.parameters_filled }}/{{ p.parameters_total }}</p>
            </section>
          }
        </bea-detail-drawer>
      }
    </div>
  `,
})
export class RbcmCampagnesComponent implements OnInit, OnDestroy {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly ctx = inject(RbcmContextService);
  private readonly search$ = new Subject<string>();

  readonly STATUS_LABELS = STATUS_LABELS;
  readonly statusTone = statusTone;
  readonly periodLabel = periodLabel;
  readonly statuses = Object.keys(STATUS_LABELS);

  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly items = signal<RbcmCampaign[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly pageSize = signal(25);
  readonly search = signal('');
  readonly status = signal('');
  readonly drawer = signal<RbcmCampaign | null>(null);
  readonly drawerLoading = signal(false);
  readonly progress = signal<RbcmProgress | null>(null);
  readonly deleteCheck = signal<RbcmDeleteCheck | null>(null);
  readonly drawerTab = signal('resume');
  readonly rowMenu = new RowMenu();
  readonly menuCampagne = signal<string | null>(null);
  readonly drawerTabs = [
    { key: 'resume', label: 'Résumé' },
    { key: 'progression', label: 'Progression' },
  ];

  ngOnInit(): void {
    const st = this.route.snapshot.queryParamMap.get('status');
    if (st) this.status.set(st);
    this.search$.pipe(debounceTime(300), distinctUntilChanged()).subscribe(() => {
      this.page.set(1);
      this.load();
    });
    this.load();
  }

  ngOnDestroy(): void {
    this.search$.complete();
  }

  onSearch(v: string): void {
    this.search.set(v);
    this.search$.next(v);
  }

  go(p: number): void {
    this.page.set(p);
    this.load();
  }

  labelOf(c: RbcmCampaign): string {
    if (!c.notes) return '—';
    const m = c.notes.match(/\[libellé\]\s*(.+)/);
    return m?.[1]?.split('\n')[0] ?? c.notes.slice(0, 60);
  }

  openMenu(ev: MouseEvent, c: RbcmCampaign): void {
    if (this.menuCampagne() === c.id && this.rowMenu.ouvert()) {
      this.rowMenu.fermer();
      return;
    }
    this.menuCampagne.set(c.id);
    this.rowMenu.ouvrir(ev, this.actionsFor(c));
  }

  actionsFor(c: RbcmCampaign): RowMenuItem[] {
    const items: RowMenuItem[] = [
      { icone: 'visibility', label: 'Voir les détails', action: () => this.openDrawer(c) },
      {
        icone: 'open_in_new',
        label: 'Fiche complète',
        action: () => void this.router.navigate(['/reporting-bcm-sm/campagnes', c.id]),
      },
      { icone: 'push_pin', label: 'Sélectionner', action: () => this.selectCtx(c) },
    ];
    if (c.status !== 'APPROUVEE' && c.status !== 'CLOTUREE') {
      items.splice(2, 0, { icone: 'edit', label: 'Modifier', action: () => this.editNotes(c) });
    }
    if (c.status !== 'CLOTUREE') {
      items.push({ icone: 'inventory_2', label: 'Archiver', action: () => this.archiver(c) });
    }
    if (c.status === 'CLOTUREE') {
      items.push({ icone: 'lock_open', label: 'Rouvrir', action: () => this.rouvrir(c) });
    }
    items.push({ icone: 'delete', label: 'Supprimer', danger: true, action: () => this.supprimer(c) });
    return items;
  }

  selectCtx(c: RbcmCampaign): void {
    this.ctx.select(c.id);
    this.feedback.success({ title: 'SM sélectionnée', message: periodLabel(c) });
  }

  load(): void {
    this.loading.set(true);
    const params: Record<string, string | number> = {
      page: this.page(),
      page_size: this.pageSize(),
      sort_by: 'period',
      sort_order: 'desc',
    };
    if (this.search()) params['search'] = this.search();
    if (this.status()) params['status'] = this.status();
    this.api.get<RbcmCampaignList>(`${RBCM_API}/campaigns`, params).subscribe({
      next: (r) => {
        this.items.set(r.items);
        this.total.set(r.total);
        this.loading.set(false);
      },
      error: (e) =>
        void describeApiErrorAsync(e).then((i) => {
          this.feedback.apiError(i, 'Liste des SM indisponible');
          this.loading.set(false);
        }),
    });
  }

  openDrawer(c: RbcmCampaign): void {
    this.drawer.set(c);
    this.drawerTab.set('resume');
    this.drawerLoading.set(true);
    this.progress.set(null);
    this.deleteCheck.set(null);
    this.api.get<RbcmProgress>(`${RBCM_API}/campaigns/${c.id}/progress`).subscribe({
      next: (p) => this.progress.set(p),
    });
    this.api.get<RbcmDeleteCheck>(`${RBCM_API}/campaigns/${c.id}/delete-check`).subscribe({
      next: (d) => {
        this.deleteCheck.set(d);
        this.drawerLoading.set(false);
      },
      error: () => this.drawerLoading.set(false),
    });
  }

  closeDrawer(): void {
    this.drawer.set(null);
  }

  drawerKpis() {
    const p = this.progress();
    if (!p) return [];
    return [
      { label: 'Progression', value: `${p.pct} %`, tone: null },
      { label: 'DET', value: p.det_validated ? 'OK' : '—', tone: p.det_validated ? ('ok' as const) : null },
      {
        label: 'Params',
        value: `${p.parameters_filled}/${p.parameters_total}`,
        tone: p.parameters_filled === p.parameters_total ? ('ok' as const) : ('warn' as const),
      },
    ];
  }

  editNotes(c: RbcmCampaign): void {
    this.feedback
      .runWithReason(
        (notes) => this.api.patch<RbcmCampaign>(`${RBCM_API}/campaigns/${c.id}`, { notes }),
        {
          busy: this.busy,
          reason: {
            title: 'Modifier les notes',
            message: periodLabel(c),
            confirmLabel: 'Enregistrer',
            reasonLabel: 'Notes',
            required: false,
          },
          loading: 'Enregistrement…',
          success: { title: 'SM mise à jour' },
          errorTitle: 'Modification impossible',
        },
      )
      .subscribe({
        next: (n) => {
          this.load();
          if (this.drawer()?.id === n.id) this.drawer.set(n);
        },
      });
  }

  supprimer(c: RbcmCampaign): void {
    this.api.get<RbcmDeleteCheck>(`${RBCM_API}/campaigns/${c.id}/delete-check`).subscribe({
      next: (chk) => {
        this.deleteCheck.set(chk);
        this.confirmDelete(c, chk);
      },
      error: () => this.confirmDelete(c, null),
    });
  }

  private confirmDelete(c: RbcmCampaign, chk: RbcmDeleteCheck | null): void {
    this.feedback
      .run(() => this.api.delete(`${RBCM_API}/campaigns/${c.id}`), {
        busy: this.busy,
        confirm: {
          title: 'Supprimer la SM ?',
          message: deleteCampaignConfirm(c, chk),
          confirmLabel: 'Supprimer',
          tone: 'danger',
        },
        loading: 'Suppression…',
        success: { title: 'SM supprimée' },
        errorTitle: 'Suppression impossible',
      })
      .subscribe({
        next: () => {
          this.closeDrawer();
          this.load();
          this.ctx.loadCampaigns();
        },
      });
  }

  archiver(c: RbcmCampaign): void {
    this.feedback
      .runWithReason(
        (comment) => this.api.post<RbcmCampaign>(`${RBCM_API}/campaigns/${c.id}/archive`, { comment }),
        {
          busy: this.busy,
          reason: {
            title: 'Archiver la SM ?',
            message: 'Les données (imports, paramètres, historique) sont conservées. Statut → CLOTUREE.',
            confirmLabel: 'Archiver',
            reasonLabel: 'Motif',
            required: false,
          },
          loading: 'Archivage…',
          success: { title: 'SM archivée' },
          errorTitle: 'Archivage impossible',
        },
      )
      .subscribe({
        next: () => {
          this.closeDrawer();
          this.load();
          this.ctx.loadCampaigns();
        },
      });
  }

  rouvrir(c: RbcmCampaign): void {
    this.feedback
      .runWithReason(
        (comment) => this.api.post<RbcmCampaign>(`${RBCM_API}/campaigns/${c.id}/reopen`, { comment }),
        {
          busy: this.busy,
          reason: {
            title: 'Réouverture contrôlée',
            message: 'Une nouvelle version sera créée. Les anciennes versions sont conservées.',
            confirmLabel: 'Rouvrir',
            reasonLabel: 'Motif',
            required: true,
          },
          loading: 'Réouverture…',
          success: { title: 'Nouvelle version créée' },
          errorTitle: 'Réouverture impossible',
        },
      )
      .subscribe({
        next: (n) => {
          this.closeDrawer();
          this.ctx.select(n.id);
          void this.router.navigate(['/reporting-bcm-sm/campagnes', n.id]);
        },
      });
  }
}
