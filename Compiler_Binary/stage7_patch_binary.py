#!/usr/bin/env python3
"""
Stage 7: 在机器码中插入备份补丁 ★核心★
这是纯机器码方案的核心：直接在二进制层面插入机器码字节

输入: text_section.bin (原始机器码), backup_patches.json
输出: text_instrumented.bin (插桩后的机器码)

关键操作:
  1. 在二进制文件的指定offset插入字节
  2. 修正所有跳转/调用指令的目标地址
  3. 构建地址重定位映射

注意: 这里完全是字节级别的操作，没有涉及汇编或重新编译
"""

import argparse
import json
import sys
from pathlib import Path


def insert_patches_into_binary(original_binary, patches):
    """
    在机器码二进制中插入补丁
    
    策略: 从后向前插入，避免前面的偏移影响后面的插入位置
    
    Args:
        original_binary: bytes - 原始.text段机器码
        patches: dict - {WID: {insert_offset, machine_code, size}}
    
    Returns:
        bytes - 插桩后的机器码
        dict - 地址重定位映射 {old_offset: new_offset}
    """
    # 转换为可变字节数组
    binary = bytearray(original_binary)
    
    # 按插入位置从大到小排序（从后向前插入）
    sorted_patches = sorted(patches.items(),
                           key=lambda x: x[1]['insert_offset'],
                           reverse=True)
    
    # 记录每次插入
    insertions = []  # [(offset, size), ...]
    
    print(f"\n  插入补丁 (从后向前):")
    for wid, patch in sorted_patches:
        offset = patch['insert_offset']
        machine_code = bytes(patch['machine_code'])
        size = len(machine_code)
        
        # 在offset位置插入字节
        binary[offset:offset] = machine_code
        
        insertions.append((offset, size))
        
        print(f"    {wid}: 在offset {offset} 插入 {size} 字节")
    
    # 构建地址重定位映射
    relocation_map = build_relocation_map(len(original_binary), insertions)
    
    return bytes(binary), relocation_map


def build_relocation_map(original_size, insertions):
    """
    构建地址重定位映射
    
    在每个插入点之后的所有地址都需要调整
    
    Args:
        original_size: 原始二进制大小
        insertions: [(offset, size), ...] 按offset排序
    
    Returns:
        dict: {old_offset: new_offset}
    """
    relocation_map = {}
    
    # 按offset从小到大排序
    insertions_sorted = sorted(insertions, key=lambda x: x[0])
    
    # 计算每个原始offset的新offset
    cumulative_size = 0
    insertion_idx = 0
    
    for old_offset in range(original_size):
        # 检查是否有插入发生在old_offset之前
        while (insertion_idx < len(insertions_sorted) and
               insertions_sorted[insertion_idx][0] <= old_offset):
            cumulative_size += insertions_sorted[insertion_idx][1]
            insertion_idx += 1
        
        # 新offset = 旧offset + 累积插入大小
        new_offset = old_offset + cumulative_size
        relocation_map[old_offset] = new_offset
    
    return relocation_map


def fix_jumps_and_calls(binary, relocation_map, base_addr, instructions_data):
    """
    修正跳转和调用指令的目标地址
    
    Args:
        binary: bytearray - 插桩后的机器码
        relocation_map: dict - 地址重定位映射
        base_addr: int - .text段基址
        instructions_data: dict - 原始指令信息
    
    Returns:
        bytearray - 修正后的机器码
    """
    print(f"\n  修正跳转和调用指令:")
    
    instructions = instructions_data['instructions']
    fixed_count = 0
    
    for instr in instructions:
        mnemonic = instr.get('mnemonic', '').lower()
        if not mnemonic:
            continue
            
        old_offset = instr.get('offset', 0)
        old_addr = instr.get('address', instr.get('pc', base_addr + old_offset))
        
        # 检查是否在重定位映射中
        if old_offset not in relocation_map:
            continue
        
        new_offset = relocation_map[old_offset]
        
        # 检查是否需要修正
        needs_fix = False
        target_addr = None
        
        # CALL指令: B0 12 XX XX (4字节)
        if 'call' in mnemonic:
            # 从原始字节中读取目标地址
            inst_bytes = instr.get('bytes', [])
            if len(inst_bytes) >= 4:
                # 字节数组可能是十进制
                if inst_bytes[0] == 0xB0 or inst_bytes[0] == 176:
                    # 读取目标地址（小端序）
                    target_addr = inst_bytes[2] | (inst_bytes[3] << 8)
                    needs_fix = True
        
        # 相对跳转指令（JMP/JNZ等）
        # 这些使用相对偏移，通常不需要修正，因为偏移是相对的
        
        if needs_fix and target_addr:
            # 计算新的偏移
            new_instr_offset = relocation_map.get(old_offset, old_offset)
            target_offset = target_addr - base_addr
            new_target_offset = relocation_map.get(target_offset, target_offset)
            new_target_addr = base_addr + new_target_offset
            
            # 更新binary中的目标地址
            # CALL指令格式: B0 12 [addr_lo] [addr_hi]
            addr_byte_offset = new_instr_offset + 2  # 跳过opcode
            binary[addr_byte_offset] = new_target_addr & 0xFF
            binary[addr_byte_offset + 1] = (new_target_addr >> 8) & 0xFF
            
            print(f"    CALL: 0x{target_addr:04X} → 0x{new_target_addr:04X}")
            fixed_count += 1
    
    print(f"  ✓ 修正了 {fixed_count} 个跳转/调用")
    
    return binary


