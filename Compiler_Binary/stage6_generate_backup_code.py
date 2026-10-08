#!/usr/bin/env python3
"""
Stage 6: 生成备份机器码
为每个候选写操作生成备份指令的机器码序列

输入: candidates.json, fram_slots.json
输出: backup_patches.json (插入位置 + 机器码字节)

核心: 这里生成的是纯机器码字节，将在Stage 7直接插入到text_section.bin中
"""

import argparse
import json
import sys
from pathlib import Path

# 导入编码器
import sys
sys.path.insert(0, str(Path(__file__).parent))
from msp430_encoder import MSP430Encoder


def generate_scalar_backup_code(candidate, slot_info, encoder):
    """
    生成标量备份的机器码
    
    备份序列:
      1. MOV dst, &slot_addr     (备份数据)
      2. MOV R1, &ASAP_SP_SAVE   (备份SP)
      3. MOV #WID, &ASAP_WID_SAVE (标记WID)
    
    Args:
        candidate: 候选写操作
        slot_info: FRAM槽位信息
        encoder: MSP430Encoder实例
    
    Returns:
        list: 机器码字节列表
    """
    code = []
    
    dst = candidate['dst']
    slot_addr = int(slot_info['slot_addr'], 16)
    wid_num = int(candidate['wid'][1:])  # W001 → 1
    mnemonic = candidate.get('mnemonic', 'mov').lower().split('.')[0]
    
    # 确定指令类别（按语义）
    template_type = "unknown"
    
    # 判断指令类别
    if mnemonic in ['mov', 'clr', 'bic', 'bis', 'swpb', 'sxt']:
        template_type = "overwrite"  # 模板1: 覆盖写类
    elif mnemonic in ['add', 'addc', 'sub', 'subc', 'xor', 'and', 'dadd', 'inc', 'dec', 'rrc', 'rra']:
        template_type = "read_modify_write"  # 模板2: 读改写类
    elif mnemonic == 'push':
        template_type = "push"  # 模板3: Push类
    elif mnemonic in ['jmp', 'jne', 'jeq', 'jnz', 'jz', 'jnc', 'jc', 'jn', 'jge', 'jl']:
        template_type = "control_flow"  # 模板4: 控制流
    else:
        template_type = "overwrite"  # 默认为覆盖写
    
    # 根据dst类型选择编码方式（寻址方式）
    addressing_mode = "unknown"
    
    if '(r1)' in dst.lower() or '(sp)' in dst.lower():
        # 栈变量
        offset = int(dst.split('(')[0])
        code.extend(encoder.encode_mov_indexed_to_mem('r1', offset, slot_addr))
        addressing_mode = "stack_indexed"
        
    elif dst.startswith('&0x'):
        # 全局变量，通过R15中转
        global_addr = int(dst[1:], 16)
        code.extend(encoder.encode_mov_mem_to_mem_via_temp(global_addr, slot_addr, 'r15'))
        addressing_mode = "global_absolute"
            
    elif '(' in dst and not '(r1)' in dst.lower():
        # 间接寻址
        trace_info = candidate.get('trace_info', {})
        
        if trace_info.get('success') and 'actual_address' in trace_info:
            # 追踪成功
            actual_addr = trace_info['actual_address']
            code.extend(encoder.encode_mov_mem_to_mem_via_temp(actual_addr, slot_addr, 'r15'))
            addressing_mode = "indirect_traced"
        else:
            # 运行时间接
            parts = dst.split('(')
            offset = int(parts[0]) if parts[0] else 0
            base_reg = parts[1].rstrip(')').lower()
            code.extend(encoder.encode_mov_indexed_to_mem_via_temp(base_reg, offset, slot_addr, 'r15'))
            addressing_mode = "indirect_indexed"
        
    elif dst.startswith('r'):
        # 寄存器
        code.extend(encoder.encode_mov_reg_to_mem(dst, slot_addr))
        addressing_mode = "register_direct"
    else:
        print(f"  ⚠ 警告: 不支持的dst类型: {dst}")
        return []
    
    # 2. 备份SP: MOV R1, &ASAP_SP_SAVE (0x7004)
    code.extend(encoder.encode_mov_reg_to_mem('r1', 0x7004))
    
    # 3. 标记WID: MOV #wid_num, &ASAP_WID_SAVE (0x7000)
    code.extend(encoder.encode_mov_imm_to_mem(wid_num, 0x7000))
    
    # 保存分类信息
    candidate['template_type'] = template_type
    candidate['addressing_mode'] = addressing_mode
    
    return code


