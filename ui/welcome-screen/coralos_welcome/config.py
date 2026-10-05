"""Layered configuration for the welcome screen.

Files are INI-style keyfiles with a ``[welcome]`` section. Later layers override
earlier ones, so a CoralOS settings app only needs to write the user file:

1. built-in defaults (``DEFAULTS``)
2. ``$CORALOS_PREFIX/share/coralos/welcome.conf`` (shipped defaults)
3. ``/etc/coralos/welcome.conf`` (system administrator)
4. ``$XDG_CONFIG_HOME/coralos/welcome.conf`` (per user)
5. a file passed with ``--config`` or ``$CORALOS_WELCOME_CONFIG``
"""

from __future__ import annotations

import configparser
import os
import re
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Iterable, List, Optional

SECTION = "welcome"
NAME_SOURCES = ("real_name", "first_name", "username")
_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


@dataclass
class WelcomeConfig:
    enabled: bool = True
    greeting: str = "Welcome, {name}"
    name_source: str = "real_name"
    avatar: str = ""
    accent_color: str = "#FF7A66"
    background_color: str = "#0B0F14"
    text_color: str = "#F2F4F7"
    background_image: str = "coralos-wallpaper.png"
    background_dim: int = 62
    show_branding: bool = True
    branding_logo: str = "coralos-logo-wordmark.png"
    branding_logo_height: int = 28
    branding_text: str = "CoralOS"
    avatar_size: int = 168
    min_display_ms: int = 1400
    max_wait_ms: int = 20000
    settle_ms: int = 500
    complete_ms: int = 450
    check_ms: int = 450
    success_hold_ms: int = 900
    fade_ms: int = 700
    wait_for_gnome_session: bool = True
    wait_for_bus_names: List[str] = field(default_factory=lambda: ["org.gnome.Shell"])
    wait_for_units: List[str] = field(default_factory=lambda: ["graphical-session.target"])
    allow_skip: bool = True
    all_monitors: bool = True


DEFAULTS = WelcomeConfig()


def branding_dir(prefix: Optional[str] = None) -> Path:
    prefix = prefix or os.environ.get("CORALOS_PREFIX")
    if prefix:
        return Path(prefix) / "share" / "coralos" / "branding"
    return Path(__file__).resolve().parent.parent / "data" / "branding"


def resolve_asset(value: str, prefix: Optional[str] = None) -> Optional[Path]:
    """Absolute/~ paths are used as-is; bare names are looked up in the branding dir."""
    value = value.strip()
    if not value:
        return None
    path = Path(os.path.expanduser(value))
    if not path.is_absolute():
        path = branding_dir(prefix) / path
    return path if path.is_file() else None


def default_search_paths(prefix: Optional[str] = None) -> List[Path]:
    prefix = prefix or os.environ.get("CORALOS_PREFIX")
    if prefix:
        shipped = Path(prefix) / "share" / "coralos" / "welcome.conf"
    else:
        # Running from a source checkout: ui/welcome-screen/data/welcome.conf
        shipped = Path(__file__).resolve().parent.parent / "data" / "welcome.conf"
    xdg_config = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return [
        shipped,
        Path("/etc/coralos/welcome.conf"),
        Path(xdg_config) / "coralos" / "welcome.conf",
    ]


def _parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"not a boolean: {value!r}")


def _parse_list(value: str) -> List[str]:
    return [item.strip() for item in re.split(r"[;,]", value) if item.strip()]


def _coerce(name: str, raw: str, current):
    if isinstance(current, bool):
        return _parse_bool(raw)
    if isinstance(current, int):
        number = int(raw.strip())
        if number < 0:
            raise ValueError(f"{name} must be >= 0")
        if name.endswith("_dim") and number > 100:
            raise ValueError(f"{name} must be 0-100")
        return number
    if isinstance(current, list):
        return _parse_list(raw)
    value = raw.strip()
    if name.endswith("_color") and not _HEX_COLOR.match(value):
        raise ValueError(f"{name} must be #RRGGBB or #RRGGBBAA, got {value!r}")
    if name == "name_source" and value not in NAME_SOURCES:
        raise ValueError(f"name_source must be one of {', '.join(NAME_SOURCES)}")
    return value


def apply_file(config: WelcomeConfig, path: Path, warnings: Optional[list] = None) -> bool:
    """Overlay ``path`` onto ``config``. Invalid keys are skipped with a warning."""
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with open(path, encoding="utf-8") as handle:
            parser.read_file(handle)
    except FileNotFoundError:
        return False
    except (OSError, configparser.Error) as error:
        if warnings is not None:
            warnings.append(f"{path}: {error}")
        return False

    if not parser.has_section(SECTION):
        return True
    known = {f.name for f in fields(WelcomeConfig)}
    for key, raw in parser.items(SECTION):
        if key not in known:
            if warnings is not None:
                warnings.append(f"{path}: unknown key {key!r}")
            continue
        try:
            setattr(config, key, _coerce(key, raw, getattr(config, key)))
        except ValueError as error:
            if warnings is not None:
                warnings.append(f"{path}: {error}")
    return True


def load_config(
    extra: Optional[str] = None,
    search_paths: Optional[Iterable[Path]] = None,
    warnings: Optional[list] = None,
) -> WelcomeConfig:
    config = WelcomeConfig()
    paths = list(search_paths) if search_paths is not None else default_search_paths()
    extra = extra or os.environ.get("CORALOS_WELCOME_CONFIG")
    if extra:
        paths.append(Path(extra))
    for path in paths:
        apply_file(config, Path(path), warnings)
    return config
