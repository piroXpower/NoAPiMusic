#!/bin/bash
set -e

echo "=========================================="
echo " Starting Full Automatic VPS Setup..."
echo "=========================================="

sudo apt update -y
sudo apt install -y curl git tmux unzip ffmpeg python3 python3-pip python3-venv python3-dev build-essential

# Install Node.js 20 (required by PyTgCalls engine)
if ! command -v node &> /dev/null; then
    echo "Installing Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt install -y nodejs
fi

# Install Deno if missing
if ! command -v deno &> /dev/null; then
    echo "Installing Deno..."
    curl -fsSL https://deno.land/install.sh | sh || true
    export DENO_INSTALL="$HOME/.deno"
    export PATH="$DENO_INSTALL/bin:$PATH"
fi

rm -rf New_Reapo
git clone https://github.com/rockyxd3/sriram.git
cd sriram

cat << 'EOF' > .env
API_ID=
API_HASH=
BOT_TOKEN=
MONGO_URL=
LOGGER_ID=
OWNER_ID=
SESSION=
API_URL=
API_KEY=
EOF

python3 -m venv venv
./venv/bin/pip install --upgrade pip setuptools wheel
./venv/bin/pip install -r requirements.txt

tmux kill-session -t musicbot 2>/dev/null || true
tmux new-session -d -s musicbot './venv/bin/python3 -m sriram'

sleep 4

echo "=========================================="
echo " Status Check & Logs:"
echo "=========================================="
tmux capture-pane -pt musicbot -S -30 || true

echo "=========================================="
echo " Setup Finished! Bot is running in tmux."
echo " To view live logs: tmux attach -t musicbot"
echo "=========================================="
