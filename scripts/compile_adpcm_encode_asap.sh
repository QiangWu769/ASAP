#!/bin/bash
# ADPCM Encode ASAP 完整编译脚本
# 用法: ./compile_adpcm_encode_asap.sh [timer_value]
# timer_value: 定时器周期（默认40000，约5ms @ 8MHz）。设为0禁用定时器。

set -e  # 出错即停

TIMER_VALUE=${1:-40000}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "ADPCM Encode ASAP 编译脚本"
echo "定时器周期: $TIMER_VALUE"
echo "=========================================="

# 清理并创建 build 目录
rm -rf build
mkdir -p build

# Step 1: 编译 C 到汇编
echo "[Step 1] 编译 C 到汇编..."
if [ "$TIMER_VALUE" -eq 0 ]; then
    msp430-elf-gcc -mmcu=msp430fr5969 -O0 -DTIMER=0 -S -o build/A.s Benchmarks/adpcm_encode/main_adpcm_encode.c -I Benchmarks/adpcm_encode
else
    msp430-elf-gcc -mmcu=msp430fr5969 -O0 -DTIMER=1 -DTIMER_VALUE=$TIMER_VALUE -S -o build/A.s Benchmarks/adpcm_encode/main_adpcm_encode.c -I Benchmarks/adpcm_encode
fi

# Step 2: 分析函数
echo "[Step 2] 分析函数..."
python3 Compiler/stage2_analyze_functions.py build/A.s --output build/function_info.json

# Step 2.5: 分析调用关系
echo "[Step 2.5] 分析调用关系..."
python3 Compiler/stage2_5_analyze_calls.py build/A.s --functions build/function_info.json --output build/call_info.json

# Step 2b: 幂等化处理
echo "[Step 2b] 幂等化处理..."
python3 Compiler/stage2b_make_idempotent.py build/A.s --output build/A_idempotent.s
cp build/A_idempotent.s build/A_sym.s

# Step 3: 分析写操作
echo "[Step 3] 分析写操作..."
python3 Compiler/stage3_analyze_writes_array.py build/A_sym.s --functions build/function_info.json --output build/candidates.json

# Step 3b: 检测循环数组
echo "[Step 3b] 检测循环数组..."
python3 Compiler/stage3b_detect_loop_array.py --asm build/A_sym.s --candidates build/candidates.json --output build/loop_arrays.json

# Step 4: 分配 FRAM 槽位
echo "[Step 4] 分配 FRAM 槽位..."
python3 Compiler/stage4_allocate_fram_array.py build/candidates.json --output build/fram_slots.json --linker build/fram_symbols.ld

# Step 5: 注入备份逻辑
echo "[Step 5] 注入备份逻辑..."
python3 Compiler/stage5_inject_backup_array.py build/A_sym.s --candidates build/candidates.json --fram-slots build/fram_slots.json --output build/A_instrumented.s --loop-arrays build/loop_arrays.json

# Step 5b: 注入 main 恢复检查
echo "[Step 5b] 注入 main 恢复检查..."
python3 Compiler/stage5b_inject_main_restore.py build/A_instrumented.s

# Step 5c: 注入返回地址备份
echo "[Step 5c] 注入返回地址备份..."
python3 Compiler/stage5c_inject_return_addr_backup.py build/A_instrumented.s --functions build/function_info.json --fram-slots build/fram_slots.json

# Step 5-其他: 生成调用图和重定向
echo "[Step 5-其他] 生成调用图和重定向..."
python3 Compiler/stage9b_build_call_graph.py --asm build/A_instrumented.s --function-info build/function_info.json --candidates build/candidates.json --output build/call_graph.json
python3 Compiler/stage5d_redirect_indirect_slots.py --input build/A_instrumented.s --output build/A_redirected.s --call-graph build/call_graph.json --fram-slots build/fram_slots.json --redirect-map build/redirect_map.json --loop-arrays build/loop_arrays.json
cp build/A_redirected.s build/A_array_mirror.s
python3 Compiler/stage5g_reorder_nonidempotent.py --input build/A_array_mirror.s --output build/A_redirected.s

# 创建临时 stub（用于提取 WID-PC）
echo "[临时] 创建 stub..."
cat > build/asap_restore_stub.s << 'EOF'
    .section .text
    .global _asap_restore
_asap_restore:
    RET
    .section .bss
    .global __asap_restored_flag
    .comm __asap_restored_flag, 2, 2
EOF
msp430-elf-as -mmcu=msp430fr5969 -o build/asap_restore_stub.o build/asap_restore_stub.s

# Step 7: 编译汇编并提取 WID-PC
echo "[Step 7] 编译汇编并提取 WID-PC..."
msp430-elf-gcc -mmcu=msp430fr5969 -c -o build/A_redirected.o build/A_redirected.s
msp430-elf-gcc -mmcu=msp430fr5969 -Os -o build/firmware_temp.elf build/A_redirected.o build/asap_restore_stub.o \
    -T Runtime/src/port/msp430/msp430fr5969.ld \
    -T build/fram_symbols.ld \
    -T build/func_sp_symbols.ld \
    -Wl,--gc-sections 2>/dev/null || true
