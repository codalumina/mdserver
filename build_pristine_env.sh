#!/bin/bash
# build_pristine_env.sh (Offline Deterministic Build + Nuclear Update Block)

SOURCE_MT5="$HOME/.mt5/drive_c/Program Files/MetaTrader 5"
PREFIX_PATH="$HOME/.mdserver_pristine_3"
export WINEPREFIX="$PREFIX_PATH"

echo "🔍 1. Verifying Source Files..."
if [ ! -d "$SOURCE_MT5" ]; then
    echo "❌ Error: Could not find MT5 binaries at $SOURCE_MT5"
    echo "Please ensure your working ~/.mt5 prefix exists."
    exit 1
fi

echo "🧹 2. Wiping target prefix ($PREFIX_PATH)..."
wineserver -k 2>/dev/null || true
rm -rf "$WINEPREFIX"

echo "⚙️ 3. Initializing Fresh WINE (Windows 10 mode)..."
winecfg -v win10
wineboot -u

echo "⬇️ 4. Downloading Python Installer..."
wget -nc -O python-installer.exe "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"

echo "🐍 5. Installing Python 3.10 (Silent)..."
wine python-installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
wineserver -w

echo "📦 6. Injecting Sterile MT5 Binaries..."
mkdir -p "$WINEPREFIX/drive_c/Program Files/MetaTrader 5"
cp -r "$SOURCE_MT5/"* "$WINEPREFIX/drive_c/Program Files/MetaTrader 5/"

echo "🛡️ 7. Applying MT5 Nuclear Update Block..."
# 1. Create the parent MetaQuotes directory so it exists
UPDATE_BASE="$WINEPREFIX/drive_c/users/$USER/AppData/Roaming/MetaQuotes"
mkdir -p "$UPDATE_BASE"
# 2. Ensure WebInstall isn't a directory
rm -rf "$UPDATE_BASE/WebInstall"
# 3. Create WebInstall as a dummy FILE instead of a directory
touch "$UPDATE_BASE/WebInstall"
# 4. Lock the dummy file
chmod 444 "$UPDATE_BASE/WebInstall"

echo "👀 8. Clean Launch for Verification..."
echo "================================================================"
echo " ACTION REQUIRED:"
echo " 1. The MT5 terminal should render cleanly and instantly."
echo " 2. Verify it asks to 'Open an Account'."
echo " 3. LEAVE IT OPEN FOR 5 MINUTES to verify no update pop-up appears."
echo " 4. Close the MT5 terminal normally (File -> Exit)."
echo "================================================================"
wine "C:\Program Files\MetaTrader 5\terminal64.exe"

echo ""
read -p "Press [ENTER] ONLY AFTER you have closed the MT5 window..."
wineserver -k 2>/dev/null || true

echo "🐍 9. Installing Python dependencies..."
wine python -m pip install --upgrade pip setuptools
wine python -m pip install fastapi uvicorn MetaTrader5 pydantic cachetools pydantic-settings python-dotenv tzdata "numpy==1.24.3"
wineserver -w

echo "🧹 10. Cleaning up..."
rm -f python-installer.exe

echo "✅ Pristine Golden Image base is ready!"
echo "🧪 Running Final Verification Test..."
wine python -c "import MetaTrader5 as mt5; print('MT5 Version Bridge Success:', mt5.__version__)"