def print_patching_summary(original_size, patched_size, patches):
    """打印插桩摘要"""
    print("\n" + "="*70)
    print("  插桩结果摘要")
    print("="*70)
    print(f"  原始大小:   {original_size} 字节")
    print(f"  插桩后大小: {patched_size} 字节")
    print(f"  增加:       {patched_size - original_size} 字节 (+{(patched_size - original_size) / original_size * 100:.1f}%)")
    print(f"  补丁数:     {len(patches)}")
    print("="*70)


def main():
    parser = argparse.ArgumentParser(
        description='在机器码中插入备份补丁（纯二进制操作）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
这是纯机器码方案的核心步骤！
直接在二进制文件中插入机器码字节，不经过汇编器。
        """
    )
    
    parser.add_argument('binary_file',
                       help='输入text_section.bin')
    parser.add_argument('--patches',
                       default='build/machine_code/backup_patches.json',
                       help='补丁JSON')
    parser.add_argument('--instructions',
                       default='build/machine_code/instructions.json',
                       help='指令JSON（用于修正跳转）')
    parser.add_argument('--section-info',
                       default='build/machine_code/section_info.json',
                       help='段信息JSON（用于base_addr）')
    parser.add_argument('--output',
                       default='build/machine_code/text_instrumented.bin',
                       help='输出text_instrumented.bin')
    
    args = parser.parse_args()
    
    # 检查输入文件
    bin_path = Path(args.binary_file)
    if not bin_path.exists():
        print(f"错误: 文件不存在: {bin_path}")
        sys.exit(1)
    
    patches_path = Path(args.patches)
    if not patches_path.exists():
        print(f"错误: 文件不存在: {patches_path}")
        sys.exit(1)
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"  输入二进制: {bin_path}")
    print()
    
    # 加载原始二进制
    print("[1/5] 加载原始机器码...")
    with open(bin_path, 'rb') as f:
        original_binary = f.read()
    print(f"  ✓ 加载了 {len(original_binary)} 字节")
    
    # 加载补丁
    print("\n[2/5] 加载备份补丁...")
    with open(patches_path, 'r') as f:
        patches = json.load(f)
    print(f"  ✓ 加载了 {len(patches)} 个补丁")
    
    # 插入补丁
    print("\n[3/5] 插入补丁到机器码...")
    print("\n  插桩效果展示 (前3个):")
    print("  " + "─"*66)
    
    # 展示前3个补丁的插桩效果
    for idx, (wid, patch) in enumerate(list(patches.items())[:3]):
        print(f"\n  [{idx+1}] {wid}:")
        
        # 原始指令信息
        orig = patch['original_instruction']
        offset = orig['offset']
        
        print(f"      原始指令 @ 0x{orig['address']:04X}:")
        orig_bytes = original_binary[offset:offset+orig.get('size', 4)]
        print(f"        机器码: {' '.join(f'{b:02X}' for b in orig_bytes)}")
        print(f"        反汇编: {orig['mnemonic']} {orig.get('dst', '')}")
        
        # 插入的备份代码
        tpl_type = patch.get('template_type', 'unknown')
        tpl_names = {'overwrite': '模板1-覆盖写', 'read_modify_write': '模板2-RMW双槽', 'push': '模板3-Push'}
        print(f"      ↓ 插入备份序列 ({tpl_names.get(tpl_type, tpl_type)}, {patch['size']}字节):")
        
        # 反汇编备份代码
        backup_code = patch['machine_code']
        print(f"        [1] MOV dst, &SLOT      : {' '.join(f'{b:02X}' for b in backup_code[:6])}")
        print(f"        [2] MOV PC, &0x7000     : {' '.join(f'{b:02X}' for b in backup_code[6:12])}") 
        print(f"        [3] MOV R1, &0x7004     : {' '.join(f'{b:02X}' for b in backup_code[12:16])}")
        
        print(f"      结果:")
        print(f"        原始: 1条指令")
        print(f"        插桩后: 1条原始 + 3条备份 = 4条指令")
    
    print("\n  " + "─"*66)
    print()
    
    patched_binary, relocation_map = insert_patches_into_binary(original_binary, patches)
    print(f"  ✓ 插入完成，新大小: {len(patched_binary)} 字节")
    
    # 加载指令信息用于修正跳转
    print("\n[4/5] 修正跳转和调用指令...")
    try:
        with open(args.instructions, 'r') as f:
            instructions_data = json.load(f)
        with open(args.section_info, 'r') as f:
            section_info = json.load(f)
        
        base_addr = section_info['start_addr']
        patched_binary = fix_jumps_and_calls(
            bytearray(patched_binary),
            relocation_map,
            base_addr,
            instructions_data
        )
    except FileNotFoundError as e:
        print(f"  ⚠ 警告: 无法加载指令信息，跳过跳转修正")
        print(f"    {e}")
    
    # 保存结果
    print("\n[5/5] 保存插桩后的机器码...")
    with open(output_path, 'wb') as f:
        f.write(patched_binary)
    print(f"  ✓ 保存到: {output_path}")
    
    # 打印摘要
    print_patching_summary(len(original_binary), len(patched_binary), patches)
    
    print(f"  输入:  {bin_path} ({len(original_binary)} 字节)")
    print(f"  输出:  {output_path} ({len(patched_binary)} 字节)")
    print(f"  插桩:  +{len(patched_binary) - len(original_binary)} 字节 (纯机器码插入!)")
    print()
    
    # 提示下一步
    print("  2. 提取备份点→PC映射")
    print("  3. 生成恢复逻辑机器码")
    print("  4. 重建ELF文件")
    print()


if __name__ == '__main__':
    main()







