"""Real layer-shell integration; Python standard library only.

Run: PYTHONDONTWRITEBYTECODE=1 python3 tests/test_headless_labwc.py -v
Contract: build/brisa-desktop --smoke-test maps only brisa-background and
brisa-bar; build/brisa-dock --smoke-test maps only brisa-dock. Each client
reports its GTK map signals and exits zero, reserving only panel edges.
Traces stay separate per process. Labwc must also exit zero. No host display or session bus.
"""

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from test_headless_weston import run_client


ROOT = Path(__file__).resolve().parents[1]


def mapped_names(trace):
    """IDs are local to one client's trace, never shared between processes."""
    names = []
    for surface in re.finditer(
        r'zwlr_layer_shell_v1[@#]\d+\.get_layer_surface\('
        r'new id zwlr_layer_surface_v1[@#]\d+, '
        r'wl_surface[@#](\d+), [^,]+, \d+, "([^"]+)"\)', trace,
    ):
        protocol = rf"wl_surface[@#]{surface[1]}\."
        attachment = re.search(
            protocol + r"attach\(wl_buffer[@#]\d+,", trace[surface.end():]
        )
        if attachment and re.search(
            protocol + r"commit\(\)",
            trace[surface.end() + attachment.end():],
        ):
            names.append(surface[2])
    return names


def run_dock_lifecycle(result_path, desktop_executable, dock_executable):
    """Private labwc client: normal binaries, external dock restart, bounded cleanup."""
    result = {"private_socket_connected": False, "error": None}
    clients = []
    logs = []
    runtime = Path(result_path).parent

    def start(executable, name):
        trace = runtime / f"{name}.trace"
        log = trace.open("w")
        logs.append(log)
        client = subprocess.Popen([executable], stdout=subprocess.DEVNULL, stderr=log)
        clients.append(client)
        return client, trace

    def wait_for_maps(client, trace, expected):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if client.poll() is not None:
                raise AssertionError(f"{trace.stem} exited before mapping: {client.returncode}")
            if set(expected).issubset(mapped_names(trace.read_text())):
                return
            time.sleep(0.02)
        raise AssertionError(f"{trace.stem} did not map {expected} within 3s: {trace.read_text()}")

    try:
        display = Path(os.environ["XDG_RUNTIME_DIR"]) / os.environ["WAYLAND_DISPLAY"]
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(2)
            connection.connect(str(display))
        result["private_socket_connected"] = True
        desktop, desktop_trace = start(desktop_executable, "desktop")
        wait_for_maps(desktop, desktop_trace, ["brisa-background", "brisa-bar"])
        dock, dock_trace = start(dock_executable, "dock-first")
        wait_for_maps(dock, dock_trace, ["brisa-dock"])
        dock.terminate()
        dock.wait(timeout=2)
        result["desktop_alive_after_dock_exit"] = desktop.poll() is None
        replacement, replacement_trace = start(dock_executable, "dock-restarted")
        wait_for_maps(replacement, replacement_trace, ["brisa-dock"])
        # Allow an accidental desktop shutdown/respawn time to become observable.
        time.sleep(0.2)
        result["desktop_alive_after_restart"] = desktop.poll() is None
        result["replacement_alive"] = replacement.poll() is None
        result["desktop_trace"] = desktop_trace.read_text()
        result["dock_traces"] = [dock_trace.read_text(), replacement_trace.read_text()]
    except (AssertionError, OSError, subprocess.TimeoutExpired) as error:
        result["error"] = str(error)
    finally:
        for client in reversed(clients):
            if client.poll() is None:
                client.terminate()
                try:
                    client.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    client.kill()
                    client.wait(timeout=1)
        for log in logs:
            log.close()
        Path(result_path).write_text(json.dumps(result))


