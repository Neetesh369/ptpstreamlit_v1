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
    return zscore

def calculate_rsi(series, window=14):
    """Calculate the Relative Strength Index (RSI) for a given series using a rolling window."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
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
        'Regression Coefficient': model.params[1],
        'Regression Intercept': model.params[0],
        'Regression R-squared': model.rsquared
    }
    
    return result, spread, model

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
    
    # Merge the data for correlation analysis
    try:
        df1_close = df1[['Date', 'Close']].copy()
        df2_close = df2[['Date', 'Close']].copy()
        
        # Convert Date column to datetime if it's not already
        if not pd.api.types.is_datetime64_any_dtype(df1_close['Date']):
            df1_close['Date'] = pd.to_datetime(df1_close['Date'])
        if not pd.api.types.is_datetime64_any_dtype(df2_close['Date']):
            df2_close['Date'] = pd.to_datetime(df2_close['Date'])
        
        # Merge the data on Date for correlation analysis
        corr_df = pd.merge(df1_close, df2_close, on='Date', how='inner', suffixes=('_1', '_2'))
        
        # Rename columns for clarity
        corr_df.rename(columns={
            'Close_1': stock1,
            'Close_2': stock2
        }, inplace=True)
        
        # Sort by Date (oldest first)
        corr_df = corr_df.sort_values(by='Date', ascending=True)
        
        # Calculate correlation
        correlation = corr_df[stock1].corr(corr_df[stock2])
        
        # Run cointegration test
        coint_result, spread, model = test_cointegration(corr_df[stock1], corr_df[stock2])
        
        # Display correlation and cointegration results
        st.header("Pair Statistics")
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Correlation Analysis")
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
            st.subheader("Cointegration Analysis")
            st.write(f"**ADF Test Statistic:** {coint_result['ADF Statistic']:.4f}")
            st.write(f"**p-value:** {coint_result['p-value']:.4f}")
            
            # Interpret cointegration
            if coint_result['Is Cointegrated']:
                st.success("**Result:** Cointegrated (p < 0.05)")
            else:
                st.warning("**Result:** Not cointegrated (p >= 0.05)")
        
        # Create a scatter plot of prices
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.scatter(corr_df[stock1], corr_df[stock2], alpha=0.5)
        ax.set_xlabel(stock1)
        ax.set_ylabel(stock2)
        ax.set_title(f'Price Scatter Plot: {stock1} vs {stock2}')
        
        # Add regression line
        slope, intercept, r_value, p_value, std_err = stats.linregress(corr_df[stock1], corr_df[stock2])
        x = np.array([corr_df[stock1].min(), corr_df[stock1].max()])
        y = intercept + slope * x
        ax.plot(x, y, 'r-', label=f'y = {slope:.2f}x + {intercept:.2f}')
        ax.legend()
        
        st.pyplot(fig)
        
        # Plot the spread (residuals)
        fig, ax = plt.subplots(figsize=(10, 6))
        spread_series = pd.Series(spread, index=corr_df['Date'])
        ax.plot(spread_series)
        ax.axhline(y=0, color='r', linestyle='-')
        ax.set_title('Spread (Residuals) Over Time')
        ax.set_xlabel('Date')
        ax.set_ylabel('Spread')
        st.pyplot(fig)
        
        # Add a visual separator
        st.markdown("---")
        
    except Exception as e:
        st.error(f"Error in correlation analysis: {e}")
    
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
        st.dataframe(display_df, hide_index=True)
        
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
        
        # Debug information
        debug_info = []
        
        for index, row in comparison_df.iterrows():
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
            
            # Check for long trade exit conditions if in a long trade
            if in_long_trade:
                days_in_trade = (current_date - long_entry_date).days
                current_profit_pct = ((current_ratio - long_entry_price) / long_entry_price) * 100
                
                # Check all exit conditions
                zscore_exit = current_zscore <= long_exit_zscore
                rsi_exit = use_rsi_for_exit and current_rsi >= long_exit_rsi
                time_exit = days_in_trade >= max_days_in_trade
                target_exit = current_profit_pct >= target_profit_pct
                stop_exit = current_profit_pct <= -stop_loss_pct
                
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
                    exit_date = current_date
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
                    
                    row_debug['Action'] = f'Exit Long: {exit_reason}'
                    
                    in_long_trade = False
                    long_entry_price = None
                    long_entry_date = None
                    long_entry_index = None
            
            # Check for short trade exit conditions if in a short trade
            elif in_short_trade:
                days_in_trade = (current_date - short_entry_date).days
                current_profit_pct = ((short_entry_price - current_ratio) / short_entry_price) * 100
                
                # Check all exit conditions
                zscore_exit = current_zscore <= short_exit_zscore  # For short trades, exit when Z-Score falls below exit threshold
                rsi_exit = use_rsi_for_exit and current_rsi <= short_exit_rsi
                time_exit = days_in_trade >= max_days_in_trade
                target_exit = current_profit_pct >= target_profit_pct
                stop_exit = current_profit_pct <= -stop_loss_pct
                
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
                    exit_date = current_date
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
                    
                    row_debug['Action'] = f'Exit Short: {exit_reason}'
                    
                    in_short_trade = False
                    short_entry_price = None
                    short_entry_date = None
                    short_entry_index = None
            
            # Check for new trade entries (only if not already in a trade)
            elif not in_long_trade and not in_short_trade:
                # Check long trade entry conditions
                long_zscore_condition = current_zscore <= long_entry_zscore
                long_rsi_condition = not use_rsi_for_entry or current_rsi <= long_entry_rsi
                
                # Check short trade entry conditions
                short_zscore_condition = current_zscore >= short_entry_zscore
                short_rsi_condition = not use_rsi_for_entry or current_rsi >= short_entry_rsi
                
                # Enter long trade if conditions are met
                if long_zscore_condition and long_rsi_condition:
                    in_long_trade = True
                    long_entry_price = current_ratio
                    long_entry_date = current_date
                    long_entry_index = index
                    row_debug['Action'] = 'Enter Long'
                
                # Enter short trade if conditions are met
                elif short_zscore_condition and short_rsi_condition:
                    in_short_trade = True
                    short_entry_price = current_ratio
                    short_entry_date = current_date
                    short_entry_index = index
                    row_debug['Action'] = 'Enter Short'
            
            # Add debug info for this row
            debug_info.append(row_debug)
        
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
            st.dataframe(trades_df, hide_index=True)
            
            # Create a debug dataframe
            debug_df = pd.DataFrame(debug_info)
            
            # Show debug information (only rows with actions)
            st.header("Trade Actions Log")
            action_debug_df = debug_df[debug_df['Action'] != 'None']
            st.dataframe(action_debug_df, hide_index=True)
            
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
            st.dataframe(summary_df, hide_index=True)
            
            # Display exit reason statistics
            st.subheader("Exit Reasons")
            exit_reasons_df = pd.DataFrame({
                'Exit Reason': exit_reasons.index,
                'Count': exit_reasons.values
            })
            st.dataframe(exit_reasons_df, hide_index=True)
            
            # Display total profit
            st.success(f"Total Profit: {total_profit:.2f}")
            
            # Calculate and plot Equity Curve
            trades_df['Cumulative Profit'] = trades_df['Profit'].cumsum()
            st.header("Equity Curve")
            st.line_chart(trades_df.set_index('Exit Date')['Cumulative Profit'])
        else:
            st.warning("No trades executed based on the provided parameters.")

def main():
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Data Storage", "Backtesting Page"])

    if page == "Data Storage":
        data_storage_page()
    elif page == "Backtesting Page":
        backtest_page()

if __name__ == '__main__':
    main()
