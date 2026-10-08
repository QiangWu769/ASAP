#!/usr/bin/env python3
"""
生成完整的ASAP恢复逻辑（基于Lifetime分析）

按照ASAP设计：
1. 找W*：最大的W使得∀A: L_A[W]=1 ⇒ C[A,last_write≤W]=1
2. 计算U(W*) = {A | L_A[W*]=1}
3. 对每个A∈U(W*)，恢复last_write(A,≤W*)的值

Lifetime数据格式：
{
  "pc_ranges": {
    "[start, end]": {
      "addresses": ["0x1c00", "0x1c02", ...],  # L_A[W]=1的地址集合
      "start_pc": 35300,
      "end_pc": 35319
    }
  }
}
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple

def sanitize_symbol(name: str) -> str:
    """清理符号名，与fram_layout_symbolic.py保持一致"""
    name = name.upper()
    name = name.replace("::", "__")
    name = name.replace("(", "_")
    name = name.replace(")", "")
    name = name.replace(" ", "")
    name = name.replace("&", "")
    name = name.replace("#", "")
    return name

def find_lifetime_for_wid(wid: int, wid_map: Dict, nextpc_table: Dict, lifetime_data: Dict) -> Set[str]:
    """
    查找WID对应的活跃地址集合（L_A[W]=1的所有A）
    
    支持两种格式：
    1. 新格式（推荐）：wid_to_alive 直接映射
    2. 旧格式：基于 NextPC 和 pc_ranges
    """
    wid_key = f"W{wid}"
    
    # 优先使用新格式（wid_to_alive）
    wid_to_alive = lifetime_data.get("wid_to_alive", {})
    if wid_key in wid_to_alive:
        return set(wid_to_alive[wid_key])
    
    # 回退到旧格式（基于 NextPC）
    nextpc_str = nextpc_table.get("nextpc_table", {}).get(wid_key, "0x0")
    if nextpc_str.startswith("0x"):
        pc = int(nextpc_str, 16)
    else:
        pc = int(nextpc_str)
    
    # 在lifetime的pc_ranges中查找包含该PC的range
    pc_ranges = lifetime_data.get("pc_ranges", {})
    
    for range_key, range_data in pc_ranges.items():
        start_pc = range_data.get("start_pc", 0)
        end_pc = range_data.get("end_pc", 0)
        
        if start_pc <= pc <= end_pc:
            # 找到了！返回该range的所有活跃地址
            return set(range_data.get("addresses", []))
    
    # 如果没找到，保守策略：返回空集（或该WID写的地址）
    wid_info = wid_map["wid_to_info"].get(wid_key, {})
    target_addr = wid_info.get("target_addr", "")
    return {target_addr} if target_addr else set()

def find_last_write(addr: str, up_to_wid: int, wid_map: Dict) -> Tuple[int, str]:
    """
    找到地址A在≤W范围内的last_write
    
    返回: (last_wid, slot)
    """
    addr_lower = addr.lower().replace("0x", "")
    
    # 倒序查找写这个地址的WID
    for w in range(up_to_wid, 0, -1):
        w_key = f"W{w}"
        w_info = wid_map["wid_to_info"].get(w_key, {})
        w_target = w_info.get("target_addr", "").lower().replace("0x", "")
        
        # 地址匹配？
        if addr_lower == w_target:
            return w, w_key
    
    # 没找到（可能是初始值）
    return 0, None

def compute_recovery_set(wid: int, wid_map: Dict, nextpc_table: Dict, 
                        lifetime_data: Dict, fram_layout: Dict) -> List[Dict]:
    """
    计算WID=W时的恢复集合U(W)
    
    U(W) = {A | L_A[W]=1}
    
    对每个A∈U(W)，找last_write(A,≤W)，确定恢复的slot
    """
    # 1. 获取U(W) - 活跃地址集合
    alive_addrs = find_lifetime_for_wid(wid, wid_map, nextpc_table, lifetime_data)
    
    if not alive_addrs:
        # Fallback: 只恢复这个WID写的地址
        wid_key = f"W{wid}"
        wid_info = wid_map["wid_to_info"].get(wid_key, {})
        target_addr = wid_info.get("target_addr", "")
        if target_addr:
            alive_addrs = {target_addr}
    
    # 2. 对每个A∈U(W)，找last_write并确定slot
    recovery_items = []
    slot_mapping = fram_layout.get("slot_mapping", {})
    
    for addr in alive_addrs:
        # 找到last_write(A, ≤W)
        last_w, last_w_key = find_last_write(addr, wid, wid_map)
        
        if last_w == 0:
            # 没有写过这个地址，可能是初始值，跳过
            continue
        
        # 查找该(addr, last_w)对应的slot
        addr_clean = addr.replace("0x", "").lower()
        slot_key = f"0x{addr_clean}_{last_w_key}"
        
        slot_info = slot_mapping.get(slot_key, {})
        if not slot_info:
            # Fallback: 尝试大小写/格式变化
            for key, info in slot_mapping.items():
                if last_w_key in key and addr_clean in key.lower():
                    slot_info = info
                    break
        
        if slot_info:
            recovery_items.append({
                "addr": addr,
                "last_wid": last_w,
                "slot": slot_info.get("slot", "S0"),
                "width": 2  # 默认2字节，实际应从wid_info获取
            })
    
    return recovery_items

def generate_restore_asm(wid_map: Dict, nextpc_table: Dict, 
                        lifetime_data: Dict, fram_layout: Dict) -> List[str]:
    """
    生成完整的恢复逻辑汇编代码
    """
    lines = []
    total_wids = len(wid_map["wid_to_info"])
    
    lines.append("\t.global\t_asap_restore")
    lines.append("\t.section\t.text")
    lines.append("")
    lines.append("; ===== ASAP恢复逻辑（完整版：基于Lifetime） =====")
    lines.append("_asap_restore:")
    lines.append("\t; 保存寄存器")
    lines.append("\tPUSH.W\tR12")
    lines.append("\tPUSH.W\tR13")
    lines.append("\tPUSH.W\tR14")
    lines.append("\tPUSH.W\tR15")
    lines.append("")
    
    lines.append("\t; ===== 步骤1: 找W* (最后已提交的写) =====")
    lines.append(f"\tMOV.W\t#{total_wids}, R13\t; 从W{total_wids}开始倒序")
    lines.append("")
    
    lines.append("_find_wstar_loop:")
    lines.append("\tCMP.W\t#0, R13")
    lines.append("\tJEQ\t_cold_start_from_restore\t; 所有未提交，冷启动")
    lines.append("")
    
    lines.append("\t; 计算C[W]的地址: __COMMIT_BASE + (R13-1)*2")
    lines.append("\tMOV.W\tR13, R14")
    lines.append("\tDEC.W\tR14\t\t\t; R14 = wid - 1")
    lines.append("\tADD.W\tR14, R14\t\t; R14 = (wid-1) * 2")
    lines.append("\tMOV.W\t#__COMMIT_W1, R15\t; 提交位基地址")
    lines.append("\tADD.W\tR14, R15\t\t; R15 = &C[wid]")
    lines.append("\tMOV.B\t@R15, R15\t\t; R15 = C[wid]")
    lines.append("\tCMP.B\t#1, R15")
    lines.append("\tJEQ\t_find_wstar_done\t; 找到了")
    lines.append("")
    lines.append("\tDEC.W\tR13\t\t\t; 继续检查W-1")
    lines.append("\tJMP\t_find_wstar_loop")
    lines.append("")
    
    lines.append("_find_wstar_done:")
    lines.append("\tMOV.W\tR13, R12\t\t; R12 = W*")
    lines.append("")
    
    lines.append("\t; ===== 步骤2: 按U(W*)恢复活跃变量 =====")
    lines.append("\t; 使用switch-case查找对应的恢复代码")
    lines.append("")
    
    # 生成每个WID的恢复代码
    for wid in range(1, min(total_wids + 1, 250)):  # 限制数量避免过大
        wid_key = f"W{wid}"
        
        lines.append(f"_check_W{wid}:")
        lines.append(f"\tCMP.W\t#{wid}, R12")
        lines.append(f"\tJNE\t_check_W{wid+1}")
        
        # 计算该WID的恢复集合
        recovery_items = compute_recovery_set(wid, wid_map, nextpc_table, lifetime_data, fram_layout)
        
        if recovery_items:
            lines.append(f"\t; 恢复W{wid}的U(W)集合: {len(recovery_items)}个活跃地址")
            for item in recovery_items:
                addr = item["addr"]
                slot = item["slot"]
                addr_sym = sanitize_symbol(addr)
                
                # 生成恢复指令
                slot_sym = f"__SLOT_ADDR_{addr_sym}_{slot}"
                lines.append(f"\tMOV.W\t&{slot_sym}, &{addr}\t; 恢复{addr}")
        else:
            lines.append(f"\t; W{wid}无活跃变量需恢复")
        
        lines.append(f"\tJMP\t_restore_done")
        lines.append("")
    
    # Fallback: 未知WID
    lines.append(f"_check_W{min(total_wids + 1, 250)}:")
    lines.append("\t; 未知WID，直接跳转")
    lines.append("\tJMP\t_restore_done")
    lines.append("")
    
    # 步骤3: 跳转到NextPC
    lines.append("_restore_done:")
    lines.append("\t; ===== 步骤3: 查找并跳转到NextPC[W*] =====")
    lines.append("\t; R12 = W*")
    lines.append("\t; 先恢复寄存器R13-R15（暂存PC到栈上）")
    lines.append("\tPOP.W\tR15")
    lines.append("\tPOP.W\tR14")
    lines.append("\tPOP.W\tR13")
    lines.append("")
    lines.append("\t; 使用R12计算NextPC")
    lines.append("\tDEC.W\tR12\t\t; R12 = W* - 1")
    lines.append("\tADD.W\tR12, R12\t\t; R12 = (W*-1) * 2")
    lines.append("\tADD.W\t#ASAP_NextPC, R12\t; R12 = &ASAP_NextPC[W*-1]")
    lines.append("\tMOV.W\t@R12, R11\t\t; R11 = NextPC值（使用R11避免覆盖R12）")
    lines.append("")
    lines.append("\t; 恢复最后一个寄存器R12")
    lines.append("\tPOP.W\tR12")
    lines.append("")
    lines.append("\t; 跳转到NextPC（使用R11寄存器间接跳转，不破坏内存）")
    lines.append("\tBR\tR11\t\t; 跳转到NextPC[W*]")
    lines.append("")
    
    # 冷启动路径
    lines.append("_cold_start_from_restore:")
    lines.append("\t; 所有提交位都是0，执行冷启动")
    lines.append("\tPOP.W\tR15")
    lines.append("\tPOP.W\tR14")
    lines.append("\tPOP.W\tR13")
    lines.append("\tPOP.W\tR12")
    lines.append("\tCALL\t#main")
    lines.append("_halt:")
    lines.append("\tJMP\t_halt")
    lines.append("")
    
    return lines

def main():
    parser = argparse.ArgumentParser(description="生成完整的ASAP恢复逻辑")
    parser.add_argument("--wid-map", required=True, help="WID映射文件")
    parser.add_argument("--nextpc", required=True, help="NextPC表")
    parser.add_argument("--lifetime", required=True, help="Lifetime数据")
    parser.add_argument("--fram-layout", required=True, help="FRAM布局")
    parser.add_argument("--out", required=True, help="输出汇编文件")
    args = parser.parse_args()
    
    # 加载输入数据
    with open(args.wid_map, 'r') as f:
        wid_map = json.load(f)
    
    with open(args.nextpc, 'r') as f:
        nextpc_table = json.load(f)
    
    with open(args.lifetime, 'r') as f:
        lifetime_data = json.load(f)
    
    with open(args.fram_layout, 'r') as f:
        fram_layout = json.load(f)
    
    print(f"[generate_restore] 加载数据:")
    print(f"  WID总数: {len(wid_map['wid_to_info'])}")
    print(f"  NextPC条目: {len(nextpc_table.get('nextpc_table', {}))}")
    print(f"  Lifetime范围: {len(lifetime_data.get('pc_ranges', {}))}")
    print(f"  FRAM槽位: {len(fram_layout.get('slot_mapping', {}))}")
    
    # 生成恢复逻辑
    asm_lines = generate_restore_asm(wid_map, nextpc_table, lifetime_data, fram_layout)
    
    # 写出文件
    output_path = Path(args.out)
    with open(output_path, 'w') as f:
        f.write('\n'.join(asm_lines))
    
    print(f"[generate_restore] ✅ 恢复逻辑已生成: {output_path}")
    print(f"[generate_restore] 代码行数: {len(asm_lines)}")
    
    return 0

if __name__ == "__main__":
    exit(main())
