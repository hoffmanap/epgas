import os
import re
import time
import asyncio
import pandas as pd
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def scrape_node(context, lat, lng, area_name):
    stations = {}
    page = await context.new_page()
    stealth = Stealth()
    await stealth.apply_stealth_async(page)
    
    search_url = f"https://www.google.com/maps/search/gas+stations/@{lat},{lng},15z"
    print(f"Scanning Coordinate Node: {area_name}...")
    
    try:
        await page.goto(search_url, timeout=60000)
        await page.wait_for_timeout(4000)
        
        # Deep scroll map pane to force station cards to render
        for _ in range(6): 
            try:
                await page.mouse.move(200, 400)
                await page.mouse.wheel(0, 3000)
                await page.wait_for_timeout(1000)
            except Exception:
                pass

        cards = await page.query_selector_all('div[role="article"]')
        print(f"  -> Found {len(cards)} entries on grid node {area_name}.")
        
        for card in cards[:50]:
            try:
                # 1. Structural target for station title
                name_elem = await card.query_selector('a[href*="/maps/place"]')
                if not name_elem:
                    name_elem = await card.query_selector('div.fontHeadlineSmall')
                
                if not name_elem:
                    continue

                name = await name_elem.get_attribute('aria-label')
                if not name:
                    name = await name_elem.inner_text()
                name = name.strip()

                # 2. Extract Card Text (Primary Price Source)
                card_text = await card.inner_text()
                
                # Expand panel to force Google Maps to reveal hidden price DOM elements
                await name_elem.click()
                await page.wait_for_timeout(1800) 
                
                current_url = page.url
                station_lat, station_lng = None, None
                
                coord_match = re.search(r'@([-?\d\.]+),([-?\d\.]+)', current_url)
                if coord_match:
                    station_lat, station_lng = float(coord_match.group(1)), float(coord_match.group(2))
                else:
                    fallback_match = re.search(r'!3d([-?\d\.]+)!4d([-?\d\.]+)', current_url)
                    if fallback_match:
                        station_lat, station_lng = float(fallback_match.group(1)), float(fallback_match.group(2))

                # 3. Pull text from the expanded panel if main card was missing prices
                panel_text = ""
                try:
                    panel = await page.query_selector('div[role="main"]')
                    if panel:
                        panel_text = await panel.inner_text()
                except Exception:
                    pass

                combined_text = f"{card_text}\n{panel_text}"

                # 4. Universal Price Extraction Engine
                # Matches formats: $4.30, 4.30/Regular, $4.30/Gal, 4.30
                found_prices = re.findall(r'\$?([2-6]\.\d{2})(?:\s*\/|\s*Regular|\s*Gal|\b)', combined_text, re.IGNORECASE)
                
                # Convert strings to floats
                prices = []
                for p in found_prices:
                    try:
                        val = float(p)
                        if 2.00 <= val <= 6.50: # Valid fuel threshold guard
                            prices.append(val)
                    except ValueError:
                        continue

                reg_price, plus_price, prem_price = 0.0, 0.0, 0.0
                if len(prices) >= 1: reg_price = prices[0]
                if len(prices) >= 2: plus_price = prices[1]
                if len(prices) >= 3: prem_price = prices[2]

                station_id = name.lower().replace(" ", "-").replace(",", "").replace(".", "").replace("'", "").strip()
                unique_key = f"{station_id}-{current_date}"
                
                stations[unique_key] = {
                    "Station_ID": station_id, 
                    "Name": name, 
                    "Address": f"El Paso, TX ({area_name})",
                    "Latitude": station_lat, 
                    "Longitude": station_lng,
                    "Regular_Price": reg_price if reg_price > 0 else "", # Leave clean blank instead of 0.0
                    "Plus_Price": plus_price if plus_price > 0 else "",
                    "Premium_Price": prem_price if prem_price > 0 else "",
                    "Scrape_Date": current_date
                }
            except Exception:
                continue
                
    except Exception as err:
        print(f"⚠️ Navigation challenge on node {area_name}: {err}")
    finally:
        await page.close()
        
    return stations

async def main():
    el_paso_grid = [
        (31.7587, -106.4869, "Downtown_Central"), 
        (31.8344, -106.5294, "West_Side_Mesa"),
        (31.8792, -106.5542, "Upper_Valley"), 
        (31.8455, -106.4178, "Northeast_Dyer"),
        (31.7611, -106.3683, "East_Side_Cielo_Vista"), 
        (31.7455, -106.3012, "Zaragosa_Lower_Valley"),
        (31.8214, -106.2611, "Far_East_Montana"), 
        (31.6789, -106.2789, "Socorro_Horizon_Border")
    ]
    
    all_stations = {}
    global current_date
    current_date = pd.Timestamp.now().strftime('%m/%d/%Y')
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        )
        
        for lat, lng, area_name in el_paso_grid:
            node_data = await scrape_node(context, lat, lng, area_name)
            all_stations.update(node_data)
            await asyncio.sleep(2)
        await browser.close()

    if all_stations:
        df_new = pd.DataFrame(all_stations.values())
        csv_file = "el_paso_gas_prices.csv"
        
        # Remove empty rows where Regular_Price was not captured
        df_new = df_new[df_new['Regular_Price'] != ""]
        
        if os.path.exists(csv_file):
            df_existing = pd.read_csv(csv_file)
            df_final = pd.concat([df_existing, df_new], ignore_index=True)
            df_final.drop_duplicates(subset=["Station_ID", "Scrape_Date"], keep="last", inplace=True)
        else:
            df_final = df_new
            
        df_final.to_csv(csv_file, index=False)
        print(f"✅ Success! Updated dataset with {len(df_new)} valid pricing entries for {current_date}.")
    else:
        print("❌ Error: Map scanning completed but no pricing entities could be verified.")

if __name__ == "__main__":
    asyncio.run(main())