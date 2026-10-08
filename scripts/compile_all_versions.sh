#!/bin/bash
set -e

cd /Users/wyf/Desktop/code/ASAP_right_副本/backups/conv成功版本

# 创建输出目录
OUTPUT_DIR="compiled_outputs"
mkdir -p "$OUTPUT_DIR"

# Benchmark 列表 (Makefile中的名称)
BENCHMARKS=("ar" "bc" "cf" "conv" "crc" "crc32")
BENCH_DISPLAY=("ar" "bc" "cf" "conv" "crc16" "crc32")

echo "============================================"
echo "=== 开始编译所有 benchmark 的四个版本 ==="
echo "============================================"
echo ""

for i in "${!BENCHMARKS[@]}"; do
    BENCH="${BENCHMARKS[$i]}"
    DISPLAY="${BENCH_DISPLAY[$i]}"
    
    echo ""
    echo "============================================"
    echo "=== $DISPLAY ==="
    echo "============================================"
    
    # 1. no_timer 版本
    echo ">>> $DISPLAY - no_timer"
    rm -rf build/* 2>/dev/null || true
    make all BENCHMARK=$BENCH TIMER=0 2>&1 | grep -E "(最终固件|成功)" || true
    cp ${BENCH}_asap_no_timer.out "$OUTPUT_DIR/" 2>/dev/null && echo "  ✓ 已保存" || echo "  ✗ 复制失败"
    
    # 2. 10k 版本
    echo ">>> $DISPLAY - timer_10k (TIMER_VALUE=10000)"
    rm -rf build/* 2>/dev/null || true
    make all BENCHMARK=$BENCH TIMER=1 TIMER_VALUE=10000 2>&1 | grep -E "(最终固件|成功)" || true
    cp ${BENCH}_asap_timer_10k.out "$OUTPUT_DIR/" 2>/dev/null && echo "  ✓ 已保存" || echo "  ✗ 复制失败"
    
    # 3. 20k 版本
    echo ">>> $DISPLAY - timer_20k (TIMER_VALUE=20000)"
    rm -rf build/* 2>/dev/null || true
    make all BENCHMARK=$BENCH TIMER=1 TIMER_VALUE=20000 2>&1 | grep -E "(最终固件|成功)" || true
    cp ${BENCH}_asap_timer_20k.out "$OUTPUT_DIR/" 2>/dev/null && echo "  ✓ 已保存" || echo "  ✗ 复制失败"
    
    # 4. 40k 版本
    echo ">>> $DISPLAY - timer_40k (TIMER_VALUE=40000)"
    rm -rf build/* 2>/dev/null || true
    make all BENCHMARK=$BENCH TIMER=1 TIMER_VALUE=40000 2>&1 | grep -E "(最终固件|成功)" || true
    cp ${BENCH}_asap_timer_40k.out "$OUTPUT_DIR/" 2>/dev/null && echo "  ✓ 已保存" || echo "  ✗ 复制失败"
done

echo ""
echo "============================================"
echo "=== 编译完成，验证输出文件 ==="
echo "============================================"
echo ""
ls -lh "$OUTPUT_DIR"/*.out 2>/dev/null | sort
echo ""
echo "总计: $(ls "$OUTPUT_DIR"/*.out 2>/dev/null | wc -l) 个 .out 文件"
