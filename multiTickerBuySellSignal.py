import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from sklearn.linear_model import LinearRegression
import numpy as np
from datetime import datetime, timedelta
import os
import requests
from dotenv import load_dotenv
import io
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

IMAGE_PATH = "tqqq_chart.png"
# 🧪 Toggle sandbox/live
sandbox = False
env_file = ".env.sandbox" if sandbox else ".env.live"
load_dotenv(env_file)

TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TRADIER_BASE_URL = "https://sandbox.tradier.com/v1" if sandbox else "https://api.tradier.com/v1"

def load_tickers_from_csv(file_path="tickers2.csv"):
    try:
        df = pd.read_csv(file_path)
        print("CSV columns:", df.columns.tolist())
        return df["Symbol"].dropna().unique().tolist()
    except Exception as e:
        print("Error loading tickers:", str(e))
        return []

def get_current_price(ticker):
    try:
        data = yf.Ticker(ticker).history(period="1d")
        return float(data["Close"].iloc[-1])
    except Exception as e:
        print(f"Error fetching current price for {ticker}:", str(e))
        return None

def notify_summary(trade_df, ticker, sandbox):
    today = datetime.today().date()
    today_trades = trade_df[trade_df["Date"] == str(today)]
    current_price = get_current_price(ticker)
    price_str = f"${current_price:.2f}" if current_price else "Unavailable"

    mode = "sandbox" if sandbox else "live"
    print("mode:", mode)
    print("sandbox", sandbox)
    if today_trades.empty:
        message = f"📊 No trade signal for *{ticker}* on {today.strftime('%b %d, %Y')}.\nBroker mode: `{mode}`\nCurrent Price: {price_str}"
    else:
        message = f"📊 *{ticker}* trades for {today.strftime('%b %d, %Y')} (Broker mode: `{mode}`):\n"
        for _, row in today_trades.iterrows():
            message += f"- {row['Action']} @ ${row['Price']:.2f} ({row['Shares']} shares)\n"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, data=payload)
        print("Telegram summary:", response.json())
    except Exception as e:
        print("Telegram summary error:", str(e))

def notify_telegram(action, symbol, price, shares, reason):
    portfolio_value = 5000
    balance_str = f"${portfolio_value:,.2f}" if portfolio_value is not None else "Unavailable"
    message = (
        f"📢 *{action} Signal Triggered*\n"
        f"*Symbol:* {symbol}\n"
        f"*Price:* ${price:.2f}\n"
        f"*Shares:* {shares}\n"
        f"*Portfolio Value:* {balance_str}\n"
        f"*Reason:* {reason}"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, data=payload)
        print("Telegram notify:", response.json())
    except Exception as e:
        print("Telegram error:", str(e))


def simulate_strategy(ticker="TQQQ", period="1 Year", slope_window=6):
    buffer_days = 60
    start_date = datetime.today() - timedelta(days=365 + buffer_days)
    today = datetime.today().date()

    # Download data and use 'Close' directly
    df = yf.download(ticker, start=start_date.strftime("%Y-%m-%d"), auto_adjust=True)[['Close']].dropna()

    # Compute indicators
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["SMA40"] = df["Close"].rolling(window=40).mean()

    # Filter to last 1 year
    df = df[df.index >= datetime.today() - timedelta(days=365)]

    position=0
    trade_log = []

    shares = 1
    for i in range(slope_window, len(df)):
        try:
            price = float(df["Close"].iloc[i])
            prev_price = float(df["Close"].iloc[i - 1])
            ema = float(df["EMA20"].iloc[i])
            prev_ema = float(df["EMA20"].iloc[i - 1])
            sma = float(df["SMA40"].iloc[i])
            prev_sma = float(df["SMA40"].iloc[i - 1])
        except:
            continue

        date = df.index[i].date()
        ema_slice = df["EMA20"].iloc[i - slope_window:i].values.reshape(-1, 1)
        x_vals = np.arange(slope_window).reshape(-1, 1)
        ema_slope = LinearRegression().fit(x_vals, ema_slice).coef_[0][0]

        buy_condition_1 = prev_price < prev_ema and price > ema and ema_slope > 0
        buy_condition_2 = prev_ema < prev_sma and ema > sma and price > ema and price > sma

        if position == 0 and price > ema and price > sma: #and (buy_condition_1 or buy_condition_2):
            reason = "Slope-confirmed EMA crossover" #if buy_condition_1 else "EMA > SMA breakout"
            if date == today:
                notify_telegram("BUY", ticker, price, shares, reason)
            position = shares
            trade_log.append({
                "Date": str(date),
                "Action": "BUY",
                "Price": round(price, 2),
                "Shares": shares
            })

        elif position > 0 and prev_price > prev_sma and price < sma:
            reason = "Price dropped below SMA after uptrend"
            if date == today:
                notify_telegram("SELL", ticker, price, position, reason)
            trade_log.append({
                "Date": str(date),
                "Action": "SELL",
                "Price": round(price, 2),
                "Shares": position
            })
            position = 0

    trade_df = pd.DataFrame(trade_log, columns=["Date", "Action", "Price", "Shares"])
    summary = f"{ticker} Strategy — Trades: {len(trade_df)}"
    return df, trade_df, trade_log, summary


