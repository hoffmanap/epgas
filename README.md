# El Paso Spatial Gas Price Tracker (EPGas) 
## Dashboard: https://hoffmanap.github.io/epgas/ 

An automated data pipeline that extracts hyper-local, multi-grade fuel prices alongside spatial coordinates across El Paso, Texas. The resulting time-series dataset is explicitly structured to support geospatial analysis and mapping applications (QGIS, ArcGIS, CARTO).

## 📊 Dataset Schema
The pipeline automatically compiles and appends data daily into `el_paso_gas_prices.csv` using the following format:

| Column Name | Type | Description |
| :--- | :--- | :--- |
| `Station_ID` | String | Unique slug identifier matching the station name. |
| `Name` | String | Commercial brand name of the service station (e.g., Chevron, Circle K). |
| `Address` | String | Local street address including verified Zip Code. |
| `Latitude` | Float | Decimal coordinate point (WGS 84 format) for mapping geometry. |
| `Longitude` | Float | Decimal coordinate point (WGS 84 format) for mapping geometry. |
| `Regular_Price` | Float | Real-time price ($ USD) for 87 Octane gasoline. |
| `Plus_Price` | Float | Real-time price ($ USD) for 89 Octane gasoline. |
| `Premium_Price` | Float | Real-time price ($ USD) for 91/93 Octane gasoline. |
| `Scrape_Date` | String | Calendar execution timestamp (`YYYY-MM-DD`). |

## 🛠️ How the Data is Collected
As of October 2026, this pipeline sources prices from **GasBuddy**'s crowdsourced station data rather than Google Maps. (Google began gating place-detail interactions behind a sign-in wall in late September 2026, which silently broke the original Maps-based scraper — it kept running, but every click into a station card was blocked by an invisible overlay, so no prices were ever collected after 9/30.)

1. **Self-expanding station graph:** `station_master.csv` holds the list of known station IDs, names, addresses, and coordinates. Each station's detail page on GasBuddy links out to a handful of nearby stations, so every run that encounters an unfamiliar station ID automatically adds it to the master list — the coverage area grows on its own over time without needing a hardcoded geographic grid.
2. **Browser automation:** **Playwright** drives a headless Chromium instance to each known station's detail page and waits for the client-rendered price panel to resolve.
3. **Structured + text extraction:** Station metadata (name, address, latitude/longitude) comes from the page's embedded Apollo GraphQL cache (`window.__APOLLO_STATE__`); fuel grade prices (Regular/Midgrade/Premium) are parsed from the rendered price panel.
4. **Data deduplication:** A Python engine built on **Pandas** reads the existing CSV archive, appends the day's new readings, and drops duplicate station/date pairs before rewriting the dataset.

## 🚀 Automation & Synchronizing
The pipeline runs daily via a **GitHub Actions workflow** (`.github/workflows/scrape.yml`), so it no longer depends on any particular computer being powered on:
* A scheduled job spins up an Ubuntu runner, installs Playwright + Chromium, and runs `scraper.py` followed by `clean_data.py`.
* If the resulting CSV or station list changed, the workflow commits and pushes the update directly to `main` using the built-in `GITHUB_TOKEN` — which also refreshes the live GitHub Pages dashboard automatically.
* The workflow can also be triggered manually from the **Actions** tab (`workflow_dispatch`) at any time.