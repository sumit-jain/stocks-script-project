# fetch_200_days.py
import requests, csv, os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv('.env.live')  # or .env.live

TRADIER_TOKEN = os.getenv('TRADIER_TOKEN')
TRADIER_BASE_URL = os.getenv('TRADIER_BASE_URL')
SYMBOL = 'TQQQ'
CSV_FILE = 'tqqq_data.csv'

def fetch_history():
    url = f"{TRADIER_BASE_URL}/markets/history"
    headers = {'Authorization': f'Bearer ' + TRADIER_TOKEN, 'Accept': 'application/json'}
    end = datetime.today().date()
    start = end - timedelta(days=300)
    params = {
        'symbol': SYMBOL,
        'interval': 'daily',
        'start': start.strftime('%Y-%m-%d'),
        'end': end.strftime('%Y-%m-%d')
    }
    response = requests.get(url, headers=headers, params=params)
    data = response.json().get('history', {}).get('day', [])
    return data[-200:] if len(data) >= 200 else data

def save_csv(data):
    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['date', 'open', 'high', 'low', 'close', 'volume'])
        for row in data:
            writer.writerow([row['date'], row['open'], row['high'], row['low'], row['close'], row['volume']])
    print(f"✅ Saved {len(data)} rows to {CSV_FILE}")

if __name__ == '__main__':
    try:
        data = fetch_history()
        if data:
            save_csv(data)
        else:
            print("⚠️ No data returned.")
    except Exception as e:
        print(f"❌ Error: {e}")

