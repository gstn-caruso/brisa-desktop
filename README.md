# Brisa · laboratorio de escritorio

**Brisa es un nombre provisional. Este incremento ofrece dos paneles Vala/GTK4
sobre labwc con gtk4-layer-shell, no un entorno de escritorio completo ni una
sesión instalable.** Usa un compositor existente y puede ejecutarse anidado en
GNOME Wayland sin reemplazarlo.

## Qué hay ahora

- Dos superficies Wayland independientes en la capa `TOP`: `brisa-bar`, anclada
  arriba y a ambos lados, y `brisa-dock`, centrada abajo. Ambas reservan espacio
  mediante una zona exclusiva automática y no solicitan foco de teclado.
- Barra con marca `🐧 Linux` y reloj local. El pingüino es texto Unicode
  (U+1F427), dependiente de la fuente del sistema, no un asset oficial de Tux
  ni un menú.
- Dock con **etiquetas de demostración sin acciones**: Archivos, Navegador y
  Papelera. No hay lanzadores, aplicaciones fijadas, recientes, papelera
  operativa ni reubicación; tampoco botones que prometan esas funciones.
- Si el compositor no ofrece layer-shell, se conserva el prototipo anterior:
  una sola ventana GTK con fondo, barra y dock visuales. Es el fallback que
  comprueba Weston, no una integración de shell equivalente.
- Lanzadores separados para labwc anidado y una VM live QEMU/KVM.

Labwc es responsable de la composición y de la gestión de ventanas. Brisa aporta
estos dos paneles; no implementa un compositor ni dibuja ahora un fondo propio
cuando usa layer-shell. `--full-screen` solo afecta al fallback de una ventana y
no se usa en el lanzador anidado.

## Requisitos locales

Meson >= 1.0, Ninja, compilador C, Vala, desarrollo GTK4 >= 4.12 y
`gtk4-layer-shell-0` >= 1.0 (paquete de desarrollo `libgtk4-layer-shell-dev`).
Para probar: Python 3 (solo biblioteca estándar), labwc con backend headless y
Pixman, Weston con backend headless y `weston-simple-shm`.
Para iterar anidado: sesión Wayland, labwc con backend wayland, Bash y `setsid`.
Para VM: QEMU x86_64 con interfaz GTK, acceso de lectura/escritura a `/dev/kvm`
y una ISO live local. ShellCheck es opcional para validar el lanzador.

Entorno local: GTK 4.22.4, Vala 0.56.18, Meson 1.10.1, labwc 0.9.3,
gtk4-layer-shell 1.3.0, Weston 14.0.2 y QEMU 10.2.1. Los scripts no descargan
ni instalan dependencias.

## Compilar y probar

Desde la raíz del repositorio:

```sh
meson setup build
meson compile -C build
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_headless_labwc.py -v
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_headless_weston.py -v
```

`meson setup build` es para la primera configuración; después basta con compilar.
El ejecutable es `build/brisa-desktop`. Los dos archivos son la batería actual:

- Labwc headless: comprueba los namespaces, los anclajes, zonas exclusivas
  positivas, recepción y confirmación de `configure` antes de mapear buffers
  reales en ambas superficies. GTK imprime `BRISA_SMOKE_TEST_BAR_MAPPED` y
  `BRISA_SMOKE_TEST_DOCK_MAPPED` desde sus señales `map`. En `--smoke-test`,
  Brisa sale 300 ms después de que ambas se hayan mapeado y labwc también termina.
- Weston headless: primero comprueba un frame real con `weston-simple-shm`;
  después verifica el fallback, su señal `map`, el marcador
  `BRISA_SMOKE_TEST_WINDOW_MAPPED` y la salida automática de cliente y compositor.

Ambos tests utilizan sockets y runtimes privados, sin pantalla física ni acceso
al bus de sesión anfitrión. Verifican integración y mapeo, **no apariencia visual
ni funcionalidades de aplicaciones o archivos**.

La compilación local produce una advertencia de obsolescencia de
`Gtk.StyleContext` y avisos del C generado por Vala; no se suprimen para aparentar
una compilación sin advertencias.

## Iterar dentro de GNOME Wayland

```sh
bash scripts/dev.sh

# Comprobación breve, con salida automática:
bash scripts/dev.sh --smoke-test

# Validación del lanzador:
bash -n scripts/dev.sh
shellcheck scripts/dev.sh
```

