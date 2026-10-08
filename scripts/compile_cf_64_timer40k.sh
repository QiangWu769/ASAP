#!/bin/bash
# CF基准测试编译脚本（NUM_BUCKETS=64, Timer=40000）- 三个版本
# 1. 纯净版本（不走ASAP，没有定时器）
# 2. ASAP版本（走ASAP，没有定时器）
# 3. ASAP+定时器版本（走ASAP，有定时器，周期5ms）

set -e  # 遇到错误立即退出

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "╔════════════════════════════════════════════════════╗"
echo "║  CF基准测试（NUM_BUCKETS=64，Timer=40000）       ║"
echo "║  三版本编译 - 定时器周期延长到5ms                ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

# ============================================================
# 版本1: 纯净版本（不走ASAP，没有定时器）
# ============================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【版本1】编译纯净版本（不走ASAP，没有定时器）"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

msp430-elf-gcc -mmcu=msp430fr5969 -O0 -g -DTIMER=0 \
  -o cf_64_pure_no_asap.out \
  Benchmarks/cf/main_cf.c \
  -lgcc

msp430-elf-objcopy -O ihex cf_64_pure_no_asap.out cf_64_pure_no_asap.hex

echo "✓ 纯净版本编译完成: cf_64_pure_no_asap.hex"
ls -lh cf_64_pure_no_asap.*
echo ""

# ============================================================
# 版本2: ASAP版本（走ASAP，但没有定时器）
# ============================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【版本2】编译ASAP版本（走ASAP，但没有定时器）"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 清理之前的build目录
rm -rf build/*

# 使用Makefile编译ASAP版本（TIMER=0，使用去重优化）
make clean
make SRC=Benchmarks/cf/main_cf.c \
     OUTPUT=cf_64_asap_no_timer.out \
     TIMER=0 \
     CFLAGS="-O0 -g -DTIMER=0" \
     STAGE11=Compiler/stage11_generate_restore_dedup.py

# 转换为hex
msp430-elf-objcopy -O ihex cf_64_asap_no_timer.out cf_64_asap_no_timer.hex

echo "✓ ASAP版本（无定时器）编译完成: cf_64_asap_no_timer.hex"
ls -lh cf_64_asap_no_timer.*
echo ""

# ============================================================
# 版本3: ASAP+定时器版本（走ASAP，有定时器，周期5ms）
# ============================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【版本3】编译ASAP+定时器版本（走ASAP，定时器5ms周期）"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 清理之前的build目录
rm -rf build/*

# 使用Makefile编译ASAP+定时器版本（TIMER=1，使用去重优化）
make clean
make SRC=Benchmarks/cf/main_cf.c \
     OUTPUT=cf_64_asap_timer40k.out \
     TIMER=1 \
     CFLAGS="-O0 -g -DTIMER=1" \
     STAGE11=Compiler/stage11_generate_restore_dedup.py

# 转换为hex
msp430-elf-objcopy -O ihex cf_64_asap_timer40k.out cf_64_asap_timer40k.hex

echo "✓ ASAP+定时器版本编译完成: cf_64_asap_timer40k.hex"
ls -lh cf_64_asap_timer40k.*
echo ""

# ============================================================
# 编译总结
# ============================================================
echo "╔════════════════════════════════════════════════════╗"
echo "║  编译完成总结                                      ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "三个版本已生成（NUM_BUCKETS=64, Timer=40000）："
echo ""
echo "1. cf_64_pure_no_asap.hex      - 纯净版本（不走ASAP，无定时器）"
echo "   特性：直接编译，无ASAP保护，无断电模拟"
echo ""
echo "2. cf_64_asap_no_timer.hex     - ASAP版本（走ASAP，无定时器）"
echo "   特性：ASAP备份恢复，无断电模拟"
echo ""
echo "3. cf_64_asap_timer40k.hex     - ASAP+定时器版本（走ASAP，定时器5ms）"
echo "   特性：ASAP备份恢复 + 定时器断电模拟（周期5ms，比原来2.5ms慢一倍）"
echo ""
echo "文件大小对比："
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -f "cf_64_pure_no_asap.out" ]; then
    echo "纯净版本："
    msp430-elf-size cf_64_pure_no_asap.out
    echo ""
fi

if [ -f "cf_64_asap_no_timer.out" ]; then
    echo "ASAP版本（无定时器）："
    msp430-elf-size cf_64_asap_no_timer.out
    echo ""
fi

if [ -f "cf_64_asap_timer40k.out" ]; then
    echo "ASAP+定时器版本（5ms周期）："
    msp430-elf-size cf_64_asap_timer40k.out
    echo ""
fi

echo "文件列表："
ls -lh cf_64_*.hex cf_64_*.out 2>/dev/null || true
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【关键配置】"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "NUM_BUCKETS: 64 (数组大小128字节)"
echo "NUM_KEYS: 16"
echo "定时器周期: 40000 (5ms @ 8MHz)"
echo "定时器中断频率: 200 Hz (原来400Hz)"
echo ""
echo "💡 定时器周期加倍，应该能让程序有更多时间执行业务逻辑"
echo ""
echo "✅ 全部编译完成！"


