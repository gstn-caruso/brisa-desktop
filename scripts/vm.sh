#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == --help ]]; then
    printf 'Uso: bash scripts/vm.sh [ISO]\nISO: argumento, BRISA_VM_ISO o Ubuntu live local por defecto.\n'
    exit 0
fi
if (( $# > 1 )); then
    printf 'Uso: bash scripts/vm.sh [ISO]\n' >&2
    exit 2
fi
iso=${1:-${BRISA_VM_ISO:-/home/gaston/Downloads/ubuntu-26.04.1-desktop-amd64.iso}}
command -v qemu-system-x86_64 >/dev/null || { printf 'Falta qemu-system-x86_64.\n' >&2; exit 1; }
if [[ ! -r /dev/kvm || ! -w /dev/kvm ]]; then
    printf 'Se necesita acceso de lectura y escritura a /dev/kvm.\n' >&2
    exit 1
fi
if [[ ! -f "$iso" || ! -r "$iso" ]]; then
    printf 'ISO no legible: %s\n' "$iso" >&2
    exit 1
fi
printf 'VM live: 2 CPU, 4 GiB, sin disco ni red. Cerrá la ventana para salir.\n'
printf 'Valida el arranque de la infraestructura; Brisa aún no está en el invitado.\n'
exec qemu-system-x86_64 \
    -name brisa-live-lab \
    -enable-kvm -cpu host -smp 2 -m 4096 \
    -boot order=d -cdrom "$iso" \
    -nic none -snapshot -no-reboot \
    -vga virtio -display gtk,gl=off \
    -monitor none -serial none
