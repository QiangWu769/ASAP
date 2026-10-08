#!/bin/bash
# ADPCM Encode 纯净版编译脚本（无 ASAP，仅用于测试基准时间）
# 用法: ./compile_adpcm_encode_plain.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "ADPCM Encode 纯净版编译"
echo "=========================================="

# 编译
msp430-elf-gcc -mmcu=msp430fr5969 -O0 -DTIMER=0 \
    -o adpcm_encode_plain.out \
    Benchmarks/adpcm_encode/main_adpcm_encode.c \
    -I Benchmarks/adpcm_encode

msp430-elf-objcopy -O ihex adpcm_encode_plain.out adpcm_encode_plain.hex

echo ""
echo "=========================================="
echo "编译完成！"
echo "输出文件: adpcm_encode_plain.out, adpcm_encode_plain.hex"
echo "=========================================="























