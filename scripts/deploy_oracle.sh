#!/usr/bin/env bash
# ==============================================================================
# MHIDE STORY INTELLIGENCE — ORACLE CLOUD ALWAYS FREE 1-CLICK DEPLOY SCRIPT
# ==============================================================================
set -euo pipefail

echo "============================================================"
echo "🚀 Setting up Mhide Story Intelligence on Oracle Cloud VM..."
echo "============================================================"

# 1. Update system packages
echo "📦 Updating system packages..."
sudo apt-get update -y
sudo apt-get upgrade -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release ffmpeg fonts-liberation fonts-dejavu-core git

# 2. Install Docker & Docker Compose if not already installed
if ! command -v docker &> /dev/null; then
    echo "🐳 Installing Docker Engine..."
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo usermod -aG docker "$USER"
    echo "✓ Docker installed successfully."
fi

# 3. Create required data directories
mkdir -p data/audio data/asset_cache data/research_cache data/curated_assets output/jobs logs credentials

# 4. Build and start containers
echo "🚀 Launching Mhide Story Intelligence container in background..."
sudo docker compose down 2>/dev/null || true
sudo docker compose up -d --build

echo "============================================================"
echo "🎉 DEPLOYMENT COMPLETE!"
echo "============================================================"
echo "• Both the Telegram Bot (@DarkestMindsbot) and Autonomous Scheduler are running 24/7."
echo "• To view live logs:    sudo docker compose logs -f"
echo "• To check container:   sudo docker ps"
echo "• To restart anytime:   sudo docker compose restart"
echo "============================================================"
