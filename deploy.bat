@echo off
chcp 65001 >nul
echo.
echo === AUTO DEPLOY ke GitHub + Render ===
echo.

cd /d "%~dp0"

git rev-parse --git-dir >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Bukan git repository.
    pause
    exit /b 1
)

echo [1/4] Menambahkan semua file...
git add .

echo [2/4] Memastikan file sensitif tidak ikut...
git reset HEAD .env >nul 2>&1
git reset HEAD requirements.txt >nul 2>&1

for %%F in (client_secret_*.json) do (
    git reset HEAD "%%F" >nul 2>&1
)

echo [3/4] File yang akan di-commit:
git diff --cached --name-only
echo.

git diff --cached --quiet
if %errorlevel% equ 0 (
    echo Tidak ada perubahan baru untuk di-commit.
    pause
    exit /b 0
)

set /p MSG="Pesan commit (Enter = pakai tanggal): "
if "%MSG%"=="" set MSG=update %date% %time%

git commit -m "%MSG%"
if %errorlevel% neq 0 (
    echo ERROR: Commit gagal.
    pause
    exit /b 1
)

echo [4/4] Push ke GitHub...
git push
if %errorlevel% neq 0 (
    echo ERROR: Push gagal. Cek koneksi atau login GitHub.
    pause
    exit /b 1
)

echo.
echo === SELESAI! Render akan auto-deploy. ===
echo Pantau: https://dashboard.render.com
echo.
pause
