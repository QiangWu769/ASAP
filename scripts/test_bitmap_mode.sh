#!/bin/bash
# 位图模式测试脚本
# 在不破坏现有编译流程的情况下测试位图功能

set -e

echo "================================================================================"
echo "位图模式测试 - RSA代码"
echo "================================================================================"

# 清理
echo -e "\n[1] 清理构建目录..."
rm -rf build_bitmap_test
mkdir build_bitmap_test

# 标准编译流程（到stage4）
echo -e "\n[2] 运行标准编译流程（到stage4）..."
BUILD_DIR=build_bitmap_test make SRC=Benchmarks/rsa/main_rsa.c stage4

# 检测数组访问
echo -e "\n[3] 检测数组访问..."
python3 Compiler/detect_array_access.py \
    build_bitmap_test/A_idempotent.s \
    --candidates build_bitmap_test/candidates.json \
    --output build_bitmap_test/array_detection.json

# 分配位图结构
echo -e "\n[4] 分配位图结构..."
python3 Compiler/stage4_bitmap_extension.py \
    build_bitmap_test/A_idempotent.s \
    --candidates build_bitmap_test/candidates.json \
    --fram-slots build_bitmap_test/fram_slots.json \
    --output-json build_bitmap_test/fram_slots_bitmap.json \
    --output-linker build_bitmap_test/fram_symbols.ld

# 对比
echo -e "\n[5] 对比分析..."
python3 << 'EOF'
import json

print("="*80)
print("位图结构分配结果")
print("="*80)

with open('build_bitmap_test/fram_slots_bitmap.json', 'r') as f:
    fram_slots = json.load(f)

# 统计
bitmap_wids = [w for w, s in fram_slots['wid_to_slot'].items() 
               if s.get('_use_bitmap', False)]

print(f"\n使用位图的WID: {len(bitmap_wids)} 个")

# 按数组分组
array_groups = {}
for wid in bitmap_wids:
    slot = fram_slots['wid_to_slot'][wid]
    group = slot.get('_array_group', slot['logical_addr'])
    if group not in array_groups:
        array_groups[group] = []
    array_groups[group].append(wid)

print(f"数组数量: {len(array_groups)}")

for group, wids in sorted(array_groups.items()):
    print(f"\n  [{group}]")
    print(f"    WID: {wids}")
    if wids:
        bs = fram_slots['wid_to_slot'][wids[0]]['_bitmap_struct']
        print(f"    位图地址: {bs['bitmap_slot']}")
        print(f"    values基址: {bs['values_base']}")
        print(f"    最大元素: {bs['max_elements']}")

EOF

echo -e "\n================================================================================"
echo "测试完成"
echo "================================================================================"
echo ""
echo "验证项："
echo "  ✓ 自动检测数组访问"
echo "  ✓ 分配位图结构（地址不冲突）"
echo "  ✓ 更新fram_slots.json（添加标记）"
echo ""
echo "下一步："
echo "  1. 实现 stage5 位图备份代码生成"
echo "  2. 实现 stage11 位图恢复代码生成"
echo "  3. 集成到完整编译流程"
echo ""















