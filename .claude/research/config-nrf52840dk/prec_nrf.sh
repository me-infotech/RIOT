#!/bin/bash
# usage: prec_nrf.sh <tree> -- the 25 precedence cases of the P4 log
# (2026-11-13-p4-config-layer.md, section 3) with nrf52840dk instead of
# native64/native; prints normalised results
T=$1
unset BOARD CFLAGS DEVELHELP QUIET WERROR USEMODULE USE_ZEP ZEP_PORT_BASE APPLICATION EXTERNAL_BOARD_DIRS RIOTBASE
HW=examples/basic/hello-world; GN=examples/networking/gnrc/networking
VARS="BOARD APPLICATION RIOTBASE DEVELHELP QUIET WERROR USEMODULE USE_ZEP ZEP_PORT_BASE EXTERNAL_BOARD_DIRS CFLAGS BINDIR"
tg() { for v in $VARS; do echo -n "info-debug-variable-$v "; done; }
c() {
  local label=$1 app=$2; shift 2; local envs=(); while [ "$1" != -- ]; do envs+=("$1"); shift; done; shift
  echo "### $label"
  env "${envs[@]}" make --no-print-directory -C "$T/$app" "$@" $(tg) 2>&1 | sed "s#$T#<TREE>#g"
}
B=nrf52840dk
c "HW default (no BOARD)" $HW --
c "HW env BOARD=$B" $HW BOARD=$B --
c "HW cmd BOARD=$B" $HW -- BOARD=$B
c "HW env DEVELHELP=0" $HW DEVELHELP=0 -- BOARD=$B
c "HW cmd DEVELHELP=0" $HW -- BOARD=$B DEVELHELP=0
c "HW env QUIET=0" $HW QUIET=0 -- BOARD=$B
c "HW cmd QUIET=0" $HW -- BOARD=$B QUIET=0
c "HW cmd APPLICATION=foo" $HW -- BOARD=$B APPLICATION=foo
c "HW env APPLICATION=foo" $HW APPLICATION=foo -- BOARD=$B
c "HW env RIOTBASE=tree" $HW RIOTBASE=$T -- BOARD=$B
c "HW env CFLAGS=-DFOO" $HW CFLAGS=-DFOO -- BOARD=$B
c "HW cmd CFLAGS=-DFOO" $HW -- BOARD=$B CFLAGS=-DFOO
c "HW env USEMODULE=ztimer" $HW USEMODULE=ztimer -- BOARD=$B
c "HW cmd USEMODULE+=ztimer" $HW -- BOARD=$B USEMODULE+=ztimer
c "GN env USEMODULE=ztimer" $GN USEMODULE=ztimer -- BOARD=$B
c "GN cmd USEMODULE+=ztimer" $GN -- BOARD=$B USEMODULE+=ztimer
c "GN cmd USEMODULE=shell" $GN -- BOARD=$B USEMODULE=shell
c "GN env USE_ZEP=1" $GN USE_ZEP=1 -- BOARD=$B
c "GN cmd USE_ZEP=1" $GN -- BOARD=$B USE_ZEP=1
c "GN env ZEP_PORT_BASE=20000" $GN ZEP_PORT_BASE=20000 -- BOARD=$B
c "GN cmd ZEP_PORT_BASE=20000" $GN -- BOARD=$B ZEP_PORT_BASE=20000
c "GN env DEVELHELP=0" $GN DEVELHELP=0 -- BOARD=$B
c "GN env EXTERNAL_BOARD_DIRS=/nonexistent" $GN EXTERNAL_BOARD_DIRS=/nonexistent -- BOARD=$B
c "GN cmd EXTERNAL_BOARD_DIRS=" $GN -- BOARD=$B EXTERNAL_BOARD_DIRS=
c "GN env BOARD=$B" $GN BOARD=$B --
