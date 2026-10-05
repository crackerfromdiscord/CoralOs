#!/bin/sh
# Remove the CoralOS welcome screen and restore the stock Ubuntu login.
# Usage: sudo ./uninstall.sh [--prefix DIR] [--purge]
#   --purge also deletes /etc/coralos/welcome.conf
set -eu

PREFIX=/usr/local
PURGE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --prefix) PREFIX=$2; shift 2 ;;
        --prefix=*) PREFIX=${1#--prefix=}; shift ;;
        --purge) PURGE=1; shift ;;
        -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "uninstall.sh must be run as root (sudo ./uninstall.sh)" >&2
    exit 1
fi

case "$PREFIX" in
    /usr|/usr/local) UNIT_DIR=$PREFIX/lib/systemd/user ;;
    *) UNIT_DIR=/etc/systemd/user ;;
esac

systemctl --global disable coralos-welcome.service 2>/dev/null || true
rm -f "$UNIT_DIR/coralos-welcome.service"
rm -rf "$PREFIX/lib/coralos/welcome"
rmdir "$PREFIX/lib/coralos" 2>/dev/null || true
rm -f "$PREFIX/bin/coralos-welcome"
rm -f "$PREFIX/share/coralos/welcome.conf"
rm -rf "$PREFIX/share/coralos/branding"
rmdir "$PREFIX/share/coralos" 2>/dev/null || true

rm -f /usr/share/gnome-background-properties/coralos-wallpapers.xml
if [ -e /usr/share/glib-2.0/schemas/95_coralos-wallpaper.gschema.override ]; then
    rm -f /usr/share/glib-2.0/schemas/95_coralos-wallpaper.gschema.override
    glib-compile-schemas /usr/share/glib-2.0/schemas
fi

if [ -e /usr/share/gdm/dconf/95-coralos-branding ]; then
    rm -f /usr/share/gdm/dconf/95-coralos-branding
    if [ -x /usr/share/gdm/generate-config ]; then /usr/share/gdm/generate-config || true; fi
fi

if [ "$PURGE" = 1 ]; then
    rm -f /etc/coralos/welcome.conf
    rmdir /etc/coralos 2>/dev/null || true
fi

echo "CoralOS welcome screen removed. The stock login applies from the next login."
