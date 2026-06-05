@echo off
setlocal
echo === Intel oneAPI 2026.0 + Nuitka 4.1.2 + clang-cl + LTO ===
echo.

call "C:\Program Files (x86)\Intel\oneAPI\2026.0\oneapi-vars.bat" --include-intel-llvm

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

echo === BUILD SUCCESS ===
endlocal