def generate_array_backup_code(candidate, slot_info, encoder):
    """
    生成数组备份的机器码（索引感知）
    
    流程:
      1. 读取索引变量 i
      2. 计算 backup[i] 地址
      3. 备份 array[i] 到 backup[i]
      4. 备份 SP 和 WID
    """
    code = []
    
    array_info = candidate.get('array_info', {})
    if not array_info:
        return []
    
    index_location = array_info.get('index_location', '0(r1)')
    # 解析索引偏移
    index_offset = int(index_location.split('(')[0])
    
    backup_base_addr = int(slot_info['slot_addr'], 16)
    wid_num = int(candidate['wid'][1:])
    dst = candidate['dst']
    
    # 使用R14作为临时寄存器
    temp_reg = 'r14'
    
    # 1. 读取索引: MOV index_offset(R1), R14
    code.extend(encoder.encode_mov_indexed_to_reg('r1', index_offset, temp_reg))
    
    # 2. 计算偏移: RLAM #1, R14 (i*2)
    code.extend(encoder.encode_rlam(1, temp_reg))
    
    # 3. 计算backup地址: ADD #backup_base, R14
    code.extend(encoder.encode_add_imm_to_reg(backup_base_addr, temp_reg))
    
    # 4. 备份数据（取决于dst类型）
    if dst.startswith('@'):
        # 间接寻址: @R13 → 从R13指向的地址读取
        src_reg = dst[1:]  # 去掉@
        # MOV @Rsrc, @R14
        code.extend(encoder.encode_mov_indirect_to_indirect(src_reg, temp_reg))
    else:
        # 其他情况暂不支持
        print(f"  ⚠ 数组dst类型不支持: {dst}")
        return []
    
    # 5. 备份SP和WID
    code.extend(encoder.encode_mov_reg_to_mem('r1', 0x7004))
    code.extend(encoder.encode_mov_imm_to_mem(wid_num, 0x7000))
    
    return code


def generate_indirect_backup_code(candidate, slot_info, encoder):
    """
    生成间接寻址备份的机器码
    
    需要备份:
      1. 数据本身
      2. 寄存器的值（地址）
    """
    code = []
    
    dst = candidate['dst']
    slot_addr = int(slot_info['slot_addr'], 16)
    wid_num = int(candidate['wid'][1:])
    
    # 解析间接寻址: @R12, @R13, etc.
    if not dst.startswith('@'):
        return []
    
    reg = dst[1:]  # 去掉@
    
    # 1. 备份数据: MOV @Rreg, &slot_addr
    # 需要先MOV到临时寄存器
    code.extend(encoder.encode_mov_indirect_to_reg(reg, 'r15'))
    code.extend(encoder.encode_mov_reg_to_mem('r15', slot_addr))
    
    # 2. 备份寄存器值（地址）
    # 需要额外的地址槽位（假设在slot_addr+2）
    addr_slot = slot_addr + 2
    code.extend(encoder.encode_mov_reg_to_mem(reg, addr_slot))
    
    # 3. 备份SP和WID
    code.extend(encoder.encode_mov_reg_to_mem('r1', 0x7004))
    code.extend(encoder.encode_mov_imm_to_mem(wid_num, 0x7000))
    
    return code


