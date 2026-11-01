// SPDX-License-Identifier: GPL-3.0-or-later
class BrisaDockApplication : Gtk.Application {
    private bool smoke_test;
    private string dock_position = "bottom";

    public BrisaDockApplication () {
        Object (application_id: "org.brisa.Dock",
                flags: ApplicationFlags.NON_UNIQUE);
        add_main_option ("smoke-test", 0, OptionFlags.NONE, OptionArg.NONE,
                         "Mapear el dock y salir automáticamente", null);
        add_main_option ("dock-position", 0, OptionFlags.NONE, OptionArg.STRING,
                         "Posición del dock", "bottom|left|right");
        handle_local_options.connect ((options) => {
            smoke_test = options.contains ("smoke-test");
            var position = options.lookup_value ("dock-position", VariantType.STRING);
            if (position != null)
                dock_position = position.get_string ();
            if (dock_position != "bottom" && dock_position != "left" && dock_position != "right") {
                stderr.printf ("Invalid --dock-position '%s'; valid positions: bottom, left, right\n",
                               dock_position);
                return 1;
            }
            return -1;
        });
    }

    protected override void activate () {
        if (active_window != null) {
            active_window.present ();
            return;
        }

        var window = new Gtk.ApplicationWindow (this);
        window.title = "Brisa · dock";
        window.add_css_class ("dock-window");
        if (GtkLayerShell.is_supported ()) {
            GtkLayerShell.init_for_window (window);
            GtkLayerShell.set_namespace (window, "brisa-dock");
            GtkLayerShell.set_layer (window, GtkLayerShell.Layer.TOP);
            GtkLayerShell.set_anchor (window, dock_position == "left"
                                     ? GtkLayerShell.Edge.LEFT : dock_position == "right"
                                     ? GtkLayerShell.Edge.RIGHT : GtkLayerShell.Edge.BOTTOM, true);
            GtkLayerShell.auto_exclusive_zone_enable (window);
            GtkLayerShell.set_keyboard_mode (window, GtkLayerShell.KeyboardMode.NONE);
        }

        var css = new Gtk.CssProvider ();
        css.load_from_string ("window.dock-window { background: transparent; color: #ffffff; }");
        Gtk.StyleContext.add_provider_for_display (
            window.get_display (), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
        window.child = new BrisaDock (dock_position, window);
        if (smoke_test) {
            window.map.connect (() => {
                stdout.printf ("BRISA_SMOKE_TEST_DOCK_MAPPED\n");
                stdout.flush ();
                Timeout.add (300, () => {
                    window.close ();
                    return Source.REMOVE;
                });
            });
        }
        window.present ();
    }
}

int main (string[] args) {
    return new BrisaDockApplication ().run (args);
}
