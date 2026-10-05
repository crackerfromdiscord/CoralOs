#!/bin/sh
# Install the CoralOS welcome screen (Ubuntu 24.04 / GNOME).
# Usage: sudo ./install.sh [--prefix DIR] [--no-gdm-branding] [--no-wallpaper] [--no-enable]
# Nothing here touches PAM or GDM's authentication; see docs/login-screen.md.
set -eu

PREFIX=/usr/local
GDM_BRANDING=1
WALLPAPER=1
ENABLE=1
while [ $# -gt 0 ]; do
    case "$1" in
        --prefix) PREFIX=$2; shift 2 ;;
        --prefix=*) PREFIX=${1#--prefix=}; shift ;;
        --no-gdm-branding) GDM_BRANDING=0; shift ;;
        --no-wallpaper) WALLPAPER=0; shift ;;
        --no-enable) ENABLE=0; shift ;;
        -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "install.sh must be run as root (sudo ./install.sh)" >&2
    exit 1
fi

SRC=$(cd "$(dirname "$0")" && pwd)
LIB_DIR=$PREFIX/lib/coralos/welcome
SHARE_DIR=$PREFIX/share/coralos
case "$PREFIX" in
    /usr|/usr/local) UNIT_DIR=$PREFIX/lib/systemd/user ;;
    *) UNIT_DIR=/etc/systemd/user ;;
esac
GDM_DCONF_DIR=/usr/share/gdm/dconf
SCHEMA_DIR=/usr/share/glib-2.0/schemas
WP_LIST_DIR=/usr/share/gnome-background-properties

subst() { sed "s|@PREFIX@|$PREFIX|g" "$1" > "$2"; }

if ! python3 -c 'import gi; gi.require_version("Gtk", "4.0"); gi.require_foreign("cairo"); from gi.repository import Gtk' 2>/dev/null; then
    echo "Installing dependencies: python3-gi python3-gi-cairo gir1.2-gtk-4.0"
    apt-get install -y python3-gi python3-gi-cairo gir1.2-gtk-4.0
fi

echo "Installing CoralOS welcome screen into $PREFIX"
rm -rf "$LIB_DIR/coralos_welcome"
install -d "$LIB_DIR/coralos_welcome" "$SHARE_DIR/branding" "$UNIT_DIR" "$PREFIX/bin" /etc/coralos
install -m644 "$SRC"/coralos_welcome/*.py "$SRC"/coralos_welcome/style.css "$LIB_DIR/coralos_welcome/"
subst "$SRC/bin/coralos-welcome" "$PREFIX/bin/coralos-welcome"
chmod 755 "$PREFIX/bin/coralos-welcome"
install -m644 "$SRC/data/welcome.conf" "$SHARE_DIR/welcome.conf"
install -m644 "$SRC"/data/branding/*.png "$SHARE_DIR/branding/"
subst "$SRC/data/coralos-welcome.service" "$UNIT_DIR/coralos-welcome.service"
chmod 644 "$UNIT_DIR/coralos-welcome.service"

if [ ! -e /etc/coralos/welcome.conf ]; then
    cat > /etc/coralos/welcome.conf <<CONF
# System-wide overrides for the CoralOS welcome screen.
# See $SHARE_DIR/welcome.conf for every key and its default.
[welcome]
CONF
fi

if [ "$GDM_BRANDING" = 1 ] && [ -d "$GDM_DCONF_DIR" ]; then
    echo "Adding CoralOS logo to the GDM login screen"
    subst "$SRC/data/gdm/95-coralos-branding" "$GDM_DCONF_DIR/95-coralos-branding"
    chmod 644 "$GDM_DCONF_DIR/95-coralos-branding"
    # Recompile the greeter defaults now; GDM also does this on every start.
    if [ -x /usr/share/gdm/generate-config ]; then /usr/share/gdm/generate-config || true; fi
fi

if [ "$WALLPAPER" = 1 ]; then
    echo "Setting the CoralOS wallpaper as the GNOME default"
    subst "$SRC/data/desktop/95_coralos-wallpaper.gschema.override" "$SCHEMA_DIR/95_coralos-wallpaper.gschema.override"
    chmod 644 "$SCHEMA_DIR/95_coralos-wallpaper.gschema.override"
    glib-compile-schemas "$SCHEMA_DIR"
    install -d "$WP_LIST_DIR"
    subst "$SRC/data/desktop/coralos-wallpapers.xml" "$WP_LIST_DIR/coralos-wallpapers.xml"
    chmod 644 "$WP_LIST_DIR/coralos-wallpapers.xml"
fi

if [ "$ENABLE" = 1 ]; then
    systemctl --global enable coralos-welcome.service
fi

echo "Done. Log out and back in to see it, or run: coralos-welcome --preview"
