#!/usr/bin/env python3
# Runtime/src/port/msp430/parse_platform.py
# --------------------------------------------------
# 从 msp430 .ld 与 _symbols.ld 提取完整内存区域与符号映射
# 输出 Runtime/config/<mcu>.json

import re
import json
import argparse
from pathlib import Path

# ---------- helpers ----------

def to_hex(v: int) -> str:
    return f"0x{v:04x}"

def parse_ld_file(ld_path: Path) -> dict:
    """解析 MEMORY { ... }，返回 {name: [start, end]}"""
    text = ld_path.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(
        r"(\w+)\s*:\s*ORIGIN\s*=\s*0x([0-9A-Fa-f]+)\s*,\s*LENGTH\s*=\s*0x([0-9A-Fa-f]+)"
    )
    regions = {}
    for name, org, length in pattern.findall(text):
        start = int(org, 16)
        end = start + int(length, 16) - 1
        regions[name.upper()] = [to_hex(start), to_hex(end)]
    return regions

def parse_symbols_ld(symbols_path: Path) -> dict:
    """解析 PROVIDE(NAME = 0xXXXX);"""
    if not symbols_path.exists():
        return {}
    text = symbols_path.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(
        r"(?:PROVIDE\()?\s*([A-Za-z0-9_]+)\s*\)?\s*=\s*0x([0-9A-Fa-f]+)\s*;?"
    )
    symbols = {}
    for name, val in pattern.findall(text):
        addr = int(val, 16)
        symbols[to_hex(addr)] = name
    return symbols

def find_repo_root(start: Path) -> Path:
    """向上搜索 Runtime 目录"""
    cur = start.resolve()
    for _ in range(8):
        if (cur / "Runtime").exists():
            return cur / "Runtime"
        cur = cur.parent
    raise SystemExit("❌ cannot locate Runtime/ directory")

# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mcu", required=True)
    ap.add_argument("--config-dir", default=None)
    args = ap.parse_args()

    mcu = args.mcu.lower()
    base = Path(__file__).resolve().parent
    runtime_root = find_repo_root(base)
    out_dir = Path(args.config_dir) if args.config_dir else (runtime_root / "config")
    out_dir.mkdir(parents=True, exist_ok=True)

    ld_file = base / f"{mcu}.ld"
    sym_file = base / f"{mcu}_symbols.ld"
    if not ld_file.exists():
        raise SystemExit(f"❌ missing {ld_file}")

    regions = parse_ld_file(ld_file)
    symbols = parse_symbols_ld(sym_file)

    out_json = out_dir / f"{mcu}.json"
    cfg = {"platform": mcu, "memory_regions": regions, "symbols": symbols}
    out_json.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print(f"✅ Generated {out_json}")

if __name__ == "__main__":
    main()
