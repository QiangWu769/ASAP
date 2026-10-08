#!/usr/bin/env python3
# =============================================================
# ReflexSave: Stage 5 — Operand Normalization Pass
# =============================================================
# 目标：
#   对于所有关键写（requires_backup == True），若其源为寄存器，
#   且该寄存器的值非稳定来源（非ABS/STACK/FRAM_OR_FLASH），
#   则在写入前物化该寄存器值到shadow slot，并更新指令。
#
# 输入：
#   build/candidates.json  ← Stage 3.5 输出
# 输出：
#   build/normalize_map.json   ← 各寄存器对应shadow地址
#   build/normalized.json      ← 重写后的指令信息
#   build/normalized.s         ← 伪汇编形式（供人工检查）
# =============================================================

import json, re, argparse
from pathlib import Path

# shadow 起始地址（可根据平台调整）
SHADOW_BASE = 0x1C00  # 改为 RAM 底部，避免与栈冲突
SHADOW_STEP = 0x0002

def split_operands(op_text: str):
    """安全拆分操作数字符串"""
    parts = [x.strip() for x in op_text.split(",") if x.strip()]
    return parts if len(parts) == 2 else (None, None)

def is_register(operand: str) -> bool:
    return bool(re.fullmatch(r"r\d+", operand.strip().lower()))

def is_immediate(operand: str) -> bool:
    return operand.strip().startswith("#")

def analyze_stack_usage(candidates):
    """分析栈使用情况，返回安全的影子槽起始地址"""
    stack_top = 0x2400  # MSP430 栈顶
    actual_stack_addrs = []
    
    # 分析所有栈相关的写操作
    for e in candidates:
        if 'STACK' in e.get('target', ''):
            if e['write_site']['mode'] == 'IDX' and e['write_site']['base'] == 'r1':
                disp = e['write_site']['disp']
                if disp is not None:
                    actual_addr = stack_top - disp  # 栈向下增长
                    actual_stack_addrs.append(actual_addr)
    
    # 强制使用固定安全地址0x1D00，避免和uart_putc等函数的临时变量(0x23bc)冲突！
    safe_start = 0x1D00
    print(f"[normalize_operands] ⚠️  强制使用固定shadow地址避免冲突")
    return safe_start

