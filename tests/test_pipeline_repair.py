import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from pipeline.schedule import resolve_schedule
from pipeline.publisher import publish_snapshot, refresh_manifest, write_health, verify_pointer
from pipeline.calendar import resolve_calendar
from pipeline.adapters.direct_quotes import parse_quotes, parse_tencent
from tests.helpers import valid_snapshot
from tests.test_publisher import calendar

TZ = ZoneInfo('Asia/Shanghai')

class RepairTests(unittest.TestCase):
    def test_delayed_early_becomes_actual_intraday_not_fake_early(self):
        p = resolve_schedule('schedule', '17 0 * * 1-5', moment=datetime(2026,10,12,13,51,tzinfo=TZ))
        self.assertEqual(('intraday','13:51','2026-10-12','delayed-current-phase'),
                         (p.snapshot_type,p.planned_at,p.report_date,p.attempt_role))

    def test_cross_midnight_evening_does_not_make_future_time(self):
        p = resolve_schedule('schedule', '17 12 * * *', moment=datetime(2026,10,12,1,45,tzinfo=TZ))
        self.assertEqual(('early','01:45','2026-10-12'), (p.snapshot_type,p.planned_at,p.report_date))

    def test_on_time_noon_keeps_fixed_cycle(self):
        p = resolve_schedule('schedule', '37 3 * * 1-5', moment=datetime(2026,10,12,11,38,tzinfo=TZ))
        self.assertEqual(('noon','11:37','2026-10-12'), (p.snapshot_type,p.planned_at,p.report_date))

    def test_failed_next_day_expires_ready_without_changing_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pub = publish_snapshot(valid_snapshot(),root,calendar())
            before = pub.archive_path.read_bytes()
            cal = dict(calendar(), date='2026-07-17', latest_completed_trading_day='2026-07-16')
            refresh_manifest(root,cal,'2026-07-17T08:20:00+08:00')
            write_health(root,dict(status='error', snapshot_type='early', quality_grade='F',
                started_at='2026-07-17T08:20:00+08:00',finished_at='2026-07-17T08:21:00+08:00',
                published=False,reason='provider unavailable'))
            manifest=json.loads(pub.manifest_path.read_text())
            self.assertEqual('not_ready',manifest['report_readiness']['noon']['status'])
            self.assertEqual('2026-07-17',manifest['calendar']['date'])
            self.assertEqual(before,pub.archive_path.read_bytes())
            self.assertEqual('error',manifest['health']['last_attempt']['status'])

    def test_broken_previous_target_does_not_block_new_valid_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            pub=publish_snapshot(valid_snapshot(),root,calendar())
            pub.archive_path.write_text('broken')
            candidate=valid_snapshot()
            candidate['snapshot_id']='20260716-1225-noon-full-repair'
            result=publish_snapshot(candidate,root,calendar())
            self.assertTrue(result.published)
            manifest=json.loads(result.manifest_path.read_text())
            verify_pointer(root,manifest['snapshots']['noon'])

    def test_corrupt_target_remains_not_ready_after_health_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            pub=publish_snapshot(valid_snapshot(),root,calendar())
            pub.archive_path.write_text('broken')
            refresh_manifest(root,calendar(),'2026-07-16T12:20:00+08:00')
            write_health(root,dict(status='error',snapshot_type='noon',started_at='2026-07-16T12:20:00+08:00',
                                  finished_at='2026-07-16T12:21:00+08:00',reason='failed',published=False))
            manifest=json.loads(pub.manifest_path.read_text())
            self.assertEqual('not_ready',manifest['report_readiness']['noon']['status'])

    def test_out_of_range_calendar_is_not_valid_holiday(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'output/cache/trade_calendar.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'source':'expired','trade_dates':['2025-12-30','2025-12-31']}))
            info=resolve_calendar(datetime(2026,10,12,8,tzinfo=TZ),Path(tmp),ak_module=None)
            self.assertFalse(info.valid)

    def test_sina_uses_source_date_and_share_units(self):
        fields=['name','56','56.2','54','57','53','54','54','1000','54000']+['0']*20+['2026-10-12','11:30:00','00']
        row=parse_quotes('var hq_str_sh688700="'+','.join(fields)+'";')['sh688700']
        self.assertEqual('2026-10-12T11:30:00+08:00',row['quote_time'])
        self.assertEqual(1000,row['today_volume'])
        self.assertEqual('shares',row['volume_unit'])

    def test_tencent_unverified_volume_is_missing_not_guessed(self):
        fields=['']*40
        for k,v in {1:'name',3:'54',4:'56',5:'56',30:'20261012113000',33:'57',34:'53',37:'100'}.items(): fields[k]=v
        row=parse_tencent('v_sh688700="'+'~'.join(fields)+'";')['sh688700']
        self.assertIsNone(row['today_volume'])
        self.assertEqual(1000000,row['today_amount'])

class FreshnessTests(unittest.TestCase):
    def test_quote_arriving_during_collection_is_fresh(self):
        from pipeline.quality import _quote_is_fresh
        self.assertTrue(_quote_is_fresh({"started_at":"2026-10-12T14:00:00+08:00",
            "quote_time_max":"2026-10-12T14:00:10+08:00", "published_at":"2026-10-12T14:00:15+08:00"},15))
        self.assertFalse(_quote_is_fresh({"started_at":"2026-10-12T14:00:00+08:00",
            "quote_time_max":"2026-10-12T14:00:10+08:00", "published_at":"2026-10-12T14:20:15+08:00"},15))
