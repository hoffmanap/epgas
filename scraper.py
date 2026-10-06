"""
El Paso Gas Price Scraper (v2 - GasBuddy source)
=================================================
Google Maps started gating place-detail interactions behind a
"limited view" wall around 9/30/2026, which silently broke the old
click-into-card approach (every result card was covered by an
invisible overlay, so no price grid could ever be opened).

This version pulls the same station-level, geolocated price data from
GasBuddy instead, which renders price data without needing an
authenticated session. It also self-expands its own station list over
time: every station detail page links out to a handful of "nearby"
stations, so each run that finds a brand-new station adds it to
station_master.csv for all future runs.

Designed to run unattended (e.g. via GitHub Actions / cron) with no
dependency on a specific machine or residential IP.
"""

import os
import re
import json
import random
import asyncio
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

STATION_MASTER_FILE = "station_master.csv"
LISTING_STATE_FILE = "listing_state.json"
OUTPUT_CSV = "el_paso_gas_prices.csv"
SEARCH_TERM = "El Paso, TX"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# Map GasBuddy's fuel grade labels onto the dashboard's existing schema
FUEL_LABEL_MAP = {
    "Regular": "Regular_Price",
    "Midgrade": "Plus_Price",
    "Premium": "Premium_Price",
}

# Safety cap so a single run can never balloon out of control if the
# "nearby" discovery graph turns out to be larger than expected.
MAX_NEW_STATIONS_PER_RUN = 60


