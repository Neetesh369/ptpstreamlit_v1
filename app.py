import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
import os
import pickle
import matplotlib.pyplot as plt
from statsmodels.tsa.stattools import adfuller
from scipy import stats
import statsmodels.api as sm
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from scipy.signal import hilbert

# Create a directory for storing data if it doesn't exist
DATA_DIR = "data_storage"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

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

# Load existing data files into session state at startup
def load_all_data_files():
    """Load all saved data files into session state."""
    if 'dataframes' not in st.session_state:
        st.session_state['dataframes'] = {}
    
    if 'csv_files' not in st.session_state:
        st.session_state['csv_files'] = []
    
    # Check if data directory exists
    if not os.path.exists(DATA_DIR):
        return
    
    # Load all pickle files from the data directory
    for filename in os.listdir(DATA_DIR):
        if filename.endswith('.pkl'):
            file_path = os.path.join(DATA_DIR, filename)
            try:
                with open(file_path, 'rb') as f:
                    df = pickle.load(f)
                
                # Store in session state
                symbol = filename[:-4]  # Remove .pkl extension
                st.session_state['dataframes'][symbol] = df
                
                # Add to list of available files if not already there
                if symbol not in st.session_state['csv_files']:
                    st.session_state['csv_files'].append(symbol)
            except Exception as e:
                st.error(f"Error loading {filename}: {e}")

# Call this function at startup
load_all_data_files()

# Function to standardize column names
def standardize_columns(df):
    """Standardize column names to Symbol, Date, Open, High, Low, Close, Volume."""
    # Check if we have the expected number of columns
    if len(df.columns) == 7:
        df.columns = ['Symbol', 'Date', 'Open', 'High', 'Low', 'Close', 'Volume']
    return df

# Function to save dataframe to persistent storage
def save_dataframe(symbol, df):
    """Save a dataframe to persistent storage with standardized columns."""
    try:
        # Standardize column names before saving
        df = standardize_columns(df)
        
        # Store in session state
        st.session_state['dataframes'][symbol] = df
        
        # Add to list of available files if not already there
        if symbol not in st.session_state['csv_files']:
            st.session_state['csv_files'].append(symbol)
        
        # Save to pickle file for persistence across refreshes
        file_path = os.path.join(DATA_DIR, f"{symbol}.pkl")
        with open(file_path, 'wb') as f:
            pickle.dump(df, f)
        
        return True
    except Exception as e:
        st.error(f"Error saving dataframe: {e}")
        return False

# Function to load dataframe from persistent storage
def load_dataframe(symbol):
    """Load a dataframe from persistent storage."""
    # First try to get from session state
    if symbol in st.session_state['dataframes']:
        return st.session_state['dataframes'][symbol]
    
    # If not in session state, try to load from file
    file_path = os.path.join(DATA_DIR, f"{symbol}.pkl")
    if os.path.exists(file_path):
        try:
            with open(file_path, 'rb') as f:
                df = pickle.load(f)
            
            # Store in session state for future use
            st.session_state['dataframes'][symbol] = df
            
            return df
        except Exception as e:
            st.error(f"Error loading {symbol}: {e}")
    
    return None

# Function to delete dataframe from persistent storage
def delete_dataframe(symbol):
    """Delete a dataframe from persistent storage."""
    try:
        # Remove from session state
        if symbol in st.session_state['dataframes']:
            del st.session_state['dataframes'][symbol]
        
        # Remove from list of files
        if symbol in st.session_state['csv_files']:
            st.session_state['csv_files'].remove(symbol)
        
        # Delete the file
        file_path = os.path.join(DATA_DIR, f"{symbol}.pkl")
        if os.path.exists(file_path):
            os.remove(file_path)
        
        return True
    except Exception as e:
        st.error(f"Error deleting {symbol}: {e}")
        return False

def calculate_zscore(series, window=50):
    """Calculate the Z-score for a given series using a rolling window."""
    rolling_mean = series.rolling(window=window).mean()
    rolling_std = series.rolling(window=window).std()
    zscore = (series - rolling_mean) / rolling_std
    # Handle division by zero and infinite values
    zscore = zscore.replace([np.inf, -np.inf], np.nan)
    return zscore

