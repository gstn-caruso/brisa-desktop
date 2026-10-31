"""Real headless integration; Python standard library only.

Contract: Meson builds build/brisa-desktop. With --smoke-test, it presents a
GTK4 window, prints BRISA_SMOKE_TEST_WINDOW_MAPPED from that window's GTK map
signal handler (not startup), then exits automatically with status zero.

Run: python3 tests/test_headless_weston.py -v
"""

import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAPPED = "BRISA_SMOKE_TEST_WINDOW_MAPPED"


def run_client(result_path, mode, executable, *arguments):
    """Run inside Weston, preserving client status independently of Weston."""
    display = Path(os.environ["XDG_RUNTIME_DIR"]) / os.environ["WAYLAND_DISPLAY"]
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(2)
        connection.connect(str(display))
    command = [executable] + (["--smoke-test"] if mode == "prototype" else []) + list(arguments)
    try:
        client = subprocess.run(command, capture_output=True, timeout=8 if mode == "prototype" else 2)
        result = {
            "returncode": client.returncode,
            "stdout": client.stdout.decode(errors="replace"),
            "stderr": client.stderr.decode(errors="replace"),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as error:
        # subprocess.run kills and reaps this specific client on timeout.
        result = {
            "returncode": None,
            "stdout": (error.stdout or b"").decode(errors="replace"),
            "stderr": (error.stderr or b"").decode(errors="replace"),
            "timed_out": True,
        }
    result["private_socket_connected"] = True
    Path(result_path).write_text(json.dumps(result))


class HeadlessWestonIntegration(unittest.TestCase):
    def run_in_weston(self, mode, executable):
        with tempfile.TemporaryDirectory(prefix="brisa-smoke-") as directory:
            runtime = Path(directory)
            runtime.chmod(0o700)
            result_path = runtime / "client.json"
            log_path = runtime / "weston.log"
            environment = os.environ.copy()
            environment.pop("WAYLAND_SOCKET", None)
            environment.pop("DISPLAY", None)
            environment.update(
                XDG_RUNTIME_DIR=str(runtime),
                WAYLAND_DISPLAY="brisa-smoke",
                GDK_BACKEND="wayland",
                GSK_RENDERER="cairo",
                GTK_A11Y="none",
                WAYLAND_DEBUG="client",
                DBUS_SESSION_BUS_ADDRESS=f"unix:path={runtime}/no-session-bus",
            )
            command = [
                shutil.which("weston"),
                "-B", "headless", "--renderer=pixman",
                "--width=800", "--height=600",
                "--socket=brisa-smoke", "--no-config",
                "--", sys.executable, str(Path(__file__).resolve()),
                "--weston-client", str(result_path), mode, str(executable),
            ]
            with log_path.open("w") as log:
                compositor = subprocess.Popen(
                    command, env=environment, cwd=ROOT,
                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                )
                try:
                    compositor.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self.fail(f"{mode}: Weston did not exit automatically within 15s:\n{log_path.read_text()}")
                finally:
                    # Only our private process group, including shell children.
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
            self.assertEqual(compositor.returncode, 0, f"{mode}: Weston failed:\n{diagnostics}")
            self.assertTrue(result_path.is_file(), f"{mode}: client harness failed:\n{diagnostics}")
            result = json.loads(result_path.read_text())
            self.assertTrue(result["private_socket_connected"], diagnostics)
            return result

    def givenHeadlessWeston_whenPrototypeStarts_thenWindowMapsAndExitsCleanly(self):
        self.assertIsNotNone(shutil.which("weston"), "Prerequisite missing: weston")
        reference_client = shutil.which("weston-simple-shm")
        self.assertIsNotNone(reference_client, "Prerequisite missing: weston-simple-shm")

        baseline = self.run_in_weston("baseline", reference_client)
        # A frame callback requires an actual rendered Wayland client, not just
        # a live compositor or a startup log. The reference client is bounded
        # deliberately; only the prototype is required to exit on its own.
        self.assertRegex(
            baseline["stderr"], r"wl_callback(?:@|#)\d+\.done\(",
            f"Weston baseline could not deliver a frame: {baseline}",
        )

        prototype = ROOT / "build" / "brisa-desktop"
        self.assertTrue(
            prototype.is_file() and os.access(prototype, os.X_OK),
            "Weston baseline passed (real frame callback and compositor exit 0); "
            "missing executable: build/brisa-desktop. Required API: "
            "build/brisa-desktop --smoke-test, GTK map marker "
            f"{MAPPED}, then automatic exit 0. Build with Meson first.",
        )
        result = self.run_in_weston("prototype", prototype)
        self.assertFalse(result["timed_out"], f"Prototype did not exit automatically: {result}")
        self.assertEqual(result["returncode"], 0, f"Prototype did not exit cleanly: {result}")
        self.assertIn(MAPPED, result["stdout"].splitlines(), f"No GTK map signal reported: {result}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--weston-client":
        run_client(*sys.argv[2:])
    else:
        loader = unittest.TestLoader()
        loader.testMethodPrefix = "given"
        unittest.main(testLoader=loader)
