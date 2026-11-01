#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
smoke_test=false
dock_position=bottom
while (( $# )); do
    case "$1" in
        --smoke-test) smoke_test=true ;;
        --dock-position=*) dock_position=${1#*=} ;;
        --dock-position)
            if (( $# < 2 )); then
                printf 'Falta --dock-position: bottom, left, right.\n' >&2
                exit 1
            fi
            shift
            dock_position=$1
            ;;
        *)
            printf 'Opción de sesión desconocida: %s. Opciones: --smoke-test, --dock-position bottom|left|right.\n' "$1" >&2
            exit 1
            ;;
    esac
    shift
done
case "$dock_position" in
    bottom|left|right) ;;
    *)
        printf 'Invalid --dock-position %s; valid positions: bottom, left, right\n' "$dock_position" >&2
        exit 1
        ;;
esac
for binary in brisa-desktop brisa-dock; do
    if [[ ! -x "$root/build/$binary" ]]; then
        printf 'Falta build/%s. Ejecutá meson compile -C build.\n' "$binary" >&2
        exit 1
    fi
done

# Sólo estos dos hijos pertenecen a la sesión; nunca se señala al compositor.
desktop_pid=
dock_pid=
# Invocada indirectamente por el trap EXIT.
# shellcheck disable=SC2329
cleanup() {
    local pid
    for pid in $(jobs -pr); do
        if [[ "$pid" == "$desktop_pid" || "$pid" == "$dock_pid" ]]; then
            kill -TERM "$pid" 2>/dev/null || true
        fi
    done
    if [[ -n "$desktop_pid" ]]; then
        wait "$desktop_pid" 2>/dev/null || true
    fi
    if [[ -n "$dock_pid" ]]; then
        wait "$dock_pid" 2>/dev/null || true
    fi
}
trap 'cleanup' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

arguments=()
if "$smoke_test"; then
    arguments+=(--smoke-test)
fi
"$root/build/brisa-desktop" "${arguments[@]}" &
desktop_pid=$!
"$root/build/brisa-dock" "${arguments[@]}" "--dock-position=$dock_position" &
dock_pid=$!

# En uso normal sólo el escritorio gobierna la duración de la sesión.
status=0
wait "$desktop_pid" || status=$?
desktop_pid=
if "$smoke_test"; then
    dock_status=0
    wait "$dock_pid" || dock_status=$?
    dock_pid=
    if (( status == 0 )); then
        status=$dock_status
    fi
fi
exit "$status"
