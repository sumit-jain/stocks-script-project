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
sandbox = True
env_file = ".env.sandbox" if sandbox else ".env.live"
load_dotenv(env_file)

TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TRADIER_BASE_URL = "https://sandbox.tradier.com/v1" if sandbox else "https://api.tradier.com/v1"

def get_account_balance():
    url = f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/balances"
    headers = {
        "Authorization": f"Bearer {TRADIER_TOKEN}",
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        if "fault" in data:
            print("Tradier error:", data["fault"])
            return None
        balance = data.get("balances", {}).get("total_equity")
        return float(balance) if balance is not None else None
    except Exception as e:
        print("Error fetching account balance:", str(e))
        return None

def notify_summary(trade_df, ticker, sandbox):
    today = datetime.today().date()
    today_trades = trade_df[trade_df["Date"] == str(today)]

    mode = "sandbox" if sandbox else "live"
    print("mode:", mode)
    print("sandbox", sandbox)
    if today_trades.empty:
        message = f"📊 No trades triggered for *{ticker}* on {today.strftime('%b %d, %Y')}.\nBroker mode: `{mode}`"
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
    portfolio_value = get_account_balance()
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

def place_order(action, quantity, symbol, price):
    side = "buy" if action.startswith("BUY") else "sell"
    payload = {
        "class": "equity",
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "type": "market",
        "duration": "gtc"
    }
    headers = {
        "Authorization": f"Bearer {TRADIER_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    url = f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders"
    response = requests.post(url, data=payload, headers=headers)
    try:
        if response.status_code == 200:
            print(f"{action} order → {symbol} x{quantity} @ ${price:.2f} →", response.json())
        else:
            print(f"{action} order failed → Status: {response.status_code}, Body: {response.text}")
    except Exception as e:
        print(f"{action} order error →", str(e), "| Raw response:", response.text)

def send_chart_to_telegram(fig, caption="Strategy Chart"):
    img_bytes = fig.to_image(format="png", width=1000, height=600, scale=2)
    img_io = io.BytesIO(img_bytes)
    img_io.name = "chart.png"
    img_io.seek(0)
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    files = {"photo": img_io}
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption}
    try:
        response = requests.post(url, data=data, files=files)
        print("Telegram chart sent:", response.json())
    except Exception as e:
        print("Telegram chart error:", str(e))

def calculate_shares(price, max_allocation):
    return max(int(max_allocation // price), 1)

def get_current_price(ticker):
    base_url = "https://sandbox.tradier.com/v1" if sandbox else "https://api.tradier.com/v1"
    url = f"{base_url}/markets/quotes?symbols={ticker}"
    headers = {
        "Authorization": f"Bearer {TRADIER_TOKEN}",
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        return float(data["quotes"]["quote"]["last"])
    except Exception as e:
        print("Price fetch error:", str(e))
        return None

def get_portfolio_value():
    base_url = "https://sandbox.tradier.com/v1" if sandbox else "https://api.tradier.com/v1"
    url = f"{base_url}/accounts/{TRADIER_ACCOUNT_ID}/balances"
    headers = {
        "Authorization": f"Bearer {TRADIER_TOKEN}",
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        equity = float(data["balances"]["total_equity"])
        print(f"✅ Portfolio value fetched: ${equity:.2f}")
        return equity
    except Exception as e:
        print("⚠️ Portfolio fetch failed, defaulting to $5000:", str(e))
        return 5000

def get_tqqq_position():
    base_url = "https://sandbox.tradier.com/v1" if sandbox else "https://api.tradier.com/v1"
    url = f"{base_url}/accounts/{TRADIER_ACCOUNT_ID}/positions"
    headers = {
        "Authorization": f"Bearer {TRADIER_TOKEN}",
        "Accept": "application/json"
    }

    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        positions = data.get("positions", {}).get("position", [])

        if not positions:
            print("✅ No open positions found.")
            return 0

        if isinstance(positions, dict):  # Single position
            positions = [positions]

        for pos in positions:
            if pos["symbol"].upper() == "TQQQ":
                shares = int(pos["quantity"])
                print(f"📊 TQQQ position: {shares} shares")
                return shares

        print("⚠️ No TQQQ position found.")
        return 0

    except Exception as e:
        print("❌ Error fetching TQQQ position:", str(e))
        return 0

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

    position = get_tqqq_position()
    trade_log = []
    price = get_current_price(ticker)
    portfolio_value = get_portfolio_value()
    capital_per_trade = portfolio_value * 0.90  # 90% allocation
    shares = max(int(capital_per_trade // price), 1)
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
                place_order("BUY", shares, ticker, price)
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
                place_order("SELL", position, ticker, price)
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



def generate_chart(df, trade_log, output_path="tqqq_chart.png"):
    # Ensure datetime index is clean and sorted
    df.index = pd.to_datetime(df.index)
    df.sort_index(inplace=True)

    # Flatten MultiIndex columns if needed
    df.columns = ['_'.join(col) if isinstance(col, tuple) else col for col in df.columns]

    # Convert x-axis to list of naive datetime objects
    x_dates = [pd.Timestamp(d).to_pydatetime() for d in df.index]

    # Prepare marker data
    buy_dates, buy_prices = [], []
    sell_dates, sell_prices = [], []

    for trade in trade_log:
        date = pd.to_datetime(trade["Date"]).to_pydatetime()
        price = float(trade["Price"])
        if "BUY" in trade["Action"]:
            buy_dates.append(date)
            buy_prices.append(price)
        else:
            sell_dates.append(date)
            sell_prices.append(price)

    # Create figure
    fig = go.Figure()

    # Line traces
    fig.add_trace(go.Scatter(
        x=x_dates,
        y=df["Close_TQQQ"].tolist(),
        mode='lines',
        name='Close_TQQQ',
        line=dict(color='blue')
    ))

    fig.add_trace(go.Scatter(
        x=x_dates,
        y=df["EMA20"].tolist(),
        mode='lines',
        name='EMA20',
        line=dict(color='orange')
    ))

    fig.add_trace(go.Scatter(
        x=x_dates,
        y=df["SMA40"].tolist(),
        mode='lines',
        name='SMA40',
        line=dict(color='green')
    ))

    # Marker traces
    fig.add_trace(go.Scatter(
        x=buy_dates,
        y=buy_prices,
        mode="markers",
        marker=dict(symbol="triangle-up", color="green", size=14, line=dict(width=1, color="black")),
        name="BUY",
        hovertext=[f"BUY @ ${p:.2f}" for p in buy_prices],
        hoverinfo="text",
        showlegend=True
    ))

    fig.add_trace(go.Scatter(
        x=sell_dates,
        y=sell_prices,
        mode="markers",
        marker=dict(symbol="triangle-down", color="red", size=14, line=dict(width=1, color="black")),
        name="SELL",
        hovertext=[f"SELL @ ${p:.2f}" for p in sell_prices],
        hoverinfo="text",
        showlegend=True
    ))

    # Layout
    fig.update_layout(
        title="TQQQ Strategy Chart",
        template="plotly_white",
        paper_bgcolor="white",
        plot_bgcolor="white",
        autosize=False,
        width=1200,
        height=700,
        margin=dict(l=40, r=40, t=40, b=40),
        xaxis=dict(showgrid=True, showline=True, zeroline=False, type="date"),
        yaxis=dict(showgrid=True, showline=True, zeroline=False)
    )

    # Export
    fig.write_image(output_path, format="png", scale=2)
    return fig

if __name__ == "__main__":
    ticker = "TQQQ"
    period = "1 Year"
    df, trade_df, trade_log, summary = simulate_strategy(ticker, period)
    notify_summary(trade_df, ticker, sandbox)
    df.columns = [col[0] if col[1] == '' else f"{col[0]}_{col[1]}" for col in df.columns]
    fig = generate_chart(df, trade_log, ticker)
    # === Send to Telegram ===
    send_chart_to_telegram(fig, caption=summary)
    #print(TRADIER_BASE_URL)



