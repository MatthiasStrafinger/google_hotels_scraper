from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)
CORS(app)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

HOTELS = [
    {'name': 'Hotel Pension Suzanne',       'query': 'Hotel Pension Suzanne Vienna',       'is_mine': True},
    {'name': 'Pension Neuer Markt',          'query': 'Pension Neuer Markt Vienna',          'is_mine': False},
    {'name': 'Hotel am Schubertring',        'query': 'Hotel am Schubertring Vienna',        'is_mine': False},
    {'name': 'Pension Opera Suites',         'query': 'Pension Opera Suites Vienna',         'is_mine': False},
    {'name': 'Motel One Wien-Staatsoper',    'query': 'Motel One Wien-Staatsoper Vienna',    'is_mine': False},
    {'name': 'Hotel Post Wien',              'query': 'Hotel Post Wien Vienna',              'is_mine': False},
    {'name': 'Hotel Secession an der Oper',  'query': 'Hotel Secession an der Oper Vienna',  'is_mine': False},
]

def scrape_price(hotel, check_in_str, check_out_str, guests):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        url = (
            f"https://www.google.com/travel/hotels"
            f"?q={requests.utils.quote(hotel['query'])}"
            f"&checkin={check_in_str}"
            f"&checkout={check_out_str}"
            f"&adults={guests}"
            f"&hl=en"
        )
        resp = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(resp.content, 'html.parser')
        prices = []
        for el in soup.find_all(string=re.compile(r'€\s*\d+')):
            match = re.search(r'€\s*(\d[\d,]*)', str(el))
            if match:
                price = float(match.group(1).replace(',', ''))
                if 20 <= price <= 2000:
                    prices.append(price)
        price = min(prices) if prices else None
        return {
            'name':          hotel['name'],
            'is_mine':       hotel['is_mine'],
            'pricePerNight': price,
            'source':        'Google Hotels' if price else 'Unavailable',
            'status':        'success' if price else 'error',
        }
    except Exception as e:
        print(f"Error scraping {hotel['name']}: {e}")
        return {
            'name':          hotel['name'],
            'is_mine':       hotel['is_mine'],
            'pricePerNight': None,
            'source':        'Unavailable',
            'status':        'error',
        }

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'Vienna Hotel Revenue API', 'version': '3.0.0'})

@app.route('/api/fetch-prices', methods=['POST', 'OPTIONS'])
def fetch_prices():
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    try:
        data          = request.get_json()
        check_in      = datetime.strptime(data['check_in'],  '%Y-%m-%d')
        check_out     = datetime.strptime(data['check_out'], '%Y-%m-%d')
        guests        = int(data.get('guests', 2))
        nights        = (check_out - check_in).days
        check_in_str  = check_in.strftime('%Y-%m-%d')
        check_out_str = check_out.strftime('%Y-%m-%d')

        # Fetch all hotels IN PARALLEL (much faster!)
        results = []
        with ThreadPoolExecutor(max_workers=7) as executor:
            futures = {
                executor.submit(scrape_price, hotel, check_in_str, check_out_str, guests): hotel
                for hotel in HOTELS
            }
            for future in as_completed(futures):
                result = future.result()
                if result['pricePerNight']:
                    result['totalPrice'] = round(result['pricePerNight'] * nights, 2)
                else:
                    result['totalPrice'] = None
                results.append(result)

        return jsonify({'success': True, 'data': results, 'nights': nights})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/')
def index():
    hotels_list = ''.join(
        f'<li>{h["name"]}{" ⭐ (YOUR HOTEL)" if h["is_mine"] else ""}</li>'
        for h in HOTELS
    )
    return f'''<html><body style="font-family:Arial;padding:40px">
    <h1>Vienna Hotel Revenue API v3.0</h1>
    <p>🚀 Parallel scraping enabled</p>
    <ul>{hotels_list}</ul>
    </body></html>'''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
