// SPDX-License-Identifier: GPL-3.0-or-later
class Brisa : Gtk.Application {
    private bool smoke_test;
    private bool full_screen;
    private string dock_position = "bottom";
    private uint mapped_surfaces;

    public Brisa () {
        Object (application_id: "org.brisa.Prototype",
                flags: ApplicationFlags.NON_UNIQUE);
        add_main_option ("smoke-test", 0, OptionFlags.NONE, OptionArg.NONE,
                         "Mapear las superficies y salir automáticamente", null);
        add_main_option ("full-screen", 0, OptionFlags.NONE, OptionArg.NONE,
                         "Ocupar la salida del compositor de laboratorio", null);
        add_main_option ("dock-position", 0, OptionFlags.NONE, OptionArg.STRING,
                         "Posición del dock en la vista previa conjunta", "bottom|left|right");
        set_option_context_description (
            "Con layer-shell, el escritorio muestra sólo fondo y barra; el dock se ejecuta con brisa-dock.\n"
            + "Sin layer-shell (X11/Weston), muestra una vista previa conjunta con el dock integrado.");
        handle_local_options.connect ((options) => {
            smoke_test = options.contains ("smoke-test");
            full_screen = options.contains ("full-screen");
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

        bool layer_shell = GtkLayerShell.is_supported ();
        var window = new Gtk.ApplicationWindow (this);
        window.title = "Brisa";
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
            window.desktop, window.panel { background: transparent; color: #ffffff; }
            .top-bar {
                background: alpha(#0e325c, 0.28);
                border-bottom: 1px solid alpha(#ffffff, 0.12);
                padding: 4px 18px;
                font-size: 12px;
            }
            .brand { font-weight: 600; letter-spacing: 0.5px; }
        """);
        Gtk.StyleContext.add_provider_for_display (
            window.get_display (), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);

        var desktop = new Gtk.Overlay ();
        desktop.child = new BrisaBackground ();
        var top_bar = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 24);
        top_bar.add_css_class ("top-bar");
        var brand = new Gtk.Label ("Brisa");
        brand.add_css_class ("brand");
        top_bar.append (brand);
        var space = new Gtk.Box (Gtk.Orientation.HORIZONTAL, 0);
        space.hexpand = true;
        top_bar.append (space);
        var clock = new Gtk.Label (new DateTime.now_local ().format ("%a %e %b   %H:%M"));
        top_bar.append (clock);
        uint clock_timer = Timeout.add_seconds (1, () => {
            clock.label = new DateTime.now_local ().format ("%a %e %b   %H:%M");
            return Source.CONTINUE;
        });
        shutdown.connect (() => Source.remove (clock_timer));
        if (!layer_shell) {
            top_bar.valign = Gtk.Align.START;
            desktop.add_overlay (top_bar);
        }

        if (layer_shell) {
            var background = new Gtk.ApplicationWindow (this);
            background.title = "Brisa · fondo";
            background.add_css_class ("panel");
            GtkLayerShell.init_for_window (background);
            GtkLayerShell.set_namespace (background, "brisa-background");
            GtkLayerShell.set_layer (background, GtkLayerShell.Layer.BACKGROUND);
            foreach (var edge in new GtkLayerShell.Edge[] { GtkLayerShell.Edge.TOP,
                     GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT })
                GtkLayerShell.set_anchor (background, edge, true);
            // Cover the whole output, including the areas behind the translucent panels.
            GtkLayerShell.set_exclusive_zone (background, -1);
            GtkLayerShell.set_keyboard_mode (background, GtkLayerShell.KeyboardMode.NONE);
            background.child = new BrisaBackground ();
            window.child = top_bar;
            if (smoke_test) {
                background.map.connect (() => smoke_layer_mapped ("BACKGROUND"));
                window.map.connect (() => smoke_layer_mapped ("BAR"));
            }
            background.present ();
            window.present ();
            return;
        }

        var dock = new BrisaDock (dock_position, window);
        dock.valign = dock_position == "left" || dock_position == "right"
                      ? Gtk.Align.CENTER : Gtk.Align.END;
        dock.halign = dock_position == "left" ? Gtk.Align.START : dock_position == "right"
                      ? Gtk.Align.END : Gtk.Align.CENTER;
        desktop.add_overlay (dock);
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

// Original Brisa artwork, GPL-3.0-or-later. Vector curves stay crisp at any output size.
class BrisaBackground : Gtk.Box {
    private Gtk.Popover context_menu;
    private Gtk.DrawingArea artwork;
    private bool alternate_palette;

    public BrisaBackground () {
        can_target = true;
        hexpand = true;
        vexpand = true;
        context_menu = new Gtk.Popover ();
        context_menu.set_parent (this);
        var menu_content = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
        menu_content.append (new Gtk.Label ("Apariencia"));
        var change_background = new Gtk.Button.with_label ("Cambiar fondo");
        change_background.clicked.connect (() => {
            alternate_palette = !alternate_palette;
            artwork.queue_draw ();
            context_menu.popdown ();
        });
        menu_content.append (change_background);
        var close_menu = new Gtk.Button.with_label ("Cerrar");
        close_menu.clicked.connect (() => context_menu.popdown ());
        menu_content.append (close_menu);
        context_menu.child = menu_content;
        context_menu.closed.connect (() => {
            var window = get_root () as Gtk.Window;
            if (window != null && GtkLayerShell.is_layer_window (window))
                GtkLayerShell.set_keyboard_mode (window, GtkLayerShell.KeyboardMode.NONE);
        });
        var right_click = new Gtk.GestureClick ();
        right_click.button = 3;
        right_click.pressed.connect ((presses, x, y) => {
            var window = get_root () as Gtk.Window;
            if (window != null && GtkLayerShell.is_layer_window (window))
                GtkLayerShell.set_keyboard_mode (window, GtkLayerShell.KeyboardMode.ON_DEMAND);
            context_menu.set_pointing_to ({ (int) x, (int) y, 1, 1 });
            context_menu.popup ();
            close_menu.grab_focus ();
        });
        add_controller (right_click);
        artwork = new Gtk.DrawingArea ();
        artwork.can_target = false;
        artwork.hexpand = true;
        artwork.vexpand = true;
        append (artwork);
        artwork.set_draw_func ((area, cr, width, height) => {
            cr.scale (width / 1600.0, height / 1000.0);
            var sky = new Cairo.Pattern.linear (0, 0, 1300, 1000);
            sky.add_color_stop_rgb (0, 0.39, 0.63, 0.79);
            sky.add_color_stop_rgb (0.44, 0.73, 0.85, 0.87);
            sky.add_color_stop_rgb (1, 0.16, 0.43, 0.69);
            cr.set_source (sky);
            cr.paint ();

            var glow = new Cairo.Pattern.radial (230, 330, 0, 230, 330, 1050);
            glow.add_color_stop_rgba (0, 0.94, 0.93, 0.79, 0.65);
            glow.add_color_stop_rgba (1, 0.66, 0.83, 0.92, 0);
            cr.set_source (glow);
            cr.paint ();

            cr.move_to (-100, 740);
            cr.curve_to (340, 860, 530, 330, 1110, 120);
            cr.curve_to (1350, 30, 1500, 10, 1700, -60);
            cr.line_to (1700, 1100);
            cr.line_to (-100, 1100);
            cr.close_path ();
            var wave = new Cairo.Pattern.linear (430, 240, 1050, 1030);
            wave.add_color_stop_rgb (0, 0.28, 0.82, 0.91);
            wave.add_color_stop_rgb (0.23, 0.04, 0.56, 0.84);
            wave.add_color_stop_rgb (0.50, 0.02, 0.34, 0.76);
            wave.add_color_stop_rgb (0.82, 0.03, 0.17, 0.49);
            wave.add_color_stop_rgb (1, 0.02, 0.12, 0.35);
            cr.set_source (wave);
            cr.fill_preserve ();
            cr.save ();
            cr.clip ();
            var sheen = new Cairo.Pattern.radial (1080, 210, 10, 1080, 210, 850);
            sheen.add_color_stop_rgba (0, 0.40, 0.96, 1, 0.8);
            sheen.add_color_stop_rgba (0.32, 0.11, 0.73, 0.95, 0.45);
            sheen.add_color_stop_rgba (1, 0.04, 0.38, 0.85, 0);
            cr.set_source (sheen);
            cr.paint ();
            cr.restore ();

            // A fine light-catching crest, rather than a hard geometric edge.
            cr.move_to (-100, 740);
            cr.curve_to (340, 860, 530, 330, 1110, 120);
            cr.curve_to (1350, 30, 1500, 10, 1700, -60);
            var rim = new Cairo.Pattern.linear (0, 780, 1400, 0);
            rim.add_color_stop_rgba (0, 0.72, 0.94, 1, 0.9);
            rim.add_color_stop_rgba (0.55, 0.69, 0.93, 1, 0.6);
            rim.add_color_stop_rgba (1, 0.82, 0.98, 1, 0.1);
            cr.set_source (rim);
            cr.set_line_width (2);
            cr.stroke ();

            cr.move_to (-100, 920);
            cr.curve_to (470, 980, 690, 470, 1170, 370);
            cr.curve_to (1400, 320, 1500, 380, 1700, 260);
            cr.line_to (1700, 1100);
            cr.line_to (-100, 1100);
            cr.close_path ();
            var fold = new Cairo.Pattern.linear (620, 500, 1000, 1120);
            fold.add_color_stop_rgba (0, 0.17, 0.68, 0.94, 0);
            fold.add_color_stop_rgba (0.24, 0.13, 0.62, 0.93, 0.58);
            fold.add_color_stop_rgba (0.65, 0.02, 0.29, 0.75, 0.75);
            fold.add_color_stop_rgba (1, 0.02, 0.16, 0.48, 0.9);
            cr.set_source (fold);
            cr.fill ();

            cr.move_to (620, 1100);
            cr.curve_to (1030, 890, 1130, 650, 1330, 500);
            cr.curve_to (1460, 400, 1590, 400, 1700, 310);
            cr.line_to (1700, 1100);
            cr.close_path ();
            var silk = new Cairo.Pattern.linear (1020, 650, 1650, 1030);
            silk.add_color_stop_rgb (0, 0.20, 0.61, 0.79);
            silk.add_color_stop_rgb (0.22, 0.49, 0.78, 0.85);
            silk.add_color_stop_rgb (0.52, 0.31, 0.63, 0.77);
            silk.add_color_stop_rgb (1, 0.10, 0.35, 0.62);
            cr.set_source (silk);
            cr.fill_preserve ();
            cr.save ();
            cr.clip ();
            var light = new Cairo.Pattern.radial (1320, 530, 0, 1320, 530, 600);
            light.add_color_stop_rgba (0, 0.73, 0.95, 0.96, 0.55);
            light.add_color_stop_rgba (1, 0.51, 0.82, 0.9, 0);
            cr.set_source (light);
            cr.paint ();
            cr.restore ();

            if (alternate_palette) {
                cr.set_operator (Cairo.Operator.HSL_COLOR);
                cr.set_source_rgb (0.62, 0.38, 0.76);
                cr.paint ();
            }
        });
    }

    public override void dispose () {
        if (context_menu != null) {
            context_menu.unparent ();
            context_menu = null;
        }
        base.dispose ();
    }
}

int main (string[] args) {
    return new Brisa ().run (args);
}
