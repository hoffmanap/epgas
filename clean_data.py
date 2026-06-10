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
        
    except Exception as e:
        print(f"An error occurred during cleanup: {e}")

if __name__ == "__main__":
    sanitize_and_unify_csv()