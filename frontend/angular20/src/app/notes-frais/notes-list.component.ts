import { MontantPipe } from '../shared/montant.pipe';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormArray, FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/services/api.service';
import { MgGedPanelComponent } from '../moyens-generaux/mg-ged-panel.component';

interface Note {
  id: string;
  reference: string;
  date_demande: string;
  demandeur_nom: string | null;
  statut: string;
  total_mru: number;
}

@Component({
  selector: 'bea-notes-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, RouterLink, MontantPipe, MgGedPanelComponent],
  template: `
    <section class="bea-stock-page">
      <header class="bea-stock-page__head">
        <div>
          <p class="bea-stock-page__kicker">Notes de frais</p>
          <h1>{{ mode() === 'list' ? 'Registre' : 'Fiche note de frais' }}</h1>
        </div>
        <a class="bea-admin-btn" routerLink="/notes-frais/nouvelle">Nouvelle note</a>
      </header>

      @if (mode() === 'list') {
        <div class="bea-mg__table-scroll">
        <table class="bea-stock-table">
          <thead><tr><th>Réf.</th><th>Date</th><th>Demandeur</th><th>Total</th><th>Statut</th><th></th></tr></thead>
          <tbody>
            @for (n of notes(); track n.id) {
              <tr>
                <td>{{ n.reference }}</td><td>{{ n.date_demande }}</td>
                <td>{{ n.demandeur_nom || '—' }}</td>
                <td>{{ n.total_mru | montant }}</td>
                <td>{{ n.statut }}</td>
                <td><a [routerLink]="['/notes-frais/notes', n.id]">Ouvrir</a></td>
              </tr>
            }
          </tbody>
        </table>
        </div>
      } @else {
        <form class="bea-stock-form" [formGroup]="form" (ngSubmit)="save()">
          <div class="bea-stock-form__grid">
            <label>Date demande <input type="date" formControlName="date_demande" /></label>
            <label>Demandeur <input formControlName="demandeur_nom" /></label>
            <label>Département <input formControlName="departement" /></label>
            <label>Fonction <input formControlName="fonction" /></label>
          </div>
          <h2>Dépenses</h2>
          <div formArrayName="lignes">
            @for (c of lignes.controls; track $index; let i = $index) {
              <div class="bea-stock-form__grid" [formGroupName]="i">
                <label>Date <input type="date" formControlName="date_depense" /></label>
                <label>Description <input formControlName="description" /></label>
                <label>Motif <input formControlName="motif" /></label>
                <label>Montant <input type="number" formControlName="montant" /></label>
                <label>Règlement <input formControlName="mode_reglement" /></label>
              </div>
            }
          </div>
          <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="addLigne()">+ Ligne</button>
          <div class="bea-stock-form__actions">
            <button type="submit" class="bea-admin-btn">Enregistrer</button>
            @if (noteId()) {
              <button type="button" class="bea-admin-btn" (click)="transition('soumettre')">Soumettre</button>
              <button type="button" class="bea-admin-btn" (click)="transition('visa_mg')">Visa MG</button>
              <button type="button" class="bea-admin-btn" (click)="transition('visa_dr')">Visa DR</button>
              <button type="button" class="bea-admin-btn" (click)="transition('valider')">Valider</button>
            }
            <a routerLink="/notes-frais/notes">Retour</a>
          </div>
          @if (noteId(); as id) {
            <button type="button" class="bea-admin-btn bea-admin-btn--ghost" (click)="downloadPdf()">PDF</button>
            <bea-mg-ged moduleCode="notes-frais" entity="note_frais" [entityId]="id" />
          }
          @if (erreur()) { <p class="bea-stock-page__error">{{ erreur() }}</p> }
        </form>
      }
    </section>
  `,
})
export class NotesListComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly mode = signal<'list' | 'edit'>('list');
  readonly notes = signal<Note[]>([]);
  readonly noteId = signal<string | null>(null);
  readonly erreur = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    date_demande: ['', Validators.required],
    demandeur_nom: [''],
    departement: [''],
    fonction: [''],
    lignes: this.fb.array([this.newLigne()]),
  });

  get lignes(): FormArray {
    return this.form.get('lignes') as FormArray;
  }

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    const path = this.route.snapshot.routeConfig?.path ?? '';
    if (path === 'nouvelle' || id) {
      this.mode.set('edit');
      this.noteId.set(id);
      const today = new Date().toISOString().slice(0, 10);
      this.form.patchValue({ date_demande: today });
      this.lignes.at(0)?.patchValue({ date_depense: today });
    } else {
      this.api.get<Note[]>('/mg/notes-frais/notes').subscribe({
        next: (rows) => this.notes.set(rows),
        error: () => this.erreur.set('Chargement impossible.'),
      });
    }
  }

  newLigne() {
    return this.fb.nonNullable.group({
      date_depense: ['', Validators.required],
      description: ['', Validators.required],
      motif: [''],
      montant: [0, Validators.required],
      mode_reglement: [''],
    });
  }

  addLigne(): void {
    this.lignes.push(this.newLigne());
  }

  save(): void {
    if (this.form.invalid) return;
    const body = this.form.getRawValue();
    const req = this.noteId()
      ? this.api.patch<Note>(`/mg/notes-frais/notes/${this.noteId()}`, body)
      : this.api.post<Note>('/mg/notes-frais/notes', body);
    req.subscribe({
      next: (n) => void this.router.navigateByUrl(`/notes-frais/notes/${n.id}`),
      error: () => this.erreur.set('Enregistrement impossible.'),
    });
  }

  transition(action: string): void {
    const id = this.noteId();
    if (!id) return;
    this.api.post(`/mg/notes-frais/notes/${id}/transition`, { action }).subscribe({
      next: () => this.erreur.set(null),
      error: () => this.erreur.set('Transition refusée.'),
    });
  }

  downloadPdf(): void {
    const id = this.noteId();
    if (!id) return;
    this.api.download(`/mg/notes-frais/notes/${id}/pdf`).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `note-${id}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      },
      error: () => this.erreur.set('Export PDF impossible.'),
    });
  }
}
