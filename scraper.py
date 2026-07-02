import datetime
import re
import os
import urllib.parse
from playwright.sync_api import sync_playwright

# Complete list of live geographic search targets using Google Maps queries
TARGET_HUBS = [
    {"name": "Central / Downtown", "query": "gas stations in Central Downtown El Paso TX"},
    {"name": "West Side / Mesa Hills", "query": "gas stations in West Side Mesa Hills El Paso TX"},
    {"name": "East Side / Cielo Vista", "query": "gas stations in East Side Cielo Vista El Paso TX"},
    {"name": "Northeast / Dyer St", "query": "gas stations in Northeast Dyer St El Paso TX"},
    {"name": "Lower Valley / Zaragosa", "query": "gas stations in Lower Valley Zaragosa El Paso TX"},
    {"name": "Socorro / Horizon", "query": "gas stations in Socorro Horizon El Paso TX"},
    {"name": "Far East Montana", "query": "gas stations in Far East Montana El Paso TX"}
]

CSV_FILE = "el_paso_gas_prices.csv"

def parse_listing_text_block(text_content, hub_name):
    """
    Parses a raw text block from a Google Maps element to extract Name, Address, and Price.
    """
    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    if not lines:
        return None
        
    station_name = lines[0]
    
    # Extract Price: Look for numbers matching gas prices (e.g., $3.45 or 3.45)
    reg_price = None
    price_matches = re.findall(r"\b\$?\d\.\d{2}\b", text_content)
    if price_matches:
        # Take the first match and strip the dollar sign if present
        reg_price = float(price_matches[0].replace("$", ""))
        
    # If no price is listed in this block, skip it to avoid empty entries
    if not reg_price:
        return None
        
    # Extract Address: Look for standard street abbreviations or El Paso text
    address_str = f"El Paso, TX ({hub_name})"
    address_patterns = [
        r"\d+\s+[A-Za-z0-9\s\.\-]+(?:St|Ave|Blvd|Dr|Rd|Ln|Way|Ct|Cir|Hwy|Loop|Gtwy)\b",
        r"[A-Za-z0-9\s\.\-]+,\s*El\s*Paso"
    ]
    
    for pattern in address_patterns:
        addr_match = re.search(pattern, text_content, re.IGNORECASE)
        if addr_match:
            address_str = addr_match.group(0).strip()
            break
            
    # Final cleanup to keep the CSV well-formatted
    station_name = station_name.replace('"', '').replace(',', ' ')
    address_str = address_str.replace('"', '').replace(',', ' ')
    
    return {
        "Name": station_name,
        "Address": address_str,
        "Regular_Price": reg_price
    }

def run():
    all_parsed_records = []
    current_date = datetime.datetime.now().strftime("%m/%d/%Y")
    
    with sync_playwright() as playwright:
        # Launch browser with anti-detection flags
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()
        
        # Block heavy visual elements to increase rendering speeds
        page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "font"] else route.continue_())
        
        for hub in TARGET_HUBS:
            print(f"Scraping geographic target matrix section: {hub['name']}...")
            try:
                # Generate URL and navigate
                encoded_query = urllib.parse.quote(hub["query"])
                maps_url = f"https://www.google.com/maps/search/{encoded_query}"
                
                page.goto(maps_url, wait_until="load", timeout=60000)
                page.wait_for_timeout(5000) # Give dynamic panels full time to settle text rows
                
                # Broad capture: Grab ALL links or structural elements that look like a location entry
                elements = page.query_selector_all("a[href*='/maps/place/'], [role='article'], div[jsaction*='pane.wfvdfl']")
                
                for index, element in enumerate(elements):
                    try:
                        text_content = element.text_content()
                        if not text_content or len(text_content.strip()) < 10:
                            continue
                            
                        # Extract data points purely via text parsing logic
                        parsed_data = parse_listing_text_block(text_content, hub["name"])
                        
                        if parsed_data:
                            # Extract link attributes safely for metadata strings
                            station_url = element.get_attribute("href") or ""
                            
                            # Build a reliable Station ID string
                            if station_url and "/maps/place/" in station_url:
                                parts = station_url.split('/maps/place/')
                                station_id = re.sub(r'[^a-zA-Z0-9\-]', '', parts[1].split('/')[0])[:40].lower()
                            else:
                                clean_name = re.sub(r'[^a-z0-9]', '', parsed_data["Name"].lower())[:15]
                                station_id = f"station_{clean_name}_{index}"
                                
                            # Capture positional GPS coordinates if available in the url
                            lat, lng = "", ""
                            if station_url and "!3d" in station_url:
                                coords_match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', station_url)
                                if coords_match:
                                    lat = coords_match.group(1)
                                    lng = coords_match.group(2)
                                    
                            all_parsed_records.append({
                                "Station_ID": station_id,
                                "Name": parsed_data["Name"],
                                "Address": parsed_data["Address"],
                                "Latitude": lat,
                                "Longitude": lng,
                                "Regular_Price": parsed_data["Regular_Price"],
                                "Plus_Price": "",
                                "Premium_Price": "",
                                "Scrape_Date": current_date
                            })
                    except Exception:
                        continue
                        
            except Exception as nav_err:
                print(f"   Skipped hub {hub['name']} due to connection layout timeout.")
                continue
                
        browser.close()
        
    # Write entries out directly matching database column header tracking schema
    if all_parsed_records:
        # Deduplicate records grabbed multiple times due to broad element selectors
        unique_records = {}
        for rec in all_parsed_records:
            unique_key = f"{rec['Name']}_{rec['Regular_Price']}"
            unique_records[unique_key] = rec
            
        file_exists = os.path.exists(CSV_FILE)
        with open(CSV_FILE, mode="a", encoding="utf-8") as f:
            if not file_exists:
                f.write("Station_ID,Name,Address,Latitude,Longitude,Regular_Price,Plus_Price,Premium_Price,Scrape_Date\n")
            
            for record in unique_records.values():
                line = f'"{record["Station_ID"]}","{record["Name"]}","{record["Address"]}","{record["Latitude"]}","{record["Longitude"]}","{record["Regular_Price"]}","{record["Plus_Price"]}","{record["Premium_Price"]}","{record["Scrape_Date"]}"\n'
                f.write(line)
                
        print(f"\nPipeline finished. Added {len(unique_records)} unique gas stations with coordinates across all El Paso sectors.")
    else:
        print("\nWarning: No records with valid price details found during this sweep.")

if __name__ == "__main__":
    run()