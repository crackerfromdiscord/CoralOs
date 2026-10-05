"""Information about the logged-in Linux user (name and avatar).

Uses AccountsService over D-Bus when available, which is the same source GDM
and GNOME Settings use, and falls back to the passwd database and ``~/.face``.
"""

from __future__ import annotations

import os
import pwd
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .config import WelcomeConfig


@dataclass
class UserInfo:
    username: str
    real_name: str = ""
    icon_file: Optional[str] = None

    @property
    def first_name(self) -> str:
        parts = self.real_name.split()
        return parts[0] if parts else self.username

    def display_name(self, source: str) -> str:
        if source == "username":
            return self.username
        if source == "first_name":
            return self.first_name
        return self.real_name.strip() or self.username

    @property
    def initials(self) -> str:
        words = (self.real_name or self.username).replace(".", " ").replace("_", " ").split()
        letters = "".join(word[0] for word in words[:2] if word)
        return (letters or self.username[:1] or "?").upper()


def _usable_image(path: Optional[str]) -> Optional[str]:
    if path and os.path.isfile(path) and os.access(path, os.R_OK) and os.path.getsize(path) > 0:
        return path
    return None


def _accounts_service_lookup(uid: int):
    """Return (real_name, icon_file) from AccountsService, or (None, None)."""
    try:
        from gi.repository import Gio, GLib
    except ImportError:
        return None, None
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        reply = bus.call_sync(
            "org.freedesktop.Accounts",
            "/org/freedesktop/Accounts",
            "org.freedesktop.Accounts",
            "FindUserById",
            GLib.Variant("(x)", (uid,)),
            GLib.VariantType.new("(o)"),
            Gio.DBusCallFlags.NONE,
            2000,
            None,
        )
        (object_path,) = reply.unpack()
        values = {}
        for prop in ("RealName", "IconFile"):
            result = bus.call_sync(
                "org.freedesktop.Accounts",
                object_path,
                "org.freedesktop.DBus.Properties",
                "Get",
                GLib.Variant("(ss)", ("org.freedesktop.Accounts.User", prop)),
                GLib.VariantType.new("(v)"),
                Gio.DBusCallFlags.NONE,
                2000,
                None,
            )
            values[prop] = result.unpack()[0]
        return values.get("RealName") or None, values.get("IconFile") or None
    except Exception:  # D-Bus unavailable, service missing, timeouts...
        return None, None


def current_user(
    config: WelcomeConfig,
    accounts_lookup: Callable[[int], tuple] = _accounts_service_lookup,
) -> UserInfo:
    uid = os.getuid()
    entry = pwd.getpwuid(uid)
    username = entry.pw_name
    gecos_name = entry.pw_gecos.split(",")[0].strip()
    home = Path(entry.pw_dir or Path.home())

    as_name, as_icon = accounts_lookup(uid)
    real_name = (as_name or gecos_name or "").strip()


    configured = os.path.expanduser(config.avatar) if config.avatar else None
    icon = (
        _usable_image(configured)
        or _usable_image(as_icon)
        or _usable_image(str(home / ".face"))
        or _usable_image(str(home / ".face.icon"))
    )
    return UserInfo(username=username, real_name=real_name, icon_file=icon)


def format_greeting(template: str, user: UserInfo, name_source: str) -> str:
    values = {
        "name": user.display_name(name_source),
        "username": user.username,
        "real_name": user.real_name or user.username,
        "first_name": user.first_name,
    }
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return f"Welcome, {values['name']}"
