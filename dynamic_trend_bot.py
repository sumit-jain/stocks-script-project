import os
import requests
import pandas as pd
import pandas_ta as ta
from datetime import datetime
from dotenv import load_dotenv
import time
import logging
from collections import deque
import matplotlib.pyplot as plt

# === Setup ===
load_dotenv("/root/qqq-trading/.env.live")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

BASE_URL = "https://api.tradier.com"
HEADERS = {
    "Authorization": f"Bearer {TRADIER_TOKEN}",
    "Accept": "application/json"
}

logging.basicConfig(filename="/root/qqq-trading/bot_errors.log", level=logging.ERROR)
recent_tickers = deque(maxlen=10)

# === Telegram API ===
def send_telegram(text, chat_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        logging.error(f"Telegram send failed: {e}")

def send_chart(path, chat_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(path, "rb") as img:
        requests.post(url, data={"chat_id": chat_id}, files={"photo": img})

# === Historical Data ===
def fetch_history(ticker):
    try:
        params = {
            "symbol": ticker.upper(),
            "interval": "daily",
            "start": (datetime.today() - pd.Timedelta(days=60)).strftime("%Y-%m-%d"),
            "end": datetime.today().strftime("%Y-%m-%d")
        }
        r = requests.get(f"{BASE_URL}/v1/markets/history", headers=HEADERS, params=params)
        data = r.json().get("history", {}).get("day", [])
        if not data:
            return None
        df = pd.DataFrame(data)
        df["close"] = pd.to_numeric(df["close"])
        df["volume"] = pd.to_numeric(df["volume"])
        return df
    except Exception as e:
        logging.error(f"Fetch history failed: {e}")
        return None

# === Intraday Data ===
def analyze_intraday_ticker(ticker):
    now = datetime.now()

    # Check if market is open (9:30 AM to 4:00 PM ET)
    if now.hour < 9 or (now.hour == 9 and now.minute < 30) or now.hour >= 16:
        return f"⚠️ Market is closed. Intraday data for `{ticker}` is only available between 9:30 AM and 4:00 PM ET."

    start = now.replace(hour=9, minute=30, second=0).strftime("%Y-%m-%dT%H:%M")
    end = now.strftime("%Y-%m-%dT%H:%M")

    params = {
        "symbol": ticker.upper(),
        "interval": "5min",
        "start": start,
        "end": end,
        "session_filter": "open"
    }

    try:
        r = requests.get(f"{BASE_URL}/v1/markets/timesales", headers=HEADERS, params=params)
        if r.status_code != 200:
            logging.error(f"Tradier intraday API failed: {r.status_code} {r.text}")
            return f"⚠️ Error fetching intraday data for `{ticker}`."

        data = r.json().get("series", {}).get("data", [])
        if not data:
            return f"⚠️ No intraday data available for `{ticker}`. Try again during market hours."

        df = pd.DataFrame(data)
        df["close"] = pd.to_numeric(df["close"])
        df["volume"] = pd.to_numeric(df["volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        macd_df = df.ta.macd(close="close")
        rsi_df = df.ta.rsi(close="close")
        df = pd.concat([df, macd_df, rsi_df], axis=1)

        latest = df.iloc[-1]
        macd = latest.get("MACD_12_26_9")
        rsi = latest.get("RSI_14")
        volume_strength = latest["volume"] / df["volume"].tail(50).mean()
        price = latest["close"]

        return (
            f"📊 *{ticker.upper()} Intraday Trend*\n\n"
            f"• Price: ${price:.2f}\n"
            f"• MACD: {macd:.2f} {'📈' if macd > 0 else '📉'}\n"
            f"• RSI (14): {rsi:.2f} {'✅' if rsi > 50 else '⚠️'}\n"
            f"• Volume Spike: {volume_strength:.2f}x {'✅' if volume_strength > 1 else '⚠️'}\n\n"
            f"{'✅ Bullish momentum' if macd > 0 and rsi > 50 else '⚠️ Weak or reversing trend'}"
        )

    except Exception as e:
        logging.error(f"Intraday analysis failed: {e}")
        return f"⚠️ Error analyzing intraday data for `{ticker}`."

# === Daily Trend ===
def analyze_ticker(ticker):
    df = fetch_history(ticker)
    if df is None or df.empty:
        return f"⚠️ No data found for `{ticker}`."

    try:
        macd_df = df.ta.macd(close="close")
        rsi_df = df.ta.rsi(close="close")
        df["SMA_20"] = df["close"].rolling(window=20).mean()
        df = pd.concat([df, macd_df, rsi_df], axis=1)

        latest = df.iloc[-1]
        price = latest["close"]
        macd = latest.get("MACD_12_26_9")
        macd_signal = latest.get("MACDs_12_26_9")
        rsi = latest.get("RSI_14")
        sma = latest.get("SMA_20")
        volume_strength = latest["volume"] / df["volume"].tail(50).mean()

        trend = {
            "macd": f"{macd:.2f} {'📈' if macd > 0 else '📉'}",
            "rsi": f"{rsi:.2f} {'✅' if rsi > 50 else '⚠️'}",
            "volume": f"{volume_strength:.2f}x {'✅' if volume_strength > 1 else '⚠️'}",
            "sma": f"{sma:.2f} {'⬆️ Above' if price > sma else '⬇️ Below'}"
        }

        crossover = "✅ Bullish crossover" if macd > macd_signal else "⚠️ Bearish crossover"
        return (
            f"📊 *{ticker.upper()} Daily Trend*\n\n"
            f"• Price: ${price:.2f}\n"
            f"• MACD: {trend['macd']}\n"
            f"• MACD Signal: {macd_signal:.2f}\n"
            f"• RSI (14): {trend['rsi']}\n"
            f"• SMA(20): {trend['sma']}\n"
            f"• Volume Strength: {trend['volume']}\n"
            f"• {crossover}\n\n"
            f"{'✅ Bullish momentum' if macd > 0 and rsi > 50 else '⚠️ Weak or reversing trend'}"
        )
    except Exception as e:
        logging.error(f"Analysis failed: {e}")
        return f"⚠️ Error analyzing `{ticker}`."

# === News Sentiment ===
def fetch_news_sentiment(ticker):
    url = f"https://api.polygon.io/v2/reference/news?ticker={ticker.upper()}&limit=3&apiKey={POLYGON_API_KEY}"
    r = requests.get(url)
    articles = r.json().get("results", [])
    if not articles:
        return f"⚠️ No news found for `{ticker}`."

    summary = f"📰 *{ticker.upper()} News Sentiment*\n\n"
    sentiment_score = 0
    for a in articles:
        title = a.get("title", "")
        sentiment = a.get("sentiment", "neutral")
        emoji = "✅" if sentiment == "positive" else "⚠️" if sentiment == "negative" else "➖"
        summary += f"• {title} {emoji}\n"
        sentiment_score += {"positive": 1, "neutral": 0, "negative": -1}.get(sentiment, 0)

    overall = "✅ Bullish" if sentiment_score > 0 else "⚠️ Bearish" if sentiment_score < 0 else "➖ Neutral"
    return summary + f"\nSentiment: {overall}"

# === Spread Strategy ===
def preview_spread_strategy(ticker):
    df = fetch_history(ticker)
    if df is None or df.empty:
        return f"⚠️ No price data for `{ticker}`."
    price = df["close"].iloc[-1]
    short_strike = round(price * 0.97, 1)
    long_strike = round(price * 0.94, 1)
    credit = 1.68
    spread_width = short_strike - long_strike
    max_profit = credit * 100
    max_loss = (spread_width - credit) * 100
    breakeven = short_strike - credit
    pop = "71%"  # placeholder, can be calculated from delta later

    return (
        f"💰 *{ticker.upper()} Bull Put Spread Preview*\n\n"
        f"• Sell {short_strike}P / Buy {long_strike}P\n"
        f"• Credit: ${credit:.2f}\n"
        f"• Max Profit: ${max_profit:.0f}\n"
        f"• Max Loss: ${max_loss:.0f}\n"
        f"• Breakeven: ${breakeven:.2f}\n"
        f"• POP: {pop} ✅\n\n"
        f"Bias: Bullish above ${short_strike}"
    )

def generate_chart(df, ticker):
    try:
        plt.figure(figsize=(10, 4))
        plt.plot(df["timestamp"] if "timestamp" in df else df.index, df["close"], label="Close", color="blue")
        plt.title(f"{ticker.upper()} Closing Prices")
        plt.xlabel("Time")
        plt.ylabel("Price")
        plt.grid(True)
        plt.tight_layout()
        path = f"/root/qqq-trading/charts/{ticker}_chart.png"
        plt.savefig(path)
        return path
    except Exception as e:
        logging.error(f"Chart generation failed: {e}")
        return None

def run_bot():
    send_telegram("✅ Trend bot is now live and listening for tickers.", CHAT_ID)
    offset = None
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            if offset:
                url += f"?offset={offset}"
            r = requests.get(url).json()
            for update in r.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                text = msg.get("text", "").strip()
                chat_id = msg.get("chat", {}).get("id")

                if not text:
                    continue
                if text in recent_tickers:
                    continue
                recent_tickers.append(text)

                # === Command Handling ===
                if text.startswith("/"):
                    if text == "/help":
                        send_telegram("ℹ️ Send a ticker like `AAPL`, `QQQ`, or `/spread QQQ`, `/news AAPL`, `/chart TSLA`.", chat_id)
                    elif text == "/start":
                        send_telegram("👋 Welcome! Send a ticker symbol to get started.", chat_id)
                    elif text.startswith("/news "):
                        ticker = text.split("/news ")[1].strip()
                        response = fetch_news_sentiment(ticker)
                        send_telegram(response, chat_id)
                    elif text.startswith("/spread "):
                        ticker = text.split("/spread ")[1].strip()
                        response = preview_spread_strategy(ticker)
                        send_telegram(response, chat_id)
                    elif text.lower().startswith("/intra "):
                        ticker = text.split("/intra ")[1].strip().upper()
                        response = analyze_intraday_ticker(ticker)
                        send_telegram(response, chat_id)
                        continue
                    elif text.startswith("/chart "):
                        ticker = text.split("/chart ")[1].strip()
                        df = fetch_history(ticker)
                        if df is not None:
                            path = generate_chart(df, ticker)
                            if path:
                                send_chart(path, chat_id)
                            else:
                                send_telegram("⚠️ Chart generation failed.", chat_id)
                        else:
                            send_telegram("⚠️ No data available for chart.", chat_id)
                    continue

                # === Intraday Mode ===
                if text.upper().endswith("_INTRA"):
                    ticker = text.upper().replace("_INTRA", "")
                    response = analyze_intraday_ticker(ticker)
                    send_telegram(response, chat_id)
                    continue

                # === Daily Analysis ===
                if text.isalpha() and len(text) <= 5:
                    print(f"📥 Received ticker: {text}")
                    response = analyze_ticker(text)
                    send_telegram(response, chat_id)
                else:
                    send_telegram("⚠️ Invalid ticker format. Please send a valid symbol like `AAPL` or `QQQ`.", chat_id)
        except Exception as e:
            logging.error(f"Polling loop error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    run_bot()

