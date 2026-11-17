import {
  DOCUMENT_STATUS_LABELS,
  documentNeverValidated,
  documentWarningLines,
  formatDocumentKind,
  splitCampaignDocuments,
  type RbcmDocument,
} from './rbcm.models';

function doc(partial: Partial<RbcmDocument> & Pick<RbcmDocument, 'id' | 'status'>): RbcmDocument {
  return {
    campaign_id: 'c1',
    kind: 'EXCEL',
    format: 'xlsx',
    document_seq: null,
    filename: 'f.xlsx',
    sha256: null,
    sha256_available: false,
    created_at: null,
    created_by_id: null,
    template_id: null,
    superseded_by_id: null,
    is_current_work: partial.status === 'WORK',
    regulatory_validated: false,
    work_disclaimer: partial.status === 'WORK' ? 'non validé' : null,
    generation_kind: partial.status === 'GENERATED' ? 'technical_export' : 'documentary',
    ...partial,
  };
}

describe('Reporting BCM SM — documents (T3.5-3-E)', () => {
  it('sépare WORK, SUPERSEDED et GENERATED sans jamais étiqueter VALIDATED', () => {
    const split = splitCampaignDocuments([
      doc({ id: 'g', status: 'GENERATED', is_current_work: false }),
      doc({ id: 's', status: 'SUPERSEDED', document_seq: 1, is_current_work: false }),
      doc({ id: 'w', status: 'WORK', document_seq: 2, is_current_work: true }),
    ]);
    expect(split.work?.id).toBe('w');
    expect(split.superseded.map((d) => d.id)).toEqual(['s']);
    expect(split.generated.map((d) => d.id)).toEqual(['g']);
    expect(DOCUMENT_STATUS_LABELS['WORK']).not.toMatch(/valid/i);
    expect(documentNeverValidated(split.work!)).toBeTrue();
  });

  it('présente Excel comme format métier', () => {
    expect(formatDocumentKind({ kind: 'EXCEL', format: 'xlsx' })).toBe('Excel (xlsx)');
  });

  it('traduit les avertissements API sans exposer de chemin', () => {
    const lines = documentWarningLines({
      regulatory_validation: false,
      stored_path: '/secret',
      gates_open: { D01: true, D09: true, D02: false },
      div_zero_possible: true,
      concordance_true_if_empty: true,
      graph_parse_errors: ['x', 'y'],
    });
    expect(lines.some((l) => /réglementaire validé/i.test(l))).toBeTrue();
    expect(lines.some((l) => l.includes('mapping') && l.includes('crédits'))).toBeTrue();
    expect(lines.join(' ')).not.toContain('/secret');
    expect(lines.some((l) => l.includes('2 formule'))).toBeTrue();
  });
});
