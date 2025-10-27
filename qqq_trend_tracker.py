import os
import requests
import pandas as pd
import pandas_ta as ta
from datetime import datetime
from dotenv import load_dotenv
import json

# === Load Environment ===
env_mode = os.getenv("ENV_MODE", "sandbox")
env_path = f"/root/qqq-trading/.env.{env_mode}"
load_dotenv(dotenv_path=env_path)

API_TOKEN = os.getenv("TRADIER_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE_URL = "https://sandbox.tradier.com" if env_mode == "sandbox" else "https://api.tradier.com"
HISTORY_URL = f"{BASE_URL}/v1/markets/history"
HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Accept": "application/json"
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

# === Fetch Full History (60 days) ===
def fetch_full_history():
    start_date = (datetime.today() - pd.Timedelta(days=60)).strftime("%Y-%m-%d")
    end_date = datetime.today().strftime("%Y-%m-%d")
    params = {
        "symbol": "QQQ",
        "interval": "daily",
        "start": start_date,
        "end": end_date
    }
    response = requests.get(HISTORY_URL, headers=HEADERS, params=params)
    print("🔍 Raw response:", response.text)
    try:
        data = response.json()
        bars = data.get("history", {}).get("day", [])
        df = pd.DataFrame(bars)
        df["date"] = pd.to_datetime(df["date"])
        df["close"] = pd.to_numeric(df["close"])
        df["volume"] = pd.to_numeric(df["volume"])
        return df
    except Exception as e:
        print("⚠️ JSON decode failed:", str(e))
        return pd.DataFrame()

# === Save Updated CSV ===
def save_history_csv(df):
    df.to_csv("/root/qqq-trading/qqq_history.csv", index=False)

# === Save Trend Snapshot ===
def save_trend_snapshot(macd, rsi, volume_strength):
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "macd": round(macd, 2),
        "rsi": round(rsi, 2),
        "volume_strength": round(volume_strength, 2)
    }
    with open("/root/qqq-trading/qqq_trend_snapshot.json", "w") as f:
        json.dump(snapshot, f, indent=2)

# === Interpret Trend with Emojis ===
def interpret_trend(macd, rsi, volume_strength, price, sma_50, sma_200):
    return {
        "macd": f"{macd:.2f} {'📈' if macd > 0 else '📉'}",
        "rsi": f"{rsi:.2f} {'✅' if rsi > 50 else '⚠️'}",
        "volume": f"{volume_strength:.2f}x {'✅' if volume_strength > 1 else '⚠️'}",
        "sma_50": f"{'✅' if price > sma_50 else '⚠️'}",
        "sma_200": f"{'✅' if price > sma_200 else '⚠️'}"
    }

# === Determine Market Phase ===
def get_market_phase():
    now = datetime.now()
    hour = now.hour
    minute = now.minute
    if hour < 9 or (hour == 9 and minute < 30):
        return "Pre-market"
    elif 9 <= hour < 16 or (hour == 16 and minute == 0):
        return "Regular hours"
    else:
        return "After-hours"

# === Main Execution ===
def main():
    print(f"🔧 Running in {env_mode.upper()} mode")
    df = fetch_full_history()
    if df.empty:
        notify_telegram("⚠️ No historical data available. Skipping trend update.")
        return

    save_history_csv(df)

    # === Calculate Indicators ===
    macd_df = df.ta.macd(close="close")
    rsi_df = df.ta.rsi(close="close")
    sma_50_df = df.ta.sma(length=50)
    sma_200_df = df.ta.sma(length=200)
    stoch_df = df.ta.stoch()
    atr_df = df.ta.atr(length=14)

    df = pd.concat([df, macd_df, rsi_df, sma_50_df, sma_200_df, stoch_df, atr_df], axis=1)

    latest_row = df.iloc[-1]
    macd = latest_row.get("MACD_12_26_9", None)
    rsi = latest_row.get("RSI_14", None)
    sma_50 = latest_row.get("SMA_50", None)
    sma_200 = latest_row.get("SMA_200", None)
    stoch_k = latest_row.get("STOCHk_14_3_3", None)
    stoch_d = latest_row.get("STOCHd_14_3_3", None)
    atr = latest_row.get("ATRr_14", None)

    if None in [macd, rsi, sma_50, sma_200]:
        notify_telegram("⚠️ One or more indicators missing. Skipping trend alert.")
        return

    price = latest_row["close"]
    volume_strength = latest_row["volume"] / df["volume"].tail(50).mean()

    save_trend_snapshot(macd, rsi, volume_strength)

    trend = interpret_trend(macd, rsi, volume_strength, price, sma_50, sma_200)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    market_phase = get_market_phase()
    volume_note = " (Extended hours)" if market_phase != "Regular hours" else ""

    message = (
        f"📈 *QQQ Trend Update — {timestamp} ({market_phase})*\n\n"
        f"• MACD: {trend['macd']} → {'Bullish' if macd > 0 else 'Bearish'} momentum\n"
        f"• RSI (14): {trend['rsi']} → {'Bullish' if rsi > 50 else 'Bearish'}\n"
        f"• Volume Strength{volume_note}: {trend['volume']} → {'Above' if volume_strength > 1 else 'Below'} avg\n"
        f"• Price: ${price:.2f}\n"
        f"• 50-day SMA: ${sma_50:.2f} {trend['sma_50']}\n"
        f"• 200-day SMA: ${sma_200:.2f} {trend['sma_200']}\n"
        f"• Stochastic Oscillator: %K={stoch_k:.2f}, %D={stoch_d:.2f}\n"
        f"• ATR (14): {atr:.2f} → Volatility level\n\n"
        f"{'✅ Trend supports bullish positions.' if macd > 0 and rsi > 50 else '⚠️ Trend may be weakening.'}"
    )

    notify_telegram(message)

if __name__ == "__main__":
    main()

