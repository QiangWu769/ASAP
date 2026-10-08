#!/bin/bash
# CF基准测试编译脚本 - 使用去重优化的恢复表
# 这个版本使用 stage11_generate_restore_dedup.py 来避免恢复表的重复代码

set -e  # 遇到错误立即退出

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "╔════════════════════════════════════════════════════╗"
echo "║  CF基准测试 - 使用去重优化的恢复表              ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

# 清理之前的build目录
rm -rf build/*

# 使用Makefile编译，但替换 Stage 11 为去重版本
# 方法：临时替换 STAGE11 变量

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【编译】使用去重优化版本的 Stage 11"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

make clean
make SRC=Benchmarks/cf/main_cf.c \
     OUTPUT=cf_asap_timer_dedup.out \
     TIMER=1 \
     CFLAGS="-O0 -g -DTIMER=1" \
     STAGE11=Compiler/stage11_generate_restore_dedup.py

# 转换为hex
msp430-elf-objcopy -O ihex cf_asap_timer_dedup.out cf_asap_timer_dedup.hex

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【完成】编译成功"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ls -lh cf_asap_timer_dedup.*
echo ""

# 显示代码大小对比
echo "╔════════════════════════════════════════════════════╗"
echo "║  代码大小统计                                      ║"
echo "╚════════════════════════════════════════════════════╝"

if [ -f "build/asap_restore.s" ]; then
    RESTORE_LINES=$(wc -l < build/asap_restore.s)
    echo "恢复逻辑代码行数: $RESTORE_LINES"
fi

if [ -f "build/A_redirected.s" ]; then
    MAIN_LINES=$(wc -l < build/A_redirected.s)
    echo "主程序代码行数: $MAIN_LINES"
fi

echo ""
msp430-elf-size cf_asap_timer_dedup.out

echo ""
echo "✅ 编译完成！文件: cf_asap_timer_dedup.hex"


