import streamlit as st
import pandas as pd
import json
import math
from datetime import datetime

# Custom JSON encoder to handle Timestamp and NaN values
class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, pd.Timestamp):
            return obj.strftime('%Y-%m-%d')
        elif isinstance(obj, float) and math.isnan(obj):
            return None
        return super().default(obj)

# Sample stock data (replace this with your actual data loading logic)
def load_stock_data():
    # Example stock data with Timestamp and NaN values
    stock_data = [
        {
            "Date": pd.Timestamp("2025-02-10"),
            "Close": float('nan'),
            "High": float('nan'),
            "Low": float('nan'),
            "Open": float('nan'),
            "Volume": 0,
            "Dividends": 0.25,
            "Stock Splits": 0.0,
            "symbol": "AAPL"
        },
        {
            "Date": pd.Timestamp("2025-02-11"),
            "Close": 232.62,
            "High": 235.23,
            "Low": 228.13,
            "Open": 228.20,
            "Volume": 53718400,
            "Dividends": 0.0,
            "Stock Splits": 0.0,
            "symbol": "AAPL"
        }
    ]
    return stock_data

# Function to clean and serialize stock data
def clean_and_serialize_stock_data(stock_data):
    cleaned_data = []
    for entry in stock_data:
        cleaned_entry = {}
        for key, value in entry.items():
            if isinstance(value, pd.Timestamp):
                cleaned_entry[key] = value.strftime('%Y-%m-%d')
            elif isinstance(value, float) and math.isnan(value):
                cleaned_entry[key] = None
            else:
                cleaned_entry[key] = value
        cleaned_data.append(cleaned_entry)
    return json.dumps(cleaned_data, cls=CustomEncoder)

# Streamlit app
def main():
    st.title("Stock Data Viewer")

    # Load stock data
    stock_data = load_stock_data()

    # Clean and serialize the data
    serialized_data = clean_and_serialize_stock_data(stock_data)

    # Display the stock data
    st.write("### Stock Data")
    st.json(serialized_data)

    # Download button
    st.write("### Download Data")
    st.download_button(
        label="Download Stock Data as JSON",
        data=serialized_data,
        file_name="stock_data.json",
        mime="application/json"
    )

    # Delete button (example functionality)
    st.write("### Delete Data")
    if st.button("Delete Data"):
        st.warning("Data deletion functionality not implemented yet.")

# Run the app
if __name__ == "__main__":
    main()
