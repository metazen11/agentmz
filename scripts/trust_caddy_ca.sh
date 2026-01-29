#!/bin/bash
# Trust the Caddy local CA root certificate on the host OS.

set -e

CONTAINER_NAME="${CADDY_CONTAINER:-wfhub-v2-caddy}"
CERT_PATH="/data/caddy/pki/authorities/local/root.crt"

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "ERROR: Caddy container not running: ${CONTAINER_NAME}"
  exit 1
fi

TMP_DIR=$(mktemp -d)
CERT_FILE="${TMP_DIR}/wfhub-caddy-root.crt"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

if ! docker exec "${CONTAINER_NAME}" cat "${CERT_PATH}" > "${CERT_FILE}" 2>/dev/null; then
  echo "ERROR: Could not copy Caddy root certificate from container."
  echo "Make sure Caddy has started and generated local certs."
  exit 1
fi

OS_NAME="$(uname -s)"
if [ "${OS_NAME}" = "Darwin" ]; then
  echo "Installing Caddy root CA into macOS System keychain (sudo required)..."
  sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain "${CERT_FILE}"
  echo "Caddy root CA trusted on macOS."
  exit 0
fi

if [ "${OS_NAME}" = "Linux" ]; then
  if grep -qi microsoft /proc/version 2>/dev/null; then
    WINDOWS_CERT="/mnt/c/Windows/Temp/wfhub-caddy-root.crt"
    cp "${CERT_FILE}" "${WINDOWS_CERT}"
    echo "WSL detected. Copied cert to ${WINDOWS_CERT}."
    if command -v powershell.exe >/dev/null 2>&1; then
      echo "Attempting to install cert into Windows trust store (admin required)..."
      powershell.exe -NoProfile -Command "Start-Process -Verb RunAs powershell -ArgumentList 'Import-Certificate -FilePath \"${WINDOWS_CERT}\" -CertStoreLocation Cert:\\LocalMachine\\Root'" || true
    fi
    echo "If the browser still warns, manually trust the cert in Windows."
    exit 0
  fi

  echo "Installing Caddy root CA into Linux trust store (sudo required)..."
  sudo cp "${CERT_FILE}" /usr/local/share/ca-certificates/wfhub-caddy-root.crt
  sudo update-ca-certificates
  echo "Caddy root CA trusted on Linux."
  exit 0
fi

echo "Unsupported OS for automatic trust."
exit 1
