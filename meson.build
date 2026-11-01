# SPDX-License-Identifier: GPL-3.0-or-later
project('brisa-desktop', 'vala', 'c', meson_version: '>= 1.0.0',
  license: 'GPL-3.0-or-later')

executable('brisa-dock', 'src/dock/main.vala', 'src/dock/dock.vala',
  dependencies: [
    dependency('gtk4', version: '>= 4.12'),
    dependency('gtk4-layer-shell-0', version: '>= 1.0'),
  ],
  install: false,
)

executable('brisa-desktop', 'src/main.vala', 'src/dock/dock.vala',
  dependencies: [
    dependency('gtk4', version: '>= 4.12'),
    dependency('gtk4-layer-shell-0', version: '>= 1.0'),
  ],
  install: false,
)
