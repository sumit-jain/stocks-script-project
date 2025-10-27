import os
import pandas as pd
import pandas_ta as ta
from datetime import datetime
import json
from dotenv import load_dotenv
import requests

# === Load Environment ===
env_path = "/root/qqq-trading/.env.sandbox"
load_dotenv(dotenv_path=env_path)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === Telegram Alert ===
def notify_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not set.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print("⚠️ Telegram error:", str(e))

# === Load Intraday CSV ===
def load_intraday_data():
    path = "/root/qqq-trading/qqq_intraday_data.csv"
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        print("⚠️ File missing or empty.")
        return pd.DataFrame()
    df = pd.read_csv(path)
    expected_cols = {"datetime", "open", "high", "low", "close", "volume"}
    if not expected_cols.issubset(df.columns):
        print("⚠️ Missing expected columns:", df.columns.tolist())
        return pd.DataFrame()
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["close"] = pd.to_numeric(df["close"])
    df["volume"] = pd.to_numeric(df["volume"])
    return df

# === Save Snapshot ===
def save_snapshot(macd, rsi, volume_strength):
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "macd": round(macd, 2),
        "rsi": round(rsi, 2),
        "volume_strength": round(volume_strength, 2)
    }
    with open("/root/qqq-trading/qqq_intraday_snapshot.json", "w") as f:
        json.dump(snapshot, f, indent=2)

# === Interpret Trend ===
def interpret_trend(macd, rsi, volume_strength):
    return {
        "macd": f"{macd:.2f} {'📈' if macd > 0 else '📉'}",
        "rsi": f"{rsi:.2f} {'✅' if rsi > 50 else '⚠️'}",
        "volume": f"{volume_strength:.2f}x {'✅' if volume_strength > 1 else '⚠️'}"
    }

# === Main ===
def main():
    df = load_intraday_data()

    # Calculate indicators
    macd_df = df.ta.macd(close="close")
    rsi_df = df.ta.rsi(close="close")
    df = pd.concat([df, macd_df, rsi_df], axis=1)

    latest = df.iloc[-1]
    macd = latest.get("MACD_12_26_9", None)
    rsi = latest.get("RSI_14", None)
    volume_strength = latest["volume"] / df["volume"].tail(50).mean()

    if None in [macd, rsi]:
        notify_telegram("⚠️ Intraday MACD/RSI missing. Skipping alert.")
        return

    save_snapshot(macd, rsi, volume_strength)
    trend = interpret_trend(macd, rsi, volume_strength)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    message = (
        f"📊 *QQQ Intraday Trend — {timestamp}*\n\n"
        f"• MACD: {trend['macd']} → {'Bullish' if macd > 0 else 'Bearish'}\n"
        f"• RSI (14): {trend['rsi']} → {'Bullish' if rsi > 50 else 'Bearish'}\n"
        f"• Volume Strength: {trend['volume']} → {'Above' if volume_strength > 1 else 'Below'} avg\n"
        f"• Price: ${latest['close']:.2f}\n\n"
        f"{'✅ Momentum building intraday.' if macd > 0 and rsi > 50 else '⚠️ Weak or reversing trend.'}"
    )

    notify_telegram(message)

if __name__ == "__main__":
    main()

