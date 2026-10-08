#!/usr/bin/env python3
"""
生成符号化的ASAP恢复逻辑

实现算法：
1. 选择最大安全继续点 W*：max{W | ∀A: L_A[W]=1 ⇒ C[A, last_write(A, ≤W)] = 1}
2. 计算需要恢复的地址集合 U(W*) = {A | L_A[W*] = 1}
3. 对每个 A ∈ U(W*)：
   - w_last = last_write_of(A, ≤W*)
   - slot = slot_of(A, w_last)
   - 从 slot 恢复值到 A
4. PC ← NextPC[W*]

使用符号化表示，便于阅读和维护。
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple

def sanitize_symbol(name: str) -> str:
    """清理符号名，与fram_layout_symbolic.py保持一致"""
    name = name.upper()
    name = name.replace("::", "__")
    name = name.replace("(", "_")
    name = name.replace(")", "")
    name = name.replace(" ", "")
    name = name.replace("&", "")
    name = name.replace("#", "")
    # 确保以字母或下划线开头
    if name and name[0].isdigit():
        name = "ADDR_" + name
    return name

def generate_find_wstar(wid_map: Dict, metadata: Dict) -> List[str]:
    """
    生成查找W*的汇编代码
    
    算法：从K向下扫描，找到最大的W满足：
    ∀A: L_A[W]=1 ⇒ C[A, last_write(A, ≤W)] = 1
    
    简化实现：扫描所有提交位，找到最大已提交的连续WID
    """
    lines = []
    total_wids = len(wid_map.get("wid_to_info", {}))
    
    lines.append("\t; ===== 步骤1: 查找最大安全继续点 W* =====")
    lines.append("\t;")
    lines.append("\t; 策略: 从最大WID向下扫描，找到最大的连续已提交WID")
    lines.append("\t; R12 = W* (返回值)")
    lines.append("\t; R13 = 当前检查的WID")
    lines.append("\t; R14 = 临时地址")
    lines.append("\t; R15 = 临时值")
    lines.append("")
    
    lines.append(f"\tMOV.W\t#0, R12\t\t\t; W* = 0 (初始化)")
    lines.append(f"\tMOV.W\t#{total_wids}, R13\t\t; 从最大WID开始")
    lines.append("")
    
    lines.append("_find_wstar_loop:")
    lines.append("\tCMP.W\t#0, R13\t\t\t; 检查是否到达WID=0")
    lines.append("\tJEQ\t_find_wstar_done")
    lines.append("")
    
    lines.append("\t; 检查 C[W] 是否已提交")
    lines.append("\t; 使用符号__COMMIT_Wn直接访问")
    
    # 生成每个WID的检查代码
    for wid_num in range(1, min(total_wids + 1, 21)):
        wid = f"W{wid_num}"
        lines.append(f"\tCMP.W\t#{wid_num}, R13")
        lines.append(f"\tJNE\t_check_next_{wid_num}")
        lines.append(f"\tMOV.B\t&__COMMIT_{wid}, R15\t; 读取C[{wid}]")
        lines.append(f"\tCMP.B\t#1, R15")
        lines.append(f"\tJNE\t_wstar_not_found")
        lines.append(f"\tMOV.W\tR13, R12\t\t; W* = {wid}")
        lines.append(f"\tJMP\t_find_wstar_done")
        lines.append(f"_check_next_{wid_num}:")
    
    lines.append("")
    lines.append("\t; 如果没有匹配，尝试下一个")
    lines.append("\tMOV.B\t#0, R15\t\t\t; 默认未提交")
    lines.append("\tCMP.B\t#1, R15")
    lines.append("\tJNE\t_wstar_not_found\t\t; 如果未提交，继续向下找")
    lines.append("")
    
    lines.append("\t; 找到已提交的WID")
    lines.append("\tMOV.W\tR13, R12\t\t; W* = 当前WID")
    lines.append("\tJMP\t_find_wstar_done")
    lines.append("")
    
    lines.append("_wstar_not_found:")
    lines.append("\tDEC.W\tR13\t\t\t; WID--")
    lines.append("\tJMP\t_find_wstar_loop")
    lines.append("")
    
    lines.append("_find_wstar_done:")
    lines.append("\t; R12 现在包含 W*")
    lines.append("\tCMP.W\t#0, R12")
    lines.append("\tJEQ\t_restore_cold_start\t; W*=0，冷启动")
    lines.append("")
    
    return lines

def generate_restore_addresses(
    wid_map: Dict,
    fram_layout: Dict,
    lifetime_data: Dict
) -> List[str]:
    """
    生成恢复地址的汇编代码
    
    对每个地址A ∈ U(W*)：
    1. 计算 last_write = last_write_of(A, ≤W*)
    2. 获取 slot = slot_of(A, last_write)
    3. 从 slot 恢复值到 A
    """
    lines = []
    
    wid_to_info = wid_map.get("wid_to_info", {})
    slot_mapping = fram_layout.get("slot_mapping", {})
    
    # 按地址分组WID
    from collections import defaultdict
    addr_to_wids = defaultdict(list)
    for wid, info in wid_to_info.items():
        target_addr = info.get("target_addr", "")
        if target_addr:
            addr_to_wids[target_addr].append(wid)
    
    lines.append("\t; ===== 步骤2: 恢复状态（按需恢复 U(W*)）=====")
    lines.append("\t;")
    lines.append("\t; 策略: 对每个地址A，如果L_A[W*]=1，则恢复")
    lines.append("\t; 简化实现: 恢复所有最近写入的槽位")
    lines.append("")
    
    # 为每个地址生成恢复代码
    for i, (addr, wids) in enumerate(sorted(addr_to_wids.items())[:20]):  # 限制前20个
        # 获取该地址的最后一个WID（假设按顺序）
        last_wid = wids[-1] if wids else None
        if not last_wid:
            continue
        
        # 获取槽位选择
        slot_key = f"{addr}_{last_wid}"
        slot_info = slot_mapping.get(slot_key, {})
        slot_choice = slot_info.get("slot", "S0")
        
        # 生成符号化的槽位名称
        clean_addr = sanitize_symbol(addr)
        slot_symbol = f"__SLOT_{clean_addr}_{slot_choice}"
        
        # 生成目标地址（如果是绝对地址）
        if addr.startswith("0x") or addr.startswith("ADDR_0X"):
            target_addr_str = f"&{addr}"
        else:
            # 索引寻址或其他复杂模式，简化为注释
            target_addr_str = f"; {addr} (需要运行时计算)"
        
        lines.append(f"\t; 恢复地址 {addr} (WID={last_wid})")
        lines.append(f"\tMOV.W\t&{slot_symbol}, R14\t; 从槽位读取")
        
        # 只有绝对地址才能直接写回
        if target_addr_str.startswith("&0x"):
            lines.append(f"\tMOV.W\tR14, {target_addr_str}\t; 写回目标地址")
        else:
            lines.append(f"\t; TODO: 写回到 {addr}")
        lines.append("")
    
    return lines

def generate_jump_to_nextpc(nextpc_table: Dict, wid_map: Dict) -> List[str]:
    """
    生成跳转到NextPC[W*]的代码
    
    使用查找表实现：
    PC ← NextPC[W*]
    """
    lines = []
    
    total_wids = len(wid_map.get("wid_to_info", {}))
    
    lines.append("\t; ===== 步骤3: 跳转到NextPC[W*] =====")
    lines.append("\t;")
    lines.append("\t; R12 = W*")
    lines.append("")
    
    lines.append("\t; 使用查找表获取NextPC")
    lines.append("\tCMP.W\t#0, R12")
    lines.append("\tJEQ\t_restore_cold_start\t; W*=0，冷启动")
    lines.append("")
    
    # 生成跳转表
    lines.append("\t; NextPC查找表（使用符号）")
    for wid_num in range(1, min(total_wids + 1, 21)):  # 限制前20个
        wid = f"W{wid_num}"
        nextpc_addr = nextpc_table.get(wid, "0x0000")
        
        lines.append(f"\tCMP.W\t#{wid_num}, R12")
        lines.append(f"\tJEQ\t_restore_to_{wid}")
    
    lines.append("")
    lines.append("\t; 默认：冷启动")
    lines.append("\tJMP\t_restore_cold_start")
    lines.append("")
    
    # 生成每个WID的恢复点
    for wid_num in range(1, min(total_wids + 1, 21)):
        wid = f"W{wid_num}"
        nextpc_addr = nextpc_table.get(wid, "0x0000")
        
        lines.append(f"_restore_to_{wid}:")
        lines.append(f"\t; 跳转到NextPC[{wid}] = {nextpc_addr}")
        lines.append(f"\t; 恢复上下文后跳转")
        lines.append(f"\tPOP\tR15")
        lines.append(f"\tPOP\tR14")
        lines.append(f"\tPOP\tR13")
        lines.append(f"\tPOP\tR12")
        lines.append(f"\tBR\t#{nextpc_addr}\t; 跳转到NextPC")
        lines.append("")
    
    return lines

def generate_restore_function_complete(
    wid_map: Dict,
    fram_layout: Dict,
    nextpc_table: Dict,
    lifetime_data: Dict,
    metadata: Dict
) -> str:
    """生成完整的恢复函数"""
    
    lines = []
    
    lines.append("; ===========================================================")
    lines.append("; ASAP 运行时恢复逻辑 - 符号化版本")
    lines.append("; Auto-generated by generate_restore_symbolic.py")
    lines.append(";")
    lines.append("; 实现断电后状态恢复：")
    lines.append(";   1. 选择最大安全继续点 W*")
    lines.append(";   2. 按需恢复 U(W*)")
    lines.append(";   3. 跳转到 NextPC[W*]")
    lines.append("; ===========================================================")
    lines.append("")
    
    lines.append("\t.global\t_asap_restore")
    lines.append("\t.section\t.text")
    lines.append("")
    
    lines.append("_asap_restore:")
    lines.append("\t; 保存上下文")
    lines.append("\tPUSH\tR12")
    lines.append("\tPUSH\tR13")
    lines.append("\tPUSH\tR14")
    lines.append("\tPUSH\tR15")
    lines.append("")
    
    # 步骤1: 查找W*
    lines.extend(generate_find_wstar(wid_map, metadata))
    
    # 步骤2: 恢复状态
    lines.extend(generate_restore_addresses(wid_map, fram_layout, lifetime_data))
    
    # 步骤3: 跳转到NextPC
    lines.extend(generate_jump_to_nextpc(nextpc_table, wid_map))
    
    # 冷启动处理
    lines.append("_restore_cold_start:")
    lines.append("\t; 冷启动：跳转到main函数")
    lines.append("\tPOP\tR15")
    lines.append("\tPOP\tR14")
    lines.append("\tPOP\tR13")
    lines.append("\tPOP\tR12")
    lines.append("\tCALL\t#main")
    lines.append("_halt:")
    lines.append("\tJMP\t_halt\t\t\t; 永久循环")
    lines.append("")
    
    lines.append("; ===========================================================")
    lines.append("; End of ASAP Restore Logic")
    lines.append("; ===========================================================")
    lines.append("")
    
    return "\n".join(lines)

def main():
    ap = argparse.ArgumentParser(description="生成符号化的ASAP恢复逻辑")
    ap.add_argument("--wid-map", required=True, help="WID映射文件")
    ap.add_argument("--fram-layout", required=True, help="FRAM布局文件")
    ap.add_argument("--nextpc", required=True, help="NextPC表文件")
    ap.add_argument("--lifetime", help="生命周期数据文件（可选）")
    ap.add_argument("--metadata", help="完整元数据文件（可选）")
    ap.add_argument("--out", default="build/asap_restore.s", help="输出恢复汇编文件")
    args = ap.parse_args()
    
    # 加载数据
    print("[generate_restore] 加载数据...")
    
    with open(args.wid_map, 'r') as f:
        wid_map = json.load(f)
    
    with open(args.fram_layout, 'r') as f:
        fram_layout = json.load(f)
    
    with open(args.nextpc, 'r') as f:
        nextpc_data = json.load(f)
        nextpc_table = nextpc_data.get("nextpc_table", {})
    
    lifetime_data = {}
    if args.lifetime and Path(args.lifetime).exists():
        with open(args.lifetime, 'r') as f:
            lifetime_data = json.load(f)
    
    metadata = {}
    if args.metadata and Path(args.metadata).exists():
        with open(args.metadata, 'r') as f:
            metadata = json.load(f)
    
    print(f"[generate_restore] 数据加载完成")
    print(f"  - WID数量: {len(wid_map.get('wid_to_info', {}))}")
    print(f"  - 槽位映射: {len(fram_layout.get('slot_mapping', {}))}")
    print(f"  - NextPC条目: {len(nextpc_table)}")
    
    # 生成恢复函数
    print(f"[generate_restore] 生成恢复汇编代码...")
    restore_asm = generate_restore_function_complete(
        wid_map,
        fram_layout,
        nextpc_table,
        lifetime_data,
        metadata
    )
    
    # 写入文件
    output_path = Path(args.out)
    with open(output_path, 'w') as f:
        f.write(restore_asm)
    
    print(f"[generate_restore] ✅ 恢复逻辑已生成: {output_path}")
    print(f"[generate_restore]    - 函数: _asap_restore")
    print(f"[generate_restore]    - 大小: {len(restore_asm)} 字节")
    
    return 0

if __name__ == "__main__":
    exit(main())

