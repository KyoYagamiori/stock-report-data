#!/usr/bin/env python3
"""Download ALL Eastmoney structured financial pages; not a stock recommendation.

Stdlib only. Saves exact raw bytes plus request/timing/hash and per-code evidence.
Eastmoney is a secondary financial aggregator, not primary filings read by an LLM.
Join to an independently validated CURRENT universe before claiming any coverage.
"""
import argparse
import concurrent.futures
import csv
import datetime as dt
import gzip
import hashlib
import json
import math
from pathlib import Path
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
REPORTS = {
    'income': 'RPT_DMSK_FN_INCOME',
    'balance': 'RPT_DMSK_FN_BALANCE',
    'cashflow': 'RPT_DMSK_FN_CASHFLOW',
    'main': 'RPT_F10_FINANCE_MAINFINADATA',
    'detailed_balance': 'RPT_F10_FINANCE_GBALANCE',
}
ASOF = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
def periods_for_asof(asof):
    moment = dt.date.fromisoformat(asof)
    quarters = []
    for year in (moment.year - 1, moment.year):
        for month, day in ((3,31),(6,30),(9,30),(12,31)):
            candidate = dt.date(year,month,day)
            if candidate <= moment: quarters.append(candidate)
    recent = sorted(quarters, reverse=True)[:2]
    desired = [q.isoformat() for q in recent]
    desired += [f'{recent[0].year-1}-12-31']
    desired += [q.replace(year=q.year-1).isoformat() for q in recent]
    return list(dict.fromkeys(desired))

PERIODS = periods_for_asof(ASOF)
lock = threading.Lock()
ROOT = Path(__file__).resolve().parents[1] / 'reports' / 'research' / 'state' / 'financials'


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def fetch(kind, period, page=1):
    root = ROOT / 'raw'
    root.mkdir(parents=True, exist_ok=True)
    stem = f'{kind}_{period}_p{page:03d}'
    rawpath = root / (stem + '.json.gz')
    metapath = root / (stem + '.meta.json')
    filt = f'(REPORT_DATE=\'{period}\')(NOTICE_DATE<=\'{ASOF}\')'
    if kind in ['main', 'detailed_balance']:
        filt += '(SECURITY_TYPE_CODE="058001001")'
    if kind == 'main':
        filt += '(IS_BZ="0")'
    params = {
        'reportName': REPORTS[kind], 'columns': 'ALL',
        'sortColumns': 'SECURITY_CODE,NOTICE_DATE', 'sortTypes': '1,-1',
        'pageSize': '500', 'pageNumber': str(page), 'filter': filt,
    }
    if kind == 'detailed_balance':
        params['columns'] = ','.join([
            'SECUCODE','SECURITY_CODE','SECURITY_NAME_ABBR','ORG_TYPE','REPORT_DATE','NOTICE_DATE','UPDATE_DATE',
            'SECURITY_TYPE_CODE','CURRENCY','LISTING_STATE','TOTAL_ASSETS','TOTAL_LIABILITIES','TOTAL_PARENT_EQUITY',
            'MONETARYFUNDS','SHORT_LOAN','LONG_LOAN','BOND_PAYABLE','SHORT_BOND_PAYABLE','SHORT_FIN_PAYABLE',
            'LEASE_LIAB','NONCURRENT_LIAB_1YEAR','LONG_PAYABLE','INTEREST_PAYABLE','GOODWILL','CONTRACT_LIAB',
            'TOTAL_CURRENT_ASSETS','TOTAL_CURRENT_LIAB','INVENTORY','ACCOUNTS_RECE','NOTE_RECE'])
    url = BASE + '?' + urllib.parse.urlencode(params)
    if rawpath.exists() and metapath.exists():
        raw = gzip.decompress(rawpath.read_bytes())
        meta = json.loads(metapath.read_text())
        payload = json.loads(raw)
        if meta.get('success') and meta.get('url') == url:
            return payload, meta
    attempts = []
    for attempt in range(1, 3):
        started = utcnow()
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'})
            with urllib.request.urlopen(req, timeout=12) as resp:
                raw = resp.read()
                status = resp.status
            payload = json.loads(raw)
            success = bool(payload.get('success') and payload.get('result') is not None)
            # An empty result with a successful "no data" response can be a zero-count period.
            empty = payload.get('code') in [9201] and '数据' in str(payload.get('message', ''))
            meta = {'url': url, 'params': params, 'request_started_utc': started,
                    'fetched_at_utc': utcnow(), 'http_status': status,
                    'sha256': hashlib.sha256(raw).hexdigest(), 'raw_bytes': len(raw),
                    'success': success, 'empty': empty, 'source_category': 'secondary_aggregator',
                    'attempts': attempts, 'raw_path': str(rawpath.relative_to(ROOT))}
            rawpath.write_bytes(gzip.compress(raw, mtime=0))
            write_json(metapath, meta)
            if success or empty:
                return payload, meta
            raise ValueError(f'API failure: {payload.get("code")} {payload.get("message")}')
        except Exception as exc:
            attempts.append({'attempt': attempt, 'started_utc': started,
                             'error': f'{type(exc).__name__}: {exc}'})
            if attempt < 2:
                time.sleep(0.7 * attempt)
    meta = {'url': url, 'params': params, 'success': False, 'fetched_at_utc': utcnow(),
            'attempts': attempts, 'raw_path': str(rawpath.relative_to(ROOT)) if rawpath.exists() else None}
    write_json(metapath, meta)
    return {'result': None}, meta


