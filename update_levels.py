#!/usr/bin/env python3
"""
update_levels.py — Daily Market Data Updater
=============================================
Récupère les prix de clôture + PDH/PDL/PWH/PWL
via yfinance et injecte les données dans index.html.

Lancé automatiquement chaque matin par GitHub Actions.
Peut aussi être lancé manuellement : python update_levels.py
"""

import yfinance as yf
import json
import re
import os
from datetime import datetime
import pytz


# ================================================================
# CONFIGURATION — modifier les tickers si besoin
# ================================================================
ASSETS = {
    'XAU': {
        'ticker': 'GC=F',        # Gold Futures (proche du spot XAU/USD)
        'label':  'XAU/USD',
        'digits':  2             # décimales pour l'arrondi
    },
    'BTC': {
        'ticker': 'BTC-USD',     # Bitcoin / USD
        'label':  'BTC/USD',
        'digits':  0
    },
    'SP5': {
        'ticker': '^GSPC',       # S&P 500
        'label':  'SP500',
        'digits':  2
    },
    'WTI': {
        'ticker': 'CL=F',        # WTI Crude Oil Futures
        'label':  'WTI',
        'digits':  2
    },
    'DXY': {
        'ticker': 'DX-Y.NYB',    # Dollar Index
        'label':  'DXY',
        'digits':  3
    },
    'NAS': {
        'ticker': '^IXIC',       # NASDAQ Composite
        'label':  'NASDAQ',
        'digits':  2
    },
}

# Fuseau horaire Paris pour l'horodatage
PARIS_TZ = pytz.timezone('Europe/Paris')


# ================================================================
# FETCH DATA
# ================================================================
def fetch_asset(key, config):
    """
    Récupère pour un actif :
    - price  : dernier prix de clôture disponible
    - pdh    : Previous Day High (J-1)
    - pdl    : Previous Day Low  (J-1)
    - pwh    : Previous Week High
    - pwl    : Previous Week Low
    """
    ticker  = config['ticker']
    digits  = config['digits']

    try:
        t = yf.Ticker(ticker)

        # Données journalières — 15 derniers jours pour avoir J-1 fiable
        hist_d = t.history(period='15d', interval='1d')

        # Données hebdomadaires — 10 semaines pour avoir W-1 fiable
        hist_w = t.history(period='70d', interval='1wk')

        if hist_d.empty:
            print(f'  [{key}] ERREUR : aucune donnée journalière.')
            return None

        # Prix = clôture la plus récente
        price = round(float(hist_d['Close'].iloc[-1]), digits)

        # PDH/PDL = jour J-1 (avant-dernier point)
        if len(hist_d) >= 2:
            pdh = round(float(hist_d['High'].iloc[-2]), digits)
            pdl = round(float(hist_d['Low'].iloc[-2]),  digits)
        else:
            # Pas assez de données — fallback sur le seul point disponible
            pdh = round(float(hist_d['High'].iloc[-1]), digits)
            pdl = round(float(hist_d['Low'].iloc[-1]),  digits)

        # PWH/PWL = semaine W-1 (avant-dernière bougie hebdo)
        if len(hist_w) >= 2:
            pwh = round(float(hist_w['High'].iloc[-2]), digits)
            pwl = round(float(hist_w['Low'].iloc[-2]),  digits)
        else:
            pwh = round(float(hist_w['High'].iloc[-1]), digits) if not hist_w.empty else price
            pwl = round(float(hist_w['Low'].iloc[-1]),  digits) if not hist_w.empty else price

        result = {
            'price': price,
            'pdh':   pdh,
            'pdl':   pdl,
            'pwh':   pwh,
            'pwl':   pwl,
        }

        print(f'  [{key}] Prix: {price} | PDH: {pdh} | PDL: {pdl} | PWH: {pwh} | PWL: {pwl}')
        return result

    except Exception as e:
        print(f'  [{key}] ERREUR : {e}')
        return None


# ================================================================
# BUILD MARKET DATA OBJECT
# ================================================================
def build_market_data():
    now_paris = datetime.now(PARIS_TZ)
    market_data = {
        'generated_date': now_paris.strftime('%Y-%m-%d'),
        'generated_time': now_paris.strftime('%H:%M'),
        'assets': {}
    }

    for key, config in ASSETS.items():
        print(f'Fetching {config["label"]} ({config["ticker"]})...')
        data = fetch_asset(key, config)
        if data:
            market_data['assets'][key] = data

    return market_data


# ================================================================
# UPDATE HTML
# ================================================================
def update_html(market_data):
    # Chemin du fichier HTML (même dossier que ce script)
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index.html')

    if not os.path.exists(html_path):
        raise FileNotFoundError(f'index.html introuvable : {html_path}')

    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # Sérialiser les données en JSON lisible
    data_json = json.dumps(market_data, indent=2, ensure_ascii=False)

    # Bloc de remplacement
    date_str = market_data['generated_date']
    time_str = market_data['generated_time']
    replacement = (
        f'<!-- MARKET_DATA:START -->\n'
        f'<script id="auto-market-data">\n'
        f'/* Auto-généré par GitHub Actions — {date_str} {time_str} (Paris) */\n'
        f'const AUTO_MARKET_DATA = {data_json};\n'
        f'</script>\n'
        f'<!-- MARKET_DATA:END -->'
    )

    # Remplacer le bloc entre les marqueurs
    pattern = r'<!-- MARKET_DATA:START -->.*?<!-- MARKET_DATA:END -->'
    new_html, count = re.subn(pattern, replacement, html, flags=re.DOTALL)

    if count == 0:
        raise ValueError(
            'Marqueurs MARKET_DATA:START / MARKET_DATA:END introuvables dans index.html.\n'
            'Vérifie que le fichier HTML contient bien ces commentaires.'
        )

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(new_html)

    print(f'\nindex.html mis à jour avec succès ({count} bloc remplacé).')


# ================================================================
# MAIN
# ================================================================
def main():
    print('=' * 52)
    print('KEY LEVELS GRID — Daily Market Data Update')
    now_paris = datetime.now(PARIS_TZ)
    print(f'Heure Paris : {now_paris.strftime("%Y-%m-%d %H:%M")}')
    print('=' * 52)

    market_data = build_market_data()

    n_assets = len(market_data['assets'])
    print(f'\n{n_assets}/{len(ASSETS)} actifs récupérés.')

    if n_assets == 0:
        print('ERREUR : aucun actif récupéré. index.html non modifié.')
        return

    update_html(market_data)
    print(f'\nTerminé — données du {market_data["generated_date"]} à {market_data["generated_time"]}.')


if __name__ == '__main__':
    main()
