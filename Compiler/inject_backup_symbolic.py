#!/usr/bin/env python3
"""
符号化插桩脚本 - ASAP简化流程的核心

在归一化后的符号汇编上直接插桩，使用符号化的槽位名称。
每个关键写后面插入两条指令：
  1. MOV src, &__SLOT_xxx_S0/S1  （备份）
  2. MOV #1, &__COMMIT_Wn         （提交）

符号化命名规则：
  - 绝对地址: __SLOT_0x0200_S0 或 __SLOT_var_name_S0
  - 栈访问: __SLOT_func_sp_16_S0
  - 索引寻址: __SLOT_func_r12_8_S0
  - 提交位: __COMMIT_W1, __COMMIT_W2, ...
"""

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

def sanitize_symbol_name(name: str) -> str:
    """
    清理字符串以生成有效的汇编符号名
    function::16(r1) -> FUNCTION__16_R1
    0x0200 -> 0X0200
    """
    name = name.upper()
    name = name.replace("::", "__")
    name = name.replace("(", "_")
    name = name.replace(")", "")
    name = name.replace(" ", "")
    name = name.replace("&", "")
    name = name.replace("#", "")
    name = name.replace("0X", "0X")  # 保持0x格式
    # 确保以字母或下划线开头
    if name and name[0].isdigit():
        name = "ADDR_" + name
    return name

def generate_slot_symbol(addr: str, wid: str, slot_choice: str, mode: str) -> str:
    """
    生成槽位的符号名称
    
    Args:
        addr: 目标地址（可能包含函数名，如 "main::16(r1)" 或 "0x0200"）
        wid: Write ID（如 "W1"）
        slot_choice: "S0" 或 "S1"
        mode: 寻址模式（"ABS", "IDX"等）
    
    Returns:
        符号名称，如 "__SLOT_MAIN__16_R1_S0"
    """
    clean_addr = sanitize_symbol_name(addr)
    return f"__SLOT_{clean_addr}_{slot_choice}"

def generate_commit_symbol(wid: str) -> str:
    """生成提交位的符号名称"""
    return f"__COMMIT_{wid}"

def get_slot_choice(addr: str, wid: str, fram_layout: Dict) -> str:
    """
    从FRAM布局中获取槽位选择（S0或S1）
    如果没有布局信息，使用简单的奇偶轮换
    """
    if fram_layout:
        slot_mapping = fram_layout.get("slot_mapping", {})
        slot_key = f"{addr}_{wid}"
        slot_info = slot_mapping.get(slot_key, {})
        slot_choice = slot_info.get("slot", "S0")
        if slot_choice == 0 or slot_choice == "S0":
            return "S0"
        else:
            return "S1"
    
    # 回退：简单奇偶轮换（基于WID编号）
    try:
        wid_num = int(wid.replace("W", ""))
        return "S0" if wid_num % 2 == 1 else "S1"
    except:
        return "S0"

def build_backup_instruction(
    candidate: Dict,
    wid: str,
    wid_info: Dict,
    fram_layout: Optional[Dict] = None
) -> Tuple[Optional[str], Optional[str], str]:
    """
    为关键写构建符号化的保存PC和备份指令
    
    Returns:
        (save_pc_inst, backup_inst, slot_symbol)
    """
    # 从wid_info获取目标地址（包含函数名的完整标识符）
    target_addr = wid_info.get("target_addr", "")
    mode = wid_info.get("mode", "")
    width = wid_info.get("width", "w")  # 'b' 或 'w'
    
    if not target_addr:
        # 回退：从candidate提取
        write_site = candidate.get("write_site", {})
        mode = write_site.get("mode", "")
        if mode == "ABS":
            target_addr = write_site.get("effective_addr", "")
        elif mode == "IDX":
            base = write_site.get("base", "r1")
            disp = write_site.get("disp", 0)
            target_addr = f"{disp}({base})"
    
    if not target_addr:
        return None, None, ""
    
    # 确定槽位选择（S0或S1）
    slot_choice = get_slot_choice(target_addr, wid, fram_layout)
    
    # 生成符号化的槽位名称
    slot_symbol = generate_slot_symbol(target_addr, wid, slot_choice, mode)
    
    # 构建备份指令
    # 备份指令需要从目标地址读取当前值，然后写入槽位
    operands = candidate.get("operands", "")
    
    # 移除注释（以分号开始的部分）
    if ';' in operands:
        operands = operands.split(';')[0].strip()
    
    # 解析操作数（source, destination）
    ops_parts = [x.strip() for x in operands.split(",")]
    if len(ops_parts) != 2:
        return None, None, ""
    
    src, dst = ops_parts
    
    # 备份指令：MOV <destination>, &<slot_symbol>
    # 注意：备份的是写入的目标值，不是源值！
    # 实际上，我们需要备份的是"写之前"的旧值
    # 所以应该是：MOV <destination_before_write>, &<slot_symbol>
    
    # 根据寻址模式构建备份源
    write_site = candidate.get("write_site", {})
    if mode == "ABS":
        # 绝对地址：MOV &addr, &slot
        backup_src = dst  # 直接使用目标地址
    elif mode == "IDX":
        # 索引寻址：MOV disp(base), &slot
        base = write_site.get("base", "r1")
        disp = write_site.get("disp", 0)
        backup_src = f"{disp}({base})"
    else:
        # 其他模式
        backup_src = dst
    
    # 确定指令后缀（.b 或 .w）
    suffix = ".b" if width == "b" or width == 1 else ".w" if width == "w" or width == 2 else ""
    
    # 构建保存PC指令：MOV PC, &ASAP_CURRENT_PC
    # PC是R0寄存器
    save_pc_inst = "mov.w\tr0, &ASAP_CURRENT_PC"
    
    # 构建备份指令：读取目标地址的值，写入槽位
    backup_inst = f"mov{suffix}\t{backup_src}, &{slot_symbol}"
    
    return save_pc_inst, backup_inst, slot_symbol

