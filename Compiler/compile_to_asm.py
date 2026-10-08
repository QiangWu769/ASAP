# compiler/compile_to_asm.py
# -----------------------------------------------
# Step 1: Compile C source to symbolic assembly (.s)
# Default toolchain: msp430-gcc ；若不存在则回退到系统 gcc
#
# Usage:
#   python3 compiler/compile_to_asm.py examples/BC/bc.c
#   python3 compiler/compile_to_asm.py examples/BC/bc.c --compiler msp430-gcc --cflags "-Og -g"
#   python3 compiler/compile_to_asm.py examples/BC/bc.c --out-dir build
#
# Output:
#   build/A_sym.s          —— 规范化命名（后续管线依赖）
#   build/<base>.s         —— 以源文件名命名的副本（便于多基准并行）
#
# Exit code 非 0 表示失败；stderr 会打印详细错误。

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_COMPILERS = ["msp430-gcc", "gcc"]

def which_or_none(cmd: str) -> str | None:
    return shutil.which(cmd)

def pick_compiler(preferred: str | None) -> str:
    if preferred:
        if which_or_none(preferred):
            return preferred
        print(f"[compile_to_asm] Warning: preferred compiler '{preferred}' not found, will try fallbacks.", file=sys.stderr)
    for c in DEFAULT_COMPILERS:
        if which_or_none(c):
            return c
    raise SystemExit("[compile_to_asm] Error: no suitable compiler found (tried msp430-gcc, gcc). Please install one or pass --compiler.")

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def run(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[compile_to_asm] Error running: {' '.join(cmd)}", file=sys.stderr)
        raise SystemExit(e.returncode)

def compile_to_asm(src_path: Path, out_dir: Path, compiler: str, cflags: str) -> tuple[Path, Path]:
    """
    Compile a single C file into symbolic assembly (.s).

    Returns:
        (a_sym, named_s) where
          a_sym   = build/A_sym.s (canonical name for downstream)
          named_s = build/<basename>.s (kept for debugging/multi-benchmark)
    """
    if not src_path.exists():
        raise SystemExit(f"[compile_to_asm] Error: source not found: {src_path}")

    ensure_dir(out_dir)

    basename = src_path.stem
    named_s = out_dir / f"{basename}.s"
    a_sym = out_dir / "A_sym.s"

    # Prepare compile command
    # -S : compile to assembly
    # -g/-Og 默认便于保留符号；允许用户覆盖
    base_flags = ["-S"]
    user_flags = cflags.strip().split() if cflags else []
    # 若用户未提供优化/调试级别，给出温和默认值，保留符号便于后续匹配
    if not any(f.startswith("-O") for f in user_flags):
        user_flags += ["-Og"]
    if not any(f == "-g" or f.startswith("-g") for f in user_flags):
        user_flags += ["-g"]

    cmd = [compiler, *base_flags, *user_flags, str(src_path), "-o", str(named_s)]
    print(f"[compile_to_asm] Running: {' '.join(cmd)}")
    run(cmd)

    # 覆盖/同步到规范名 A_sym.s（后续管线固定读取这个文件）
    shutil.copy2(named_s, a_sym)

    print(f"[compile_to_asm] OK: {src_path.name} -> {named_s.name} (and A_sym.s)")
    return a_sym, named_s

def main():
    ap = argparse.ArgumentParser(description="Compile C source to symbolic assembly (.s)")
    ap.add_argument("src", help="Path to input .c file")
    ap.add_argument("--out-dir", default="build", help="Output directory (default: build)")
    ap.add_argument("--compiler", default=None, help="C compiler (default: try msp430-gcc, then gcc)")
    ap.add_argument("--cflags", default="", help="Additional compiler flags, e.g. '-Os -Wall'")
    args = ap.parse_args()

    compiler = pick_compiler(args.compiler)
    out_dir = Path(args.out_dir)
    src_path = Path(args.src).resolve()

    a_sym, named_s = compile_to_asm(src_path, out_dir, compiler, args.cflags)
    # 友好提示下阶段输入
    print(f"[compile_to_asm] Next step: link temp ELF and disassemble:")
    print(f"  (example) msp430-gcc -c {named_s} -o {out_dir}/A.o && "
          f"msp430-gcc {out_dir}/A.o -o {out_dir}/firmware_tmp.elf")

if __name__ == "__main__":
    main()
