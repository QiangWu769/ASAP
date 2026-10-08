#!/usr/bin/env python3
"""
分析归一化后的汇编文件，识别关键写指令
"""
import argparse
import json
import re
from pathlib import Path

# 正则表达式
RE_LINE3 = re.compile(r"^\s*([0-9a-fA-F]+):\s+([A-Za-z.]+)\s*(.*)$")
RE_ABS = re.compile(r"&0x([0-9a-fA-F]+)")
RE_SYMBOL = re.compile(r"&([A-Za-z_][A-Za-z0-9_]*)")
RE_IDX = re.compile(r"(-?\d+)\(([Rr][0-9]+)\)")
RE_IND = re.compile(r"@r([0-9]+)")

# 关键写指令
WRITE_DST_MNEMS = {"mov", "bis", "bic", "xor", "add", "sub", "and", "or"}

def load_symbol_map(symbol_file_path):
    """加载符号映射文件"""
    symbol_map = {}
    addr_to_symbol = {}
    
    with open(symbol_file_path, 'r') as f:
        for line in f:
            match = re.match(r'PROVIDE\((\w+)\s*=\s*0x([0-9A-Fa-f]+)\);', line.strip())
            if match:
                symbol = match.group(1)
                addr = match.group(2).lower()
                symbol_map[symbol] = addr
                if addr not in addr_to_symbol:
                    addr_to_symbol[addr] = symbol
    
    return symbol_map, addr_to_symbol

def parse_asm(asm_path):
    """解析汇编文件"""
    lines = asm_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    pc2line = {}
    pcs = []
    
    for i, line in enumerate(lines):
        # 如果有PC地址，使用PC地址
        if m := RE_LINE3.match(line):
            pc = int(m.group(1), 16)
            pc2line[pc] = line
            pcs.append(pc)
        else:
            # 如果没有PC地址，使用行号作为"PC"
            pc = i + 1
            pc2line[pc] = line
            pcs.append(pc)
    
    return lines, pc2line, pcs

def parse_mnem_ops_from_line(line):
    """从汇编行中解析助记符和操作数"""
    if m := RE_LINE3.match(line):
        mnem = m.group(2)
        ops = m.group(3)
        return mnem, ops
    else:
        # 处理没有PC地址的行
        line_clean = line.strip()
        if not line_clean or line_clean.startswith(';') or line_clean.startswith('.'):
            return None, None
        
        parts = line_clean.split()
        if len(parts) >= 2:
            mnem = parts[0]
            ops = ' '.join(parts[1:])
            return mnem, ops
    return None, None

def classify_addr(addr, plat_cfg):
    """分类地址类型"""
    if addr < 0x2000:
        return "MMIO"
    elif addr < 0x4000:
        return "RAM"
    else:
        return "FRAM"

def analyze_normalized_asm(asm_path, symbol_file_path, plat_cfg, out_json):
    """分析归一化后的汇编文件"""
    symbol_map, addr_to_symbol = load_symbol_map(symbol_file_path)
    lines, pc2line, pcs = parse_asm(asm_path)
    
    results = []
    
    for pc in pcs:
        line = pc2line[pc]
        mnem, ops = parse_mnem_ops_from_line(line)
        if not mnem or not ops or "," not in ops:
            continue
        
        mnem_l = mnem.lower()
        base_m = mnem_l.split(".")[0]
        if base_m not in WRITE_DST_MNEMS:
            continue
        
        src, dst = [x.strip() for x in ops.rsplit(",", 1)]
        ws = {"mode": "REG", "base": None, "disp": None, "effective_addr": None}
        dst_mode = "REG"
        base = None
        abs_addr = None
        
        # 检查绝对地址
        if m := RE_ABS.search(dst):
            dst_mode = "ABS"
            abs_addr = int(m.group(1), 16)
            ws.update({"mode": "ABS", "effective_addr": f"0x{abs_addr:04x}"})
        # 检查符号地址
        elif m := RE_SYMBOL.search(dst):
            symbol = m.group(1)
            if symbol in symbol_map:
                dst_mode = "ABS"
                abs_addr = int(symbol_map[symbol], 16)
                ws.update({"mode": "ABS", "effective_addr": f"0x{abs_addr:04x}"})
            else:
                # 跳过没有地址映射的符号（用户定义的变量）
                continue
        # 检查索引寻址
        elif m := RE_IDX.search(dst):
            dst_mode = "IDX"
            base = m.group(2).lower()
            ws.update({"mode": "IDX", "base": base, "disp": int(m.group(1))})
        # 检查间接寻址
        elif m := RE_IND.search(dst):
            dst_mode = "IND"
            base = "r" + m.group(1)
            ws.update({"mode": "IND", "base": base})
        else:
            # 非内存写，跳过
            continue
        
        width = 1 if ".b" in mnem_l else 2
        entry = {
            "pc": f"0x{pc:04x}",
            "mnemonic": mnem_l,
            "operands": ops,
            "width": width,
            "is_memory_write": True,
            "requires_backup": False,
            "write_site": ws,
            "value_origin": {"kind": "UNKNOWN"},
            "trace_chain": []
        }
        
        # 绝对地址直接写
        if dst_mode == "ABS":
            region = classify_addr(abs_addr, plat_cfg)
            entry["target"] = region
            entry["requires_backup"] = (region in ("RAM", "MMIO"))
            results.append(entry)
            continue
        
        # 栈写（以 r1 为基址）
        if dst_mode == "IDX" and base == "r1":
            entry["target"] = "STACK"
            entry["requires_backup"] = True
            results.append(entry)
            continue
        
        # 其他内存写
        if dst_mode in ("IDX", "IND"):
            entry["target"] = "MEMORY"
            entry["requires_backup"] = True
            results.append(entry)
            continue
    
    # 保存结果
    with open(out_json, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"[analyze_normalized_asm] 分析了 {len(results)} 个关键写指令 → {out_json}")
    return results

def main():
    ap = argparse.ArgumentParser(description="分析归一化后的汇编文件")
    ap.add_argument("asm_path", help="归一化后的汇编文件路径")
    ap.add_argument("--symbol-file", default="Runtime/src/port/msp430/msp430fr5969_symbols.ld", help="符号映射文件")
    ap.add_argument("--out", default="build/candidates_normalized.json", help="输出文件")
    ap.add_argument("--mcu", default="msp430fr5969", help="MCU型号")
    args = ap.parse_args()
    
    # 加载平台配置
    plat_cfg = {"mcu": args.mcu}
    
    analyze_normalized_asm(
        Path(args.asm_path),
        Path(args.symbol_file),
        plat_cfg,
        Path(args.out)
    )

if __name__ == "__main__":
    main()
