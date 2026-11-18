#!/usr/bin/env bash
# 用 arduino-cli 編譯所有範例與所有接法。
# 用法：compile_all.sh <arduino-cli.exe> <arduino-cli.yaml> <log 目錄> [只跑名稱符合此 regex 的組合]
set -u
CLI="$1"; CFG="$2"; OUT="$3"; ONLY="${4:-.}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$HERE/libraries/EvacOled"
FQBN="ideasHatch:AmebaPro2:Ameba_HUB-8735_ultra"
# 覆寫 build.extra_flags 時必須保留板子原本的旗標（boards.txt 第 108 行），否則 Arduino.h 會報 Flash/SD 錯誤
BOARD_FLAGS='-DARDUINO_SDK -DARDUINO_AMBPRO2 -DBOARD_AMB82_HUB8735 -DBOARD_AMB82_HUB8735_ULTRA {build.usb_flags} {build.menu_flags}'
mkdir -p "$OUT"
fail=0
run() {  # name sketch flags
  local name="$1" sketch="$2" flags="$3"
  [[ "$name" =~ $ONLY ]] || return 0
  if "$CLI" compile --config-file "$CFG" --fqbn "$FQBN" --library "$LIB" \
      --build-path "$OUT/build_$name" --build-property "build.extra_flags=$BOARD_FLAGS $flags" \
      "$LIB/examples/$sketch" > "$OUT/$name.log" 2>&1; then
    echo "PASS $name: $(grep -E 'Sketch uses|使用了' "$OUT/$name.log" | head -1)"
  else
    echo "FAIL $name (see $OUT/$name.log)"; fail=1
  fi
}
for w in 1 2 3; do run "wiring$w" MultiOledDemo "-DEVAC_WIRING=$w"; done
# 方案 D：鏡頭 HUB 各 1 塊角落 0x3C；H5/H6/H7 只驅動 OLED，只用 Wire
for h in 0 1 2 3 5 6 7; do run "hub$h" Hub1FCeiling "-DEVAC_HUB=$h"; done
# 備案：一台驅動 5 塊（TCA9548A），或 Wire 2 塊 + Wire1 1 塊 / 2 塊
run backup_tca       Hub1FCeiling "-DEVAC_HUB=4 -DEVAC_HUB5_BUS=2"
run backup_wire1_2p1 Hub1FCeiling "-DEVAC_HUB=4 -DEVAC_HUB5_BUS=1 -DEVAC_WIRE1_COUNT=1"
run backup_wire1_2p2 Hub1FCeiling "-DEVAC_HUB=4 -DEVAC_HUB5_BUS=1 -DEVAC_WIRE1_COUNT=2"
exit $fail