def generate_backup_patches(candidates, fram_slots):
    """
    为所有候选写操作生成备份机器码补丁
    
    Args:
        candidates: 候选写操作字典
        fram_slots: FRAM槽位分配
    
    Returns:
        dict: 补丁字典 {WID: {insert_offset, machine_code, size}}
    """
    encoder = MSP430Encoder()
    patches = {}
    
    addr_to_slot = fram_slots.get('addr_to_slot', {})
    wid_to_slot = fram_slots.get('wid_to_slot', {})
    
    for wid, candidate in candidates.items():
        # 获取槽位信息
        if wid in wid_to_slot:
            slot_info = wid_to_slot[wid]
        else:
            # 从logical_addr查找
            logical_addr = candidate['logical_addr']
            if logical_addr in addr_to_slot:
                slot_info = addr_to_slot[logical_addr]
            else:
                print(f"  ⚠ 警告: {wid} 没有分配槽位")
                continue
        
        # 根据类型生成备份机器码
        candidate_type = candidate.get('type', 'scalar')
        addr_mode = candidate.get('addr_mode', 'DIRECT')
        
        if candidate_type == 'array':
            # 数组备份
            backup_code = generate_array_backup_code(candidate, slot_info, encoder)
            if not backup_code:
                print(f"  ⚠ {wid}: 数组备份生成失败，回退到标量")
                backup_code = generate_scalar_backup_code(candidate, slot_info, encoder)
        elif addr_mode == 'INDIRECT':
            # 间接寻址备份
            backup_code = generate_indirect_backup_code(candidate, slot_info, encoder)
            if not backup_code:
                print(f"  ⚠ {wid}: 间接寻址备份生成失败，回退到标量")
                backup_code = generate_scalar_backup_code(candidate, slot_info, encoder)
        else:
            # 标量备份
            backup_code = generate_scalar_backup_code(candidate, slot_info, encoder)
        
        if not backup_code:
            continue
        
        # 计算插入位置：原始写指令之后
        insert_offset = candidate['offset'] + candidate['instruction_size']
        
        patches[wid] = {
            'insert_offset': insert_offset,
            'insert_address': candidate['address'] + candidate['instruction_size'],
            'machine_code': backup_code,
            'size': len(backup_code),
            'type': candidate_type,
            'template_type': candidate.get('template_type', 'unknown'),
            'addressing_mode': candidate.get('addressing_mode', 'unknown'),
            'original_instruction': {
                'offset': candidate['offset'],
                'address': candidate['address'],
                'mnemonic': candidate['mnemonic'],
                'dst': candidate['dst']
            }
        }
    
    return patches


