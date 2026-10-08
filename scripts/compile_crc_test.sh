#!/bin/bash
set -e

echo "========================================="
echo "编译CRC测试程序"
echo "========================================="

# 清理旧的编译产物
rm -rf build_crc_test
mkdir -p build_crc_test

# 复制必要文件
cp -r Runtime build_crc_test/
cp -r Compiler build_crc_test/
cp Benchmarks/crc/main_crc_test.c build_crc_test/main.c
cp Makefile build_crc_test/

cd build_crc_test

# 编译 TIMER=0 (无断电)
echo ""
echo ">>> 编译 CRC_PURE (TIMER=0)"
make clean > /dev/null 2>&1 || true
make MCU=msp430fr5969 \
     SOURCE=main.c \
     OUTPUT=crc_pure \
     CFLAGS="-DTIMER=0" \
     BUILD_DIR=build_pure \
     2>&1 | tee ../compile_crc_pure.log

echo ""
echo ">>> 编译 CRC_ASAP (TIMER=1)"
make clean > /dev/null 2>&1 || true
make MCU=msp430fr5969 \
     SOURCE=main.c \
     OUTPUT=crc_asap \
     CFLAGS="-DTIMER=1" \
     BUILD_DIR=build_asap \
     2>&1 | tee ../compile_crc_asap.log

cd ..

# 复制输出文件
cp build_crc_test/crc_pure.hex ./
cp build_crc_test/crc_pure.out ./
cp build_crc_test/crc_asap.hex ./
cp build_crc_test/crc_asap.out ./

echo ""
echo "========================================="
echo "✅ 编译完成！"
echo "========================================="
echo "  纯净版: crc_pure.hex"
echo "  ASAP版: crc_asap.hex"
echo ""

# 检查大小
ls -lh crc_pure.hex crc_asap.hex 2>/dev/null || true
