import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { FeedbackService } from '../core/feedback/feedback.service';

export interface StockAlerteLive {
  article_id: string | null;
  code: string | null;
  designation: string | null;
  stock_actuel: number | null;
  stock_min: number | null;
  niveau: string;
  type_alerte?: string;
  titre?: string | null;
  message?: string | null;
}

const ALERTES_PATH = '/stock-fournitures/alertes';
const POLL_MS = 30_000;
const MIN_GAP_MS = 5_000;
const MAX_POPUPS = 3;
const SEEN_KEY = 'bea.stock.alertesVues';
const SUMMARY_KEY = 'bea.stock.alertesResume';

/**
 * Surveille les alertes stock tant que le module est ouvert (quel que soit l’onglet) :
 * pop-up à l’apparition d’une alerte, notification navigateur si la fenêtre est en arrière-plan.
 */
@Injectable({ providedIn: 'root' })
export class StockAlertesWatcherService {
  private readonly api = inject(ApiService);
  private readonly feedback = inject(FeedbackService);
  private readonly router = inject(Router);

  readonly alertes = signal<StockAlerteLive[]>([]);
  readonly count = signal(0);
  readonly notificationsNavigateur = signal<NotificationPermission | 'unsupported'>(
    typeof Notification === 'undefined' ? 'unsupported' : Notification.permission,
  );

  private timer: ReturnType<typeof setInterval> | null = null;
  private lastFetch = 0;
  private inFlight = false;
  private readonly onVisible = () => {
    if (document.visibilityState === 'visible') this.refresh();
  };

  start(): void {
    if (this.timer) return;
    this.refresh(true);
    this.timer = setInterval(() => this.refresh(true), POLL_MS);
    document.addEventListener('visibilitychange', this.onVisible);
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    document.removeEventListener('visibilitychange', this.onVisible);
  }

  /** Recharge les alertes (ignoré si un appel vient d’avoir lieu, sauf `force`). */
  refresh(force = false): void {
    if (!this.timer && !force) return;
    const now = Date.now();
    if (this.inFlight || (!force && now - this.lastFetch < MIN_GAP_MS)) return;
    this.inFlight = true;
    this.lastFetch = now;
    this.api.get<StockAlerteLive[]>('/mg/stock/alertes').subscribe({
      next: (rows) => {
        this.inFlight = false;
        this.alertes.set(rows);
        this.count.set(rows.length);
        this.signalerNouvelles(rows);
      },
      error: () => {
        this.inFlight = false;
      },
    });
  }

  demanderNotificationsNavigateur(): void {
    if (typeof Notification === 'undefined') return;
    void Notification.requestPermission().then((p) => this.notificationsNavigateur.set(p));
  }

  static cle(a: StockAlerteLive): string {
    return `${a.type_alerte || a.niveau}|${a.article_id || a.code}`;
  }

  private signalerNouvelles(rows: StockAlerteLive[]): void {
    const vues = this.lireVues();
    const courantes = new Set(rows.map((a) => StockAlertesWatcherService.cle(a)));
    const nouvelles = rows.filter((a) => !vues.has(StockAlertesWatcherService.cle(a)));
    this.ecrireVues(courantes);

    const premiereFois = !sessionStorage.getItem(SUMMARY_KEY);
    if (premiereFois) {
      sessionStorage.setItem(SUMMARY_KEY, '1');
      if (rows.length) this.resume(rows);
      return;
    }
    if (!nouvelles.length) return;
    if (nouvelles.length > MAX_POPUPS) {
      this.resume(nouvelles, true);
    } else {
      nouvelles.forEach((a) => this.popup(a));
    }
    this.notifierNavigateur(nouvelles);
  }

  private popup(a: StockAlerteLive): void {
    const rupture = a.niveau === 'epuise';
    const details = a.article_id
      ? [
          { label: 'Stock actuel', value: String(a.stock_actuel ?? 0) },
          { label: 'Seuil minimum', value: String(a.stock_min ?? 0) },
        ]
      : undefined;
    const message = {
      title: rupture ? `Rupture de stock — ${a.code}` : a.article_id ? `Stock faible — ${a.code}` : a.titre || 'Alerte stock',
      message: a.article_id ? a.designation || undefined : a.designation || a.message || undefined,
      details,
      duration: rupture ? 0 : 12_000,
      action: { label: 'Voir les alertes', run: () => void this.router.navigateByUrl(ALERTES_PATH) },
    };
    if (rupture) this.feedback.error(message);
    else this.feedback.warning(message);
  }

  private resume(rows: StockAlerteLive[], nouvelles = false): void {
    const ruptures = rows.filter((a) => a.niveau === 'epuise').length;
    const faibles = rows.filter((a) => a.niveau === 'faible').length;
    const autres = rows.length - ruptures - faibles;
    const details = [
      ruptures ? { label: 'Ruptures', value: String(ruptures) } : null,
      faibles ? { label: 'Stocks faibles', value: String(faibles) } : null,
      autres ? { label: 'Autres', value: String(autres) } : null,
    ].filter((d): d is { label: string; value: string } => d !== null);
    this.feedback.warning({
      title: nouvelles ? `${rows.length} nouvelles alertes stock` : `${rows.length} alerte(s) stock en cours`,
      details,
      duration: 12_000,
      action: { label: 'Voir les alertes', run: () => void this.router.navigateByUrl(ALERTES_PATH) },
    });
  }

  private notifierNavigateur(rows: StockAlerteLive[]): void {
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
    if (document.visibilityState === 'visible') return;
    const first = rows[0];
    const body =
      rows.length > 1
        ? `${rows.length} nouvelles alertes (dont ${first.code} — ${first.designation ?? ''})`
        : `${first.code} — ${first.designation ?? ''}`;
    const n = new Notification(first.niveau === 'epuise' ? 'BEA DIGITAL — Rupture de stock' : 'BEA DIGITAL — Alerte stock', {
      body,
      icon: '/brand/icon-bea.png',
      tag: 'bea-stock-alertes',
    });
    n.onclick = () => {
      window.focus();
      void this.router.navigateByUrl(ALERTES_PATH);
      n.close();
    };
  }

  private lireVues(): Set<string> {
    try {
      return new Set(JSON.parse(sessionStorage.getItem(SEEN_KEY) || '[]') as string[]);
    } catch {
      return new Set();
    }
  }

  private ecrireVues(keys: Set<string>): void {
    try {
      sessionStorage.setItem(SEEN_KEY, JSON.stringify([...keys]));
    } catch {
      /* stockage indisponible : les alertes seront re-signalées */
    }
  }
}
