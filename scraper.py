import datetime
import re
import os
from playwright.sync_api import sync_playwright

# List of distinct geographic search coordinates/queries across El Paso to widen coverage
TARGET_HUBS = [
    {"name": "Central / Downtown", "url": "https://www.google.com/maps/search/Gas+Stations+Central+El+Paso+TX/"},
    {"name": "West Side / Mesa Hills", "url": "https://www.google.com/maps/search/Gas+Stations+West+El+Paso+TX/"},
    {"name": "East Side / Cielo Vista", "url": "https://www.google.com/maps/search/Gas+Stations+East+El+Paso+TX/"},
    {"name": "Northeast / Dyer St", "url": "https://www.google.com/maps/search/Gas+Stations+Northeast+El+Paso+TX/"},
    {"name": "Lower Valley / Zaragosa", "url": "https://www.google.com/maps/search/Gas+Stations+Lower+Valley+El+Paso+TX/"},
    {"name": "Socorro / Horizon", "url": "https://www.google.com/maps/search/Gas+Stations+Socorro+Horizon+TX/"}
]

CSV_FILE = "el_paso_gas_prices.csv"

def extract_prices_from_text(text):
    """
    Scans the raw element innerText for price listings.
    Defaults to empty string if missing to avoid breaking statistical averages.
    """
    price_pattern = re.compile(r'\$\s*(\d+\.\d{2})')
    matches = price_pattern.findall(text)
    
    reg, plus, prem = "", "", ""
    lower_text = text.lower()
    
    if "regular" in lower_text and matches:
        reg = matches[0]
    if "plus" in lower_text and len(matches) > 1:
        plus = matches[1]
    if "premium" in lower_text and len(matches) > 2:
        prem = matches[2]
        
    if not reg and matches:
        reg = matches[0]
        
    return reg, plus, prem

def run_pipeline():
    current_date = datetime.datetime.now().strftime("%m/%d/%Y")
    print(f"--- Launching Multi-Location Scraping Pipeline for {current_date} ---")
    
    # Track unique combinations of (Station Name + Address) to prevent local duplication 
    seen_stations = set()
    all_parsed_records = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()
        # Speed optimization: block heavy images and fonts
        page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "font", "media"] else route.continue_())
        
        # Loop through each distinct sector of the city
        for hub in TARGET_HUBS:
            print(f"\nScanning Sector: {hub['name']}...")
            try:
                page.goto(hub["url"], wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(5000) # Quick pause for data rows to settle
                
                # Attempt to find standard map list view markers
                elements = page.locator('div[role="article"]').all()
                if not elements:
                    elements = page.locator('div.Nv2PK').all()
                
                print(f" -> Found {len(elements)} potential listings in this view.")
                
                for element in elements:
                    try:
                        text_content = element.inner_text()
                        if not text_content:
                            continue
                            
                        station_name = element.get_attribute("aria-label") or "Unknown Station"
                        reg_price, plus_price, prem_price = extract_prices_from_text(text_content)
                        
                        # Extract basic street address details from text block
                        address = "El Paso, TX"
                        address_match = re.search(r'·\s*([^·\n\d]*\d+[^·\n]*)', text_content)
                        if address_match:
                            address = address_match.group(1).strip()
                        
                        # Clean out line breaks if any snuck into address field
                        address = address.replace('\n', ' ').strip()
                        
                        # De-duplication check matching name + address signature
                        station_signature = f"{station_name.lower()}|{address.lower()}"
                        if station_signature in seen_stations:
                            continue
                            
                        seen_stations.add(station_signature)
                        
                        all_parsed_records.append({
                            "Date": current_date,
                            "Station": station_name,
                            "Address": address,
                            "Regular": reg_price,
                            "Plus": plus_price,
                            "Premium": prem_price
                        })
                        
                    except Exception as elem_err:
                        continue
                        
            except Exception as nav_err:
                print(f"   Skipped hub {hub['name']} due to navigation timeout.")
                continue
                
        browser.close()
        
    # Write aggregated metrics safely to the historical log
    if all_parsed_records:
        file_exists = os.path.exists(CSV_FILE)
        
        with open(CSV_FILE, mode="a", encoding="utf-8") as f:
            if not file_exists:
                f.write("Date,Station,Address,Regular,Plus,Premium\n")
            
            for record in all_parsed_records:
                line = f'"{record["Date"]}","{record["Station"]}","{record["Address"]}","{record["Regular"]}","{record["Plus"]}","{record["Premium"]}"\n'
                f.write(line)
                
        print(f"\nPipeline finished. Added {len(all_parsed_records)} unique gas stations across El Paso.")
    else:
        print("\nWarning: No records were processed during this citywide sweep.")

if __name__ == "__main__":
    run_pipeline()