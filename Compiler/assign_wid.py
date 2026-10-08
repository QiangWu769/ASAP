#!/usr/bin/env python3
"""
WID 分配器：基于原始关键写分配全局唯一的 Write ID
支持函数边界分析，为跨函数的索引寻址生成唯一地址标识符
"""

import json
import argparse
from pathlib import Path
from typing import Optional, Dict, List

def load_function_boundaries(func_boundary_file: Path) -> Optional[List[Dict]]:
    """加载函数边界元数据"""
    if not func_boundary_file.exists():
        print(f"[assign_wid] 警告: 函数边界文件不存在: {func_boundary_file}")
        return None
    
    with open(func_boundary_file, 'r') as f:
        metadata = json.load(f)
    
    return metadata.get('functions', [])

def build_inst_to_pc_mapping(real_asm_path: Path) -> Dict[str, List[str]]:
    """
    从实际汇编构建指令特征→PC的映射
    
    策略：归一化每条指令，建立指令特征→实际PC的字典
    用于candidates通过指令内容查找实际PC
    """
    import re
    
    inst_to_pc = {}
    
    with open(real_asm_path, 'r') as f:
        for line in f:
            # 匹配格式: "    4678:	5c 42 0b 02 	mov.b	&0x020b,r12	;0x020b"
            if m := re.match(r'^\s*([0-9a-f]+):\s+[0-9a-f ]+\s+(.+)', line):
                pc = f"0x{m.group(1)}"
                inst = m.group(2).split(';')[0].strip()  # 去掉注释
                
                # 归一化指令作为key（统一大写）
                norm_inst = re.sub(r'\s+', ' ', inst).strip().upper()
                norm_inst = re.sub(r'#0X', '#', norm_inst)  # 统一立即数前缀
                norm_inst = re.sub(r',\s*', ',', norm_inst)  # 去掉逗号后空格
                norm_inst = re.sub(r'\t+', ' ', norm_inst)   # tab转空格
                
                # 可能有多个相同的指令，存储所有PC
                if norm_inst not in inst_to_pc:
                    inst_to_pc[norm_inst] = []
                inst_to_pc[norm_inst].append(pc)
    
    return inst_to_pc

def find_function_for_pc(pc_hex: str, functions: Optional[List[Dict]], pc_mapping: Optional[Dict[str, str]] = None) -> Optional[str]:
    """根据PC查找所属函数，支持PC映射"""
    if not functions:
        return None
    
    # 如果有PC映射，先转换
    if pc_mapping and pc_hex in pc_mapping:
        pc_hex = pc_mapping[pc_hex]
    
    try:
        pc = int(pc_hex, 16)
    except ValueError:
        return None
    
    for func in functions:
        if func['pc'] <= pc <= func['end_pc']:
            return func['name']
    
    return None

