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
from datetime import datetime

# Inject custom CSS to use Inter font
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

    h1 {
            font-size: 24px !important;
    }
    h2 {
            font-size: 20px !important;
    }
    h3 {
            font-size: 18px !important;
    }
    
    </style>
    """,
    unsafe_allow_html=True
)

# If modifying these SCOPES, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive.readonly', 'https://www.googleapis.com/auth/drive.file']

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
    """Read and compare stock price data from CSV files in the 'nsetestnow' folder."""
    try:
        service = build('drive', 'v3', credentials=creds)
        
        # Find the folder ID of 'nsetestnow'
        folder_query = "mimeType='application/vnd.google-apps.folder' and name='nsetestnow'"
        folder_results = service.files().list(q=folder_query, fields="files(id, name)").execute()
        folders = folder_results.get('files', [])
        
        if not folders:
            st.write("Folder 'nsetestnow' not found.")
            return
        
        nsetestnow_folder_id = folders[0]['id']
        
        # Find all CSV files in the 'nsetestnow' folder
        file_query = f"'{nsetestnow_folder_id}' in parents and mimeType='text/csv'"
        file_results = service.files().list(q=file_query, fields="files(id, name)").execute()
        files = file_results.get('files', [])
        
        if not files:
            st.write("No CSV files found in the 'nsetestnow' folder.")
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

def download_historical_data(symbol_file_path, output_folder_path, start_date, end_date):
    """Download historical data from Yahoo Finance without cleaning."""
    try:
        # Read the symbol file
        symbols = pd.read_csv(symbol_file_path, header=None).iloc[:, 0].tolist()
    except Exception as e:
        st.error(f"Error reading symbol file: {e}")
        return

    # Ensure the output folder exists
    if not os.path.exists(output_folder_path):
        os.makedirs(output_folder_path)

    # Download data for each symbol
    for symbol in symbols:
        try:
            st.write(f"Downloading data for {symbol}...")
            data = yf.download(symbol, start=start_date, end=end_date)

            # If no data is retrieved, skip saving
            if data.empty:
                st.warning(f"No data found for {symbol}. Skipping...")
                continue

            # Add Symbol column and reset index
            data['Symbol'] = symbol
            data.reset_index(inplace=True)

            # Rearrange columns
            data = data[['Symbol', 'Date', 'Open', 'High', 'Low', 'Close', 'Volume']]

            # Save to CSV (as-is, without cleaning)
            output_file = os.path.join(output_folder_path, f"{symbol}.csv")
            data.to_csv(output_file, index=False)
            st.success(f"Data for {symbol} saved to {output_file}")
        except Exception as e:
            st.error(f"Error downloading data for {symbol}: {e}")

def clean_and_upload_files(creds, output_folder_path):
    """Clean CSV files (remove first two rows) and upload them to Google Drive."""
    try:
        # Find the folder ID of 'nsetestnow'
        service = build('drive', 'v3', credentials=creds)
        folder_query = "mimeType='application/vnd.google-apps.folder' and name='nsetestnow'"
        folder_results = service.files().list(q=folder_query, fields="files(id, name)").execute()
        folders = folder_results.get('files', [])
        
        if not folders:
            st.error("Folder 'nsetestnow' not found.")
            return
        
        nsetestnow_folder_id = folders[0]['id']

        # Process each file in the output folder
        for file_name in os.listdir(output_folder_path):
            file_path = os.path.join(output_folder_path, file_name)
            
            # Read the CSV file
            try:
                df = pd.read_csv(file_path)
                
                # Remove the first two rows (index 0 and 1)
                if len(df) > 2:  # Check if there are at least 3 rows
                    df = df.drop([0, 1])  # Drop the first two rows
                elif len(df) > 1:  # If only 2 rows, drop both
                    df = df.drop([0, 1])
                else:  # If only 1 row, skip this file
                    st.warning(f"File {file_name} has only 1 row. Skipping...")
                    continue
                
                # Save the cleaned file back to the same path
                df.to_csv(file_path, index=False)
                st.success(f"Cleaned {file_name} (removed first two rows).")
                
                # Upload the cleaned file to Google Drive
                upload_file_to_drive(creds, file_path, file_name, folder_id=nsetestnow_folder_id)
            except Exception as e:
                st.error(f"Error processing {file_name}: {e}")
    except Exception as e:
        st.error(f"An error occurred: {e}")

def upload_file_to_drive(creds, file_path, file_name, folder_id=None):
    """Upload a file to Google Drive."""
    try:
        service = build('drive', 'v3', credentials=creds)
        
        # Define file metadata
        file_metadata = {
            'name': file_name,
        }
        if folder_id:
            file_metadata['parents'] = [folder_id]
        
        # Upload the file
        media = MediaFileUpload(file_path, resumable=True)
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        st.success(f"File uploaded successfully! File ID: {file.get('id')}")
    except Exception as e:
        st.error(f"An error occurred while uploading the file: {e}")

def data_storage_page(creds):
    """Data Storage page to download and store stock data."""
    st.title("📂 Data Storage")

    # Input fields for start and end dates
    st.write("### Enter Date Range")
    start_date = st.date_input("Start Date")
    end_date = st.date_input("End Date")

    # Path to the symbol file
    symbol_file_path = "fosymbols.csv"  # Replace with the path to your symbol file

    # Output folder path
    output_folder_path = "downloaded_data"
    if not os.path.exists(output_folder_path):
        os.makedirs(output_folder_path)

    # Download data (as-is)
    if st.button("Download Data"):
        download_historical_data(symbol_file_path, output_folder_path, start_date, end_date)

    # View downloaded data (raw)
    if st.button("View Downloaded Data"):
        if not os.path.exists(output_folder_path):
            st.warning("No data has been downloaded yet.")
        else:
            st.write("### Downloaded Data (Raw)")
            for file_name in os.listdir(output_folder_path):
                file_path = os.path.join(output_folder_path, file_name)
                try:
                    df = pd.read_csv(file_path)
                    st.write(f"#### File: {file_name}")
                    st.dataframe(df)  # Display the raw data in a table
                except Exception as e:
                    st.error(f"Error reading {file_name}: {e}")

    # Clean and upload files
    if st.button("Clean and Upload"):
        clean_and_upload_files(creds, output_folder_path)
        
def backtest_page():
    """Backtesting page to analyze stock data."""
    st.title("Backtesting Page")
    
    # Check if the CSV files and dataframes are available in session_state
    if 'csv_files' not in st.session_state or 'dataframes' not in st.session_state:
        st.warning("Please load data from the Google Drive Viewer first.")
        return
    
    # Retrieve the list of CSV files and dataframes from session_state
    csv_files = st.session_state['csv_files']
    dataframes = st.session_state['dataframes']
    
    # Add dropdowns to select two stocks
    st.header("Select Stocks")
    col1, col2 = st.columns(2)
    with col1:
        stock1 = st.selectbox("Select Stock 1", csv_files, key="stock1")
    with col2:
        stock2 = st.selectbox("Select Stock 2", csv_files, key="stock2")
    
    if stock1 == stock2:
        st.error("Please select two different stocks.")
        return
    
    # Retrieve the selected dataframes
    df1 = dataframes[stock1]
    df2 = dataframes[stock2]
    
    # Extract Date and Close columns
    try:
        df1 = df1[['Date', 'Close']]
        df2 = df2[['Date', 'Close']]
    except KeyError as e:
        st.error(f"Error extracting columns: {e}. Ensure the CSV files have 'Date' and 'Close' columns.")
        return
    
    # Merge the data on Date
    try:
        comparison_df = pd.merge(df1, df2, on='Date', how='outer', suffixes=('_1', '_2'))
    except Exception as e:
        st.error(f"Error merging DataFrames: {e}")
        return
    
    # Rename columns for clarity
    comparison_df.rename(columns={
        'Close_1': stock1,
        'Close_2': stock2
    }, inplace=True)
    
    # Calculate Ratio
    comparison_df['Ratio'] = comparison_df[stock1] / comparison_df[stock2]
    
    # Add input boxes for Z-Score lookback and RSI period
    st.header("Adjust Parameters")
    col1, col2 = st.columns(2)
    with col1:
        zscore_lookback = st.number_input("Z-Score Lookback Period (days)", min_value=1, value=50, key="zscore_lookback")
    with col2:
        rsi_period = st.number_input("RSI Period (days)", min_value=1, value=14, key="rsi_period")
    
    # Add RSI checkboxes
    st.subheader("RSI Settings")
    col1, col2 = st.columns(2)
    with col1:
        use_rsi_for_entry = st.checkbox("Use RSI for Entry", value=True, key="use_rsi_for_entry")
    with col2:
        use_rsi_for_exit = st.checkbox("Use RSI for Exit", value=True, key="use_rsi_for_exit")
    
    # Create two columns for long and short trade inputs
    st.subheader("Trade Parameters")
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Long Trade Parameters**")
        long_entry_zscore = st.number_input("Long Entry Z-Score", value=-2.5, key="long_entry_zscore")
        long_exit_zscore = st.number_input("Long Exit Z-Score", value=-1.5, key="long_exit_zscore")
        
        # Only show RSI parameters if RSI is enabled
        if use_rsi_for_entry:
            long_entry_rsi = st.slider("Long Entry RSI", 0, 100, 30, key="long_entry_rsi")
        else:
            long_entry_rsi = 0  # Default value, won't be used
            
        if use_rsi_for_exit:
            long_exit_rsi = st.slider("Long Exit RSI", 0, 100, 70, key="long_exit_rsi")
        else:
            long_exit_rsi = 100  # Default value, won't be used
    
    with col2:
        st.markdown("**Short Trade Parameters**")
        short_entry_zscore = st.number_input("Short Entry Z-Score", value=2.5, key="short_entry_zscore")
        short_exit_zscore = st.number_input("Short Exit Z-Score", value=1.5, key="short_exit_zscore")
        
        # Only show RSI parameters if RSI is enabled
        if use_rsi_for_entry:
            short_entry_rsi = st.slider("Short Entry RSI", 0, 100, 70, key="short_entry_rsi")
        else:
            short_entry_rsi = 100  # Default value, won't be used
            
        if use_rsi_for_exit:
            short_exit_rsi = st.slider("Short Exit RSI", 0, 100, 30, key="short_exit_rsi")
        else:
            short_exit_rsi = 0  # Default value, won't be used
    
    # Add stop loss parameters
    st.subheader("Stop Loss Parameters")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        max_days_in_trade = st.number_input("Max Days in Trade", min_value=1, value=12, key="max_days_in_trade")
    
    with col2:
        target_profit_pct = st.number_input("Target Profit (%)", min_value=0.0, value=5.0, step=0.1, key="target_profit_pct")
    
    with col3:
        stop_loss_pct = st.number_input("Stop Loss (%)", min_value=0.0, value=3.0, step=0.1, key="stop_loss_pct")
    
    # Add a "Go" button
    if st.button("Go"):
        # Calculate Z-Score of Ratio
        comparison_df['Z-Score'] = calculate_zscore(comparison_df['Ratio'], window=zscore_lookback)
        
        # Calculate RSI of Ratio
        comparison_df['RSI'] = calculate_rsi(comparison_df['Ratio'], window=rsi_period)
        
        # Convert Date column to datetime if it's not already
        if not pd.api.types.is_datetime64_any_dtype(comparison_df['Date']):
            comparison_df['Date'] = pd.to_datetime(comparison_df['Date'])
        
        # Sort by Date (oldest first) for proper trade simulation
        comparison_df = comparison_df.sort_values(by='Date', ascending=True)
        
        # Display the comparison table (most recent 300 rows)
        st.header("Stock Price Comparison (Last 300 Rows)")
        display_df = comparison_df.sort_values(by='Date', ascending=False).head(300)
        st.dataframe(display_df)
        
        # Calculate trade results
        trades = []
        in_long_trade = False
        in_short_trade = False
        long_entry_price = None
        long_entry_date = None
        long_entry_index = None
        short_entry_price = None
        short_entry_date = None
        short_entry_index = None
        
        for index, row in comparison_df.iterrows():
            current_date = row['Date']
            
            # Check for long trade exit conditions if in a long trade
            if in_long_trade:
                days_in_trade = (current_date - long_entry_date).days
                current_profit_pct = ((row['Ratio'] - long_entry_price) / long_entry_price) * 100
                
                # Check all exit conditions
                zscore_exit = row['Z-Score'] <= long_exit_zscore
                rsi_exit = use_rsi_for_exit and row['RSI'] >= long_exit_rsi
                time_exit = days_in_trade >= max_days_in_trade
                target_exit = current_profit_pct >= target_profit_pct
                stop_exit = current_profit_pct <= -stop_loss_pct
                
                if zscore_exit or rsi_exit or time_exit or target_exit or stop_exit:
                    # Determine exit reason
                    exit_reason = "Z-Score" if zscore_exit else "RSI" if rsi_exit else "Time" if time_exit else "Target" if target_exit else "Stop Loss"
                    
                    # Exit long trade
                    exit_price = row['Ratio']
                    exit_date = row['Date']
                    profit = exit_price - long_entry_price
                    profit_pct = (profit / long_entry_price) * 100
                    
                    trades.append({
                        'Entry Date': long_entry_date,
                        'Exit Date': exit_date,
                        'Days in Trade': days_in_trade,
                        'Entry Price': long_entry_price,
                        'Exit Price': exit_price,
                        'Profit': profit,
                        'Profit %': profit_pct,
                        'Type': 'Long',
                        'Exit Reason': exit_reason
                    })
                    
                    in_long_trade = False
                    long_entry_price = None
                    long_entry_date = None
                    long_entry_index = None
            
            # Check for short trade exit conditions if in a short trade
            if in_short_trade:
                days_in_trade = (current_date - short_entry_date).days
                current_profit_pct = ((short_entry_price - row['Ratio']) / short_entry_price) * 100
                
                # Check all exit conditions
                zscore_exit = row['Z-Score'] >= short_exit_zscore
                rsi_exit = use_rsi_for_exit and row['RSI'] <= short_exit_rsi
                time_exit = days_in_trade >= max_days_in_trade
                target_exit = current_profit_pct >= target_profit_pct
                stop_exit = current_profit_pct <= -stop_loss_pct
                
                if zscore_exit or rsi_exit or time_exit or target_exit or stop_exit:
                    # Determine exit reason
                    exit_reason = "Z-Score" if zscore_exit else "RSI" if rsi_exit else "Time" if time_exit else "Target" if target_exit else "Stop Loss"
                    
                    # Exit short trade
                    exit_price = row['Ratio']
                    exit_date = row['Date']
                    profit = short_entry_price - exit_price  # Profit calculation for short trades
                    profit_pct = (profit / short_entry_price) * 100
                    
                    trades.append({
                        'Entry Date': short_entry_date,
                        'Exit Date': exit_date,
                        'Days in Trade': days_in_trade,
                        'Entry Price': short_entry_price,
                        'Exit Price': exit_price,
                        'Profit': profit,
                        'Profit %': profit_pct,
                        'Type': 'Short',
                        'Exit Reason': exit_reason
                    })
                    
                    in_short_trade = False
                    short_entry_price = None
                    short_entry_date = None
                    short_entry_index = None
            
            # Check for new trade entries (only if not already in a trade)
            # Long trade logic
            if not in_long_trade and not in_short_trade:
                # Check Z-Score condition
                zscore_condition = row['Z-Score'] <= long_entry_zscore
                
                # Check RSI condition only if RSI is enabled for entry
                rsi_condition = not use_rsi_for_entry or row['RSI'] <= long_entry_rsi
                
                if zscore_condition and rsi_condition:
                    # Enter long trade
                    in_long_trade = True
                    long_entry_price = row['Ratio']
                    long_entry_date = row['Date']
                    long_entry_index = index
            
            # Short trade logic (only check if not in a trade)
            elif not in_long_trade and not in_short_trade:
                # Check Z-Score condition
                zscore_condition = row['Z-Score'] >= short_entry_zscore
                
                # Check RSI condition only if RSI is enabled for entry
                rsi_condition = not use_rsi_for_entry or row['RSI'] >= short_entry_rsi
                
                if zscore_condition and rsi_condition:
                    # Enter short trade
                    in_short_trade = True
                    short_entry_price = row['Ratio']
                    short_entry_date = row['Date']
                    short_entry_index = index
        
        # Close any open trades at the end of the data
        if in_long_trade:
            last_row = comparison_df.iloc[-1]
            days_in_trade = (last_row['Date'] - long_entry_date).days
            exit_price = last_row['Ratio']
            profit = exit_price - long_entry_price
            profit_pct = (profit / long_entry_price) * 100
            
            trades.append({
                'Entry Date': long_entry_date,
                'Exit Date': last_row['Date'],
                'Days in Trade': days_in_trade,
                'Entry Price': long_entry_price,
                'Exit Price': exit_price,
                'Profit': profit,
                'Profit %': profit_pct,
                'Type': 'Long',
                'Exit Reason': 'End of Data'
            })
        
        if in_short_trade:
            last_row = comparison_df.iloc[-1]
            days_in_trade = (last_row['Date'] - short_entry_date).days
            exit_price = last_row['Ratio']
            profit = short_entry_price - exit_price
            profit_pct = (profit / short_entry_price) * 100
            
            trades.append({
                'Entry Date': short_entry_date,
                'Exit Date': last_row['Date'],
                'Days in Trade': days_in_trade,
                'Entry Price': short_entry_price,
                'Exit Price': exit_price,
                'Profit': profit,
                'Profit %': profit_pct,
                'Type': 'Short',
                'Exit Reason': 'End of Data'
            })
        
        # Display trade results
        if trades:
            trades_df = pd.DataFrame(trades)
            st.header("Trade Results")
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
            
            # Calculate average profit percentage and average days in trade
            avg_profit_pct = trades_df['Profit %'].mean()
            avg_days_in_trade = trades_df['Days in Trade'].mean()
            
            # Count exit reasons
            exit_reasons = trades_df['Exit Reason'].value_counts()
            
            # Display trade summary
            st.header("Trade Summary")
            summary_data = {
                'Metric': [
                    'Total Trades', 'Win Rate (%)', 'Lose Rate (%)',
                    'Total Long Trades', 'Long Win Rate (%)', 'Long Lose Rate (%)',
                    'Total Short Trades', 'Short Win Rate (%)', 'Short Lose Rate (%)',
                    'Max Drawdown ($)', 'Profit Factor', 'Avg Profit (%)', 'Avg Days in Trade'
                ],
                'Value': [
                    total_trades, f"{win_rate:.2f}", f"{lose_rate:.2f}",
                    total_long_trades, f"{long_win_rate:.2f}", f"{long_lose_rate:.2f}",
                    total_short_trades, f"{short_win_rate:.2f}", f"{short_lose_rate:.2f}",
                    f"{max_drawdown:.2f}", f"{profit_factor:.2f}", f"{avg_profit_pct:.2f}", f"{avg_days_in_trade:.2f}"
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            st.dataframe(summary_df)
            
            # Display exit reason statistics
            st.subheader("Exit Reasons")
            exit_reasons_df = pd.DataFrame({
                'Exit Reason': exit_reasons.index,
                'Count': exit_reasons.values
            })
            st.dataframe(exit_reasons_df)
            
            # Display total profit
            st.success(f"Total Profit: {total_profit:.2f}")
            
            # Calculate and plot Equity Curve
            trades_df['Cumulative Profit'] = trades_df['Profit'].cumsum()
            st.header("Equity Curve")
            st.line_chart(trades_df.set_index('Exit Date')['Cumulative Profit'])
        else:
            st.warning("No trades executed based on the provided parameters.")
            
def logout():
    """Clear the session state and log out the user."""
    session_id = st.query_params.get('session_id', None)
    if session_id and session_id in st.session_state['tokens']:
        del st.session_state['tokens'][session_id]
    st.success("Logged out successfully!")

def main():
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Google Drive Viewer", "Backtesting Page", "Data Storage"])

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
    elif page == "Data Storage":
        creds = authenticate_google()
        if creds:
            data_storage_page(creds)

if __name__ == '__main__':
    main()
