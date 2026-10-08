#!/bin/bash
set -e

PROJECT_DIR="/Users/wyf/Desktop/code/ASAP_right_副本/backups/conv成功版本"
cd "$PROJECT_DIR"

# 编译函数 - 不使用 make clean，只清理 build 目录
compile_version() {
    local BENCH_NAME=$1
    local OUTPUT_PREFIX=$2
    local TIMER=$3
    local TIMER_VALUE=$4
    local OUTPUT_SUFFIX=$5
    
    local OUTPUT_FILE="${OUTPUT_PREFIX}_asap_${OUTPUT_SUFFIX}.out"
    
    echo ""
    echo ">>> 编译 $OUTPUT_PREFIX - TIMER=$TIMER, TIMER_VALUE=$TIMER_VALUE → $OUTPUT_FILE"
    
    # 只清理 build 目录，不删除 .out 文件
    rm -rf build/*
    
    if [ "$TIMER" -eq 0 ]; then
        make all BENCHMARK=$BENCH_NAME TIMER=0 2>&1 | tail -3
        local SRC_OUT="${BENCH_NAME}_asap_no_timer.out"
    else
        make all BENCHMARK=$BENCH_NAME TIMER=1 TIMER_VALUE=$TIMER_VALUE 2>&1 | tail -3
        local SRC_OUT="${BENCH_NAME}_asap_timer.out"
    fi
    
    if [ -f "$SRC_OUT" ]; then
        # 如果源文件和目标文件不同，才移动
        if [ "$SRC_OUT" != "$OUTPUT_FILE" ]; then
            mv "$SRC_OUT" "$OUTPUT_FILE"
        fi
        echo "  ✓ 生成 $OUTPUT_FILE"
    else
        echo "  ✗ 编译失败"
        return 1
    fi
}

# 编译一个 benchmark 的四个版本
compile_benchmark() {
    local BENCH_NAME=$1
    local OUTPUT_PREFIX=$2
    
    echo ""
    echo "============================================"
    echo "=== $OUTPUT_PREFIX ==="
    echo "============================================"
    
    compile_version "$BENCH_NAME" "$OUTPUT_PREFIX" 0 0       "no_timer"
    compile_version "$BENCH_NAME" "$OUTPUT_PREFIX" 1 10000   "10k"
    compile_version "$BENCH_NAME" "$OUTPUT_PREFIX" 1 20000   "20k"
    compile_version "$BENCH_NAME" "$OUTPUT_PREFIX" 1 40000   "40k"
}

echo "============================================"
echo "=== 开始编译所有 benchmark ==="
echo "============================================"
echo ""
echo "定时器值:"
echo "  no_timer = 无定时器 (TIMER=0)"
echo "  10k = TIMER_VALUE=10000"
echo "  20k = TIMER_VALUE=20000"  
echo "  40k = TIMER_VALUE=40000"

# 编译所有 benchmark
compile_benchmark "ar"    "ar"
compile_benchmark "bc"    "bc"
compile_benchmark "cf"    "cf"
compile_benchmark "conv"  "conv"
compile_benchmark "crc"   "crc16"
compile_benchmark "crc32" "crc32"

echo ""
echo "============================================"
echo "=== 所有编译完成 ==="
echo "============================================"
echo ""
echo "生成的 .out 文件:"
ls -lh ar_asap_*.out bc_asap_*.out cf_asap_*.out conv_asap_*.out crc16_asap_*.out crc32_asap_*.out 2>/dev/null || echo "未找到"
