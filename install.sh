#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

INSTALL_DIR="$HOME/.local/share/dofus-focus-tray"
BIN_DIR="$HOME/.local/bin"

DEPENDENCIES=(
    "python"
    "pyside6"
    "kstatusnotifieritem"
    "python-dbus-next"
    "python-evdev"
    "python-pyudev"
    "libxkbcommon"
    "kpackage"
    "kconfig"
    "qt6-tools"
)

declare -A MIN_VERSIONS=(
    [python]="3.11"
    [pyside6]="6.6"
    [kstatusnotifieritem]="6.0"
    [python-dbus-next]="0.2.3"
    [python-evdev]="2.0.0"
    [python-pyudev]="0.24.4"
    [libxkbcommon]="0.4.0"
    [kpackage]="6.0"
    [kconfig]="6.0"
    [qt6-tools]="6.0"
)

info() {
    printf '%s\n' "$*"
}

check_passed() {
    printf '  ✓ %s\n' "$1"
}

check_failed() {
    printf '  ✗ %s\n' "$1" >&2
    exit 1
}

require_command() {
    if command -v "$1" >/dev/null 2>&1; then
        check_passed "$2"
    else
        check_failed "$2"
    fi
}

require_file() {
    if [[ -f "$ROOT/$1" ]]; then
        check_passed "$2"
    else
        check_failed "$2"
    fi
}

check_dependency() {
    local package="$1"
    local minimum="${MIN_VERSIONS[$package]}"
    local installed

    if ! pacman -Q "$package" >/dev/null 2>&1; then
        printf '  ✗ %s (missing, requires >= %s)\n' "$package" "$minimum"
        return 1
    fi

    installed="$(pacman -Q "$package" | awk '{print $2}')"

    if (( $(vercmp "$installed" "$minimum") < 0 )); then
        printf '  ✗ %s %s (requires >= %s)\n' \
            "$package" "$installed" "$minimum"
        return 1
    fi

    printf '  ✓ %s %s\n' "$package" "$installed"
}

# ---------------------------------------------------------------------------
# Target user and privileges
# ---------------------------------------------------------------------------

info "Checking system requirements..."

if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    check_failed "Installer must not be run as root."
fi
check_passed "Non-root user"

INSTALL_USER="$(id -un)"
INSTALL_UID="$(id -u)"

# ---------------------------------------------------------------------------
# Operating system
# ---------------------------------------------------------------------------

if [[ ! -r /etc/os-release ]]; then
    check_failed "Reading /etc/os-release"
fi

# shellcheck disable=SC1091
source /etc/os-release

if [[ "${ID:-}" == "arch" || " ${ID_LIKE:-} " =~ [[:space:]]arch[[:space:]] ]]; then
    check_passed "Arch Linux / Arch-based distribution"
else
    check_failed "Arch Linux / Arch-based distribution"
fi

# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

if [[ "${XDG_SESSION_TYPE:-}" == "wayland" ]]; then
    check_passed "Wayland session"
else
    check_failed "Wayland session"
fi

if [[ "${XDG_CURRENT_DESKTOP:-}" == *KDE* || "${XDG_CURRENT_DESKTOP:-}" == *Kde* ]]; then
    check_passed "KDE Plasma"
else
    check_failed "KDE Plasma"
fi

# ---------------------------------------------------------------------------
# Plasma version
# ---------------------------------------------------------------------------

if ! command -v plasmashell >/dev/null 2>&1; then
    check_failed "KDE Plasma 6 or newer"
fi

PLASMA_VERSION="$(plasmashell --version 2>/dev/null | sed -n 's/.* //p')"

if [[ -z "$PLASMA_VERSION" ]]; then
    check_failed "KDE Plasma 6 or newer"
fi

PLASMA_MAJOR="${PLASMA_VERSION%%.*}"

if [[ "$PLASMA_MAJOR" =~ ^[0-9]+$ ]] && (( PLASMA_MAJOR >= 6 )); then
    check_passed "KDE Plasma $PLASMA_VERSION"
else
    check_failed "KDE Plasma 6 or newer"
fi

# ---------------------------------------------------------------------------
# systemd
# ---------------------------------------------------------------------------

if [[ -d /run/systemd/system ]]; then
    check_passed "systemd"
else
    check_failed "systemd"
fi

if command -v systemctl >/dev/null 2>&1 && systemctl --version >/dev/null 2>&1; then
    check_passed "systemctl"
else
    check_failed "systemctl"
fi

# ---------------------------------------------------------------------------
# Required installation tools
# ---------------------------------------------------------------------------

