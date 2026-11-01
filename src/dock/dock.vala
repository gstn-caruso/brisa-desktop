// SPDX-License-Identifier: GPL-3.0-or-later
class BrisaDock : Gtk.Box {
    private Gtk.Popover context_menu;
    private string dock_position;
    public int icon_size { get; private set; default = 42; }

    public BrisaDock (string position, Gtk.Widget icon_context) {
        Object (orientation: position == "bottom" ? Gtk.Orientation.HORIZONTAL
                                                 : Gtk.Orientation.VERTICAL, spacing: 0);
        halign = Gtk.Align.CENTER;
        add_css_class ("dock");
        load_styles (icon_context.get_display ());
        populate_icons (icon_context);
        dock_position = position;
        context_menu = new Gtk.Popover ();
        context_menu.set_parent (this);
        var menu_content = new Gtk.Box (Gtk.Orientation.VERTICAL, 8);
        var title = new Gtk.Label ("Posición del dock");
        title.add_css_class ("heading");
        menu_content.append (title);
        string[] labels = { "Abajo", "Izquierda", "Derecha" };
        string[] positions = { "bottom", "left", "right" };
        for (int i = 0; i < labels.length; i++) {
            var selected_position = positions[i];
            var choice = new Gtk.Button.with_label (labels[i]);
            choice.clicked.connect (() => {
                context_menu.popdown ();
                move_to (selected_position);
            });
            menu_content.append (choice);
        }
        context_menu.child = menu_content;
        context_menu.position = position == "left" ? Gtk.PositionType.RIGHT
                              : position == "right" ? Gtk.PositionType.LEFT : Gtk.PositionType.TOP;
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
            menu_content.get_first_child ().get_next_sibling ().grab_focus ();
        });
        add_controller (right_click);
    }

    private void load_styles (Gdk.Display display) {
        var css = new Gtk.CssProvider ();
        css.load_from_string ("""
            .dock {
                background: alpha(#d7edff, 0.26);
                border: 1px solid alpha(#ffffff, 0.48);
                border-radius: 19px;
                box-shadow: 0 6px 20px alpha(#031b4b, 0.25);
                padding: 7px;
                margin: 12px;
            }
            .dock-item { padding: 3px; }
            .dock separator { background: alpha(#ffffff, 0.3); margin: 5px; background-clip: content-box; }
            .dock separator.vertical { padding: 0 6px; }
            .dock separator.horizontal { padding: 6px 0; }
        """);
        Gtk.StyleContext.add_provider_for_display (
            display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
    }

    private void populate_icons (Gtk.Widget icon_context) {
        var display_theme = Gtk.IconTheme.get_for_display (icon_context.get_display ());
        // Resolve artwork, not executable availability; Yaru also supplies full-color
        // app icons in an isolated session whose default theme is only Adwaita.
        var preview_theme = new Gtk.IconTheme ();
        preview_theme.theme_name = "Yaru";
        string[] names = { "Archivos", "Navegador", "Editor de texto", "Terminal",
                           "Videos", "Calculadora", "Papelera" };
        string[] icons = { "org.gnome.Nautilus|system-file-manager|folder",
                           "firefox|web-browser|org.gnome.Epiphany",
                           "org.gnome.TextEditor|accessories-text-editor",
                           "org.gnome.Terminal|utilities-terminal",
                           "org.gnome.Totem|multimedia-video-player|multimedia-player",
                           "org.gnome.Calculator|accessories-calculator",
                           "user-trash" };
        for (int i = 0; i < names.length; i++) {
            foreach (string candidate in icons[i].split ("|")) {
                var icon_theme = preview_theme.has_icon (candidate) ? preview_theme : display_theme;
                if (!icon_theme.has_icon (candidate))
                    continue;
                if (i == names.length - 1)
                    append_resize_separator ();
                var artwork = icon_theme.lookup_icon (candidate, null, 42,
                    icon_context.get_scale_factor (), Gtk.TextDirection.NONE, Gtk.IconLookupFlags.FORCE_REGULAR);
                var item = new Gtk.Image.from_paintable (artwork);
                item.pixel_size = 42;
                item.tooltip_text = names[i];
                item.add_css_class ("dock-item");
                append (item);
                notify["icon-size"].connect (() => {
                    item.pixel_size = icon_size;
                    item.paintable = icon_theme.lookup_icon (candidate, null, icon_size,
                        icon_context.get_scale_factor (), Gtk.TextDirection.NONE, Gtk.IconLookupFlags.FORCE_REGULAR);
                });
                break;
            }
        }
    }

    public void append_resize_separator () {
        var separator = new Gtk.Separator (orientation == Gtk.Orientation.HORIZONTAL
                                           ? Gtk.Orientation.VERTICAL : Gtk.Orientation.HORIZONTAL);
        separator.set_cursor_from_name (orientation == Gtk.Orientation.HORIZONTAL ? "ns-resize" : "ew-resize");
        var drag = new Gtk.GestureDrag ();
        drag.button = 1;
        int initial_size = icon_size;
        drag.drag_begin.connect (() => {
            initial_size = icon_size;
            drag.set_state (Gtk.EventSequenceState.CLAIMED);
        });
        drag.drag_update.connect ((x, y) => {
            double delta = dock_position == "bottom" ? -y : dock_position == "left" ? x : -x;
            icon_size = (initial_size + (int) delta).clamp (24, 80);
        });
        separator.add_controller (drag);
        append (separator);
    }

    private void move_to (string position) {
        dock_position = position;
        orientation = position == "bottom" ? Gtk.Orientation.HORIZONTAL : Gtk.Orientation.VERTICAL;
        for (var child = get_first_child (); child != null; child = child.get_next_sibling ()) {
            if (child is Gtk.Separator) {
                ((Gtk.Separator) child).orientation = orientation == Gtk.Orientation.HORIZONTAL
                                                     ? Gtk.Orientation.VERTICAL : Gtk.Orientation.HORIZONTAL;
                child.set_cursor_from_name (orientation == Gtk.Orientation.HORIZONTAL ? "ns-resize" : "ew-resize");
            }
        }
        context_menu.position = position == "left" ? Gtk.PositionType.RIGHT
                              : position == "right" ? Gtk.PositionType.LEFT : Gtk.PositionType.TOP;
        var window = get_root () as Gtk.Window;
        if (window != null && GtkLayerShell.is_layer_window (window)) {
            var anchor = position == "left" ? GtkLayerShell.Edge.LEFT
                       : position == "right" ? GtkLayerShell.Edge.RIGHT : GtkLayerShell.Edge.BOTTOM;
            foreach (var edge in new GtkLayerShell.Edge[] { GtkLayerShell.Edge.TOP,
                     GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT })
                GtkLayerShell.set_anchor (window, edge, edge == anchor);
            GtkLayerShell.auto_exclusive_zone_enable (window);
        } else {
            halign = position == "left" ? Gtk.Align.START
                   : position == "right" ? Gtk.Align.END : Gtk.Align.CENTER;
            valign = position == "bottom" ? Gtk.Align.END : Gtk.Align.CENTER;
        }
    }

    public override void dispose () {
        if (context_menu != null) {
            context_menu.unparent ();
            context_menu = null;
        }
        base.dispose ();
    }
}
