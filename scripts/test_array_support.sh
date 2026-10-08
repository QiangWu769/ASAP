#!/bin/bash
# ============================================================
# 测试动态数组支持功能
# ============================================================

set -e  # 遇到错误立即退出

WORKDIR="/Users/wyf/Desktop/ASAP_right_副本/backups/complete_backup_before_no_sp_20251105_204648 21"
cd "$WORKDIR"

echo "========================================"
echo "测试动态数组支持功能"
echo "========================================"
echo ""

# 清理之前的构建
echo "[1/7] 清理构建目录..."
rm -rf build/*
mkdir -p build

# Stage 1: 编译到汇编
echo "[2/7] Stage 1: 编译 cf/main_cf_plain.c 到汇编..."
python3 Compiler/stage1_compile_to_asm.py \
    Benchmarks/cf/main_cf_plain.c \
    --output build/A_sym.s \
    --compiler msp430-elf-gcc \
    --mcu msp430fr5969 \
    --cflags "-O0 -g -DPRINTF=printf"

# Stage 2b: 幂等化
echo "[3/7] Stage 2b: 幂等化转换..."
python3 Compiler/stage2b_make_idempotent.py \
    build/A_sym.s \
    --output build/A_idempotent.s

# Stage 2: 分析函数
echo "[4/7] Stage 2: 分析函数信息..."
python3 Compiler/stage2_analyze_functions.py \
    build/A_idempotent.s \
    --output build/function_info.json

# Stage 3 with array: 识别关键写 + 动态数组
echo "[5/7] Stage 3 (增强): 识别关键写 + 动态数组..."
python3 Compiler/stage3_analyze_writes_with_array.py \
    build/A_idempotent.s \
    --functions build/function_info.json \
    --config Compiler/bc_core_config.json \
    --output build/candidates.json

# 检查是否识别到动态数组
echo ""
echo ">>> 检查动态数组识别结果:"
python3 -c "
import json
with open('build/candidates.json') as f:
    candidates = json.load(f)

array_wids = [wid for wid, info in candidates.items() if info.get('is_dynamic_array')]
print(f'  识别到 {len(array_wids)} 个动态数组WID: {array_wids[:10]}')

if array_wids:
    example = candidates[array_wids[0]]
    print(f'  示例: {array_wids[0]} -> {example[\"array_group_id\"]}')
else:
    print('  ⚠️ 未识别到动态数组！')
"

# Stage 4 with array: 分配FRAM + 哈希表
echo ""
echo "[6/7] Stage 4 (增强): 分配FRAM槽位 + 哈希表..."
python3 Compiler/stage4_allocate_fram_with_array.py \
    build/candidates.json \
    --output build/fram_slots.json \
    --linker build/fram_symbols.ld \
    --fram-base 0x6400 \
    --array-base 0x6000

# 检查哈希表分配
echo ""
echo ">>> 检查哈希表分配结果:"
python3 -c "
import json
with open('build/fram_slots.json') as f:
    fram_slots = json.load(f)

array_tables = fram_slots.get('array_hashtables', {})
print(f'  分配了 {len(array_tables)} 个哈希表:')
for array_id, info in array_tables.items():
    print(f'    [{array_id}]')
    print(f'      哈希表: {info[\"hashtable_symbol\"]} @ {info[\"hashtable_addr\"]}')
    print(f'      WID数: {len(info[\"wids\"])}')
"

# Stage 5 with array: 插桩备份 + 哈希表备份
echo ""
echo "[7/7] Stage 5 (增强): 插桩备份 + 哈希表备份..."
python3 Compiler/stage5_inject_backup_with_array.py \
    build/A_idempotent.s \
    --candidates build/candidates.json \
    --fram-slots build/fram_slots.json \
    --output build/A_instrumented.s

echo ""
echo "========================================"
echo "✅ 测试完成！"
echo "========================================"
echo ""
echo "生成的文件:"
echo "  - build/candidates.json (含动态数组标记)"
echo "  - build/fram_slots.json (含哈希表分配)"
echo "  - build/A_instrumented.s (含哈希表备份插桩)"
echo ""
echo "下一步:"
echo "  1. 检查 build/A_instrumented.s 中的哈希表插桩代码"
echo "  2. 继续运行完整编译流程（stage6-13）"
echo "  3. 验证恢复逻辑正确性"
echo ""









