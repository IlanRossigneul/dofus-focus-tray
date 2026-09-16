#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="$HOME/.local/share/dofus-focus-tray"
BIN_DIR="$HOME/.local/bin"
APPLICATIONS_DIR="$HOME/.local/share/applications"
AUTOSTART_DIR="$HOME/.config/autostart"

APP_WRAPPER="$BIN_DIR/dofus-focus-tray"
UNINSTALL_WRAPPER="$BIN_DIR/dofus-focus-tray-uninstall"
DESKTOP_FILE="$APPLICATIONS_DIR/dofus-focus-tray.desktop"
AUTOSTART_FILE="$AUTOSTART_DIR/dofus-focus-tray.desktop"

SYSTEMD_SERVICE="/etc/systemd/system/dofus-focus-input.service"
SYSTEMD_SOCKET="/etc/systemd/system/dofus-focus-input.socket"
INPUT_SOCKET="/run/dofus-focus-input.sock"

PLUGIN_ID="dofus-focus-tray"

info() {
    printf '%s\n' "$1"
}

check_failed() {
    printf '  ✗ %s\n' "$1" >&2
    exit 1
}

if [[ "$EUID" -eq 0 ]]; then
    check_failed "Do not run uninstall.sh as root"
fi

if ! command -v sudo >/dev/null 2>&1; then
    check_failed "sudo is required for uninstallation"
fi

info ""
info "Dofus Focus Tray uninstallation"
info "================================="

info ""
info "Stopping Dofus Focus Tray..."

if pgrep -af 'python dofus_focus_tray.py' >/dev/null 2>&1; then
    info "  Stopping existing Dofus Focus Tray process..."

    while read -r pid _; do
        kill -TERM "$pid"
    done < <(pgrep -af 'python dofus_focus_tray.py')

    for _ in {1..50}; do
        if ! pgrep -af 'python dofus_focus_tray.py' >/dev/null 2>&1; then
            break
        fi
        sleep 0.1
    done

    if pgrep -af 'python dofus_focus_tray.py' >/dev/null 2>&1; then
        info "  Process did not stop gracefully; forcing termination..."

        while read -r pid _; do
            kill -KILL "$pid"
        done < <(pgrep -af 'python dofus_focus_tray.py')
    fi
fi

if pgrep -af 'python dofus_focus_tray.py' >/dev/null 2>&1; then
    check_failed "Dofus Focus Tray process is still running"
else
    printf '  ✓ Dofus Focus Tray process stopped\n'
fi

info ""
info "Removing systemd integration..."

sudo systemctl stop dofus-focus-input.service 2>/dev/null || true
sudo systemctl stop dofus-focus-input.socket 2>/dev/null || true
sudo systemctl disable dofus-focus-input.socket 2>/dev/null || true

sudo rm -f "$INPUT_SOCKET"
sudo rm -f "$SYSTEMD_SERVICE" "$SYSTEMD_SOCKET"

sudo systemctl daemon-reload

if [[ ! -e "$SYSTEMD_SERVICE" && ! -e "$SYSTEMD_SOCKET" ]]; then
    printf '  ✓ Helper systemd units removed\n'
else
    check_failed "Helper systemd units could not be removed"
fi

if [[ ! -e "$INPUT_SOCKET" ]]; then
    printf '  ✓ Helper socket removed\n'
else
    check_failed "Helper socket could not be removed"
fi

info ""
info "Removing KWin integration..."

qdbus6 org.kde.KWin /Scripting org.kde.kwin.Scripting.unloadScript "$PLUGIN_ID" \
    >/dev/null 2>&1 || true

kwriteconfig6 \
    --file kwinrc \
    --group Plugins \
    --key "${PLUGIN_ID}Enabled" \
    false

qdbus6 org.kde.KWin /KWin reconfigure

kpackagetool6 \
    --type KWin/Script \
    -r "$PLUGIN_ID" \
    >/dev/null 2>&1 || true

qdbus6 org.kde.KWin /KWin reconfigure

if ! kpackagetool6 -s \
    --type KWin/Script \
    2>/dev/null | grep -q "$PLUGIN_ID"; then
    printf '  ✓ KWin integration removed\n'
else
    check_failed "KWin integration could not be removed"
fi

info ""
info "Removing application runtime..."

rm -rf "$INSTALL_DIR"

if [[ ! -e "$INSTALL_DIR" ]]; then
    printf '  ✓ Application runtime removed\n'
else
    check_failed "Application runtime could not be removed"
fi

info ""
info "Removing application wrappers..."

rm -f "$APP_WRAPPER"

if [[ ! -e "$APP_WRAPPER" ]]; then
    printf '  ✓ Application wrapper removed\n'
else
    check_failed "Application wrapper could not be removed"
fi

info ""
info "Removing desktop integration..."

rm -f "$DESKTOP_FILE"

if [[ ! -e "$DESKTOP_FILE" ]]; then
    printf '  ✓ Desktop launcher removed\n'
else
    check_failed "Desktop launcher could not be removed"
fi

rm -f "$AUTOSTART_FILE"

if [[ ! -e "$AUTOSTART_FILE" ]]; then
    printf '  ✓ Autostart removed\n'
else
    check_failed "Autostart file could not be removed"
fi

info ""
info "Uninstallation completed successfully."

info ""
info "Optional dependency removal"
info "---------------------------"
info "The following commands can be used to remove the dependencies installed"
info "for Dofus Focus Tray. They are optional and are not executed automatically."
info ""

printf '  sudo pacman -Rns python\n'
printf '  sudo pacman -Rns pyside6\n'
printf '  sudo pacman -Rns kstatusnotifieritem\n'
printf '  sudo pacman -Rns python-dbus-next\n'
printf '  sudo pacman -Rns python-evdev\n'
printf '  sudo pacman -Rns python-pyudev\n'
printf '  sudo pacman -Rns libxkbcommon\n'
printf '  sudo pacman -Rns kpackage\n'
printf '  sudo pacman -Rns kconfig\n'
printf '  sudo pacman -Rns qt6-tools\n'

info ""
info "Dofus Focus Tray has been uninstalled."

# This must remain the final cleanup operation.
rm -f "$UNINSTALL_WRAPPER"
