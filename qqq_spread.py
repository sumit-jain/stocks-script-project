import os
import yfinance as yf
import requests
from math import log, sqrt, exp
from scipy.stats import norm
from datetime import datetime
from dotenv import load_dotenv

env_mode = os.getenv("ENV_MODE", "sandbox")  # default to sandbox
env_path = f"/root/qqq-trading/.env.{env_mode}"
load_dotenv(dotenv_path=env_path)


# === Environment Variables ===
SANDBOX = os.getenv("SANDBOX", "true").lower() == "true"
PLACE_TRADE = os.getenv("PLACE_TRADE", "true").lower() == "true"
API_TOKEN = os.getenv("TRADIER_TOKEN")
ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === Tradier API Setup ===
BASE_URL = "https://sandbox.tradier.com" if SANDBOX else "https://api.tradier.com"
ORDER_URL = f"{BASE_URL}/v1/accounts/{ACCOUNT_ID}/orders"
CHAIN_URL = f"{BASE_URL}/v1/markets/options/chains"
EXPIRATION_URL = f"{BASE_URL}/v1/markets/options/expirations"
CLOCK_URL = f"{BASE_URL}/v1/markets/clock"

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded"
}

# === Telegram Notification ===
def notify_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not set. Skipping notification.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=payload)
        print("📨 Telegram notification sent.")
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")

# === Black-Scholes Pricing ===
def black_scholes_put_price(S, K, T, r, sigma):
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    return round(K * exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1), 2)

# === Market Status Check ===
def is_market_open():
    response = requests.get(CLOCK_URL, headers=HEADERS)
    try:
        data = response.json()
        return data["clock"]["state"] == "open"
    except Exception:
        print("⚠️ Failed to decode market clock response.")
        return False

# === Price Fetching ===
def get_qqq_prices():
    qqq = yf.Ticker("QQQ")
    hist = qqq.history(period="2d", interval="1d")
    last_close = hist['Close'].iloc[-2]
    today_open = hist['Open'].iloc[-1]
    return round(last_close, 2), round(today_open, 2)

# === Spread Pricing ===
def get_put_spread_prices(open_price, spread_width=5, T=0.01, r=0.02, sigma=0.25):
    sell_strike = round(open_price - 10, 2)
    buy_strike = round(sell_strike - spread_width, 2)
    sell_price = black_scholes_put_price(open_price, sell_strike, T, r, sigma)
    buy_price = black_scholes_put_price(open_price, buy_strike, T, r, sigma)
    net_credit = round(sell_price - buy_price, 2)
    return sell_strike, sell_price, buy_strike, buy_price, net_credit

# === Option Symbol Lookup with Expiration Fallback ===
def fetch_option_symbol(strike):
    today = datetime.today().strftime("%Y-%m-%d")
    params = {
        "symbol": "QQQ",
        "expiration": today,
        "greeks": "false"
    }
    response = requests.get(CHAIN_URL, headers=HEADERS, params=params)
    try:
        data = response.json()
    except Exception:
        print("⚠️ Failed to decode option chain response.")
        return None

    if "options" not in data or not data["options"].get("option"):
        print("⚠️ No options found for today's expiration. Falling back to next available.")
        exp_response = requests.get(EXPIRATION_URL, headers=HEADERS, params={"symbol": "QQQ"})
        exp_data = exp_response.json()
        next_exp = exp_data["expirations"]["date"][0]
        params["expiration"] = next_exp
        response = requests.get(CHAIN_URL, headers=HEADERS, params=params)
        data = response.json()

    puts = [o for o in data['options']['option'] if o['option_type'] == 'put']
    match = min(puts, key=lambda o: abs(o['strike'] - strike))
    return match['symbol']

# === Order Placement ===
def place_bull_put_spread(sell_symbol, buy_symbol, quantity=1):
    payload = {
        "type": "market",
        "duration": "day",
        "class": "multileg",
        "symbol": "QQQ",
        "side[0]": "sell_to_open",
        "option_symbol[0]": sell_symbol,
        "quantity[0]": str(quantity),
        "side[1]": "buy_to_open",
        "option_symbol[1]": buy_symbol,
        "quantity[1]": str(quantity)
    }
    response = requests.post(ORDER_URL, headers=HEADERS, data=payload)
    print("🔍 Raw response:", response.text)
    try:
        return response.json()
    except Exception:
        return {"error": "Invalid JSON response"}

# === Main Execution ===
def main():
    print(f"🔧 Running in {'SANDBOX' if SANDBOX else 'LIVE'} mode")
    summary = ""

    if not SANDBOX and not is_market_open():
        summary = "🚫 Market is closed. Skipping strategy execution."
        print(summary)
        notify_telegram(summary)
        return

    last_close, today_open = get_qqq_prices()
    print(f"Last Close: {last_close}, Today's Open: {today_open}")
    summary += f"📈 QQQ Bull Put Spread Summary:\nLast Close: {last_close}\nToday's Open: {today_open}\n"

    if today_open > last_close:
        print("✅ Entry condition met.")
        sell_strike, sell_price, buy_strike, buy_price, net_credit = get_put_spread_prices(today_open)
        print(f"Sell {sell_strike} Put @ ${sell_price}, Buy {buy_strike} Put @ ${buy_price}, Net Credit: ${net_credit}")
        summary += f"Entry met ✅\nSell {sell_strike} Put @ ${sell_price}, Buy {buy_strike} Put @ ${buy_price}\nNet Credit: ${net_credit}\n"

        if PLACE_TRADE:
            sell_symbol = fetch_option_symbol(sell_strike)
            buy_symbol = fetch_option_symbol(buy_strike)
            if not sell_symbol or not buy_symbol:
                print("❌ Could not fetch valid option symbols. Trade aborted.")
                summary += "❌ Trade aborted: missing option symbols."
                notify_telegram(summary)
                return
            print("📌 Sell leg symbol:", sell_symbol)
            print("📌 Buy leg symbol:", buy_symbol)
            result = place_bull_put_spread(sell_symbol, buy_symbol)
            print("🛠️ Order Response:", result)
            summary += f"Trade placed 🛠️\nSell: {sell_symbol}\nBuy: {buy_symbol}\nResult: {result}"
        else:
            print("🧪 Simulation only: trade not placed.")
            summary += "🧪 Simulation only: trade not placed."
    else:
        print("❌ No trade: QQQ did not open higher than previous close.")
        summary += "❌ No trade: QQQ did not open higher than previous close."

    notify_telegram(summary)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_msg = f"❌ Script failed: {str(e)}"
        print(error_msg)
        notify_telegram(error_msg)

