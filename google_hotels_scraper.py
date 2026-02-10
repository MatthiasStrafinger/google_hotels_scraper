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
    {
        'name': 'Pension Suzanne',
        'url_template': 'https://booking.pension-suzanne.at/?skd-checkin={checkin}&skd-checkout={checkout}&skd-adults={guests}',
        'is_mine': True
    },
    {
        'name': 'Aviano Boutique Hotel',
        'url_template': 'https://booking.avianoboutiquehotel.com/?skd-checkin={checkin}&skd-checkout={checkout}&skd-adults={guests}',
        'is_mine': False
    },
    {
        'name': 'Hahn Hotel Vienna',
        'url_template': 'https://booking.hahn-hotel-vienna.at/?activeBookingEngine=KBE&propertyCode=S004586&skd-checkin={checkin}&skd-checkout={checkout}&skd-property-code=S004586&skd-adults={guests}',
        'is_mine': False
    },
    {
        'name': 'Hotel Urania',
        'url_template': 'https://s001276.officialbookings.com/?activeBookingEngine=KBE&propertyCode=S001276&skd-checkin={checkin}&skd-checkout={checkout}&skd-property-code=S001276&skd-adults={guests}',
        'is_mine': False
    },
]

def scrape_seekda(hotel, checkin, checkout, guests):
    try:
        url = hotel['url_template'].format(
            checkin=checkin,
            checkout=checkout,
            guests=guests
        )
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        resp = requests.get(url, headers=headers, timeout=12)
        soup = BeautifulSoup(resp.content, 'html.parser')

        prices = []

        # Method 1: Look for EUR price patterns in text
        for el in soup.find_all(string=re.compile(r'EUR\s*\d+|\d+[\.,]\d{2}\s*€|€\s*\d+')):
            text = str(el)
            for pattern in [r'EUR\s*(\d[\d,\.]*)', r'(\d[\d,\.]*)\s*€', r'€\s*(\d[\d,\.]*)']:
                match = re.search(pattern, text)
                if match:
                    price_str = match.group(1).replace(',', '').replace('.', '')
                    try:
                        price = float(price_str)
                        if 20 <= price <= 5000:
                            prices.append(price)
                    except:
                        pass

        # Method 2: Look in data attributes and specific tags
        for tag in soup.find_all(['span', 'div', 'p'], class_=re.compile(r'price|rate|amount|cost', re.I)):
            text = tag.get_text()
            match = re.search(r'(\d[\d,\.]+)', text)
            if match:
                try:
                    price = float(match.group(1).replace(',', '').replace('.', ''))
                    if 20 <= price <= 5000:
                        prices.append(price)
                except:
                    pass

        if prices:
            # Return lowest price (cheapest available room)
            min_price = min(prices)
            nights = (datetime.strptime(checkout, '%Y-%m-%d') - datetime.strptime(checkin, '%Y-%m-%d')).days
            price_per_night = round(min_price / nights, 2) if nights > 1 else min_price
            return {
                'name': hotel['name'],
                'is_mine': hotel['is_mine'],
                'pricePerNight': price_per_night,
                'totalPrice': min_price,
                'status': 'success',
                'source': 'Direct'
            }

        return {
            'name': hotel['name'],
            'is_mine': hotel['is_mine'],
            'pricePerNight': None,
            'totalPrice': None,
            'status': 'error',
            'source': 'Unavailable'
        }

    except Exception as e:
        print(f"Error scraping {hotel['name']}: {e}")
        return {
            'name': hotel['name'],
            'is_mine': hotel['is_mine'],
            'pricePerNight': None,
            'totalPrice': None,
            'status': 'error',
            'source': 'Unavailable'
        }


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'service': 'Vienna Hotel Revenue API',
        'version': '4.0.0',
        'hotels': [h['name'] for h in HOTELS]
    })


@app.route('/api/fetch-prices', methods=['POST', 'OPTIONS'])
def fetch_prices():
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    try:
        data      = request.get_json()
        checkin   = data['check_in']
        checkout  = data['check_out']
        guests    = int(data.get('guests', 2))
        nights    = (datetime.strptime(checkout, '%Y-%m-%d') - datetime.strptime(checkin, '%Y-%m-%d')).days

        # Fetch ALL hotels in parallel!
        results = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(scrape_seekda, hotel, checkin, checkout, guests): hotel
                for hotel in HOTELS
            }
            for future in as_completed(futures):
                results.append(future.result())

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
    <h1>Vienna Hotel Revenue API v4.0</h1>
    <p>🚀 Parallel Seekda scraping · 4 hotels</p>
    <ul>{hotels_list}</ul>
    </body></html>'''


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