def print_patches_summary(patches):
    """
    打印补丁摘要 - 模板驱动的备份代码生成展示
    """
    print("\n" + "="*70)
    print("  备份插桩 - 模板驱动的备份序列生成")
    print("="*70)
    
    # 第1部分：备份槽位分配
    print("\n[备份槽位分配]")
    print(f"  说明: 为{len(patches)}个关键状态更新分配FRAM备份槽位")
    print(f"  策略: 每个写操作分配一个槽位，包含数据+PC+SP字段")
    print(f"  总补丁数: {len(patches)}")
    
    total_bytes = sum(p['size'] for p in patches.values())
    print(f"  总字节数: {total_bytes}")
    print(f"  平均大小: {total_bytes / len(patches):.1f} 字节/补丁" if patches else "  平均大小: 0")
    
    # 第2部分：备份元数据表
    print(f"\n[备份元数据表]")
    print(f"  说明: 为每个写操作维护备份槽位索引和字段偏移")
    print(f"  结构: (备份点 → 槽位地址, 槽位类型, 字段集合)")
    
    # 统计寻址类型
    addressing_stats = {}
    for patch in patches.values():
        addr_type = patch.get('addressing_type', 'unknown')
        addressing_stats[addr_type] = addressing_stats.get(addr_type, 0) + 1
    
    # 按模板类型（指令语义）统计
    template_stats = {}
    for patch in patches.values():
        tpl_type = patch.get('template_type', 'unknown')
        template_stats[tpl_type] = template_stats.get(tpl_type, 0) + 1
    
    print(f"\n  备份模板分类 (按指令语义):")
    template_names = {
        'overwrite': '模板1: 覆盖写类(MOV等)',
        'read_modify_write': '模板2: 读改写类(ADD等,双槽)',
        'push': '模板3: Push指令',
        'control_flow': '模板4: 控制流',
        'unknown': '其他'
    }
    
    for tpl_type, count in sorted(template_stats.items(), key=lambda x: -x[1]):
        tpl_name = template_names.get(tpl_type, tpl_type)
        # 估算字节数
        if tpl_type == 'overwrite':
            # 覆盖写，根据寻址方式计算
            tpl_patches = [p for p in patches.values() if p.get('template_type') == 'overwrite']
            total_bytes = sum(p['size'] for p in tpl_patches)
            print(f"    {tpl_name:35s}: {count:3d} 个, {total_bytes:4d}B 总计")
        elif tpl_type == 'read_modify_write':
            avg_size = 24  # 双槽
            print(f"    {tpl_name:35s}: {count:3d} 个 × ~{avg_size}B = {count*avg_size:4d}B")
        elif tpl_type == 'push':
            avg_size = 14
            print(f"    {tpl_name:35s}: {count:3d} 个 × {avg_size}B = {count*avg_size:4d}B")
        else:
            print(f"    {tpl_name:35s}: {count:3d} 个")
    
    # 详细分解覆盖写类的寻址方式
    if 'overwrite' in template_stats:
        print(f"\n  模板1详细分解 (按寻址方式):")
        overwrite_patches = [p for p in patches.values() if p.get('template_type') == 'overwrite']
        addr_mode_stats = {}
        for p in overwrite_patches:
            mode = p.get('addressing_mode', 'unknown')
            addr_mode_stats[mode] = addr_mode_stats.get(mode, 0) + 1
        
        mode_names = {
            'stack_indexed': '栈变量',
            'global_absolute': 'SRAM全局变量',
            'indirect_indexed': '间接寻址(运行时)',
            'indirect_traced': '间接寻址(已追踪)',
        }
        for mode, count in sorted(addr_mode_stats.items(), key=lambda x: -x[1]):
            mode_name = mode_names.get(mode, mode)
            mode_patches = [p for p in overwrite_patches if p.get('addressing_mode') == mode]
            total_bytes = sum(p['size'] for p in mode_patches)
            print(f"    ├─ {mode_name:20s}: {count:3d} 个, {total_bytes:4d}B")
    
    # 第3部分：模板驱动生成
    print(f"\n[模板实例化示例]")
    print(f"  说明: 每个写指令后插入备份序列")
    print()
    
    # 展示不同类型的模板
    print(f"  模板1: 栈变量备份 (16字节)")
    print(f"    MOV offset(R1), &SLOT_ADDR    ; 6字节 - 备份数据")
    print(f"    MOV R1, &0x7004               ; 4字节 - 备份SP")
    print(f"    MOV PC, &0x7000               ; 6字节 - 标记提交点")
    print()
    
    print(f"  模板2: 全局变量备份 (18字节，需临时寄存器)")
    print(f"    MOV &GLOBAL_ADDR, R15         ; 4字节 - 读全局变量到临时寄存器")
    print(f"    MOV R15, &SLOT_ADDR           ; 4字节 - 临时寄存器写槽位")
    print(f"    MOV R1, &0x7004               ; 4字节 - 备份SP")
    print(f"    MOV PC, &0x7000               ; 6字节 - 标记提交点")
    print()
    
    print(f"  模板3: 间接寻址备份 (18字节，运行时解引用)")
    print(f"    MOV offset(RX), R15           ; 4字节 - 间接读到临时寄存器")
    print(f"    MOV R15, &SLOT_ADDR           ; 4字节 - 临时寄存器写槽位")
    print(f"    MOV R1, &0x7004               ; 4字节 - 备份SP")
    print(f"    MOV PC, &0x7000               ; 6字节 - 标记提交点")
    
    # 第4部分：实际生成的补丁
    print(f"\n[生成的备份补丁] (前10个):")
    print(f"  {'WID':5s} {'插入位置':12s} {'大小':6s} {'模板':12s} {'寻址':10s} {'机器码':20s}")
    print(f"  {'-'*70}")
    
    for wid, patch in list(patches.items())[:10]:
        offset = patch['insert_offset']
        size = patch['size']
        tpl_type = patch.get('template_type', 'unknown')
        addr_mode = patch.get('addressing_mode', 'unknown')
        
        # 模板类型名称
        tpl_names = {
            'overwrite': '覆盖写',
            'read_modify_write': 'RMW双槽',
            'push': 'Push',
            'control_flow': '跳转PC',
        }
        tpl_name = tpl_names.get(tpl_type, tpl_type)
        
        # 寻址方式名称（简短）
        addr_names = {
            'stack_indexed': '栈',
            'global_absolute': 'SRAM全局',
            'indirect_indexed': '间接',
            'indirect_traced': '间接追踪',
        }
        addr_name = addr_names.get(addr_mode, addr_mode[:10])
        
        machine_code_hex = ' '.join(f'{b:02X}' for b in patch['machine_code'][:6])
        if len(patch['machine_code']) > 6:
            machine_code_hex += '...'
        
        print(f"  {wid:5s} 0x{offset:04X}({offset:5d})  {size:3d}B  {tpl_name:12s} {addr_name:10s} {machine_code_hex}")
    
    if len(patches) > 10:
        print(f"  ... 还有 {len(patches) - 10} 个补丁")
    
    print("="*70)


