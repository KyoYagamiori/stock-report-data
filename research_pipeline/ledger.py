"""Persist source dossiers and separately validate analyst-authored reviews.

Collecting evidence never creates a review. Even a full data set is incomplete
until the executor has written a company-specific, source-linked assessment.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

DIMENSIONS = ('business', 'financials', 'valuation', 'disclosures', 'technicals', 'synthesis')
CODE = re.compile(r'^(?:00[0-3]|30[012]|60[0135]|688)\d{3}$')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(payload, encoding='utf-8')
    temp.replace(path)


def validate_universe(rows):
    codes = [r['code'] for r in rows]
    if not rows or len(codes) != len(set(codes)):
        raise ValueError('Official universe is empty or contains duplicate codes')
    if any(not CODE.fullmatch(c) for c in codes):
        raise ValueError('Universe contains a B-share, BSE, CDR or unrecognized code')
    if any(r.get('exchange') not in ('SH', 'SZ') for r in rows):
        raise ValueError('Only official SH/SZ ordinary A-shares are eligible')


def review_errors(dossier, review, cycle, cutoff):
    if not review:
        return ['no_individual_review']
    errors = []
    if review.get('code') != dossier['code']: errors.append('wrong_code')
    if review.get('cycle') != cycle: errors.append('stale_review_cycle')
    if review.get('evidence_sha256') != digest(dossier): errors.append('evidence_changed')
    try:
        reviewed_at = datetime.fromisoformat(review['reviewed_at'])
        if reviewed_at.tzinfo is None: errors.append('review_time_has_no_timezone')
    except (KeyError, ValueError):
        errors.append('invalid_review_time')
    if review.get('information_cutoff') != cutoff: errors.append('wrong_information_cutoff')
    evidence = {e.get('id'): e for e in dossier.get('primary_evidence', [])}
    for name in DIMENSIONS:
        section = review.get('sections', {}).get(name, {})
        # This validates structure and provenance; it is not proof of prose quality.
        if len(section.get('assessment', '').strip()) < 40:
            errors.append(name + ':missing_substantive_assessment')
        refs = section.get('source_ids', [])
        if not refs or any(ref not in evidence for ref in refs):
            errors.append(name + ':missing_read_source')
    if not review.get('counterevidence') or not review.get('next_validation'):
        errors.append('missing_falsifier_or_validation')
    if dossier.get('blocking_gaps'):
        errors.extend('evidence:' + gap for gap in dossier['blocking_gaps'])
    for source in evidence.values():
        if not source.get('url') or not source.get('document_sha256'):
            errors.append('primary_evidence_without_provenance')
        if not source.get('sections_read'):
            errors.append('primary_evidence_not_read')
        known_at = source.get('available_at')
        try:
            if not known_at or datetime.fromisoformat(known_at) > datetime.fromisoformat(cutoff):
                errors.append('source_availability_outside_cutoff')
        except ValueError:
            errors.append('invalid_source_availability')
    return sorted(set(errors))


def build_coverage(universe, dossiers, reviews, cycle, cutoff, path_index):
    validate_universe(universe)
    expected = {r['code'] for r in universe}
    if set(dossiers) != expected:
        raise ValueError('Dossier code set must exactly equal the official universe')
    if set(reviews) - expected:
        raise ValueError('Review contains an out-of-universe code')
    results, completed, individually_reviewed = {}, [], []
    for code in sorted(expected):
        dossier, review = dossiers[code], reviews.get(code)
        errors = review_errors(dossier, review, cycle, cutoff)
        results[code] = errors
        if review and 'wrong_code' not in errors and 'stale_review_cycle' not in errors and 'evidence_changed' not in errors:
            individually_reviewed.append(code)
        if not errors: completed.append(code)
    # Duplicate prose never increases completion; no automated reviewed=true flags.
    fingerprints = Counter(digest(r.get('sections', {})) for r in reviews.values())
    for code in list(completed):
        if fingerprints[digest(reviews[code].get('sections', {}))] > 1:
            completed.remove(code); results[code].append('duplicate_review_prose')
    missing = sorted(expected - set(completed))
    return {
        'schema_version': '2.0', 'cycle': cycle, 'information_cutoff': cutoff,
        'scope': 'SSE/SZSE ordinary A-shares; BSE excluded',
        'exchange_counts': dict(Counter(r['exchange'] for r in universe)),
        'expected_count': len(expected), 'dossier_count': len(dossiers),
        'individual_review_count': len(individually_reviewed),
        'reviewed_count': len(completed), 'complete_count': len(completed),
        'incomplete_count': len(missing), 'missing_codes': missing, 'duplicate_codes': [],
        'completed_codes': completed, 'review_errors_by_code': results,
        'evidence_counts': {name: sum(bool(d.get(name)) for d in dossiers.values())
                            for name in ('business', 'financials', 'quote', 'technicals', 'announcements')},
        'dossier_shards': path_index,
        'focus_stock_code': None,
        'focus_status': 'full_market_analysis_incomplete' if missing else 'awaiting_final_comparison',
        'counting_note': 'Evidence coverage is not analyst review. review_errors checks provenance and structure, not quality; a real executor must read and assess each company. complete_count never follows a fetched-row count or reviewed=true flag.',
    }


def prepare(seed, universe_file, out, cycle, cutoff, reviews_dir=None, overlays_dir=None):
    universe_data = json.loads(universe_file.read_text())
    universe = universe_data['records'] if isinstance(universe_data, dict) else universe_data
    validate_universe(universe)
    profiles = json.loads((seed / 'business_profiles/profiles.json').read_text())
    finance_path = seed / 'financials/financials.json'
    finances = {r['code']: r for r in json.loads(finance_path.read_text())['records']} if finance_path.exists() else {}
    quotes = {r['code']: r for r in json.loads((seed / 'universe_quotes/universe_quotes.json').read_text())}
    announcements = json.loads((seed / 'disclosures/per_code_index.json').read_text())
    technicals = {}
    # Read every persisted per-code checkpoint, never a stale all_records.json alias.
    for path in sorted((seed / 'technicals/records').glob('*.json')):
        item = json.loads(path.read_text())
        if item.get('fetch_status') == 'success': technicals[item['code']] = item
    dossiers = {}
    for row in universe:
        code = row['code']; profile = profiles.get(code, {}); finance = finances.get(code, {})
        q = quotes.get(code, {}); ann = announcements.get(code, {})
        financial = {k:v for k,v in finance.get('latest', {}).items()
                     if v is not None and k not in ('source_evidence','debt_components_note','business_description')}
        financial['source_refs'] = {k:{'metadata_file':v.get('metadata_path'),
                                     'response_sha256':v.get('response_sha256'), 'row_index':v.get('row_index')}
                                    for k,v in finance.get('latest', {}).get('source_evidence', {}).items()}
        if not finance: financial = {}
        # Facts are retained with dated source URLs, never expanded into research prose.
        dossiers[code] = {
            'code': code, 'name': row['name'], 'exchange': row['exchange'],
            'listing_date': row.get('listing_date'), 'universe_version': row.get('version_date', row.get('official_version_date')),
            'business': {k: profile.get(k) for k in ('main_business', 'industry_level3', 'revenue_structure_period', 'revenue_structure_names', 'revenue_structure_percentages', 'source_url')},
            'financials': financial,
            'quote': {k: q.get(k) for k in ('quote_date', 'quote_time', 'close', 'prev_close', 'volume_shares', 'amount_cny', 'market_cap', 'pe_ttm', 'pb', 'valuation_source', 'quote_source', 'status')},
            'technicals': technicals.get(code),
            'announcements': {'status': ann.get('recent30_catalogue_status'),
                              'items': [{k:v.get(k) for k in ('announcement_id','title','published_at','published_time_precision','pdf_url')}
                                        for v in ann.get('announcements', [])]},
            'primary_evidence': [],
            'blocking_gaps': ['primary_financials_not_yet_read', 'current_announcements_not_yet_fully_reviewed', 'economic_peer_valuation_not_yet_reviewed', 'current_cycle_individual_synthesis_not_yet_written'],
            'automatically_generated': True, 'data_only': True, 'review_must_be_read_separately': True,
        }
        if not financial: dossiers[code]['blocking_gaps'].append('financial_data_missing')
        if code not in technicals: dossiers[code]['blocking_gaps'].append('daily_history_missing')
        if q.get('quote_date') != cutoff[:10] and q.get('quote_date') != cycle[:10]:
            # A previous completed trading day is legitimate; preserve its date.
            dossiers[code]['quote_is_historical'] = True
    if overlays_dir and overlays_dir.exists():
        for path in sorted(overlays_dir.glob('*.json')):
            overlay = json.loads(path.read_text()); code = overlay['code']
            if code not in dossiers: raise ValueError('Overlay outside official universe: ' + code)
            # Only explicitly authored source reconciliation may close evidence gaps.
            if overlay.get('cycle') != cycle: raise ValueError('Stale evidence overlay')
            for key in ('primary_evidence', 'blocking_gaps', 'financials', 'technicals', 'announcements', 'valuation'):
                if key in overlay: dossiers[code][key] = overlay[key]
            dossiers[code]['source_reconciliation'] = overlay.get('source_reconciliation')
    reviews = {}
    if reviews_dir and reviews_dir.exists():
        for path in sorted(reviews_dir.glob('*.json')):
            record = json.loads(path.read_text()); reviews[record['code']] = record
    index = {}; codes = sorted(dossiers)
    for start in range(0, len(codes), 100):
        batch = codes[start:start + 100]; path = out / 'dossiers' / f'{batch[0]}-{batch[-1]}.json'
        write_json(path, {'cycle': cycle, 'records': [dossiers[c] for c in batch]})
        for code in batch: index[code] = str(path.relative_to(out))
    coverage = build_coverage(universe, dossiers, reviews, cycle, cutoff, index)
    coverage['source_baseline_note'] = 'Imported dated 2026-10-13 public evidence. Company facts are a reusable baseline; per-cycle updates and primary-document review remain required. No claim of current complete research.'
    coverage['evidence_counts']['announcements'] = sum(bool(d['announcements'].get('items')) for d in dossiers.values())
    coverage['evidence_counts']['current_complete_announcement_search'] = sum(bool(d['announcements'].get('search_complete')) or d['announcements'].get('status') in ('searched_found_announcements','searched_no_announcements') for d in dossiers.values())
    pages = {}
    for path in sorted((seed/'financials/raw').glob('*.meta.json')):
        meta=json.loads(path.read_text())
        if meta.get('success'):
            pages['raw/'+path.name] = {k:meta.get(k) for k in ('url','fetched_at_utc','sha256','raw_bytes')}
    write_json(out/'financial_page_sources.json', pages)
    write_json(out / 'universe.json', universe)
    write_json(out / 'coverage.json', coverage)
    # Deterministic code order prevents the old Top30-only research trap.
    write_json(out / 'next_batch.json', {'cycle': cycle, 'codes': [c for c in codes if c not in coverage['completed_codes']][:100], 'remaining': coverage['incomplete_count']})
    return coverage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=Path, required=True)
    parser.add_argument('--universe', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cycle', required=True)
    parser.add_argument('--cutoff', required=True)
    parser.add_argument('--reviews', type=Path)
    parser.add_argument('--overlays', type=Path)
    args = parser.parse_args()
    coverage = prepare(args.seed, args.universe, args.out, args.cycle, args.cutoff, args.reviews, args.overlays)
    print(json.dumps({k: coverage[k] for k in ('expected_count', 'dossier_count', 'individual_review_count', 'complete_count', 'incomplete_count', 'evidence_counts')}))


if __name__ == '__main__': main()