El lanzador resuelve `WAYLAND_DISPLAY` (por defecto `wayland-0`) contra el
`XDG_RUNTIME_DIR` anfitrión, salvo que ya sea una ruta absoluta. Pasa esa ruta
absoluta al backend Wayland de labwc para que pueda conectarse al anfitrión aun
con un runtime temporal privado de permisos 700. Labwc define después el
`WAYLAND_DISPLAY` privado que hereda Brisa al arrancar mediante `-S`.

Se usa `WLR_BACKENDS=wayland`, `WLR_RENDERER=pixman` y `GSK_RENDERER=cairo`,
sin depender de aceleración GL. Labwc recibe `-C` con una configuración mínima
privada, sin Xwayland, autostart ni shutdown personalizados. Los directorios XDG
de configuración también son privados: no se hereda la configuración de labwc
del usuario ni del sistema. No se pasa `--full-screen`: barra y dock son paneles
independientes dentro de la ventana exterior de labwc.

Para salir, cerrá la ventana exterior de labwc en GNOME o usá **Ctrl+C** en la
terminal. Al terminar el cliente de sesión, labwc también termina. La limpieza
se limita al grupo de procesos propio y al runtime temporal creado por el
lanzador; no cambia la configuración de GNOME ni archivos globales.

`LABWC_UPDATE_ACTIVATION_ENV=0` impide que labwc actualice el entorno de activación
de D-Bus/systemd. El bus D-Bus apunta a una dirección privada sin servicio:
este prototipo no necesita activar portales ni servicios anfitriones. Tampoco
hereda `WAYLAND_SOCKET`, `DISPLAY` ni las variables `DBUS_STARTER_*`.

El smoke anidado se verificó con ambos marcadores y terminación automática.
Se revisó una captura visual de la ejecución anidada. Al enviar SIGINT al lanzador,
salió con código 130, se retiró su runtime privado y se conservó el socket de GNOME.
**El cierre mediante el botón de la ventana exterior sigue pendiente de validación.**
El aislamiento es de compositor, socket, configuración y acceso al bus de sesión,
**no un sandbox de seguridad**: el proceso mantiene los permisos del usuario.

## VM live para validar infraestructura

```sh
# ISO local por defecto:
bash scripts/vm.sh

# Otra ISO explícita:
bash scripts/vm.sh /ruta/a/imagen-live.iso

# O mediante variable de entorno:
BRISA_VM_ISO=/ruta/a/imagen-live.iso bash scripts/vm.sh
```

Por defecto se usa `/home/gaston/Downloads/ubuntu-26.04.1-desktop-amd64.iso`.
La VM tiene KVM, 2 CPU, 4 GiB de RAM, vídeo VirtIO e interfaz GTK. Arranca desde
el CD-ROM con la ISO; no recibe discos duros, red, carpetas compartidas ni
passthrough de dispositivos anfitriones. No crea una imagen persistente de disco.
Cerrá la ventana de QEMU para terminar la instancia; no configura una VM global.
No hay fallback silencioso a emulación si KVM no está disponible.

**Esta VM solo permite validar el arranque de la infraestructura live. No contiene
Brisa.** El binario compilado en el anfitrión no se supone portable al invitado:
falta preparar allí las dependencias, las fuentes y la compilación, o producir una
imagen aprovisionada en un incremento posterior. El arranque completo de la ISO y
la revisión visual de la VM quedan pendientes de validación; disponer de la ISO y
KVM no demuestra que haya arrancado.

## Próximos incrementos y límites

- Dock reubicable y aplicaciones fijadas reales.
- Aplicaciones recientes y papelera operativa.
- Integración de sesión propia y ciclo de sesión.
- Aprovisionamiento del prototipo en el invitado y validación visual.

No hay lanzadores de aplicaciones, persistencia de preferencias ni manipulación
de archivos en este incremento. No se instala nada en el anfitrión ni se
habilita Brisa como sesión de inicio de sesión.

## Licencia

Las fuentes de este proyecto se distribuyen bajo la GNU General Public License,
versión 3 o cualquier versión posterior, a tu elección
(`SPDX-License-Identifier: GPL-3.0-or-later`). El texto completo de GPLv3 está en
[LICENSE](LICENSE).

Las dependencias conservan sus respectivas licencias.
