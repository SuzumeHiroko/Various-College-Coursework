#!/bin/bash
# install.sh - Sets up the radar project on Raspberry Pi Zero W 2 (Raspbian)
# Run with: sudo bash install.sh

# Force bash if invoked with sh
if [ -z "$BASH_VERSION" ]; then
    exec bash "$0" "$@"
fi

# Strip Windows CRLF line endings from this script and re-exec if needed
if grep -qP '\r' "$0" 2>/dev/null; then
    sed -i 's/\r//' "$0"
    exec bash "$0" "$@"
fi

set -e

# ── Resolve paths ──────────────────────────────────────────────────────────────
REAL_USER="admin"
REAL_HOME="/home/admin"
PROJECT_DIR="$REAL_HOME/repos/group-project-radar-project"

# ── Checks ─────────────────────────────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Please run as root: sudo bash install.sh"
    exit 1
fi

echo "=== Radar Project Installer ==="
echo "Project directory : $PROJECT_DIR"
echo "Running as user   : $REAL_USER"
echo "User home         : $REAL_HOME"
echo ""

# ── Helpers ────────────────────────────────────────────────────────────────────
WARNINGS=""

apt_install() {
    if ! apt-get install -y "$1" -qq 2>/dev/null; then
        echo "  WARNING: Could not install $1 — skipping."
        WARNINGS="${WARNINGS}\n  - apt package '$1' could not be installed"
    fi
}

# ── System packages ────────────────────────────────────────────────────────────
echo "[1/6] Installing system packages..."
apt-get update -q
apt_install python3
apt_install python3-pip
apt_install python3-venv
apt_install python3-tk
apt_install libatlas-base-dev
apt_install libjpeg-dev
apt_install libopenblas-dev
apt_install fonts-dejavu-core

# ── Virtual environment ────────────────────────────────────────────────────────
echo "[2/6] Creating Python virtual environment..."
VENV_DIR="$PROJECT_DIR/venv"
python3 -m venv "$VENV_DIR"
chown -R "$REAL_USER:$REAL_USER" "$VENV_DIR"

# ── Python dependencies ────────────────────────────────────────────────────────
echo "[3/6] Installing Python dependencies..."
sudo -u "$REAL_USER" "$VENV_DIR/bin/pip" install --upgrade pip --quiet
sudo -u "$REAL_USER" "$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements.txt" --quiet

# ── Serial port access ─────────────────────────────────────────────────────────
echo "[4/6] Adding $REAL_USER to dialout group (serial port access)..."
usermod -aG dialout "$REAL_USER"

# ── Auto-login to desktop ──────────────────────────────────────────────────────
echo "[5/7] Configuring desktop auto-login for $REAL_USER..."
LIGHTDM_CONF="/etc/lightdm/lightdm.conf"
if [ -f "$LIGHTDM_CONF" ]; then
    # Set autologin user and disable timeout
    sed -i "s/^#*autologin-user=.*/autologin-user=$REAL_USER/" "$LIGHTDM_CONF"
    sed -i "s/^#*autologin-user-timeout=.*/autologin-user-timeout=0/" "$LIGHTDM_CONF"
    # If the lines don't exist yet, append them under [Seat:*]
    grep -q "^autologin-user=" "$LIGHTDM_CONF" || sed -i "/^\[Seat:\*\]/a autologin-user=$REAL_USER\nautologin-user-timeout=0" "$LIGHTDM_CONF"
    echo "  Auto-login enabled in $LIGHTDM_CONF."
elif command -v raspi-config >/dev/null 2>&1; then
    raspi-config nonint do_boot_behaviour B4
    echo "  Auto-login enabled via raspi-config."
else
    echo "  WARNING: Could not configure auto-login automatically."
    echo "  Enable manually: sudo raspi-config → System Options → Boot / Auto Login → Desktop Autologin"
fi

# ── systemd service ────────────────────────────────────────────────────────────
echo "[6/7] Installing systemd service..."
SERVICE_FILE="/etc/systemd/system/radar.service"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

sed \
    -e "s|__USER__|$REAL_USER|g" \
    -e "s|__HOME__|$REAL_HOME|g" \
    -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
    -e "s|__VENV_DIR__|$VENV_DIR|g" \
    "$SCRIPT_DIR/radar.service" > "$SERVICE_FILE"

chmod 644 "$SERVICE_FILE"

systemctl daemon-reload
systemctl enable radar.service

# ── Done ───────────────────────────────────────────────────────────────────────
echo "[7/7] Done!"
echo ""
echo "The radar service is enabled and will start automatically on next boot."
echo ""
echo "Useful commands:"
echo "  sudo systemctl start radar      # start now"
echo "  sudo systemctl stop radar       # stop"
echo "  sudo systemctl status radar     # check status"
echo "  journalctl -u radar -f          # view live logs"
echo ""
echo "NOTE: Log out and back in (or reboot) for dialout group membership to take effect."

if [ -n "$WARNINGS" ]; then
    echo ""
    echo "⚠  Installation completed with warnings:"
    printf "%b\n" "$WARNINGS"
    echo "These may or may not affect functionality."
fi
