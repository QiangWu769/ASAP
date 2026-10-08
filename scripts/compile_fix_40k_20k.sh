#!/bin/bash
set -e

PROJECT_DIR="/Users/wyf/Desktop/code/ASAP_right_副本/backups/conv成功版本"
cd "$PROJECT_DIR"

# 编译函数
compile_version() {
    local BENCH_NAME=$1    # Makefile中的名称 (crc, crc32, conv, bc, cf, ar)
    local OUTPUT_PREFIX=$2 # 输出文件前缀 (crc16, crc32, conv, bc, cf, ar)
    local TIMER_VALUE=$3
    local SUFFIX=$4        # 20k 或 40k
    local OUT_DIR=$5
    
    echo ""
    echo ">>> 编译 $OUTPUT_PREFIX - TIMER=1, TIMER_VALUE=$TIMER_VALUE"
    
    make clean > /dev/null 2>&1 || true
    rm -rf build/*
    
    make all BENCHMARK=$BENCH_NAME TIMER=1 TIMER_VALUE=$TIMER_VALUE 2>&1 | tail -5
    
    # 输出文件是 ${BENCH_NAME}_asap_timer.out
    local SRC_OUT="${BENCH_NAME}_asap_timer.out"
    local DST_OUT="$OUT_DIR/${OUTPUT_PREFIX}_asap_timer_${SUFFIX}.out"
    
    if [ -f "$SRC_OUT" ]; then
        cp "$SRC_OUT" "$DST_OUT"
        echo "  ✓ 已复制 $SRC_OUT → $DST_OUT"
    else
        echo "  ✗ 未找到 $SRC_OUT"
        return 1
    fi
}

# crc16 (Makefile中叫 crc)
echo "============================================"
echo "=== crc16 ==="
echo "============================================"
compile_version "crc" "crc16" 20000 "20k" "Benchmarks/crc"
compile_version "crc" "crc16" 40000 "40k" "Benchmarks/crc"

# crc32
echo "============================================"
echo "=== crc32 ==="
echo "============================================"
compile_version "crc32" "crc32" 20000 "20k" "Benchmarks/crc"
compile_version "crc32" "crc32" 40000 "40k" "Benchmarks/crc"

# conv
echo "============================================"
echo "=== conv ==="
echo "============================================"
compile_version "conv" "conv" 20000 "20k" "Benchmarks/conv"
compile_version "conv" "conv" 40000 "40k" "Benchmarks/conv"

# bc
echo "============================================"
echo "=== bc ==="
echo "============================================"
compile_version "bc" "bc" 20000 "20k" "Benchmarks/bc"
compile_version "bc" "bc" 40000 "40k" "Benchmarks/bc"

# cf
echo "============================================"
echo "=== cf ==="
echo "============================================"
compile_version "cf" "cf" 20000 "20k" "Benchmarks/cf"
compile_version "cf" "cf" 40000 "40k" "Benchmarks/cf"

# ar
echo "============================================"
echo "=== ar ==="
echo "============================================"
compile_version "ar" "ar" 20000 "20k" "Benchmarks/ar"
compile_version "ar" "ar" 40000 "40k" "Benchmarks/ar"

# 删除错误后缀的文件
echo ""
echo "清理错误后缀的文件..."
rm -f Benchmarks/crc/*_2k0.out Benchmarks/crc/*_4k0.out
rm -f Benchmarks/conv/*_2k0.out Benchmarks/conv/*_4k0.out
rm -f Benchmarks/bc/*_2k0.out Benchmarks/bc/*_4k0.out
rm -f Benchmarks/cf/*_2k0.out Benchmarks/cf/*_4k0.out
rm -f Benchmarks/ar/*_2k0.out Benchmarks/ar/*_4k0.out

echo ""
echo "============================================"
echo "=== 所有编译完成 ==="
echo "============================================"
echo ""
echo "验证生成的 .out 文件："
echo "--- crc ---"
ls -lh Benchmarks/crc/*_asap_timer_20k.out Benchmarks/crc/*_asap_timer_40k.out 2>/dev/null || echo "未找到"
echo "--- conv ---"
ls -lh Benchmarks/conv/*_asap_timer_20k.out Benchmarks/conv/*_asap_timer_40k.out 2>/dev/null || echo "未找到"
echo "--- bc ---"
ls -lh Benchmarks/bc/*_asap_timer_20k.out Benchmarks/bc/*_asap_timer_40k.out 2>/dev/null || echo "未找到"
echo "--- cf ---"
ls -lh Benchmarks/cf/*_asap_timer_20k.out Benchmarks/cf/*_asap_timer_40k.out 2>/dev/null || echo "未找到"
echo "--- ar ---"
ls -lh Benchmarks/ar/*_asap_timer_20k.out Benchmarks/ar/*_asap_timer_40k.out 2>/dev/null || echo "未找到"
