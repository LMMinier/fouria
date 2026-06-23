@echo off
where cl.exe >nul 2>&1
if %errorlevel% neq 0 (
    echo MSVC not found. Trying to find Visual Studio...
    for /f "tokens=*" %%i in ('"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -property installationPath 2^>nul') do (
        call "%%i\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
    )
)
cl.exe virtual_midi.cpp /O2 /link winmm.lib /out:virtual_midi.exe
if exist virtual_midi.exe (
    echo Build successful: virtual_midi.exe
    copy virtual_midi.exe ..\data\ >nul
) else (
    echo Build failed. Make sure MSVC is installed.
)
