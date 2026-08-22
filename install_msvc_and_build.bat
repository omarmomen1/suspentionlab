@echo off
echo ===============================================
echo  SuspensionLab - MSVC Build Tools Installer
echo  This will open a UAC prompt - click YES
echo ===============================================
echo.

set INSTALLER=%LOCALAPPDATA%\Temp\WinGet\Microsoft.VisualStudio.2022.BuildTools.17.14.37\vs_BuildTools.exe

if not exist "%INSTALLER%" (
    echo Installer not found at: %INSTALLER%
    echo Downloading fresh copy...
    winget download --id Microsoft.VisualStudio.2022.BuildTools --download-directory "%TEMP%\vsbt" 2>nul
    set INSTALLER=%TEMP%\vsbt\vs_BuildTools.exe
)

echo Launching installer - click YES on the UAC prompt...
"%INSTALLER%" --quiet --wait --norestart ^
    --add Microsoft.VisualStudio.Workload.VCTools ^
    --add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 ^
    --add Microsoft.VisualStudio.Component.Windows11SDK.22621 ^
    --includeRecommended

echo.
echo Exit code: %ERRORLEVEL%
if %ERRORLEVEL% == 0 (
    echo SUCCESS! Building C++ extension now...
    cd /d D:\project
    C:\Users\omaar\AppData\Local\Python\pythoncore-3.14-64\python.exe bootstrap_compiler.py
) else (
    echo Install failed with code %ERRORLEVEL%
    echo If 1602: You cancelled the UAC prompt - run this script again and click YES
)
pause
