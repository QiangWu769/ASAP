#!/usr/bin/env python3
"""
BC核心功能分析器 - 排除输出相关代码
基于 analyze_normalized_asm.py，增加了函数和外设过滤功能
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
RE_FUNC_START = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):")

# 关键写指令
WRITE_DST_MNEMS = {"mov", "bis", "bic", "xor", "add", "sub", "and", "or"}

class BCCoreAnalyzer:
    def __init__(self, config_path):
        """加载BC核心配置"""
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.exclude_functions = set(self.config['exclude_functions'])
        self.bc_core_functions = set(self.config['bc_core_functions'])
        
        # 构建排除的外设地址集合
        self.exclude_addrs = set()
        for category in self.config['exclude_peripherals'].values():
            if isinstance(category, dict) and 'comment' not in category:
                for addr in category.values():
                    if addr.startswith('0x'):
                        self.exclude_addrs.add(int(addr, 16))
        
        print(f"✓ 加载配置: 排除 {len(self.exclude_functions)} 个函数")
        print(f"✓ 排除 {len(self.exclude_addrs)} 个外设地址")
        print(f"✓ 只分析 {len(self.bc_core_functions)} 个核心函数")
    
    def should_exclude_function(self, func_name):
        """判断是否应该排除该函数"""
        return func_name in self.exclude_functions
    
    def should_exclude_address(self, addr):
        """判断是否应该排除该地址"""
        return addr in self.exclude_addrs
    
    def is_core_function(self, func_name):
        """判断是否是BC核心函数"""
        return func_name in self.bc_core_functions

def extract_functions(lines):
    """提取所有函数的边界"""
    functions = {}
    current_func = None
    start_line = None
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        
        # 检测函数开始
        if m := RE_FUNC_START.match(line_stripped):
            if current_func:
                # 保存前一个函数
                functions[current_func] = (start_line, i - 1)
            
            current_func = m.group(1)
            start_line = i
    
    # 保存最后一个函数
    if current_func:
        functions[current_func] = (start_line, len(lines) - 1)
    
    return functions

def get_function_at_line(line_num, functions):
    """获取指定行所属的函数"""
    for func_name, (start, end) in functions.items():
        if start <= line_num <= end:
            return func_name
    return None

def classify_addr(addr):
    """分类地址类型"""
    if addr < 0x2000:
        return "MMIO"
    elif addr < 0x4000:
        return "RAM"
    else:
        return "FRAM"

def parse_mnem_ops_from_line(line):
    """从汇编行中解析助记符和操作数"""
    if m := RE_LINE3.match(line):
        mnem = m.group(2)
        ops = m.group(3)
        return mnem, ops
    else:
        line_clean = line.strip()
        if not line_clean or line_clean.startswith(';') or line_clean.startswith('.'):
            return None, None
        
        parts = line_clean.split()
        if len(parts) >= 2:
            mnem = parts[0]
            ops = ' '.join(parts[1:])
            return mnem, ops
    return None, None

def analyze_bc_core(asm_path, config_path, out_json):
    """分析BC核心功能，排除输出相关代码"""
    analyzer = BCCoreAnalyzer(config_path)
    
    # 读取汇编文件
    lines = asm_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    
    # 提取函数边界
    functions = extract_functions(lines)
    print(f"\n✓ 识别到 {len(functions)} 个函数:")
    for func_name in sorted(functions.keys()):
        status = "CORE" if analyzer.is_core_function(func_name) else \
                 "EXCLUDE" if analyzer.should_exclude_function(func_name) else "OTHER"
        print(f"  [{status}] {func_name}")
    
    results = []
    excluded_count = 0
    
    for i, line in enumerate(lines):
        # 确定当前行所属函数
        current_func = get_function_at_line(i, functions)
        
        # 如果在排除函数中，跳过
        if current_func and analyzer.should_exclude_function(current_func):
            continue
        
        # 如果不在核心函数中，也跳过（可选策略）
        # if current_func and not analyzer.is_core_function(current_func):
        #     continue
        
        mnem, ops = parse_mnem_ops_from_line(line)
        if not mnem or not ops or "," not in ops:
            continue
        
        mnem_l = mnem.lower()
        base_m = mnem_l.split(".")[0]
        if base_m not in WRITE_DST_MNEMS:
            continue
        
        # 解析目的操作数
        parts = [p.strip() for p in ops.split(",")]
        if len(parts) < 2:
            continue
        
        dst = parts[-1]  # 目的操作数
        src = ",".join(parts[:-1])  # 源操作数
        
        # 解析目的地址
        addr = None
        addr_type = None
        
        # 绝对地址 &0x1234
        if m := RE_ABS.search(dst):
            addr = int(m.group(1), 16)
            addr_type = "ABS"
        
        # 符号地址 &symbol
        elif m := RE_SYMBOL.search(dst):
            symbol = m.group(1)
            addr_type = "SYMBOL"
        
        # 索引寻址 x(Rx)
        elif m := RE_IDX.search(dst):
            offset = int(m.group(1))
            reg = m.group(2).upper()
            addr_type = "INDEXED"
        
        # 间接寻址 @Rx
        elif m := RE_IND.search(dst):
            reg = int(m.group(1))
            addr_type = "INDIRECT"
        
        # 如果是绝对地址，检查是否应该排除
        if addr is not None and analyzer.should_exclude_address(addr):
            excluded_count += 1
            print(f"  [SKIP] Line {i+1}: {line.strip()} (排除外设地址 0x{addr:04x})")
            continue
        
        # 分类地址
        if addr is not None:
            region = classify_addr(addr)
        else:
            region = "UNKNOWN"
        
        # 记录结果
        result = {
            "line": i + 1,
            "pc": f"L{i+1}",  # 使用行号作为PC
            "mnem": mnem,
            "src": src,
            "dst": dst,
            "addr_type": addr_type,
            "region": region,
            "function": current_func or "UNKNOWN"
        }
        
        if addr is not None:
            result["addr"] = f"0x{addr:04x}"
        
        results.append(result)
    
    # 保存结果
    output = {
        "total_writes": len(results),
        "excluded_writes": excluded_count,
        "functions_analyzed": list(analyzer.bc_core_functions),
        "functions_excluded": list(analyzer.exclude_functions),
        "candidates": results
    }
    
    with open(out_json, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✓ 分析完成:")
    print(f"  - 识别到 {len(results)} 个BC核心关键写")
    print(f"  - 排除了 {excluded_count} 个输出相关写操作")
    print(f"  - 结果保存到: {out_json}")

def main():
    parser = argparse.ArgumentParser(description="BC核心功能分析器")
    parser.add_argument("asm_file", type=Path, help="符号汇编文件")
    parser.add_argument("--config", type=Path, 
                       default=Path("Compiler/bc_core_config.json"),
                       help="BC核心配置文件")
    parser.add_argument("--out", type=Path, 
                       default=Path("build/bc_core_candidates.json"),
                       help="输出JSON文件")
    
    args = parser.parse_args()
    
    analyze_bc_core(args.asm_file, args.config, args.out)

if __name__ == "__main__":
    main()





































