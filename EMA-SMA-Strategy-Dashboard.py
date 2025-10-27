import dash
from dash import dcc, html, Input, Output, dash_table
import pandas as pd
import yfinance as yf
import webbrowser
import threading
import plotly.graph_objects as go
from sklearn.linear_model import LinearRegression
import numpy as np
from datetime import datetime, timedelta

app = dash.Dash(__name__)
app.title = "EMA/SMA Strategy Dashboard"

def open_browser():
    webbrowser.open_new("http://127.0.0.1:8050/")

def generate_chart(df, trade_log, initial_capital, final_capital, ticker):
    fig = go.Figure()

    # Plot price and indicators
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df[('Close', ticker)],
        mode='lines',
        name=f'{ticker} Close',
        line=dict(color='blue')
    ))

    fig.add_trace(go.Scatter(
        x=df.index,
        y=df[('EMA20', '')],
        mode='lines',
        name='EMA20',
        line=dict(color='orange')
    ))

    fig.add_trace(go.Scatter(
        x=df.index,
        y=df[('SMA40', '')],
        mode='lines',
        name='SMA40',
        line=dict(color='green')
    ))

    # Plot trades
    show_buy_legend = True
    show_sell_legend = True

    for trade in trade_log:
        date = pd.to_datetime(trade['Date'])
        price = float(trade['Price'])
        action = trade['Action']
        hovertext = f"{action} @ ${price:.2f}"

        if action=="BUY":
            fig.add_trace(go.Scatter(
                x=[date], y=[price], mode='markers',
                marker=dict(symbol='triangle-up', color='green', size=12),
                name='BUY',
                showlegend=show_buy_legend,
                hovertext=[hovertext]
            ))
            show_buy_legend = False
        elif action=="SELL":
            fig.add_trace(go.Scatter(
                x=[date], y=[price], mode='markers',
                marker=dict(symbol='triangle-down', color='red', size=12),
                name='SELL',
                showlegend=show_sell_legend,
                hovertext=[hovertext]
            ))
            show_sell_legend = False

    fig.update_layout(
        title=f"{ticker} Strategy — Start: ${initial_capital:,.2f} → End: ${final_capital:,.2f}",
        xaxis_title="Date",
        yaxis_title="Price",
        height=600
    )

    return fig


def get_start_date(period):
    today = datetime.today()
    return {
        "1 Month": today - timedelta(days=30),
        "3 Months": today - timedelta(days=90),
        "6 Months": today - timedelta(days=180),
        "3 Years": today - timedelta(days=3*365),
    }.get(period, today - timedelta(days=365))  # Default: 1 Year



def simulate_strategy(ticker, period, initial_capital=5000, slope_window=6):
    buffer_days = 60  # or more if using longer SMAs
    start_date = get_start_date(period) - pd.Timedelta(days=buffer_days)

    df = yf.download(ticker, start=start_date.strftime("%Y-%m-%d"), auto_adjust=True)
    df = df[['Close']].copy()
    df.dropna(inplace=True)



    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['SMA40'] = df['Close'].rolling(window=40).mean()
    df = df[df.index >= get_start_date(period)]

    position = 0
    cash = initial_capital
    trade_log = []

    for i in range(slope_window, len(df)):
        try:
            price = float(df['Close'].iloc[i])
            prev_price = float(df['Close'].iloc[i - 1])
            ema = float(df['EMA20'].iloc[i])
            prev_ema = float(df['EMA20'].iloc[i - 1])
            sma = float(df['SMA40'].iloc[i])
            prev_sma = float(df['SMA40'].iloc[i - 1])
        except:
            continue

        date = df.index[i].date()

        # Calculate EMA20 slope over last N candles
        ema_slice = df['EMA20'].iloc[i - slope_window:i].values.reshape(-1, 1)
        x_vals = np.arange(slope_window).reshape(-1, 1)
        model = LinearRegression().fit(x_vals, ema_slice)
        ema_slope = model.coef_[0][0]

        # ✅ BUY condition: either slope-confirmed crossover OR EMA20 > SMA40 crossover with price above both
        buy_condition_1 = (
            prev_price < prev_ema and
            price > ema and
            ema_slope > 0
        )

        buy_condition_2 = (
            prev_ema < prev_sma and
            ema > sma and
            price > ema and
            price > sma
        )

        if position == 0 and price > ema and price > sma :
            shares = cash // price
            if shares > 0:
                position = shares
                cash -= shares * price
                trade_log.append({
                    "Date": str(date),
                    "Action": "BUY",
                    "Price": round(price, 2),
                    "Shares": int(shares),
                    "Portfolio Value": round(cash + shares * price, 2)
                })


        # SELL condition
        elif (
            position > 0 and
            prev_price > prev_sma and
            price < sma 
        ):
            cash += position * price
            trade_log.append({
                "Date": str(date),
                "Action": "SELL",
                "Price": round(price, 2),
                "Shares": int(position),
                "Portfolio Value": round(cash, 2)
            })
            position = 0

    # Final exit
    if position > 0:
        final_price = float(df['Close'].iloc[-1])
        cash += position * final_price
        trade_log.append({
            "Date": str(df.index[-1].date()),
            "Action": "SELL (EOD)",
            "Price": round(final_price, 2),
            "Shares": int(position),
            "Portfolio Value": round(cash, 2)
        })

    trade_df = pd.DataFrame(trade_log, columns=["Date", "Action", "Price", "Shares", "Portfolio Value"])
    trade_df['Price'] = trade_df['Price'].map('${:,.2f}'.format)
    trade_df['Portfolio Value'] = trade_df['Portfolio Value'].map('${:,.2f}'.format)
    summary = f"Initial: ${initial_capital:,.2f} → Final: ${cash:,.2f} → Profit: ${cash - initial_capital:,.2f} ({(cash / initial_capital - 1) * 100:.2f}%)"
    return df, trade_df, trade_log, summary, cash


app.layout = html.Div([
    html.H2("📈 EMA(20)/SMA(40) Strategy Simulator"),
    html.Div([
        html.Label("Stock Ticker:"),
        dcc.Input(id="ticker-input", type="text", value="TQQQ", debounce=True),
    ], style={"marginBottom": "10px"}),
    html.Div([
        html.Label("Time Period:"),
        dcc.Dropdown(
            id="period-dropdown",
            options=[{"label": p, "value": p} for p in ["1 Month", "3 Months", "6 Months", "1 Year", "3 Years"]],
            value="1 Year"
        ),
    ], style={"marginBottom": "20px"}),
    html.Div(id="summary-output", style={"fontWeight": "bold", "marginBottom": "10px"}),
    dcc.Graph(id="strategy-chart", style={"height": "600px"}),
    dash_table.DataTable(id="trade-table", page_size=10, style_table={"overflowX": "auto"})

])

@app.callback(
    Output("trade-table", "data"),
    Output("trade-table", "columns"),
    Output("summary-output", "children"),
    Output("strategy-chart", "figure"),
    Input("ticker-input", "value"),
    Input("period-dropdown", "value")
)
def update_table(ticker, period):
    if not ticker:
        return [], [], "Please enter a valid ticker."
    try:
        df, trade_df, trade_log, summary, cash = simulate_strategy(ticker.upper(), period)
        columns = [{"name": col, "id": col} for col in trade_df.columns]

        fig = generate_chart(df, trade_log, 5000, cash, ticker)
        return trade_df.to_dict("records"), columns, summary, fig
    except Exception as e:
        return [], [], f"Error: {str(e)}", go.Figure()


if __name__ == "__main__":
    threading.Timer(1, open_browser).start()
    app.run(debug=True, use_reloader=False)


