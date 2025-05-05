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
    """Clean CSV files (remove first row) and upload them to Google Drive."""
    try:
        # Find the folder ID of 'nsetest'
        service = build('drive', 'v3', credentials=creds)
        folder_query = "mimeType='application/vnd.google-apps.folder' and name='nsetest'"
        folder_results = service.files().list(q=folder_query, fields="files(id, name)").execute()
        folders = folder_results.get('files', [])
        
        if not folders:
            st.error("Folder 'nsetest' not found.")
            return
        
        nsetest_folder_id = folders[0]['id']

        # Process each file in the output folder
        for file_name in os.listdir(output_folder_path):
            file_path = os.path.join(output_folder_path, file_name)
            
            # Read the CSV file
            try:
                df = pd.read_csv(file_path)
                
                # Remove the first row (index 0)
                if len(df) > 1:  # Check if there are at least 2 rows
                    df = df.drop(0)  # Drop the first row
                else:  # If only 1 row, skip this file
                    st.warning(f"File {file_name} has only 1 row. Skipping...")
                    continue
                
                # Save the cleaned file back to the same path
                df.to_csv(file_path, index=False)
                st.success(f"Cleaned {file_name} (removed first row).")
                
                # Upload the cleaned file to Google Drive
                upload_file_to_drive(creds, file_path, file_name, folder_id=nsetest_folder_id)
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
    """Backtesting page with strict Z-Score sign enforcement."""
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
        
        # Initialize session state with proper defaults
        if 'long_entry_zscore' not in st.session_state:
            st.session_state.long_entry_zscore = -2.5
        if 'long_exit_zscore' not in st.session_state:
            st.session_state.long_exit_zscore = 0.0
        
        # Long Entry Z-Score (must be ≤ 0)
        st.write("Entry Z-Score (≤ 0)")
        entry_col = st.columns([1, 4, 1])
        with entry_col[0]:
            if st.button("−", key="long_entry_dec"):
                st.session_state.long_entry_zscore -= 0.1
        with entry_col[1]:
            st.text_input(
                "Current Value",
                value=f"{st.session_state.long_entry_zscore:.1f}",
                key="long_entry_display",
                disabled=True,
                label_visibility="collapsed"
            )
        with entry_col[2]:
            if st.button("+", key="long_entry_inc"):
                st.session_state.long_entry_zscore = min(st.session_state.long_entry_zscore + 0.1, 0.0)
        
        # Long Exit Z-Score (must be ≥ 0)
        st.write("Exit Z-Score (≥ 0)")
        exit_col = st.columns([1, 4, 1])
        with exit_col[0]:
            if st.button("−", key="long_exit_dec"):
                st.session_state.long_exit_zscore = max(st.session_state.long_exit_zscore - 0.1, 0.0)
        with exit_col[1]:
            st.text_input(
                "Current Value",
                value=f"{st.session_state.long_exit_zscore:.1f}",
                key="long_exit_display",
                disabled=True,
                label_visibility="collapsed"
            )
        with exit_col[2]:
            if st.button("+", key="long_exit_inc"):
                st.session_state.long_exit_zscore += 0.1
        
        # RSI parameters
        long_entry_rsi = st.slider("Entry RSI (≤)", 0, 100, 30, key="long_entry_rsi")
        long_exit_rsi = st.slider("Exit RSI (≥)", 0, 100, 70, key="long_exit_rsi")
    
    with col2:
        st.markdown("**Short Trade Parameters**")
        
        # Initialize session state with proper defaults
        if 'short_entry_zscore' not in st.session_state:
            st.session_state.short_entry_zscore = 2.5
        if 'short_exit_zscore' not in st.session_state:
            st.session_state.short_exit_zscore = 0.0
        
        # Short Entry Z-Score (must be ≥ 0)
        st.write("Entry Z-Score (≥ 0)")
        entry_col = st.columns([1, 4, 1])
        with entry_col[0]:
            if st.button("−", key="short_entry_dec"):
                st.session_state.short_entry_zscore = max(st.session_state.short_entry_zscore - 0.1, 0.0)
        with entry_col[1]:
            st.text_input(
                "Current Value",
                value=f"{st.session_state.short_entry_zscore:.1f}",
                key="short_entry_display",
                disabled=True,
                label_visibility="collapsed"
            )
        with entry_col[2]:
            if st.button("+", key="short_entry_inc"):
                st.session_state.short_entry_zscore += 0.1
        
        # Short Exit Z-Score (must be ≤ 0)
        st.write("Exit Z-Score (≤ 0)")
        exit_col = st.columns([1, 4, 1])
        with exit_col[0]:
            if st.button("−", key="short_exit_dec"):
                st.session_state.short_exit_zscore -= 0.1
        with exit_col[1]:
            st.text_input(
                "Current Value",
                value=f"{st.session_state.short_exit_zscore:.1f}",
                key="short_exit_display",
                disabled=True,
                label_visibility="collapsed"
            )
        with exit_col[2]:
            if st.button("+", key="short_exit_inc"):
                st.session_state.short_exit_zscore = min(st.session_state.short_exit_zscore + 0.1, 0.0)
        
        # RSI parameters
        short_entry_rsi = st.slider("Entry RSI (≥)", 0, 100, 70, key="short_entry_rsi")
        short_exit_rsi = st.slider("Exit RSI (≤)", 0, 100, 30, key="short_exit_rsi")

    if st.button("Run Backtest"):
        comparison_df['Z-Score'] = calculate_zscore(comparison_df['Ratio'], zscore_lookback)
        comparison_df['RSI'] = calculate_rsi(comparison_df['Ratio'], rsi_period)
        comparison_df = comparison_df.sort_values('Date', ascending=False).head(300)
        
        trades = []
        in_long = in_short = False
        long_entry_price = short_entry_price = None
        
        for _, row in comparison_df.iterrows():
            # Long trade logic
            if not in_long and row['Z-Score'] <= st.session_state.long_entry_zscore and row['RSI'] <= long_entry_rsi:
                in_long, long_entry_price = True, row['Ratio']
            elif in_long and (row['Z-Score'] >= st.session_state.long_exit_zscore or row['RSI'] >= long_exit_rsi):
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
            if not in_short and row['Z-Score'] >= st.session_state.short_entry_zscore and row['RSI'] >= short_entry_rsi:
                in_short, short_entry_price = True, row['Ratio']
            elif in_short and (row['Z-Score'] <= st.session_state.short_exit_zscore or row['RSI'] <= short_exit_rsi):
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
