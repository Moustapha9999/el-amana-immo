import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { FeedbackService } from '../../core/feedback/feedback.service';
import { ReclamationsService, ReclamationsStore } from '../reclamations.service';
import { RcExportComponent } from './rc-export.component';

describe('Réclamations — export de la liste filtrée', () => {
  let fixture: ComponentFixture<RcExportComponent>;
  const exporter = jasmine.createSpy('exporter').and.returnValue(of(new Blob(['x'])));
  const run = jasmine.createSpy('run').and.callFake((fn: () => ReturnType<typeof of>) => fn());

  beforeEach(() => {
    exporter.calls.reset();
    spyOn(URL, 'createObjectURL').and.returnValue('blob:test');
    spyOn(URL, 'revokeObjectURL');
    TestBed.configureTestingModule({
      imports: [RcExportComponent],
      providers: [
        { provide: ReclamationsService, useValue: { exporter } },
        { provide: ReclamationsStore, useValue: { cap: (c: string) => c === 'reporting_exporter' } },
        { provide: FeedbackService, useValue: { run } },
      ],
    });
    fixture = TestBed.createComponent(RcExportComponent);
    fixture.componentRef.setInput('filtres', { statut: 'SUSPENDUE', q: 'SUSP-test' });
    fixture.detectChanges();
  });

  it('n’affiche les boutons que si l’export est autorisé, et transmet les filtres (dont Suspendue)', () => {
    expect(fixture.nativeElement.textContent).toContain('PDF');
    expect(fixture.nativeElement.textContent).toContain('Excel');
    fixture.componentInstance.telecharger('xlsx');
    expect(exporter).toHaveBeenCalledWith({ statut: 'SUSPENDUE', q: 'SUSP-test' }, 'xlsx');
  });

  it('masque l’export sans la capacité', () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [RcExportComponent],
      providers: [
        { provide: ReclamationsService, useValue: { exporter } },
        { provide: ReclamationsStore, useValue: { cap: () => false } },
        { provide: FeedbackService, useValue: { run } },
      ],
    });
    const f = TestBed.createComponent(RcExportComponent);
    f.detectChanges();
    expect(f.nativeElement.textContent).not.toContain('PDF');
  });
});
