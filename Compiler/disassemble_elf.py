# compiler/disassemble_elf.py
# -----------------------------------------------
# Step 2: 生成临时 ELF 并反汇编得到地址汇编 (A_real.s)
#
# 用法:
#   python3 compiler/disassemble_elf.py build/A_sym.s
#   python3 compiler/disassemble_elf.py build/A_sym.s --compiler msp430-elf-gcc --cflags "-mmcu=msp430fr5969"
#
# 输出:
#   build/firmware_tmp.elf
#   build/A_real.s

import argparse
import subprocess
import sys
from pathlib import Path

def run(cmd: list[str]):
    """执行命令并打印。出错即退出。"""
    print("[disassemble_elf] >", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"[disassemble_elf] Error executing: {' '.join(cmd)}\n{e}")

def disassemble_elf(
    sym_asm: Path,
    out_dir: Path,
    compiler: str = "msp430-elf-gcc",
    objdump: str = "msp430-elf-objdump",
    cflags: str = "-mmcu=msp430fr5969",
    output_name: str = "A_real.s"
) -> tuple[Path, Path]:
    """
    编译符号汇编→临时ELF→反汇编.
    返回 (elf_path, a_real_path)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    elf_path = out_dir / "firmware_tmp.elf"
    a_real_path = out_dir / output_name
    obj_path = out_dir / "A.o"

    # === 1️⃣ Assemble ===
    run([compiler, *cflags.split(), "-c", str(sym_asm), "-o", str(obj_path)])

    # === 2️⃣ Link ===
    run([compiler, *cflags.split(), str(obj_path), "-o", str(elf_path)])

    # === 3️⃣ Disassemble once ===
    with open(a_real_path, "w") as f:
        subprocess.run([objdump, "-d", str(elf_path)], check=True, stdout=f)

    print(f"[disassemble_elf] OK: generated {a_real_path}")
    return elf_path, a_real_path

def main():
    ap = argparse.ArgumentParser(description="Assemble symbolic ASM → ELF → disassembled ASM")
    ap.add_argument("sym_asm", help="Path to symbolic assembly (.s)")
    ap.add_argument("--compiler", default="msp430-elf-gcc", help="Compiler executable")
    ap.add_argument("--objdump", default="msp430-elf-objdump", help="Objdump executable")
    ap.add_argument("--out-dir", default="build", help="Output directory")
    ap.add_argument("--cflags", default="-mmcu=msp430fr5969", help="Extra compiler flags")
    ap.add_argument("--output-name", default="A_real.s", help="Output disassembled file name")
    args = ap.parse_args()

    sym_asm = Path(args.sym_asm)
    out_dir = Path(args.out_dir)
    if not sym_asm.exists():
        raise SystemExit(f"[disassemble_elf] Error: {sym_asm} not found")

    disassemble_elf(sym_asm, out_dir, args.compiler, args.objdump, args.cflags, args.output_name)

if __name__ == "__main__":
    main()
