# CoralOS welcome / login screen

After you type your password, CoralOS shows a full-screen welcome: your profile
picture with a progress ring around it and "Welcome, {name}" underneath. The
ring tracks the desktop session as it loads. When the session is ready the
ring closes, a checkmark appears, and the screen fades into the desktop.

Target: Ubuntu 24.04 LTS, GNOME (the default "Ubuntu" session, Wayland or X11).

## How it works (and why it is safe)

```
GDM (stock, handles the password / PAM)    <- only change: CoralOS logo via dconf
        |
        v  user session starts (systemd --user)
gnome-shell ready -> coralos-welcome.service (fullscreen GTK 4 window)
        |                watches: org.gnome.Shell on the bus,
        |                         graphical-session.target active,
        |                         gnome-session IsSessionRunning()
        v
ring closes -> checkmark -> fade -> desktop
```

- **Authentication is untouched.** GDM, PAM, the lock screen, fingerprint and
  smartcard login all work as before. The welcome screen runs as your user,
  after you've logged in, with no extra privileges.
- **Why not a custom greeter?** LightDM/GDM end the greeter process the moment
  the session starts, so a greeter can't animate *while the desktop loads*.
  Replacing GDM would also mean re-implementing authentication and GNOME's lock
  screen integration. A post-login session splash gets the experience without
  that risk.
- **It can't trap you.** The splash only ever covers the screen. If it crashes,
  the desktop is simply visible. It gives up waiting after `max_wait_ms`
  (default 20 s), and systemd kills it after 90 s (`RuntimeMaxSec`) no matter
  what. Esc / Enter / Space / click skips it.
- **Dynamic user.** The name comes from AccountsService (what GNOME Settings >
  Users edits), falling back to the passwd entry. The picture comes from the
  AccountsService icon, then `~/.face`, then generated initials.

## Files

| Source (`ui/welcome-screen/`) | Installed to (default prefix `/usr/local`) |
| --- | --- |
| `coralos_welcome/` (Python package) | `/usr/local/lib/coralos/welcome/coralos_welcome/` |
| `bin/coralos-welcome` | `/usr/local/bin/coralos-welcome` |
| `data/coralos-welcome.service` | `/usr/local/lib/systemd/user/coralos-welcome.service`, enabled globally via `/etc/systemd/user/gnome-session-initialized.target.wants/` |
| `data/welcome.conf` | `/usr/local/share/coralos/welcome.conf` (shipped defaults) |
| (created if missing) | `/etc/coralos/welcome.conf` (system overrides) |
| `data/branding/*.png` | `/usr/local/share/coralos/branding/` (wallpapers, logo, logo + wordmark) |
| `data/gdm/95-coralos-branding` | `/usr/share/gdm/dconf/95-coralos-branding` (GDM logo: `coralos-logo-wordmark.png`) |
| `data/desktop/95_coralos-wallpaper.gschema.override` | `/usr/share/glib-2.0/schemas/` (default desktop + lock screen wallpaper) |
| `data/desktop/coralos-wallpapers.xml` | `/usr/share/gnome-background-properties/` (lists both wallpapers in Settings > Appearance) |

### Branding assets

| File | Used for |
| --- | --- |
| `coralos-wallpaper.png` | Welcome screen backdrop (dimmed by `background_dim`) and the default desktop/lock-screen wallpaper, so the fade lands on the same picture. |
| `coralos-wallpaper-branded.png` | Optional wallpaper with the logo, selectable in Settings > Appearance. |
| `coralos-logo-wordmark.png` | GDM login screen logo, and the small logo at the bottom of the welcome screen. |
| `coralos-logo.png` | Square logo mark, for places that need an icon. |

To change them, replace the PNGs (keep the names) and reinstall, or point
`background_image` / `branding_logo` in `welcome.conf` at other files.

The default-wallpaper override only changes GNOME's *default*. Anyone who has
already picked a wallpaper keeps it; to switch to CoralOS run
`gsettings reset org.gnome.desktop.background picture-uri` and
`gsettings reset org.gnome.desktop.background picture-uri-dark`.

Code layout, so later work (e.g. a CoralOS Settings page) knows where to plug in:

- `config.py`: layered settings (`welcome.conf`). Settings UIs write `~/.config/coralos/welcome.conf`.
- `user.py`: who is logged in, display name, avatar.
- `readiness.py`: probes that decide when the session is "loaded".
- `timeline.py`: the animation state machine, with no GTK dependency (unit tested).
- `ring.py`: Cairo drawing of the avatar, ring and checkmark.
- `app.py` + `style.css`: windows (one per monitor), layout, theming.

