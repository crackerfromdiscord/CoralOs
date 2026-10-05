from coralos_welcome.config import WelcomeConfig, apply_file, branding_dir, load_config, resolve_asset


def write(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_defaults_when_no_files(tmp_path):
    config = load_config(search_paths=[tmp_path / "missing.conf"])
    assert config == WelcomeConfig()


def test_later_layers_override_earlier(tmp_path):
    system = write(tmp_path, "system.conf", "[welcome]\ngreeting = Hi {name}\nfade_ms = 100\n")
    user = write(tmp_path, "user.conf", "[welcome]\nfade_ms = 250\nenabled = no\n")
    config = load_config(search_paths=[system, user])
    assert config.greeting == "Hi {name}"
    assert config.fade_ms == 250
    assert config.enabled is False


def test_lists_and_bad_values(tmp_path):
    path = write(
        tmp_path,
        "c.conf",
        "[welcome]\nwait_for_units = a.target; b.target\naccent_color = red\n"
        "name_source = nickname\nmin_display_ms = -5\nbogus = 1\n",
    )
    warnings = []
    config = WelcomeConfig()
    apply_file(config, path, warnings)
    assert config.wait_for_units == ["a.target", "b.target"]
    assert config.accent_color == WelcomeConfig().accent_color
    assert config.name_source == "real_name"
    assert config.min_display_ms == WelcomeConfig().min_display_ms
    assert len(warnings) == 4


def test_shipped_defaults_file_matches_builtin():
    from pathlib import Path

    shipped = Path(__file__).resolve().parents[1] / "data" / "welcome.conf"
    warnings = []
    config = load_config(search_paths=[shipped], warnings=warnings)
    assert warnings == []
    assert config == WelcomeConfig()


def test_background_dim_range(tmp_path):
    conf = tmp_path / "w.conf"
    conf.write_text("[welcome]\nbackground_dim = 140\n")
    warnings = []
    config = load_config(search_paths=[conf], warnings=warnings)
    assert config.background_dim == WelcomeConfig().background_dim
    assert any("background_dim" in w for w in warnings)


def test_resolve_asset(tmp_path):
    branding = tmp_path / "share" / "coralos" / "branding"
    branding.mkdir(parents=True)
    (branding / "logo.png").write_bytes(b"png")
    other = tmp_path / "elsewhere.png"
    other.write_bytes(b"png")
    prefix = str(tmp_path)
    assert branding_dir(prefix) == branding
    assert resolve_asset("logo.png", prefix) == branding / "logo.png"
    assert resolve_asset(str(other), prefix) == other
    assert resolve_asset("missing.png", prefix) is None
    assert resolve_asset("  ", prefix) is None


def test_shipped_branding_assets_exist():
    for name in (WelcomeConfig().background_image, WelcomeConfig().branding_logo):
        assert resolve_asset(name) is not None, name
