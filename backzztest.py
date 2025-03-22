import streamlit as st
import pandas as pd

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

def main():
    st.title("Backtesting Page")
    
    if 'comparison_df' not in st.session_state:
        st.warning("Please load data from the Google Drive Data Loader page.")
        return
    
    # Retrieve the merged DataFrame from session_state
    comparison_df = st.session_state['comparison_df']
    
    # Add input boxes for Z-Score lookback and RSI period
    st.write("### Adjust Parameters")
    zscore_lookback = st.number_input("Z-Score Lookback Period (days)", min_value=1, value=50)
    rsi_period = st.number_input("RSI Period (days)", min_value=1, value=14)
    
    # Calculate Z-Score and RSI
    comparison_df['Z-Score'] = calculate_zscore(comparison_df['Ratio'], window=zscore_lookback)
    comparison_df['RSI'] = calculate_rsi(comparison_df['Ratio'], window=rsi_period)
    
    # Sort by Date (most recent first) and limit to 300 rows
    comparison_df = comparison_df.sort_values(by='Date', ascending=False).head(300)
    
    # Display the comparison table
    st.write("### Stock Price Comparison (Last 300 Rows)")
    st.dataframe(comparison_df[['Date', 'A2ZINFRA', 'AARTIIND', 'Ratio', 'Z-Score', 'RSI']])

if __name__ == '__main__':
    main()
