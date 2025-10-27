import yfinance as yf
import pandas as pd
import sys

def fetch_data(ticker):
    df = yf.download(ticker, period='6mo', interval='1d', auto_adjust=False)
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
    df['EMA10'] = df['Close'].ewm(span=10, adjust=False).mean()

    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = macd - signal

    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    df.dropna(inplace=True)
    return df

def simulate_trades(df, ticker):
    holding = False
    qty = 100
    entry_price = 0.0
    trades = []
    total_profit = 0.0
    wins = 0
    losses = 0

    for i in range(len(df)):
        row = df.iloc[i]
        date = row.name.strftime('%Y-%m-%d')
        price = float(row['Close'])
        ema10 = float(row['EMA10'])
        macd_hist = float(row['MACD_Hist'])
        rsi = float(row['RSI'])

        if not holding and price > ema10 and macd_hist > 0 and rsi < 70:
            entry_price = price
            trades.append([date, 'BUY', qty, f"${price:.2f}", 'EMA10 + MACD + RSI', ''])
            holding = True

        elif holding and (macd_hist < 0 or rsi > 80):
            profit = (price - entry_price) * qty
            total_profit += profit
            win = profit > 0
            if win: wins += 1
            else: losses += 1
            reason = 'MACD exit or RSI > 80'
            trades.append([date, 'SELL', qty, f"${price:.2f}", reason, f"${profit:.2f}"])
            holding = False

    return trades, total_profit, wins, losses

def print_trades(trades, ticker, total_profit, wins, losses):
    df = pd.DataFrame(trades, columns=['Date', 'Type', 'Qty', 'Price', 'Reason', 'P&L'])
    print(f"\n📊 Simulated Trade Log for {ticker}")
    try:
        print(df.to_markdown(index=False))
    except ImportError:
        print(df.tail(10))  # fallback if tabulate not installed

    total_trades = wins + losses
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    print(f"\n📈 Summary:")
    print(f"Total Trades: {total_trades}")
    print(f"Profitable Trades: {wins}")
    print(f"Unprofitable Trades: {losses}")
    print(f"Win Rate: {win_rate:.1f}%")
    print(f"Total P&L: ${total_profit:.2f}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python signal_bot.py <TICKER>")
    else:
        ticker = sys.argv[1].upper()
        df = fetch_data(ticker)
        trades, total_profit, wins, losses = simulate_trades(df, ticker)
        print_trades(trades, ticker, total_profit, wins, losses)