require_command pacman "pacman"
require_command sudo "sudo"
require_command vercmp "vercmp"
require_command kpackagetool6 "kpackagetool6"
require_command qdbus6 "qdbus6"
require_command kwriteconfig6 "kwriteconfig6"
require_command kreadconfig6 "kreadconfig6"

# ---------------------------------------------------------------------------
# User installation directories
# ---------------------------------------------------------------------------

if mkdir -p "$BIN_DIR" && [[ -w "$BIN_DIR" ]]; then
    check_passed "User binary directory"
else
    check_failed "User binary directory"
fi

if mkdir -p "$HOME/.local/share" && [[ -w "$HOME/.local/share" ]]; then
    check_passed "User data directory"
else
    check_failed "User data directory"
fi

# ---------------------------------------------------------------------------
# Source tree
# ---------------------------------------------------------------------------

if [[ -d "$ROOT/src" ]]; then
    check_passed "Source directory"
else
    check_failed "Source directory"
fi

require_file "src/start.sh" "Application startup script"
require_file "src/dofus_focus_tray.py" "Application entry point"

for directory in \
    app \
    bridge \
    config \
    helper \
    input \
    icons \
    kwin_script \
    notifications \
    shortcuts \
    ui
do
    if [[ -d "$ROOT/src/$directory" ]]; then
        check_passed "Source directory: src/$directory"
    else
        check_failed "Source directory: src/$directory"
    fi
done

info ""
info "System requirements are satisfied."

info ""
info "Checking dependencies..."

dependencies_satisfied=0

for package in "${DEPENDENCIES[@]}"; do
    if ! check_dependency "$package"; then
        dependencies_satisfied=1
    fi
done

if (( dependencies_satisfied == 0 )); then
    info ""
    info "Dependencies are satisfied."
else
    info ""
    info "Installing dependencies..."

    sudo pacman --needed -S "${DEPENDENCIES[@]}"

    info ""
    info "Rechecking dependencies..."

    for package in "${DEPENDENCIES[@]}"; do
        if ! check_dependency "$package"; then
            check_failed "Dependency validation failed: $package"
        fi
    done

    info ""
    info "Dependencies installed successfully."
fi

info ""
info "Installing application runtime..."

if [[ -d "$INSTALL_DIR" ]]; then
    IS_REINSTALL=1
else
    IS_REINSTALL=0
fi

SHORTCUTS_FILE="$INSTALL_DIR/config/shortcuts.json"
SHORTCUTS_BACKUP=""

if [[ -f "$SHORTCUTS_FILE" ]]; then
    SHORTCUTS_BACKUP="$(mktemp)"
    cp "$SHORTCUTS_FILE" "$SHORTCUTS_BACKUP"
    info "  ✓ Existing shortcut configuration preserved"
fi

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

rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

cp -a "$ROOT/src/." "$INSTALL_DIR/"

if [[ -n "$SHORTCUTS_BACKUP" ]]; then
    mkdir -p "$INSTALL_DIR/config"
    cp "$SHORTCUTS_BACKUP" "$INSTALL_DIR/config/shortcuts.json"
    rm -f "$SHORTCUTS_BACKUP"
fi

chmod 755 "$INSTALL_DIR/start.sh"

printf '  ✓ Runtime installed in %s\n' "$INSTALL_DIR"

info ""
info "Application runtime installed successfully."

info ""
info "Installing application wrappers..."

mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/dofus-focus-tray" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "$INSTALL_DIR/start.sh" "\$@"
EOF

chmod 755 "$BIN_DIR/dofus-focus-tray"

printf '  ✓ Application launcher installed in %s\n' \
    "$BIN_DIR/dofus-focus-tray"

cat "$ROOT/uninstall.sh" > "$BIN_DIR/dofus-focus-tray-uninstall"

chmod 755 "$BIN_DIR/dofus-focus-tray-uninstall"

printf '  ✓ Uninstall wrapper installed in %s\n' \
    "$BIN_DIR/dofus-focus-tray-uninstall"

info ""
info "Application wrappers installed successfully."

info ""
info "Installing desktop launcher..."

APPLICATIONS_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$APPLICATIONS_DIR/dofus-focus-tray.desktop"

mkdir -p "$APPLICATIONS_DIR"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Dofus Focus Tray
Comment=Dofus Focus tray indicator
Exec=dofus-focus-tray
Icon=$INSTALL_DIR/icons/dofus.webp
Terminal=false
Categories=Utility;Game;
EOF

chmod 644 "$DESKTOP_FILE"

