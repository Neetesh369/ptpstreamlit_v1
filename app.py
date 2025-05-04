import streamlit as st
import os
import pandas as pd
import io
import numpy as np
import yfinance as yf
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import uuid

# Custom CSS for styling
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji";
    }
    .stHorizontalBlock {
        background: #fafafa;
        padding: 20px;
        border: 10px solid #eeeeee;
        border-radius: 20px;
    }
    h1 { font-size: 24px !important; }
    h2 { font-size: 20px !important; }
    h3 { font-size: 18px !important; }
    button.step-up { display: none; }
    button.step-down { display: none; }
    </style>
    """,
    unsafe_allow_html=True
)

# OAuth and Google Drive setup
SCOPES = ['https://www.googleapis.com/auth/drive.readonly', 'https://www.googleapis.com/auth/drive.file']
REDIRECT_URI = 'https://ptpapp-qjxrob2c9ydjxeroncdq9z.streamlit.app/'

if 'tokens' not in st.session_state:
    st.session_state['tokens'] = {}

def authenticate_google():
    """Google OAuth authentication."""
    session_id = st.query_params.get('session_id', None)
    if not session_id:
        st.error("Session ID not found. Please reload the page.")
        return None

    if session_id in st.session_state['tokens']:
        creds = Credentials.from_authorized_user_info(st.session_state['tokens'][session_id])
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            st.session_state['tokens'][session_id] = {
                'token': creds.token,
                'refresh_token': creds.refresh_token,
                'token_uri': creds.token_uri,
                'client_id': creds.client_id,
                'client_secret': creds.client_secret,
                'scopes': creds.scopes
            }
            return creds

    if not os.path.exists('credentials.json'):
        st.error("Error: 'credentials.json' file is missing.")
        return None

    flow = InstalledAppFlow.from_client_secrets_file(
        'credentials.json', SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, _ = flow.authorization_url(prompt='consent')
    st.write("Please authorize the application:")
    st.write(auth_url)

    query_params = st.query_params
    if 'code' in query_params:
        auth_code = query_params['code']
        flow.fetch_token(code=auth_code)
        creds = flow.credentials
        st.session_state['tokens'][session_id] = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes
        }
        st.success("Logged in successfully!")
        return creds
    else:
        st.warning("Waiting for authorization...")
        return None

def calculate_zscore(series, window=50):
    """Calculate Z-Score with rolling window."""
    rolling_mean = series.rolling(window=window).mean()
    rolling_std = series.rolling(window=window).std()
    return (series - rolling_mean) / rolling_std

def calculate_rsi(series, window=14):
    """Calculate RSI with rolling window."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def backtest_page():
    """Updated backtesting page with Z-Score sign enforcement."""
    st.title("Backtesting Page")
    
    if 'csv_files' not in st.session_state or 'dataframes' not in st.session_state:
        st.warning("Please load data from Google Drive first.")
        return
    
    csv_files = st.session_state['csv_files']
    dataframes = st.session_state['dataframes']
    
    st.header("Select Stocks")
    col1, col2 = st.columns(2)
    with col1:
        stock1 = st.selectbox("Select Stock 1", csv_files, key="stock1")
    with col2:
        stock2 = st.selectbox("Select Stock 2", csv_files, key="stock2")
    
    if stock1 == stock2:
        st.error("Please select two different stocks.")
        return
    
    try:
        df1 = dataframes[stock1][['Date', 'Close']]
        df2 = dataframes[stock2][['Date', 'Close']]
        comparison_df = pd.merge(df1, df2, on='Date', how='outer', suffixes=('_1', '_2'))
        comparison_df.rename(columns={
            'Close_1': stock1,
            'Close_2': stock2
        }, inplace=True)
        comparison_df['Ratio'] = comparison_df[stock1] / comparison_df[stock2]
    except Exception as e:
        st.error(f"Error processing data: {e}")
        return

    st.header("Adjust Parameters")
    zscore_lookback = st.number_input("Z-Score Lookback Period", min_value=1, value=50)
    rsi_period = st.number_input("RSI Period", min_value=1, value=14)

    st.subheader("Trade Parameters")
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Long Trade Parameters**")
        # Long Entry (must be ≤ 0)
        long_entry_col = st.columns([1, 2, 1])
        with long_entry_col[0]:
            if st.button("−", key="long_entry_dec"):
                st.session_state.long_entry_zscore = max(st.session_state.get('long_entry_zscore', -1.0) - 0.1, -3.0)
        with long_entry_col[1]:
            long_entry_zscore = st.number_input(
                "Entry Z-Score (≤ 0)",
                value=-1.0,
                max_value=0.0,
                key="long_entry_zscore"
            )
        with long_entry_col[2]:
            if st.button("+", key="long_entry_inc"):
                st.session_state.long_entry_zscore = min(st.session_state.get('long_entry_zscore', -1.0) + 0.1, 0.0)
        
        # Long Exit (must be ≥ 0)
        long_exit_col = st.columns([1, 2, 1])
        with long_exit_col[0]:
            if st.button("−", key="long_exit_dec"):
                st.session_state.long_exit_zscore = max(st.session_state.get('long_exit_zscore', 0.0) - 0.1, 0.0)
        with long_exit_col[1]:
            long_exit_zscore = st.number_input(
                "Exit Z-Score (≥ 0)",
                value=0.0,
                min_value=0.0,
                key="long_exit_zscore"
            )
        with long_exit_col[2]:
            if st.button("+", key="long_exit_inc"):
                st.session_state.long_exit_zscore = min(st.session_state.get('long_exit_zscore', 0.0) + 0.1, 3.0)
        
        long_entry_rsi = st.slider("Entry RSI (≤)", 0, 100, 30)
        long_exit_rsi = st.slider("Exit RSI (≥)", 0, 100, 70)
    
    with col2:
        st.markdown("**Short Trade Parameters**")
        # Short Entry (must be ≥ 0)
        short_entry_col = st.columns([1, 2, 1])
        with short_entry_col[0]:
            if st.button("−", key="short_entry_dec"):
                st.session_state.short_entry_zscore = max(st.session_state.get('short_entry_zscore', 1.0) - 0.1, 0.0)
        with short_entry_col[1]:
            short_entry_zscore = st.number_input(
                "Entry Z-Score (≥ 0)",
                value=1.0,
                min_value=0.0,
                key="short_entry_zscore"
            )
        with short_entry_col[2]:
            if st.button("+", key="short_entry_inc"):
                st.session_state.short_entry_zscore = min(st.session_state.get('short_entry_zscore', 1.0) + 0.1, 3.0)
        
        # Short Exit (must be ≤ 0)
        short_exit_col = st.columns([1, 2, 1])
        with short_exit_col[0]:
            if st.button("−", key="short_exit_dec"):
                st.session_state.short_exit_zscore = max(st.session_state.get('short_exit_zscore', 0.0) - 0.1, -3.0)
        with short_exit_col[1]:
            short_exit_zscore = st.number_input(
                "Exit Z-Score (≤ 0)",
                value=0.0,
                max_value=0.0,
                key="short_exit_zscore"
            )
        with short_exit_col[2]:
            if st.button("+", key="short_exit_inc"):
                st.session_state.short_exit_zscore = min(st.session_state.get('short_exit_zscore', 0.0) + 0.1, 0.0)
        
        short_entry_rsi = st.slider("Entry RSI (≥)", 0, 100, 70)
        short_exit_rsi = st.slider("Exit RSI (≤)", 0, 100, 30)

    if st.button("Run Backtest"):
        comparison_df['Z-Score'] = calculate_zscore(comparison_df['Ratio'], zscore_lookback)
        comparison_df['RSI'] = calculate_rsi(comparison_df['Ratio'], rsi_period)
        comparison_df = comparison_df.sort_values('Date', ascending=False).head(300)
        
        trades = []
        in_long = in_short = False
        long_entry_price = short_entry_price = None
        
        for _, row in comparison_df.iterrows():
            # Long trade logic
            if not in_long and row['Z-Score'] <= long_entry_zscore and row['RSI'] <= long_entry_rsi:
                in_long, long_entry_price = True, row['Ratio']
            elif in_long and (row['Z-Score'] >= long_exit_zscore or row['RSI'] >= long_exit_rsi):
                trades.append({
                    'Type': 'Long',
                    'Entry': long_entry_price,
                    'Exit': row['Ratio'],
                    'Profit': row['Ratio'] - long_entry_price,
                    'Entry Date': row['Date'],
                    'Exit Date': row['Date']
                })
                in_long = False
            
            # Short trade logic
            if not in_short and row['Z-Score'] >= short_entry_zscore and row['RSI'] >= short_entry_rsi:
                in_short, short_entry_price = True, row['Ratio']
            elif in_short and (row['Z-Score'] <= short_exit_zscore or row['RSI'] <= short_exit_rsi):
                trades.append({
                    'Type': 'Short',
                    'Entry': short_entry_price,
                    'Exit': row['Ratio'],
                    'Profit': short_entry_price - row['Ratio'],
                    'Entry Date': row['Date'],
                    'Exit Date': row['Date']
                })
                in_short = False
        
        if trades:
            trades_df = pd.DataFrame(trades)
            st.success(f"Backtest complete! {len(trades_df)} trades executed.")
            st.dataframe(trades_df)
            
            # Calculate performance metrics
            total_profit = trades_df['Profit'].sum()
            st.metric("Total Profit", f"${total_profit:.2f}")
            
            # Plot equity curve
            trades_df['Cumulative'] = trades_df['Profit'].cumsum()
            st.line_chart(trades_df.set_index('Exit Date')['Cumulative'])
        else:
            st.warning("No trades were executed with current parameters.")

# [Rest of the original functions (list_google_drive_folders, data_storage_page, etc.) remain unchanged]

def main():
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Google Drive Viewer", "Backtesting Page", "Data Storage"])
    
    session_id = st.query_params.get('session_id') or str(uuid.uuid4())
    st.query_params['session_id'] = session_id

    if page == "Google Drive Viewer":
        st.title("Google Drive Viewer")
        if st.button("Login"):
            creds = authenticate_google()
            if creds:
                list_google_drive_folders(creds)
    elif page == "Backtesting Page":
        backtest_page()
    elif page == "Data Storage":
        creds = authenticate_google()
        if creds:
            data_storage_page(creds)

if __name__ == '__main__':
    main()