def extract_apollo_state(html):
    """Pull the window.__APOLLO_STATE__ JSON blob out of a GasBuddy page."""
    marker = "window.__APOLLO_STATE__ = "
    idx = html.find(marker)
    if idx == -1:
        return None
    start = html.find("{", idx)
    depth = 0
    in_str = False
    esc = False
    end = None
    for i in range(start, len(html)):
        c = html[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
    if end is None:
        return None
    try:
        return json.loads(html[start:end])
    except json.JSONDecodeError:
        return None


def format_address(addr):
    if not addr:
        return "El Paso, TX"
    parts = [addr.get("line1", ""), addr.get("locality", ""), addr.get("region", "")]
    return ", ".join(p for p in parts if p)


async def load_station_master():
    if os.path.exists(STATION_MASTER_FILE):
        df = pd.read_csv(STATION_MASTER_FILE, dtype=str)
        return {row["Station_ID"]: row.to_dict() for _, row in df.iterrows()}
    return {}


def save_station_master(stations):
    df = pd.DataFrame(stations.values())
    if not df.empty:
        df = df.sort_values("Station_ID")
    df.to_csv(STATION_MASTER_FILE, index=False)


MAX_LISTING_PAGES = 20  # safety cap: 20 pages * 20/page = up to 400 stations per run


def load_listing_state():
    if os.path.exists(LISTING_STATE_FILE):
        try:
            with open(LISTING_STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"cursor": 0, "total_count": None}


def save_listing_state(state):
    with open(LISTING_STATE_FILE, "w") as f:
        json.dump(state, f)


async def discover_from_city_listing(page, stations):
    """Walk GasBuddy's city-wide search results (paginated via &cursor=)
    every run, not just once. The organic 'nearby station' graph only
    grows outward from wherever it started, so it crawls one
    neighborhood at a time and can take many runs to reach the far
    side of a city. The city search index itself has no such
    geographic bias, so paging through it directly is a much faster
    way to pick up new stations in every part of town right away.

    GasBuddy's Cloudflare check frequently blocks this past the very
    first page in a given run (sometimes even the first page), so a
    run often only gets one page through before giving up. To make
    progress anyway, where we left off is persisted across runs
    (listing_state.json) instead of restarting at cursor=0 every
    time, so a slow trickle of successful single-page fetches still
    walks the whole index eventually rather than re-fetching the same
    page over and over. Once the end of the index is reached, the
    cursor wraps back to 0 so a later pass can pick up stations added
    to GasBuddy after the first full walk."""
    added = 0
    state = load_listing_state()
    cursor = state.get("cursor", 0) or 0
    total_count = state.get("total_count")
    reached_end = False
    for _ in range(MAX_LISTING_PAGES):
        url = (
            f"https://www.gasbuddy.com/home?search={SEARCH_TERM.replace(' ', '+').replace(',', '%2C')}"
            f"&fuel=1&cursor={cursor}"
        )
        try:
            await page.goto(url, timeout=45000)
            await page.wait_for_timeout(1200)
            html = await page.content()
        except Exception as err:
            print(f"⚠️ City listing page at cursor={cursor} failed to load: {err}")
            break  # transient failure - resume at this same cursor next run

        data = extract_apollo_state(html)
        if not data:
            print(f"⚠️ Could not read city listing at cursor={cursor} (may have been challenged).")
            break  # challenged - resume at this same cursor next run

        loc_key = next((k for k in data if k.startswith("Location:")), None)
        if not loc_key:
            break
        loc = data[loc_key]
        stations_key = next((k for k in loc if k.startswith("stations(")), None)
        if not stations_key:
            break
        sdata = loc[stations_key]
        total_count = sdata.get("count", total_count)
        refs = sdata.get("results", [])
        if not refs:
            reached_end = True
            break

        for ref in refs:
            sid = ref["__ref"].split(":")[1]
            if sid not in stations:
                obj = data.get(ref["__ref"], {})
                stations[sid] = {
                    "Station_ID": sid,
                    "Name": obj.get("name", ""),
                    "Address": format_address(obj.get("address")),
                    "Latitude": "",
                    "Longitude": "",
                }
                added += 1

        nxt = sdata.get("cursor", {}).get("next")
        if not nxt:
            reached_end = True
            break
        cursor = int(nxt)
        if total_count is not None and cursor >= total_count:
            reached_end = True
            break
        await asyncio.sleep(random.uniform(0.4, 0.9))

    # Persist where we left off so the next run resumes further into the
    # index instead of re-fetching page one again. On reaching the end,
    # wrap back to 0 so a future pass can catch newly listed stations.
    save_listing_state({"cursor": 0 if reached_end else cursor, "total_count": total_count})

    if added:
        print(f"🌱 City listing added {added} new station(s) (master list now {len(stations)}), next cursor={0 if reached_end else cursor}.")
    else:
        print(f"🌱 City listing found no new stations this run (next cursor={0 if reached_end else cursor}).")


async def scrape_station(page, station_id):
    """Visit one station's detail page and return its current prices,
    its own master-list fields, and any brand-new nearby station ids
    this run has not seen before (id + name + address only; those get
    their own lat/lon the first time they are actually visited)."""
    url = f"https://www.gasbuddy.com/station/{station_id}"
    await page.goto(url, timeout=45000)

    try:
        await page.wait_for_function(
            """() => {
                const els = document.querySelectorAll('[class*="priceDisplay"]');
                if (els.length === 0) return false;
                return Array.from(els).every(e => !e.querySelector('[class*="loader"]'));
            }""",
            timeout=15000,
        )
    except Exception:
        pass  # fall through and parse whatever rendered

    await page.wait_for_timeout(400)
    html = await page.content()

    apollo = extract_apollo_state(html)
    station_obj = apollo.get(f"Station:{station_id}") if apollo else None

    master_fields = None
    if station_obj:
        master_fields = {
            "Station_ID": station_id,
            "Name": station_obj.get("name", ""),
            "Address": format_address(station_obj.get("address")),
            "Latitude": station_obj.get("latitude", ""),
            "Longitude": station_obj.get("longitude", ""),
        }

    prices = {"Regular_Price": "", "Plus_Price": "", "Premium_Price": ""}
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find("h2", string=re.compile("Station Prices"))
    if heading:
        panel = heading.find_parent("div").find_next_sibling("div")
        if panel:
            labels = [l.get_text(strip=True) for l in panel.select('[class*="fuelTypeDisplay"]')]
            price_divs = panel.select('[class*="priceDisplay"]')
            for label, pdiv in zip(labels, price_divs):
                col = FUEL_LABEL_MAP.get(label)
                if not col:
                    continue
                text = pdiv.get_text(" ", strip=True)
                m = re.search(r"\$\s*([\d.]+)", text)
                if m:
                    prices[col] = m.group(1)

    # Harvest nearby station stubs for future-run discovery.
    new_nearby = {}
    if station_obj:
        for ref in station_obj.get("nearby", []):
            nid = ref.get("__ref", "").split(":")[-1]
            if nid and nid not in new_nearby:
                nearby_obj = apollo.get(ref["__ref"], {})
                new_nearby[nid] = {
                    "Station_ID": nid,
                    "Name": nearby_obj.get("name", ""),
                    "Address": "",
                    "Latitude": "",
                    "Longitude": "",
                }

    return master_fields, prices, new_nearby


async def main():
    current_date = pd.Timestamp.now().strftime("%m/%d/%Y")
    stations = await load_station_master()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900}, user_agent=USER_AGENT
        )
        page = await context.new_page()

        await discover_from_city_listing(page, stations)
        await asyncio.sleep(1)

        rows = []
        visited_ids = list(stations.keys())
        new_ids_this_run = []
        failures = []

        for sid in visited_ids:
            try:
                master_fields, prices, new_nearby = await scrape_station(page, sid)
            except Exception as err:
                failures.append(sid)
                print(f"⚠️ Failed to scrape station {sid}: {err}")
                await asyncio.sleep(random.uniform(0.5, 1.2))
                continue

            if master_fields:
                stations[sid].update(master_fields)

            if any(prices.values()):
                row = {
                    "Station_ID": sid,
                    "Name": stations[sid].get("Name", ""),
                    "Address": stations[sid].get("Address", "El Paso, TX"),
                    "Latitude": stations[sid].get("Latitude", ""),
                    "Longitude": stations[sid].get("Longitude", ""),
                    "Regular_Price": prices["Regular_Price"],
                    "Plus_Price": prices["Plus_Price"],
                    "Premium_Price": prices["Premium_Price"],
                    "Scrape_Date": current_date,
                }
                rows.append(row)

            for nid, stub in new_nearby.items():
                if nid not in stations and nid not in [x[0] for x in new_ids_this_run]:
                    if len(new_ids_this_run) < MAX_NEW_STATIONS_PER_RUN:
                        new_ids_this_run.append((nid, stub))

            await asyncio.sleep(random.uniform(0.4, 0.9))

        # Visit newly discovered stations in this same run so they get
        # full lat/lon + a price reading immediately instead of waiting
        # for the next scheduled run.
        for nid, stub in new_ids_this_run:
            stations[nid] = stub
            try:
                master_fields, prices, _ = await scrape_station(page, nid)
            except Exception as err:
                failures.append(nid)
                print(f"⚠️ Failed to scrape newly discovered station {nid}: {err}")
                continue

            if master_fields:
                stations[nid].update(master_fields)

            if any(prices.values()):
                rows.append({
                    "Station_ID": nid,
                    "Name": stations[nid].get("Name", ""),
                    "Address": stations[nid].get("Address", "El Paso, TX"),
                    "Latitude": stations[nid].get("Latitude", ""),
                    "Longitude": stations[nid].get("Longitude", ""),
                    "Regular_Price": prices["Regular_Price"],
                    "Plus_Price": prices["Plus_Price"],
                    "Premium_Price": prices["Premium_Price"],
                    "Scrape_Date": current_date,
                })
            await asyncio.sleep(random.uniform(0.4, 0.9))

        await browser.close()

    save_station_master(stations)

    if rows:
        df_new = pd.DataFrame(rows)
        df_new = df_new[df_new["Regular_Price"] != ""]

        if not df_new.empty:
            if os.path.exists(OUTPUT_CSV):
                df_existing = pd.read_csv(OUTPUT_CSV)
                df_final = pd.concat([df_existing, df_new], ignore_index=True)
                df_final.drop_duplicates(subset=["Station_ID", "Scrape_Date"], keep="last", inplace=True)
            else:
                df_final = df_new
            df_final.to_csv(OUTPUT_CSV, index=False)
            print(f"✅ Success! Updated dataset with {len(df_new)} valid pricing entries for {current_date}.")
            if new_ids_this_run:
                print(f"🔎 Discovered {len(new_ids_this_run)} new station(s) this run.")
            if failures:
                print(f"⚠️ {len(failures)} station(s) failed to load and were skipped: {failures}")
        else:
            print(f"⚠️ Scan completed, but no valid pricing grids were found for {current_date}.")
    else:
        print("❌ Error: No pricing data could be collected this run.")


if __name__ == "__main__":
    asyncio.run(main())
