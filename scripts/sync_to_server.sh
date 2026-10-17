#!/usr/bin/env bash
# ==============================================================================
# SYNC LOCAL CODE, CREDENTIALS, AND LAUNCH ON REMOTE SERVER
# Usage: ./scripts/sync_to_server.sh <SERVER_IP> <SSH_PRIVATE_KEY_PATH>
# Example: ./scripts/sync_to_server.sh 140.238.10.25 ~/.ssh/oracle_key.key
# ==============================================================================
set -euo pipefail

if [ "$#" -lt 2 ]; then
    echo "Usage: $0 <SERVER_IP> <SSH_KEY_PATH>"
    echo "Example: $0 152.67.12.89 ~/Downloads/ssh-key.key"
    exit 1
fi

SERVER_IP="$1"
SSH_KEY="$2"
REMOTE_USER="ubuntu"
REMOTE_DIR="~/mhide"

echo "============================================================"
echo "🚀 Deploying Mhide Story Intelligence to $SERVER_IP..."
echo "============================================================"

# Fix SSH key permissions
chmod 400 "$SSH_KEY" 2>/dev/null || true

# Test SSH connectivity
echo "📡 Checking connection to $SERVER_IP..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 "${REMOTE_USER}@${SERVER_IP}" "mkdir -p ${REMOTE_DIR}"

# Sync files (excluding large temporary directories)
echo "📦 Uploading code, environment configuration, and YouTube credentials..."
rsync -avz -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" \
    --exclude '.venv' \
    --exclude '__pycache__' \
    --exclude '.git' \
    --exclude 'output/jobs' \
    --exclude 'output/test_*' \
    --exclude 'data/video_cache' \
    --exclude '.tempmediaStorage' \
    ./ "${REMOTE_USER}@${SERVER_IP}:${REMOTE_DIR}/"

# Execute remote deployment
echo "🚀 Running installation and starting containers on $SERVER_IP..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "${REMOTE_USER}@${SERVER_IP}" \
    "cd ${REMOTE_DIR} && chmod +x scripts/deploy_oracle.sh && ./scripts/deploy_oracle.sh"

echo "============================================================"
echo "🎉 SUCCESS: System is running online 24/7 on your server!"
echo "• Message /status or /latest to @DarkestMindsbot on Telegram to verify."
echo "============================================================"
