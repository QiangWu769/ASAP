#!/bin/bash
# AR基准测试编译脚本 - 三个版本
# 1. 纯净版本（不走ASAP，没有定时器）
# 2. ASAP版本（走ASAP，但没有定时器）
# 3. ASAP+定时器版本（走ASAP，有定时器）

set -e  # 遇到错误立即退出

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "╔════════════════════════════════════════════════════╗"
echo "║  AR基准测试 - 三版本编译                          ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

# ============================================================
# 版本1: 纯净版本（不走ASAP，没有定时器）
# ============================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【版本1】编译纯净版本（不走ASAP，没有定时器）"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

msp430-elf-gcc -mmcu=msp430fr5969 -O0 -g -DTIMER=0 \
  -I Benchmarks/ar \
  -o ar_pure_no_asap.out \
  Benchmarks/ar/main_ar.c \
  -lgcc

msp430-elf-objcopy -O ihex ar_pure_no_asap.out ar_pure_no_asap.hex

echo "✓ 纯净版本编译完成: ar_pure_no_asap.hex"
ls -lh ar_pure_no_asap.*
echo ""

# ============================================================
# 版本2: ASAP版本（走ASAP，但没有定时器）
# ============================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【版本2】编译ASAP版本（走ASAP，但没有定时器）"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 清理之前的build目录
rm -rf build/*

# 使用Makefile编译ASAP版本（TIMER=0）
make clean
make SRC=Benchmarks/ar/main_ar.c \
     OUTPUT=ar_asap_no_timer.out \
     TIMER=0 \
     CFLAGS="-O0 -g -DTIMER=0"

# 转换为hex
msp430-elf-objcopy -O ihex ar_asap_no_timer.out ar_asap_no_timer.hex

echo "✓ ASAP版本（无定时器）编译完成: ar_asap_no_timer.hex"
ls -lh ar_asap_no_timer.*
echo ""

# ============================================================
# 版本3: ASAP+定时器版本（走ASAP，有定时器）
# ============================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【版本3】编译ASAP+定时器版本（走ASAP，有定时器）"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 清理之前的build目录
rm -rf build/*

# 使用Makefile编译ASAP+定时器版本（TIMER=1）
make clean
make SRC=Benchmarks/ar/main_ar.c \
     OUTPUT=ar_asap_timer.out \
     TIMER=1 \
     CFLAGS="-O0 -g -DTIMER=1"

# 转换为hex
msp430-elf-objcopy -O ihex ar_asap_timer.out ar_asap_timer.hex

echo "✓ ASAP+定时器版本编译完成: ar_asap_timer.hex"
ls -lh ar_asap_timer.*
echo ""

# ============================================================
# 编译总结
# ============================================================
echo "╔════════════════════════════════════════════════════╗"
echo "║  编译完成总结                                      ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "三个版本已生成："
echo ""
echo "1. ar_pure_no_asap.hex      - 纯净版本（不走ASAP，无定时器）"
echo "   特性：直接编译，无ASAP保护，无断电模拟"
echo ""
echo "2. ar_asap_no_timer.hex     - ASAP版本（走ASAP，无定时器）"
echo "   特性：ASAP备份恢复，无断电模拟"
echo ""
echo "3. ar_asap_timer.hex        - ASAP+定时器版本（走ASAP，有定时器）"
echo "   特性：ASAP备份恢复 + 定时器断电模拟"
echo ""
echo "文件列表："
ls -lh ar_*.hex ar_*.out 2>/dev/null || true
echo ""
echo "✅ 全部编译完成！"


