python3 Compiler/stage7_extract_wid_pc.py build/firmware_temp.elf --output build/wid_pc_map.json

# Step 8-10: 分析读写、生命周期、合并 PC 范围
echo "[Step 8-10] 分析读写、生命周期、合并 PC 范围..."
python3 Compiler/stage8_analyze_reads_writes_v2.py build/firmware_temp.elf --output build/reads_writes.json
python3 Compiler/stage9_analyze_lifetime.py --reads-writes build/reads_writes.json --wid-pc-map build/wid_pc_map.json --candidates build/candidates.json --output build/lifetime_data.json
python3 Compiler/stage10_merge_pc_ranges.py --wid-pc-map build/wid_pc_map.json --lifetime build/lifetime_data.json --fram-slots build/fram_slots.json --call-graph build/call_graph.json --candidates build/candidates.json --redirect-map build/redirect_map.json --output build/pc_ranges.json

# Step 11: 生成恢复代码
echo "[Step 11] 生成恢复代码..."
python3 Compiler/stage11_generate_restore_dedup.py --pc-ranges build/pc_ranges.json --wid-pc-map build/wid_pc_map.json --fram-slots build/fram_slots.json --function-info build/function_info.json --candidates build/candidates.json --output build/asap_restore.s --loop-arrays build/loop_arrays.json

# Step 12: 最终编译和链接（两遍链接解决地址偏移问题）
echo "[Step 12] 最终编译和链接（第一遍）..."
msp430-elf-as -mmcu=msp430fr5969 -o build/asap_restore.o build/asap_restore.s
msp430-elf-as -mmcu=msp430fr5969 -o build/func_sp_symbols.o build/func_sp_symbols.s
cp Runtime/bootloader_with_restore.s build/
msp430-elf-as -mmcu=msp430fr5969 -o build/bootloader.o build/bootloader_with_restore.s

# 确定输出文件名
if [ "$TIMER_VALUE" -eq 0 ]; then
    OUTPUT_NAME="adpcm_encode_asap_pure"
else
    OUTPUT_NAME="adpcm_encode_asap_timer"
fi

# 第一遍链接（获取正确的WID地址）
msp430-elf-gcc -mmcu=msp430fr5969 -nostartfiles -o build/firmware_pass1.elf \
    build/A_redirected.o build/asap_restore.o build/func_sp_symbols.o build/bootloader.o \
    -T Runtime/src/port/msp430/msp430fr5969.ld \
    -T build/fram_symbols.ld \
    -T build/func_sp_symbols.ld \
    -Wl,--gc-sections

# 从第一遍链接结果重新提取WID-PC映射
echo "[Step 12b] 重新提取WID-PC映射..."
python3 Compiler/stage7_extract_wid_pc.py build/firmware_pass1.elf --output build/wid_pc_map_final.json

# 用正确的PC地址重新生成asap_restore.s
echo "[Step 12c] 用正确地址重新生成恢复代码..."
python3 Compiler/stage11_generate_restore_dedup.py --pc-ranges build/pc_ranges.json --wid-pc-map build/wid_pc_map_final.json --fram-slots build/fram_slots.json --function-info build/function_info.json --candidates build/candidates.json --output build/asap_restore.s --loop-arrays build/loop_arrays.json

# 第二遍链接（使用正确的PC地址）
echo "[Step 12d] 最终链接（第二遍）..."
msp430-elf-as -mmcu=msp430fr5969 -o build/asap_restore.o build/asap_restore.s
msp430-elf-gcc -mmcu=msp430fr5969 -nostartfiles -o ${OUTPUT_NAME}.out \
    build/A_redirected.o build/asap_restore.o build/func_sp_symbols.o build/bootloader.o \
    -T Runtime/src/port/msp430/msp430fr5969.ld \
    -T build/fram_symbols.ld \
    -T build/func_sp_symbols.ld \
    -Wl,--gc-sections

msp430-elf-objcopy -O ihex ${OUTPUT_NAME}.out ${OUTPUT_NAME}.hex

echo ""
echo "=========================================="
echo "编译完成！"
echo "输出文件: ${OUTPUT_NAME}.out, ${OUTPUT_NAME}.hex"
echo ""
WID_COUNT=$(python3 -c "import json; print(len(json.load(open('build/candidates.json'))))")
echo "WID 数量: $WID_COUNT"
echo ""
echo "Reset vector:"
msp430-elf-objdump -s ${OUTPUT_NAME}.out | grep "fffe" | head -1
msp430-elf-nm ${OUTPUT_NAME}.out | grep bootloader_entry
echo "=========================================="























