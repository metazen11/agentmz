#!/bin/bash
# Initialize SSH server in ollama container
#
# This script runs during ollama container startup to:
# 1. Wait for the public key to be available in the shared volume
# 2. Copy the public key to authorized_keys
# 3. Start the SSH daemon
#
# Environment variables:
#   SSH_KEY_DIR: Directory containing keys (default: /ssh_keys)
#   SSH_KEY_TYPE: Key type - ed25519 or rsa (default: ed25519)
#   SSH_KEY_WAIT_TIMEOUT: Max seconds to wait for key (default: 60)

set -e

KEY_DIR="${SSH_KEY_DIR:-/ssh_keys}"
KEY_TYPE="${SSH_KEY_TYPE:-ed25519}"
PUBKEY_FILE="$KEY_DIR/id_$KEY_TYPE.pub"
MAX_WAIT="${SSH_KEY_WAIT_TIMEOUT:-60}"

echo "[SSH-INIT] Waiting for public key at $PUBKEY_FILE..."

# Wait for the public key to appear (main-api generates it)
for i in $(seq 1 $MAX_WAIT); do
    if [ -f "$PUBKEY_FILE" ]; then
        echo "[SSH-INIT] Found public key after ${i}s"
        break
    fi
    if [ $i -eq $MAX_WAIT ]; then
        echo "[SSH-INIT] Warning: Public key not found after ${MAX_WAIT}s, SSH will not work"
        # Don't exit - allow container to start without SSH
        break
    fi
    sleep 1
done

# Setup authorized_keys if key exists
if [ -f "$PUBKEY_FILE" ]; then
    echo "[SSH-INIT] Setting up authorized_keys..."
    mkdir -p /root/.ssh
    chmod 700 /root/.ssh
    cp "$PUBKEY_FILE" /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys
    echo "[SSH-INIT] Authorized key installed"
fi

# Start SSH daemon
echo "[SSH-INIT] Starting SSH daemon..."
/usr/sbin/sshd

echo "[SSH-INIT] SSH daemon started"
