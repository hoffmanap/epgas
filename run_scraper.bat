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

:: Force stage everything inside the directory (CSV, HTML, scripts)
git add -A

:: Commit the data with a dynamic timestamp message
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set current_date=%datetime:~4,2%/%datetime:~6,2%/%datetime:~0,4%

git commit -m "Automated data sync: %current_date%"

:: Push the live metrics to your public GitHub pages branch
echo Pushing updates to repository server...
git push origin main

echo ===================================================
echo   SUCCESS: Pipeline execution complete!
echo ===================================================

:end
pause