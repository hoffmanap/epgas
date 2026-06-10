import datetime
import re
import os
from playwright.sync_api import sync_playwright

# List of distinct geographic search queries across El Paso
TARGET_HUBS = [
    {"name": "Central / Downtown", "url": "https://www.google.com/maps/search/Gas+Stations+Central+El+Paso+TX/"},
    {"name": "West Side / Mesa Hills", "url": "https://www.google.com/maps/search/Gas+Stations+West+El+Paso+TX/"},
    {"name": "East Side / Cielo Vista", "url": "https://www.google.com/maps/search/Gas+Stations+East+El+Paso+TX/"},
    {"name": "Northeast / Dyer St", "url": "https://www.google.com/maps/search/Gas+Stations+Northeast+El+Paso+TX/"},
    {"name": "Lower Valley / Zaragosa", "url": "https://www.google.com/maps/search/Gas+Stations+Lower+Valley+El+Paso+TX/"},
    {"name": "Socorro / Horizon", "url": "https://www.google.com/maps/search/Gas+Stations+Socorro+Horizon+TX/"}
]

CSV_FILE = "el_paso_gas_prices.csv"

def extract_prices_directly(element):
    """
    Locates text containing money symbols ($X.XX) inside the card container.
    """
    raw_text = element.inner_text() or ""
    prices = re.findall(r'\$(\d+\.\d{2})', raw_text)
    
    reg_price, plus_price, prem_price = "", "", ""
    
    if len(prices) >= 1:
        reg_price = prices[0]
    if len(prices) >= 2:
        plus_price = prices[1]
    if len(prices) >= 3:
        prem_price = prices[2]
        
    return reg_price, plus_price, prem_price

def run_pipeline():
    current_date = datetime.datetime.now().strftime("%m/%d/%Y")
    print(f"--- Launching Multi-Location Scraping Pipeline for {current_date} ---")
    
    seen_stations = set()
    all_parsed_records = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()
        page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "font", "media"] else route.continue_())
        
        for hub in TARGET_HUBS:
            print(f"\nScanning Sector: {hub['name']}...")
            try:
                page.goto(hub["url"], wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(6000)
                
                elements = page.locator('div[role="article"]').all()
                if not elements:
                    elements = page.locator('div.Nv2PK').all()
                
                print(f" -> Found {len(elements)} potential listings in this view.")
                
                for element in elements:
                    try:
                        station_name = element.get_attribute("aria-label") or "Unknown Station"
                        if "unknown" in station_name.lower() or not station_name.strip():
                            continue
                            
                        reg_price, plus_price, prem_price = extract_prices_directly(element)
                        
                        # Fallback: if no prices are visible, skip to avoid appending incomplete data
                        if not reg_price:
                            continue
                        
                        text_content = element.inner_text() or ""
                        address = "El Paso, TX"
                        address_match = re.search(r'·\s*([^·\n\d]*\d+[^·\n]*)', text_content)
                        if address_match:
                            address = address_match.group(1).strip().replace('\n', ' ')
                        
                        station_signature = f"{station_name.lower()}|{address.lower()}"
                        if station_signature in seen_stations:
                            continue
                            
                        seen_stations.add(station_signature)
                        
                        # Create clean lowercase Station_ID token
                        station_id = re.sub(r'[^a-z0-9\s-]', '', station_name.lower())
                        station_id = re.sub(r'[\s]+', '-', station_id).strip('-')

                        all_parsed_records.append({
                            "Station_ID": station_id,
                            "Name": station_name,
                            "Address": address,
                            "Latitude": "",
                            "Longitude": "",
                            "Regular_Price": reg_price,
                            "Plus_Price": plus_price,
                            "Premium_Price": prem_price,
                            "Scrape_Date": current_date
                        })
                        
                    except Exception as elem_err:
                        continue
                        
            except Exception as nav_err:
                print(f"   Skipped hub {hub['name']} due to navigation timeout.")
                continue
                
        browser.close()
        
    # Write aggregated metrics safely using the exact original schema headers
    if all_parsed_records:
        file_exists = os.path.exists(CSV_FILE)
        
        with open(CSV_FILE, mode="a", encoding="utf-8") as f:
            if not file_exists:
                f.write("Station_ID,Name,Address,Latitude,Longitude,Regular_Price,Plus_Price,Premium_Price,Scrape_Date\n")
            
            for record in all_parsed_records:
                line = f'"{record["Station_ID"]}","{record["Name"]}","{record["Address"]}","{record["Latitude"]}","{record["Longitude"]}","{record["Regular_Price"]}","{record["Plus_Price"]}","{record["Premium_Price"]}","{record["Scrape_Date"]}"\n'
                f.write(line)
                
        print(f"\nPipeline finished. Added {len(all_parsed_records)} unique gas stations with valid tracking schemas.")
    else:
        print("\nWarning: No records with valid price details found during this sweep.")

if __name__ == "__main__":
    run_pipeline()