#!/bin/bash
# Generate SSH keys for ollama restart service
#
# This script runs on main-api container startup to generate SSH keys
# if they don't already exist. Keys are stored in a shared volume
# that is mounted by both main-api and ollama containers.
#
# Environment variables:
#   SSH_KEY_DIR: Directory to store keys (default: /ssh_keys)
#   SSH_KEY_TYPE: Key type - ed25519 or rsa (default: ed25519)

set -e

KEY_DIR="${SSH_KEY_DIR:-/ssh_keys}"
KEY_TYPE="${SSH_KEY_TYPE:-ed25519}"
KEY_FILE="$KEY_DIR/id_$KEY_TYPE"

echo "[SSH-KEYGEN] Checking for SSH keys in $KEY_DIR..."

# Create directory if it doesn't exist
mkdir -p "$KEY_DIR"

if [ -f "$KEY_FILE" ]; then
    echo "[SSH-KEYGEN] Keys already exist at $KEY_FILE"
    ls -la "$KEY_DIR"
else
    echo "[SSH-KEYGEN] Generating $KEY_TYPE keypair..."
    ssh-keygen -t "$KEY_TYPE" -f "$KEY_FILE" -N "" -C "ollama-restart-service"

    # Set proper permissions
    chmod 600 "$KEY_FILE"
    chmod 644 "$KEY_FILE.pub"

    echo "[SSH-KEYGEN] Keys generated successfully"
    ls -la "$KEY_DIR"
fi

echo "[SSH-KEYGEN] Done"