def normalize_candidates(candidates, out_dir: Path):
    normalize_map = {}
    normalized_entries = []
    asm_lines = []
    
    # 动态分析栈使用情况，确定安全的影子槽起始地址
    safe_start = analyze_stack_usage(candidates)
    shadow_cursor = safe_start
    
    print(f"[normalize_operands] 分析栈使用情况，影子槽起始地址: 0x{safe_start:04x}")

    processed_count = 0
    for ins in candidates:
        if not ins.get("requires_backup"):  # 非关键写跳过
            continue
        
        processed_count += 1
        if processed_count <= 5:
            print(f"[DEBUG] Processing {processed_count}: PC={ins['pc']}, ops={ins.get('operands', '')}")

        ops = ins.get("operands", "")
        src, dst = split_operands(ops)
        if not src or not dst:
            # 无法解析操作数的指令，直接复制
            normalized_entries.append(ins)
            if processed_count <= 5:
                print(f"[DEBUG] Added unparseable: PC={ins['pc']}")
            continue

        # 检查是否需要归一化
        needs_normalization = False
        if is_register(src):
            origin_kind = ins.get("value_origin", {}).get("kind", "UNKNOWN")
            if origin_kind not in ("ABS", "STACK", "FRAM_OR_FLASH"):
                needs_normalization = True

        if needs_normalization:
            reg = src.lower()

            # 为寄存器分配shadow槽
            if reg not in normalize_map:
                normalize_map[reg] = f"0x{shadow_cursor:04x}"
                shadow_cursor += SHADOW_STEP

            slot_addr = normalize_map[reg]

            # 构造归一化操作
            normalized_entry = {
                "pc": ins["pc"],
                "mnemonic": ins["mnemonic"],
                "operands": f"&{slot_addr}, {dst}",
                "original_operands": ins["operands"],
                "width": ins.get("width", 2),
                "write_site": ins.get("write_site", {}),
                "normalized_from": reg,
                "shadow_slot": slot_addr,
                "insert_before": f"MOV {reg}, &{slot_addr}",
                "reason": f"critical write with volatile source {reg} → materialized",
            }

            normalized_entries.append(normalized_entry)
            print(f"[DEBUG] Normalized: PC={ins['pc']}, reg={reg}, slot={slot_addr}")

            # 汇编输出
            asm_lines.append(f"; ---- Normalized critical write @ {ins['pc']} ----")
            asm_lines.append(f"MOV   {reg}, &{slot_addr}     ; materialize {reg}")
            asm_lines.append(f"{ins['mnemonic'].upper()}   &{slot_addr}, {dst}")
            asm_lines.append("")
        else:
            # 不需要归一化的指令，直接复制
            normalized_entries.append(ins)

    # 输出结果
    (out_dir / "normalize_map.json").write_text(json.dumps(normalize_map, indent=2), encoding="utf-8")
    (out_dir / "normalized_candidates.json").write_text(json.dumps(normalized_entries, indent=2), encoding="utf-8")
    (out_dir / "normalized.json").write_text(json.dumps(normalized_entries, indent=2), encoding="utf-8")
    (out_dir / "normalized.s").write_text("\n".join(asm_lines), encoding="utf-8")

    # 验证地址安全性
    shadow_addrs = [int(addr, 16) for addr in normalize_map.values()]
    shadow_min = min(shadow_addrs) if shadow_addrs else 0
    shadow_max = max(shadow_addrs) if shadow_addrs else 0
    
    # 重新分析栈使用情况进行验证
    stack_top = 0x2400
    actual_stack_addrs = []
    for e in candidates:
        if 'STACK' in e.get('target', ''):
            if e['write_site']['mode'] == 'IDX' and e['write_site']['base'] == 'r1':
                disp = e['write_site']['disp']
                if disp is not None:
                    actual_addr = stack_top - disp
                    actual_stack_addrs.append(actual_addr)
    
    if actual_stack_addrs:
        min_stack_addr = min(actual_stack_addrs)
        max_stack_addr = max(actual_stack_addrs)
        
        # 检查冲突
        conflicting = [addr for addr in shadow_addrs if min_stack_addr <= addr <= max_stack_addr]
        
        print(f"[normalize_operands] normalized {len(normalized_entries)} instructions")
        print(f"[normalize_operands] shadow slots allocated: {len(normalize_map)} (0x{shadow_min:04x}–0x{shadow_max:04x})")
        print(f"[normalize_operands] stack usage: 0x{min_stack_addr:04x}–0x{max_stack_addr:04x}")
        
        if conflicting:
            print(f"⚠️  WARNING: {len(conflicting)} shadow slots conflict with stack usage!")
            for addr in conflicting:
                print(f"   Conflict at 0x{addr:04x}")
        else:
            safety_margin = min_stack_addr - shadow_max - 1
            print(f"✅ Shadow slots are safe with {safety_margin} bytes margin")
    else:
        print(f"[normalize_operands] normalized {len(normalized_entries)} instructions")
        print(f"[normalize_operands] shadow slots allocated: {len(normalize_map)} (0x{shadow_min:04x}–0x{shadow_max:04x})")
        print("[normalize_operands] No stack usage detected")

def main():
    ap = argparse.ArgumentParser(description="Normalize volatile register sources for critical writes")
    ap.add_argument("--in", dest="in_json", default="build/candidates.json", help="Stage 3.5 candidates.json")
    ap.add_argument("--out-dir", default="build", help="Output directory")
    args = ap.parse_args()

    in_path = Path(args.in_json)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates = json.loads(in_path.read_text(encoding="utf-8"))
    normalize_candidates(candidates, out_dir)

if __name__ == "__main__":
    main()