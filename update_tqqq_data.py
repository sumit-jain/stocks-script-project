import requests
import csv
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('.env.live')  # or .env.live

TRADIER_TOKEN = os.getenv('TRADIER_TOKEN')
TRADIER_BASE_URL = os.getenv('TRADIER_BASE_URL')
SYMBOL = 'TQQQ'
CSV_FILE = 'tqqq_data.csv'

def get_latest_tradier_data():
    url = f"{TRADIER_BASE_URL}/markets/history"
    headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
    params = {'symbol': SYMBOL, 'interval': 'daily'}
    response = requests.get(url, headers=headers, params=params)
    data = response.json().get('history', {}).get('day', [])
    return data[-1] if data else None

def get_last_csv_date():
    if not os.path.exists(CSV_FILE):
        return None
    with open(CSV_FILE, 'r') as f:
        last_line = f.readlines()[-1]
        return last_line.split(',')[0]

def append_to_csv(row):
    with open(CSV_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([row['date'], row['open'], row['high'], row['low'], row['close'], row['volume']])

def update_csv():
    latest = get_latest_tradier_data()
    if not latest:
        print("No data received.")
        return
    last_date = get_last_csv_date()
    if latest['date'] != last_date:
        append_to_csv(latest)
        print(f"✅ Appended {latest['date']} to {CSV_FILE}")
    else:
        print("⏸️ No new data to append.")

if __name__ == '__main__':
    update_csv()