def calculate_rsi(series, window=14):
    """Calculate the Relative Strength Index (RSI) for a given series using a rolling window."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def download_historical_data(symbol_file_path, start_date, end_date):
    """Download historical data from Yahoo Finance, clean it, and store in persistent storage."""
    try:
        # Read the symbol file
        symbols = pd.read_csv(symbol_file_path, header=None).iloc[:, 0].tolist()
    except Exception as e:
        st.error(f"Error reading symbol file: {e}")
        return

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
            
            # Clean the data (remove first two rows if they exist)
            if len(data) > 2:
                data = data.iloc[2:].reset_index(drop=True)
            
            # Save to persistent storage with standardized column names
            if save_dataframe(f"{symbol}.csv", data):
                st.success(f"Data for {symbol} saved successfully with standardized column names")
            else:
                st.error(f"Failed to save data for {symbol}")
                
        except Exception as e:
            st.error(f"Error downloading data for {symbol}: {e}")

def clean_uploaded_data(df):
    """Clean the uploaded data and standardize column names."""
    # Remove first two rows if they exist
    if len(df) > 2:
        df = df.iloc[2:].reset_index(drop=True)
    
    # Standardize column names
    df = standardize_columns(df)
    
    return df

# Function to test for cointegration
def test_cointegration(series1, series2):
    """
    Test for cointegration between two price series using the Engle-Granger two-step method.
    
    Returns:
    - result: Dictionary containing test results
    """
    # Step 1: Run OLS regression
    X = sm.add_constant(series1)
    model = sm.OLS(series2, X).fit()
    
    # Get the residuals (spread)
    spread = model.resid
    
    # Step 2: Test for stationarity of residuals using ADF test
    adf_result = adfuller(spread)
    
    # Prepare result dictionary
    result = {
        'ADF Statistic': adf_result[0],
        'p-value': adf_result[1],
        'Critical Values': adf_result[4],
        'Is Cointegrated': adf_result[1] < 0.05,  # p-value < 0.05 indicates cointegration
        'Regression Coefficient': model.params.iloc[1],
        'Regression Intercept': model.params.iloc[0],
        'Regression R-squared': model.rsquared
    }
    
    return result, spread, model

def calculate_hurst_exponent(series, max_lag=20):
    """
    Calculate the Hurst exponent for a time series.
    
    Args:
        series: Time series data
        max_lag: Maximum lag to consider
    
    Returns:
        hurst_exponent: Hurst exponent value
    """
    try:
        # Remove NaN values
        series = series.dropna()
        
        if len(series) < max_lag:
            return np.nan
            
        # Calculate R/S (Rescaled Range) for different lags
        lags = range(2, min(max_lag, len(series)//2))
        rs_values = []
        
        for lag in lags:
            # Split series into chunks of size lag
            chunks = [series[i:i+lag] for i in range(0, len(series) - lag + 1, lag)]
            
            if not chunks:
                continue
                
            rs_chunk_values = []
            for chunk in chunks:
                if len(chunk) < 2:
                    continue
                    
                # Calculate mean
                mean_chunk = chunk.mean()
                
                # Calculate cumulative deviation
                cum_dev = (chunk - mean_chunk).cumsum()
                
                # Calculate R (range)
                R = cum_dev.max() - cum_dev.min()
                
                # Calculate S (standard deviation)
                S = chunk.std()
                
                if S != 0:
                    rs_chunk_values.append(R / S)
            
            if rs_chunk_values:
                rs_values.append(np.mean(rs_chunk_values))
        
        if len(rs_values) < 2:
            return np.nan
            
        # Calculate Hurst exponent using linear regression
        log_lags = np.log(lags[:len(rs_values)])
        log_rs = np.log(rs_values)
        
        # Linear regression
        slope, intercept, r_value, p_value, std_err = stats.linregress(log_lags, log_rs)
        
        return slope
        
    except Exception as e:
        return np.nan

def test_johansen_cointegration(series1, series2, significance_level=0.05):
    """
    Test for cointegration using Johansen test.
    
    Args:
        series1: First time series
        series2: Second time series
        significance_level: Significance level for the test
    
    Returns:
        result: Dictionary containing Johansen test results
    """
    try:
        # Prepare data for Johansen test
        data = pd.DataFrame({'series1': series1, 'series2': series2})
        data = data.dropna()
        
        if len(data) < 10:  # Need sufficient data
            return {
                'Is Cointegrated': False,
                'Trace Statistic': np.nan,
                'Critical Value': np.nan,
                'p-value': np.nan,
                'Error': 'Insufficient data'
            }
        
        # Run Johansen test
        result = coint_johansen(data, det_order=0, k_ar_diff=1)
        
        # Check if cointegrated (trace statistic > critical value)
        trace_stat = result.lr1[0]  # Trace statistic for r=0
        critical_value = result.cvt[0, 1]  # Critical value at 5%
        
        is_cointegrated = trace_stat > critical_value
        
        return {
            'Is Cointegrated': is_cointegrated,
            'Trace Statistic': trace_stat,
            'Critical Value': critical_value,
            'p-value': result.pvalue[0] if hasattr(result, 'pvalue') else np.nan,
            'Error': None
        }
        
    except Exception as e:
        return {
            'Is Cointegrated': False,
            'Trace Statistic': np.nan,
            'Critical Value': np.nan,
            'p-value': np.nan,
            'Error': str(e)
        }

def data_storage_page():
    """Data Storage page to download and store stock data."""
    st.title("📂 Data Storage")

    # Input fields for start and end dates
    st.write("### Enter Date Range")
    start_date = st.date_input("Start Date")
    end_date = st.date_input("End Date")

    # Path to the symbol file
    symbol_file_path = "fosymbols.csv"  # Replace with the path to your symbol file

    # Download data
    if st.button("Download Data"):
        download_historical_data(symbol_file_path, start_date, end_date)

    # View stored data
    if st.button("View Stored Data"):
        if not st.session_state['csv_files']:
            st.warning("No data has been downloaded yet.")
        else:
            st.write("### Stored Data")
            for file_name in st.session_state['csv_files']:
                df = load_dataframe(file_name)
                if df is not None:
                    st.write(f"#### File: {file_name}")
                    
                    # Display the dataframe
                    st.dataframe(df.head(10), hide_index=True)
                else:
                    st.error(f"Error loading {file_name}")
    
    # Upload CSV files directly
    st.write("### Upload CSV Files")
    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
    if uploaded_file is not None:
        try:
            # Read the uploaded file
            df = pd.read_csv(uploaded_file)
        
            # Clean the data and standardize column names
            df = clean_uploaded_data(df)
        
            # Save to persistent storage
            file_name = uploaded_file.name
            if save_dataframe(file_name, df):
                st.success(f"File {file_name} uploaded, cleaned, and standardized successfully")
            else:
                st.error(f"Failed to upload {file_name}")
        except Exception as e:
            st.error(f"Error processing uploaded file: {e}")
    
    # Delete stored files
    if st.session_state['csv_files']:
        st.write("### Delete Stored Files")
        file_to_delete = st.selectbox("Select file to delete", st.session_state['csv_files'])
        if st.button("Delete Selected File"):
            if delete_dataframe(file_to_delete):
                st.success(f"File {file_to_delete} deleted successfully")
            else:
                st.error(f"Error deleting file: {file_to_delete}")

def backtest_page():
    """Backtesting page to analyze stock data."""
    st.title("Backtesting Page")
    
    # Check if the CSV files and dataframes are available in session_state
    if not st.session_state['csv_files']:
        st.warning("Please download or upload data from the Data Storage page first.")
        return
    
    # Add dropdowns to select two stocks
    st.header("Select Stocks")
    col1, col2 = st.columns(2)
    with col1:
        stock1 = st.selectbox("Select Stock 1", st.session_state['csv_files'], key="stock1")
    with col2:
        stock2 = st.selectbox("Select Stock 2", st.session_state['csv_files'], key="stock2")
    
    if stock1 == stock2:
        st.error("Please select two different stocks.")
        return
    
    # Retrieve the selected dataframes
    df1 = load_dataframe(stock1)
    df2 = load_dataframe(stock2)
    
    if df1 is None or df2 is None:
        st.error("Error loading dataframes. Please check your data.")
        return
    
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
    
    # Add a section for correlation and cointegration lookback
    st.header("Statistical Analysis Parameters")
    # Note: All statistical tests now use the entire dataset
    
    # Add date range selection for backtesting
    st.header("Date Range Selection")
    col1, col2 = st.columns(2)
    
    with col1:
        analysis_start_date = st.date_input("Analysis Start Date", 
                                          value=comparison_df['Date'].min() if not comparison_df.empty else None,
                                          help="Start date for statistical analysis and backtesting")
    
    with col2:
        analysis_end_date = st.date_input("Analysis End Date", 
                                        value=comparison_df['Date'].max() if not comparison_df.empty else None,
                                        help="End date for statistical analysis and backtesting")
    
    # Add input boxes for Z-Score lookback and RSI period
    st.header("Trading Parameters")
    col1, col2 = st.columns(2)
    with col1:
        zscore_lookback = st.number_input("Z-Score Lookback Period (days)", min_value=1, value=50, key="zscore_lookback")
    with col2:
        rsi_period = st.number_input("RSI Period (days)", min_value=1, value=14, key="rsi_period")
    
    # Add RSI checkboxes with a more visible style
    st.markdown("### RSI Settings")
    st.markdown("Enable or disable RSI conditions for trade entry and exit")
    
    col1, col2 = st.columns(2)
    with col1:
        use_rsi_for_entry = st.checkbox("✅ Use RSI for Entry", value=True, key="use_rsi_for_entry", 
                                       help="When enabled, RSI conditions must be met for trade entry")
    with col2:
        use_rsi_for_exit = st.checkbox("✅ Use RSI for Exit", value=True, key="use_rsi_for_exit",
                                      help="When enabled, RSI conditions must be met for trade exit")
    
    # Add a visual separator
    st.markdown("---")
    
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
            long_entry_rsi = 100  # Impossible value when disabled
            
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
            short_entry_rsi = 0  # Impossible value when disabled
            
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
    
    # Add test mode for debugging (moved here to avoid re-running after Go button)
    test_mode = st.checkbox("🔧 Test Mode (Simplified Conditions)", value=False, 
                           help="Use simplified conditions to test if trading logic works")
    
    if test_mode:
        st.warning("🧪 Test Mode Enabled: Using simplified entry conditions for debugging")
        # Use simpler conditions for testing
        long_entry_zscore = -1.0  # More relaxed
        short_entry_zscore = 1.0   # More relaxed
        use_rsi_for_entry = False  # Disable RSI for testing
        use_rsi_for_exit = False   # Disable RSI for testing
    
    # Add a "Go" button
    if st.button("Go"):
        # Data validation
        comparison_df = comparison_df.dropna()
        comparison_df = comparison_df[comparison_df['Ratio'] != 0]
        comparison_df = comparison_df[comparison_df['Ratio'].notna()]
        
        if len(comparison_df) < 50:
            st.error("Insufficient data after cleaning. Need at least 50 data points.")
            return
        
        # Calculate Z-Score of Ratio
        comparison_df['Z-Score'] = calculate_zscore(comparison_df['Ratio'], window=zscore_lookback)
        
        # Calculate RSI of Ratio
        comparison_df['RSI'] = calculate_rsi(comparison_df['Ratio'], window=rsi_period)
        
        # Filter data for calculation table and trading based on selected date range
        if analysis_start_date and analysis_end_date:
            # Convert date inputs to datetime
            start_dt = pd.to_datetime(analysis_start_date)
            end_dt = pd.to_datetime(analysis_end_date)
            
            # Filter the dataframe for trading
            trading_df = comparison_df[(comparison_df['Date'] >= start_dt) & (comparison_df['Date'] <= end_dt)]
            
            if len(trading_df) == 0:
                st.error("No data available for the selected date range. Please adjust the dates.")
                return
        else:
            # Use the entire dataset if no date range is selected
            trading_df = comparison_df
        
        # Display calculation table first
        st.header("📊 Calculation Table")
        
        # Create calculation table with all required columns
        calc_table = trading_df[['Date', stock1, stock2, 'Ratio', 'Z-Score', 'RSI']].copy()
        calc_table.columns = ['Date', f'{stock1} Price', f'{stock2} Price', 'Ratio', 'Z-Score', 'RSI']
        
        # Format the table for better display
        calc_table['Ratio'] = calc_table['Ratio'].round(4)
        calc_table['Z-Score'] = calc_table['Z-Score'].round(2)
        calc_table['RSI'] = calc_table['RSI'].round(2)
        calc_table[f'{stock1} Price'] = calc_table[f'{stock1} Price'].round(2)
        calc_table[f'{stock2} Price'] = calc_table[f'{stock2} Price'].round(2)
        
        # Display as scrollable table
        st.dataframe(calc_table, use_container_width=True, height=400)
        
        # Add debugging information
        st.header("🔍 Trading Parameters Debug")
        
        # Create date range string safely
        if len(trading_df) > 0:
            start_date_str = trading_df['Date'].min().strftime('%Y-%m-%d')
            end_date_str = trading_df['Date'].max().strftime('%Y-%m-%d')
            date_range_str = f"{start_date_str} to {end_date_str}"
        else:
            date_range_str = "No data"
        
        debug_params = {
            'Parameter': [
                'Long Entry Z-Score', 'Long Exit Z-Score', 'Short Entry Z-Score', 'Short Exit Z-Score',
                'Long Entry RSI', 'Long Exit RSI', 'Short Entry RSI', 'Short Exit RSI',
                'Use RSI for Entry', 'Use RSI for Exit', 'Max Days in Trade', 'Target Profit %', 'Stop Loss %',
                'Data Points Available', 'Date Range'
            ],
            'Value': [
                str(long_entry_zscore), str(long_exit_zscore), str(short_entry_zscore), str(short_exit_zscore),
                str(long_entry_rsi), str(long_exit_rsi), str(short_entry_rsi), str(short_exit_rsi),
                str(use_rsi_for_entry), str(use_rsi_for_exit), str(max_days_in_trade), str(target_profit_pct), str(stop_loss_pct),
                str(len(trading_df)), date_range_str
            ]
        }
        debug_params_df = pd.DataFrame(debug_params)
        st.dataframe(debug_params_df, hide_index=True)
        
        # Check for potential trade signals (crossover-based)
        long_crossovers = 0
        short_crossovers = 0
        
        prev_zscore_check = None
        for _, row in trading_df.iterrows():
            current_zscore_check = row['Z-Score']
            if prev_zscore_check is not None:
                # Check for crossovers
                if prev_zscore_check > long_entry_zscore and current_zscore_check <= long_entry_zscore:
                    long_crossovers += 1
                if prev_zscore_check < short_entry_zscore and current_zscore_check >= short_entry_zscore:
                    short_crossovers += 1
            prev_zscore_check = current_zscore_check
        
        st.info(f"📊 Potential Crossovers: {long_crossovers} long crossovers, {short_crossovers} short crossovers")
        
        # First perform correlation and cointegration analysis
        st.header("Pair Statistics")
        
        try:
            # Convert Date column to datetime if it's not already
            if not pd.api.types.is_datetime64_any_dtype(comparison_df['Date']):
                comparison_df['Date'] = pd.to_datetime(comparison_df['Date'])
            
            # Sort by Date (oldest first)
            comparison_df = comparison_df.sort_values(by='Date', ascending=True)
            
            # Filter data based on selected date range
            if analysis_start_date and analysis_end_date:
                # Convert date inputs to datetime
                start_dt = pd.to_datetime(analysis_start_date)
                end_dt = pd.to_datetime(analysis_end_date)
                
                # Filter the dataframe
                stat_df = comparison_df[(comparison_df['Date'] >= start_dt) & (comparison_df['Date'] <= end_dt)]
                
                if len(stat_df) == 0:
                    st.error("No data available for the selected date range. Please adjust the dates.")
                    return
                    
                st.info(f"📅 Using data from {start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')} ({len(stat_df)} days)")
            else:
                # Use the entire dataset if no date range is selected
                stat_df = comparison_df
                st.info(f"📅 Using entire dataset ({len(stat_df)} days)")
            
            # Calculate correlation using selected date range
            correlation = stat_df[stock1].corr(stat_df[stock2])
            
            # Run Engle-Granger cointegration test using selected date range
            coint_result, spread, model = test_cointegration(stat_df[stock1], stat_df[stock2])
            
            # Run Johansen cointegration test using selected date range
            johansen_result = test_johansen_cointegration(stat_df[stock1], stat_df[stock2])
            
            # Calculate Hurst exponent for the ratio using selected date range
            hurst_exponent = calculate_hurst_exponent(stat_df['Ratio'])
            
            # Display results in three columns
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.subheader("Correlation Analysis")
                st.write(f"**Analysis Period:** {len(stat_df)} days")
                st.write(f"**Pearson Correlation:** {correlation:.4f}")
                
                # Interpret correlation
                if abs(correlation) > 0.8:
                    correlation_strength = "Very Strong"
                elif abs(correlation) > 0.6:
                    correlation_strength = "Strong"
                elif abs(correlation) > 0.4:
                    correlation_strength = "Moderate"
                elif abs(correlation) > 0.2:
                    correlation_strength = "Weak"
                else:
                    correlation_strength = "Very Weak"
                
                correlation_direction = "Positive" if correlation > 0 else "Negative"
                st.write(f"**Interpretation:** {correlation_direction} {correlation_strength} correlation")
            
            with col2:
                st.subheader("Engle-Granger Cointegration")
                st.write(f"**Analysis Period:** {len(stat_df)} days")
                st.write(f"**ADF Test Statistic:** {coint_result['ADF Statistic']:.4f}")
                st.write(f"**p-value:** {coint_result['p-value']:.4f}")
                
                # Interpret cointegration
                if coint_result['Is Cointegrated']:
                    st.success("**Result:** Cointegrated (p < 0.05)")
                else:
                    st.warning("**Result:** Not cointegrated (p >= 0.05)")
            
            with col3:
                st.subheader("Johansen Cointegration")
                st.write(f"**Analysis Period:** {len(stat_df)} days")
                if johansen_result['Error'] is None:
                    st.write(f"**Trace Statistic:** {johansen_result['Trace Statistic']:.4f}")
                    st.write(f"**Critical Value:** {johansen_result['Critical Value']:.4f}")
                    
                    if johansen_result['Is Cointegrated']:
                        st.success("**Result:** Cointegrated")
                    else:
                        st.warning("**Result:** Not cointegrated")
                else:
                    st.error(f"**Error:** {johansen_result['Error']}")
            
            # Display Hurst exponent
            st.subheader("Hurst Exponent Analysis")
            if not np.isnan(hurst_exponent):
                st.write(f"**Hurst Exponent:** {hurst_exponent:.4f}")
                
                # Interpret Hurst exponent
                if hurst_exponent > 0.5:
                    hurst_interpretation = "Trending (Mean-reverting pairs trading may not be optimal)"
                elif hurst_exponent < 0.5:
                    hurst_interpretation = "Mean-reverting (Good for pairs trading)"
                else:
                    hurst_interpretation = "Random walk"
                
                st.write(f"**Interpretation:** {hurst_interpretation}")
            else:
                st.warning("**Hurst Exponent:** Could not be calculated")
            
            # Add a visual separator
            st.markdown("---")
            
            # Add statistical summary
            st.subheader("Ratio Statistics")
            ratio_stats = {
                'Metric': ['Mean', 'Std Dev', 'Min', 'Max', 'Current Z-Score', 'Current RSI'],
                'Value': [
                    f"{comparison_df['Ratio'].mean():.4f}",
                    f"{comparison_df['Ratio'].std():.4f}",
                    f"{comparison_df['Ratio'].min():.4f}",
                    f"{comparison_df['Ratio'].max():.4f}",
                    f"{comparison_df['Z-Score'].iloc[-1]:.2f}" if not np.isnan(comparison_df['Z-Score'].iloc[-1]) else "N/A",
                    f"{comparison_df['RSI'].iloc[-1]:.2f}" if not np.isnan(comparison_df['RSI'].iloc[-1]) else "N/A"
                ]
            }
            ratio_stats_df = pd.DataFrame(ratio_stats)
            st.dataframe(ratio_stats_df, hide_index=True)
            
        except Exception as e:
            st.error(f"Error in correlation/cointegration analysis: {e}")
            
            # Debug information
            debug_info = []
            trades = [] # Initialize trades list
            trade_count = 0
            
            # Track previous Z-score for crossover detection
            prev_zscore = None
            in_trade = False
            trade_type = None
            entry_price = None
            entry_date = None
            entry_index = None

            for index, row in trading_df.iterrows():
                current_date = row['Date']
                current_zscore = row['Z-Score']
                current_rsi = row['RSI']
                current_ratio = row['Ratio']
                
                # Debug data for this row
                row_debug = {
                    'Date': current_date,
                    'Z-Score': current_zscore,
                    'RSI': current_rsi,
                    'Ratio': current_ratio,
                    'Action': 'None'
                }
                
                # Check for trade exit conditions if in a trade
                if in_trade:
                    days_in_trade = (current_date - entry_date).days
                    
                    if trade_type == 'Long':
                        current_profit_pct = ((current_ratio - entry_price) / entry_price) * 100
                        
                        # Check exit conditions for long trade
                        zscore_exit = current_zscore >= long_exit_zscore  # Exit when Z-score goes above exit threshold
                        rsi_exit = use_rsi_for_exit and current_rsi >= long_exit_rsi
                        time_exit = days_in_trade >= max_days_in_trade
                        target_exit = current_profit_pct >= target_profit_pct
                        stop_exit = current_profit_pct <= -stop_loss_pct
                        
                        # Debug exit conditions
                        st.info(f"🔍 Long Trade Debug - Z-Score: {current_zscore:.2f} (Exit at: {long_exit_zscore}), RSI: {current_rsi:.2f} (Exit at: {long_exit_rsi}), Profit: {current_profit_pct:.2f}%, Days: {days_in_trade}")
                        st.info(f"🔍 Exit Conditions - Z-Score: {zscore_exit}, RSI: {rsi_exit}, Time: {time_exit}, Target: {target_exit}, Stop: {stop_exit}")
                        
                        # Determine exit reason with priority
                        exit_reason = None
                        if target_exit:
                            exit_reason = "Target"
                        elif stop_exit:
                            exit_reason = "Stop Loss"
                        elif time_exit:
                            exit_reason = "Time"
                        elif zscore_exit:
                            exit_reason = "Z-Score"
                        elif rsi_exit:
                            exit_reason = "RSI"
                        
                        if exit_reason:
                            # Exit long trade
                            exit_price = current_ratio
                            profit = exit_price - entry_price
                            profit_pct = (profit / entry_price) * 100
                            
                            trades.append({
                                'Entry Date': entry_date,
                                'Exit Date': current_date,
                                'Days in Trade': days_in_trade,
                                'Entry Price': entry_price,
                                'Exit Price': exit_price,
                                'Profit': profit,
                                'Profit %': profit_pct,
                                'Type': 'Long',
                                'Exit Reason': exit_reason
                            })
                            
                            st.info(f"🔍 Added Long trade: Entry={entry_date}, Exit={current_date}, Profit={profit:.2f}")
                            
                            row_debug['Action'] = f'Exit Long: {exit_reason}'
                            
                            in_trade = False
                            trade_type = None
                            entry_price = None
                            entry_date = None
                            entry_index = None
                    
                    elif trade_type == 'Short':
                        current_profit_pct = ((entry_price - current_ratio) / entry_price) * 100
                        
                        # Check exit conditions for short trade
                        zscore_exit = current_zscore <= short_exit_zscore  # Exit when Z-score goes below exit threshold
                        rsi_exit = use_rsi_for_exit and current_rsi <= short_exit_rsi
                        time_exit = days_in_trade >= max_days_in_trade
                        target_exit = current_profit_pct >= target_profit_pct
                        stop_exit = current_profit_pct <= -stop_loss_pct
                        
                        # Debug exit conditions
                        st.info(f"🔍 Short Trade Debug - Z-Score: {current_zscore:.2f} (Exit at: {short_exit_zscore}), RSI: {current_rsi:.2f} (Exit at: {short_exit_rsi}), Profit: {current_profit_pct:.2f}%, Days: {days_in_trade}")
                        st.info(f"🔍 Exit Conditions - Z-Score: {zscore_exit}, RSI: {rsi_exit}, Time: {time_exit}, Target: {target_exit}, Stop: {stop_exit}")
                        
                        # Determine exit reason with priority
                        exit_reason = None
                        if target_exit:
                            exit_reason = "Target"
                        elif stop_exit:
                            exit_reason = "Stop Loss"
                        elif time_exit:
                            exit_reason = "Time"
                        elif zscore_exit:
                            exit_reason = "Z-Score"
                        elif rsi_exit:
                            exit_reason = "RSI"
                        
                        if exit_reason:
                            # Exit short trade
                            exit_price = current_ratio
                            profit = entry_price - exit_price
                            profit_pct = (profit / entry_price) * 100
                            
                            trades.append({
                                'Entry Date': entry_date,
                                'Exit Date': current_date,
                                'Days in Trade': days_in_trade,
                                'Entry Price': entry_price,
                                'Exit Price': exit_price,
                                'Profit': profit,
                                'Profit %': profit_pct,
                                'Type': 'Short',
                                'Exit Reason': exit_reason
                            })
                            
                            st.info(f"🔍 Added Short trade: Entry={entry_date}, Exit={current_date}, Profit={profit:.2f}")
                            
                            row_debug['Action'] = f'Exit Short: {exit_reason}'
                            
                            in_trade = False
                            trade_type = None
                            entry_price = None
                            entry_date = None
                            entry_index = None
                
                # Check for new trade entries (only if not in a trade)
                elif not in_trade and prev_zscore is not None:
                    # Check for crossover-based entries
                    long_crossover = prev_zscore > long_entry_zscore and current_zscore <= long_entry_zscore
                    short_crossover = prev_zscore < short_entry_zscore and current_zscore >= short_entry_zscore
                    
                    # Check RSI conditions
                    long_rsi_ok = not use_rsi_for_entry or current_rsi <= long_entry_rsi
                    short_rsi_ok = not use_rsi_for_entry or current_rsi >= short_entry_rsi
                    
                    # Enter long trade if crossover and RSI conditions are met
                    if long_crossover and long_rsi_ok:
                        in_trade = True
                        trade_type = 'Long'
                        entry_price = current_ratio
                        entry_date = current_date
                        entry_index = index
                        row_debug['Action'] = f'Enter Long (Crossover: {prev_zscore:.2f} → {current_zscore:.2f})'
                        trade_count += 1
                        st.info(f"🔍 Entered Long trade: Date={current_date}, Price={current_ratio:.4f}")
                    
                    # Enter short trade if crossover and RSI conditions are met
                    elif short_crossover and short_rsi_ok:
                        in_trade = True
                        trade_type = 'Short'
                        entry_price = current_ratio
                        entry_date = current_date
                        entry_index = index
                        row_debug['Action'] = f'Enter Short (Crossover: {prev_zscore:.2f} → {current_zscore:.2f})'
                        trade_count += 1
                        st.info(f"🔍 Entered Short trade: Date={current_date}, Price={current_ratio:.4f}")
                
                # Update previous Z-score for next iteration
                prev_zscore = current_zscore
                
                # Add debug info for this row
                debug_info.append(row_debug)
            
            # Close any open trades at the end of the data
            if in_trade:
                last_row = trading_df.iloc[-1]
                days_in_trade = (last_row['Date'] - entry_date).days
                exit_price = last_row['Ratio']
                profit = exit_price - entry_price
                profit_pct = (profit / entry_price) * 100
                
                trades.append({
                    'Entry Date': entry_date,
                    'Exit Date': last_row['Date'],
                    'Days in Trade': days_in_trade,
                    'Entry Price': entry_price,
                    'Exit Price': exit_price,
                    'Profit': profit,
                    'Profit %': profit_pct,
                    'Type': trade_type,
                    'Exit Reason': 'End of Data'
                })
            
            # Display trade results
            if trades:
                trades_df = pd.DataFrame(trades)
                
                # Debug: Show trade count immediately
                st.success(f"✅ {len(trades)} trades executed successfully!")
                
                # Create date-wise trade results table
                st.header("📊 Date-wise Trade Results")
                
                # Prepare the trade results table with requested columns
                trade_results_table = trades_df.copy()
                trade_results_table['Date'] = trade_results_table['Entry Date'].dt.strftime('%Y-%m-%d')
                trade_results_table['Long Stock'] = stock1
                trade_results_table['Short Stock'] = stock2
                trade_results_table['Profit/Loss %'] = trade_results_table['Profit %'].round(2)
                trade_results_table['Holding Period (Days)'] = trade_results_table['Days in Trade']
                
                # Select and rename columns for display
                display_columns = ['Date', 'Long Stock', 'Short Stock', 'Profit/Loss %', 'Holding Period (Days)', 'Type', 'Exit Reason']
                trade_display = trade_results_table[display_columns].copy()
                
                # Display the trade results table
                st.dataframe(trade_display, use_container_width=True, hide_index=True)
                
                # Create a debug dataframe
                debug_df = pd.DataFrame(debug_info)
                
                # Show debug information (only rows with actions)
                st.header("Trade Actions Log")
                action_debug_df = debug_df[debug_df['Action'] != 'None']
                st.dataframe(action_debug_df, hide_index=True)
                
                # Calculate comprehensive trade summary metrics
                total_trades = len(trades_df)
                winning_trades = trades_df[trades_df['Profit'] > 0]
                losing_trades = trades_df[trades_df['Profit'] <= 0]
                
                # Basic metrics
                win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0
                lose_rate = (len(losing_trades) / total_trades) * 100 if total_trades > 0 else 0
                
                # Profit/Loss metrics
                avg_win_pct = winning_trades['Profit %'].mean() if len(winning_trades) > 0 else 0
                avg_loss_pct = losing_trades['Profit %'].mean() if len(losing_trades) > 0 else 0
                
                # Holding period metrics
                avg_holding_period = trades_df['Days in Trade'].mean()
                max_holding_period = trades_df['Days in Trade'].max()
                
                # Drawdown calculation
                cumulative_profit = trades_df['Profit'].cumsum()
                running_max = cumulative_profit.expanding().max()
                drawdown = (cumulative_profit - running_max) / running_max * 100
                max_drawdown_pct = drawdown.min()
                
                # Total profit
                total_profit = trades_df['Profit'].sum()
                
                # Display comprehensive trade summary
                st.header("📈 Trade Summary")
                summary_data = {
                    'Metric': [
                        'Number of Trades',
                        'Win Rate (%)',
                        'Lose Rate (%)',
                        'Max Drawdown (%)',
                        'Avg Win (%)',
                        'Avg Loss (%)',
                        'Avg Holding Period (Days)',
                        'Max Holding Period (Days)',
                        'Total Profit ($)'
                    ],
                    'Value': [
                        total_trades,
                        f"{win_rate:.2f}",
                        f"{lose_rate:.2f}",
                        f"{max_drawdown_pct:.2f}",
                        f"{avg_win_pct:.2f}",
                        f"{avg_loss_pct:.2f}",
                        f"{avg_holding_period:.1f}",
                        max_holding_period,
                        f"{total_profit:.2f}"
                    ]
                }
                summary_df = pd.DataFrame(summary_data)
                st.dataframe(summary_df, hide_index=True)
                
                # Display exit reason statistics
                st.subheader("Exit Reasons")
                exit_reasons = trades_df['Exit Reason'].value_counts()
                exit_reasons_df = pd.DataFrame({
                    'Exit Reason': exit_reasons.index,
                    'Count': exit_reasons.values
                })
                st.dataframe(exit_reasons_df, hide_index=True)
                
                # Display total profit with color coding
                if total_profit > 0:
                    st.success(f"💰 Total Profit: ${total_profit:.2f}")
                else:
                    st.error(f"💸 Total Loss: ${total_profit:.2f}")
                
                # Calculate and plot Equity Curve
                trades_df['Cumulative Profit'] = trades_df['Profit'].cumsum()
                st.header("📊 Equity Curve")
                st.line_chart(trades_df.set_index('Exit Date')['Cumulative Profit'])
            else:
                st.warning("No trades executed based on the provided parameters.")
                st.info(f"🔍 Debug Info: {trade_count} trade entries detected, but no completed trades.")
                st.info(f"🔍 Trades list length: {len(trades)}")
                
                # Show some debugging info about why no trades
                if len(trading_df) > 0:
                    zscore_range = f"Z-Score range: {trading_df['Z-Score'].min():.2f} to {trading_df['Z-Score'].max():.2f}"
                    rsi_range = f"RSI range: {trading_df['RSI'].min():.2f} to {trading_df['RSI'].max():.2f}"
                    st.info(f"📊 Data ranges: {zscore_range}, {rsi_range}")
                    
                    # Check if conditions are too strict
                    extreme_zscore_count = len(trading_df[(trading_df['Z-Score'] <= long_entry_zscore) | (trading_df['Z-Score'] >= short_entry_zscore)])
                    st.info(f"📊 Extreme Z-Score conditions met: {extreme_zscore_count} times")
                    
                    # Show current parameters
                    st.info(f"📊 Current Parameters: Long Entry Z-Score: {long_entry_zscore}, Short Entry Z-Score: {short_entry_zscore}")
                    st.info(f"📊 RSI Entry Enabled: {use_rsi_for_entry}, Long Entry RSI: {long_entry_rsi}, Short Entry RSI: {short_entry_rsi}")
                    
                    # Show first few rows of data for debugging
                    st.subheader("🔍 First 5 rows of trading data:")
                    debug_data = trading_df[['Date', 'Z-Score', 'RSI', 'Ratio']].head()
                    st.dataframe(debug_data, hide_index=True)

def main():
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Data Storage", "Backtesting Page"])

    if page == "Data Storage":
        data_storage_page()
    elif page == "Backtesting Page":
        backtest_page()

if __name__ == '__main__':
    main()
