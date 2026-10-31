"""Real mouse interaction in the X11 fallback; no host display or session bus.

Run: PYTHONDONTWRITEBYTECODE=1 python3 tests/test_background_context_menu.py -v
Visible contract: right-clicking empty background opens a context menu beside
that point; Escape dismisses it. The «Apariencia» menu offers «Cambiar fondo»:
clicking that labeled action changes the artwork, dismisses the menu, and keeps
the bar/dock foreground and window geometry. Wayland input is a separate scenario.
"""

import csv
import io
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BackgroundContextMenuIntegration(unittest.TestCase):
    def givenVisibleBackground_whenRightClicked_thenContextMenuAppearsAndEscapeDismissesIt(self):
        self._exercise_background_menu()

    def givenVisibleBackground_whenChangeBackgroundSelected_thenArtworkChangesAndPanelsRemain(self):
        self.assertIsNotNone(shutil.which("tesseract"), "Prerequisite missing: tesseract")
        self._exercise_background_menu(select_background=True)

    def givenBottomDockIcon_whenRightClickedAndLeftSelected_thenDockMovesToLeftVertically(self):
        self.assertIsNotNone(shutil.which("tesseract"), "Prerequisite missing: tesseract")
        self._exercise_background_menu(select_dock_position=True)

    def givenBottomDockSeparator_whenDraggedUp_thenDockAndIconsGrowKeepingBottomAnchor(self):
        self._exercise_background_menu(resize_dock=True)

    def _exercise_background_menu(self, select_background=False, select_dock_position=False,
                                  resize_dock=False):
        for tool in ("Xvfb", "xdotool", "xwd", "ffmpeg", "dbus-run-session"):
            self.assertIsNotNone(shutil.which(tool), f"Prerequisite missing: {tool}")
        executable = ROOT / "build" / "brisa-desktop"
        self.assertTrue(
            executable.is_file() and os.access(executable, os.X_OK),
            "Missing build/brisa-desktop; run meson compile -C build first",
        )
        with tempfile.TemporaryDirectory(prefix="brisa-background-input-") as directory:
            runtime = Path(directory)
            runtime.chmod(0o700)
            environment = os.environ.copy()
            for variable in (
                "DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET",
                "DBUS_SESSION_BUS_ADDRESS", "DBUS_STARTER_ADDRESS",
                "DBUS_STARTER_BUS_TYPE", "AT_SPI_BUS_ADDRESS",
            ):
                environment.pop(variable, None)
            environment.update(
                XDG_RUNTIME_DIR=str(runtime), XDG_CONFIG_HOME=str(runtime / "config"),
                GDK_BACKEND="x11", GSK_RENDERER="cairo", GTK_A11Y="none",
            )
            processes = []
            with (runtime / "session.log").open("w+") as log:
                try:
                    # -displayfd allocates an unused display without touching the host.
                    with (runtime / "display").open("w+") as display_file:
                        server = subprocess.Popen(
                            ["Xvfb", "-displayfd", str(display_file.fileno()),
                             "-screen", "0", "1200x800x24", "-nolisten", "tcp"],
                            pass_fds=(display_file.fileno(),), env=environment,
                            stdout=log, stderr=log, start_new_session=True,
                        )
                        processes.append(server)
                        deadline = time.monotonic() + 5
                        display = ""
                        while time.monotonic() < deadline and server.poll() is None:
                            display_file.seek(0)
                            display = display_file.read().strip()
                            if display:
                                break
                            time.sleep(0.05)
                        self.assertTrue(display, "Private Xvfb failed to start")
                    environment["DISPLAY"] = f":{display}"
                    client = subprocess.Popen(
                        ["dbus-run-session", "--", str(executable)], cwd=ROOT,
                        env=environment, stdout=log, stderr=log, start_new_session=True,
                    )
                    processes.append(client)

                    def xdo(*arguments):
                        return subprocess.run(
                            ["xdotool", *arguments], env=environment,
                            capture_output=True, text=True, timeout=3,
                        )

                    deadline = time.monotonic() + 5
                    window = ""
                    while time.monotonic() < deadline and client.poll() is None:
                        result = xdo("search", "--onlyvisible", "--name", "^Brisa$")
                        if result.returncode == 0 and result.stdout.strip():
                            window = result.stdout.splitlines()[0]
                            break
                        time.sleep(0.05)
                    log.flush()
                    self.assertTrue(window, f"Brisa did not map:\n{(runtime / 'session.log').read_text()}")
                    geometry = xdo("getwindowgeometry", "--shell", window)
                    self.assertEqual(geometry.returncode, 0, geometry.stderr)
                    bounds = dict(line.split("=", 1) for line in geometry.stdout.splitlines())
                    self.assertGreaterEqual(int(bounds["WIDTH"]), 800)
                    self.assertGreaterEqual(int(bounds["HEIGHT"]), 600)
                    crop_x, crop_y = int(bounds["X"]) + 220, int(bounds["Y"]) + 100

                    def screenshot(window_id=None, crop=None):
                        capture = subprocess.run(
                            ["xwd", *(["-id", window_id] if window_id else ["-root"]),
                             "-silent"], env=environment,
                            capture_output=True, timeout=3, check=True,
                        )
                        image = subprocess.run(
                            ["ffmpeg", "-v", "error", "-f", "xwd_pipe", "-i", "pipe:0",
                             *(["-vf", crop] if crop else []),
                             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                            input=capture.stdout, capture_output=True, timeout=5, check=True,
                        ).stdout
                        self.assertTrue(image, "Empty screenshot")
                        return image

                    def background_region():
                        image = screenshot(crop=f"crop=500:400:{crop_x}:{crop_y}")
                        self.assertEqual(len(image), 500 * 400 * 3, "Invalid screenshot setup")
                        return image

                    def visible_popovers():
                        result = xdo("search", "--onlyvisible", "--name", "^brisa-desktop$")
                        popovers = {}
                        for candidate in result.stdout.splitlines():
                            geometry = xdo("getwindowgeometry", "--shell", candidate)
                            if geometry.returncode != 0:
                                continue
                            box = dict(line.split("=", 1) for line in geometry.stdout.splitlines())
                            if int(box["WIDTH"]) > 30 and int(box["HEIGHT"]) > 30:
                                # GTK reports both the dock menu and the hovered center
                                # icon's tooltip as _NET_WM_WINDOW_TYPE_MENU on X11.
                                # Exclude only the observed tooltip text, not a menu
                                # with missing labels: its assertions must still fail.
                                if select_dock_position and set(menu_lines(candidate, box)) == {"Terminal"}:
                                    continue
                                popovers[candidate] = box
                        return popovers

                    def changed_pixels(before, after):
                        return sum(
                            max(abs(before[i + c] - after[i + c]) for c in range(3)) > 12
                            for i in range(0, len(before), 3)
                        )

                    def panel_foreground():
                        # Exclude the ticking clock and allow translucent panel backgrounds
                        # to follow the wallpaper; preserve the opaque text/icon pixels.
                        return (
                            screenshot(crop=f"crop=150:40:{bounds['X']}:{bounds['Y']}")
                            + screenshot(crop=f"crop={bounds['WIDTH']}:100:{bounds['X']}:"
                                         f"{int(bounds['Y']) + int(bounds['HEIGHT']) - 100}")
                        )

                    def menu_lines(popup, box):
                        # OCR the native drawable, not the root (which omits GTK popups).
                        menu_image = screenshot(window_id=popup)
                        self.assertEqual(len(menu_image), int(box["WIDTH"]) * int(box["HEIGHT"]) * 3)
                        ppm = f"P6\n{box['WIDTH']} {box['HEIGHT']}\n255\n".encode() + menu_image
                        text = subprocess.run(
                            ["tesseract", "stdin", "stdout", "--psm", "6", "tsv"],
                            input=ppm, capture_output=True, timeout=5, check=True,
                        ).stdout.decode()
                        lines = {}
                        for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
                            if row["text"].strip():
                                key = (row["block_num"], row["par_num"], row["line_num"])
                                lines.setdefault(key, []).append(row)
                        return {" ".join(word["text"] for word in words): words
                                for words in lines.values()}

                    if resize_dock:
                        width, height = int(bounds["WIDTH"]), int(bounds["HEIGHT"])
                        strip_height = 180

                        def dock_measurements():
                            image = screenshot(crop=f"crop={width}:{strip_height}:{bounds['X']}:"
                                                    f"{int(bounds['Y']) + height - strip_height}")
                            # Long horizontal luminance edges belong to the dock border,
                            # not to individual icon artwork or the smooth wallpaper.
                            edges = []
                            for y in range(2, strip_height - 2):
                                run_start = None
                                for x in range(width):
                                    i = (y * width + x) * 3
                                    edge = max(image[i] - image[i - 2 * width * 3],
                                               image[i] - image[i + 2 * width * 3]) > 45
                                    if edge and run_start is None:
                                        run_start = x
                                    if not edge and run_start is not None:
                                        if x - run_start > 200:
                                            edges.append((run_start, x - 1, y))
                                        run_start = None
                            self.assertTrue(edges, "No visible horizontal dock borders in root capture")
                            box = (min(e[0] for e in edges), min(e[2] for e in edges),
                                   max(e[1] for e in edges), max(e[2] for e in edges))
                            # Warm artwork (folder/browser) is distinct from blue wallpaper
                            # and the translucent panel; include antialiased edges tolerantly.
                            warm = [(x, y) for y in range(box[1] + 2, box[3] - 1)
                                    for x in range(box[0], box[2] + 1)
                                    if (lambda r, g, b: r > b + 20 and r > g + 10)(
                                        *image[(y * width + x) * 3:(y * width + x) * 3 + 3])]
                            self.assertGreater(len(warm), 50, "No warm icon artwork in dock capture")
                            icon_box = (min(p[0] for p in warm), min(p[1] for p in warm),
                                        max(p[0] for p in warm), max(p[1] for p in warm))
                            return image, box, icon_box

                        self.assertEqual(xdo("mousemove", "--window", window, "200", "150").returncode, 0)
                        time.sleep(0.4)
                        before, dock_before, icons_before = dock_measurements()
                        center_y = (dock_before[1] + dock_before[3]) // 2
                        # The existing separator is just before the final 48px trash item.
                        # Locate its visible vertical stroke, not a widget/state hook.
                        candidates = []
                        for x in range(dock_before[2] - 65, dock_before[2] - 35):
                            contrast = sum(
                                before[(y * width + x) * 3] - max(
                                    before[(y * width + x - 3) * 3],
                                    before[(y * width + x + 3) * 3]) > 20
                                for y in range(center_y - 12, center_y + 13)
                            )
                            if contrast >= 23:
                                candidates.append(x)
                        self.assertTrue(candidates, "No visible separator stroke before trash icon")
                        separator_x = candidates[len(candidates) // 2]
                        separator_y = height - strip_height + center_y
                        self.assertEqual(xdo("mousemove", "--window", window,
                                             str(separator_x), str(separator_y)).returncode, 0)
                        self.assertEqual(xdo("mousedown", "1").returncode, 0)
                        try:
                            for delta in range(4, 49, 4):
                                self.assertEqual(xdo("mousemove", "--sync", "--window", window,
                                                     str(separator_x), str(separator_y - delta)).returncode, 0)
                                time.sleep(0.02)
                        finally:
                            self.assertEqual(xdo("mouseup", "1").returncode, 0)
                        self.assertEqual(xdo("mousemove", "--window", window, "200", "150").returncode, 0)
                        time.sleep(0.3)
                        _, dock_after, icons_after = dock_measurements()
                        evidence = (f"dock bbox {dock_before} -> {dock_after}; "
                                    f"warm icon bbox {icons_before} -> {icons_after}")
                        self.assertGreater(dock_after[3] - dock_after[1],
                                           dock_before[3] - dock_before[1] + 4,
                                           "Dragging separator upward did not grow dock: " + evidence)
                        self.assertGreater(dock_after[2] - dock_after[0],
                                           dock_before[2] - dock_before[0] + 4, evidence)
                        self.assertGreater(icons_after[3] - icons_after[1],
                                           icons_before[3] - icons_before[1] + 3,
                                           "Icon artwork did not grow: " + evidence)
                        self.assertLessEqual(abs(dock_after[3] - dock_before[3]), 2,
                                             "Bottom anchor moved: " + evidence)
                        self.assertLessEqual(abs(dock_after[0] + dock_after[2] - width), 6,
                                             "Dock lost horizontal centering: " + evidence)
                        self.assertEqual(xdo("getwindowgeometry", "--shell", window).stdout,
                                         geometry.stdout, "Desktop geometry changed")
                        return

                    if select_dock_position:
                        width, height = int(bounds["WIDTH"]), int(bounds["HEIGHT"])

                        def dock_regions():
                            return (
                                screenshot(crop=f"crop=120:{height - 180}:{bounds['X']}:"
                                                f"{int(bounds['Y']) + 70}"),
                                screenshot(crop=f"crop={width}:100:{bounds['X']}:"
                                                f"{int(bounds['Y']) + height - 100}"),
                            )

                        # The center icon in the horizontal dock, not its empty margin.
                        self.assertEqual(xdo("mousemove", "--window", window,
                                             str(width // 2), str(height - 44)).returncode, 0)
                        time.sleep(0.4)
                        left_before, bottom_before = dock_regions()
                        self.assertEqual(xdo("click", "3").returncode, 0)
                        deadline = time.monotonic() + 3
                        popovers = {}
                        while time.monotonic() < deadline:
                            self.assertIsNone(client.poll(), "Brisa exited after right-clicking dock icon")
                            popovers = visible_popovers()
                            if popovers:
                                break
                            time.sleep(0.1)
                        self.assertEqual(len(popovers), 1,
                                         f"Right-clicking a dock icon must open one position menu; observed: {popovers}")
                        popup, box = next(iter(popovers.items()))
                        time.sleep(0.2)
                        lines = menu_lines(popup, box)
                        # Tesseract can read the accented ó as é at this small size.
                        # Accept only that known heading ambiguity, never action labels.
                        self.assertTrue(
                            any(heading in lines for heading in ("Posición del dock", "Posicién del dock")),
                            f"Missing visible «Posición del dock» heading; observed: {list(lines)}",
                        )
                        for label in ("Abajo", "Izquierda", "Derecha"):
                            self.assertIn(label, lines,
                                          f"Missing visible «{label}» in dock menu; observed: {list(lines)}")
                        word = lines["Izquierda"][0]
                        self.assertEqual(xdo(
                            "mousemove", str(int(box["X"]) + int(word["left"]) + int(word["width"]) // 2),
                            str(int(box["Y"]) + int(word["top"]) + int(word["height"]) // 2),
                        ).returncode, 0)
                        self.assertEqual(xdo("click", "1").returncode, 0)
                        # Move away so a tooltip cannot masquerade as changed dock pixels.
                        self.assertEqual(xdo("mousemove", "--window", window, "700", "150").returncode, 0)
                        deadline = time.monotonic() + 3
                        while visible_popovers() and time.monotonic() < deadline:
                            time.sleep(0.05)
                        self.assertFalse(visible_popovers(), "Selecting «Izquierda» did not dismiss the menu")
                        deadline = time.monotonic() + 3
                        while time.monotonic() < deadline:
                            self.assertIsNone(client.poll(), "Brisa exited while moving dock")
                            left_after, bottom_after = dock_regions()
                            if changed_pixels(left_before, left_after) > 500:
                                break
                            time.sleep(0.1)
                        changed = [i // 3 for i in range(0, len(left_before), 3)
                                   if max(abs(left_before[i + c] - left_after[i + c])
                                          for c in range(3)) > 12]
                        self.assertGreater(len(changed), 500, "«Izquierda» did not render a dock at the left edge")
                        span_x = max(p % 120 for p in changed) - min(p % 120 for p in changed) + 1
                        span_y = max(p // 120 for p in changed) - min(p // 120 for p in changed) + 1
                        self.assertGreater(span_y, 250, "Left dock does not have a vertical footprint")
                        self.assertGreater(span_y, span_x * 3, "Left dock is not vertically oriented")
                        self.assertGreater(changed_pixels(bottom_before, bottom_after), 500,
                                           "Dock remained unchanged at the bottom after selecting «Izquierda»")
                        geometry_after = xdo("getwindowgeometry", "--shell", window)
                        self.assertEqual(geometry_after.stdout, geometry.stdout, "Desktop geometry changed")
                        return

                    # Interior background: no bar, dock, clock, or tooltip in this crop.
                    self.assertEqual(xdo("mousemove", "--window", window, "400", "250").returncode, 0)
                    time.sleep(0.4)
                    before = background_region()
                    self.assertGreater(len(set(before)), 50, "Background did not render")
                    panels_before = panel_foreground() if select_background else b""
                    self.assertEqual(xdo("click", "3").returncode, 0)
                    deadline = time.monotonic() + 3
                    popovers = {}
                    while time.monotonic() < deadline:
                        self.assertIsNone(client.poll(), "Brisa exited after right-click")
                        popovers = visible_popovers()
                        if popovers:
                            break
                        time.sleep(0.1)
                    self.assertEqual(len(popovers), 1, "Expected one visible Apariencia popup")
                    popup, box = next(iter(popovers.items()))
                    self.assertLess(abs(int(box["X"]) - (int(bounds["X"]) + 400)), 150)
                    self.assertLess(abs(int(box["Y"]) - (int(bounds["Y"]) + 250)), 150)
                    # Native GTK popups have a different depth from the root on Xvfb.
                    # Read their actual drawable: root GetImage omits their pixels.
                    time.sleep(0.2)
                    menu_image = screenshot(window_id=popup)
                    self.assertEqual(len(menu_image), int(box["WIDTH"]) * int(box["HEIGHT"]) * 3)
                    self.assertGreater(len(set(menu_image)), 50, "Context menu did not render")
                    if select_background:
                        # OCR only the real native drawable, then click the named action;
                        # do not assume a button order or activate an unrelated «Cerrar».
                        lines = menu_lines(popup, box)
                        action = lines.get("Cambiar fondo")
                        observed = " | ".join(lines)
                        self.assertIsNotNone(
                            action,
                            f"Missing visible action «Cambiar fondo» in Apariencia menu; observed: {observed}",
                        )
                        word = action[0]
                        action_x = int(box["X"]) + int(word["left"]) + int(word["width"]) // 2
                        action_y = int(box["Y"]) + int(word["top"]) + int(word["height"]) // 2
                        self.assertEqual(xdo("mousemove", str(action_x), str(action_y)).returncode, 0)
                        self.assertEqual(xdo("click", "1").returncode, 0)
                    else:
                        self.assertEqual(xdo("key", "Escape").returncode, 0)
                    deadline = time.monotonic() + 3
                    while visible_popovers() and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.assertFalse(visible_popovers(), "Context menu was not dismissed")
                    if select_background:
                        deadline = time.monotonic() + 3
                        changed = 0
                        while time.monotonic() < deadline:
                            self.assertIsNone(client.poll(), "Brisa exited after changing background")
                            changed = changed_pixels(before, background_region())
                            if changed > 500:
                                break
                            time.sleep(0.1)
                        self.assertGreater(changed, 500, "«Cambiar fondo» did not change the visible artwork")
                        geometry_after = xdo("getwindowgeometry", "--shell", window)
                        self.assertEqual(geometry_after.stdout, geometry.stdout, "Desktop geometry changed")
                        panels_after = panel_foreground()
                        self.assertEqual(len(panels_before), len(panels_after))
                        foreground = [i for i in range(0, len(panels_before), 3)
                                      if min(panels_before[i:i + 3]) > 245]
                        self.assertGreater(len(foreground), 20, "Bar/dock foreground did not render")
                        changed_foreground = sum(
                            max(abs(panels_before[i + c] - panels_after[i + c]) for c in range(3)) > 12
                            for i in foreground
                        )
                        self.assertLess(changed_foreground, len(foreground) * 0.05,
                                        "Changing the artwork altered bar/dock foreground")
                        return
                    self.assertLess(
                        changed_pixels(before, background_region()), 500,
                        "Escape did not dismiss the context menu and restore the background",
                    )
                finally:
                    for process in reversed(processes):
                        for stop_signal in (signal.SIGTERM, signal.SIGKILL):
                            try:
                                os.killpg(process.pid, stop_signal)
                            except ProcessLookupError:
                                pass
                            try:
                                process.wait(timeout=2)
                                break
                            except subprocess.TimeoutExpired:
                                pass


if __name__ == "__main__":
    loader = unittest.TestLoader()
    loader.testMethodPrefix = "given"
    unittest.main(testLoader=loader)
