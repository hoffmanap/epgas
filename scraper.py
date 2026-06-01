import os
import re
import time
import asyncio
import pandas as pd
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def scrape_zip(context, zipcode):
    stations = {}
    page = await context.new_page()
    
    # Enable anti-fingerprinting stealth layers
    stealth = Stealth()
    await stealth.apply_stealth_async(page)
    
    # Direct Google Maps search string for the target El Paso zip code
    search_url = f"https://www.google.com/maps/search/gas+stations+in+El+Paso,+TX+{zipcode}/"
    print(f"Searching Google Maps for Zip: {zipcode}...")
    
    try:
        await page.goto(search_url, timeout=60000)
        await page.wait_for_timeout(5000)
        
        # Deep scroll the sidebar to reveal dozens of hidden stations
        print("Scrolling sidebar deeply to load maximum stations...")
        for _ in range(10): 
            try:
                await page.mouse.move(200, 400) # Anchor pointer over sidebar listing
                await page.mouse.wheel(0, 4000) # Rapid vertical wheel scroll
                await page.wait_for_timeout(1500)
            except Exception:
                pass

        # Locate individual result elements
        cards = await page.query_selector_all('div[role="article"]')
        print(f"-> Found {len(cards)} potential locations for {zipcode}. Processing coordinates...")
        
        # Increased cap to process up to 60 cards per zip code sector
        for card in cards[:60]:
            try:
                # Extract business text name
                name_elem = await card.query_selector('.hfpxzc')
                if not name_elem:
                    continue
                name = await name_elem.get_attribute('aria-label')
                
                # CLICK THE CARD: Expands the item pane and alters the URL to expose coordinates
                await name_elem.click()
                await page.wait_for_timeout(3000) 
                
                current_url = page.url
                lat, lng = None, None
                
                # Check for standard coordinate URL tags (@Latitude,Longitude)
                coord_match = re.search(r'@([-?\d\.]+),([-?\d\.]+)', current_url)
                if coord_match:
                    lat = float(coord_match.group(1))
                    lng = float(coord_match.group(2))
                else:
                    # Secondary fallback matrix matching patterns (!3d... !4d...)
                    fallback_match = re.search(r'!3d([-?\d\.]+)!4d([-?\d\.]+)', current_url)
                    if fallback_match:
                        lat = float(fallback_match.group(1))
                        lng = float(fallback_match.group(2))

                # Parse prices from card body text strings
                info_text = await card.inner_text()
                found_prices = re.findall(r'\b\d\.\d{2}\b', info_text)
                prices = [float(p) for p in found_prices]
                
                reg_price, plus_price, prem_price = None, None, None
                if len(prices) >= 1: reg_price = prices[0]
                if len(prices) >= 2: plus_price = prices[1]
                if len(prices) >= 3: prem_price = prices[2]

                # Place safe baseline placeholders if numbers are currently unpainted on screen
                if not reg_price:
                    reg_price, plus_price, prem_price = 0.0, 0.0, 0.0

                station_id = name.lower().replace(" ", "-").replace(",", "").replace(".", "").strip()
                unique_key = f"{station_id}-{current_date}"
                
                stations[unique_key] = {
                    "Station_ID": station_id,
                    "Name": name,
                    "Address": f"El Paso, TX {zipcode}",
                    "Latitude": lat,
                    "Longitude": lng,
                    "Regular_Price": reg_price,
                    "Plus_Price": plus_price,
                    "Premium_Price": prem_price,
                    "Scrape_Date": current_date
                }
            except Exception:
                continue
                
    except Exception as err:
        print(f"⚠️ Navigation challenge on zip {zipcode}: {err}")
    finally:
        await page.close()
        
    return stations

async def main():
    # Complete 15 zip code array to blanketing the entire El Paso footprint
    el_paso_zips = [
        "79901", "79902", "79903", "79904", "79905", 
        "79912", "79915", "79924", "79925", "79930", 
        "79932", "79934", "79935", "79936", "79938"
    ]
    all_stations = {}
    global current_date
    current_date = pd.Timestamp.now().strftime('%Y-%m-%d')
    
    async with async_playwright() as p:
        print("Launching stealth browser automation layer...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        )
        
        for zipcode in el_paso_zips:
            zip_data = await scrape_zip(context, zipcode)
            all_stations.update(zip_data)
            await asyncio.sleep(2)
            
        await browser.close()

    # Consolidate and Append File Frameworks
    if all_stations:
        df_new = pd.DataFrame(all_stations.values())
        csv_file = "el_paso_gas_prices.csv"
        
        if os.path.exists(csv_file):
            df_existing = pd.read_csv(csv_file)
            df_final = pd.concat([df_existing, df_new], ignore_index=True)
            df_final.drop_duplicates(subset=["Station_ID", "Scrape_Date"], keep="last", inplace=True)
        else:
            df_final = df_new
            
        df_final.to_csv(csv_file, index=False)
        print(f"✅ Success! Local CSV updated with {len(df_new)} unique entries.")
        
        # SURGICAL REPOSITORY COMMIT AND SYNC PIPELINE
        print("🤖 Starting automated GitHub repository sync...")
        try:
            # Sync any remote changes before committing
            os.system("git pull origin main --rebase")
            
            # Explicitly target ONLY your data project assets
            os.system(f"git add {csv_file} scraper.py .gitignore README.md")
            os.system(f'git commit -m "Local Spatial Update: {current_date}"')
            os.system("git push origin main")
            print("🚀 Success! Changes fully synced and visible on your epgas GitHub dashboard!")
        except Exception as git_err:
            print(f"❌ Git Automation Error: {git_err}")
    else:
        print("❌ Error: Map scanning completed but no pricing entities could be verified.")

if __name__ == "__main__":
    asyncio.run(main())