import unittest
from research_pipeline.ledger import build_coverage, digest, validate_universe
from research_pipeline.financials import audit_pages, periods_for_asof


class ResearchCoverageTests(unittest.TestCase):
    cutoff = '2026-10-14T09:00:00+08:00'
    cycle = '2026-10-14-early'

    def setUp(self):
        self.universe = [{'code': '000001', 'exchange': 'SZ', 'name': 'Example'}]
        self.dossier = {'code': '000001', 'primary_evidence': [{
            'id': 'filing', 'url': 'https://example.org/filing',
            'document_sha256': 'a' * 64, 'sections_read': ['Business', 'Financials'],
            'available_at': '2026-10-13T20:00:00+08:00'}], 'blocking_gaps': []}
        self.review = {'code': '000001', 'cycle': self.cycle,
            'information_cutoff': self.cutoff, 'reviewed_at': '2026-10-14T09:30:00+08:00',
            'evidence_sha256': digest(self.dossier),
            'sections': {name: {'assessment': name + ': company-specific source-backed assessment ' * 3,
                               'source_ids': ['filing']}
                         for name in ('business', 'financials', 'valuation', 'disclosures', 'technicals', 'synthesis')},
            'counterevidence': 'Specific adverse evidence', 'next_validation': 'Concrete dated trigger'}

    def coverage(self, reviews):
        return build_coverage(self.universe, {'000001': self.dossier}, reviews,
                              self.cycle, self.cutoff, {})

    def test_fetched_record_never_counts_as_review(self):
        self.dossier['reviewed'] = True
        self.assertEqual(self.coverage({})['complete_count'], 0)

    def test_complete_source_linked_review(self):
        self.assertEqual(self.coverage({'000001': self.review})['complete_count'], 1)

    def test_stale_cycle_invalidates_completion(self):
        self.review['cycle'] = '2026-10-13-evening'
        self.assertEqual(self.coverage({'000001': self.review})['complete_count'], 0)

    def test_changed_evidence_requires_new_review(self):
        self.dossier['quote'] = {'close': 12.34}
        self.assertEqual(self.coverage({'000001': self.review})['complete_count'], 0)

    def test_missing_peer_assessment_blocks_completion(self):
        self.review['sections'].pop('valuation')
        self.assertEqual(self.coverage({'000001': self.review})['complete_count'], 0)

    def test_source_after_cutoff_rejected(self):
        self.dossier['primary_evidence'][0]['available_at'] = '2026-10-14T09:01:00+08:00'
        self.review['evidence_sha256'] = digest(self.dossier)
        self.assertEqual(self.coverage({'000001': self.review})['complete_count'], 0)

    def test_missing_dossier_raises(self):
        with self.assertRaises(ValueError):
            build_coverage(self.universe, {}, {}, self.cycle, self.cutoff, {})

    def test_bse_excluded(self):
        with self.assertRaises(ValueError):
            validate_universe([{'code': '920001', 'exchange': 'BJ'}])

    def test_duplicate_universe_raises(self):
        with self.assertRaises(ValueError): validate_universe(self.universe * 2)

    def test_unfetched_provider_pages_not_hidden(self):
        payload = {'result': {'pages': 13, 'count': 6380, 'data': []}}
        meta = {'success': True, 'params': {'pageNumber': '1'}}
        audit = audit_pages([('main', '2026-06-30', payload, meta)])
        self.assertFalse(audit['complete'])
        self.assertEqual(len(audit['missing_pages']), 12)

    def test_failed_first_page_is_a_gap(self):
        audit = audit_pages([('cashflow','2026-06-30',{'result':None},{'success':False})])
        self.assertFalse(audit['complete'])
        self.assertEqual(audit['missing_pages'][0]['page'], 1)

    def test_missing_entire_table_is_a_gap(self):
        audit = audit_pages([], [('main','2026-06-30')])
        self.assertFalse(audit['complete'])

    def test_provider_total_must_equal_received_rows(self):
        audit=audit_pages([('main','2026-06-30',{'result':{'pages':1,'count':3,'data':[{}]}},
                           {'success':True,'params':{'pageNumber':1}})])
        self.assertFalse(audit['complete'])

    def test_financial_periods_roll_forward(self):
        self.assertEqual(periods_for_asof('2026-10-14')[:2], ['2026-09-30','2026-06-30'])
        self.assertEqual(periods_for_asof('2027-01-14')[0], '2026-12-31')


if __name__ == '__main__': unittest.main()
