#!/usr/bin/env python3
"""
update_levels.py — Daily Market Data Updater v2
================================================
Récupère et calcule les niveaux mécaniques ICT/SMC :
  - Previous Day/Week/Month High/Low (PDH/PDL/PWH/PWL/PMH/PML)
  - Daily/Weekly/Monthly Open (DO/WO/MO)
  - Session High/Low Asia / London / New York
  - Prix actuel (dernière clôture disponible)
"""

import yfinance as yf
import json, re, os
from datetime import datetime, timedelta
import pytz

# ================================================================
# CONFIGURATION ACTIFS
# ================================================================
ASSETS = {
    'XAU': { 'ticker': 'GC=F',      'label': 'XAU/USD',  'digits': 2  },
    'BTC': { 'ticker': 'BTC-USD',   'label': 'BTC/USD',  'digits': 0  },
    'SP5': { 'ticker': '^GSPC',     'label': 'SP500',    'digits': 2  },
    'NAS': { 'ticker': '^IXIC',     'label': 'NASDAQ',   'digits': 2  },
    'WTI': { 'ticker': 'CL=F',      'label': 'WTI',      'digits': 2  },
    'DXY': { 'ticker': 'DX-Y.NYB',  'label': 'DXY',      'digits': 3  },
}

PARIS_TZ = pytz.timezone('Europe/Paris')
UTC_TZ   = pytz.utc

# Sessions en heures UTC (start, end)
SESSIONS = {
    'asia':   (22, 8),   # 22h UTC J-1 -> 08h UTC (chevauche minuit)
    'london': (7,  16),
    'ny':     (13, 21),
}


# ================================================================
# UTILITAIRES
# ================================================================
def r(v, d): return round(float(v), d)

def in_session(dt_utc, sess):
    h = dt_utc.hour
    start, end = SESSIONS[sess]
    if start < end:
        return start <= h < end
    return h >= start or h < end  # chevauche minuit

def get_week_start(today):
    return today - timedelta(days=today.weekday())

def get_month_start(today):
    return today.replace(day=1)

def to_date(idx):
    d = idx
    if hasattr(d, 'to_pydatetime'):
        d = d.to_pydatetime()
    if hasattr(d, 'date'):
        d = d.date()
    return d


# ================================================================
# FETCH JOURNALIER — previous levels + opens
# ================================================================
def fetch_daily(ticker, digits):
    t = yf.Ticker(ticker)
    hist_d = t.history(period='3mo',  interval='1d')
    hist_w = t.history(period='6mo',  interval='1wk')
    hist_m = t.history(period='12mo', interval='1mo')

    if hist_d.empty:
        return None

    now_utc     = datetime.now(UTC_TZ)
    week_start  = get_week_start(now_utc.date())
    month_start = get_month_start(now_utc.date())

    # Prix actuel
    price = r(hist_d['Close'].iloc[-1], digits)

    # PDH / PDL (avant-dernier jour)
    i = -2 if len(hist_d) >= 2 else -1
    pdh = r(hist_d['High'].iloc[i], digits)
    pdl = r(hist_d['Low'].iloc[i],  digits)

    # PWH / PWL (avant-dernière semaine)
    pwh = pwl = None
    if not hist_w.empty and len(hist_w) >= 2:
        pwh = r(hist_w['High'].iloc[-2], digits)
        pwl = r(hist_w['Low'].iloc[-2],  digits)

    # PMH / PML (avant-dernier mois)
    pmh = pml = None
    if not hist_m.empty and len(hist_m) >= 2:
        pmh = r(hist_m['High'].iloc[-2], digits)
        pml = r(hist_m['Low'].iloc[-2],  digits)

    # DO — open du dernier jour disponible
    do = r(hist_d['Open'].iloc[-1], digits)

    # WO — open du premier trading day de la semaine courante
    wo = None
    for i in range(len(hist_d) - 1, -1, -1):
        d = to_date(hist_d.index[i])
        if d >= week_start:
            wo = r(hist_d['Open'].iloc[i], digits)
        else:
            break

    # MO — open du premier trading day du mois courant
    mo = None
    for i in range(len(hist_d) - 1, -1, -1):
        d = to_date(hist_d.index[i])
        if d >= month_start:
            mo = r(hist_d['Open'].iloc[i], digits)
        else:
            break

    return {
        'price': price,
        'pdh': pdh, 'pdl': pdl,
        'pwh': pwh, 'pwl': pwl,
        'pmh': pmh, 'pml': pml,
        'do':  do,  'wo':  wo,  'mo': mo,
    }


