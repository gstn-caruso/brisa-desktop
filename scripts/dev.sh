#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
binary="$root/build/brisa-desktop"
if [[ ! -x "$binary" ]]; then
    printf 'Falta el prototipo. Ejecutá meson setup build y meson compile -C build.\n' >&2
    exit 1
fi
for tool in labwc setsid; do
    command -v "$tool" >/dev/null || { printf 'Falta %s.\n' "$tool" >&2; exit 1; }
done
: "${XDG_RUNTIME_DIR:?Se necesita una sesión Wayland con XDG_RUNTIME_DIR}"
parent_display=${WAYLAND_DISPLAY:-wayland-0}
if [[ "$parent_display" != /* ]]; then
    parent_display="$XDG_RUNTIME_DIR/$parent_display"
fi
if [[ ! -S "$parent_display" ]]; then
    printf 'No existe el socket Wayland anfitrión: %s\n' "$parent_display" >&2
    exit 1
fi

runtime=$(mktemp -d "$XDG_RUNTIME_DIR/brisa-dev.XXXXXX")
labwc_pid=
cleanup() {
    if [[ -n "$labwc_pid" ]]; then
        # El grupo es exclusivamente el compositor y sus clientes de laboratorio.
        kill -TERM -- "-$labwc_pid" 2>/dev/null || true
        wait "$labwc_pid" 2>/dev/null || true
    fi
    if [[ "$runtime" == "$XDG_RUNTIME_DIR"/brisa-dev.* && -d "$runtime" ]]; then
        rm -rf -- "$runtime"
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
config="$runtime/config/labwc"
mkdir -p -- "$config" "$runtime/config-dirs"
printf '%s\n' '<labwc_config><core><xwayland>no</xwayland></core></labwc_config>' > "$config/rc.xml"
for file in autostart shutdown environment; do
    : > "$config/$file"
done

# -S recibe un comando con comillas estilo shell, no instrucciones de Bash.
shell_quote() {
    printf "'%s'" "${1//\'/\'\\\'\'}"
}
session=$(shell_quote "$binary")
for argument in "$@"; do
    session+=" $(shell_quote "$argument")"
done

printf 'Brisa anidado en labwc: cerrá la ventana exterior o usá Ctrl+C para salir.\n'
setsid env -u WAYLAND_SOCKET -u DISPLAY \
    -u DBUS_STARTER_ADDRESS -u DBUS_STARTER_BUS_TYPE \
    XDG_RUNTIME_DIR="$runtime" WAYLAND_DISPLAY="$parent_display" \
    XDG_CONFIG_HOME="$runtime/config" XDG_CONFIG_DIRS="$runtime/config-dirs" \
    WLR_BACKENDS=wayland WLR_RENDERER=pixman WLR_WL_OUTPUTS=1 \
    LABWC_UPDATE_ACTIVATION_ENV=0 \
    GDK_BACKEND=wayland GSK_RENDERER=cairo GTK_A11Y=none \
    DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime/no-session-bus" \
    labwc -C "$config" -S "$session" &
labwc_pid=$!
wait "$labwc_pid"
