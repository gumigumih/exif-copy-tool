@echo off
setlocal EnableExtensions
pushd "%~dp0\..\.."

if not exist "dist\ExifCopyTool\ExifCopyTool.exe" (
  echo dist\ExifCopyTool\ExifCopyTool.exe was not found.
  echo Run packaging\windows\build_windows.bat first.
  pause
  popd
  exit /b 1
)

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
  echo Inno Setup 6 was not found.
  echo Install Inno Setup 6, then run this file again.
  echo https://jrsoftware.org/isdl.php
  pause
  popd
  exit /b 1
)

if exist installer rmdir /s /q installer
"%ISCC%" packaging\windows\ExifCopyTool.iss
if errorlevel 1 goto :error

echo.
echo Done.
echo Created: %CD%\installer\ExifCopyToolSetup.exe
pause
popd
exit /b 0

:error
echo.
echo Installer build failed.
pause
popd
exit /b 1
