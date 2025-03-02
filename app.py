import streamlit as st
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
import json
import os

# Load secrets from Streamlit
google_secrets = st.secrets["google"]

# Create client_secrets.json dynamically
client_secrets = {
    "web": {
        "client_id": google_secrets.client_id,
        "client_secret": google_secrets.client_secret,
        "auth_uri": google_secrets.auth_uri,
        "token_uri": google_secrets.token_uri,
        "redirect_uris": [google_secrets.redirect_uri]
    }
}

with open("client_secrets.json", "w") as f:
    json.dump(client_secrets, f)

# Authenticate user with OAuth
def authenticate_user():
    gauth = GoogleAuth()
    gauth.LoadClientConfigFile("client_secrets.json")
    gauth.LocalWebserverAuth()  # Opens OAuth login in browser
    return GoogleDrive(gauth)

drive = authenticate_user()

# List available CSV files in Google Drive
def list_csv_files(drive):
    file_list = drive.ListFile({'q': "mimeType='text/csv'"}).GetList()
    return {file['title']: file['id'] for file in file_list}

csv_files = list_csv_files(drive)
if len(csv_files) < 2:
    st.error("You need at least two stock CSV files to perform pair trading backtesting.")
    st.stop()

# User selects two stocks for pair trading
st.sidebar.header("Select Stocks for Pair Trading")
stock1 = st.sidebar.selectbox("Select Stock 1", list(csv_files.keys()))
stock2 = st.sidebar.selectbox("Select Stock 2", list(csv_files.keys()))

if stock1 == stock2:
    st.error("Please select two different stocks.")
    st.stop()

# Download and load CSVs
def load_csv(file_id):
    file = drive.CreateFile({'id': file_id})
    file.GetContentFile(file['title'])
    df = pd.read_csv(file['title'])
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)
    return df

df1 = load_csv(csv_files[stock1])
df2 = load_csv(csv_files[stock2])

# Ensure same date range
df = df1[['Close']].join(df2[['Close']], lsuffix=f'_{stock1}', rsuffix=f'_{stock2}').dropna()
df.columns = [stock1, stock2]

# Sidebar parameters
st.sidebar.header("Backtest Parameters")
lookback = st.sidebar.number_input("Lookback Period (Days)", min_value=10, max_value=200, value=50)
entry_z = st.sidebar.number_input("Entry Z-Score", min_value=1.0, max_value=5.0, value=2.5)
exit_z = st.sidebar.number_input("Exit Z-Score", min_value=0.5, max_value=3.0, value=1.5)
capital_per_trade = st.sidebar.number_input("Capital Allocation per Trade", min_value=10000, max_value=500000, value=100000, step=10000)

# Compute price ratio and Z-score
df['Ratio'] = df[stock1] / df[stock2]
df['Rolling Mean'] = df['Ratio'].rolling(lookback).mean()
df['Rolling Std'] = df['Ratio'].rolling(lookback).std()
df['Z-score'] = (df['Ratio'] - df['Rolling Mean']) / df['Rolling Std']

def backtest(df):
    positions = []
    capital = 0
    for i in range(lookback, len(df)):
        if df['Z-score'][i] > entry_z:
            positions.append(('Short', df.index[i], df[stock1][i], df[stock2][i]))
            capital -= capital_per_trade  # Short first stock, long second
        elif df['Z-score'][i] < -entry_z:
            positions.append(('Long', df.index[i], df[stock1][i], df[stock2][i]))
            capital += capital_per_trade  # Long first stock, short second
        elif abs(df['Z-score'][i]) < exit_z and positions:
            positions.append(('Exit', df.index[i], df[stock1][i], df[stock2][i]))
            capital = 0  # Exit all positions
    return positions

# Run backtest
if st.sidebar.button("Run Backtest"):
    trades = backtest(df)
    if not trades:
        st.warning("No trades were executed based on the given parameters.")
    else:
        trade_log = pd.DataFrame(trades, columns=['Action', 'Date', stock1, stock2])
        st.write("## Trade Log")
        st.dataframe(trade_log)

        # Plot Z-score and signals
        fig, ax = plt.subplots()
        ax.plot(df.index, df['Z-score'], label='Z-score')
        ax.axhline(entry_z, color='r', linestyle='dashed', label='Entry Z')
        ax.axhline(-entry_z, color='r', linestyle='dashed')
        ax.axhline(exit_z, color='g', linestyle='dashed', label='Exit Z')
        ax.axhline(-exit_z, color='g', linestyle='dashed')
        ax.legend()
        st.pyplot(fig)

        st.success("Backtest complete!")
