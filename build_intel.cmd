@echo off
setlocal enabledelayedexpansion

echo === Intel oneAPI + Nuitka + clang-cl + LTO ===
echo.

call "C:\Program Files (x86)\Intel\oneAPI\2026.0\oneapi-vars.bat" --include-intel-llvm
if %errorlevel% neq 0 (
    echo ERROR: Intel oneAPI not found at C:\Program Files (x86)\Intel\oneAPI\2026.0
    exit /b 1
)

python -m nuitka ^
    --onefile ^
    --clang ^
    --lto=yes ^
    --output-dir=dist ^
    --output-filename=py1cv8-win-x64-intel.exe ^
    --remove-output ^
    --python-flag="-m" ^
    --prefer-source-code ^
    --nofollow-import-to=mypy ^
    --include-module=psycopg2 ^
    --include-module=sqlalchemy.dialects.postgresql ^
    --include-module=pyodbc ^
    --include-module=charset_normalizer ^
    --include-windows-runtime-dlls=yes ^
    src/py1cv8

if %errorlevel% neq 0 (
    echo === BUILD FAILED ===
    exit /b 1
)

echo === BUILD SUCCESS ===
echo Output: dist\py1cv8-win-x64-intel.exe
exit /b 0
