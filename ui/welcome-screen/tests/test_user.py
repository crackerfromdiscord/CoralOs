import os
import pwd

from coralos_welcome.config import WelcomeConfig
from coralos_welcome.user import UserInfo, current_user, format_greeting


def test_display_names():
    user = UserInfo(username="abbo", real_name="Abbo Wolf")
    assert user.display_name("real_name") == "Abbo Wolf"
    assert user.display_name("first_name") == "Abbo"
    assert user.display_name("username") == "abbo"
    assert user.initials == "AW"
    assert UserInfo(username="dev").display_name("real_name") == "dev"
    assert UserInfo(username="john.smith").initials == "JS"


def test_format_greeting_falls_back_on_bad_template():
    user = UserInfo(username="abbo", real_name="Abbo Wolf")
    assert format_greeting("Welcome, {name}", user, "first_name") == "Welcome, Abbo"
    assert format_greeting("Hey {username}!", user, "real_name") == "Hey abbo!"
    assert format_greeting("Hi {nope}", user, "username") == "Welcome, abbo"


def test_current_user_is_dynamic(tmp_path):
    avatar = tmp_path / "me.png"
    avatar.write_bytes(b"\x89PNG fake")
    me = pwd.getpwuid(os.getuid()).pw_name

    user = current_user(WelcomeConfig(), accounts_lookup=lambda uid: ("Real Person", str(avatar)))
    assert user.username == me
    assert user.real_name == "Real Person"
    assert user.icon_file == str(avatar)

    configured = WelcomeConfig(avatar=str(avatar))
    user = current_user(configured, accounts_lookup=lambda uid: (None, "/nonexistent.png"))
    assert user.icon_file == str(avatar)
