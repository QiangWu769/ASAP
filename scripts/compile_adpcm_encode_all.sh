#!/bin/bash
# ADPCM Encode ASAP 完整编译脚本（同时编译四个版本）
# 用法: ./compile_adpcm_encode_all.sh

set -e  # 出错即停

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║       ADPCM Encode ASAP 编译脚本（四个版本）                   ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# 函数：编译单个版本
compile_version() {
    local TIMER_FLAG=$1
    local TIMER_VALUE=$2
    local OUTPUT_NAME=$3
    
    echo "=========================================="
    echo "编译: $OUTPUT_NAME"
    echo "TIMER=$TIMER_FLAG, TIMER_VALUE=$TIMER_VALUE"
    echo "=========================================="
    
    # 清理并创建 build 目录
    rm -rf build
    mkdir -p build
    
    # Step 1: 编译 C 到汇编
    echo "[Step 1] 编译 C 到汇编..."
    if [ "$TIMER_FLAG" -eq 0 ]; then
        msp430-elf-gcc -mmcu=msp430fr5969 -O0 -g -DTIMER=0 -S -o build/A_sym.s Benchmarks/adpcm_encode/main_adpcm_encode.c -I Benchmarks/adpcm_encode
    else
        msp430-elf-gcc -mmcu=msp430fr5969 -O0 -g -DTIMER=1 -DTIMER_VALUE=$TIMER_VALUE -S -o build/A_sym.s Benchmarks/adpcm_encode/main_adpcm_encode.c -I Benchmarks/adpcm_encode
    fi
    
    # Step 2b: 幂等化处理
    echo "[Step 2b] 幂等化处理..."
    python3 Compiler/stage2b_make_idempotent.py build/A_sym.s --output build/A_idempotent.s
    cp build/A_idempotent.s build/A_sym.s
    
    # Step 2: 分析函数
    echo "[Step 2] 分析函数..."
    python3 Compiler/stage2_analyze_functions.py build/A_sym.s --output build/function_info.json
    
    # Step 2.5: 分析调用关系
    echo "[Step 2.5] 分析调用关系..."
    python3 Compiler/stage2_5_analyze_calls.py build/A_sym.s --functions build/function_info.json --output build/call_info.json
    
    # Step 3: 分析写操作
    echo "[Step 3] 分析写操作..."
    python3 Compiler/stage3_analyze_writes_array.py build/A_sym.s --functions build/function_info.json --call-info build/call_info.json --output build/candidates.json
    
    # Step 3b: 检测循环数组
    echo "[Step 3b] 检测循环数组..."
    python3 Compiler/stage3b_detect_loop_array.py --asm build/A_sym.s --candidates build/candidates.json --output build/loop_arrays.json
    
    # Step 4: 分配 FRAM 槽位
    echo "[Step 4] 分配 FRAM 槽位..."
    python3 Compiler/stage4_allocate_fram_array.py build/candidates.json --output build/fram_slots.json --linker build/fram_symbols.ld
    
    # Step 4b: 分配数组镜像空间
    echo "[Step 4b] 分配数组镜像空间..."
    python3 Compiler/stage4b_allocate_array_mirror.py --loop-arrays build/loop_arrays.json --fram-slots build/fram_slots.json --symbols-ld build/fram_symbols.ld
    
    # Step 5: 注入备份逻辑
    echo "[Step 5] 注入备份逻辑..."
    python3 Compiler/stage5_inject_backup_array.py build/A_sym.s --candidates build/candidates.json --fram-slots build/fram_slots.json --output build/A_instrumented.s --loop-arrays build/loop_arrays.json
    
    # 【新增】Step 5-opt: SP备份优化
    echo "[Step 5-opt] SP备份优化..."
    python3 Compiler/stage5_optimize_sp.py build/A_instrumented.s --output build/A_instrumented.s
    
    # Step 5g: 重排非幂等操作
    echo "[Step 5g] 重排非幂等操作..."
    python3 Compiler/stage5g_reorder_nonidempotent.py --input build/A_instrumented.s --output build/A_instrumented.s
    
    # Step 5b: 注入 main 恢复检查
    echo "[Step 5b] 注入 main 恢复检查..."
    python3 Compiler/stage5b_inject_main_restore.py build/A_instrumented.s
    
    # Step 5c: 注入返回地址备份
    echo "[Step 5c] 注入返回地址备份..."
    python3 Compiler/stage5c_inject_return_addr_backup.py build/A_instrumented.s --functions build/function_info.json --fram-slots build/fram_slots.json
    
    # Step 5-其他: 生成调用图和重定向
    echo "[Step 5d] 生成调用图和重定向..."
    python3 Compiler/stage9b_build_call_graph.py --asm build/A_instrumented.s --function-info build/function_info.json --candidates build/candidates.json --output build/call_graph.json
    python3 Compiler/stage5d_redirect_indirect_slots.py --input build/A_instrumented.s --output build/A_redirected.s --call-graph build/call_graph.json --fram-slots build/fram_slots.json --redirect-map build/redirect_map.json --loop-arrays build/loop_arrays.json
    
    # Step 5f: 备份下一条写入的寄存器
    echo "[Step 5f] 备份下一条写入的寄存器..."
    python3 Compiler/stage5f_backup_next_reg.py --input build/A_redirected.s --output build/A_redirected.s --fram-slots build/fram_slots.json --fram-symbols build/fram_symbols.ld --reg-map build/wid_reg_map.json
    
    # Step 6: 创建临时 stub 和编译
    echo "[Step 6] 编译临时固件..."
    cat > build/asap_restore_stub.s << 'EOF'
    .section .text
    .global _asap_restore
_asap_restore:
    RET
    .section .bss
    .global __asap_restored_flag
    .comm __asap_restored_flag, 2, 2
EOF
    msp430-elf-gcc -mmcu=msp430fr5969 -c -o build/A_redirected.o build/A_redirected.s
    msp430-elf-gcc -mmcu=msp430fr5969 -c -o build/asap_restore_stub.o build/asap_restore_stub.s
    msp430-elf-gcc -mmcu=msp430fr5969 -c -o build/func_sp_symbols.o build/func_sp_symbols.s
    msp430-elf-gcc -mmcu=msp430fr5969 -c -o build/bootloader.o Runtime/bootloader_with_restore.s
    
    msp430-elf-gcc -mmcu=msp430fr5969 -nostartfiles -o build/firmware_temp.elf \
        build/A_redirected.o build/asap_restore_stub.o build/func_sp_symbols.o build/bootloader.o \
        -T Runtime/src/port/msp430/msp430fr5969_bootloader.ld \
        -Wl,--just-symbols=build/fram_symbols.ld \
        -Wl,--gc-sections
    
    # Step 7: 提取 WID-PC
    echo "[Step 7] 提取 WID-PC..."
    python3 Compiler/stage7_extract_wid_pc.py build/firmware_temp.elf --output build/wid_pc_map.json
    
    # Step 8-10: 分析读写、生命周期、合并 PC 范围
    echo "[Step 8-10] 分析读写、生命周期、合并 PC 范围..."
    python3 Compiler/stage8_analyze_reads_writes_v2.py build/firmware_temp.elf --output build/reads_writes.json
    python3 Compiler/stage9_analyze_lifetime.py --reads-writes build/reads_writes.json --wid-pc-map build/wid_pc_map.json --candidates build/candidates.json --output build/lifetime_data.json
    python3 Compiler/stage10_merge_pc_ranges.py --wid-pc-map build/wid_pc_map.json --lifetime build/lifetime_data.json --fram-slots build/fram_slots.json --call-graph build/call_graph.json --candidates build/candidates.json --redirect-map build/redirect_map.json --output build/pc_ranges.json
    
    # Step 11: 生成恢复代码
    echo "[Step 11] 生成恢复代码..."
    python3 Compiler/stage11_generate_restore_dedup.py --pc-ranges build/pc_ranges.json --wid-pc-map build/wid_pc_map.json --fram-slots build/fram_slots.json --function-info build/function_info.json --wid-backup-regs build/wid_reg_map.json --output build/asap_restore.s
    
    # Step 11b: 注入数组恢复
    echo "[Step 11b] 注入数组恢复..."
    python3 Compiler/stage11b_array_restore.py --restore build/asap_restore.s --loop-arrays build/loop_arrays.json --fram-slots build/fram_slots.json
    
    # Step 12: 最终编译和链接（两遍链接）
    echo "[Step 12] 最终链接（第一遍）..."
    msp430-elf-gcc -mmcu=msp430fr5969 -c -o build/asap_restore.o build/asap_restore.s
    
    msp430-elf-gcc -mmcu=msp430fr5969 -nostartfiles -o build/firmware_pass1.elf \
        build/A_redirected.o build/asap_restore.o build/func_sp_symbols.o build/bootloader.o \
        -T Runtime/src/port/msp430/msp430fr5969_bootloader.ld \
        -Wl,--just-symbols=build/fram_symbols.ld \
        -Wl,--gc-sections
    
    # 从第一遍链接结果重新提取WID-PC映射
    echo "[Step 12b] 重新提取WID-PC映射..."
    python3 Compiler/stage7_extract_wid_pc.py build/firmware_pass1.elf --output build/wid_pc_map_final.json
    
    # 用正确的PC地址重新生成asap_restore.s
    echo "[Step 12c] 用正确地址重新生成恢复代码..."
    python3 Compiler/stage11_generate_restore_dedup.py --pc-ranges build/pc_ranges.json --wid-pc-map build/wid_pc_map_final.json --fram-slots build/fram_slots.json --function-info build/function_info.json --wid-backup-regs build/wid_reg_map.json --output build/asap_restore.s
    python3 Compiler/stage11b_array_restore.py --restore build/asap_restore.s --loop-arrays build/loop_arrays.json --fram-slots build/fram_slots.json
    
    # 第二遍链接
    echo "[Step 12d] 最终链接（第二遍）..."
    msp430-elf-gcc -mmcu=msp430fr5969 -c -o build/asap_restore.o build/asap_restore.s
    msp430-elf-gcc -mmcu=msp430fr5969 -nostartfiles -o ${OUTPUT_NAME}.out \
        build/A_redirected.o build/asap_restore.o build/func_sp_symbols.o build/bootloader.o \
        -T Runtime/src/port/msp430/msp430fr5969_bootloader.ld \
        -Wl,--just-symbols=build/fram_symbols.ld \
        -Wl,--gc-sections
    
    msp430-elf-objcopy -O ihex ${OUTPUT_NAME}.out ${OUTPUT_NAME}.hex
    
    # 复制到 Benchmarks 目录
    cp ${OUTPUT_NAME}.out Benchmarks/adpcm_encode/
    cp ${OUTPUT_NAME}.hex Benchmarks/adpcm_encode/
    
    echo "✓ ${OUTPUT_NAME} 编译完成"
    echo ""
}

# 编译无定时器版本
compile_version 0 0 "adpcm_encode_asap_no_timer"

# 编译有定时器版本 (10000)
compile_version 1 10000 "adpcm_encode_asap_timer_10k"

# 编译有定时器版本 (20000)
compile_version 1 20000 "adpcm_encode_asap_timer_20k"

# 编译有定时器版本 (40000)
compile_version 1 40000 "adpcm_encode_asap_timer_40k"

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    编译结果汇总                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "生成的固件文件:"
ls -lh adpcm_encode_asap_*.out
echo ""
echo "代码大小:"
msp430-elf-size adpcm_encode_asap_no_timer.out adpcm_encode_asap_timer_10k.out adpcm_encode_asap_timer_20k.out adpcm_encode_asap_timer_40k.out
echo ""
echo "文件已复制到 Benchmarks/adpcm_encode/"
ls -lh Benchmarks/adpcm_encode/adpcm_encode_asap_*.out
echo ""
echo "✅ 全部编译完成！"




