def parse_function_boundaries_from_asm(asm_lines: List[str]) -> Dict[str, Tuple[int, int, bool]]:
    """
    从符号汇编中提取函数边界
    
    Returns:
        {function_name: (start_line, end_line, is_isr)}
    """
    # 定义不应该被插桩的函数黑名单
    NOINSTRUMENT_FUNCTIONS = {
        'uart_init', 'uart_putc', 'uart_puts', 'uart_putnum',
        'uart_put_hex', 'uart_puthex', 'uart_put_hex16',
        'timer_init', 'timer_restart',  # Timer配置函数
        'hw_init_cold',  # 硬件初始化函数
        # 可以添加更多需要排除的函数
    }
    
    functions = {}
    current_func = None
    func_start = 0
    is_isr = False
    
    for i, line in enumerate(asm_lines):
        # 检测ISR标记
        if current_func and re.search(r';\s*attributes:\s*interrupt', line, re.IGNORECASE):
            is_isr = True
            print(f"[inject_symbolic] 检测到ISR函数: {current_func}")
        
        # 检测noinstrument标记
        if current_func and re.search(r';\s*attributes:\s*noinstrument', line, re.IGNORECASE):
            is_isr = True  # 复用is_isr标志来跳过插桩
            print(f"[inject_symbolic] 检测到noinstrument函数: {current_func}")
        
        # 匹配函数标签：以标签开头，后跟冒号
        # 例如：main:, __do_copy_data:
        if m := re.match(r'^([A-Za-z_][A-Za-z0-9_]*):$', line.strip()):
            # 保存上一个函数
            if current_func:
                functions[current_func] = (func_start, i - 1, is_isr)
            
            # 开始新函数
            current_func = m.group(1)
            func_start = i
            is_isr = False
            
            # 检查是否在黑名单中
            if current_func in NOINSTRUMENT_FUNCTIONS:
                is_isr = True  # 复用is_isr标志来跳过插桩
                print(f"[inject_symbolic] 跳过UART/系统函数: {current_func}")
        
        # 匹配 .size 指令（GNU汇编的函数结束标记）
        elif current_func and re.match(r'^\s*\.size\s+' + re.escape(current_func), line):
            functions[current_func] = (func_start, i, is_isr)
            current_func = None
            is_isr = False
    
    # 处理最后一个函数
    if current_func:
        functions[current_func] = (func_start, len(asm_lines) - 1, is_isr)
    
    return functions

def find_function_for_line(line_no: int, functions: Dict[str, Tuple[int, int, bool]]) -> Optional[Tuple[str, bool]]:
    """找到给定行号所属的函数
    
    Returns:
        (function_name, is_isr) 或 None
    """
    for func_name, (start, end, is_isr) in functions.items():
        if start <= line_no <= end:
            return (func_name, is_isr)
    return None

