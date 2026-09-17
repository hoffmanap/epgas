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
        
        # Deep scroll map pane to force all station cards to load into the DOM
        for _ in range(6): 
            try:
                await page.mouse.move(200, 400)
                await page.mouse.wheel(0, 3000)
                await page.wait_for_timeout(1000)
            except Exception:
                pass

        # We cap at 35 to ensure the script completes before timing out
        for i in range(35):
            try:
                # Re-query cards every loop to avoid "Detached Element" errors after navigating back
                cards = await page.query_selector_all('div[role="article"]')
                if i >= len(cards):
                    break
                
                card = cards[i]
                
                # Locate the station title
                name_elem = await card.query_selector('a[href*="/maps/place"]')
                if not name_elem:
                    name_elem = await card.query_selector('div.fontHeadlineSmall')
                
                if not name_elem:
                    continue

                name = await name_elem.get_attribute('aria-label')
                if not name:
                    name = await name_elem.inner_text()
                name = name.strip()

                # Click to expand the new detailed place panel shown in the image
                await name_elem.click()
                await page.wait_for_timeout(2500) 
                
                current_url = page.url
                station_lat, station_lng = None, None
                
                coord_match = re.search(r'@([-?\d\.]+),([-?\d\.]+)', current_url)
                if coord_match:
                    station_lat, station_lng = float(coord_match.group(1)), float(coord_match.group(2))
                else:
                    fallback_match = re.search(r'!3d([-?\d\.]+)!4d([-?\d\.]+)', current_url)
                    if fallback_match:
                        station_lat, station_lng = float(fallback_match.group(1)), float(fallback_match.group(2))

                # Scrape the entire expanded sidebar panel to capture the new price grid
                sidebar = await page.query_selector('div[role="main"]')
                panel_text = await sidebar.inner_text() if sidebar else await page.inner_text('body')

                # Regex specifically targets the $X.XX format from the grid (e.g., $4.50 *)
                found_prices = re.findall(r'\$\s*([2-6]\.\d{2})', panel_text)
                
                # Deduplicate and validate prices
                prices = []
                for p in found_prices:
                    try:
                        val = float(p)
                        if 2.00 <= val <= 6.50 and val not in prices:
                            prices.append(val)
                    except ValueError:
                        continue

                # The grid orders them logically: Regular, Midgrade (Plus), Premium
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
                    "Regular_Price": reg_price if reg_price > 0 else "", 
                    "Plus_Price": plus_price if plus_price > 0 else "",
                    "Premium_Price": prem_price if prem_price > 0 else "",
                    "Scrape_Date": current_date
                }

                # CRITICAL: Click the "Back" arrow to restore the list view so the loop can continue
                back_btn = await page.query_selector('button[aria-label="Back"]')
                if back_btn:
                    await back_btn.click()
                    await page.wait_for_timeout(1500)
                else:
                    # Failsafe if the back button is hidden
                    await page.goto(search_url)
                    await page.wait_for_timeout(4000)

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
        
        # Filter out rows where Regular_Price was not successfully scraped
        df_new = df_new[df_new['Regular_Price'] != ""]
        
        if not df_new.empty:
            if os.path.exists(csv_file):
                df_existing = pd.read_csv(csv_file)
                if not df_existing.empty:
                    df_final = pd.concat([df_existing, df_new], ignore_index=True)
                else:
                    df_final = df_new
                df_final.drop_duplicates(subset=["Station_ID", "Scrape_Date"], keep="last", inplace=True)
            else:
                df_final = df_new
                
            df_final.to_csv(csv_file, index=False)
            print(f"✅ Success! Updated dataset with {len(df_new)} valid pricing entries for {current_date}.")
        else:
            print(f"⚠️ Scan completed, but no valid pricing grids were found for {current_date}.")
    else:
        print("❌ Error: Map scanning completed but no pricing entities could be verified.")

if __name__ == "__main__":
    asyncio.run(main())