class HeadlessLabwcIntegration(unittest.TestCase):
    def run_in_labwc(self, executable, *arguments, client_mode="--labwc-client"):
        with tempfile.TemporaryDirectory(prefix="brisa-layer-smoke-") as directory:
            runtime = Path(directory)
            runtime.chmod(0o700)
            config = runtime / "config"
            config.mkdir()
            (config / "rc.xml").write_text(
                "<labwc_config><core><xwayland>no</xwayland></core></labwc_config>\n"
            )
            (config / "autostart").write_text("")
            result_path = runtime / "client.json"
            log_path = runtime / "labwc.log"
            environment = os.environ.copy()
            for variable in (
                "DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET",
                "DBUS_STARTER_ADDRESS", "DBUS_STARTER_BUS_TYPE",
            ):
                environment.pop(variable, None)
            environment.update(
                XDG_RUNTIME_DIR=str(runtime),
                XDG_CONFIG_HOME=str(config),
                WLR_BACKENDS="headless",
                WLR_RENDERER="pixman",
                WLR_HEADLESS_OUTPUTS="1",
                LABWC_UPDATE_ACTIVATION_ENV="0",
                GDK_BACKEND="wayland",
                GSK_RENDERER="cairo",
                GTK_A11Y="none",
                WAYLAND_DEBUG="client",
                DBUS_SESSION_BUS_ADDRESS=f"unix:path={runtime}/no-session-bus",
            )
            session = shlex.join([
                sys.executable, str(Path(__file__).resolve()),
                client_mode, str(result_path), str(executable), *arguments,
            ])
            with log_path.open("w") as log:
                compositor = subprocess.Popen(
                    [shutil.which("labwc"), "-C", str(config), "-S", session],
                    env=environment, cwd=ROOT, stdout=log,
                    stderr=subprocess.STDOUT, start_new_session=True,
                )
                try:
                    compositor.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self.fail(f"Labwc did not exit within 15s:\n{log_path.read_text()}")
                finally:
                    # Reap only the private compositor/session process group.
                    for stop_signal in (signal.SIGTERM, signal.SIGKILL):
                        try:
                            os.killpg(compositor.pid, stop_signal)
                        except ProcessLookupError:
                            pass
                        try:
                            compositor.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            pass
            diagnostics = log_path.read_text()
            self.assertEqual(compositor.returncode, 0, f"Labwc failed:\n{diagnostics}")
            self.assertTrue(result_path.is_file(), f"Client harness failed:\n{diagnostics}")
            result = json.loads(result_path.read_text())
            self.assertTrue(result["private_socket_connected"], diagnostics)
            return result

    def givenHeadlessLabwc_whenSessionStartsWithLeftDock_thenBackgroundBarAndDockMapAndExitCleanly(self):
        self.assertIsNotNone(shutil.which("labwc"), "Prerequisite missing: labwc")
        for binary in ("brisa-desktop", "brisa-dock"):
            executable = ROOT / "build" / binary
            self.assertTrue(
                executable.is_file() and os.access(executable, os.X_OK),
                f"Missing build/{binary}; compile with meson compile -C build first",
            )

        result = self.run_in_labwc(
            "bash", "scripts/session.sh", "--smoke-test", "--dock-position=left",
            client_mode="--labwc-session-client",
        )
        self.assertFalse(result["timed_out"], f"Session did not exit automatically: {result}")
        self.assertEqual(
            result["returncode"], 0,
            "Required API: bash scripts/session.sh --smoke-test --dock-position=left; "
            f"start brisa-desktop and brisa-dock and exit 0. Result: {result}",
        )
        for surface in ("BACKGROUND", "BAR", "DOCK"):
            self.assertIn(
                f"BRISA_SMOKE_TEST_{surface}_MAPPED", result["stdout"].splitlines(),
                f"Session did not report {surface} mapping: {result}",
            )

    def givenHeadlessLabwc_whenShellStarts_thenBarAndDockReserveTheirEdges(self):
        self.assert_shell_reserves_edges(2)

    def givenHeadlessLabwc_whenDockPositionIsLeft_thenDockReservesLeftEdgeAndBarIsUnchanged(self):
        self.assert_shell_reserves_edges(4, "--dock-position=left")

    def givenHeadlessLabwc_whenDockPositionIsRight_thenDockReservesRightEdgeAndBarIsUnchanged(self):
        self.assert_shell_reserves_edges(8, "--dock-position=right")

    def givenUnknownDockPosition_whenDockStarts_thenRejectsBeforeMappingWithValidPositions(self):
        self.assertIsNotNone(shutil.which("labwc"), "Prerequisite missing: labwc")
        executable = ROOT / "build" / "brisa-dock"
        self.assertTrue(
            executable.is_file() and os.access(executable, os.X_OK),
            "Missing build/brisa-dock; compile with meson compile -C build first",
        )

        result = self.run_in_labwc(executable, "--dock-position=diagonal")
        self.assertFalse(result["timed_out"], "Invalid dock position must exit promptly")
        self.assertNotEqual(
            result["returncode"], 0,
            "Unknown dock position 'diagonal' was accepted instead of rejected; "
            f"GTK map signals: {result['stdout']!r}",
        )
        for value in ("dock-position", "diagonal", "bottom", "left", "right"):
            self.assertIn(value, result["stderr"], "Missing useful CLI diagnostic")
        self.assertNotRegex(
            result["stderr"], r"wl_surface[@#]\d+\.attach\(wl_buffer[@#]\d+,",
            "Invalid dock position must be rejected before mapping any surface",
        )

    def givenHeadlessLabwc_whenStandaloneDockStarts_thenOnlyDockMapsReservesBottomAndExitsCleanly(self):
        self.assertIsNotNone(shutil.which("labwc"), "Prerequisite missing: labwc")
        executable = ROOT / "build" / "brisa-dock"
        self.assertTrue(
            executable.is_file() and os.access(executable, os.X_OK),
            "Missing executable: build/brisa-dock. Required API: "
            "build/brisa-dock --smoke-test; map only brisa-dock, reserve the "
            "bottom edge, report BRISA_SMOKE_TEST_DOCK_MAPPED, then exit 0.",
        )

        result = self.run_in_labwc(executable)
        self.assertFalse(result["timed_out"], f"Dock did not exit automatically: {result}")
        self.assertEqual(result["returncode"], 0, f"Dock failed: {result}")
        trace = result["stderr"]
        surfaces = list(re.finditer(
            r'zwlr_layer_shell_v1[@#]\d+\.get_layer_surface\('
            r'new id zwlr_layer_surface_v1[@#](\d+), '
            r'wl_surface[@#](\d+), [^,]+, \d+, "([^"]+)"\)', trace,
        ))
        self.assertEqual(
            [surface[3] for surface in surfaces], ["brisa-dock"],
            "Standalone dock must create only brisa-dock, without background or bar",
        )
        surface = surfaces[0]
        layer_id, surface_id, _ = surface.groups()
        layer = rf"zwlr_layer_surface_v1[@#]{layer_id}\."
        wayland_surface = rf"wl_surface[@#]{surface_id}\."
        attachment = re.search(
            wayland_surface + r"attach\(wl_buffer[@#]\d+,", trace[surface.end():]
        )
        self.assertIsNotNone(attachment, "Dock: no actual buffer attached")
        attached_at = surface.end() + attachment.end()
        commit = re.search(wayland_surface + r"commit\(\)", trace[attached_at:])
        self.assertIsNotNone(commit, "Dock: attached buffer never committed")
        before_map = trace[surface.end():attached_at + commit.start()]
        anchors = re.findall(layer + r"set_anchor\((\d+)\)", before_map)
        self.assertTrue(anchors, "Dock: missing anchor before mapping")
        self.assertEqual(int(anchors[-1]), 2, "Dock must anchor only to the bottom edge")
        zones = re.findall(layer + r"set_exclusive_zone\((-?\d+)\)", before_map)
        self.assertTrue(zones, "Dock: missing exclusive zone before mapping")
        self.assertGreater(int(zones[-1]), 0, "Dock must reserve bottom edge space")
        self.assertIn("BRISA_SMOKE_TEST_DOCK_MAPPED", result["stdout"].splitlines())

    def givenDesktopAndDock_whenDockIsClosedAndRestarted_thenDesktopStaysMappedWithoutDuplicateDock(self):
        self.assertIsNotNone(shutil.which("labwc"), "Prerequisite missing: labwc")
        desktop = ROOT / "build" / "brisa-desktop"
        dock = ROOT / "build" / "brisa-dock"
        for executable in (desktop, dock):
            self.assertTrue(
                executable.is_file() and os.access(executable, os.X_OK),
                f"Missing {executable}; compile with meson compile -C build first",
            )

        result = self.run_in_labwc(
            desktop, str(dock), client_mode="--labwc-dock-lifecycle"
        )
        self.assertIsNone(result["error"], f"Lifecycle harness failed: {result['error']}")
        self.assertTrue(result["desktop_alive_after_dock_exit"], "Closing dock closed desktop")
        self.assertTrue(result["desktop_alive_after_restart"], "Restarting dock closed desktop")
        self.assertTrue(result["replacement_alive"], "Replacement dock exited unexpectedly")
        for trace in result["dock_traces"]:
            self.assertEqual(mapped_names(trace), ["brisa-dock"], "Each dock must map exactly once")
        self.assertCountEqual(
            mapped_names(result["desktop_trace"]), ["brisa-background", "brisa-bar"],
            "Desktop must map only background and bar; its embedded dock duplicates "
            "the independent dock and survives that dock's shutdown/restart",
        )

    def assert_shell_reserves_edges(self, dock_anchor, *arguments):
        # Check dock first so its position coverage runs even while desktop still
        # creates a duplicate dock. Never combine protocol IDs across clients.
        self.assert_client_reserves_edges(
            "brisa-dock", ["brisa-dock"], dock_anchor, *arguments
        )
        self.assert_client_reserves_edges(
            "brisa-desktop", ["brisa-background", "brisa-bar"], dock_anchor
        )

    def assert_client_reserves_edges(self, binary, expected_names, dock_anchor, *arguments):
        self.assertIsNotNone(shutil.which("labwc"), "Prerequisite missing: labwc")
        executable = ROOT / "build" / binary
        self.assertTrue(
            executable.is_file() and os.access(executable, os.X_OK),
            f"Missing build/{binary}; compile with meson compile -C build first",
        )

        result = self.run_in_labwc(executable, *arguments)
        self.assertFalse(result["timed_out"], f"Brisa did not exit automatically: {result}")
        self.assertEqual(result["returncode"], 0, f"Brisa failed: {result}")
        trace = result["stderr"]
        self.assertRegex(
            trace, r'wl_registry[@#]\d+\.global\(\d+, "zwlr_layer_shell_v1", \d+\)',
            "Private labwc did not advertise layer-shell",
        )
        surfaces = list(re.finditer(
            r'zwlr_layer_shell_v1[@#]\d+\.get_layer_surface\('
            r'new id zwlr_layer_surface_v1[@#](\d+), '
            r'wl_surface[@#](\d+), [^,]+, \d+, "([^"]+)"\)', trace,
        ))
        self.assertEqual(
            len(surfaces), len(expected_names),
            "Labwc advertised layer-shell and client/compositor exited 0, but "
            f"{binary} created {len(surfaces)} layer surfaces; expected {expected_names}. "
            f"Client stdout: {result['stdout']!r}",
        )
        self.assertCountEqual(
            [surface[3] for surface in surfaces], expected_names,
        )
        self.assertEqual(len({surface[1] for surface in surfaces}), len(expected_names))
        self.assertEqual(len({surface[2] for surface in surfaces}), len(expected_names))

        for surface in surfaces:
            layer_id, surface_id, namespace = surface.groups()
            layer = rf"zwlr_layer_surface_v1[@#]{layer_id}\."
            wayland_surface = rf"wl_surface[@#]{surface_id}\."
            # A non-null buffer committed to this wl_surface is the actual map,
            # unlike a stdout marker or the initial empty configure-triggering commit.
            attachment = re.search(
                wayland_surface + r"attach\(wl_buffer[@#]\d+,", trace[surface.end():]
            )
            self.assertIsNotNone(attachment, f"{namespace}: no actual buffer attached")
            attached_at = surface.end() + attachment.end()
            commit = re.search(wayland_surface + r"commit\(\)", trace[attached_at:])
            self.assertIsNotNone(commit, f"{namespace}: attached buffer never committed")
            mapped_at = attached_at + commit.start()
            before_map = trace[surface.end():mapped_at]

            anchors = re.findall(layer + r"set_anchor\((\d+)\)", before_map)
            expected_anchor = (
                15 if namespace == "brisa-background" else
                13 if namespace == "brisa-bar" else dock_anchor
            )
            self.assertTrue(anchors, f"{namespace}: missing anchor before mapping")
            self.assertEqual(int(anchors[-1]), expected_anchor, namespace)
            zones = re.findall(layer + r"set_exclusive_zone\((-?\d+)\)", before_map)
            self.assertTrue(zones, f"{namespace}: no exclusive zone before mapping")
            if namespace == "brisa-background":
                self.assertRegex(
                    surface[0], r', 0, "brisa-background"\)',
                    "Background must use the BACKGROUND layer",
                )
                self.assertEqual(int(zones[-1]), -1, "Background must not reserve space")
                keyboard_modes = re.findall(
                    layer + r"set_keyboard_interactivity\((\d+)\)", before_map
                )
                self.assertTrue(keyboard_modes, "Background: missing keyboard mode")
                self.assertEqual(int(keyboard_modes[-1]), 0, "Background keyboard must be NONE")
            else:
                self.assertGreater(int(zones[-1]), 0, f"{namespace}: must reserve space")

            configurations = list(re.finditer(
                layer + r"configure\((\d+), \d+, \d+\)", before_map
            ))
            self.assertTrue(configurations, f"{namespace}: no configure before mapping")
            self.assertTrue(
                any(re.search(
                    layer + rf"ack_configure\({configuration[1]}\)",
                    before_map[configuration.end():],
                ) for configuration in configurations),
                f"{namespace}: configure serial not acknowledged before mapping",
            )
            marker = f"BRISA_SMOKE_TEST_{namespace.removeprefix('brisa-').upper()}_MAPPED"
            self.assertIn(marker, result["stdout"].splitlines(), namespace)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--labwc-client":
        run_client(sys.argv[2], "prototype", sys.argv[3], *sys.argv[4:])
    elif len(sys.argv) > 1 and sys.argv[1] == "--labwc-session-client":
        run_client(sys.argv[2], "session", sys.argv[3], *sys.argv[4:])
    elif len(sys.argv) > 1 and sys.argv[1] == "--labwc-dock-lifecycle":
        run_dock_lifecycle(*sys.argv[2:])
    else:
        loader = unittest.TestLoader()
        loader.testMethodPrefix = "given"
        unittest.main(testLoader=loader)
