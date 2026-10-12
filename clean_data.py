import pandas as pd
import numpy as np

def sanitize_and_unify_csv(file_path="el_paso_gas_prices.csv"):
    try:
        df = pd.read_csv(file_path, skipinitialspace=True)

        price_cols = ['Regular_Price', 'Plus_Price', 'Premium_Price']
        for col in price_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                df[col] = df[col].replace(0.0, np.nan)

        if 'Scrape_Date' in df.columns:
            df['Scrape_Date'] = pd.to_datetime(df['Scrape_Date'], errors='coerce')
            df = df.dropna(subset=['Scrape_Date'])
            df['Scrape_Date'] = df['Scrape_Date'].dt.strftime('%m/%d/%Y')

        for col in ['Station_ID', 'Name', 'Address']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip().replace('nan', '')

        df.to_csv(file_path, index=False)
        print("Data harmonization complete. Zero values removed and dates unified.")

    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"An error occurred during cleanup: {e}")


def sanitize_history_csv(file_path="station_price_history.csv"):
    """Same harmonization as above, but for the full-resolution history
    file: Scrape_Timestamp is a timestamp, not a calendar date, so it's
    validated (and unparseable rows dropped) without collapsing it down
    to a date - that would throw away the intraday precision this file
    exists to keep."""
    try:
        df = pd.read_csv(file_path, skipinitialspace=True)

        price_cols = ['Regular_Price', 'Plus_Price', 'Premium_Price']
        for col in price_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                df[col] = df[col].replace(0.0, np.nan)

        if 'Scrape_Timestamp' in df.columns:
            parsed = pd.to_datetime(df['Scrape_Timestamp'], errors='coerce', utc=True)
            df = df[parsed.notna()]

        for col in ['Station_ID', 'Name', 'Address']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip().replace('nan', '')

        df.to_csv(file_path, index=False)
        print("History dataset harmonization complete.")

    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"An error occurred during history cleanup: {e}")


if __name__ == "__main__":
    sanitize_and_unify_csv()
    sanitize_history_csv()
