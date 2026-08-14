#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ID="dofus-focus-tray"

echo "=================================="
echo " Reloading $PLUGIN_ID..."
echo "=================================="

echo
echo "Unloading script from KWin memory..."
# 1. On force KWin à décharger l'ancien code QML/JS de sa mémoire vive
qdbus6 org.kde.KWin /Scripting org.kde.kwin.Scripting.unloadScript "$PLUGIN_ID" || true

echo
echo "Disabling in configuration..."
kwriteconfig6 \
    --file kwinrc \
    --group Plugins \
    --key "${PLUGIN_ID}Enabled" \
    false

qdbus6 org.kde.KWin /KWin reconfigure

sleep 2

echo
echo "Removing package..."
kpackagetool6 \
    --type KWin/Script \
    -r "$PLUGIN_ID" \
    || true

echo
echo "Installing new package version..."
kpackagetool6 \
    --type KWin/Script \
    -i "$ROOT/kwin_script"

echo
echo "Enabling in configuration..."
kwriteconfig6 \
    --file kwinrc \
    --group Plugins \
    --key "${PLUGIN_ID}Enabled" \
    true

qdbus6 org.kde.KWin /KWin reconfigure


sleep 3

echo
echo "Forcing KWin Scripting engine to restart..."
# 2. On demande au gestionnaire de script de KWin de scanner à nouveau et de démarrer
qdbus6 org.kde.KWin /Scripting org.kde.kwin.Scripting.start

echo
echo "=================================="
echo " Reload complete & Cache bypassed!"
echo "=================================="
