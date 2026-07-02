@echo off
echo ===================================================
echo   STEP 1: Running Daily Gas Price Web Scraper...
echo ===================================================
python scraper.py

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Scraper encountered a critical crash! Skipping data upload.
    goto end
)

echo ===================================================
echo   STEP 2: Running Database Cleanup...
echo ===================================================
python clean_data.py

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Data cleanup failed! Skipping data upload.
    goto end
)

echo ===================================================
echo   STEP 3: Syncing Cleaned Data to GitHub Pages...
echo ===================================================

:: Ensure execution context stays inside your project directory
cd /d "C:\Users\Angelica\OneDrive\EPGas"

:: Fetch updates just to align local indexes
echo Syncing tracking references with GitHub...
git fetch origin main

:: Clear Git's internal file cache to force it to notice the updated CSV file
git rm --cached el_paso_gas_prices.csv >nul 2>&1

:: Aggressively force-stage the specific data file and any other updates
git add -f el_paso_gas_prices.csv
git add -A

:: Generate a safe, reliable date/time string without relying on flaky WMIC commands
set current_timestamp=%date% %time%

echo Committing new data points...
git commit -m "Automated data sync: %current_timestamp%"

:: FORCE push the local spreadsheet database to completely bypass OneDrive sync loops
echo Overwriting server data with fresh local database...
git push origin main --force

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Git push failed! Check your network or GitHub credentials.
    goto end
)

echo ===================================================
echo   SUCCESS: Pipeline execution complete!
echo ===================================================

:end
pause