# ================================================================
# FETCH SESSIONS — données horaires
# ================================================================
def fetch_sessions(ticker, digits):
    empty = {k: None for k in ['asia_h','asia_l','london_h','london_l','ny_h','ny_l']}
    try:
        t = yf.Ticker(ticker)
        hist_1h = t.history(period='2d', interval='1h')
        if hist_1h.empty:
            return empty

        buckets = {s: {'h': [], 'l': []} for s in SESSIONS}

        for idx, row in hist_1h.iterrows():
            if hasattr(idx, 'to_pydatetime'):
                dt = idx.to_pydatetime()
            else:
                dt = idx
            if dt.tzinfo is None:
                dt = UTC_TZ.localize(dt)
            else:
                dt = dt.astimezone(UTC_TZ)

            for sess in SESSIONS:
                if in_session(dt, sess):
                    buckets[sess]['h'].append(float(row['High']))
                    buckets[sess]['l'].append(float(row['Low']))

        result = {}
        for sess, data in buckets.items():
            result[f'{sess}_h'] = r(max(data['h']), digits) if data['h'] else None
            result[f'{sess}_l'] = r(min(data['l']), digits) if data['l'] else None

        return result
    except Exception as e:
        print(f'    Sessions error: {e}')
        return empty


# ================================================================
# FETCH COMPLET PAR ACTIF
# ================================================================
def fetch_asset(key, config):
    ticker = config['ticker']
    digits = config['digits']
    try:
        daily    = fetch_daily(ticker, digits)
        if not daily:
            print(f'  [{key}] ERREUR : pas de données journalières.')
            return None
        sessions = fetch_sessions(ticker, digits)
        data = {**daily, **sessions}
        print(f'  [{key}] OK — price={data["price"]} | '
              f'PDH={data["pdh"]}/{data["pdl"]} | '
              f'PWH={data["pwh"]}/{data["pwl"]} | '
              f'PMH={data["pmh"]}/{data["pml"]} | '
              f'DO={data["do"]} WO={data["wo"]} MO={data["mo"]}')
        return data
    except Exception as e:
        print(f'  [{key}] ERREUR : {e}')
        return None


# ================================================================
# BUILD + INJECT
# ================================================================
def build_market_data():
    now_paris = datetime.now(PARIS_TZ)
    md = {
        'generated_date': now_paris.strftime('%Y-%m-%d'),
        'generated_time': now_paris.strftime('%H:%M'),
        'assets': {}
    }
    for key, config in ASSETS.items():
        print(f'\nFetching {config["label"]}...')
        data = fetch_asset(key, config)
        if data:
            md['assets'][key] = data
    return md


def update_html(md):
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index.html')
    if not os.path.exists(html_path):
        raise FileNotFoundError(f'index.html introuvable : {html_path}')

    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    data_json = json.dumps(md, indent=2, ensure_ascii=False)
    repl = (
        f'<!-- MARKET_DATA:START -->\n'
        f'<script id="auto-market-data">\n'
        f'/* Auto-généré — {md["generated_date"]} {md["generated_time"]} (Paris) */\n'
        f'const AUTO_MARKET_DATA = {data_json};\n'
        f'applyMarketData();\n'
        f'</script>\n'
        f'<!-- MARKET_DATA:END -->'
    )
    new_html, n = re.subn(
        r'<!-- MARKET_DATA:START -->.*?<!-- MARKET_DATA:END -->', repl, html, flags=re.DOTALL
    )
    if n == 0:
        raise ValueError('Marqueurs MARKET_DATA introuvables dans index.html.')

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(new_html)
    print(f'\nindex.html mis à jour.')


def main():
    print('=' * 56)
    print('KEY LEVELS GRID — Daily Market Data Update v2')
    print(f'Paris : {datetime.now(PARIS_TZ).strftime("%Y-%m-%d %H:%M")}')
    print('=' * 56)

    md = build_market_data()
    n  = len(md['assets'])
    print(f'\n{n}/{len(ASSETS)} actifs récupérés.')
    if n == 0:
        print('Aucun actif — index.html non modifié.')
        return
    update_html(md)
    print(f'Terminé — {md["generated_date"]} {md["generated_time"]}.')

if __name__ == '__main__':
    main()
