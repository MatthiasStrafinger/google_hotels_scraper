from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time
import re
import os

app = Flask(__name__)

# CORS - allow all origins
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
    {'name': 'Hotel Post Wien',             'query': 'Hotel Post Wien Vienna',              'is_mine': False},
    {'name': 'Hotel Secession an der Oper', 'query': 'Hotel Secession an der Oper Vienna', 'is_mine': False},
]

def scrape_price(hotel_query, check_in, check_out, guests):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        checkin_str  = check_in.strftime('%Y-%m-%d')
        checkout_str = check_out.strftime('%Y-%m-%d')
        url = (
            f"https://www.google.com/travel/hotels"
            f"?q={requests.utils.quote(hotel_query)}"
            f"&checkin={checkin_str}"
            f"&checkout={checkout_str}"
            f"&adults={guests}"
            f"&hl=en"
        )
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.content, 'html.parser')
        prices = []
        for el in soup.find_all(string=re.compile(r'€\s*\d+')):
            match = re.search(r'€\s*(\d[\d,]*)', str(el))
            if match:
                price = float(match.group(1).replace(',', ''))
                if 20 <= price <= 2000:
                    prices.append(price)
        if prices:
            return min(prices)
        return None
    except Exception as e:
        print(f"Error scraping {hotel_query}: {e}")
        return None

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'Vienna Hotel Revenue API', 'version': '2.0.0'})

@app.route('/api/fetch-prices', methods=['POST', 'OPTIONS'])
def fetch_prices():
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    try:
        data      = request.get_json()
        check_in  = datetime.strptime(data['check_in'],  '%Y-%m-%d')
        check_out = datetime.strptime(data['check_out'], '%Y-%m-%d')
        guests    = int(data.get('guests', 2))
        nights    = (check_out - check_in).days
        results = []
        for hotel in HOTELS:
            print(f"Fetching: {hotel['name']}...")
            price = scrape_price(hotel['query'], check_in, check_out, guests)
            results.append({
                'name':          hotel['name'],
                'is_mine':       hotel['is_mine'],
                'pricePerNight': price,
                'totalPrice':    round(price * nights, 2) if price else None,
                'source':        'Google Hotels' if price else 'Unavailable',
                'status':        'success' if price else 'error',
            })
            time.sleep(1)
        return jsonify({'success': True, 'data': results, 'nights': nights})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/')
def index():
    hotels_list = ''.join(f'<li>{h["name"]}{" (YOUR HOTEL)" if h["is_mine"] else ""}</li>' for h in HOTELS)
    return f'<html><body style="font-family:Arial;padding:40px"><h1>Vienna Hotel Revenue API v2.0</h1><ul>{hotels_list}</ul></body></html>'

if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
