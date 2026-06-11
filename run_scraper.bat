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

:: Pull online updates first to reconcile out-of-sync tracking trees
echo Fetching latest updates from GitHub server...
git pull origin main --rebase

:: Explicitly stage changes to override OneDrive locks
git add -f el_paso_gas_prices.csv
git add -A

:: Commit the data with a dynamic timestamp message
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set current_date=%datetime:~4,2%/%datetime:~6,2%/%datetime:~0,4%

git commit -m "Automated data sync: %current_date%"

:: Push the combined live data metrics to your repository
echo Pushing updates to repository server...
git push origin main

echo ===================================================
echo   SUCCESS: Pipeline execution complete!
echo ===================================================

:end
pause