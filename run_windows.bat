@echo off
rem Double-click to run the generator. Put the report folders (or zips) in the "source" folder first.
rem Add options after the file name, for example:  run_windows.bat --ai
cd /d "%~dp0"
python run.py %*
echo.
pause
