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


def parse_seekda_price(html_text, nights):
    """
    Seekda pages show prices like:
      € 1,193.00   <- original total price
      -17 %        <- discount
      € 990.19     <- discounted total price  <-- WE WANT THIS

    Strategy: find all EUR price blocks, then look for discount pattern.
    The discounted price always follows a "- X %" pattern.
    If no discount exists, take the first (lowest) total price.
    """

    # Find all price blocks: "€ 1,193.00" or "EUR 990.19"
    # Seekda always uses format: € 1,234.56 (with comma thousands separator)
    price_pattern = re.compile(r'€\s*([\d]{2,}[,\.][\d,\.]+)')
    discount_pattern = re.compile(r'-\s*\d+\s*%')

    all_prices = []
    for m in price_pattern.finditer(html_text):
        price_str = m.group(1).replace(',', '')
        try:
            price = float(price_str)
            if 30 <= price <= 50000:  # valid total price range
                all_prices.append((m.start(), price))
        except:
            pass

    if not all_prices:
        return None

    # Look for discounted prices: find a discount marker, then take the NEXT price after it
    discounted_prices = []
    for dm in discount_pattern.finditer(html_text):
        # Find the next price that comes AFTER this discount marker
        for pos, price in all_prices:
            if pos > dm.start():
                discounted_prices.append(price)
                break

    if discounted_prices:
        # Take the lowest discounted total price (cheapest room)
        best_total = min(discounted_prices)
    else:
        # No discount found - take the lowest total price
        best_total = min(p for _, p in all_prices)

    price_per_night = round(best_total / nights, 2)
    return price_per_night


def scrape_seekda(hotel, checkin, checkout, guests):
    try:
        url = hotel['url_template'].format(
            checkin=checkin,
            checkout=checkout,
            guests=guests
        )
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        resp = requests.get(url, headers=headers, timeout=12)
        html_text = resp.text

        nights = (
            datetime.strptime(checkout, '%Y-%m-%d') -
            datetime.strptime(checkin, '%Y-%m-%d')
        ).days

        price_per_night = parse_seekda_price(html_text, nights)

        if price_per_night:
            return {
                'name': hotel['name'],
                'is_mine': hotel['is_mine'],
                'pricePerNight': price_per_night,
                'totalPrice': round(price_per_night * nights, 2),
                'status': 'success',
                'source': 'Direct'
            }
        else:
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
        'version': '4.1.0',
        'hotels': [h['name'] for h in HOTELS]
    })


@app.route('/api/fetch-prices', methods=['POST', 'OPTIONS'])
def fetch_prices():
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    try:
        data     = request.get_json()
        checkin  = data['check_in']
        checkout = data['check_out']
        guests   = int(data.get('guests', 2))
        nights   = (
            datetime.strptime(checkout, '%Y-%m-%d') -
            datetime.strptime(checkin,  '%Y-%m-%d')
        ).days

        # Fetch ALL 4 hotels in parallel
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
    <h1>Vienna Hotel Revenue API v4.1</h1>
    <p>✅ Seekda direct scraping · rabattierte Preise · parallel</p>
    <ul>{hotels_list}</ul>
    </body></html>'''


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