def get_price_with_backup(ticker):
    """Try yfinance first, fallback to Tradier if it fails."""
    try:
        price = get_current_price(ticker)  # your existing yfinance function
        if price is not None:
            return price
        raise ValueError("yfinance returned None")
    except Exception:
        # Fallback to Tradier API
        try:
            headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
            url = f"https://api.tradier.com/v1/markets/quotes?symbols={ticker}"  # switch to live if needed
            response = requests.get(url, headers=headers)
            data = response.json()
            price = data["quotes"]["quote"]["last"]
            return price
        except Exception as e:
            print(f"❌ Tradier API failed for {ticker}: {e}")
            return None


if __name__ == "__main__":
    ticker_list = load_tickers_from_csv("tickers2.csv")
    total_tickers = len(ticker_list)  # ✅ Count how many tickers we are scanning
    period = "1 Year"

    all_rows = []
    today = datetime.today().date()
    mode = "sandbox" if sandbox else "live"

    for ticker in ticker_list:
        try:
            print(f"\n🔄 Running strategy for {ticker}...")
            df, trade_df, trade_log, summary = simulate_strategy(ticker, period)

            today_trades = trade_df[trade_df["Date"] == str(today)]
            if today_trades.empty:
                continue  # Skip tickers with no trades today

            last_trade = today_trades.iloc[-1]
            action = last_trade["Action"]
            if action == "NO SIGNAL":
                continue  # Skip trades with no signal

            trade_price = f"${last_trade['Price']:.2f}"
            current_price = get_price_with_backup(ticker)
            price_str = f"${current_price:.2f}" if current_price else "Unavailable"

            all_rows.append((ticker, action, trade_price, price_str))

        except Exception as e:
            print(f"❌ Error processing {ticker}: {str(e)}")
            all_rows.append((ticker, "ERROR", "-", "-"))

    # === Message building ===
    if len(all_rows) == 0:
        final_message = (
            f"📈 *Daily Trade Summary* ({today.strftime('%b %d, %Y')})\n"
            f"Broker mode: `{mode}`\n"
            f"Tickers scanned: *{total_tickers}*\n"
            f"No trading signals were found today. ✅"
        )
    else:
        header = f"{'Ticker':<8}{'Action':<10}{'Price':<10}{'Current':<10}"
        message_lines = [header, "-"*38]
        for row in all_rows:
            line = f"{row[0]:<8}{row[1]:<10}{row[2]:<10}{row[3]:<10}"
            message_lines.append(line)

        final_message = (
            f"📈 *Daily Trade Summary* ({today.strftime('%b %d, %Y')})\n"
            f"Broker mode: `{mode}`\n"
            f"Tickers scanned: *{total_tickers}*\n"
            f"Signals found: *{len(all_rows)}*\n\n"
            + "```\n"
            + "\n".join(message_lines)
            + "\n```"
        )

    # === Send Telegram message ===
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": final_message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, data=payload)
        print("✅ Combined Telegram summary sent:", response.json())
    except Exception as e:
        print("❌ Telegram send error:", str(e))








