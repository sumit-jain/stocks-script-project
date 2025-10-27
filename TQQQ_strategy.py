import requests
import datetime
import yfinance as yf
import pandas as pd
from config_loader import load_config

# === LOAD CONFIG ===
config = load_config()
SANDBOX_MODE = config['SANDBOX_MODE']
TRADIER_TOKEN = config['TRADIER_TOKEN']
TRADIER_ACCOUNT_ID = config['TRADIER_ACCOUNT_ID']
TRADIER_BASE_URL = config['TRADIER_BASE_URL']
TELEGRAM_BOT_TOKEN = config['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = config['TELEGRAM_CHAT_ID']

SYMBOL = 'TQQQ'
BUY_THRESHOLD = 0.25
POSITION_SIZE = 100

# === TELEGRAM ===
def send_telegram(message):
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print("Telegram error:", e)

# === TRADIER API ===
def get_quote(symbol):
    url = f'{TRADIER_BASE_URL}/markets/quotes'
    headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
    params = {'symbols': symbol}
    response = requests.get(url, headers=headers, params=params)
    return response.json()['quotes']['quote']

def get_account_balance():
    url = f'{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/balances'
    headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
    response = requests.get(url, headers=headers)
    try:
        data = response.json()
        return float(data['balances']['cash']['available'])
    except (KeyError, TypeError, ValueError):
        fallback = 10000.0 if SANDBOX_MODE else 0.0
        send_telegram(f"⚠️ Warning: 'cash' balance not found. Using fallback: ${fallback:.2f}")
        return fallback

def get_tqqq_position():
    url = f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/positions"
    headers = {
        'Authorization': f'Bearer {TRADIER_TOKEN}',
        'Accept': 'application/json'
    }
    try:
        response = requests.get(url, headers=headers)
        result = response.json()
        positions_data = result.get('positions')
        if not positions_data or isinstance(positions_data, str):
            return None
        positions = positions_data.get('position')
        if isinstance(positions, dict):
            positions = [positions]
        for pos in positions:
            if pos.get('symbol', '').upper() == 'TQQQ':
                return {
                    'quantity': pos.get('quantity'),
                    'average_price': pos.get('cost_basis'),
                    'market_value': pos.get('market_value', 0),
                    'unrealized_gain': pos.get('unrealized_gain', 0)
                }
        return None
    except Exception as e:
        send_telegram(f"⚠️ Error fetching TQQQ position: {str(e)}")
        return None

def place_order(symbol, qty, side, type='market', duration='day'):
    url = f'{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders'
    headers = {
        'Authorization': f'Bearer {TRADIER_TOKEN}',
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = {
        'class': 'equity',
        'symbol': symbol,
        'side': side,
        'quantity': qty,
        'type': type,
        'duration': duration
    }
    response = requests.post(url, headers=headers, data=data)
    return response.json()

# === TECHNICAL INDICATORS ===
def get_ema10(symbol):
    df = yf.download(symbol, period='30d', interval='1d')
    df['EMA10'] = df['Close'].ewm(span=10, adjust=False).mean()
    return df['EMA10'].iloc[-1]

def get_macd_histogram(symbol):
    df = yf.download(symbol, period='60d', interval='1d')
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal
    return histogram.iloc[-1]

# === STRATEGY EXECUTION ===
def execute_trade():
    print(f"🔧 Running in {'SANDBOX' if SANDBOX_MODE else 'LIVE'} mode")
    quote = get_quote(SYMBOL)
    price = float(quote['last'])
    capital = get_account_balance()
    position = get_tqqq_position()

    if position:
        entry_price = position['average_price']
        qty = position['quantity']
        gain = (price - entry_price) / entry_price

        if gain >= BUY_THRESHOLD:
            sell_qty = qty // 2
            order = place_order(SYMBOL, sell_qty, 'sell')
            send_telegram(f"📤 SELL {sell_qty} shares of {SYMBOL} at ${price:.2f} (+25% gain)\nOrder ID: {order.get('id', 'N/A')}")
        elif price < get_ema10(SYMBOL) and get_macd_histogram(SYMBOL) < 0:
            order = place_order(SYMBOL, qty, 'sell')
            send_telegram(f"🔻 Exit: SELL {qty} shares of {SYMBOL} at ${price:.2f} (MACD/EMA10 exit)\nOrder ID: {order.get('id', 'N/A')}")
        else:
            send_telegram(f"📊 Holding {qty} shares of {SYMBOL}. No action taken.")
    else:
        qty = int((capital * POSITION_SIZE / 100) // price)
        if qty == 0:
            send_telegram(f"🚫 Not enough capital to buy {SYMBOL}. Available: ${capital:.2f}")
            return
        order = place_order(SYMBOL, qty, 'buy')
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        send_telegram(f"🟢 BUY {qty} shares of {SYMBOL} at ${price:.2f}\nTime: {timestamp}\nOrder ID: {order.get('id', 'N/A')}")
        target_price = price * (1 + BUY_THRESHOLD)
        send_telegram(f"📈 Target SELL price set at ${target_price:.2f} (+25%)")

# === RUN ===
if __name__ == '__main__':
    execute_trade()

