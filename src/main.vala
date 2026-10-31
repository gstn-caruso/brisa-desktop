// SPDX-License-Identifier: GPL-3.0-or-later
class Brisa : Gtk.Application {
    private bool smoke_test;
    private bool full_screen;
    private uint mapped_surfaces;

    public Brisa () {
        Object (application_id: "org.brisa.Prototype",
                flags: ApplicationFlags.NON_UNIQUE);
        add_main_option ("smoke-test", 0, OptionFlags.NONE, OptionArg.NONE,
                         "Mapear las superficies y salir automáticamente", null);
        add_main_option ("full-screen", 0, OptionFlags.NONE, OptionArg.NONE,
                         "Ocupar la salida del compositor de laboratorio", null);
        handle_local_options.connect ((options) => {
            smoke_test = options.contains ("smoke-test");
            full_screen = options.contains ("full-screen");
            return -1;
        });
    }

    protected override void activate () {
        if (active_window != null) {
            active_window.present ();
            return;
        }

        bool layer_shell = GtkLayerShell.is_supported ();
        var window = new Gtk.ApplicationWindow (this);
        window.title = "Brisa · laboratorio";
        if (layer_shell) {
            GtkLayerShell.init_for_window (window);
            GtkLayerShell.set_namespace (window, "brisa-bar");
            GtkLayerShell.set_layer (window, GtkLayerShell.Layer.TOP);
            GtkLayerShell.set_anchor (window, GtkLayerShell.Edge.TOP, true);
            GtkLayerShell.set_anchor (window, GtkLayerShell.Edge.LEFT, true);
            GtkLayerShell.set_anchor (window, GtkLayerShell.Edge.RIGHT, true);
            GtkLayerShell.auto_exclusive_zone_enable (window);
            GtkLayerShell.set_keyboard_mode (window, GtkLayerShell.KeyboardMode.NONE);
            window.add_css_class ("panel");
        } else {
            window.set_default_size (1000, 680);
            window.add_css_class ("desktop");
        }

        var css = new Gtk.CssProvider ();
        css.load_from_string ("""
            window.desktop {
                background: linear-gradient(135deg, #183b50, #426b75 55%, #b7c7bc);
                color: #ffffff;
            }
            window.panel { background: transparent; color: #ffffff; }
            .top-bar { background: alpha(#142d3a, 0.9); padding: 10px 20px; }
            .brand { font-weight: bold; }
            .desktop-title { font-size: 42px; font-weight: 300; }
            .subtitle { color: #e1ebec; }
            .dock {
                background: alpha(#122c38, 0.88);
                border: 1px solid alpha(#ffffff, 0.3);
                border-radius: 22px;
                padding: 16px 24px;
                margin: 20px;
            }
            .dock-item { padding: 0 14px; }
            .demo-note { font-size: 12px; color: #e1ebec; }
        """);
        Gtk.StyleContext.add_provider_for_display (
            window.get_display (), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);

        var desktop = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
        var top_bar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 24);
        top_bar.add_css_class ("top-bar");
        var brand = new Gtk.Label ("🐧 Linux");
        brand.add_css_class ("brand");
        top_bar.append (brand);
        var status = new Gtk.Label ("Brisa · prototipo");
        status.hexpand = true;
        status.halign = Gtk.Align.START;
        top_bar.append (status);
        var clock = new Gtk.Label (new DateTime.now_local ().format ("%H:%M"));
        top_bar.append (clock);
        uint clock_timer = Timeout.add_seconds (1, () => {
            clock.label = new DateTime.now_local ().format ("%H:%M");
            return Source.CONTINUE;
        });
        shutdown.connect (() => Source.remove (clock_timer));
        if (!layer_shell)
            desktop.append (top_bar);

        var center = new Gtk.Box (Gtk.Orientation.VERTICAL, 12);
        center.vexpand = true;
        center.valign = Gtk.Align.CENTER;
        var title = new Gtk.Label ("Un escritorio más simple");
        title.add_css_class ("desktop-title");
        center.append (title);
        var subtitle = new Gtk.Label ("Brisa · nombre provisional · laboratorio GTK4");
        subtitle.add_css_class ("subtitle");
        center.append (subtitle);
        desktop.append (center);

        var demo_note = new Gtk.Label ("Dock de demostración · sin acciones todavía");
        demo_note.add_css_class ("demo-note");
        var dock = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
        dock.halign = Gtk.Align.CENTER;
        dock.add_css_class ("dock");
        foreach (string name in new string[] { "Archivos", "Navegador", "Papelera" }) {
            var item = new Gtk.Label (name);
            item.add_css_class ("dock-item");
            dock.append (item);
        }
        if (layer_shell) {
            window.child = top_bar;
            var dock_window = new Gtk.ApplicationWindow (this);
            dock_window.title = "Brisa · dock";
            dock_window.add_css_class ("panel");
            GtkLayerShell.init_for_window (dock_window);
            GtkLayerShell.set_namespace (dock_window, "brisa-dock");
            GtkLayerShell.set_layer (dock_window, GtkLayerShell.Layer.TOP);
            GtkLayerShell.set_anchor (dock_window, GtkLayerShell.Edge.BOTTOM, true);
            GtkLayerShell.auto_exclusive_zone_enable (dock_window);
            GtkLayerShell.set_keyboard_mode (dock_window, GtkLayerShell.KeyboardMode.NONE);
            var dock_content = new Gtk.Box (Gtk.Orientation.VERTICAL, 0);
            dock_content.append (demo_note);
            dock_content.append (dock);
            dock_window.child = dock_content;
            if (smoke_test) {
                window.map.connect (() => smoke_layer_mapped ("BAR"));
                dock_window.map.connect (() => smoke_layer_mapped ("DOCK"));
            }
            window.present ();
            dock_window.present ();
            return;
        }

        desktop.append (demo_note);
        desktop.append (dock);
        window.child = desktop;

        if (smoke_test) {
            window.map.connect (() => {
                stdout.printf ("BRISA_SMOKE_TEST_WINDOW_MAPPED\n");
                stdout.flush ();
                Timeout.add (300, () => {
                    window.close ();
                    return Source.REMOVE;
                });
            });
        }
        if (full_screen)
            window.fullscreen ();
        window.present ();
    }

    private void smoke_layer_mapped (string surface) {
        stdout.printf ("BRISA_SMOKE_TEST_%s_MAPPED\n", surface);
        stdout.flush ();
        mapped_surfaces++;
        if (mapped_surfaces == 2) {
            Timeout.add (300, () => {
                quit ();
                return Source.REMOVE;
            });
        }
    }
}

int main (string[] args) {
    return new Brisa ().run (args);
}
