from coralos_welcome.config import WelcomeConfig, apply_file, load_config


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
