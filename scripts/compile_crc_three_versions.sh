#!/bin/bash
set -e

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║    编译CRC三个版本                                          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo

# ===== 版本1: 纯净版 (无ASAP, TIMER=0) =====
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣  编译纯净版 (crc_pure.out)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
make clean > /dev/null 2>&1
msp430-elf-gcc -mmcu=msp430fr5969 -O0 -g -DTIMER=0 \
    Benchmarks/crc/main_crc_test.c \
    -o crc_pure.out \
    -lgcc
msp430-elf-objcopy -O ihex crc_pure.out crc_pure.hex
echo "✅ 纯净版编译完成"
ls -lh crc_pure.*
echo

# ===== 版本2: ASAP无定时器 (TIMER=0) =====
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣  编译ASAP无定时器版本 (crc_asap_notimer.out)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
make clean > /dev/null 2>&1
make all \
    SRC="Benchmarks/crc/main_crc_test.c" \
    OUTPUT="crc_asap_notimer.out" \
    CFLAGS="-mmcu=msp430fr5969 -O0 -g -DTIMER=0" \
    STAGE11="Compiler/stage11_generate_restore_dedup.py" \
    2>&1 | grep -E "✅|✓|Stage|WID"
msp430-elf-objcopy -O ihex crc_asap_notimer.out crc_asap_notimer.hex
echo "✅ ASAP无定时器版本编译完成"
ls -lh crc_asap_notimer.*
echo

# ===== 版本3: ASAP定时器 (TIMER=1) =====
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣  编译ASAP定时器版本 (crc_asap_timer.out)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
make clean > /dev/null 2>&1
make all \
    SRC="Benchmarks/crc/main_crc_test.c" \
    OUTPUT="crc_asap_timer.out" \
    CFLAGS="-mmcu=msp430fr5969 -O0 -g -DTIMER=1" \
    STAGE11="Compiler/stage11_generate_restore_dedup.py" \
    2>&1 | grep -E "✅|✓|Stage|WID"
msp430-elf-objcopy -O ihex crc_asap_timer.out crc_asap_timer.hex
echo "✅ ASAP定时器版本编译完成"
ls -lh crc_asap_timer.*
echo

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 全部编译完成！"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ls -lh crc_*.out crc_*.hex