def assign_wids(normalized_candidates, function_boundaries: Optional[List[Dict]] = None, inst_to_pc_map: Optional[Dict[str, List[str]]] = None):
    """
    基于原始关键写分配 WID - 为每个关键写指令实例分配唯一 WID
    
    Args:
        normalized_candidates: 归一化后的关键写列表
        function_boundaries: 函数边界信息
        inst_to_pc_map: 指令→实际PC的映射（用于查找函数）
        
    Returns:
        wid_to_info: WID 到关键写信息的映射
        pc_to_wid: PC 到 WID 的映射（用于插桩时查找）
    """
    wid_to_info = {}
    pc_to_wid = {}
    next_wid = 1  # 从1开始，符合设计中的 1..K
    
    # 按PC顺序处理原始关键写，确保全局顺序
    sorted_candidates = sorted(normalized_candidates, key=lambda x: int(x['pc'], 16))
    
    print(f"[assign_wid] Processing {len(sorted_candidates)} normalized candidates")
    
    for candidate in sorted_candidates:
        wid = f"W{next_wid}"
        
        # 提取关键写信息
        pc = candidate['pc']
        mnemonic = candidate['mnemonic']
        operands = candidate['operands']
        original_operands = candidate.get('original_operands', '')
        write_site = candidate['write_site']
        width = candidate['width']
        normalized_from = candidate.get('normalized_from', '')
        
        # 生成 key（用于标识地址类型）和 target_addr
        mode = write_site['mode']
        target_addr = None
        
        # 查找当前PC所属的函数（通过目标地址匹配真实PC）
        function_name = None
        if function_boundaries and inst_to_pc_map:
            # 策略：在real中查找写入相同目标地址的指令
            # 对于 ABS 模式，用effective_addr
            # 对于 IDX 模式，用disp(base)
            target_pattern = None
            
            if mode == 'ABS':
                addr = write_site.get('effective_addr') or write_site.get('addr')
                if addr:
                    # 在real中找 "mov.* r*, &0xADDR" 或 "mov.* #*, &0xADDR"
                    addr_hex = addr.replace('0x', '').upper()
                    target_pattern = f"&0X{addr_hex}"
            elif mode == 'IDX':
                base = write_site.get('base', 'r1')
                disp = write_site.get('disp', 0)
                # 在real中找 "mov.* r*, disp(base)"
                target_pattern = f"{disp}({base.upper()})"
            
            # 在inst_to_pc_map中查找包含目标模式的指令
            if target_pattern:
                # 提取助记符基础部分（去掉.b/.w后缀）
                mnem_base = mnemonic.upper().split('.')[0]  # MOV 或 ADD
                
                # 特殊情况：ADD #1 可能被优化为 INC
                equivalent_mnems = [mnem_base]
                if mnem_base == 'ADD' and '#1' in operands.upper():
                    equivalent_mnems.append('INC')
                elif mnem_base == 'SUB' and '#1' in operands.upper():
                    equivalent_mnems.append('DEC')
                
                for inst_key, pcs in inst_to_pc_map.items():
                    # 检查是否包含目标模式
                    if target_pattern not in inst_key:
                        continue
                    
                    # 检查助记符（支持语义等价的指令）
                    matched = False
                    for mnem in equivalent_mnems:
                        if inst_key.startswith(mnem):
                            matched = True
                            break
                    
                    if not matched:
                        continue
                    
                    # 检查是否是写操作（目标在后面，可能有逗号和空格）
                    # 支持: "MOV R12,&0X05C0" 或 "INC 16(R1)"
                    if (inst_key.endswith(target_pattern) or 
                        f",{target_pattern}" in inst_key or 
                        f", {target_pattern}" in inst_key or
                        f" {target_pattern}" in inst_key):  # INC 16(R1)
                        real_pc = pcs[0]
                        function_name = find_function_for_pc(real_pc, function_boundaries)
                        break
        
        if mode == 'ABS':
            target_addr = write_site.get('effective_addr') or write_site.get('addr')
            if target_addr:
                key = f"abs_{target_addr.replace('0x', '')}"
            else:
                key = f"pc_{pc.replace('0x', '')}"
        elif mode == 'IDX':
            base = write_site.get('base', 'r1')
            disp = write_site.get('disp', 0)
            
            # 关键改进：为索引寻址加入函数上下文
            # 格式: "function_name::disp(base)" 或者仅 "disp(base)"（如果没有函数信息）
            if function_name:
                target_addr = f"{function_name}::{disp}({base})"
                key = f"func_{function_name}_{base}_{disp}"
            else:
                # 回退到旧方案（不带函数名）
                target_addr = f"{disp}({base})"
                if base == 'r1':
                    key = f"sp_{disp}"
                else:
                    key = f"idx_{base}_{disp}"
        else:
            # 其他模式，使用 PC 作为 key
            key = f"pc_{pc.replace('0x', '')}"
        
        # 存储 WID 信息
        wid_to_info[wid] = {
            'pc': pc,
            'mnemonic': mnemonic,
            'operands': operands,
            'original_operands': original_operands,
            'target_addr': target_addr,
            'mode': mode,
            'width': width,
            'key': key,
            'function': function_name,  # 新增：记录函数名
            'normalized_from': normalized_from
        }
        
        # 记录 PC 到 WID 的映射（每个 PC 对应唯一的 WID）
        pc_to_wid[pc] = wid
        
        next_wid += 1
    
    print(f"[assign_wid] Assigned {len(wid_to_info)} WIDs")
    print(f"[assign_wid] Unique PCs: {len(pc_to_wid)}")
    
    return wid_to_info, pc_to_wid

