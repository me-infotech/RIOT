#!/bin/bash
# Typical configuration mistakes: Make variables (ref) vs riot-app.yaml (cur).
# Make side: edited app Makefile, `make info-debug-variable-*` with nrf52840dk.
# YAML side: edited riot-app.yaml, generator riot_app_config.py.
C=$1; HWR=$C/ref/examples/basic/hello-world; HWC=$C/cur/examples/basic/hello-world
GEN=$C/cur/dist/tools/riot_app_config/riot_app_config.py
mk() { # label sed-expr variable
  cp $HWR/Makefile $C/Makefile.bak; sed -i "$2" $HWR/Makefile
  out=$(cd $HWR && env -u BOARD make --no-print-directory BOARD=nrf52840dk info-debug-variable-$3 2>&1); rc=$?
  cp $C/Makefile.bak $HWR/Makefile
  printf 'MAKE | %-28s | exit %s | %s=%s\n' "$1" "$rc" "$3" "$(echo "$out" | tail -1 | cut -c1-90)"
}
ym() { # label sed-expr
  cp $HWC/riot-app.yaml $C/yaml.bak; sed -i "$2" $HWC/riot-app.yaml
  out=$(cd $C/cur && python3 $GEN examples/basic/hello-world/riot-app.yaml 2>&1); rc=$?
  cp $C/yaml.bak $HWC/riot-app.yaml; git -C $C/cur checkout -q -- examples/basic/hello-world/riot-app.inc.mk
  printf 'YAML | %-28s | exit %s | %s\n' "$1" "$rc" "$(echo "$out" | head -2 | tr '\n' ' ' | cut -c1-150)"
}
mk "typo in name (DEVELHLEP)" 's/^DEVELHELP ?= 1/DEVELHLEP ?= 1/' DEVELHELP
ym "typo in name (develhlep)" 's/^develhelp: 1/develhlep: 1/'
mk "wrong type (DEVELHELP=yes)" 's/^DEVELHELP ?= 1/DEVELHELP ?= yes/' DEVELHELP
ym "wrong type (develhelp: yes)" 's/^develhelp: 1/develhelp: yes/'
mk "octal-like (QUIET=01)" 's/^QUIET ?= 1/QUIET ?= 01/' QUIET
ym "octal-like (quiet: 01)" 's/^quiet: 1/quiet: 01/'
mk "missing RIOTBASE" '/^RIOTBASE ?=/d' RIOTBASE
ym "missing riotbase" '/^riotbase:/d'
mk "unknown board (nrf52840dkx)" 's/^BOARD ?= native/BOARD ?= nrf52840dkx/' BOARD
ym "unknown board (nrf52840dkx)" 's/^board: native/board: nrf52840dkx/'
mk "duplicate setting" 's/^QUIET ?= 1/QUIET ?= 1\nQUIET ?= 0/' QUIET
ym "duplicate key" 's/^quiet: 1/quiet: 1\nquiet: 0/'