kbuildsycoca6 >/dev/null 2>&1

printf '  ✓ Desktop launcher installed in %s\n' \
    "$DESKTOP_FILE"

info ""
info "Desktop launcher installed successfully."

info ""
info "Configuring application autostart..."

AUTOSTART_DIR="$HOME/.config/autostart"
AUTOSTART_FILE="$AUTOSTART_DIR/dofus-focus-tray.desktop"
AUTOSTART_ENABLED=0

while true; do
    read -r -p "Start Dofus Focus Tray automatically with your session? [Y/n] " AUTOSTART_CHOICE

    case "${AUTOSTART_CHOICE,,}" in
        ""|y|yes)
            mkdir -p "$AUTOSTART_DIR"

            cat > "$AUTOSTART_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Dofus Focus Tray
Comment=Dofus Focus tray indicator
Exec=$BIN_DIR/dofus-focus-tray
Icon=$INSTALL_DIR/icons/dofus.webp
Terminal=false
EOF

            chmod 644 "$AUTOSTART_FILE"

            AUTOSTART_ENABLED=1

            printf '  ✓ Autostart enabled in %s\n' \
                "$AUTOSTART_FILE"
            break
            ;;

        n|no)
            rm -f "$AUTOSTART_FILE"

            AUTOSTART_ENABLED=0

            printf '  ✓ Autostart disabled\n'
            break
            ;;

        *)
            printf '  ✗ Invalid choice. Please answer Y or N.\n'
            ;;
    esac
done

info ""
info "Autostart configuration applied successfully."

info ""
info "Installing systemd input helper..."

SYSTEMD_DIR="/etc/systemd/system"
SERVICE_FILE="$SYSTEMD_DIR/dofus-focus-input.service"
SOCKET_FILE="$SYSTEMD_DIR/dofus-focus-input.socket"

SERVICE_UNIT="$(mktemp)"
SOCKET_UNIT="$(mktemp)"

cat > "$SERVICE_UNIT" <<EOF
[Unit]
Description=Dofus Focus input helper
Requires=dofus-focus-input.socket
After=dofus-focus-input.socket

[Service]
Type=simple
User=root
Environment=DOFUS_FOCUS_CLIENT_UID=$INSTALL_UID
Environment=XDG_RUNTIME_DIR=/run/user/$INSTALL_UID
Environment=WAYLAND_DISPLAY=$WAYLAND_DISPLAY
ExecStart=/usr/bin/python -m helper.main
WorkingDirectory=$INSTALL_DIR
Restart=on-failure

NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
RestrictAddressFamilies=AF_UNIX AF_NETLINK

[Install]
WantedBy=multi-user.target
EOF

cat > "$SOCKET_UNIT" <<EOF
[Unit]
Description=Dofus Focus input helper socket

[Socket]
ListenStream=/run/dofus-focus-input.sock
SocketUser=$INSTALL_USER
SocketGroup=$INSTALL_USER
SocketMode=0600
Accept=no

[Install]
WantedBy=sockets.target
EOF

sudo install -m 644 "$SERVICE_UNIT" "$SERVICE_FILE"
sudo install -m 644 "$SOCKET_UNIT" "$SOCKET_FILE"

rm -f "$SERVICE_UNIT" "$SOCKET_UNIT"

SOCKET_PATH="/run/dofus-focus-input.sock"

sudo systemctl daemon-reload

sudo systemctl stop dofus-focus-input.socket
sudo rm -f "$SOCKET_PATH"

sudo systemctl enable --now dofus-focus-input.socket

if sudo systemctl is-active --quiet dofus-focus-input.socket; then
    printf '  ✓ Input helper socket is active\n'
else
    check_failed "Input helper socket is not active"
fi

if [[ -S "$SOCKET_PATH" ]]; then
    printf '  ✓ Input helper socket created at %s\n' "$SOCKET_PATH"
else
    check_failed "Input helper socket was not created: $SOCKET_PATH"
fi

info ""
info "Systemd input helper installed successfully."

info ""
info "Installing KWin integration..."

PLUGIN_ID="dofus-focus-tray"
KWIN_SCRIPT_DIR="$INSTALL_DIR/kwin_script"

info "  Unloading previous KWin integration..."

qdbus6 \
    org.kde.KWin \
    /Scripting \
    org.kde.kwin.Scripting.unloadScript \
    "$PLUGIN_ID" \
    >/dev/null \
    || true

kwriteconfig6 \
    --file kwinrc \
    --group Plugins \
    --key "${PLUGIN_ID}Enabled" \
    false

