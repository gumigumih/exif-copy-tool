@echo off
setlocal
cd /d %~dp0
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m PyInstaller --onefile --windowed --name ExifCopyTool exif_context_app.py
if exist dist\ExifCopyTool.exe (
  echo.
  echo Build completed: dist\ExifCopyTool.exe
  echo Optional: put exiftool.exe next to dist\ExifCopyTool.exe for best EXIF support.
) else (
  echo Build failed.
)
pause
