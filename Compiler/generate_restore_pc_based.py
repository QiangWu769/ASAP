#!/usr/bin/env python3
"""
基于PC的恢复逻辑生成器

根据PC范围到活跃地址集合的映射，生成恢复汇编代码。

输入：
  - lifetime_pc.json: PC范围到活跃地址集合的映射
  - fram_layout_report.json: FRAM布局信息（槽位地址）

输出：
  - asap_restore.s: 恢复逻辑汇编代码
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List

def sanitize_symbol_name(name: str) -> str:
    """清理字符串以生成有效的符号名"""
    name = name.upper()
    name = name.replace("::", "__")
    name = name.replace("(", "_")
    name = name.replace(")", "")
    name = name.replace(" ", "")
    name = name.replace("&", "")
    name = name.replace("#", "")
    if name and name[0].isdigit():
        name = "ADDR_" + name
    return name

def generate_restore_for_range(
    range_idx: int,
    pc_range: Dict,
    fram_layout: Dict
) -> List[str]:
    """
    为一个PC范围生成恢复代码
    
    Returns:
        汇编代码行列表
    """
    start_pc = int(pc_range['start'], 16)
    end_pc = int(pc_range['end'], 16) if pc_range['end'] != "0xFFFF" else 0xFFFF
    alive_addrs = pc_range['alive']
    
    lines = []
    lines.append(f"_check_range_{range_idx}:")
    lines.append(f"\t; PC范围 [{pc_range['start']}, {pc_range['end']})")
    
    # 检查PC是否在范围内
    if range_idx == 0:
        # 第一个范围，只检查上界
        lines.append(f"\tCMP.W\t#{pc_range['end']}, R12")
        lines.append(f"\tJHS\t_check_range_{range_idx + 1}\t; PC >= end?")
    elif end_pc == 0xFFFF:
        # 最后一个范围，只检查下界
        lines.append(f"\tCMP.W\t#{pc_range['start']}, R12")
        lines.append(f"\tJLO\t_restore_cold_start\t; PC < start?")
    else:
        # 中间范围，检查上下界
        lines.append(f"\tCMP.W\t#{pc_range['start']}, R12")
        lines.append(f"\tJLO\t_check_range_{range_idx + 1}\t; PC < start?")
        lines.append(f"\tCMP.W\t#{pc_range['end']}, R12")
        lines.append(f"\tJHS\t_check_range_{range_idx + 1}\t; PC >= end?")
    
    lines.append(f"\t; 恢复{len(alive_addrs)}个活跃地址")
    
    # 恢复每个活跃地址
    slot_mapping = fram_layout.get('slot_mapping', {})
    
    for addr in alive_addrs:
        # 查找该地址的槽位（简化：使用S0）
        clean_name = sanitize_symbol_name(addr)
        slot_symbol = f"__SLOT_{clean_name}_S0"
        
        lines.append(f"\tMOV.W\t&{slot_symbol}, &{addr}\t; 恢复{addr}")
    
    lines.append(f"\tJMP\t_restore_done")
    lines.append("")
    
    return lines

def generate_restore_code(lifetime_data: Dict, fram_layout: Dict) -> List[str]:
    """生成完整的恢复逻辑汇编代码"""
    
    pc_ranges = lifetime_data.get('pc_ranges', [])
    
    lines = []
    lines.append("\t.text")
    lines.append("\t.global\t_asap_restore")
    lines.append("\t.type\t_asap_restore, @function")
    lines.append("")
    lines.append("_asap_restore:")
    lines.append("\t; ===== 基于PC的恢复逻辑 =====")
    lines.append("\t; 【调试】输出'S'表示开始恢复")
    lines.append("\tMOV.B\t#83, R12\t; 'S'")
    lines.append("\tCALL\t#_debug_putc")
    lines.append("\t; 读取保存的PC")
    lines.append("\tMOV.W\t&ASAP_CURRENT_PC, R12\t; R12 = saved PC")
    lines.append("\t; 【调试】输出PC值")
    lines.append("\tCALL\t#_debug_puthex")
    lines.append("")
    lines.append("\t; 检查是否为0（冷启动）")
    lines.append("\tCMP.W\t#0, R12")
    lines.append("\tJEQ\t_restore_cold_start")
    lines.append("")
    
    # 为每个PC范围生成检查和恢复代码
    for idx, pc_range in enumerate(pc_ranges):
        range_lines = generate_restore_for_range(idx, pc_range, fram_layout)
        lines.extend(range_lines)
    
    # 恢复完成，跳转到保存的PC
    lines.append("_restore_done:")
    lines.append("\t; 【调试】输出'D'表示恢复完成")
    lines.append("\tMOV.B\t#68, R12\t; 'D'")
    lines.append("\tCALL\t#_debug_putc")
    lines.append("\t; 【调试】输出PC值（16进制）")
    lines.append("\tMOV.W\t&ASAP_CURRENT_PC, R12")
    lines.append("\tCALL\t#_debug_puthex")
    lines.append("\t; 跳转到保存的PC")
    lines.append("\tMOV.W\t&ASAP_CURRENT_PC, R11")
    lines.append("\tBR\tR11\t; 跳转到断电点继续执行")
    lines.append("")
    
    # 冷启动路径
    lines.append("_restore_cold_start:")
    lines.append("\t; ASAP_CURRENT_PC = 0，执行冷启动")
    lines.append("\t; 返回到bootloader，由bootloader跳转到main")
    lines.append("\tRET")
    lines.append("")
    
    lines.append("\t.size\t_asap_restore, .-_asap_restore")
    lines.append("")
    
    # 调试辅助函数
    lines.append("; ===== 调试辅助函数 =====")
    lines.append("_debug_putc:")
    lines.append("\t; 等待UART ready")
    lines.append(".L_debug_wait:")
    lines.append("\tBIT.B\t#2, &0x05CE\t; UCA0IFG & UCTXIFG?")
    lines.append("\tJZ\t.L_debug_wait")
    lines.append("\tMOV.B\tR12, &0x05CC\t; UCA0TXBUF = R12")
    lines.append("\tRET")
    lines.append("")
    lines.append("_debug_puthex:")
    lines.append("\t; 输出R12的16进制值（4位）")
    lines.append("\tPUSH\tR13")
    lines.append("\tMOV.W\tR12, R13")
    lines.append("\t; 输出高字节高4位")
    lines.append("\tMOV.B\tR13, R12")
    lines.append("\tRRA.B\tR12")
    lines.append("\tRRA.B\tR12")
    lines.append("\tRRA.B\tR12")
    lines.append("\tRRA.B\tR12")
    lines.append("\tAND.W\t#0x0F, R12")
    lines.append("\tADD.B\t#48, R12\t; '0'")
    lines.append("\tCMP.B\t#58, R12")
    lines.append("\tJLO\t.L_hex1")
    lines.append("\tADD.B\t#7, R12\t; 'A'-'9'-1")
    lines.append(".L_hex1:")
    lines.append("\tCALL\t#_debug_putc")
    lines.append("\t; 输出高字节低4位")
    lines.append("\tMOV.B\tR13, R12")
    lines.append("\tAND.W\t#0x0F, R12")
    lines.append("\tADD.B\t#48, R12")
    lines.append("\tCMP.B\t#58, R12")
    lines.append("\tJLO\t.L_hex2")
    lines.append("\tADD.B\t#7, R12")
    lines.append(".L_hex2:")
    lines.append("\tCALL\t#_debug_putc")
    lines.append("\t; 输出低字节高4位")
    lines.append("\tSWPB\tR13")
    lines.append("\tMOV.B\tR13, R12")
    lines.append("\tRRA.B\tR12")
    lines.append("\tRRA.B\tR12")
    lines.append("\tRRA.B\tR12")
    lines.append("\tRRA.B\tR12")
    lines.append("\tAND.W\t#0x0F, R12")
    lines.append("\tADD.B\t#48, R12")
    lines.append("\tCMP.B\t#58, R12")
    lines.append("\tJLO\t.L_hex3")
    lines.append("\tADD.B\t#7, R12")
    lines.append(".L_hex3:")
    lines.append("\tCALL\t#_debug_putc")
    lines.append("\t; 输出低字节低4位")
    lines.append("\tMOV.B\tR13, R12")
    lines.append("\tAND.W\t#0x0F, R12")
    lines.append("\tADD.B\t#48, R12")
    lines.append("\tCMP.B\t#58, R12")
    lines.append("\tJLO\t.L_hex4")
    lines.append("\tADD.B\t#7, R12")
    lines.append(".L_hex4:")
    lines.append("\tCALL\t#_debug_putc")
    lines.append("\tPOP\tR13")
    lines.append("\tRET")
    lines.append("")
    
    return lines

def main():
    ap = argparse.ArgumentParser(description="基于PC的恢复逻辑生成")
    ap.add_argument("--lifetime", required=True, help="生命周期分析JSON")
    ap.add_argument("--fram-layout", required=True, help="FRAM布局报告JSON")
    ap.add_argument("--out", required=True, help="输出的恢复汇编文件")
    args = ap.parse_args()
    
    # 加载生命周期数据
    with open(args.lifetime, 'r') as f:
        lifetime_data = json.load(f)
    
    # 加载FRAM布局
    with open(args.fram_layout, 'r') as f:
        fram_layout = json.load(f)
    
    pc_ranges = lifetime_data.get('pc_ranges', [])
    print(f"[generate_restore_pc] 加载了 {len(pc_ranges)} 个PC范围")
    
    # 生成恢复代码
    restore_lines = generate_restore_code(lifetime_data, fram_layout)
    
    # 写入文件
    with open(args.out, 'w') as f:
        f.write('\n'.join(restore_lines))
    
    print(f"[generate_restore_pc] ✅ 生成恢复逻辑: {args.out}")
    print(f"[generate_restore_pc]    - {len(pc_ranges)} 个PC范围")
    print(f"[generate_restore_pc]    - {len(restore_lines)} 行汇编代码")
    
    stats = lifetime_data.get('statistics', {})
    print(f"[generate_restore_pc]    - 最大活跃数: {stats.get('max_alive', 0)}")
    print(f"[generate_restore_pc]    - 平均活跃数: {stats.get('avg_alive', 0):.1f}")
    
    return 0

if __name__ == "__main__":
    exit(main())


