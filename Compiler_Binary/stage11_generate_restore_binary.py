#!/usr/bin/env python3
"""
Stage 11: 生成恢复逻辑机器码
生成完整的恢复函数(_asap_restore)的机器码

输入: wid_pc_map.json, candidates.json, fram_slots.json
输出: restore_logic.bin (纯机器码)

恢复逻辑流程:
  1. 读取WID和恢复SP
  2. 恢复所有变量
  3. 根据WID跳转到对应的恢复点
"""

import argparse
import json
import sys
from pathlib import Path

# 导入编码器
sys.path.insert(0, str(Path(__file__).parent))
from msp430_encoder import MSP430Encoder


def generate_restore_entry(encoder):
    """
    生成恢复函数入口
    
    _asap_restore:
        MOV &ASAP_WID_SAVE, R12   ; 读取WID
        MOV &ASAP_SP_SAVE, R1     ; 恢复SP
    """
    code = []
    
    # MOV &0x7000, R12
    code.extend(encoder.encode_mov_mem_to_reg(0x7000, 'r12'))
    
    # MOV &0x7004, R1
    code.extend(encoder.encode_mov_mem_to_reg(0x7004, 'r1'))
    
    return code


def generate_variables_restore(candidates, fram_slots, encoder):
    """
    生成变量恢复代码
    
    为每个唯一的logical_addr，从FRAM恢复到原始位置
    注意: 同一地址的多个WID共享槽位，只恢复一次
    """
    code = []
    
    addr_to_slot = fram_slots.get('addr_to_slot', {})
    
    # 按地址恢复（不是按WID）
    for logical_addr in sorted(addr_to_slot.keys()):
        slot_info = addr_to_slot[logical_addr]
        slot_addr = int(slot_info['slot_addr'], 16)
        
        # 从logical_addr推断dst格式
        if '::SP+' in logical_addr:
            # 栈变量: main::SP+4 → 4(R1)
            offset = int(logical_addr.split('+')[1])
            # MOV &slot_addr, offset(R1)
            # 使用两步: MOV &slot, R15; MOV R15, offset(R1)
            code.extend(encoder.encode_mov_mem_to_reg(slot_addr, 'r15'))
            code.extend(encoder.encode_mov_reg_to_indexed('r15', 'r1', offset))
        elif logical_addr.startswith('0x'):
            # 全局变量: MOV &slot_addr, &global_addr
            global_addr = int(logical_addr, 16)
            code.extend(encoder.encode_mov_mem_to_reg(slot_addr, 'r15'))
            code.extend(encoder.encode_mov_reg_to_mem('r15', global_addr))
        # 更多类型待实现...
    
    return code


def generate_wid_jump_table(wid_pc_map, encoder, restore_base_addr):
    """
    生成WID跳转表
    
    根据R12中的WID值，跳转到对应的恢复点
    
    策略: 使用CMP+JEQ为每个WID生成跳转
    """
    code = []
    
    # 计算每个WID跳转块的大小（用于计算偏移）
    # CMP #wid, R12 (4字节) + JEQ (2字节) = 6字节/WID
    bytes_per_wid = 6
    
    # 为每个WID生成比较和跳转
    wid_list = sorted(wid_pc_map.items(), key=lambda x: int(x[0][1:]))
    
    for i, (wid, pc) in enumerate(wid_list):
        wid_num = int(wid[1:])
        pc_addr = int(pc, 16)
        
        # CMP #wid_num, R12
        code.extend(encoder.encode_cmp_imm_to_reg(wid_num, 'r12'))
        
        # JEQ restore_point
        # 计算跳转偏移（跳过所有后续的CMP+JEQ块）
        remaining_wids = len(wid_list) - i - 1
        skip_bytes = remaining_wids * bytes_per_wid + 2  # +2 for final JMP
        
        # 然后直接BR到PC
        # 简化: 使用固定偏移，跳转到BR指令序列
        jump_offset = (remaining_wids + 1) * 2  # 每个BR指令4字节
        code.extend(encoder.encode_jeq(jump_offset))
    
    # 如果没有匹配任何WID，死循环
    code.extend(encoder.encode_jmp(0))  # JMP $+0
    
    # 为每个WID生成BR跳转
    for wid, pc in wid_list:
        pc_addr = int(pc, 16)
        code.extend(encoder.encode_br(pc_addr))
    
    return code


def main():
    parser = argparse.ArgumentParser(
        description='生成恢复逻辑机器码',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--wid-pc-map',
                       default='build/machine_code/wid_pc_map.json',
                       help='WID→PC映射')
    parser.add_argument('--candidates',
                       default='build/machine_code/candidates.json',
                       help='候选写操作')
    parser.add_argument('--fram-slots',
                       default='build/machine_code/fram_slots.json',
                       help='FRAM槽位')
    parser.add_argument('--output',
                       default='build/machine_code/restore_logic.bin',
                       help='输出restore_logic.bin')
    parser.add_argument('--restore-base',
                       type=lambda x: int(x, 0),
                       default=0x4400,
                       help='恢复逻辑基址')
    
    args = parser.parse_args()
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print()
    
    # 加载数据
    print("[1/4] 加载备份点→PC映射...")
    with open(args.wid_pc_map, 'r') as f:
        wid_pc_map = json.load(f)
    print(f"  ✓ 加载了 {len(wid_pc_map)} 个备份点映射")
    
    print("\n[2/4] 加载候选和槽位...")
    with open(args.candidates, 'r') as f:
        candidates = json.load(f)
    with open(args.fram_slots, 'r') as f:
        fram_slots = json.load(f)
    print(f"  ✓ 候选: {len(candidates)}, 槽位: {len(fram_slots.get('wid_to_slot', {}))}")
    
    # 生成恢复逻辑
    print("\n[3/4] 生成恢复逻辑机器码...")
    encoder = MSP430Encoder()
    
    restore_code = bytearray()
    
    # 1. 入口代码
    print("  - 生成入口代码 (读取备份标识和SP)")
    restore_code.extend(generate_restore_entry(encoder))
    
    # 2. 恢复变量
    print("  - 生成变量恢复代码")
    restore_code.extend(generate_variables_restore(candidates, fram_slots, encoder))
    
    # 3. WID跳转表
    print("  - 生成备份点跳转表")
    restore_code.extend(generate_wid_jump_table(wid_pc_map, encoder, args.restore_base))
    
    print(f"  ✓ 生成了 {len(restore_code)} 字节恢复逻辑")
    
    # 保存结果
    print("\n[4/4] 保存恢复逻辑...")
    with open(output_path, 'wb') as f:
        f.write(restore_code)
    print(f"  ✓ 保存到: {output_path}")
    
    # 打印摘要
    print("\n" + "="*70)
    print("  恢复逻辑机器码生成结果")
    print("="*70)
    print(f"  总大小: {len(restore_code)} 字节")
    print(f"  备份点数: {len(wid_pc_map)}")
    print(f"  恢复变量数: {len(candidates)}")
    print("="*70)
    
    print(f"  输出: {output_path} ({len(restore_code)} 字节)")
    print()
    
    # 提示下一步
    print("  1. 合并: restore_logic.bin + text_instrumented.bin")
    print("  2. 重建ELF文件")
    print("  3. 测试完整固件")
    print()


if __name__ == '__main__':
    main()

