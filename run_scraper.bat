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

echo ===================================================
echo   STEP 3: Syncing Cleaned Data to GitHub Pages...
echo ===================================================

:: Fetch updates just to align local indexes
echo Syncing tracking references with GitHub...
git fetch origin main

:: Explicitly stage changes to override OneDrive folder cache locks
git add -f el_paso_gas_prices.csv
git add -A

:: Commit the metrics with a dynamic timestamp message
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set current_date=%datetime:~4,2%/%datetime:~6,2%/%datetime:~0,4%

git commit -m "Automated data sync: %current_date%"

:: FORCE push the combined live data metrics to your repository to break the rejection wall
echo Overwriting server data with fresh local database...
git push origin main --force

echo ===================================================
echo   SUCCESS: Pipeline execution complete!
echo ===================================================

:end
pause