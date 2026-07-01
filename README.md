# El Paso Spatial Gas Price Tracker (EPGas)

## Live Dashbaord: https://hoffmanap.github.io/epgas/

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
Because consumer websites utilize restrictive data-center firewall rules (e.g., Cloudflare tracking tokens), standard API-scraping environments often face connection limits or blocks. This repository circumvents infrastructure barriers by deploying a local automation engine:

1. **Targeting Matrix:** The script evaluates a core geographical grid of target El Paso ZIP codes spanning the West Side, East Side, Northeast, and Lower Valley regions.
2. **Browser Emulation:** Utilizing **Playwright**, the pipeline launches a headless instance of Chromium modified with stealth fingerprinting layers (`playwright-stealth`) to simulate standard human navigation.
3. **Geospatial Point Mining:** The browser visits Google Maps search endpoints. To overcome lazy-loading limitations, it programmatically engages scrolling frames. It dynamically **clicks into each discovered station element**, triggering the live map pane to load and exposing the exact decimal `Latitude` and `Longitude` configurations embedded inside the browser's active window string.
4. **Data Deduplication:** A Python engine built on **Pandas** reads existing CSV archives, stacks the fresh coordinates and pricing layers, and drops duplicate station profiles recorded on the same calendar day before rewriting the database matrix.

## 🚀 Automation & Synchronizing
The system is managed via a local machine scheduler (Windows Task Scheduler / Mac Crontab) executing daily:
* It spins up headlessly using a residential internet service provider connection, sliding smoothly past cloud data-center blocklists.
* Upon processing, the script initiates sequential git sub-shell parameters (`git pull --rebase`, `git add`, `git commit`), publishing fresh tracking updates straight to this GitHub dashboard completely unattended.
