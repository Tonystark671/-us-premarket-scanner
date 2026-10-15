import unittest
from unittest.mock import patch
from app import app, normalize

class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.client=app.test_client()
        self.row={'name':'TEST','open|15':10,'close|15':11,'close':11,'change':10,'volume':100000,'premarket_close':12,'premarket_change':20,'premarket_volume':100000,'EMA20|15':10,'EMA50|15':9,'BB.upper|15':10.5}
    def test_overnight_never_substitutes(self):
        self.assertEqual(normalize([self.row],'OVERNIGHT'),[])
        with patch('app.tv_scan') as feed:
            self.assertEqual(self.client.get('/api/scan?mode=OVERNIGHT').json['rows'],[])
            feed.assert_not_called()
    def test_extended_price_and_missing_indicators(self):
        row=normalize([self.row],'PRE-MARKET')[0]
        self.assertEqual(row['price'],12)
        self.assertIsNone(row['move15'])
        self.assertEqual(row['signals'],[])
        self.row['premarket_close']=None
        self.assertEqual(normalize([self.row],'PRE-MARKET'),[])
    def test_failure_no_fake_data(self):
        with patch('app.tv_scan',side_effect=RuntimeError):
            r=self.client.get('/api/scan?mode=MARKET')
            self.assertEqual(r.status_code,503)
            self.assertEqual(r.json['rows'],[])
            self.assertFalse(r.json['demo'])
    def test_regular_indicators(self):
        row=normalize([self.row],'MARKET')[0]
        self.assertAlmostEqual(row['move15'],10)
        self.assertIn('EMA20 > EMA50',row['signals'])
        self.assertIsNone(row['signal_time'])
    def test_routes(self):
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertEqual(self.client.get('/static/app.js').status_code,200)
        self.assertEqual(self.client.get('/api/scan?mode=bad').status_code,400)

if __name__=='__main__': unittest.main()