qdbus6 \
    org.kde.KWin \
    /KWin \
    reconfigure

sleep 2

kpackagetool6 \
    --type KWin/Script \
    -r "$PLUGIN_ID" \
    || true

kpackagetool6 \
    --type KWin/Script \
    -i "$KWIN_SCRIPT_DIR"

kwriteconfig6 \
    --file kwinrc \
    --group Plugins \
    --key "${PLUGIN_ID}Enabled" \
    true

qdbus6 \
    org.kde.KWin \
    /KWin \
    reconfigure

sleep 3

qdbus6 \
    org.kde.KWin \
    /Scripting \
    org.kde.kwin.Scripting.start

if kpackagetool6 \
    --type KWin/Script \
    -s "$PLUGIN_ID" >/dev/null 2>&1; then
    printf '  ✓ KWin integration package installed\n'
else
    check_failed "KWin integration package is not installed"
fi

if [[ "$(kreadconfig6 \
    --file kwinrc \
    --group Plugins \
    --key "${PLUGIN_ID}Enabled")" == "true" ]]; then
    printf '  ✓ KWin integration enabled\n'
else
    check_failed "KWin integration is not enabled"
fi

if qdbus6 \
    org.kde.KWin \
    /Scripting \
    org.kde.kwin.Scripting.isScriptLoaded \
    "$PLUGIN_ID" 2>/dev/null | grep -qx "true"; then
    printf '  ✓ KWin integration script is loaded\n'
else
    check_failed "KWin integration script is not loaded"
fi

info ""
info "KWin integration installed successfully."

info ""
info "Verifying installation..."

if [[ -d "$INSTALL_DIR" ]]; then
    printf '  ✓ Application runtime directory exists\n'
else
    check_failed "Application runtime directory does not exist"
fi

for required_file in \
    "$INSTALL_DIR/dofus_focus_tray.py" \
    "$INSTALL_DIR/start.sh" \
    "$INSTALL_DIR/config/paths.py"; do
    if [[ -f "$required_file" ]]; then
        printf '  ✓ %s exists\n' "$(basename "$required_file")"
    else
        check_failed "Required runtime file is missing: $required_file"
    fi
done

if [[ -x "$INSTALL_DIR/start.sh" ]]; then
    printf '  ✓ start.sh is executable\n'
else
    check_failed "start.sh is not executable"
fi

if [[ -x "$HOME/.local/bin/dofus-focus-tray" ]]; then
    printf '  ✓ Application wrapper exists and is executable\n'
else
    check_failed "Application wrapper is missing or not executable"
fi

if [[ -x "$HOME/.local/bin/dofus-focus-tray-uninstall" ]]; then
    printf '  ✓ Uninstall wrapper exists and is executable\n'
else
    check_failed "Uninstall wrapper is missing or not executable"
fi

DESKTOP_FILE="$HOME/.local/share/applications/dofus-focus-tray.desktop"

if [[ -f "$DESKTOP_FILE" ]]; then
    printf '  ✓ Desktop launcher exists\n'
else
    check_failed "Desktop launcher is missing"
fi

AUTOSTART_FILE="$HOME/.config/autostart/dofus-focus-tray.desktop"

if (( AUTOSTART_ENABLED )); then
    if [[ -f "$AUTOSTART_FILE" ]]; then
        printf '  ✓ Autostart file exists\n'
    else
        check_failed "Autostart file is missing"
    fi
else
    if [[ ! -e "$AUTOSTART_FILE" ]]; then
        printf '  ✓ Autostart is disabled\n'
    else
        check_failed "Autostart file exists although autostart is disabled"
    fi
fi

if systemctl is-enabled --quiet dofus-focus-input.socket; then
    printf '  ✓ Helper socket is enabled\n'
else
    check_failed "Helper socket is not enabled"
fi

if systemctl is-active --quiet dofus-focus-input.socket; then
    printf '  ✓ Helper socket is active\n'
else
    check_failed "Helper socket is not active"
fi

if [[ -S /run/dofus-focus-input.sock ]]; then
    printf '  ✓ Helper socket exists\n'
else
    check_failed "Helper socket does not exist"
fi

if systemctl is-enabled --quiet dofus-focus-input.service 2>/dev/null; then
    check_failed "Helper service must not be enabled"
else
    printf '  ✓ Helper service is socket-activated\n'
fi

info ""
info "Installation verification completed successfully."

info ""
info "Installation completed successfully."

if (( IS_REINSTALL )); then
    info "Please log out and log back in to load the updated KWin integration."
else
    info "Dofus Focus Tray is ready to use."
fi
