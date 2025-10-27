import streamlit as st
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from sklearn.linear_model import LinearRegression
import numpy as np
from datetime import datetime, timedelta

# Remove top padding / whitespace in Streamlit
st.markdown(
    """
    <style>
        /* Remove default top padding in main container */
        div.block-container {
            padding-top: 1rem;  /* reduce from ~6rem to 1rem */
        }
    </style>
    """,
    unsafe_allow_html=True
)
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem !important;
        }
        button[kind="secondary"] {
            background-color: #f44336 !important;
            color: white !important;
            border-radius: 6px !important;
        }
    </style>
""", unsafe_allow_html=True)

st.set_page_config(page_title="Stock Strategy Dashboard", layout="wide")

# ====================================
# Load Config
# ====================================
with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

# ====================================
# Authenticator (v0.4.2 Compatible)
# ====================================
authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# ====================================
# Login Handling
# ====================================
login_result = authenticator.login(location='main')

# login_result may be None until the user submits
if login_result:
    name, authentication_status, username = login_result
    st.session_state['authentication_status'] = authentication_status
    st.session_state['name'] = name
    st.session_state['username'] = username
else:
    name = st.session_state.get('name')
    username = st.session_state.get('username')
    authentication_status = st.session_state.get('authentication_status')

# ====================================
# Auth Logic
# ====================================
if authentication_status:
    #authenticator.logout(location='main')
    #st.success(f"Welcome {name}! 👋")
    # ===== HEADER BAR LAYOUT =====
    header = st.container()
    with header:
        col1, col2 = st.columns([6, 1])
        with col1:
            st.title("📊 Stock Strategy Dashboard")
            #st.markdown("📊 Stock Strategy Dashboard")
        with col2:
            authenticator.logout(button_name="Logout", location="main")

    #st.title("📊 Stock Strategy Dashboard")
    # Helper: start date from period
    def get_start_date(period):
        today = datetime.today()
        return {
            "1 Month": today - timedelta(days=30),
            "3 Months": today - timedelta(days=90),
            "6 Months": today - timedelta(days=180),
            "3 Years": today - timedelta(days=3 * 365),
        }.get(period, today - timedelta(days=365))

    # Strategy simulation
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
                price = df['Close'].iloc[i].item()
                prev_price = df['Close'].iloc[i - 1].item()
                ema = df['EMA20'].iloc[i].item()
                prev_ema = df['EMA20'].iloc[i - 1].item()
                sma = df['SMA40'].iloc[i].item()
                prev_sma = df['SMA40'].iloc[i - 1].item()
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

            if position == 0 and price > ema and price > sma:
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
            final_price = df['Close'].iloc[-1].item()
            cash += position * final_price
            trade_log.append({
                "Date": str(df.index[-1].date()),
                "Action": "SELL (EOD)",
                "Price": round(final_price, 2),
                "Shares": int(position),
                "Portfolio Value": round(cash, 2)
            })
        summary = f"Initial: ${initial_capital:,.2f} → Final: ${cash:,.2f} → Profit: ${cash - initial_capital:,.2f} ({(cash / initial_capital - 1) * 100:.2f}%)"
        trade_df = pd.DataFrame(trade_log, columns=["Date", "Action", "Price", "Shares", "Portfolio Value"])

        # display the styled DataFrame (Streamlit supports Styler objects)
        #st.dataframe(styled, use_container_width=True)
        # Set Date as index
        trade_df.set_index("Date", inplace=True)

        return df, trade_df, trade_log, summary, cash

    # Chart function
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

            if action == "BUY":
                fig.add_trace(go.Scatter(
                    x=[date], y=[price], mode='markers',
                    marker=dict(symbol='triangle-up', color='green', size=12),
                    name='BUY',
                    showlegend=show_buy_legend,
                    hovertext=[hovertext]
                ))
                show_buy_legend = False
            elif action == "SELL":
                fig.add_trace(go.Scatter(
                    x=[date], y=[price], mode='markers',
                    marker=dict(symbol='triangle-down', color='red', size=12),
                    name='SELL',
                    showlegend=show_sell_legend,
                    hovertext=[hovertext]
                ))
                show_sell_legend = False

        fig.update_layout(
            margin=dict(t=10, l=40, r=20, b=40),
            #title=f"{ticker} Strategy — Start: ${initial_capital:,.2f} → End: ${final_capital:,.2f}",
            xaxis_title="Date",
            yaxis_title="Price",
            height=600
        )

        return fig


    # ==============================
    # 📊 APP INTERFACE
    # ==============================
    # Replace your current ticker + period inputs with this
    col1, col2 = st.columns([1, 1])

    with col1:
        ticker = st.text_input("Enter Stock Ticker", value="TQQQ")

    with col2:
        period = st.selectbox("Select Time Period", ["1 Month", "3 Months", "6 Months", "1 Year", "3 Years"], index=3)

    #ticker = st.text_input("Enter Stock Ticker", value="TQQQ")
    #period = st.selectbox("Select Time Period", ["1 Month", "3 Months", "6 Months", "1 Year", "3 Years"], index=3)

    if ticker:
        try:
            df, trade_df, trade_log, summary, final_cash = simulate_strategy(ticker.upper(), period)
            st.markdown(f"**{summary}**")
            st.plotly_chart(generate_chart(df, trade_log, 5000, final_cash, ticker.upper()), use_container_width=True)
            trade_df['Price'] = trade_df['Price'].map('${:,.2f}'.format)
            trade_df['Portfolio Value'] = trade_df['Portfolio Value'].map('${:,.2f}'.format)


            # style only the Action column (bold + green for BUY, bold + red for SELL)
            def style_action(cell):
                cell_str = str(cell).strip().upper()
                if cell_str == "BUY":
                    return "color: green; font-weight: bold;"
                elif cell_str == "SELL":
                    return "color: red; font-weight: bold;"
                return ""


            # create a Styler and apply styling to the 'Action' column
            styled = trade_df.style.applymap(style_action, subset=['Action'])

            # optional: make the table use full width (works with the Styler's HTML)
            styled = styled.set_table_attributes('style="width:100%; border-collapse:collapse;"') \
                .set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]},
                                   {'selector': 'td', 'props': [('text-align', 'center')]}])
            st.dataframe(trade_df, use_container_width=True)
        except Exception as e:
            st.error(f"Error: {str(e)}")


elif authentication_status is False:
    st.error("Username or password is incorrect. Please try again.")
else:
    st.warning("Please enter your credentials.")

