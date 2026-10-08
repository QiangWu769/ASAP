#!/bin/bash
# SHA 三版本编译脚本
# 编译: 纯净版 / ASAP无定时器版 / ASAP定时器40k版
# 用法: ./compile_sha_all.sh

set -e  # 出错即停

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "SHA 三版本编译脚本"
echo "=========================================="

#==============================================================================
# 版本1: 纯净版（无ASAP，无定时器）
#==============================================================================
echo ""
echo "[版本1] 编译纯净版 (sha_pure)..."
echo "----------------------------------------"

msp430-elf-gcc -mmcu=msp430fr5969 -O0 -DTIMER=0 \
    -o sha_pure.out \
    Benchmarks/sha/main_sha.c \
    -I Benchmarks/sha

msp430-elf-objcopy -O ihex sha_pure.out sha_pure.hex

echo "✓ sha_pure.out / sha_pure.hex 完成"

#==============================================================================
# 版本2: ASAP无定时器版
#==============================================================================
echo ""
echo "[版本2] 编译ASAP无定时器版 (sha_asap_no_timer)..."
echo "----------------------------------------"

# 清理并创建 build 目录
rm -rf build
mkdir -p build

# Step 1: 编译 C 到汇编（TIMER=0）
echo "  [Step 1] 编译 C 到汇编..."
msp430-elf-gcc -mmcu=msp430fr5969 -O0 -DTIMER=0 -S -o build/A.s Benchmarks/sha/main_sha.c -I Benchmarks/sha

# Step 2: 分析函数
echo "  [Step 2] 分析函数..."
python3 Compiler/stage2_analyze_functions.py build/A.s --output build/function_info.json

# Step 2.5: 分析调用关系
echo "  [Step 2.5] 分析调用关系..."
python3 Compiler/stage2_5_analyze_calls.py build/A.s --functions build/function_info.json --output build/call_info.json

# Step 2b: 幂等化处理
echo "  [Step 2b] 幂等化处理..."
python3 Compiler/stage2b_make_idempotent.py build/A.s --output build/A_idempotent.s
cp build/A_idempotent.s build/A_sym.s

# Step 3: 分析写操作
echo "  [Step 3] 分析写操作..."
python3 Compiler/stage3_analyze_writes_array.py build/A_sym.s --functions build/function_info.json --output build/candidates.json

# Step 3b: 检测循环数组
echo "  [Step 3b] 检测循环数组..."
python3 Compiler/stage3b_detect_loop_array.py --asm build/A_sym.s --candidates build/candidates.json --output build/loop_arrays.json

# Step 4: 分配 FRAM 槽位
echo "  [Step 4] 分配 FRAM 槽位..."
python3 Compiler/stage4_allocate_fram_array.py build/candidates.json --output build/fram_slots.json --linker build/fram_symbols.ld

# Step 5: 注入备份逻辑
echo "  [Step 5] 注入备份逻辑..."
python3 Compiler/stage5_inject_backup_array.py build/A_sym.s --candidates build/candidates.json --fram-slots build/fram_slots.json --output build/A_instrumented.s --loop-arrays build/loop_arrays.json

# Step 5b: 注入 main 恢复检查
echo "  [Step 5b] 注入 main 恢复检查..."
python3 Compiler/stage5b_inject_main_restore.py build/A_instrumented.s

# Step 5c: 注入返回地址备份
echo "  [Step 5c] 注入返回地址备份..."
python3 Compiler/stage5c_inject_return_addr_backup.py build/A_instrumented.s --functions build/function_info.json --fram-slots build/fram_slots.json

# Step 5-其他: 生成调用图和重定向
echo "  [Step 5-其他] 生成调用图和重定向..."
python3 Compiler/stage9b_build_call_graph.py --asm build/A_instrumented.s --function-info build/function_info.json --candidates build/candidates.json --output build/call_graph.json
python3 Compiler/stage5d_redirect_indirect_slots.py --input build/A_instrumented.s --output build/A_redirected.s --call-graph build/call_graph.json --fram-slots build/fram_slots.json --redirect-map build/redirect_map.json --loop-arrays build/loop_arrays.json
cp build/A_redirected.s build/A_array_mirror.s
python3 Compiler/stage5g_reorder_nonidempotent.py --input build/A_array_mirror.s --output build/A_redirected.s

# 创建临时 stub
echo "  [临时] 创建 stub..."
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
echo "  [Step 7] 编译汇编并提取 WID-PC..."
msp430-elf-gcc -mmcu=msp430fr5969 -c -o build/A_redirected.o build/A_redirected.s
msp430-elf-gcc -mmcu=msp430fr5969 -O0 -o build/firmware_temp.elf build/A_redirected.o build/asap_restore_stub.o \
    -T Runtime/src/port/msp430/msp430fr5969.ld \
    -T build/fram_symbols.ld \
    -T build/func_sp_symbols.ld \
    -Wl,--gc-sections 2>/dev/null || true
python3 Compiler/stage7_extract_wid_pc.py build/firmware_temp.elf --output build/wid_pc_map.json

