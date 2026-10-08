#!/bin/bash

# 修复后重新编译 40k 和 20k 版本
set -e

BASE_DIR=$(pwd)

compile_version() {
    local BENCH=$1
    local TIMER_VALUE=$2
    local OUTPUT_NAME=$3
    local OUT_DIR=$4
    
    echo ""
    echo "=========================================="
    echo "编译: $OUTPUT_NAME (TIMER_VALUE=$TIMER_VALUE)"
    echo "=========================================="
    
    make clean > /dev/null 2>&1 || true
    make all BENCHMARK=$BENCH TIMER=1 TIMER_VALUE=$TIMER_VALUE OUTPUT=$OUTPUT_NAME 2>&1 | tail -3
    
    if [ -f "${OUTPUT_NAME}.out" ]; then
        cp "${OUTPUT_NAME}.out" "$OUT_DIR/"
        cp "${OUTPUT_NAME}.hex" "$OUT_DIR/" 2>/dev/null || true
        echo "✓ 复制到 $OUT_DIR/"
    fi
}

echo "=== 重新编译 20k 和 40k 版本 ==="

# crc16
compile_version "crc16" 20000 "crc16_asap_timer_20k" "Benchmarks/crc"
compile_version "crc16" 40000 "crc16_asap_timer_40k" "Benchmarks/crc"

# crc32
compile_version "crc32" 20000 "crc32_asap_timer_20k" "Benchmarks/crc"
compile_version "crc32" 40000 "crc32_asap_timer_40k" "Benchmarks/crc"

# conv
compile_version "conv" 20000 "conv_asap_timer_20k" "Benchmarks/conv"
compile_version "conv" 40000 "conv_asap_timer_40k" "Benchmarks/conv"

# bc
compile_version "bc" 20000 "bc_asap_timer_20k" "Benchmarks/bc"
compile_version "bc" 40000 "bc_asap_timer_40k" "Benchmarks/bc"

# cf
compile_version "cf" 20000 "cf_asap_timer_20k" "Benchmarks/cf"
compile_version "cf" 40000 "cf_asap_timer_40k" "Benchmarks/cf"

# ar
compile_version "ar" 20000 "ar_asap_timer_20k" "Benchmarks/ar"
compile_version "ar" 40000 "ar_asap_timer_40k" "Benchmarks/ar"

echo ""
echo "============================================"
echo "修复后重新编译完成！"
echo "============================================"
