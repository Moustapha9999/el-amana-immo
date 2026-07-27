import { DatePipe } from '@angular/common';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { ApiService } from '../core/services/api.service';
import { findNatureImmoOfficielle } from '../immobilisations/immobilisation.constants';
import { MontantPipe } from '../shared/montant.pipe';
import { UiDialogService } from '../shared/ui-dialog/ui-dialog.service';
import type {
  ArchiveAcquisitions,
  ArchiveDossierDetail,
  ArchiveExerciceSection,
  ArchiveFichier,
  ArchiveLigne,
  ArchiveNatureGroupe,
  ArchiveTotaux,
} from './archive.models';

/** Ligne d'affichage : titre exercice, acquisition, report d'ouverture ou S/T. */
export interface ArchiveDisplayRow {
  kind: 'header' | 'line' | 'ouverture' | 'sous_total';
  id: string;
  date_acquisition: string | null;
  designation: string;
  quantite: number | null;
  valeur_brute: number | null;
  taux: number | null;
  amt_n1: number | null;
  dotation: number | null;
  amt_fin: number | null;
  vnc: number | null;
  agence_label: string | null;
  is_report: boolean;
}

@Component({
  selector: 'app-archive-nature',
  imports: [RouterLink, DatePipe, MontantPipe, MatButtonModule, MatIconModule, MatTableModule],
  templateUrl: './archive-nature.component.html',
  styleUrl: './archive-nature.component.css',
})
export class ArchiveNatureComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly dialogs = inject(UiDialogService);
  private readonly route = inject(ActivatedRoute);

  readonly annee = signal(0);
  readonly natureCode = signal('');
  readonly dossier = signal<ArchiveDossierDetail | null>(null);
  readonly groupe = signal<ArchiveNatureGroupe | null>(null);
  readonly loading = signal(false);
  readonly uploading = signal(false);
  readonly busyId = signal<string | null>(null);
  readonly search = signal('');

  readonly columns = [
    'date',
    'designation',
    'qte',
    'vb',
    'taux',
    'amt_n1',
    'dotation',
    'amt_fin',
    'vnc',
    'agence',
  ];

  private selectedFile: File | null = null;

  readonly natureLibelle = computed(
    () => findNatureImmoOfficielle(this.natureCode())?.libelle ?? this.natureCode(),
  );

  readonly natureTitle = computed(() => `${this.natureLibelle()} ${this.annee()}`);

  readonly fichiers = computed(() => {
    const code = this.natureCode();
    return (this.dossier()?.fichiers ?? []).filter((f) => f.nature_code === code);
  });

  /** Lignes aplaties : en-tête exercice + ouverture + acquisitions + S/T. */
  readonly lignesAffichees = computed((): ArchiveDisplayRow[] => {
    const g = this.groupe();
    if (!g) return [];
    const q = this.search().trim().toLowerCase();
    const sections =
      g.sections && g.sections.length > 0 ? g.sections : this.fallbackSections(g.lignes);

    const rows: ArchiveDisplayRow[] = [];
    for (const sec of sections) {
      const lignes = q
        ? sec.lignes.filter((l) => l.designation.toLowerCase().includes(q))
        : sec.lignes;
      if (q && lignes.length === 0) continue;

      rows.push({
        kind: 'header',
        id: `header-${sec.annee}`,
        date_acquisition: null,
        designation: sec.label,
        quantite: null,
        valeur_brute: null,
        taux: null,
        amt_n1: null,
        dotation: null,
        amt_fin: null,
        vnc: null,
        agence_label: null,
        is_report: false,
      });

      if (!q && sec.ouverture) {
        rows.push(this.totauxToRow('ouverture', sec, sec.ouverture));
      }
      for (const l of lignes) {
        rows.push(this.ligneToRow(l));
      }
      if (!q) {
        rows.push(this.totauxToRow('sous_total', sec, sec.totaux));
      }
    }
    return rows;
  });

  ngOnInit(): void {
    const annee = Number(this.route.snapshot.paramMap.get('annee'));
    const nature = (this.route.snapshot.paramMap.get('natureCode') || '').trim();
    if (!annee || !nature || !findNatureImmoOfficielle(nature)) {
      void this.dialogs.error('Dossier nature invalide').subscribe();
      return;
    }
    this.annee.set(annee);
    this.natureCode.set(nature);
    this.reload();
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedFile = input.files?.[0] ?? null;
  }

  onSearch(event: Event): void {
    this.search.set((event.target as HTMLInputElement).value);
  }

  reload(): void {
    this.loading.set(true);
    const annee = this.annee();
    const nature = this.natureCode();
    this.api.get<ArchiveDossierDetail>(`/archives/dossiers/${annee}`).subscribe({
      next: (d) => {
        this.dossier.set(d);
        this.api
          .get<ArchiveAcquisitions>(`/archives/dossiers/${annee}/acquisitions`, {
            nature_code: nature,
          })
          .subscribe({
            next: (acq) => {
              this.groupe.set(acq.groupes[0] ?? null);
              this.loading.set(false);
            },
            error: (err: { error?: { detail?: unknown } }) => {
              this.loading.set(false);
              const detail = err.error?.detail;
              void this.dialogs
                .error(typeof detail === 'string' ? detail : 'Impossible de charger les lignes')
                .subscribe();
            },
          });
      },
      error: (err: { error?: { detail?: unknown } }) => {
        this.loading.set(false);
        const detail = err.error?.detail;
        void this.dialogs
          .error(typeof detail === 'string' ? detail : 'Dossier introuvable')
          .subscribe();
      },
    });
  }

  upload(): void {
    if (!this.selectedFile) {
      void this.dialogs.error('Choisissez un fichier Excel ou PDF').subscribe();
      return;
    }
    const nature = this.natureCode();
    if (!nature) {
      void this.dialogs.error('Nature manquante — rouvrez AAI 2008 depuis le dossier').subscribe();
      return;
    }
    this.uploading.set(true);
    this.api
      .upload<ArchiveFichier>(`/archives/dossiers/${this.annee()}/fichiers`, this.selectedFile, {
        nature_code: nature,
      })
      .subscribe({
        next: (f) => {
          this.uploading.set(false);
          this.selectedFile = null;
          const input = document.getElementById('arn-file') as HTMLInputElement | null;
          if (input) input.value = '';
          if (f.parse_status === 'error') {
            void this.dialogs
              .error(f.parse_error || 'Scan en erreur — fichier conservé')
              .subscribe();
          }
          this.reload();
        },
        error: (err: { error?: { detail?: unknown } }) => {
          this.uploading.set(false);
          const detail = err.error?.detail;
          let msg = 'Upload impossible';
          if (typeof detail === 'string') {
            msg = detail;
          } else if (Array.isArray(detail) && detail[0]?.msg) {
            msg = String(detail[0].msg);
          }
          void this.dialogs.error(msg).subscribe();
        },
      });
  }

  rescan(f: ArchiveFichier): void {
    this.busyId.set(f.id);
    this.api
      .post<ArchiveFichier>(`/archives/dossiers/${this.annee()}/fichiers/${f.id}/rescan`, {})
      .subscribe({
        next: () => {
          this.busyId.set(null);
          this.reload();
        },
        error: (err: { error?: { detail?: unknown } }) => {
          this.busyId.set(null);
          const detail = err.error?.detail;
          void this.dialogs
            .error(typeof detail === 'string' ? detail : 'Rescan impossible')
            .subscribe();
        },
      });
  }

  download(f: ArchiveFichier): void {
    this.api.download(`/archives/dossiers/${this.annee()}/fichiers/${f.id}/download`).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = f.filename;
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => void this.dialogs.error('Téléchargement impossible').subscribe(),
    });
  }

  remove(f: ArchiveFichier): void {
    this.dialogs
      .confirmAction('suppression', `Supprimer « ${f.filename} » et ses lignes extraites ?`)
      .subscribe((ok) => {
        if (!ok) return;
        this.busyId.set(f.id);
        this.api.delete(`/archives/dossiers/${this.annee()}/fichiers/${f.id}`).subscribe({
          next: () => {
            this.busyId.set(null);
            this.reload();
          },
          error: (err: { error?: { detail?: unknown } }) => {
            this.busyId.set(null);
            const detail = err.error?.detail;
            void this.dialogs
              .error(typeof detail === 'string' ? detail : 'Suppression impossible')
              .subscribe();
          },
        });
      });
  }

  statusLabel(status: string): string {
    switch (status) {
      case 'ok':
        return 'OK';
      case 'error':
        return 'Erreur';
      case 'partial':
        return 'Partiel';
      default:
        return 'En attente';
    }
  }

  formatTaux(taux: number | null): string {
    if (taux == null || Number.isNaN(Number(taux))) {
      return '—';
    }
    const n = Number(taux);
    const compact = Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/\.?0+$/, '');
    return `${compact} %`;
  }

  private fallbackSections(lignes: ArchiveLigne[]): ArchiveExerciceSection[] {
    const byYear = new Map<number, ArchiveLigne[]>();
    for (const l of lignes) {
      const y = l.date_acquisition ? Number(l.date_acquisition.slice(0, 4)) : 0;
      const list = byYear.get(y) ?? [];
      list.push(l);
      byYear.set(y, list);
    }
    const years = [...byYear.keys()].sort((a, b) => a - b);
    const merged = new Map<number, ArchiveLigne[]>();
    for (let i = 0; i < years.length; i++) {
      const y = years[i];
      const yLines = byYear.get(y) ?? [];
      const onlyReports = yLines.length > 0 && yLines.every((l) => l.is_report);
      if (onlyReports && i + 1 < years.length) {
        const nextY = years[i + 1];
        merged.set(nextY, [...(merged.get(nextY) ?? []), ...yLines]);
        continue;
      }
      merged.set(y, [...(merged.get(y) ?? []), ...yLines]);
    }
    const sections: ArchiveExerciceSection[] = [];
    let cum: ArchiveLigne[] = [];
    let prev: ArchiveTotaux | null = null;
    for (const y of [...merged.keys()].sort((a, b) => a - b)) {
      const yearLines = merged.get(y) ?? [];
      cum = cum.concat(yearLines);
      const tot = this.sumTotaux(cum);
      sections.push({
        annee: y,
        label: y ? `Exercice ${y}` : 'Sans date',
        ouverture: prev,
        lignes: yearLines,
        totaux: tot,
      });
      prev = tot;
    }
    return sections;
  }

  private ligneToRow(l: ArchiveLigne): ArchiveDisplayRow {
    return {
      kind: 'line',
      id: l.id,
      date_acquisition: l.date_acquisition,
      designation: l.designation,
      quantite: l.quantite,
      valeur_brute: l.valeur_brute,
      taux: l.taux,
      amt_n1: l.amt_n1,
      dotation: l.dotation,
      amt_fin: l.amt_fin,
      vnc: l.vnc,
      agence_label: l.agence_label,
      is_report: l.is_report,
    };
  }

  private totauxToRow(
    kind: 'ouverture' | 'sous_total',
    sec: ArchiveExerciceSection,
    t: ArchiveTotaux,
  ): ArchiveDisplayRow {
    const prevYear = sec.annee > 0 ? sec.annee - 1 : 0;
    const designation =
      kind === 'ouverture'
        ? `Report exercice ${prevYear}`
        : `S/T au 31/12/${sec.annee || '—'}`;
    const dateStr =
      kind === 'ouverture'
        ? sec.annee
          ? `${sec.annee}-01-01`
          : null
        : sec.annee
          ? `${sec.annee}-12-31`
          : null;
    return {
      kind,
      id: `${kind}-${sec.annee}`,
      date_acquisition: dateStr,
      designation,
      quantite: null,
      valeur_brute: t.valeur_brute,
      taux: null,
      amt_n1: t.amt_n1,
      dotation: t.dotation,
      amt_fin: t.amt_fin,
      vnc: t.vnc,
      agence_label: null,
      is_report: kind === 'ouverture',
    };
  }

  private sumTotaux(lignes: ArchiveLigne[]): ArchiveTotaux {
    return lignes.reduce(
      (acc, l) => ({
        valeur_brute: acc.valeur_brute + Number(l.valeur_brute || 0),
        amt_n1: acc.amt_n1 + Number(l.amt_n1 || 0),
        dotation: acc.dotation + Number(l.dotation || 0),
        amt_fin: acc.amt_fin + Number(l.amt_fin || 0),
        vnc: acc.vnc + Number(l.vnc || 0),
        nb_lignes: acc.nb_lignes + 1,
      }),
      { valeur_brute: 0, amt_n1: 0, dotation: 0, amt_fin: 0, vnc: 0, nb_lignes: 0 },
    );
  }
}
