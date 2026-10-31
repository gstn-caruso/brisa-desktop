# Brisa · laboratorio de escritorio

**Brisa es un nombre provisional. Este incremento ofrece fondo, barra y dock
Vala/GTK4 sobre labwc con gtk4-layer-shell, no un entorno de escritorio completo ni una
sesión instalable.** Usa un compositor existente y puede ejecutarse anidado en
GNOME Wayland sin reemplazarlo.

## Qué hay ahora

- Tres superficies Wayland independientes: `brisa-background` en la capa
  `BACKGROUND`, anclada a los cuatro bordes con zona exclusiva `-1` (cubre también
  detrás de los paneles, sin reservar espacio); `brisa-bar` y `brisa-dock` en `TOP`.
  La barra se ancla arriba y a ambos lados; el dock, inicialmente centrado abajo,
  también puede ocupar el lateral izquierdo o derecho. Ambos paneles reservan
  espacio mediante una zona exclusiva automática.
- Fondo vectorial original de Brisa, azul con variante violeta. Clic derecho en
  el fondo abre el popup «Apariencia» junto al puntero: «Cambiar fondo» alterna
  la paleta y cierra el menú; «Cerrar» o Escape lo descartan. No es un selector
  de archivos de imagen. Las superficies no solicitan foco de teclado salvo
  temporalmente al abrir un menú (`ON_DEMAND`).
- Barra con marca `Brisa`, fecha y reloj local.
- Dock con iconos reales de temas disponibles (Yaru y el tema del sistema), sin
  exigir que estén instaladas las aplicaciones representadas: Archivos,
  Navegador, Editor de texto, Terminal, Videos, Calculadora y Papelera. Se omiten
  los iconos que no se puedan resolver. **No lanzan aplicaciones** ni representan
  aplicaciones fijadas o recientes reales; la papelera no es operativa.
- Clic derecho en el dock, incluidos sus iconos, abre «Posición del dock» con
  «Abajo», «Izquierda» y «Derecha» para reubicarlo durante la ejecución. También
  acepta `--dock-position bottom|left|right` al arrancar (por defecto `bottom`);
  un valor inválido se rechaza antes de mapear superficies e indica los válidos.
- El separador anterior a Papelera permite redimensionar el dock arrastrándolo:
  tamaño de iconos entre 24 y 80 píxeles, inicialmente 42. Con el dock abajo,
  arrastrar hacia arriba lo agranda conservando su anclaje inferior.
- Si el compositor no ofrece layer-shell, se usa un fallback de una sola
  ventana GTK con fondo, barra, dock y los mismos controles. Es el fallback que
  comprueba Weston, no una integración de shell equivalente.
- Lanzadores separados para labwc anidado y una VM live QEMU/KVM.

Labwc es responsable de la composición y de la gestión de ventanas. Brisa aporta
el fondo y estos dos paneles; no implementa un compositor. `--full-screen` solo
afecta al fallback de una ventana y no se usa en el lanzador anidado.

## Requisitos locales

Meson >= 1.0, Ninja, compilador C, Vala, desarrollo GTK4 >= 4.12 y
`gtk4-layer-shell-0` >= 1.0 (paquete de desarrollo `libgtk4-layer-shell-dev`).
Para probar: Python 3 (solo biblioteca estándar), labwc con backend headless y
Pixman, Weston con backend headless y `weston-simple-shm`.
La prueba de interacción del fallback X11 usa además `Xvfb`, `xdotool`, `xwd`,
`ffmpeg`, `tesseract` (OCR de etiquetas visibles) y `dbus-run-session`.
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
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_background_context_menu.py -v
```

`meson setup build` es para la primera configuración; después basta con compilar.
El ejecutable es `build/brisa-desktop`. Los tres archivos son la batería actual:

- Labwc headless (4 casos): comprueba namespaces, anclajes, zona `-1` del fondo
  y zonas positivas de los paneles, recepción y confirmación de `configure`
  antes de mapear buffers reales en las tres superficies. Cubre el dock inicial
  abajo, a izquierda y a derecha mediante CLI, y el rechazo de una posición
  inválida. GTK imprime `BRISA_SMOKE_TEST_BACKGROUND_MAPPED`,
  `BRISA_SMOKE_TEST_BAR_MAPPED` y `BRISA_SMOKE_TEST_DOCK_MAPPED` desde sus señales
  `map`. En `--smoke-test`, Brisa sale 300 ms después de que las tres se hayan
  mapeado y labwc también termina.
- Weston headless (1 caso): primero comprueba un frame real con
  `weston-simple-shm`; después verifica el fallback, su señal `map`, el marcador
  `BRISA_SMOKE_TEST_WINDOW_MAPPED` y la salida automática de cliente y compositor.
- Interacción X11 (4 casos): usa ratón real en Xvfb y capturas para comprobar
  apertura del menú del fondo junto al clic y cierre con Escape; cambio de fondo
  sin alterar geometría ni primer plano de los paneles; selección de «Izquierda»
  desde el menú del dock y su orientación vertical; crecimiento del dock y sus
  iconos arrastrando el separador hacia arriba, conservando el anclaje inferior.
  **Estas pruebas del fallback X11 no garantizan la entrada en Wayland.** No hay
  cobertura específica de reducción, límites del tamaño ni arrastre lateral.

Las pruebas utilizan sockets y runtimes privados, sin pantalla física ni acceso
al bus de sesión anfitrión. Las de Wayland verifican integración y mapeo; la de
X11 comprueba además cambios visibles e interacción, **no funcionalidades de
aplicaciones o archivos ni fidelidad visual completa**.

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
del usuario ni del sistema. No se pasa `--full-screen`: fondo, barra y dock son superficies
independientes dentro de la ventana exterior de labwc.

Para salir, cerrá la ventana exterior de labwc en GNOME o usá **Ctrl+C** en la
terminal. Al terminar el cliente de sesión, labwc también termina. La limpieza
se limita al grupo de procesos propio y al runtime temporal creado por el
lanzador; no cambia la configuración de GNOME ni archivos globales.

`LABWC_UPDATE_ACTIVATION_ENV=0` impide que labwc actualice el entorno de activación
de D-Bus/systemd. El bus D-Bus apunta a una dirección privada sin servicio:
este prototipo no necesita activar portales ni servicios anfitriones. Tampoco
hereda `WAYLAND_SOCKET`, `DISPLAY` ni las variables `DBUS_STARTER_*`.

En el incremento anterior se verificó el smoke anidado con los dos marcadores
de panel y terminación automática, y se revisó una captura visual. Esa evidencia
no valida las nuevas interacciones Wayland. Al enviar SIGINT al lanzador,
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

- Aplicaciones fijadas reales y lanzadores.
- Aplicaciones recientes y papelera operativa.
- Integración de sesión propia y ciclo de sesión.
- Aprovisionamiento del prototipo en el invitado y validación visual.

No hay lanzadores de aplicaciones, recientes reales, Finder ni manipulación
de archivos en este incremento. Los cambios de fondo, posición y tamaño del dock
solo viven durante la ejecución: no hay persistencia de preferencias. No se
instala nada en el anfitrión ni se habilita Brisa como sesión de inicio de sesión.

## Licencia

Las fuentes de este proyecto se distribuyen bajo la GNU General Public License,
versión 3 o cualquier versión posterior, a tu elección
(`SPDX-License-Identifier: GPL-3.0-or-later`). El texto completo de GPLv3 está en
[LICENSE](LICENSE).

Las dependencias conservan sus respectivas licencias.