# Step 8-10: 分析读写、生命周期、合并 PC 范围
echo "  [Step 8-10] 分析读写、生命周期、合并 PC 范围..."
python3 Compiler/stage8_analyze_reads_writes_v2.py build/firmware_temp.elf --output build/reads_writes.json
python3 Compiler/stage9_analyze_lifetime.py --reads-writes build/reads_writes.json --wid-pc-map build/wid_pc_map.json --candidates build/candidates.json --output build/lifetime_data.json
python3 Compiler/stage10_merge_pc_ranges.py --wid-pc-map build/wid_pc_map.json --lifetime build/lifetime_data.json --fram-slots build/fram_slots.json --call-graph build/call_graph.json --candidates build/candidates.json --redirect-map build/redirect_map.json --output build/pc_ranges.json

# Step 11: 生成恢复代码
echo "  [Step 11] 生成恢复代码..."
python3 Compiler/stage11_generate_restore_dedup.py --pc-ranges build/pc_ranges.json --wid-pc-map build/wid_pc_map.json --fram-slots build/fram_slots.json --function-info build/function_info.json --candidates build/candidates.json --output build/asap_restore.s --loop-arrays build/loop_arrays.json

# Step 12: 最终编译和链接
echo "  [Step 12] 最终编译和链接..."
msp430-elf-as -mmcu=msp430fr5969 -o build/asap_restore.o build/asap_restore.s
msp430-elf-as -mmcu=msp430fr5969 -o build/func_sp_symbols.o build/func_sp_symbols.s
cp Runtime/bootloader_with_restore.s build/
msp430-elf-as -mmcu=msp430fr5969 -o build/bootloader.o build/bootloader_with_restore.s

msp430-elf-gcc -mmcu=msp430fr5969 -nostartfiles -o sha_asap_no_timer.out \
    build/A_redirected.o build/asap_restore.o build/func_sp_symbols.o build/bootloader.o \
    -T Runtime/src/port/msp430/msp430fr5969.ld \
    -T build/fram_symbols.ld \
    -T build/func_sp_symbols.ld \
    -Wl,--gc-sections

msp430-elf-objcopy -O ihex sha_asap_no_timer.out sha_asap_no_timer.hex

# 保存 build 目录
cp -r build build_sha_no_timer

WID_COUNT=$(python3 -c "import json; print(len(json.load(open('build/candidates.json'))))")
echo "✓ sha_asap_no_timer.out / sha_asap_no_timer.hex 完成 (WID数量: $WID_COUNT)"

#==============================================================================
# 版本3: ASAP定时器40k版
#==============================================================================
echo ""
echo "[版本3] 编译ASAP定时器40k版 (sha_asap_timer_40k)..."
echo "----------------------------------------"

# 清理并创建 build 目录
rm -rf build
mkdir -p build

# Step 1: 编译 C 到汇编（TIMER=1）
echo "  [Step 1] 编译 C 到汇编..."
msp430-elf-gcc -mmcu=msp430fr5969 -O0 -DTIMER=1 -DTIMER_VALUE=40000 -S -o build/A.s Benchmarks/sha/main_sha.c -I Benchmarks/sha

# Step 2: 分析函数
echo "  [Step 2] 分析函数..."
python3 Compiler/stage2_analyze_functions.py build/A.s --output build/function_info.json

# Step 2.5: 分析调用关系
echo "  [Step 2.5] 分析调用关系..."
python3 Compiler/stage2_5_analyze_calls.py build/A.s --functions build/function_info.json --output build/call_info.json

# Step 2b: 幂等化处理
echo "  [Step 2b] 幂等化处理..."
python3 Compiler/stage2b_make_idempotent.py build/A.s --output build/A_idempotent.s
cp build/A_idempotent.s build/A_sym.s

# Step 3: 分析写操作
echo "  [Step 3] 分析写操作..."
python3 Compiler/stage3_analyze_writes_array.py build/A_sym.s --functions build/function_info.json --output build/candidates.json

# Step 3b: 检测循环数组
echo "  [Step 3b] 检测循环数组..."
python3 Compiler/stage3b_detect_loop_array.py --asm build/A_sym.s --candidates build/candidates.json --output build/loop_arrays.json

# Step 4: 分配 FRAM 槽位
echo "  [Step 4] 分配 FRAM 槽位..."
python3 Compiler/stage4_allocate_fram_array.py build/candidates.json --output build/fram_slots.json --linker build/fram_symbols.ld

# Step 5: 注入备份逻辑
echo "  [Step 5] 注入备份逻辑..."
python3 Compiler/stage5_inject_backup_array.py build/A_sym.s --candidates build/candidates.json --fram-slots build/fram_slots.json --output build/A_instrumented.s --loop-arrays build/loop_arrays.json

# Step 5b: 注入 main 恢复检查
echo "  [Step 5b] 注入 main 恢复检查..."
python3 Compiler/stage5b_inject_main_restore.py build/A_instrumented.s

