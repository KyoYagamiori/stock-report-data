"""Bounded, resumable full-universe daily evidence collection (never reviews)."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from .ledger import write_json, validate_universe


def calculate(rows, market_date):
    rows = sorted((r for r in rows if r['day'][:10] <= market_date), key=lambda r: r['day'])[-160:]
    if not rows or len({r['day'] for r in rows}) != len(rows):
        raise ValueError('Empty or duplicate completed daily history')
    for row in rows:
        for key in ('open', 'high', 'low', 'close', 'volume'): row[key] = float(row[key])
        if not all(math.isfinite(row[k]) for k in ('open', 'high', 'low', 'close', 'volume')):
            raise ValueError('Non-finite OHLCV')
        if row['close'] <= 0 or not row['low'] <= min(row['open'], row['close']) <= max(row['open'], row['close']) <= row['high']:
            raise ValueError('Invalid OHLC bounds')
    prices = [r['close'] for r in rows]
    k = d = 50.; ema12 = ema26 = prices[0]; dea = 0.; previous = None
    for i, row in enumerate(rows):
        nine = rows[max(0, i-8):i+1]
        low = min(r['low'] for r in nine); high = max(r['high'] for r in nine)
        rsv = (row['close']-low)/(high-low)*100 if i >= 8 and high > low else 50.
        k = (2*k+rsv)/3; d = (2*d+k)/3
        if i:
            ema12 += (row['close']-ema12)*2/13
            ema26 += (row['close']-ema26)*2/27
        dif = ema12-ema26; dea += (dif-dea)*2/10
        current = {'K': k, 'D': d, 'J': 3*k-2*d, 'DIF': dif, 'DEA': dea, 'hist2': 2*(dif-dea)}
        if i == len(rows)-2: previous = current
    mid = statistics.mean(prices[-20:]) if len(rows) >= 20 else None
    sd = statistics.pstdev(prices[-20:]) if len(rows) >= 20 else None
    prev_mid = statistics.mean(prices[-21:-1]) if len(rows) >= 21 else None
    volume_ratio = rows[-1]['volume']/rows[-2]['volume'] if len(rows)>1 and rows[-2]['volume']>0 else None
    return {'bar_date': rows[-1]['day'][:10], 'history_current': rows[-1]['day'][:10] == market_date,
            'adjustment': 'unadjusted', 'bars': len(rows), 'technical_complete': len(rows)>=35,
            'last_bar': rows[-1], 'price': prices[-1],
            'boll': {'n': 20, 'sd': 2, 'ddof': 0, 'mid': mid,
                     'upper': mid+2*sd if mid is not None else None,
                     'lower': mid-2*sd if mid is not None else None, 'mid_previous': prev_mid},
            'ma': {str(n): statistics.mean(prices[-n:]) if len(rows)>=n else None for n in (10,20,60)},
            'kdj': {k: current[k] for k in ('K','D','J')},
            'macd': {k: current[k] for k in ('DIF','DEA','hist2')},
            'previous_indicators': previous, 'volume_vs_previous_ratio': volume_ratio,
            'volume_unit': 'shares', 'parameters': {'kdj': [9,3,3], 'seed': 50, 'macd': [12,26,9]},
            'analysis_reviewed': False}, rows


def fetch(code, market_date, output):
    path = output/'records'/(code+'.json')
    if path.exists():
        cached = json.loads(path.read_text())
        if cached.get('bar_date') == market_date and cached.get('adjustment') == 'unadjusted': return cached
    symbol = ('sh' if code.startswith('6') else 'sz') + code
    url = 'https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_data=/CN_MarketDataService.getKLineData?' + urlencode({'symbol':symbol,'scale':240,'ma':'no','datalen':180})
    try:
        raw = urlopen(Request(url,headers={'Referer':'https://finance.sina.com.cn/','User-Agent':'Mozilla/5.0'}),timeout=12).read()
        match = re.search(rb'\(\s*(\[.*\])\s*\)', raw, re.S)
        if not match: raise ValueError('Missing JSONP daily array')
        record, rows = calculate(json.loads(match.group(1)), market_date)
        canonical = json.dumps(rows, ensure_ascii=False, separators=(',',':')).encode()
        raw_path = output/'raw'/(code+'.json.gz'); raw_path.parent.mkdir(parents=True,exist_ok=True)
        raw_path.write_bytes(gzip.compress(canonical, mtime=0))
        record.update(code=code,fetch_status='success',source_url=url,raw_response_sha256=hashlib.sha256(raw).hexdigest(),
                      completed_history_sha256=hashlib.sha256(canonical).hexdigest(),raw_file='raw/'+raw_path.name,
                      fetched_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat())
    except Exception as exc:
        record={'code':code,'fetch_status':'failed','error':type(exc).__name__+': '+str(exc), 'analysis_reviewed':False}
    write_json(path,record)
    return record


def run(universe, market_date, output, seconds, workers):
    validate_universe(universe); output.mkdir(parents=True,exist_ok=True)
    codes = iter(sorted(r['code'] for r in universe)); deadline = time.monotonic()+seconds
    pending = {}; processed = 0
    def submit(ex):
        if time.monotonic() >= deadline: return False
        try: code = next(codes)
        except StopIteration: return False
        pending[ex.submit(fetch,code,market_date,output)] = code
        return True
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for _ in range(workers): submit(ex)
        while pending:
            ready,_ = wait(pending,return_when=FIRST_COMPLETED)
            for future in ready:
                future.result(); pending.pop(future); processed += 1
                submit(ex)
            if processed%100 < len(ready):
                write_json(output/'progress.json',{'target':len(universe),'processed_this_run':processed,'market_date':market_date,'reviewed':0})
                print(json.dumps({'processed_this_run':processed,'target':len(universe)}),flush=True)
    records=[json.loads(p.read_text()) for p in sorted((output/'records').glob('*.json'))]
    current=[r for r in records if r.get('history_current') and r.get('fetch_status')=='success']
    summary={'target':len(universe),'persisted':len(records),'current':len(current),
             'technical_complete':sum(bool(r.get('technical_complete')) for r in current),
             'failed':sum(r.get('fetch_status')=='failed' for r in records),'reviewed':0,'market_date':market_date}
    write_json(output/'progress.json',summary); return summary


def main():
    p=argparse.ArgumentParser();p.add_argument('--universe',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--market-date',required=True);p.add_argument('--max-seconds',type=int,default=360);p.add_argument('--workers',type=int,default=12)
    args=p.parse_args();u=json.loads(args.universe.read_text());u=u['records'] if isinstance(u,dict) else u
    print(json.dumps(run(u,args.market_date,args.out,args.max_seconds,args.workers)),flush=True)


if __name__=='__main__':main()
