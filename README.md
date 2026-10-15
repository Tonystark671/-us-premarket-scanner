# Pulse15 US Scanner

Mobile-friendly Flask dashboard. Auto-refresh every 30 seconds while open, London/New York clocks, session tabs, prices, volume, EMA20/50 and upper Bollinger band.

## Run

```sh
pip install -r requirements.txt
python app.py
```

Open http://localhost:8000. For hosting, use Python 3.11+ with build command `pip install -r requirements.txt` and start command `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 30`.

This is a Python web service, not a GitHub Pages static website. Hosting is required to obtain a phone-accessible URL. The Procfile is provided for compatible Python hosts.

## Data limitations

- Best-effort public TradingView endpoint: availability and exchange delays are not guaranteed. Refresh time is not quote time.
- Regular-session 15-minute indicators use the provider's developing bar; they are not confirmed closed candles. Bar timestamp is unavailable.
- Premarket/after-hours use dedicated session price/change/volume. Unverified extended-session intraday indicators are blank. Ranking uses session change in these sessions.
- Overnight data is unavailable. Never substitutes regular or after-hours quotes for overnight prices.
- Minimum session change +5%, volume 90,000; scans up to 250 source candidates and displays 40. Not an exhaustive market scan.
- Session clock follows weekday New York hours, not a holiday/early-close exchange calendar. Manual views may show past-session values.
- Daily relative volume is not a 15-minute volume surge measure. Related headlines are not verified catalysts.
- No automatic demo fallback. Feed failures clear results and show an error.

## Checks

```sh
python -m unittest discover -s tests
```
