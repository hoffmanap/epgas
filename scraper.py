import os
import re
import time
import asyncio
import subprocess
import pandas as pd
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def scrape_node(context, lat, lng, area_name):
    stations = {}
    page = await context.new_page()
    
    # Enable anti-fingerprinting stealth layers
    stealth = Stealth()
    await stealth.apply_stealth_async(page)
    
    # Use exact coordinates at a highly localized zoom level (15z)
    search_url = f"https://www.google.com/maps/search/gas+stations/@{lat},{lng},15z"
    print(f"Scanning Coordinate Node: {area_name} ({lat}, {lng})...")
    
    try:
        await page.goto(search_url, timeout=60000)
        await page.wait_for_timeout(5000)
        
        # Deep scroll the left results pane to force hidden stations to load
        print("  Scrolling map sidebar deeply...")
        for _ in range(8): 
            try:
                await page.mouse.move(200, 400) # Anchor pointer over sidebar listing
                await page.mouse.wheel(0, 4000) # Rapid vertical wheel scroll
                await page.wait_for_timeout(1200)
            except Exception:
                pass

        # Locate individual result elements
        cards = await page.query_selector_all('div[role="article"]')
        print(f"  -> Found {len(cards)} visual points. Extracting details...")
        
        # Parse through visible stations (capped at 50 entries per node for performance balance)
        for card in cards[:50]:
            try:
                # Extract business text name
                name_elem = await card.query_selector('.hfpxzc')
                if not name_elem:
                    continue
                name = await name_elem.get_attribute('aria-label')
                
                # CLICK THE CARD: Expands the item pane and alters the URL to expose coordinates
                await name_elem.click()
                await page.wait_for_timeout(2500) 
                
                current_url = page.url
                station_lat, station_lng = None, None
                
                # Check for standard coordinate URL tags (@Latitude,Longitude)
                coord_match = re.search(r'@([-?\d\.]+),([-?\d\.]+)', current_url)
                if coord_match:
                    station_lat = float(coord_match.group(1))
                    station_lng = float(coord_match.group(2))
                else:
                    # Secondary fallback matrix matching patterns (!3d... !4d...)
                    fallback_match = re.search(r'!3d([-?\d\.]+)!4d([-?\d\.]+)', current_url)
                    if fallback_match:
                        station_lat = float(fallback_match.group(1))
                        station_lng = float(fallback_match.group(2))

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
                    "Address": f"El Paso, TX ({area_name})",
                    "Latitude": station_lat,
                    "Longitude": station_lng,
                    "Regular_Price": reg_price,
                    "Plus_Price": plus_price,
                    "Premium_Price": prem_price,
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
    # A localized coordinates grid that blankets El Paso comprehensively from edge to edge
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
    current_date = pd.Timestamp.now().strftime('%Y-%m-%d')
    
    async with async_playwright() as p:
        print("Launching stealth browser automation layer...")
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
        
        # AUTOMATED REPOSITORY COMMIT AND SYNC PIPELINE
        print("🤖 Initiating GitHub repository sync execution...")
        repo_dir = r"C:\Users\Angelica\OneDrive\EPGas"
        
        def run_git(args):
            result = subprocess.run(args, cwd=repo_dir, capture_output=True, text=True, shell=True)
            if result.returncode != 0:
                print(f"   Git notice: {result.stderr.strip()}")
            return result.returncode == 0

        # Execute local sequencing scripts explicitly
        run_git(["git", "pull", "origin", "main", "--rebase"])
        run_git(["git", "add", "el_paso_gas_prices.csv", "scraper.py", ".gitignore", "README.md"])
        run_git(["git", "commit", "-m", f"Automated Spatial Sync: {current_date}"])
        
        print("🚀 Pushing data to online GitHub server...")
        if run_git(["git", "push", "origin", "main"]):
            print("🌟 Live Sync Complete! Your dataset is fully updated on GitHub.")
        else:
            print("❌ Push failed. Please verify your system git credentials.")
            
    else:
        print("❌ Error: Map scanning completed but no pricing entities could be verified.")

if __name__ == "__main__":
    asyncio.run(main())