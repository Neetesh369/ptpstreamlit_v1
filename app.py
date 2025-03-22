import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

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

def backtest_trades(comparison_df, entry_threshold, exit_threshold, from_date, to_date):
    """Backtest trades based on Z-Score deviations."""
    trades = []
    in_trade = False
    trade_type = None
    entry_price_stock1 = None
    entry_price_stock2 = None
    entry_date = None
    max_loss = 0

    for i, row in comparison_df.iterrows():
        date = row['Date']
        zscore = row['Z-Score']
        price_stock1 = row[stock1]
        price_stock2 = row[stock2]

        # Skip rows outside the backtesting period
        if date < from_date or date > to_date:
            continue

        # Entry logic
        if not in_trade:
            if zscore > entry_threshold:
                trade_type = "Short Ratio"
                entry_price_stock1 = price_stock1
                entry_price_stock2 = price_stock2
                entry_date = date
                in_trade = True
                max_loss = 0
            elif zscore < -entry_threshold:
                trade_type = "Long Ratio"
                entry_price_stock1 = price_stock1
                entry_price_stock2 = price_stock2
                entry_date = date
                in_trade = True
                max_loss = 0

        # Exit logic
        if in_trade:
            if (trade_type == "Short Ratio" and zscore < exit_threshold) or (trade_type == "Long Ratio" and zscore > -exit_threshold):
                exit_date = date
                exit_price_stock1 = price_stock1
                exit_price_stock2 = price_stock2

                # Calculate profit %
                if trade_type == "Long Ratio":
                    profit_pct = ((exit_price_stock1 - entry_price_stock1) / entry_price_stock1) - ((exit_price_stock2 - entry_price_stock2) / entry_price_stock2)
                else:
                    profit_pct = ((exit_price_stock2 - entry_price_stock2) / entry_price_stock2) - ((exit_price_stock1 - entry_price_stock1) / entry_price_stock1)

                # Calculate holding period
                holding_period = (exit_date - entry_date).days

                # Add trade to the list
                trades.append({
                    "Entry Date": entry_date,
                    "Exit Date": exit_date,
                    "Trade Type": trade_type,
                    "Profit %": profit_pct * 100,
                    "Holding Period": holding_period,
                    "Max Loss": max_loss * 100
                })

                # Reset trade state
                in_trade = False
                trade_type = None
                entry_price_stock1 = None
                entry_price_stock2 = None
                entry_date = None
                max_loss = 0

            # Update max loss
            if trade_type == "Long Ratio":
                current_loss = ((price_stock1 - entry_price_stock1) / entry_price_stock1) - ((price_stock2 - entry_price_stock2) / entry_price_stock2)
            else:
                current_loss = ((price_stock2 - entry_price_stock2) / entry_price_stock2) - ((price_stock1 - entry_price_stock1) / entry_price_stock1)
            if current_loss < max_loss:
                max_loss = current_loss

    return pd.DataFrame(trades)

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
    st.write("### Select Stocks")
    stock1 = st.selectbox("Select Stock 1", csv_files)
    stock2 = st.selectbox("Select Stock 2", csv_files)
    
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
    st.write("### Adjust Parameters")
    zscore_lookback = st.number_input("Z-Score Lookback Period (days)", min_value=1, value=50)
    rsi_period = st.number_input("RSI Period (days)", min_value=1, value=14)
    
    # Calculate Z-Score of Ratio
    comparison_df['Z-Score'] = calculate_zscore(comparison_df['Ratio'], window=zscore_lookback)
    
    # Calculate RSI of Ratio
    comparison_df['RSI'] = calculate_rsi(comparison_df['Ratio'], window=rsi_period)
    
    # Sort by Date (most recent first) and limit to 300 rows
    comparison_df = comparison_df.sort_values(by='Date', ascending=False).head(300)
    
    # Display the comparison table
    st.write("### Stock Price Comparison (Last 300 Rows)")
    st.dataframe(comparison_df)
    
    # Add sliders for entry and exit Z-Score deviations
    st.write("### Trade Parameters")
    entry_threshold = st.slider("Entry Z-Score Deviation", min_value=0.0, max_value=5.0, value=2.5, step=0.1)
    exit_threshold = st.slider("Exit Z-Score Deviation", min_value=0.0, max_value=5.0, value=1.5, step=0.1)
    
    # Add date range input
    st.write("### Backtesting Period")
    from_date = st.date_input("From Date", value=comparison_df['Date'].min())
    to_date = st.date_input("To Date", value=comparison_df['Date'].max())
    
    # Backtest trades
    trades_df = backtest_trades(comparison_df, entry_threshold, exit_threshold, from_date, to_date)
    
    # Display trades table
    st.write("### Trades")
    st.dataframe(trades_df)

def main():
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Google Drive Viewer", "Backtesting Page"])

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