def generate_wid_map(wid_to_info, pc_to_wid, out_path: Path):
    """生成 WID 映射表"""
    wid_map = {
        'wid_to_info': wid_to_info,
        'pc_to_wid': pc_to_wid,
        'total_wids': len(wid_to_info),
        'unique_pcs': len(pc_to_wid)
    }
    
    out_path.write_text(json.dumps(wid_map, indent=2), encoding="utf-8")
    print(f"[assign_wid] Generated {out_path} with {len(wid_to_info)} WIDs")

def check_cross_function_addressing(wid_to_info: Dict, function_boundaries: List[Dict]):
    """检查并报告跨函数的索引寻址"""
    # 按 target_addr 分组（不包含函数名的部分）
    from collections import defaultdict
    addr_to_funcs = defaultdict(set)
    
    for wid, info in wid_to_info.items():
        if info['mode'] == 'IDX' and info.get('function'):
            # 提取不带函数名的地址部分
            target = info['target_addr']
            if '::' in target:
                bare_addr = target.split('::')[1]
            else:
                bare_addr = target
            
            addr_to_funcs[bare_addr].add(info['function'])
    
    # 找出跨函数的地址
    cross_func = {addr: funcs for addr, funcs in addr_to_funcs.items() if len(funcs) > 1}
    
    if cross_func:
        print(f"\n[assign_wid] ⚠️ 发现 {len(cross_func)} 个跨函数的索引寻址:")
        for addr, funcs in sorted(cross_func.items()):
            print(f"  {addr}: 在 {len(funcs)} 个函数中 ({', '.join(sorted(funcs)[:3])}{'...' if len(funcs) > 3 else ''})")
        print(f"[assign_wid] ✅ 已为这些地址添加函数上下文以区分不同内存位置")
    else:
        print(f"\n[assign_wid] ✅ 所有索引寻址都在各自的函数内，无跨函数冲突")

def main():
    ap = argparse.ArgumentParser(description="Assign WIDs to normalized critical writes")
    ap.add_argument("--candidates", default="build/normalized_candidates.json", help="normalized candidates JSON file")
    ap.add_argument("--functions", default="build/function_boundaries.json", help="function boundaries JSON file (optional)")
    ap.add_argument("--sym-asm", default="build/A_normalized.s", help="symbolic assembly (for PC mapping)")
    ap.add_argument("--real-asm", default="build/A_normalized_real.s", help="real assembly (for PC mapping)")
    ap.add_argument("--out", default="build/wid_map.json", help="output WID map JSON file")
    args = ap.parse_args()
    
    # 加载归一化后的关键写
    candidates_path = Path(args.candidates)
    if not candidates_path.exists():
        print(f"[assign_wid] ❌ Candidates file not found: {candidates_path}")
        return 1
    
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    print(f"[assign_wid] Loaded {len(candidates)} normalized candidates")
    
    # 加载函数边界（可选）
    functions_path = Path(args.functions)
    function_boundaries = load_function_boundaries(functions_path)
    
    # 建立指令→PC映射（从实际汇编）
    inst_to_pc_map = None
    real_asm_path = Path(args.real_asm)
    
    if real_asm_path.exists() and function_boundaries:
        print(f"[assign_wid] 建立指令→PC映射从 {real_asm_path.name} ...")
        inst_to_pc_map = build_inst_to_pc_mapping(real_asm_path)
        print(f"[assign_wid] ✅ 映射了 {len(inst_to_pc_map)} 个不同指令")
    
    if function_boundaries:
        print(f"[assign_wid] ✅ 加载了 {len(function_boundaries)} 个函数的边界信息")
    else:
        print(f"[assign_wid] ⚠️ 未加载函数边界信息，将使用简化的地址标识符")
    
    # 分配 WID
    wid_to_info, pc_to_wid = assign_wids(candidates, function_boundaries, inst_to_pc_map)
    
    # 检查跨函数的索引寻址
    if function_boundaries:
        check_cross_function_addressing(wid_to_info, function_boundaries)
    
    # 生成 WID 映射表
    generate_wid_map(wid_to_info, pc_to_wid, Path(args.out))
    
    print(f"[assign_wid] ✅ Successfully assigned WIDs")
    return 0

if __name__ == "__main__":
    exit(main())
