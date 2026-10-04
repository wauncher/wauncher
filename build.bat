@echo off
setlocal
cd /d "%~dp0"
echo === wauncher - build ===
python -m pip install -q -r requirements.txt || goto :fail
for /f "delims=" %%v in ('python tools\bump_version.py %1') do set EXE_BASE=%%v
if "%EXE_BASE%"=="" goto :fail
echo Version stamped: %EXE_BASE%
python tools\make_icon.py || goto :fail
python -m PyInstaller --noconfirm --clean wauncher.spec || goto :fail
python -m PyInstaller --noconfirm --clean wauncher-onedir.spec || goto :fail
echo.
echo Build complete:
echo   dist\%EXE_BASE%.exe        single file (slower start: unpacks itself on every launch)
echo   dist\wauncher\wauncher.exe  one folder, starts in a fraction of the time; ship the whole folder
echo Data lives in %%LOCALAPPDATA%%\eve-wauncher either way.
goto :eof
:fail
echo.
echo BUILD FAILED
exit /b 1