def num(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        n = float(x)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def shsz(row):
    code = str(row.get('SECURITY_CODE', '')).zfill(6)
    secu = str(row.get('SECUCODE', ''))
    return (secu.endswith('.SH') or secu.endswith('.SZ')) and code.startswith(('000', '001', '002', '003', '300', '301', '600', '601', '603', '605', '688', '689'))


def pct(cur, prev):
    return 100 * (cur - prev) / abs(prev) if cur is not None and prev not in [None, 0] else None


def unified(group):
    """Map each report to canonical fields without replacing absent values with zero."""
    m = group.get('main', {}).get('row', {})
    i = group.get('income', {}).get('row', {})
    b = group.get('balance', {}).get('row', {})
    c = group.get('cashflow', {}).get('row', {})
    d = group.get('detailed_balance', {}).get('row', {})
    def one(row, field): return num(row.get(field))
    def choose(a, b): return a if a is not None else b
    report_date = next((x['row'].get('REPORT_DATE', '')[:10] for x in group.values()), None)
    org_type = m.get('ORG_TYPE')
    financial = org_type in ['银行', '证券', '保险'] or any(t in str(i.get('INDUSTRY_NAME', '')) for t in ['银行', '证券', '保险'])
    values = {
        'report_date': report_date,
        'notice_dates_by_table': {k: v['row'].get('NOTICE_DATE', '')[:10] for k, v in group.items()},
        'name': i.get('SECURITY_NAME_ABBR') or m.get('SECURITY_NAME_ABBR') or b.get('SECURITY_NAME_ABBR'),
        'industry_name': i.get('INDUSTRY_NAME') or b.get('INDUSTRY_NAME') or c.get('INDUSTRY_NAME'),
        'industry_code': i.get('INDUSTRY_CODE') or b.get('INDUSTRY_CODE'),
        'org_type': org_type, 'financial_sector': financial,
        'basic_eps_cny': one(m, 'EPSJB'), 'deducted_basic_eps_cny': one(m, 'EPSKCJB'),
        'bps_cny': one(m, 'BPS'), 'weighted_roe_pct': one(m, 'ROEJQ'),
        'deducted_weighted_roe_pct': one(m, 'ROEKCJQ'), 'gross_margin_pct': one(m, 'XSMLL'),
        'net_margin_pct': one(m, 'XSJLL'),
        'revenue_cny': choose(one(i, 'TOTAL_OPERATE_INCOME'), one(m, 'TOTALOPERATEREVE')),
        'parent_profit_cny': choose(one(i, 'PARENT_NETPROFIT'), one(m, 'PARENTNETPROFIT')),
        'deducted_parent_profit_cny': choose(one(i, 'DEDUCT_PARENT_NETPROFIT'), one(m, 'KCFJCXSYJLR')),
        'revenue_yoy_pct_upstream': choose(one(m, 'TOTALOPERATEREVETZ'), one(i, 'TOI_RATIO')),
        'parent_profit_yoy_pct_upstream': choose(one(m, 'PARENTNETPROFITTZ'), one(i, 'PARENT_NETPROFIT_RATIO')),
        'deducted_profit_yoy_pct_upstream': choose(one(m, 'KCFJCXSYJLRTZ'), one(i, 'DPN_RATIO')),
        'operating_cashflow_cny': choose(one(c, 'NETCASH_OPERATE'), one(m, 'NETCASH_OPERATE_PK')),
        'investing_cashflow_cny': choose(one(c, 'NETCASH_INVEST'), one(m, 'NETCASH_INVEST_PK')),
        'financing_cashflow_cny': choose(one(c, 'NETCASH_FINANCE'), one(m, 'NETCASH_FINANCE_PK')),
        'capex_cash_cny': one(c, 'CONSTRUCT_LONG_ASSET'),
        'total_assets_cny': choose(one(b, 'TOTAL_ASSETS'), one(m, 'TOTAL_ASSETS_PK')),
        'total_liabilities_cny': choose(one(b, 'TOTAL_LIABILITIES'), one(m, 'LIABILITY')),
        'total_equity_including_minority_cny': choose(one(b, 'TOTAL_EQUITY'), one(m, 'TOTAL_EQUITY_PK')),
        'monetary_funds_cny': one(b, 'MONETARYFUNDS'),
        'receivables_cny': one(b, 'ACCOUNTS_RECE'), 'inventory_cny': one(b, 'INVENTORY'),
        'short_term_loans_cny': choose(one(d, 'SHORT_LOAN'), one(b, 'SHORT_LOAN')),
        'long_term_loans_cny': one(d, 'LONG_LOAN'),
        'bonds_payable_cny': one(d, 'BOND_PAYABLE'),
        'short_bonds_payable_cny': one(d, 'SHORT_BOND_PAYABLE'),
        'short_financing_payable_cny': one(d, 'SHORT_FIN_PAYABLE'),
        'lease_liabilities_cny': one(d, 'LEASE_LIAB'),
        'noncurrent_liabilities_due_in_one_year_cny': one(d, 'NONCURRENT_LIAB_1YEAR'),
        'long_term_payables_cny': one(d, 'LONG_PAYABLE'),
        'goodwill_cny': one(d, 'GOODWILL'),
        'contract_liabilities_cny': one(d, 'CONTRACT_LIAB'),
        'parent_equity_cny': one(d, 'TOTAL_PARENT_EQUITY'),
        'debt_assets_ratio_pct_upstream': choose(one(b, 'DEBT_ASSET_RATIO'), one(m, 'ZCFZL')),
        'interest_bearing_debt_ratio_pct_upstream': one(m, 'INTEREST_DEBT_RATIO'),
        'interest_bearing_debt_cny': None,
        'current_ratio': one(m, 'LD'), 'quick_ratio': one(m, 'SD'),
        'total_shares_at_report': one(m, 'TOTAL_SHARE'),
        'bank_npl_pct': one(m, 'NONPERLOAN'), 'bank_provision_coverage_pct': one(m, 'BLDKBBL'),
        'bank_cet1_pct': one(m, 'HXYJBCZL'), 'bank_net_interest_margin_pct': one(m, 'NET_INTEREST_MARGIN'),
        'insurance_solvency_ratio_pct': one(m, 'SOLVENCY_AR'),
        'income_total_cost_cny': one(i, 'TOTAL_OPERATE_COST'),
        'finance_expense_cny': one(i, 'FINANCE_EXPENSE'),
        'source_category': 'secondary_aggregator',
        'primary_filing_read': False,
        'business_description': None,
        'source_evidence': {k: {'raw_path': v['raw_path'], 'metadata_path': v['metadata_path'],
                               'url': v['url'], 'row_index': v['row_index'],
                               'response_sha256': v['sha256']} for k, v in group.items()},
        'available_tables': sorted(group),
    }
    profit = values['parent_profit_cny']
    ocf = values['operating_cashflow_cny']
    values['ocf_to_parent_profit_diagnostic'] = ocf / profit if not financial and profit is not None and profit > 0 and ocf is not None else None
    capex = values['capex_cash_cny']
    values['ocf_less_capex_cny'] = ocf - capex if ocf is not None and capex is not None and not financial else None
    ass, liab = values['total_assets_cny'], values['total_liabilities_cny']
    values['debt_assets_ratio_pct_recomputed'] = liab / ass * 100 if ass and liab is not None else None
    deducted = values['deducted_parent_profit_cny']
    values['nonrecurring_profit_fraction_diagnostic'] = (profit - deducted) / profit if profit is not None and profit > 0 and deducted is not None else None
    components = {k: values[k] for k in ['short_term_loans_cny', 'long_term_loans_cny', 'bonds_payable_cny',
                                       'short_bonds_payable_cny', 'short_financing_payable_cny']}
    known = [v for v in components.values() if v is not None]
    values['reported_loans_bonds_known_sum_cny'] = sum(known) if known else None
    values['debt_components_note'] = ('Known disclosed loans/bonds line items only; null is not zero. Excludes current '
                                     'maturities, lease liabilities and unclassified interest-bearing financing. '
                                     'Noncurrent liabilities due within 1 year are separately reported and not all '
                                     'automatically classified as debt. This is NOT complete interest-bearing debt.')
    return values


def normalize(outputs):
    expected_pairs = [(k, p) for k in REPORTS for p in (PERIODS[:2] if k == 'detailed_balance' else PERIODS)]
    page_audit = audit_pages(outputs, expected_pairs)
    bycode = {}
    excluded = set()
    duplicate_rows = []
    api_counts = {}
    missing_pages = []
    for kind, period, payload, meta in outputs:
        result = payload.get('result') or {}
        api_counts.setdefault(kind, {})[period] = max(api_counts.get(kind, {}).get(period, 0), result.get('count', 0))
        if not meta.get('success') and not meta.get('empty'):
            missing_pages.append({'kind': kind, 'period': period, 'url': meta['url']})
        for ix, row in enumerate(result.get('data') or []):
            code = str(row.get('SECURITY_CODE', '')).zfill(6)
            if not shsz(row):
                excluded.add(str(row.get('SECUCODE', code)))
                continue
            date = str(row.get('REPORT_DATE', ''))[:10]
            notice = str(row.get('NOTICE_DATE', ''))[:10]
            if date != period or not notice or notice > ASOF:
                raise ValueError(f'Time filter invariant failed: {kind} {code} {date} {notice}')
            group = bycode.setdefault(code, {}).setdefault(date, {})
            evidence = {'row': row, 'raw_path': meta['raw_path'], 'metadata_path': meta['raw_path'].replace('.json.gz', '.meta.json'),
                        'url': meta['url'], 'row_index': ix, 'sha256': meta.get('sha256')}
            if kind in group:
                old = group[kind]
                duplicate_rows.append({'code': code, 'period': date, 'kind': kind, 'old_notice': old['row'].get('NOTICE_DATE'),
                                       'new_notice': row.get('NOTICE_DATE'), 'old_update': old['row'].get('UPDATE_DATE'), 'new_update': row.get('UPDATE_DATE')})
                # Keep the latest disclosed/updated row still available by the analysis date.
                oldkey = (old['row'].get('NOTICE_DATE', ''), old['row'].get('UPDATE_DATE', ''))
                newkey = (row.get('NOTICE_DATE', ''), row.get('UPDATE_DATE', ''))
                if newkey <= oldkey:
                    continue
            group[kind] = evidence
    records = []
    for code, periods in sorted(bycode.items()):
        periods = {period: unified(group) for period, group in periods.items()}
        latestdate = max(periods)
        latest = periods[latestdate]
        prior_year_same = str(int(latestdate[:4]) - 1) + latestdate[4:]
        baseline = periods.get(prior_year_same)
        if baseline:
            latest['revenue_yoy_pct_recomputed_abs_base'] = pct(latest['revenue_cny'], baseline['revenue_cny'])
            latest['profit_yoy_pct_recomputed_abs_base'] = pct(latest['parent_profit_cny'], baseline['parent_profit_cny'])
            latest['deducted_profit_yoy_pct_recomputed_abs_base'] = pct(latest['deducted_parent_profit_cny'], baseline['deducted_parent_profit_cny'])
        latest['prior_year_same_period'] = prior_year_same if baseline else None
        annual = periods.get(f'{int(latestdate[:4])-1}-12-31')
        for key in ['revenue_cny', 'parent_profit_cny', 'deducted_parent_profit_cny']:
            value = None
            if annual and baseline and latestdate[:4] == ASOF[:4]:
                a, b, c = latest.get(key), annual.get(key), baseline.get(key)
                if a is not None and b is not None and c is not None:
                    value = a + b - c
            latest[key.replace('_cny', '_ttm_cny')] = value
        mandatory = ['revenue_cny', 'parent_profit_cny', 'deducted_parent_profit_cny', 'basic_eps_cny', 'bps_cny',
                     'weighted_roe_pct', 'operating_cashflow_cny', 'total_assets_cny', 'total_liabilities_cny']
        absent = [key for key in mandatory if latest[key] is None]
        gaps = ['primary_financial_filing_not_read', 'business_description_not_provided', 'full_interest_bearing_debt_not_available']
        if absent:
            gaps.append('missing_fields:' + ','.join(absent))
        if baseline is None: gaps.append('previous_year_comparison_unavailable')
        if latest['parent_profit_ttm_cny'] is None: gaps.append('ttm_profit_unavailable')
        records.append({'code': code, 'latest_report_date': latestdate, 'latest': latest, 'periods': periods,
                        'gaps': gaps, 'structured_financial_evidence_present': not absent,
                        'substantive_stock_analysis_completed': False})
    counts = {}
    for kind in REPORTS:
        counts[kind] = {p: sum(kind in bycode[c].get(p, {}) for c in bycode) for p in PERIODS}
    report = {
        'analysis_asof_date': ASOF, 'built_at_utc': utcnow(), 'source': 'Eastmoney Datacenter structured secondary data',
        'stock_analysis_completed': False, 'primary_filings_read_count': 0,
        'join_note': 'Contains historical/delisted SH/SZ issuers; must intersect current exchange-backed stock universe.',
        'unique_shsz_codes_with_any_financial_record': len(records),
        'count_with_latest_core_fields': sum(r['structured_financial_evidence_present'] for r in records),
        'latest_report_dates': {d: sum(r['latest_report_date'] == d for r in records) for d in sorted(set(r['latest_report_date'] for r in records))},
        'shsz_unique_table_period_counts': counts, 'api_table_period_counts_including_excluded': api_counts,
        'excluded_non_shsz_codes': sorted(excluded), 'duplicate_rows': duplicate_rows,
        'missing_pages': page_audit['missing_pages'] + missing_pages, 'page_audit': page_audit, 'downloaded_successful_pages': sum(bool(m.get('success')) for _, _, _, m in outputs),
        'records': records,
    }
    write_json(ROOT / 'financials.json', report)
    fields = ['code', 'latest_report_date', 'name', 'industry_name', 'org_type', 'financial_sector', 'basic_eps_cny', 'deducted_basic_eps_cny',
              'bps_cny', 'weighted_roe_pct', 'gross_margin_pct', 'revenue_cny', 'parent_profit_cny', 'deducted_parent_profit_cny',
              'revenue_yoy_pct_upstream', 'parent_profit_yoy_pct_upstream', 'deducted_profit_yoy_pct_upstream',
              'operating_cashflow_cny', 'capex_cash_cny', 'ocf_to_parent_profit_diagnostic', 'ocf_less_capex_cny',
              'total_assets_cny', 'total_liabilities_cny', 'monetary_funds_cny', 'short_term_loans_cny', 'debt_assets_ratio_pct_upstream',
              'interest_bearing_debt_ratio_pct_upstream', 'revenue_ttm_cny', 'parent_profit_ttm_cny', 'deducted_parent_profit_ttm_cny',
              'bank_npl_pct', 'bank_provision_coverage_pct', 'gaps']
    with (ROOT / 'financials.csv').open('w', newline='', encoding='utf-8-sig') as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = {k: record['latest'].get(k) for k in fields}
            row.update(code=record['code'], latest_report_date=record['latest_report_date'], gaps=';'.join(record['gaps']))
            writer.writerow(row)
    summary = {k: v for k, v in report.items() if k != 'records'}
    write_json(ROOT / 'summary.json', summary)
    return summary


def audit_pages(outputs, expected_pairs=None):
    """Reconcile provider page counts, not merely the pages passed to normalize."""
    groups = {pair: {'expected': 1, 'received': set(), 'counts': set(), 'rows': 0}
              for pair in (expected_pairs or [])}
    for kind, period, payload, meta in outputs:
        result = payload.get('result') or {}
        item = groups.setdefault((kind, period), {'expected': 0, 'received': set(), 'counts': set(), 'rows': 0})
        if meta.get('empty') and not result:
            item['expected'] = 0
        elif not meta.get('success'):
            item['expected'] = max(item['expected'], 1)
        else:
            item['expected'] = max(item['expected'], int(result.get('pages') or 0))
        if result.get('count') is not None: item['counts'].add(int(result['count']))
        if meta.get('success'):
            item['received'].add(int(meta.get('params', {}).get('pageNumber', 1)))
            item['rows'] += len(result.get('data') or [])
    missing, details = [], []
    for (kind, period), item in sorted(groups.items()):
        gaps = sorted(set(range(1, item['expected'] + 1)) - item['received'])
        missing += [{'kind': kind, 'period': period, 'page': page} for page in gaps]
        details.append({'kind': kind, 'period': period, 'expected_pages': item['expected'],
                        'received_pages': sorted(item['received']), 'observed_counts': sorted(item['counts']),
                        'totals_stable': len(item['counts']) <= 1, 'missing_pages': gaps,
                        'received_rows': item['rows'],
                        'row_count_matches': not item['counts'] or item['counts'] == {item['rows']}})
    return {'complete': not missing and bool(groups) and all(d['totals_stable'] and d['row_count_matches'] for d in details),
            'missing_pages': missing, 'tables': details}


def load_cached():
    outputs = []
    for path in sorted((ROOT / 'raw').glob('*.meta.json')):
        meta = json.loads(path.read_text())
        rawpath = path.with_name(path.name.replace('.meta.json', '.json.gz'))
        if not meta.get('success') or not rawpath.exists(): continue
        kind = next((k for k, v in REPORTS.items() if v == meta.get('params', {}).get('reportName')), None)
        period = next((p for p in PERIODS if p in meta.get('params', {}).get('filter', '')), None)
        if kind and period:
            raw = gzip.decompress(rawpath.read_bytes())
            if hashlib.sha256(raw).hexdigest() != meta.get('sha256'):
                raise ValueError('Cached response SHA-256 mismatch: ' + str(path))
            outputs.append((kind, period, json.loads(raw), meta))
    return outputs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=5)
    parser.add_argument('--asof', required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--normalize-only', action='store_true')
    args = parser.parse_args()
    global ROOT, ASOF, PERIODS
    ASOF = args.asof
    PERIODS = periods_for_asof(ASOF)
    if args.output: ROOT = args.output
    ROOT.mkdir(parents=True, exist_ok=True)
    if args.normalize_only:
        print(json.dumps(normalize(load_cached()), ensure_ascii=False))
        return
    outputs = []
    pairs = [(k, p) for k in REPORTS for p in (PERIODS[:2] if k == 'detailed_balance' else PERIODS)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        firsts = {ex.submit(fetch, k, p, 1): (k, p) for k, p in pairs}
        remaining = []
        for future in concurrent.futures.as_completed(firsts):
            kind, period = firsts[future]
            payload, meta = future.result()
            outputs.append((kind, period, payload, meta))
            result = payload.get('result') or {}
            print(f'{kind} {period}: count={result.get("count")} pages={result.get("pages")} success={meta.get("success")}', flush=True)
            remaining += [(kind, period, page) for page in range(2, int(result.get('pages', 0)) + 1)]
        futures = {ex.submit(fetch, k, p, page): (k, p, page) for k, p, page in remaining}
        for future in concurrent.futures.as_completed(futures):
            kind, period, page = futures[future]
            payload, meta = future.result()
            outputs.append((kind, period, payload, meta))
            print(f'{kind} {period} page {page}: success={meta.get("success")} rows={len((payload.get("result") or {}).get("data") or [])}', flush=True)
    summary = normalize(outputs)
    print(json.dumps({k: v for k, v in summary.items() if k not in ['excluded_non_shsz_codes', 'duplicate_rows', 'api_table_period_counts_including_excluded']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
