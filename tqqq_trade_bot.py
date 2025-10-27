import requests
import datetime
import yfinance as yf
import pandas as pd
import csv
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
POSITION_SIZE = 100  # percent of capital

# === TELEGRAM ===
def send_telegram(message):
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print("Telegram error:", e)

# === TRADE LOGGING ===
def log_trade(date, trade_type, qty, price, reason):
    with open("trade_log.csv", mode="a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([date, trade_type, qty, f"{price:.2f}", reason])

def load_csv():
    try:
        df = pd.read_csv('tqqq_data.csv')
        df['date'] = pd.to_datetime(df['date'])
        return df.tail(60)
    except Exception as e:
        send_telegram(f"⚠️ Error loading CSV: {e}")
        return None

def get_ema10_from_csv(df):
    df['EMA10'] = df['close'].ewm(span=10, adjust=False).mean()
    return float(df['EMA10'].iloc[-1])

def get_macd_histogram_from_csv(df):
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal
    return float(histogram.iloc[-1])

def get_rsi_from_csv(df, period=14):
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])

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
    except:
        fallback = 5000.0 if SANDBOX_MODE else 0.0
        send_telegram(f"⚠️ Balance unavailable. Using fallback: ${fallback:.2f}")
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
            if pos.get('symbol', '').upper() == SYMBOL:
                return {
                    'quantity': int(pos.get('quantity')),
                    'average_price': float(pos.get('cost_basis')),
                    'market_value': float(pos.get('market_value', 0)),
                    'unrealized_gain': float(pos.get('unrealized_gain', 0))
                }
        return None
    except Exception as e:
        send_telegram(f"⚠️ Error fetching position: {str(e)}")
        return None

def place_order(symbol, qty, side, reason, type='market', duration='day'):
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
    order = response.json()
    price = get_quote(symbol)['last']
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d')
    log_trade(timestamp, side.upper(), qty, price, reason)
    send_telegram(f"{side.upper()} {qty} shares of {symbol} at ${price:.2f}\nReason: {reason}\nOrder ID: {order.get('id', 'N/A')}")
    return order

# === TECHNICAL INDICATORS ===
def get_ema10(symbol):
    df = yf.download(symbol, period='30d', interval='1d')
    df['EMA10'] = df['Close'].ewm(span=10, adjust=False).mean()
    return df['EMA10'].iloc[-1]

def get_macd_histogram(symbol):
    df = yf.download(symbol, period='60d', interval='1d', auto_adjust=False)
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal
    return float(histogram.iloc[-1].item())  # ✅ Ensure it's a float

def get_rsi(symbol, period=14):
    df = yf.download(symbol, period='60d', interval='1d', auto_adjust=False)
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1].item())  # ✅ Ensure it's a float

def should_reenter():
    df = load_csv()
    if df is None or len(df) < 60:
        send_telegram("⚠️ Indicator data unavailable. Skipping trade logic.")
        log_trade(datetime.now().strftime('%Y-%m-%d'), 'SKIP', 0, 0.0, 'Indicator data unavailable')
        return False

    price = df['close'].iloc[-1]
    volume = df['volume'].iloc[-1]
    ema10 = get_ema10_from_csv(df)
    macd_hist = get_macd_histogram_from_csv(df)
    rsi = get_rsi_from_csv(df)

    message = (
        f"📊 Indicator Check:\n"
        f"Price: ${price:.2f}\n"
        f"EMA10: ${ema10:.2f}\n"
        f"MACD Histogram: {macd_hist:.2f}\n"
        f"RSI (14): {rsi:.1f}\n"
        f"Volume: {volume:,}\n"
    )

    if macd_hist > 0 and rsi < 70 and price > ema10:
        send_telegram(message + "✅ Signal confirmed. Good time to BUY.")
        return True
    else:
        send_telegram(message + "🚫 Signal not confirmed. Avoid buying.")
        return False

# === STRATEGY EXECUTION ===
def execute_trade():
    price = get_quote(SYMBOL)['last']
    capital = get_account_balance()
    position = get_tqqq_position()

    if position:
        entry_price = position['average_price']
        qty = position['quantity']
        gain = (price - entry_price) / entry_price

        if gain >= 0.25:
            sell_qty = qty // 2
            place_order(SYMBOL, sell_qty, 'sell', '+25% profit')
        elif price < get_ema10(SYMBOL) and get_macd_histogram(SYMBOL) < 0:
            place_order(SYMBOL, qty, 'sell', 'MACD exit')
        else:
            send_telegram(f"Holding {qty} shares. No action.")
    else:
        if should_reenter():
            qty = int((capital * POSITION_SIZE / 100) // price)
            if qty > 0:
                place_order(SYMBOL, qty, 'buy', 'Trend resumed')
            else:
                send_telegram("🚫 Not enough capital to re-enter.")

# === RUN ===
if __name__ == '__main__':
    execute_trade()

