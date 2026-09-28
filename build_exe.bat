@echo off
REM Builds ScreenCaptureToPDF.exe and bundles Tesseract OCR next to it.
REM Run this on a Windows PC that has Python and Tesseract installed.
cd /d "%~dp0"

echo Installing build tools and libraries...
python -m pip install --upgrade pyinstaller mss keyboard pytesseract pillow pypdf
if errorlevel 1 goto fail

echo Building the exe...
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "ScreenCaptureToPDF" screen_capture_app.py
if errorlevel 1 goto fail

set "TESS=C:\Program Files\Tesseract-OCR"
if not exist "%TESS%\tesseract.exe" set "TESS=%LOCALAPPDATA%\Programs\Tesseract-OCR"
if exist "%TESS%\tesseract.exe" (
    echo Copying Tesseract into the dist folder...
    xcopy "%TESS%" "dist\Tesseract-OCR\" /E /I /Y /Q >nul
) else (
    echo WARNING: Tesseract not found, so OCR won't work unless users install it themselves.
)

echo.
echo Done. Share the whole "dist" folder (zip it). It contains:
echo   ScreenCaptureToPDF.exe
echo   Tesseract-OCR\
pause
exit /b 0

:fail
echo.
echo Build failed. Scroll up for the error.
pause
exit /b 1