def inject_symbolic_backup(
    asm_path: Path,
    wid_map_path: Path,
    fram_layout_path: Optional[Path],
    output_path: Path
) -> int:
    """
    在符号汇编上直接插桩，使用符号化的槽位名称
    
    Returns:
        插桩的指令数量
    """
    # 加载WID映射
    with open(wid_map_path, 'r') as f:
        wid_map = json.load(f)
    
    wid_to_info = wid_map.get("wid_to_info", {})
    pc_to_wid = wid_map.get("pc_to_wid", {})
    
    # 加载FRAM布局（可选）
    fram_layout = None
    if fram_layout_path and fram_layout_path.exists():
        with open(fram_layout_path, 'r') as f:
            fram_layout = json.load(f)
    
    # 读取汇编文件
    with open(asm_path, 'r') as f:
        lines = f.readlines()
    
    # 提取函数边界（从符号汇编）
    functions = parse_function_boundaries_from_asm(lines)
    isr_count = len([f for f in functions.values() if f[2]])  # f[2] is is_isr
    print(f"[inject_symbolic] 识别了 {len(functions)} 个函数，其中 {isr_count} 个是ISR")
    
    # 构建插桩计划：{line_no: (backup_inst, commit_inst)}
    injection_plan = {}
    isr_skipped = 0
    
    # 遍历所有WID，找到对应的行号并准备插桩
    for wid, info in wid_to_info.items():
        pc = info.get("pc", "")
        if not pc:
            continue
        
        # 在符号汇编中，PC可能是行号（如果是归一化后的）
        # 尝试将PC转换为行号
        try:
            # PC可能是十六进制地址或行号
            if pc.startswith("0x"):
                line_no = int(pc, 16)
            else:
                line_no = int(pc)
        except ValueError:
            print(f"[inject_symbolic] 警告: 无法解析PC {pc}")
            continue
        
        # 检查行号是否有效
        if line_no < 1 or line_no > len(lines):
            print(f"[inject_symbolic] 警告: 行号 {line_no} 超出范围 (1-{len(lines)})")
            continue
        
        # 将行号转换为0-based索引
        line_idx = line_no - 1
        
        # 检查该行是否在 ISR 中
        func_info = find_function_for_line(line_idx, functions)
        if func_info:
            func_name, is_isr = func_info
            if is_isr:
                print(f"[inject_symbolic] 跳过ISR函数 {func_name} 中的WID {wid} (line {line_no})")
                isr_skipped += 1
                continue
        
        # 查找对应的candidate信息（从WID info重建）
        # 对于IDX模式，需要从target_addr解析base和disp
        mode = info.get("mode", "")
        target_addr = info.get("target_addr", "")
        base = None
        disp = None
        
        if mode == "IDX" and target_addr:
            # 解析 "10(r1)" -> base="r1", disp=10
            import re
            m = re.match(r'(\d+)\(([rR]\d+)\)', target_addr)
            if m:
                disp = int(m.group(1))
                base = m.group(2).lower()
        
        candidate = {
            "pc": pc,
            "operands": info.get("operands", ""),
            "write_site": {
                "mode": mode,
                "effective_addr": target_addr,
                "base": base,
                "disp": disp,
            },
            "width": info.get("width", "w")
        }
        
        # 构建保存PC和备份指令
        save_pc_inst, backup_inst, slot_symbol = build_backup_instruction(
            candidate, wid, info, fram_layout
        )
        
        if save_pc_inst and backup_inst:
            injection_plan[line_idx] = (save_pc_inst, backup_inst, wid)
            print(f"[inject_symbolic] 计划在行 {line_no}: {wid} -> {slot_symbol}")
    
    print(f"[inject_symbolic] 共计划插桩 {len(injection_plan)} 个位置")
    
    # 从后往前插桩，避免行号偏移
    output_lines = lines.copy()
    for line_idx in sorted(injection_plan.keys(), reverse=True):
        save_pc_inst, backup_inst, wid = injection_plan[line_idx]
        
        # 获取原始指令（用于注释）
        original_line = output_lines[line_idx].strip()
        
        # 在原始指令后插入保存PC和备份指令
        # 格式：
        #   <original instruction>           ; 关键写
        #   <save PC instruction>            ; 保存当前PC
        #   <backup instruction>             ; 备份数据
        output_lines.insert(line_idx + 1, f"\t{save_pc_inst}\t; ASAP save PC for {wid}\n")
        output_lines.insert(line_idx + 2, f"\t{backup_inst}\t; ASAP backup for {wid}\n")
    
    # 写入输出文件
    with open(output_path, 'w') as f:
        f.writelines(output_lines)
    
    print(f"[inject_symbolic] ✅ 插桩完成，插入了 {len(injection_plan)} 组备份指令")
    print(f"[inject_symbolic] 跳过(ISR): {isr_skipped} 个")
    print(f"[inject_symbolic] 输出: {output_path}")
    
    return len(injection_plan)

def main():
    ap = argparse.ArgumentParser(description="符号化插桩 - ASAP简化流程")
    ap.add_argument("asm", help="归一化后的符号汇编文件")
    ap.add_argument("--wid-map", required=True, help="WID映射文件")
    ap.add_argument("--fram-layout", help="FRAM布局文件（可选，用于槽位选择）")
    ap.add_argument("--out", required=True, help="输出的插桩汇编文件")
    args = ap.parse_args()
    
    fram_layout_path = Path(args.fram_layout) if args.fram_layout else None
    
    inject_symbolic_backup(
        Path(args.asm),
        Path(args.wid_map),
        fram_layout_path,
        Path(args.out)
    )

if __name__ == "__main__":
    main()

