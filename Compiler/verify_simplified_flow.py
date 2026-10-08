#!/usr/bin/env python3
"""
验证简化流程的正确性

检查各个stage的输出是否符合预期
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

def check_file_exists(path: Path, description: str) -> bool:
    """检查文件是否存在"""
    if path.exists():
        print(f"✅ {description}: {path.name}")
        return True
    else:
        print(f"❌ {description}: {path.name} 不存在")
        return False

def verify_wid_map(wid_map_path: Path) -> Dict:
    """验证WID映射"""
    print("\n=== 验证WID映射 ===")
    
    if not check_file_exists(wid_map_path, "WID映射文件"):
        return {}
    
    with open(wid_map_path, 'r') as f:
        wid_map = json.load(f)
    
    wid_to_info = wid_map.get("wid_to_info", {})
    pc_to_wid = wid_map.get("pc_to_wid", {})
    
    print(f"  - 总WID数: {len(wid_to_info)}")
    print(f"  - PC映射数: {len(pc_to_wid)}")
    
    # 检查每个WID的必要字段
    missing_fields = []
    for wid, info in wid_to_info.items():
        required = ["pc", "target_addr", "mode", "width"]
        for field in required:
            if field not in info:
                missing_fields.append((wid, field))
    
    if missing_fields:
        print(f"  ⚠️ {len(missing_fields)} 个WID缺少必要字段")
        for wid, field in missing_fields[:5]:
            print(f"     {wid}: 缺少 {field}")
    else:
        print(f"  ✅ 所有WID包含必要字段")
    
    return wid_map

def verify_fram_symbols(fram_symbols_path: Path, wid_map: Dict) -> bool:
    """验证FRAM符号链接脚本"""
    print("\n=== 验证FRAM符号脚本 ===")
    
    if not check_file_exists(fram_symbols_path, "FRAM符号脚本"):
        return False
    
    with open(fram_symbols_path, 'r') as f:
        content = f.read()
    
    # 统计符号定义数量
    slot_symbols = re.findall(r'PROVIDE\(__SLOT_[^=]+= 0x[0-9A-Fa-f]+\);', content)
    commit_symbols = re.findall(r'PROVIDE\(__COMMIT_W\d+ = 0x[0-9A-Fa-f]+\);', content)
    
    print(f"  - 槽位符号: {len(slot_symbols)}")
    print(f"  - 提交位符号: {len(commit_symbols)}")
    
    # 验证提交位数量是否匹配WID数量
    wid_count = len(wid_map.get("wid_to_info", {}))
    if len(commit_symbols) == wid_count:
        print(f"  ✅ 提交位数量匹配WID数量 ({wid_count})")
    else:
        print(f"  ⚠️ 提交位数量 ({len(commit_symbols)}) != WID数量 ({wid_count})")
    
    # 验证每个WID都有对应的提交位
    missing_commits = []
    for wid in wid_map.get("wid_to_info", {}).keys():
        if f"__COMMIT_{wid}" not in content:
            missing_commits.append(wid)
    
    if missing_commits:
        print(f"  ⚠️ {len(missing_commits)} 个WID缺少提交位定义")
        for wid in missing_commits[:5]:
            print(f"     {wid}")
    else:
        print(f"  ✅ 所有WID都有提交位定义")
    
    return len(missing_commits) == 0

def verify_instrumented_asm(asm_path: Path, wid_map: Dict) -> bool:
    """验证插桩后的汇编"""
    print("\n=== 验证插桩汇编 ===")
    
    if not check_file_exists(asm_path, "插桩汇编"):
        return False
    
    with open(asm_path, 'r') as f:
        lines = f.readlines()
    
    # 统计ASAP标记
    backup_count = 0
    commit_count = 0
    
    for line in lines:
        if 'ASAP backup for' in line:
            backup_count += 1
        if 'ASAP commit for' in line:
            commit_count += 1
    
    print(f"  - 备份指令: {backup_count}")
    print(f"  - 提交指令: {commit_count}")
    
    wid_count = len(wid_map.get("wid_to_info", {}))
    
    # 验证插桩数量
    if backup_count == wid_count:
        print(f"  ✅ 备份指令数量匹配WID数量 ({wid_count})")
    else:
        print(f"  ⚠️ 备份指令数量 ({backup_count}) != WID数量 ({wid_count})")
    
    if commit_count == wid_count:
        print(f"  ✅ 提交指令数量匹配WID数量 ({wid_count})")
    else:
        print(f"  ⚠️ 提交指令数量 ({commit_count}) != WID数量 ({wid_count})")
    
    if backup_count != commit_count:
        print(f"  ⚠️ 备份和提交指令数量不匹配")
        return False
    
    # 验证插桩格式（备份和提交成对出现）
    print("\n  验证插桩格式...")
    format_errors = 0
    
    for i, line in enumerate(lines):
        if 'ASAP backup for' in line:
            # 提取WID
            if m := re.search(r'ASAP backup for (W\d+)', line):
                wid = m.group(1)
                # 下一行应该是对应的commit
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    if f'ASAP commit for {wid}' not in next_line:
                        format_errors += 1
                        if format_errors <= 3:
                            print(f"    ⚠️ 行 {i+1}: {wid} 的commit指令不在下一行")
                else:
                    format_errors += 1
                    print(f"    ⚠️ 行 {i+1}: {wid} 后面没有commit指令")
    
    if format_errors == 0:
        print(f"  ✅ 所有插桩指令格式正确（备份和提交成对）")
    else:
        print(f"  ⚠️ 发现 {format_errors} 个格式错误")
    
    return format_errors == 0

def verify_nextpc_table(nextpc_path: Path, wid_map: Dict) -> bool:
    """验证NextPC表"""
    print("\n=== 验证NextPC表 ===")
    
    if not check_file_exists(nextpc_path, "NextPC表"):
        return False
    
    with open(nextpc_path, 'r') as f:
        data = json.load(f)
    
    nextpc_table = data.get("nextpc_table", {})
    statistics = data.get("statistics", {})
    
    print(f"  - NextPC条目: {len(nextpc_table)}")
    print(f"  - 覆盖率: {statistics.get('coverage', 'N/A')}")
    
    wid_count = len(wid_map.get("wid_to_info", {}))
    
    if len(nextpc_table) == wid_count:
        print(f"  ✅ NextPC数量匹配WID数量 ({wid_count})")
    else:
        print(f"  ⚠️ NextPC数量 ({len(nextpc_table)}) != WID数量 ({wid_count})")
    
    # 检查所有WID是否都有NextPC
    missing_nextpc = []
    for wid in wid_map.get("wid_to_info", {}).keys():
        if wid not in nextpc_table:
            missing_nextpc.append(wid)
    
    if missing_nextpc:
        print(f"  ⚠️ {len(missing_nextpc)} 个WID缺少NextPC")
        for wid in missing_nextpc[:5]:
            print(f"     {wid}")
        return False
    else:
        print(f"  ✅ 所有WID都有NextPC")
        return True

def main():
    print("=" * 60)
    print("ASAP 简化流程验证工具")
    print("=" * 60)
    
    build_dir = Path("build")
    
    # 检查必要文件
    files_to_check = [
        (build_dir / "A_sym.s", "Stage 1: 符号汇编"),
        (build_dir / "candidates.json", "Stage 2: 候选关键写"),
        (build_dir / "function_boundaries.json", "Stage 2: 函数边界"),
        (build_dir / "A_normalized.s", "Stage 3: 归一化汇编"),
        (build_dir / "wid_map.json", "Stage 4: WID映射"),
        (build_dir / "fram_symbols.ld", "Stage 5: FRAM符号脚本"),
        (build_dir / "A_instrumented.s", "Stage 6: 插桩汇编"),
        (build_dir / "firmware_final.elf", "Stage 7: 最终固件"),
    ]
    
    print("\n=== 检查文件存在性 ===")
    all_exist = True
    for path, desc in files_to_check:
        if not check_file_exists(path, desc):
            all_exist = False
    
    if not all_exist:
        print("\n❌ 部分文件缺失，请先完成编译")
        return 1
    
    # 详细验证
    wid_map = verify_wid_map(build_dir / "wid_map.json")
    
    fram_ok = verify_fram_symbols(build_dir / "fram_symbols.ld", wid_map)
    
    asm_ok = verify_instrumented_asm(build_dir / "A_instrumented.s", wid_map)
    
    # 如果有NextPC表，也验证它
    nextpc_path = build_dir / "nextpc_table.json"
    nextpc_ok = True
    if nextpc_path.exists():
        nextpc_ok = verify_nextpc_table(nextpc_path, wid_map)
    else:
        print("\n⏭️ NextPC表未生成（可能尚未执行Stage 8）")
    
    # 总结
    print("\n" + "=" * 60)
    print("验证总结")
    print("=" * 60)
    
    all_ok = fram_ok and asm_ok and (nextpc_ok or not nextpc_path.exists())
    
    if all_ok:
        print("✅ 所有验证通过！简化流程工作正常。")
        return 0
    else:
        print("⚠️ 发现一些问题，请检查上述警告。")
        return 1

if __name__ == "__main__":
    exit(main())

