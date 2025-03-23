import streamlit as st
import os
import pandas as pd
import io
import numpy as np
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import uuid

# If modifying these SCOPES, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# Define the redirect URI (must match the one in Google Cloud Console)
REDIRECT_URI = 'https://ptpapp-qjxrob2c9ydjxeroncdq9z.streamlit.app/'

# Dictionary to store tokens per session
if 'tokens' not in st.session_state:
    st.session_state['tokens'] = {}

def authenticate_google():
    """Authenticate the user using Google OAuth and return credentials."""
    # Get the session ID (unique for each user)
    session_id = st.query_params.get('session_id', None)
    if not session_id:
        st.error("Session ID not found. Please reload the page.")
        return None

    # Check if tokens exist for this session
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

    # If no valid tokens, start the OAuth flow
    if not os.path.exists('credentials.json'):
        st.error("Error: 'credentials.json' file is missing. Please set up Google OAuth credentials.")
        return None

    flow = InstalledAppFlow.from_client_secrets_file(
        'credentials.json', SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, _ = flow.authorization_url(prompt='consent')
    st.write("Please go to the following URL to authorize the application:")
    st.write(auth_url)
    st.write("After authorization, you will be redirected back to this app.")

    # Check if the authorization code is in the URL
    query_params = st.query_params
    if 'code' in query_params:
        auth_code = query_params['code']
        flow.fetch_token(code=auth_code)
        creds = flow.credentials
        # Store tokens in session state
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
        st.warning("Waiting for authorization code...")
        return None

def calculate_zscore(series, window=50):
    """Calculate the Z-score for a given series using a rolling window."""
    rolling_mean = series.rolling(window=window).mean()
    rolling_std = series.rolling(window=window).std()
    zscore = (series - rolling_mean) / rolling_std
    return zscore

def calculate_rsi(series, window=14):
    """Calculate the Relative Strength Index (RSI) for a given series using a rolling window."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def list_google_drive_folders(creds):
    """Read and compare stock price data from CSV files in the 'nsetest' folder."""
    try:
        service = build('drive', 'v3', credentials=creds)
        
        # Find the folder ID of 'nsetest'
        folder_query = "mimeType='application/vnd.google-apps.folder' and name='nsetest'"
        folder_results = service.files().list(q=folder_query, fields="files(id, name)").execute()
        folders = folder_results.get('files', [])
        
        if not folders:
            st.write("Folder 'nsetest' not found.")
            return
        
        nsetest_folder_id = folders[0]['id']
        
        # Find all CSV files in the 'nsetest' folder
        file_query = f"'{nsetest_folder_id}' in parents and mimeType='text/csv'"
        file_results = service.files().list(q=file_query, fields="files(id, name)").execute()
        files = file_results.get('files', [])
        
        if not files:
            st.write("No CSV files found in the 'nsetest' folder.")
            return
        
        # Store the list of CSV files in session_state
        st.session_state['csv_files'] = [file['name'] for file in files]
        
        # Download and read the CSV files
        dataframes = {}
        for file in files:
            try:
                file_id = file['id']
                request = service.files().get_media(fileId=file_id)
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                fh.seek(0)
                
                # Read the CSV file with explicit delimiter and error handling
                df = pd.read_csv(fh, delimiter=',', encoding='utf-8')
                dataframes[file['name']] = df
                st.write(f"Debug: Successfully read {file['name']} with {len(df)} rows.")
            except Exception as e:
                st.error(f"Error reading {file['name']}: {e}")
                return
        
        # Store the dataframes in session_state
        st.session_state['dataframes'] = dataframes
        
    except Exception as e:
        st.error(f"An error occurred: {e}")

def backtest_page():
    """Backtesting page to analyze stock data."""
    st.title("📈 Backtesting Page")
    
    # Check if the CSV files and dataframes are available in session_state
    if 'csv_files' not in st.session_state or 'dataframes' not in st.session_state:
        st.warning("⚠️ Please load data from the Google Drive Viewer first.")
        return
    
    # Retrieve the list of CSV files and dataframes from session_state
    csv_files = st.session_state['csv_files']
    dataframes = st.session_state['dataframes']
    
    # Add dropdowns to select two stocks
    st.header("📊 Select Stocks")
    col1, col2 = st.columns(2)
    with col1:
        stock1 = st.selectbox("Select Stock 1", csv_files, key="stock1")
    with col2:
        stock2 = st.selectbox("Select Stock 2", csv_files, key="stock2")
    
    if stock1 == stock2:
        st.error("❌ Please select two different stocks.")
        return
    
    # Retrieve the selected dataframes
    df1 = dataframes[stock1]
    df2 = dataframes[stock2]
    
    # Extract Date and Close columns
    try:
        df1 = df1[['Date', 'Close']]
        df2 = df2[['Date', 'Close']]
    except KeyError as e:
        st.error(f"❌ Error extracting columns: {e}. Ensure the CSV files have 'Date' and 'Close' columns.")
        return
    
    # Merge the data on Date
    try:
        comparison_df = pd.merge(df1, df2, on='Date', how='outer', suffixes=('_1', '_2'))
    except Exception as e:
        st.error(f"❌ Error merging DataFrames: {e}")
        return
    
    # Rename columns for clarity
    comparison_df.rename(columns={
        'Close_1': stock1,
        'Close_2': stock2
    }, inplace=True)
    
    # Calculate Ratio
    comparison_df['Ratio'] = comparison_df[stock1] / comparison_df[stock2]
    
    # Add input boxes for Z-Score lookback and RSI period
    st.header("⚙️ Adjust Parameters")
    col1, col2 = st.columns(2)
    with col1:
        zscore_lookback = st.number_input("Z-Score Lookback Period (days)", min_value=1, value=50, key="zscore_lookback")
    with col2:
        rsi_period = st.number_input("RSI Period (days)", min_value=1, value=14, key="rsi_period")
    
    # Create two columns for long and short trade inputs
    st.subheader("🎯 Trade Parameters")
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**📈 Long Trade Parameters**")
        long_entry_zscore = st.number_input("Long Entry Z-Score", value=1.0, key="long_entry_zscore")
        long_exit_zscore = st.number_input("Long Exit Z-Score", value=0.0, key="long_exit_zscore")
        long_entry_rsi = st.slider("Long Entry RSI", 0, 100, 30, key="long_entry_rsi")
        long_exit_rsi = st.slider("Long Exit RSI", 0, 100, 70, key="long_exit_rsi")
    
    with col2:
        st.markdown("**📉 Short Trade Parameters**")
        short_entry_zscore = st.number_input("Short Entry Z-Score", value=-1.0, key="short_entry_zscore")
        short_exit_zscore = st.number_input("Short Exit Z-Score", value=0.0, key="short_exit_zscore")
        short_entry_rsi = st.slider("Short Entry RSI", 0, 100, 70, key="short_entry_rsi")
        short_exit_rsi = st.slider("Short Exit RSI", 0, 100, 30, key="short_exit_rsi")
    
    # Add a "Go" button
    if st.button("🚀 Go"):
        # Calculate Z-Score of Ratio
        comparison_df['Z-Score'] = calculate_zscore(comparison_df['Ratio'], window=zscore_lookback)
        
        # Calculate RSI of Ratio
        comparison_df['RSI'] = calculate_rsi(comparison_df['Ratio'], window=rsi_period)
        
        # Sort by Date (most recent first) and limit to 300 rows
        comparison_df = comparison_df.sort_values(by='Date', ascending=False).head(300)
        
        # Display the comparison table
        st.header("📊 Stock Price Comparison (Last 300 Rows)")
        st.dataframe(comparison_df)
        
        # Calculate trade results
        trades = []
        in_long_trade = False
        in_short_trade = False
        long_entry_price = None
        long_entry_date = None
        short_entry_price = None
        short_entry_date = None
        
        for index, row in comparison_df.iterrows():
            # Long trade logic
            if not in_long_trade and row['Z-Score'] >= long_entry_zscore and row['RSI'] <= long_entry_rsi:
                # Enter long trade
                in_long_trade = True
                long_entry_price = row['Ratio']
                long_entry_date = row['Date']
            elif in_long_trade and (row['Z-Score'] <= long_exit_zscore or row['RSI'] >= long_exit_rsi):
                # Exit long trade
                exit_price = row['Ratio']
                exit_date = row['Date']
                profit = exit_price - long_entry_price
                trades.append({
                    'Entry Date': long_entry_date,
                    'Exit Date': exit_date,
                    'Entry Price': long_entry_price,
                    'Exit Price': exit_price,
                    'Profit': profit,
                    'Type': 'Long'
                })
                in_long_trade = False
                long_entry_price = None
                long_entry_date = None
            
            # Short trade logic
            if not in_short_trade and row['Z-Score'] <= short_entry_zscore and row['RSI'] >= short_entry_rsi:
                # Enter short trade
                in_short_trade = True
                short_entry_price = row['Ratio']
                short_entry_date = row['Date']
            elif in_short_trade and (row['Z-Score'] >= short_exit_zscore or row['RSI'] <= short_exit_rsi):
                # Exit short trade
                exit_price = row['Ratio']
                exit_date = row['Date']
                profit = short_entry_price - exit_price  # Profit calculation for short trades
                trades.append({
                    'Entry Date': short_entry_date,
                    'Exit Date': exit_date,
                    'Entry Price': short_entry_price,
                    'Exit Price': exit_price,
                    'Profit': profit,
                    'Type': 'Short'
                })
                in_short_trade = False
                short_entry_price = None
                short_entry_date = None
        
        # Display trade results
        if trades:
            trades_df = pd.DataFrame(trades)
            st.header("📊 Trade Results")
            st.dataframe(trades_df)
            
            # Calculate trade summary metrics
            total_trades = len(trades_df)
            winning_trades = trades_df[trades_df['Profit'] > 0]
            losing_trades = trades_df[trades_df['Profit'] <= 0]
            win_rate = (len(winning_trades) / total_trades) * 100
            lose_rate = (len(losing_trades) / total_trades) * 100
            
            long_trades = trades_df[trades_df['Type'] == 'Long']
            total_long_trades = len(long_trades)
            long_winning_trades = long_trades[long_trades['Profit'] > 0]
            long_win_rate = (len(long_winning_trades) / total_long_trades) * 100 if total_long_trades > 0 else 0
            long_lose_rate = 100 - long_win_rate
            
            short_trades = trades_df[trades_df['Type'] == 'Short']
            total_short_trades = len(short_trades)
            short_winning_trades = short_trades[short_trades['Profit'] > 0]
            short_win_rate = (len(short_winning_trades) / total_short_trades) * 100 if total_short_trades > 0 else 0
            short_lose_rate = 100 - short_win_rate
            
            max_drawdown = trades_df['Profit'].cumsum().min()
            total_profit = trades_df['Profit'].sum()
            total_loss = abs(trades_df[trades_df['Profit'] <= 0]['Profit'].sum())
            profit_factor = total_profit / total_loss if total_loss > 0 else 0
            
            # Display trade summary
            st.header("📊 Trade Summary")
            summary_data = {
                'Metric': [
                    'Total Trades', 'Win Rate (%)', 'Lose Rate (%)',
                    'Total Long Trades', 'Long Win Rate (%)', 'Long Lose Rate (%)',
                    'Total Short Trades', 'Short Win Rate (%)', 'Short Lose Rate (%)',
                    'Max Drawdown ($)', 'Profit Factor'
                ],
                'Value': [
                    total_trades, f"{win_rate:.2f}", f"{lose_rate:.2f}",
                    total_long_trades, f"{long_win_rate:.2f}", f"{long_lose_rate:.2f}",
                    total_short_trades, f"{short_win_rate:.2f}", f"{short_lose_rate:.2f}",
                    f"{max_drawdown:.2f}", f"{profit_factor:.2f}"
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            st.dataframe(summary_df)
            
            # Display total profit
            st.success(f"💰 **Total Profit:** {total_profit:.2f}")
            
            # Calculate and plot Equity Curve
            trades_df['Cumulative Profit'] = trades_df['Profit'].cumsum()
            st.header("📈 Equity Curve")
            st.line_chart(trades_df.set_index('Exit Date')['Cumulative Profit'])
        else:
            st.warning("⚠️ No trades executed based on the provided Z-Score and RSI values.")
            
def logout():
    """Clear the session state and log out the user."""
    session_id = st.query_params.get('session_id', None)
    if session_id and session_id in st.session_state['tokens']:
        del st.session_state['tokens'][session_id]
    st.success("Logged out successfully!")

def main():
    # Apply custom CSS styling from app-reference.py
    st.markdown(
        """
        <style>
        /* Use theme-based background color for the main container */
        .st-emotion-cache-bm2z3a {
            background-color: var(--background-color);
            color: var(--text-color);
        }

        .logo {
            width: 46px; /* Default size for desktop */
            height: 46px;
            margin-bottom: 2px; /* Spacing between logo and title */
        }

        /* Adjust logo size for smaller screens */
        @media (max-width: 768px) {
            .logo {
                width: 32px; /* Smaller size for tablets */
                height: 32px;
            }
        }

        /* Adjust logo size for mobile devices */
        @media (max-width: 480px) {
            .logo {
                width: 26px; /* Smallest size for mobile */
                height: 26px;
            }
        }

        .stHorizontalBlock {
            background-color: black; /* Set background color to black */
            border-radius: 20px; /* Adjust the border-radius for rounded edges */
            padding: 10px 20px 20px 20px;
        }

        .pretty-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0 10px; /* Adjust spacing between rows */
            font-size: 0.9em;
            font-family: "Source Sans Pro", sans-serif;
            min-width: 400px;
            overflow: hidden;
            text-align: center;
            border: none;
            color: var(--text-color);
        }

        /* Black background with curved edges for each row */
        .pretty-table tbody tr {
            background-color: #161616; /* Set background color to black */
            border-radius: 20px; /* Adjust the border-radius for rounded edges */
            margin-bottom: 10px;
        }

        .pretty-table th:first-child {
            border-top-left-radius: 30px; /* Adjust the border-radius for the first cell */
            border-bottom-left-radius: 30px;
        }

        .pretty-table th:last-child {
            border-top-right-radius: 30px; /* Adjust the border-radius for the first cell */
            border-bottom-right-radius: 30px;
        }

        .pretty-table th{
            background-color: #000; /* Set background color to black */
            color: #fff !important; /* Set background color to black */
            padding: 6px 9px;
            text-align: center;
            border: 2px solid #282828 !important; 
        } 

        /* Padding for table cells */
        .pretty-table td {
            padding: 5px 8px;
            text-align: center;
            border: none;
            border-top: 5px solid #282828 !important;
        }

        /* Add curved edges to the first and last cells in each row */
        .pretty-table tbody tr td:first-child {
            border-top-left-radius: 20px; /* Adjust the border-radius for the first cell */
            border-bottom-left-radius: 20px;
        }

        .pretty-table tbody tr td:last-child {
            border-top-right-radius: 20px; /* Adjust the border-radius for the last cell */
            border-bottom-right-radius: 20px;
        }

        /* Hover effect for rows */
        .pretty-table tbody tr:hover {
            background-color: #000000; /* Darker shade for hover effect */
        }

        /* Ensure the text above the table is white */
        h1, p {
            color: var(--text-color) !important;
        }

        /* Grid container for metric boxes */
        .grid-container {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            justify-content: center;
            align-items: center;
        }

        @media (max-width: 600px) {
            .grid-container { grid-template-columns: repeat(2, 1fr); gap: 5px; }
        }

        /* Styling for the "Add Stock" button */
        .stButton button {
            background-color: var(--primary-color);
            color: var(--text-color);
            border-radius: 5px;
            padding: 10px 20px;
            font-size: 16px;
            font-weight: bold;
            border: none;
            transition: background-color 0.3s ease;
        }

        .stButton button:hover {
            background-color: var(--primary-hover-color);
        }

        /* Custom CSS for the Company Name cell */
        .company-name-cell {
            text-align: center;
        }

        .company-name-cell small {
            background-color: #313131;
            border-radius: 4px;
            padding: 2px 6px;
            color: var(--text-color);
            display: inline-block;
            margin-top: 4px;
        }

        /* Custom CSS for the Trade Signal cell */
        .trade-signal-buy {
            background-color: #6eb330;
            border-radius: 10px;
            padding: 10px;
            color: var(--text-color);
        }

        .trade-signal-sell {
            background-color: #db503a;
            border-radius: 10px;
            padding: 10px;
            color: var(--text-color);
        }

        /* First grid box with line chart icon */
        .metric-box {
            background: linear-gradient(15deg, #000000, #1b1b1b);
            padding: 20px;
            border-radius: 10px;
            text-align: left;
            color: var(--text-color);
            font-size: 18px;
            font-weight: bold;
            border: 1px solid var(--border-color);
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            position: relative;
            overflow: hidden;
        }

        .metric-box::before {
            content: "";
            background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50" viewBox="0 0 24 24" fill="none" stroke="%23ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20V10M18 20V4M6 20v-4"/></svg>');
            background-size: 40px 40px;
            background-position: left top;
            background-repeat: no-repeat;
            opacity: 0.3;
            position: absolute;
            top: 20px;
            left: 20px;
            width: 40px;
            height: 40px;
            z-index: 1;
        }

        .metric-box h2 {
            margin-top: 30px;
            margin-left: 5px;
            margin-bottom: 1px;
        }

        .metric-box p {
            margin-left: 5px;
            margin-bottom: 0;
        }

        /* Second grid box with pile of cash icon */
        .metric-box-gain {
            background: linear-gradient(15deg, #000000, #1b1b1b);
            padding: 20px;
            border-radius: 10px;
            text-align: left;
            color: var(--text-color);
            font-size: 18px;
            font-weight: bold;
            border: 1px solid var(--border-color);
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            position: relative;
            overflow: hidden;
        }

        .metric-box-gain::before {
            content: "";
            background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50" viewBox="0 0 24 24" fill="none" stroke="%23ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 1 0 0 7h5a3.5 3.5 0 1 1 0 7H6"/></svg>');
            background-size: 40px 40px;
            background-position: left top;
            background-repeat: no-repeat;
            opacity: 0.3;
            position: absolute;
            top: 20px;
            left: 20px;
            width: 40px;
            height: 40px;
            z-index: 1;
        }

        .metric-box-gain h2 {
            margin-top: 30px;
            margin-left: 5px;
            margin-bottom: 1px;
        }

        .metric-box-gain p {
            margin-left: 5px;
            margin-bottom: 0;
        }

        /* Third grid box with speedometer gauge icon */
        .metric-box-speedometer {
            background: linear-gradient(15deg, #000000, #1b1b1b);
            padding: 20px;
            border-radius: 10px;
            text-align: left;
            color: var(--text-color);
            font-size: 18px;
            font-weight: bold;
            border: 1px solid var(--border-color);
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            position: relative;
            overflow: hidden;
        }

        .metric-box-speedometer::before {
            content: "";
            background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50" viewBox="0 0 24 24" fill="none" stroke="%23ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10zM12 6v6l4 2"/></svg>');
            background-size: 40px 40px;
            background-position: left top;
            background-repeat: no-repeat;
            opacity: 0.3;
            position: absolute;
            top: 20px;
            left: 20px;
            width: 40px;
            height: 40px;
            z-index: 1;
        }

        .metric-box-speedometer h2 {
            margin-top: 30px;
            margin-left: 5px;
            margin-bottom: 1px;
        }

        .metric-box-speedometer p {
            margin-left: 5px;
            margin-bottom: 0;
        }

        /* Fourth grid box with dartboard and arrow icon */
        .metric-box-accuracy {
            background: linear-gradient(15deg, #000000, #1b1b1b);
            padding: 20px;
            border-radius: 10px;
            text-align: left;
            color: var(--text-color);
            font-size: 18px;
            font-weight: bold;
            border: 1px solid var(--border-color);
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            position: relative;
            overflow: hidden;
        }

        .metric-box-accuracy::before {
            content: "";
            background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50" viewBox="0 0 24 24" fill="none" stroke="%23ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M16 8l-4 4-4-4"/></svg>');
            background-size: 40px 40px;
            background-position: left top;
            background-repeat: no-repeat;
            opacity: 0.3;
            position: absolute;
            top: 20px;
            left: 20px;
            width: 40px;
            height: 40px;
            z-index: 1;
        }

        .metric-box-accuracy h2 {
            margin-top: 30px;
            margin-left: 5px;
            margin-bottom: 1px;
        }

        .metric-box-accuracy p {
            margin-left: 5px;
            margin-bottom: 0;
        }

        /* Custom CSS for aligning titles to the left */
        .left-align {
            text-align: left;
            display: flex;
            align-items: center;
        }

        .left-align svg {
            margin-right: 10px;
        }
        
        .st-b1 {
            background-color: #000;
        }

        .st-bt {
            background-color: #fff;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Google Drive Viewer", "Backtesting Page"])

    # Generate a unique session ID
    session_id = st.query_params.get('session_id', None)
    if not session_id:
        session_id = str(uuid.uuid4())
        st.query_params['session_id'] = session_id

    if page == "Google Drive Viewer":
        st.title("Google Drive Folder Viewer")
        if st.button("Login with Google"):
            creds = authenticate_google()
            if creds:
                list_google_drive_folders(creds)
        if st.button("Logout"):
            logout()
    elif page == "Backtesting Page":
        backtest_page()

if __name__ == '__main__':
    main()
