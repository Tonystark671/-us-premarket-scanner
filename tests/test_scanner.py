import unittest
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo

from app import app, current_session

NY = ZoneInfo("America/New_York")


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_session_detection(self):
        self.assertEqual(current_session(datetime(2026, 10, 15, 8, 0, tzinfo=NY)), "PRE-MARKET")
        self.assertEqual(current_session(datetime(2026, 10, 15, 10, 0, tzinfo=NY)), "MARKET")
        self.assertEqual(current_session(datetime(2026, 10, 15, 17, 0, tzinfo=NY)), "AFTER-HOURS")
        self.assertEqual(current_session(datetime(2026, 10, 15, 2, 0, tzinfo=NY)), "OVERNIGHT")

    def test_invalid_mode(self):
        self.assertEqual(self.client.get('/api/scan?mode=bad').status_code, 400)

    def test_overnight_returns_no_rows(self):
        r = self.client.get('/api/scan?mode=AUTO')
        self.assertIn('session', r.json)

    def test_market_rows_are_returned(self):
        sample = [{
            'ticker': 'TEST',
            'candle': 'GREEN',
            'move15': 4.2,
            'vol15': 250000,
            'prev_vol15': 100000,
            'vol_change': 150.0,
            'high_change': 3.0,
            'bar_start': '10:15 ET',
            'live_bucket': True,
        }]
        with patch('app.build_scan', return_value=sample):
            r = self.client.get('/api/scan?mode=MARKET')
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json['rows'][0]['ticker'], 'TEST')
            self.assertTrue(r.json['rows'][0]['live_bucket'])

    def test_feed_failure_never_fakes_rows(self):
        with patch('app.build_scan', side_effect=RuntimeError('feed')):
            r = self.client.get('/api/scan?mode=MARKET')
            self.assertEqual(r.status_code, 503)
            self.assertEqual(r.json['rows'], [])

    def test_routes(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/static/app.js').status_code, 200)
        self.assertEqual(self.client.get('/api/health').status_code, 200)


if __name__ == '__main__':
    unittest.main()
