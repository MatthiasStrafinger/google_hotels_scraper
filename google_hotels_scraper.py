"""
Vienna Hotel Revenue Management - Google Hotels Price Scraper
This script fetches competitor hotel prices from Google Hotels
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import json
import re

app = Flask(__name__)
CORS(app)  # Enable CORS for web app access

# Competitor hotels in Vienna
COMPETITORS = {
    'pension_neuer_markt': {
        'name': 'Pension Neuer Markt',
        'google_hotel_id': 'ChIJNzL6U1PdaUcRqLm_4BBFsQ4',  # Example ID
        'search_query': 'Pension Neuer Markt Vienna'
    },
    'hotel_schubertring': {
        'name': 'Hotel am Schubertring',
        'google_hotel_id': 'ChIJexample2',
        'search_query': 'Hotel am Schubertring Vienna'
    },
    'pension_opera': {
        'name': 'Pension Opera Suites',
        'google_hotel_id': 'ChIJexample3',
        'search_query': 'Pension Opera Suites Vienna'
    },
    'motel_one': {
        'name': 'Motel One Wien-Staatsoper',
        'google_hotel_id': 'ChIJexample4',
        'search_query': 'Motel One Wien-Staatsoper'
    },
    'hotel_post': {
        'name': 'Hotel Post Wien',
        'google_hotel_id': 'ChIJexample5',
        'search_query': 'Hotel Post Wien Vienna'
    },
    'hotel_secession': {
        'name': 'Hotel Secession an der Oper',
        'google_hotel_id': 'ChIJexample6',
        'search_query': 'Hotel Secession an der Oper Vienna'
    }
}

def construct_google_hotels_url(hotel_name, check_in, check_out, guests):
    """
    Construct Google Hotels search URL
    Format: https://www.google.com/travel/hotels/LOCATION/entity/HOTEL_ID?q=QUERY&...
    """
    # Format dates as YYYY-MM-DD
    checkin_str = check_in.strftime('%Y-%m-%d')
    checkout_str = check_out.strftime('%Y-%m-%d')
    
    # Build the Google Hotels URL
    base_url = "https://www.google.com/travel/hotels"
    params = {
        'q': hotel_name,
        'g2lb': '2502548,2503771,2503781,4258168,4270442,4284970,4291517,4597339,4757164,4814050,4874190,4893075,4899571,4899573,4924070,4965990,4985711,4986153,72277293,72302247,72317059,72379271,72406588,72414906,72421566,72430850,72471280,72472051,72481459,72485658,72602734,72614662,72616120,72619172,72628719,72638273,72647020,72648289,72658035,72671093,72686036,72729615,72748767,72754431,72760082,72794649',
        'hl': 'en-US',
        'gl': 'us',
        'cs': '1',
        'ssta': '1',
        'ts': 'CAESCgoCCAMKAggDEAAaIQoDMjAwKgQSAggDOgZldXJvcDoMKgoSCAwQDhgBIAA',
        'checkin': checkin_str,
        'checkout': checkout_str,
        'adults': str(guests)
    }
    
    query_string = '&'.join([f'{k}={v}' for k, v in params.items()])
    return f"{base_url}?{query_string}"

def scrape_google_hotel_price(hotel_info, check_in, check_out, guests):
    """
    Scrape price from Google Hotels for a specific hotel
    """
    try:
        url = construct_google_hotels_url(hotel_info['search_query'], check_in, check_out, guests)
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        # Make request to Google Hotels
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find price elements - Google Hotels typically uses specific classes
        # Note: These selectors may need adjustment based on Google's current HTML structure
        price_elements = soup.find_all(['span', 'div'], class_=re.compile(r'price|rate|cost', re.I))
        
        # Look for prices in various formats
        prices = []
        for element in price_elements:
            text = element.get_text(strip=True)
            # Match prices like €120, EUR 120, 120€, etc.
            price_match = re.search(r'[€EUR\$]?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)\s*[€EUR\$]?', text)
            if price_match:
                price_str = price_match.group(1).replace(',', '')
                try:
                    price = float(price_str)
                    if 20 <= price <= 1000:  # Reasonable hotel price range
                        prices.append(price)
                except ValueError:
                    continue
        
        if prices:
            # Return the minimum price (usually the best available rate)
            min_price = min(prices)
            return {
                'success': True,
                'price': min_price,
                'currency': 'EUR',
                'source': 'Google Hotels'
            }
        else:
            return {
                'success': False,
                'error': 'No price found',
                'fallback_price': None
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'fallback_price': None
        }

@app.route('/api/fetch-prices', methods=['POST'])
def fetch_prices():
    """
    API endpoint to fetch all competitor prices
    Expected JSON: {
        "check_in": "2024-03-15",
        "check_out": "2024-03-17",
        "guests": 2
    }
    """
    try:
        data = request.get_json()
        
        # Parse dates
        check_in = datetime.strptime(data['check_in'], '%Y-%m-%d')
        check_out = datetime.strptime(data['check_out'], '%Y-%m-%d')
        guests = int(data.get('guests', 2))
        
        results = []
        
        # Fetch prices for each competitor
        for hotel_key, hotel_info in COMPETITORS.items():
            print(f"Fetching price for {hotel_info['name']}...")
            
            price_data = scrape_google_hotel_price(hotel_info, check_in, check_out, guests)
            
            nights = (check_out - check_in).days
            
            if price_data['success']:
                results.append({
                    'name': hotel_info['name'],
                    'pricePerNight': price_data['price'],
                    'totalPrice': price_data['price'] * nights,
                    'source': price_data['source'],
                    'status': 'success'
                })
            else:
                # Use fallback/estimated price if scraping fails
                results.append({
                    'name': hotel_info['name'],
                    'pricePerNight': None,
                    'totalPrice': None,
                    'source': 'Unavailable',
                    'status': 'error',
                    'error': price_data.get('error')
                })
            
            # Add delay to avoid rate limiting
            time.sleep(2)
        
        return jsonify({
            'success': True,
            'data': results,
            'nights': nights,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'Vienna Hotel Revenue Management API',
        'version': '1.0.0'
    })

@app.route('/')
def index():
    """API documentation"""
    return '''
    <html>
    <head><title>Vienna Hotel Revenue API</title></head>
    <body style="font-family: Arial; padding: 40px; max-width: 800px; margin: 0 auto;">
        <h1>Vienna Hotel Revenue Management API</h1>
        <h2>Endpoints</h2>
        
        <h3>POST /api/fetch-prices</h3>
        <p>Fetch competitor prices from Google Hotels</p>
        <pre style="background: #f4f4f4; padding: 15px; border-radius: 5px;">
{
    "check_in": "2024-03-15",
    "check_out": "2024-03-17",
    "guests": 2
}
        </pre>
        
        <h3>GET /api/health</h3>
        <p>Health check endpoint</p>
        
        <h2>Competitor Hotels</h2>
        <ul>
            <li>Pension Neuer Markt</li>
            <li>Hotel am Schubertring</li>
            <li>Pension Opera Suites</li>
            <li>Motel One Wien-Staatsoper</li>
            <li>Hotel Post Wien</li>
            <li>Hotel Secession an der Oper</li>
        </ul>
    </body>
    </html>
    '''

if __name__ == '__main__':
    print("Starting Vienna Hotel Revenue Management API...")
    print("API will be available at: http://localhost:5000")
    print("\nCompetitor hotels configured:")
    for hotel in COMPETITORS.values():
        print(f"  - {hotel['name']}")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