def main():
    parser = argparse.ArgumentParser(
        description='生成备份机器码补丁',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('candidates_json',
                       help='输入candidates.json')
    parser.add_argument('--fram-slots',
                       default='build/machine_code/fram_slots.json',
                       help='FRAM槽位JSON')
    parser.add_argument('--output',
                       default='build/machine_code/backup_patches.json',
                       help='输出补丁JSON')
    
    args = parser.parse_args()
    
    # 检查输入文件
    cand_path = Path(args.candidates_json)
    if not cand_path.exists():
        print(f"错误: 文件不存在: {cand_path}")
        sys.exit(1)
    
    # fram_slots.json可能还不存在（需要先运行stage4 allocate）
    # 这里先创建一个简单的测试版本
    fram_path = Path(args.fram_slots)
    if not fram_path.exists():
        print(f"  ⚠ {fram_path} 不存在，生成测试槽位...")
        # 临时生成简单的槽位分配
        with open(cand_path, 'r') as f:
            candidates = json.load(f)
        
        test_slots = generate_test_slots(candidates)
        fram_path.parent.mkdir(parents=True, exist_ok=True)
        with open(fram_path, 'w') as f:
            json.dump(test_slots, f, indent=2)
        print(f"  ✓ 生成测试槽位: {fram_path}")
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"  输入: {cand_path}")
    print()
    
    # 加载数据
    print("[1/3] 加载候选写操作...")
    with open(cand_path, 'r') as f:
        candidates = json.load(f)
    print(f"  ✓ 加载了 {len(candidates)} 个候选")
    
    print("\n[2/3] 加载FRAM槽位...")
    with open(fram_path, 'r') as f:
        fram_slots = json.load(f)
    print(f"  ✓ 加载槽位信息")
    
    # 生成补丁
    print("\n[3/3] 生成备份机器码...")
    patches = generate_backup_patches(candidates, fram_slots)
    print(f"  ✓ 生成了 {len(patches)} 个补丁")
    
    # 保存结果
    with open(output_path, 'w') as f:
        json.dump(patches, f, indent=2)
    print(f"  ✓ 保存到: {output_path}")
    
    # 打印摘要
    print_patches_summary(patches)
    
    print(f"  输出: {output_path}")
    print()


def generate_test_slots(candidates):
    """生成测试用的槽位分配"""
    slots = {
        'addr_to_slot': {},
        'wid_to_slot': {}
    }
    
    current_addr = 0x4800
    for wid, cand in candidates.items():
        logical_addr = cand['logical_addr']
        
        slot_info = {
            'logical_addr': logical_addr,
            'slot_addr': f'0x{current_addr:04X}',
            'slot_symbol': f'__SLOT_{logical_addr.replace("::", "_").replace("+", "_")}',
            'type': cand['type']
        }
        
        slots['addr_to_slot'][logical_addr] = slot_info
        slots['wid_to_slot'][wid] = slot_info
        
        current_addr += 2  # 每个槽位2字节
    
    return slots


if __name__ == '__main__':
    main()

