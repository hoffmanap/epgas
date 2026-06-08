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
