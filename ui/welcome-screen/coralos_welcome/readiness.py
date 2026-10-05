"""Session readiness probes.

Each probe watches one signal that the desktop session is up (GNOME Shell on
the bus, a systemd user target being active, gnome-session reaching its
Running phase). The welcome screen reports ``fraction`` for the progress ring
and ``ready`` once every probe is satisfied. Probes that cannot apply on this
system (e.g. not a GNOME session) resolve as satisfied so they never block.
The timeline also has a hard ``max_wait_ms`` so login can never hang here.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from gi.repository import Gio, GLib

POLL_MS = 250


class Probe:
    name = "probe"

    def __init__(self) -> None:
        self.done = False
        self._on_change: Optional[Callable[[], None]] = None

    def start(self, bus: Optional[Gio.DBusConnection], on_change: Callable[[], None]) -> None:
        self._on_change = on_change
        if bus is None:
            self._finish()
            return
        self._start(bus)

    def _start(self, bus: Gio.DBusConnection) -> None:
        self._finish()

    def _finish(self) -> None:
        if not self.done:
            self.done = True
            if self._on_change:
                self._on_change()

    def stop(self) -> None:
        pass


class BusNameProbe(Probe):
    """Satisfied once a well-known name (e.g. org.gnome.Shell) has an owner."""

    def __init__(self, bus_name: str) -> None:
        super().__init__()
        self.bus_name = bus_name
        self.name = f"bus:{bus_name}"
        self._watch = 0

    def _start(self, bus):
        self._watch = Gio.bus_watch_name_on_connection(
            bus, self.bus_name, Gio.BusNameWatcherFlags.NONE, lambda *a: self._finish(), None
        )

    def stop(self):
        if self._watch:
            Gio.bus_unwatch_name(self._watch)
            self._watch = 0


class PollingProbe(Probe):
    def __init__(self) -> None:
        super().__init__()
        self._source = 0
        self._bus = None
        self._busy = False

    def _start(self, bus):
        self._bus = bus
        self._tick()
        if not self.done:
            self._source = GLib.timeout_add(POLL_MS, self._tick)

    def _tick(self):
        if self.done:
            self._source = 0
            return GLib.SOURCE_REMOVE
        if not self._busy:
            self._busy = True
            self.poll(self._bus)
        return GLib.SOURCE_CONTINUE

    def _reply(self, satisfied: bool) -> None:
        self._busy = False
        if satisfied:
            self._finish()

    def poll(self, bus) -> None:
        raise NotImplementedError

    def stop(self):
        if self._source:
            GLib.source_remove(self._source)
            self._source = 0


class GnomeSessionProbe(PollingProbe):
    """Satisfied when gnome-session reports it reached the Running phase."""

    name = "gnome-session"

    def poll(self, bus):
        def done(conn, result):
            try:
                (running,) = conn.call_finish(result).unpack()
                self._reply(bool(running))
            except GLib.Error as error:
                # No gnome-session on the bus (other desktop): don't block on it.
                if error.matches(Gio.dbus_error_quark(), Gio.DBusError.SERVICE_UNKNOWN):
                    self._reply(True)
                else:
                    self._reply(False)

        bus.call(
            "org.gnome.SessionManager",
            "/org/gnome/SessionManager",
            "org.gnome.SessionManager",
            "IsSessionRunning",
            None,
            GLib.VariantType.new("(b)"),
            Gio.DBusCallFlags.NO_AUTO_START,
            1000,
            None,
            done,
        )


class SystemdUnitProbe(PollingProbe):
    """Satisfied when a systemd --user unit is active, or doesn't exist here."""

    def __init__(self, unit: str) -> None:
        super().__init__()
        self.unit = unit
        self.name = f"unit:{unit}"
        self._path: Optional[str] = None

    def _get_props(self, bus, callback):
        bus.call(
            "org.freedesktop.systemd1",
            self._path,
            "org.freedesktop.DBus.Properties",
            "GetAll",
            GLib.Variant("(s)", ("org.freedesktop.systemd1.Unit",)),
            GLib.VariantType.new("(a{sv})"),
            Gio.DBusCallFlags.NONE,
            1000,
            None,
            callback,
        )

    def poll(self, bus):
        def got_props(conn, result):
            try:
                (props,) = conn.call_finish(result).unpack()
            except GLib.Error:
                self._reply(False)
                return
            if props.get("LoadState") != "loaded":
                self._reply(True)  # unit not installed on this system: skip
            else:
                self._reply(props.get("ActiveState") == "active")

        def loaded(conn, result):
            try:
                (self._path,) = conn.call_finish(result).unpack()
            except GLib.Error:
                self._reply(True)  # no systemd user manager: skip
                return
            self._get_props(bus, got_props)

        if self._path:
            self._get_props(bus, got_props)
            return
        bus.call(
            "org.freedesktop.systemd1",
            "/org/freedesktop/systemd1",
            "org.freedesktop.systemd1.Manager",
            "LoadUnit",
            GLib.Variant("(s)", (self.unit,)),
            GLib.VariantType.new("(o)"),
            Gio.DBusCallFlags.NO_AUTO_START,
            1000,
            None,
            loaded,
        )


class SimulatedProbe(Probe):
    """Used by --preview: completes after a fixed delay."""

    def __init__(self, delay_ms: int) -> None:
        super().__init__()
        self.delay_ms = delay_ms
        self.name = f"simulated:{delay_ms}ms"
        self._source = 0

    def start(self, bus, on_change):
        self._on_change = on_change
        self._source = GLib.timeout_add(self.delay_ms, self._fire)

    def _fire(self):
        self._source = 0
        self._finish()
        return GLib.SOURCE_REMOVE

    def stop(self):
        if self._source:
            GLib.source_remove(self._source)
            self._source = 0


class SessionReadiness:
    """Aggregates probes into a progress fraction and a ready flag."""

    def __init__(self, probes: List[Probe], settle_ms: int = 0) -> None:
        self.probes = probes
        self.settle_ms = settle_ms
        self._settled = False
        self._settle_source = 0

    @property
    def fraction(self) -> float:
        if self._settled:
            return 1.0
        if not self.probes:
            return 0.9
        done = sum(1 for probe in self.probes if probe.done)
        return 0.9 * done / len(self.probes)

    @property
    def ready(self) -> bool:
        return self._settled

    def start(self) -> None:
        bus = None
        if any(not isinstance(p, SimulatedProbe) for p in self.probes):
            try:
                bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            except GLib.Error:
                bus = None
        for probe in self.probes:
            probe.start(bus, self._changed)
        self._changed()

    def _changed(self) -> None:
        if self._settled or self._settle_source:
            return
        if all(probe.done for probe in self.probes):
            if self.settle_ms:
                self._settle_source = GLib.timeout_add(self.settle_ms, self._settle)
            else:
                self._settled = True

    def _settle(self):
        self._settled = True
        self._settle_source = 0
        return GLib.SOURCE_REMOVE

    def stop(self) -> None:
        for probe in self.probes:
            probe.stop()
        if self._settle_source:
            GLib.source_remove(self._settle_source)
            self._settle_source = 0


def build_probes(config) -> List[Probe]:
    probes: List[Probe] = [BusNameProbe(name) for name in config.wait_for_bus_names]
    probes += [SystemdUnitProbe(unit) for unit in config.wait_for_units]
    if config.wait_for_gnome_session:
        probes.append(GnomeSessionProbe())
    return probes