# Step 5c: 注入返回地址备份
echo "  [Step 5c] 注入返回地址备份..."
python3 Compiler/stage5c_inject_return_addr_backup.py build/A_instrumented.s --functions build/function_info.json --fram-slots build/fram_slots.json

# Step 5-其他: 生成调用图和重定向
echo "  [Step 5-其他] 生成调用图和重定向..."
python3 Compiler/stage9b_build_call_graph.py --asm build/A_instrumented.s --function-info build/function_info.json --candidates build/candidates.json --output build/call_graph.json
python3 Compiler/stage5d_redirect_indirect_slots.py --input build/A_instrumented.s --output build/A_redirected.s --call-graph build/call_graph.json --fram-slots build/fram_slots.json --redirect-map build/redirect_map.json --loop-arrays build/loop_arrays.json
cp build/A_redirected.s build/A_array_mirror.s
python3 Compiler/stage5g_reorder_nonidempotent.py --input build/A_array_mirror.s --output build/A_redirected.s

# 创建临时 stub
echo "  [临时] 创建 stub..."
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
echo "  [Step 7] 编译汇编并提取 WID-PC..."
msp430-elf-gcc -mmcu=msp430fr5969 -c -o build/A_redirected.o build/A_redirected.s
msp430-elf-gcc -mmcu=msp430fr5969 -O0 -o build/firmware_temp.elf build/A_redirected.o build/asap_restore_stub.o \
    -T Runtime/src/port/msp430/msp430fr5969.ld \
    -T build/fram_symbols.ld \
    -T build/func_sp_symbols.ld \
    -Wl,--gc-sections 2>/dev/null || true
python3 Compiler/stage7_extract_wid_pc.py build/firmware_temp.elf --output build/wid_pc_map.json

# Step 8-10: 分析读写、生命周期、合并 PC 范围
echo "  [Step 8-10] 分析读写、生命周期、合并 PC 范围..."
python3 Compiler/stage8_analyze_reads_writes_v2.py build/firmware_temp.elf --output build/reads_writes.json
python3 Compiler/stage9_analyze_lifetime.py --reads-writes build/reads_writes.json --wid-pc-map build/wid_pc_map.json --candidates build/candidates.json --output build/lifetime_data.json
python3 Compiler/stage10_merge_pc_ranges.py --wid-pc-map build/wid_pc_map.json --lifetime build/lifetime_data.json --fram-slots build/fram_slots.json --call-graph build/call_graph.json --candidates build/candidates.json --redirect-map build/redirect_map.json --output build/pc_ranges.json

# Step 11: 生成恢复代码
echo "  [Step 11] 生成恢复代码..."
python3 Compiler/stage11_generate_restore_dedup.py --pc-ranges build/pc_ranges.json --wid-pc-map build/wid_pc_map.json --fram-slots build/fram_slots.json --function-info build/function_info.json --candidates build/candidates.json --output build/asap_restore.s --loop-arrays build/loop_arrays.json

# Step 12: 最终编译和链接
echo "  [Step 12] 最终编译和链接..."
msp430-elf-as -mmcu=msp430fr5969 -o build/asap_restore.o build/asap_restore.s
msp430-elf-as -mmcu=msp430fr5969 -o build/func_sp_symbols.o build/func_sp_symbols.s
cp Runtime/bootloader_with_restore.s build/
msp430-elf-as -mmcu=msp430fr5969 -o build/bootloader.o build/bootloader_with_restore.s

msp430-elf-gcc -mmcu=msp430fr5969 -nostartfiles -o sha_asap_timer_40k.out \
    build/A_redirected.o build/asap_restore.o build/func_sp_symbols.o build/bootloader.o \
    -T Runtime/src/port/msp430/msp430fr5969.ld \
    -T build/fram_symbols.ld \
    -T build/func_sp_symbols.ld \
    -Wl,--gc-sections

msp430-elf-objcopy -O ihex sha_asap_timer_40k.out sha_asap_timer_40k.hex

# 保存 build 目录
cp -r build build_sha_timer_40k

WID_COUNT=$(python3 -c "import json; print(len(json.load(open('build/candidates.json'))))")
echo "✓ sha_asap_timer_40k.out / sha_asap_timer_40k.hex 完成 (WID数量: $WID_COUNT)"

#==============================================================================
# 完成总结
#==============================================================================
echo ""
echo "=========================================="
echo "SHA 三版本编译完成！"
echo "=========================================="
echo ""
echo "生成的文件:"
echo "  1. sha_pure.out / sha_pure.hex         (纯净版，无ASAP)"
echo "  2. sha_asap_no_timer.out / .hex        (ASAP无定时器)"
echo "  3. sha_asap_timer_40k.out / .hex       (ASAP定时器40k)"
echo ""
echo "文件大小:"
ls -la sha_pure.out sha_asap_no_timer.out sha_asap_timer_40k.out 2>/dev/null | awk '{print "  " $NF ": " $5 " bytes"}'
echo ""
echo "Build 目录已保存到:"
echo "  - build_sha_no_timer/"
echo "  - build_sha_timer_40k/"
echo "=========================================="

