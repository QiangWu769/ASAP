#!/bin/bash
set -e

cd /Users/wyf/Desktop/code/ASAP_right_副本/backups/conv成功版本

echo "============================================"
echo "=== 编译六个 benchmark 的纯净版本 (-O0) ==="
echo "============================================"
echo ""

# 编译函数
compile_pure() {
    local NAME=$1
    local SRC=$2
    local OUTPUT="${NAME}_pure.out"
    
    echo ">>> 编译 $NAME"
    msp430-elf-gcc -mmcu=msp430fr5969 -O0 -g -DTIMER=0 \
        -I Benchmarks \
        "$SRC" \
        -o "$OUTPUT"
    
    if [ -f "$OUTPUT" ]; then
        SIZE=$(ls -lh "$OUTPUT" | awk '{print $5}')
        echo "  ✓ $OUTPUT ($SIZE)"
    else
        echo "  ✗ 编译失败"
    fi
}

# ar
compile_pure "ar" "Benchmarks/ar/main_ar.c"

# bc
compile_pure "bc" "Benchmarks/bc/main_bc.c"

# cf
compile_pure "cf" "Benchmarks/cf/main_cf_plain.c"

# conv
compile_pure "conv" "Benchmarks/conv/main_conv_plain.c"

# crc16
compile_pure "crc16" "Benchmarks/crc/main_crc_test_16.c"

# crc32
compile_pure "crc32" "Benchmarks/crc/main_crc_test_32.c"

echo ""
echo "============================================"
echo "=== 编译完成 ==="
echo "============================================"
ls -lh *_pure.out