## Install

```sh
git clone https://github.com/crackerfromdiscord/CoralOs.git
cd CoralOs/ui/welcome-screen
sudo ./install.sh                # --no-gdm-branding: leave GDM 100% stock
                                 # --no-wallpaper: don't change the default wallpaper
```

The installer pulls in `python3-gi python3-gi-cairo gir1.2-gtk-4.0` if they are
missing (they're normally preinstalled on Ubuntu Desktop). It does **not**
restart GDM, so your current session isn't touched.

## Testing

1. **Preview without logging out** (in any graphical session, no install needed):
   ```sh
   cd CoralOs/ui/welcome-screen
   python3 -m coralos_welcome --preview              # windowed, fake 3 s load
   python3 -m coralos_welcome --preview --fullscreen --simulate-ms 5000
   python3 -m coralos_welcome --preview --loop       # repeat, handy for design tweaks
   ```
   After installing, `coralos-welcome --preview` does the same.
2. **Real login:** after `sudo ./install.sh`, log out (or reboot), and log in
   from GDM. You should see the CoralOS logo at the bottom of the GDM screen,
   then the welcome screen right after you type your password.
3. **Check it ran / debug:**
   ```sh
   systemctl --user status coralos-welcome.service
   journalctl --user -u coralos-welcome.service -b   # shows user, avatar, config warnings
   ```
   Run it by hand with `coralos-welcome --verbose --windowed` to see the phases
   and readiness in the terminal.
4. **Unit tests** (Linux, Python 3):
   ```sh
   cd CoralOs/ui/welcome-screen && python3 -m pytest tests
   ```
5. **Try customisations:** put overrides in `~/.config/coralos/welcome.conf`,
   then run `coralos-welcome --preview`:
   ```ini
   [welcome]
   greeting = Hey {first_name}
   accent_color = #4FD1C5
   ```
   Every key and its default is listed in `data/welcome.conf`.

Tip: test with a second user account first, so your main account is a known-good
fallback. You can also switch to a text console with Ctrl+Alt+F3 at any time.

## Reverting to the default Ubuntu login

Any one of these works. They are listed from lightest to most complete:

- **Turn it off for one user:** `systemctl --user mask coralos-welcome.service`
  (undo with `unmask`), or set `enabled = false` in `~/.config/coralos/welcome.conf`.
- **Turn it off for everyone, keep files:** `sudo systemctl --global disable coralos-welcome.service`.
- **Remove everything:**
  ```sh
  cd CoralOs/ui/welcome-screen
  sudo ./uninstall.sh            # add --purge to also delete /etc/coralos/welcome.conf
  ```
  This disables the unit, deletes the installed files, the GDM logo drop-in
  and the wallpaper override, and recompiles GDM's settings and the GSettings
  schemas. Users who never changed their wallpaper go back to Ubuntu's. The stock login comes back from the
  next login. No reboot is needed.
- **Manual fallback** (if the repo isn't around):
  ```sh
  sudo systemctl --global disable coralos-welcome.service
  sudo rm -rf /usr/local/lib/coralos /usr/local/share/coralos /usr/local/bin/coralos-welcome \
              /usr/local/lib/systemd/user/coralos-welcome.service /etc/coralos
  sudo rm -f /usr/share/gdm/dconf/95-coralos-branding && sudo /usr/share/gdm/generate-config
  sudo rm -f /usr/share/glib-2.0/schemas/95_coralos-wallpaper.gschema.override              /usr/share/gnome-background-properties/coralos-wallpapers.xml
  sudo glib-compile-schemas /usr/share/glib-2.0/schemas
  ```
- **Locked out of the desktop?** (This shouldn't happen, because the splash
  exits on its own.) Press Ctrl+Alt+F3, log in on the text console, and run
  the manual fallback above.

## Known limitations

- GNOME only for now: the unit hangs off `gnome-session-initialized.target`,
  so it doesn't start in other desktops.
- There is a short moment between GDM disappearing and the welcome screen
  appearing while gnome-shell starts. Hiding it would mean patching gnome-shell.
- In the vanilla "GNOME" session (not the default "Ubuntu" one), GNOME opens the
  Activities overview at startup, and the overview can appear over the welcome
  screen.
- Windows that pop up during login (e.g. update notifications) can show above
  the splash until it fades.
