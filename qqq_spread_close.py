import os
import requests

from datetime import datetime
from dotenv import load_dotenv

# === Load Environment File Based on ENV_MODE ===
env_mode = os.getenv("ENV_MODE", "sandbox")  # default to sandbox
env_path = f"/root/qqq-trading/.env.{env_mode}"
load_dotenv(dotenv_path=env_path)

# === Environment Variables ===
SANDBOX = os.getenv("SANDBOX", "true").lower() == "true"
API_TOKEN = os.getenv("TRADIER_TOKEN")
ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === API Endpoints ===
BASE_URL = "https://sandbox.tradier.com" if SANDBOX else "https://api.tradier.com"
ORDER_URL = f"{BASE_URL}/v1/accounts/{ACCOUNT_ID}/orders"
POSITIONS_URL = f"{BASE_URL}/v1/accounts/{ACCOUNT_ID}/positions"
CLOCK_URL = f"{BASE_URL}/v1/markets/clock"
QUOTE_URL = f"{BASE_URL}/v1/markets/quotes"
TECH_URL = f"{BASE_URL}/v1/markets/history"

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded"
}

# === Telegram Alert ===
def notify_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not set. Skipping alert.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            print("⚠️ Telegram alert failed:", response.text)
    except Exception as e:
        print("⚠️ Telegram exception:", str(e))

# === Market Status Check (only in live mode) ===
def is_market_open():
    response = requests.get(CLOCK_URL, headers=HEADERS)
    try:
        data = response.json()
        return data["clock"]["state"] == "open"
    except Exception:
        print("⚠️ Failed to decode market clock response.")
        return False

# === Time Check: Before 4 PM EDT ===
def is_before_market_close():
    now = datetime.now()
    return now.hour < 16

# === Get All Open Positions ===
def get_open_positions():
    response = requests.get(POSITIONS_URL, headers=HEADERS)
    try:
        data = response.json()
        raw = data.get("positions", {}).get("position", [])
        if isinstance(raw, dict):
            return [raw]
        return raw
    except Exception:
        print("⚠️ Failed to decode positions response.")
        return []

# === Get Current QQQ Price ===
def get_qqq_price():
    params = {"symbols": "QQQ"}
    try:
        response = requests.get(QUOTE_URL, headers=HEADERS, params=params)
        data = response.json()
        return float(data["quotes"]["quote"]["last"])
    except Exception:
        print("⚠️ Failed to fetch QQQ price.")
        return None

# === Get Option Quote ===
def get_option_price(symbol):
    params = {"symbols": symbol}
    try:
        response = requests.get(QUOTE_URL, headers=HEADERS, params=params)
        data = response.json()
        quote = data.get("quotes", {}).get("quote", {})
        return float(quote.get("last", 0))
    except Exception:
        print(f"⚠️ Failed to fetch price for {symbol}")
        return 0

# === Get MACD and RSI ===
def get_qqq_technicals():
    params = {
        "symbol": "QQQ",
        "interval": "daily",
        "start": datetime.today().replace(day=1).strftime("%Y-%m-%d"),
        "indicators": "macd,rsi"
    }
    try:
        response = requests.get(TECH_URL, headers=HEADERS, params=params)
        data = response.json()
        indicators = data.get("technicals", {})
        macd = indicators.get("macd", [])[-1]
        rsi = indicators.get("rsi", [])[-1]
        return macd, rsi
    except Exception:
        print("⚠️ Failed to fetch MACD/RSI.")
        return None, None

# === Filter for QQQ Put Legs Expiring Today, ITM, and Premium > $0.05 ===
def find_qqq_put_legs():
    positions = get_open_positions()
    today = datetime.today().strftime("%Y-%m-%d")
    qqq_price = get_qqq_price()

    if qqq_price is None:
        notify_telegram("⚠️ Could not fetch QQQ price. Skipping close.")
        return []

    qqq_puts = []
    for p in positions:
        symbol = p.get("symbol", "")
        if not symbol.startswith("QQQ") or "P" not in symbol:
            continue
        if p.get("expiration_date") != today:
            continue

        try:
            strike_str = symbol[-8:]
            strike = int(strike_str) / 1000
            premium = get_option_price(symbol)

            if strike > qqq_price and premium > 0.05:
                qqq_puts.append(p)
        except Exception:
            print(f"⚠️ Failed to parse or price {symbol}")

    return qqq_puts

# === Submit Multileg Close Order ===
def close_qqq_put_legs(legs):
    payload = {
        "type": "market",
        "duration": "day",
        "class": "multileg",
        "symbol": "QQQ"
    }

    for i, leg in enumerate(legs):
        side = "buy_to_close" if leg["quantity"] > 0 else "sell_to_close"
        payload[f"side[{i}]"] = side
        payload[f"option_symbol[{i}]"] = leg["symbol"]
        payload[f"quantity[{i}]"] = str(abs(leg["quantity"]))

    response = requests.post(ORDER_URL, headers=HEADERS, data=payload)
    print("🔍 Raw response:", response.text)
    try:
        return response.json()
    except Exception:
        return {"error": "Invalid JSON response"}

# === Main Execution ===
def main():
    print(f"🔧 Running in {'SANDBOX' if SANDBOX else 'LIVE'} mode")

    if not SANDBOX:
        if not is_market_open():
            msg = "🚫 Market is closed. Skipping close execution."
            print(msg)
            notify_telegram(msg)
            return
        if not is_before_market_close():
            msg = "⏰ It's past 4 PM EDT. Cannot close expiring positions."
            print(msg)
            notify_telegram(msg)
            return
    else:
        print("🧪 Sandbox mode: skipping market and time checks.")

    print("📈 Checking MACD and RSI trend...")
    macd, rsi = get_qqq_technicals()
    if macd is None or rsi is None:
        notify_telegram("⚠️ Could not fetch MACD/RSI. Skipping close.")
        return

    if macd < 0 or rsi < 40:
        msg = f"📉 Trend is bearish (MACD={macd:.2f}, RSI={rsi:.2f}). Proceeding to close spreads."
        print(msg)
        notify_telegram(msg)
    else:
        print(f"✅ Trend is favorable (MACD={macd:.2f}, RSI={rsi:.2f}). No action needed.")
        return

    print("🔍 Checking for QQQ put positions expiring today, ITM, and premium > $0.05...")
    legs = find_qqq_put_legs()
    if not legs:
        msg = "📭 No QQQ puts expiring today that are ITM with premium > $0.05. Skipping close."
        print(msg)
        notify_telegram(msg)
        return

    print("🛠️ Found qualifying QQQ puts. Submitting close order...")
    result = close_qqq_put_legs(legs)
    if not result or "error" in result:
        notify_telegram(f"❌ Close order failed: {result}")
    else:
        print("✅ Close order submitted:", result)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        notify_telegram(f"❌ Script crashed: {str(e)}")
        raise

