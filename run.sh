#!/usr/bin/env bash
# ====================================================================
# J.A.R.V.I.S. Universal Cross-Platform Launcher (macOS & Linux)
# Automatically initializes virtual environment, checks dependencies,
# and starts the assistant.
# ====================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "          Starting J.A.R.V.I.S. Voice Assistant             "
echo "============================================================"

# 1. Locate Python 3
PYTHON_BIN=""
if command -v python3 &>/dev/null; then
    PYTHON_BIN="python3"
elif command -v python &>/dev/null; then
    PYTHON_BIN="python"
else
    echo "[ERROR] Python 3 was not found on this system."
    echo "        Please install Python 3.10+ (e.g. 'sudo apt install python3 python3-venv' or via brew.sh)."
    exit 1
fi

# 2. Check / Create Virtual Environment
if [ ! -d "venv" ]; then
    echo "[*] Creating isolated virtual environment in ./venv..."
    $PYTHON_BIN -m venv venv
    source venv/bin/activate
    echo "[*] Installing required dependencies..."
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
else
    source venv/bin/activate
fi

# 4. Run Pre-flight Health & Dependency Doctor
python doctor.py

# 5. Launch Assistant
echo "[*] Launching J.A.R.V.I.S. runtime..."
exec python main.py "$@"
