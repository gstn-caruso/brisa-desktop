"""Real layer-shell integration; Python standard library only.

Run: PYTHONDONTWRITEBYTECODE=1 python3 tests/test_headless_labwc.py -v
Contract: build/brisa-desktop --smoke-test maps brisa-bar and brisa-dock as
separate layer surfaces, reserves their edges, reports their GTK map signals,
and exits zero. Labwc must also exit zero. No host display or session bus.
"""

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

from test_headless_weston import run_client


ROOT = Path(__file__).resolve().parents[1]


class HeadlessLabwcIntegration(unittest.TestCase):
    def run_in_labwc(self, executable):
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
                "--labwc-client", str(result_path), str(executable),
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

    def givenHeadlessLabwc_whenShellStarts_thenBarAndDockReserveTheirEdges(self):
        self.assertIsNotNone(shutil.which("labwc"), "Prerequisite missing: labwc")
        executable = ROOT / "build" / "brisa-desktop"
        self.assertTrue(
            executable.is_file() and os.access(executable, os.X_OK),
            "Missing build/brisa-desktop; compile with meson compile -C build first",
        )

        result = self.run_in_labwc(executable)
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
            len(surfaces), 2,
            "Labwc advertised layer-shell and client/compositor exited 0, but "
            f"Brisa created {len(surfaces)} layer surfaces; expected brisa-bar and "
            f"brisa-dock. Client stdout: {result['stdout']!r}",
        )
        self.assertCountEqual(
            [surface[3] for surface in surfaces], ["brisa-bar", "brisa-dock"]
        )
        self.assertEqual(len({surface[1] for surface in surfaces}), 2)
        self.assertEqual(len({surface[2] for surface in surfaces}), 2)

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
            expected_anchor = 13 if namespace == "brisa-bar" else 2
            self.assertTrue(anchors, f"{namespace}: missing anchor before mapping")
            self.assertEqual(int(anchors[-1]), expected_anchor, namespace)
            zones = re.findall(layer + r"set_exclusive_zone\((-?\d+)\)", before_map)
            self.assertTrue(zones, f"{namespace}: no exclusive zone before mapping")
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
        run_client(sys.argv[2], "prototype", sys.argv[3])
    else:
        loader = unittest.TestLoader()
        loader.testMethodPrefix = "given"
        unittest.main(testLoader=loader)
