#!/bin/bash
# ============================================================
# 完整编译 cf/main_cf_plain.c（使用动态数组支持）
# ============================================================

set -e  # 遇到错误立即退出

WORKDIR="/Users/wyf/Desktop/ASAP_right_副本/backups/complete_backup_before_no_sp_20251105_204648 21"
cd "$WORKDIR"

SRC="Benchmarks/cf/main_cf_plain.c"
MCU="msp430fr5969"
CFLAGS="-O0 -g -DPRINTF=printf"

echo "========================================"
echo "完整编译 cf/main_cf_plain.c"
echo "使用动态数组支持"
echo "========================================"
echo ""

# 清理
echo "[0/14] 清理构建目录..."
rm -rf build/*
mkdir -p build

# Stage 1: 编译到汇编
echo "[1/14] Stage 1: C源码 → 汇编..."
python3 Compiler/stage1_compile_to_asm.py "$SRC" \
    --output build/A_sym.s \
    --compiler msp430-elf-gcc \
    --mcu "$MCU" \
    --cflags "$CFLAGS"

# Stage 2b: 幂等化
echo "[2/14] Stage 2b: 幂等化转换..."
python3 Compiler/stage2b_make_idempotent.py \
    build/A_sym.s \
    --output build/A_idempotent.s

# Stage 2: 分析函数
echo "[3/14] Stage 2: 分析函数信息..."
python3 Compiler/stage2_analyze_functions.py \
    build/A_idempotent.s \
    --output build/function_info.json

# Stage 3: 识别关键写 + 动态数组（使用增强版）
echo "[4/14] Stage 3: 识别关键写 + 动态数组..."
python3 Compiler/stage3_analyze_writes_with_array.py \
    build/A_idempotent.s \
    --functions build/function_info.json \
    --config Compiler/bc_core_config.json \
    --output build/candidates.json

# Stage 4: 分配FRAM + 哈希表（使用增强版）
echo "[5/14] Stage 4: 分配FRAM槽位 + 哈希表..."
python3 Compiler/stage4_allocate_fram_with_array.py \
    build/candidates.json \
    --output build/fram_slots.json \
    --linker build/fram_symbols.ld \
    --fram-base 0x6400 \
    --array-base 0x6000

# Stage 5: 插桩备份 + 哈希表备份（使用增强版）
echo "[6/14] Stage 5: 插桩备份 + 哈希表备份..."
python3 Compiler/stage5_inject_backup_with_array.py \
    build/A_idempotent.s \
    --candidates build/candidates.json \
    --fram-slots build/fram_slots.json \
    --output build/A_instrumented.s

# Stage 5b: 在main插入恢复检查
echo "[7/14] Stage 5b: 在main插入恢复检查..."
python3 Compiler/stage5b_inject_main_restore.py \
    build/A_instrumented.s

# Stage 5c: 函数入口返回地址备份
echo "[8/14] Stage 5c: 函数入口返回地址备份..."
python3 Compiler/stage5c_inject_return_addr_backup.py \
    build/A_instrumented.s \
    --functions build/function_info.json \
    --config Compiler/bc_core_config.json

# Stage 6: 编译临时固件
echo "[9/14] Stage 6: 编译临时固件..."
# 编译符号文件
if [ -f build/func_sp_symbols.s ]; then
    msp430-elf-gcc -mmcu="$MCU" $CFLAGS -c build/func_sp_symbols.s -o build/func_sp_symbols.o
fi

# 编译主程序
msp430-elf-gcc -mmcu="$MCU" $CFLAGS -c build/A_instrumented.s -o build/main.o

# 编译runtime组件
msp430-elf-gcc -mmcu="$MCU" $CFLAGS -c Runtime/asap_restore_stub.s -o build/asap_restore_stub.o
msp430-elf-gcc -mmcu="$MCU" $CFLAGS -c Runtime/bootloader_with_restore.s -o build/bootloader_restore.o

# 编译哈希表函数（关键！）
echo "  编译哈希表函数..."
msp430-elf-gcc -mmcu="$MCU" $CFLAGS -c Runtime/asap_hashtable.s -o build/asap_hashtable.o

# 链接临时固件（包含哈希表）
msp430-elf-gcc -mmcu="$MCU" $CFLAGS \
    -nostartfiles \
    -T Runtime/src/port/msp430/msp430fr5969_bootloader.ld \
    -Wl,--just-symbols=build/fram_symbols.ld \
    -o build/firmware_temp.elf \
    build/bootloader_restore.o \
    build/main.o \
    build/asap_restore_stub.o \
    build/asap_hashtable.o \
    build/func_sp_symbols.o \
    -lgcc

# Stage 7: 提取WID→PC映射
echo "[10/14] Stage 7: 提取WID→PC映射..."
python3 Compiler/stage7_extract_wid_pc.py \
    build/firmware_temp.elf \
    --output build/wid_pc_map.json \
    --objdump msp430-elf-objdump

# Stage 8: 分析读写操作
echo "[11/14] Stage 8: 分析读写操作..."
python3 Compiler/stage8_analyze_reads_writes_v2.py \
    build/firmware_temp.elf \
    --output build/reads_writes.json

# Stage 9: 生命周期分析
echo "[12/14] Stage 9: 生命周期分析..."
python3 Compiler/stage9_analyze_lifetime.py \
    --reads-writes build/reads_writes.json \
    --wid-pc-map build/wid_pc_map.json \
    --candidates build/candidates.json \
    --output build/lifetime_data.json

# Stage 9b: 构建调用图
echo "[13/14] Stage 9b: 构建函数调用图..."
python3 Compiler/stage9b_build_call_graph.py \
    --asm build/A_instrumented.s \
    --function-info build/function_info.json \
    --candidates build/candidates.json \
    --output build/call_graph.json

# Stage 5d: 重定向间接槽位
echo "[14/14] Stage 5d: 重定向间接槽位..."
python3 Compiler/stage5d_redirect_indirect_slots.py \
    --input build/A_instrumented.s \
    --output build/A_redirected.s \
    --call-graph build/call_graph.json \
    --fram-slots build/fram_slots.json \
    --redirect-map build/redirect_map.json

# Stage 10: 生成PC范围
echo "[15/14] Stage 10: 生成PC范围..."
python3 Compiler/stage10_merge_pc_ranges.py \
    --lifetime build/lifetime_data.json \
    --fram-slots build/fram_slots.json \
    --candidates build/candidates.json \
    --call-graph build/call_graph.json \
    --redirect-map build/redirect_map.json \
    --wid-pc-map build/wid_pc_map.json \
    --output build/pc_ranges.json

# Stage 11: 生成恢复逻辑（使用增强版）
echo "[16/14] Stage 11: 生成恢复逻辑（支持动态数组）..."
python3 Compiler/stage11_generate_restore_with_array.py \
    --pc-ranges build/pc_ranges.json \
    --wid-pc-map build/wid_pc_map.json \
    --fram-slots build/fram_slots.json \
    --function-info build/function_info.json \
    --output build/asap_restore.s \
    --format asm

# Stage 12: 编译恢复逻辑
echo "[17/14] Stage 12: 编译恢复逻辑..."
msp430-elf-gcc -mmcu="$MCU" $CFLAGS -c build/asap_restore.s -o build/asap_restore.o

# Stage 13: 最终链接（包含哈希表函数）
echo "[18/14] Stage 13: 最终链接..."

# 阶段1: 初步链接
msp430-elf-gcc -mmcu="$MCU" $CFLAGS -c Runtime/bootloader_with_restore.s -o build/bootloader_restore.o
msp430-elf-gcc -mmcu="$MCU" $CFLAGS -c build/A_redirected.s -o build/main.o

msp430-elf-gcc -mmcu="$MCU" $CFLAGS \
    -nostartfiles \
    -T Runtime/src/port/msp430/msp430fr5969_bootloader.ld \
    -Wl,--just-symbols=build/fram_symbols.ld \
    -o firmware_final.out \
    build/bootloader_restore.o \
    build/main.o \
    build/asap_restore.o \
    build/asap_hashtable.o \
    build/func_sp_symbols.o \
    -lgcc

# 阶段2: 重新提取PC映射
echo "  重新提取PC映射..."
python3 Compiler/stage7_extract_wid_pc.py \
    firmware_final.out \
    --output build/wid_pc_map.json \
    --objdump msp430-elf-objdump

# 阶段3: 重新生成恢复逻辑
echo "  重新生成恢复逻辑（使用正确PC）..."
python3 Compiler/stage11_generate_restore_with_array.py \
    --pc-ranges build/pc_ranges.json \
    --wid-pc-map build/wid_pc_map.json \
    --fram-slots build/fram_slots.json \
    --function-info build/function_info.json \
    --output build/asap_restore.s \
    --format asm

# 阶段4: 重新编译恢复逻辑
echo "  重新编译恢复逻辑..."
msp430-elf-gcc -mmcu="$MCU" $CFLAGS -c build/asap_restore.s -o build/asap_restore.o

# 阶段5: 最终链接
echo "  最终链接..."
msp430-elf-gcc -mmcu="$MCU" $CFLAGS -c Runtime/bootloader_with_restore.s -o build/bootloader_restore.o
msp430-elf-gcc -mmcu="$MCU" $CFLAGS -c build/A_redirected.s -o build/main.o

msp430-elf-gcc -mmcu="$MCU" $CFLAGS \
    -nostartfiles \
    -T Runtime/src/port/msp430/msp430fr5969_bootloader.ld \
    -Wl,--just-symbols=build/fram_symbols.ld \
    -o firmware_final.out \
    build/bootloader_restore.o \
    build/main.o \
    build/asap_restore.o \
    build/asap_hashtable.o \
    build/func_sp_symbols.o \
    -lgcc

echo ""
echo "========================================"
echo "✅ 编译完成！"
echo "========================================"
echo ""
echo "最终固件: firmware_final.out"
ls -lh firmware_final.out
echo ""
echo "固件信息："
msp430-elf-size firmware_final.out
echo ""
echo "包含的函数："
msp430-elf-nm firmware_final.out | grep -E "(asap_hashtable|asap_restore)" | head -10
echo ""

