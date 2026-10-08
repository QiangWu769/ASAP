#!/usr/bin/env python3
# =============================================================
# ReflexSave: CFG + DFG (Reaching Definitions) extractor
#  - 指令级 CFG：fallthrough / 条件跳转 / 无条件跳转 / ret 截断
#  - DFG：每条指令的 defs / uses（寄存器级别），覆盖：
#       mov/mova, add/sub/xor/and/bis/bic/dadd, inc/dec, clr/inv,
#       rrc/rrc.b, rra, rla/rlc, swpb,
#       push/pop/pushm/popm, call/calla
#  - RD 传递方程内置 MOV 等价传播（copy-prop aware）
#  - 输出：
#       build/cfg.json
#       build/dfg.json （行式，含 reaching_defs）
# =============================================================

import argparse, json, re
from pathlib import Path
from collections import defaultdict

# ---------- 正则 ----------
RE_LINE4 = re.compile(r"^\s*([0-9a-fA-F]+):\s+([0-9A-Fa-f ]+)\s+([A-Za-z.]+)\s*(.*)$")
RE_LINE3 = re.compile(r"^\s*([0-9a-fA-F]+):\s+([A-Za-z.]+)\s*(.*)$")
RE_ABS   = re.compile(r"&0x([0-9a-fA-F]+)")
RE_IDX   = re.compile(r"(-?\d+)\((r[0-9]+)\)")
RE_IND   = re.compile(r"@r([0-9]+)")
RE_ABS_TGT  = re.compile(r"abs\s+0x([0-9a-fA-F]+)")
RE_HASH_TGT = re.compile(r"#([0-9]+)")

COND_JUMPS = {"jz","jnz","jc","jnc","jl","jge","jna","ja","jn","jlo","jhs"}
UNCOND_JUMPS = {"jmp"}
RETS = {"ret"}
CALLS = {"call","calla"}

# ---------- defs/uses 规则 ----------
def defs_uses_for(mnem_base, ops_clean):
    """
    返回: (defs:set[str], uses:set[str])
    —— 扩展为“寄存器 + 伪内存”二类符号：
       - 目的为寄存器: defs += {rX}
       - 目的为内存:   defs += {mem[...]}，uses 继续包含基址寄存器
    """
    defs, uses = set(), set()
    src_txt, dst_txt = None, None
    if "," in ops_clean:
        src_txt, dst_txt = [x.strip() for x in ops_clean.rsplit(",",1)]
    elif ops_clean.strip():
        dst_txt = ops_clean.strip()

    # 工具：寄存器使用（含基址寄存器）
    def regs_used_in(operand: str):
        regs = set()
        if not operand: return regs
        s = operand.strip().lower()
        if re.fullmatch(r"r[0-9]+", s):
            regs.add(s)
        for m in RE_IND.finditer(s):
            regs.add("r"+m.group(1))          # @rX
        for m in RE_IDX.finditer(s):
            regs.add(m.group(2).lower())      # n(rX) -> rX
        return regs

    # 工具：把“内存目的操作数”归一化成伪符号 mem[...]
    def mem_token(operand: str):
        if not operand:
            return None
        s = operand.strip().lower()
        if re.fullmatch(r"r[0-9]+", s):
            return None
        if (m := RE_IDX.search(s)):
            return f"mem[{m.group(1)}({m.group(2).lower()})]"   # mem[55(r12)]
        if (m := RE_IND.search(s)):
            return f"mem[@r{m.group(1)}]"                       # mem[@r10]
        if (m := RE_ABS.search(s)):
            return f"mem[&0x{int(m.group(1),16):04x}]"          # mem[&0x05c0]
        return None

    dst_is_reg = bool(dst_txt and re.fullmatch(r"r[0-9]+", (dst_txt or "").lower()))
    dst_mem    = mem_token(dst_txt)
    mb = mnem_base.lower()

    # === 双操作数算术类：add/sub/xor/and/bis/bic/dadd ===
    if mb in ("add","sub","xor","and","bis","bic","dadd"):
        # 目的是寄存器 → def 寄存器 & use 旧值
        if dst_is_reg:
            dreg = dst_txt.lower()
            defs.add(dreg)
            uses.add(dreg)                    # 旧值
        # 目的是内存 → def mem[...] & use 基址寄存器 & 可选：旧内存值
        elif dst_mem:
            defs.add(dst_mem)
            uses |= regs_used_in(dst_txt)     # 基址寄存器（如 r12）
            uses.add(dst_mem)                 # RMW：旧内存值也被读（可选但推荐）
        # 源操作数寄存器使用
        uses |= regs_used_in(src_txt)

    # === mov/mova ===
    elif mb in ("mov","mova"):
        if dst_is_reg:
            defs.add(dst_txt.lower())
        elif dst_mem:
            defs.add(dst_mem)                  # 写内存
            uses |= regs_used_in(dst_txt)      # 基址寄存器
        # 源寄存器使用
        uses |= regs_used_in(src_txt)

    # === 单操作数：clr/inv/swpb ===
    elif mb in ("clr","inv","swpb"):
        if dst_is_reg:
            dreg = dst_txt.lower()
            defs.add(dreg)
            if mb in ("inv","swpb"):
                uses.add(dreg)                 # 读旧值
        elif dst_mem:
            defs.add(dst_mem)
            uses |= regs_used_in(dst_txt)      # 基址寄存器
            if mb in ("inv","swpb"):
                uses.add(dst_mem)              # 读旧内存值

    # === 单操作数：inc/dec/rra/rrc/rla/rlc ===
    elif mb in ("inc","dec","rra","rrc","rla","rlc"):
        if dst_is_reg:
            dreg = dst_txt.lower()
            defs.add(dreg); uses.add(dreg)     # RMW
        elif dst_mem:
            defs.add(dst_mem)
            uses |= regs_used_in(dst_txt)      # 基址寄存器
            uses.add(dst_mem)                  # 旧内存值

    # === 栈操作 ===
    elif mb == "push":
        uses |= regs_used_in(src_txt)
        # 可选：把栈写抽象成 mem[r1-2] 等，这里先不建伪内存节点
    elif mb == "pop":
        if dst_is_reg:
            defs.add(dst_txt.lower())
        # 同理可建 mem[r1] 读，这里省略
    elif mb == "pushm":
        m = re.match(r"#(\d+)\s*,\s*(r[0-9]+)", (src_txt or "").lower())
        if m:
            n, r0 = int(m.group(1)), int(m.group(2)[1:])
            for k in range(n): uses.add(f"r{r0+k}")
    elif mb == "popm":
        m = re.match(r"#(\d+)\s*,\s*(r[0-9]+)", (src_txt or "").lower())
        if m:
            n, r0 = int(m.group(1)), int(m.group(2)[1:])
            for k in range(n): defs.add(f"r{r0+k}")

    # === 调用 ===
    elif mb in ("call","calla"):
        uses |= regs_used_in(src_txt)

    # === 兜底 ===
    else:
        uses |= regs_used_in(src_txt)
        if dst_is_reg:
            # 对未知的单寄存器写，保守地认为 RMW
            defs.add(dst_txt.lower()); uses.add(dst_txt.lower())
        elif dst_mem:
            defs.add(dst_mem); uses |= regs_used_in(dst_txt); uses.add(dst_mem)

    return defs, uses
# ---------- 汇编解析 ----------
def parse_asm(path: Path):
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    pcs, pc2line, pc2size, info = [], {}, {}, {}
    for ln in lines:
        m4 = RE_LINE4.match(ln)
        if m4:
            pc_s, bytes_s, mnem, ops = m4.groups()
            pc = int(pc_s,16)
            size = len([b for b in bytes_s.strip().split() if b]) or 2
            pcs.append(pc)
            pc2line[pc]=ln; pc2size[pc]=size
            info[pc] = {"pc":pc,"mnem":mnem.strip().lower(),"ops":ops.strip()}
            continue
        m3 = RE_LINE3.match(ln)
        if m3:
            pc_s,mnem,ops = m3.groups()
            pc=int(pc_s,16)
            pcs.append(pc); pc2line[pc]=ln; pc2size[pc]=2
            info[pc] = {"pc":pc,"mnem":mnem.strip().lower(),"ops":ops.strip()}
    pcs.sort()
    return pcs, pc2line, pc2size, info

def parse_sym_asm_without_pc(sym_path: Path):
    """
    解析符号化汇编文件，不依赖PC地址，使用行号作为虚拟PC
    """
    sym_lines = sym_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    pcs, pc2line, pc2size, info = [], {}, {}, {}
    
    for line_num, ln in enumerate(sym_lines):
        # 跳过非指令行（标签、注释、字符串等）
        if not ln.strip() or ln.strip().startswith('.') or ln.strip().startswith(';') or ln.strip().startswith('\t.string'):
            continue
            
        # 匹配指令格式：\tMNEMONIC\tOPERANDS
        if ln.startswith('\t') and not ln.startswith('\t.'):
            parts = ln.strip().split(None, 1)
            if len(parts) >= 1:
                mnem = parts[0].lower()
                ops = parts[1] if len(parts) > 1 else ""
                
                # 调试输出
                if line_num < 30:  # 只输出前30行
                    print(f"Line {line_num}: '{ln.strip()}' -> mnem='{mnem}', ops='{ops}'")
                
                # 只处理实际的指令（跳过标签等）
                if mnem in ["mov", "mov.b", "mov.w", "add", "add.b", "add.w", "sub", "sub.b", "sub.w", 
                           "xor", "xor.b", "xor.w", "and", "and.b", "and.w", "bis", "bis.b", "bis.w", 
                           "bic", "bic.b", "bic.w", "dadd", "dadd.b", "dadd.w",
                           "inc", "inc.b", "inc.w", "dec", "dec.b", "dec.w", "clr", "clr.b", "clr.w", 
                           "inv", "inv.b", "inv.w", "swpb", "rra", "rra.b", "rra.w", "rla", "rla.b", "rla.w", 
                           "rrc", "rrc.b", "rrc.w", "rlc", "rlc.b", "rlc.w",
                           "push", "push.b", "push.w", "pushm", "pop", "pop.b", "pop.w", "popm", 
                           "call", "calla", "ret", "reti",
                           "jmp", "jz", "jnz", "jc", "jnc", "jl", "jge", "jna", "ja", "jn", "jlo", "jhs",
                           "nop", "eint", "dint"]:
                    # 使用行号作为虚拟PC
                    pc = line_num
                    pcs.append(pc)
                    pc2line[pc] = ln
                    pc2size[pc] = 2  # 默认大小
                    info[pc] = {"pc": pc, "mnem": mnem, "ops": ops}
                    print(f"  -> Added instruction: PC={pc}, mnem={mnem}, ops={ops}")
    
    pcs.sort()
    return pcs, pc2line, pc2size, info

# ---------- 跳转解码 ----------
def decode_targets(line_text):
    # 原有几种形式保留
    if m := RE_ABS_TGT.search(line_text):
        return [int(m.group(1),16)]
    if m := RE_HASH_TGT.search(line_text):
        try: return [int(m.group(1))]
        except: pass
    if m := RE_ABS.search(line_text):
        try: return [int(m.group(1),16)]
        except: pass

    # --- 新增：相对偏移 $+N / $-N ---
    if m := re.search(r"\$\s*([\+\-])\s*([0-9]+)", line_text):
        sign = 1 if m.group(1) == "+" else -1
        off  = int(m.group(2))
        # 从当前指令地址解析：先提取 PC，再加偏移
        pc_match = re.match(r"^\s*([0-9a-fA-F]+):", line_text)
        if pc_match:
            pc = int(pc_match.group(1), 16)
            target = pc + off
            return [target]
    return []

# ---------- CFG ----------
def build_cfg(pcs, pc2line, pc2size, info):
    succ, pred = defaultdict(list), defaultdict(list)
    pc_set = set(pcs)
    for pc in pcs:
        mnem = info[pc]["mnem"].split(".")[0]
        next_pc = pc + pc2size.get(pc,2)
        line = pc2line[pc]
        if mnem in RETS:  # ret 截断
            continue
        if mnem in UNCOND_JUMPS:
            for t in decode_targets(line):
                if t in pc_set:
                    succ[pc].append({"to":t,"kind":"jmp"}); pred[t].append(pc)
            continue
        if mnem in COND_JUMPS:
            for t in decode_targets(line):
                if t in pc_set:
                    succ[pc].append({"to":t,"kind":"cjmp"}); pred[t].append(pc)
            if next_pc in pc_set:
                succ[pc].append({"to":next_pc,"kind":"fallthrough"}); pred[next_pc].append(pc)
            continue
        if mnem in CALLS:
            if next_pc in pc_set:
                succ[pc].append({"to":next_pc,"kind":"after_call"}); pred[next_pc].append(pc)
            continue
        if next_pc in pc_set:
            succ[pc].append({"to":next_pc,"kind":"fallthrough"}); pred[next_pc].append(pc)
    return succ, pred

# ---------- Def-Use ----------
def compute_defs_uses(pcs, info):
    du={}
    for pc in pcs:
        mnem=info[pc]["mnem"]
        ops=info[pc]["ops"].split(";")[0].strip()
        base=mnem.split(".")[0]
        defs,uses=defs_uses_for(base,ops)
        du[pc]={"defs":sorted(defs),"uses":sorted(uses)}
    return du

# ---------- Reaching Definitions（含 MOV 等价传播） ----------
def reaching_definitions_copyprop(pcs, succ, pred, du, info):
    """
    标准到达定义 + MOV 等价传播：
      OUT[n] = GEN[n] ∪ (IN[n] - KILL[n]) ∪ MOVPROP[n](IN[n])
    其中，
      - GEN/KILL 与常规模型相同；
      - MOVPROP：若 n 是 mov/mova 且 src/dst 均为寄存器，
        则把 IN[n] 中对 src 的所有到达定义 (src, dpc) 映射成 (dst, dpc) 注入 OUT。
    """
    # 解析每条指令的 src/dst 文本
    def split_src_dst(ops_clean):
        if "," in ops_clean:
            s,d = [x.strip() for x in ops_clean.rsplit(",",1)]
            return s, d
        return ops_clean.strip(), None

    GEN, KILL = {}, {}
    for pc in pcs:
        defs=set(du[pc]["defs"])
        GEN[pc] = {(r,pc) for r in defs}
        # 杀死该寄存器以往的所有定义
        KILL[pc] = {(r,x) for r in defs for x in pcs}

    IN  = {pc:set() for pc in pcs}
    OUT = {pc:set() for pc in pcs}

    changed=True
    while changed:
        changed=False
        for pc in pcs:
            # 汇入
            IN_new=set()
            for p in pred.get(pc,[]): IN_new |= OUT[p]

            # 常规传递
            OUT_new = GEN[pc] | (IN_new - KILL[pc])

            # MOV 等价传播
            mnem = info[pc]["mnem"].split(".")[0]
            ops_clean = info[pc]["ops"].split(";")[0].strip()
            src_txt, dst_txt = split_src_dst(ops_clean)
            if mnem in ("mov","mova") and src_txt and dst_txt:
                src = src_txt.strip().lower()
                dst = dst_txt.strip().lower()
                if re.fullmatch(r"r[0-9]+", src) and re.fullmatch(r"r[0-9]+", dst):
                    # 把 IN 里所有 (src, dpc) 映射为 (dst, dpc)
                    for (r, dpc) in IN_new:
                        if r == src:
                            OUT_new.add((dst, dpc))

            if IN_new != IN[pc] or OUT_new != OUT[pc]:
                IN[pc]=IN_new; OUT[pc]=OUT_new; changed=True

    # per-use reaching defs（按寄存器分组）
    per_use_defs={}
    for pc in pcs:
        uses=du[pc]["uses"]
        m=defaultdict(list)
        for (r,def_pc) in IN[pc]:
            if r in uses:
                m[r].append(def_pc)
        per_use_defs[pc]={r:sorted(set(v)) for r,v in m.items()}
    return IN, OUT, per_use_defs

# ---------- 主程序 ----------
def main():
    ap=argparse.ArgumentParser(description="Build CFG+DFG with reaching definitions (copy-prop aware) for MSP430")
    ap.add_argument("asm_path")
    ap.add_argument("--build",default="build")
    ap.add_argument("--real-asm", help="Path to real assembly file for PC mapping")
    args=ap.parse_args()

    build=Path(args.build); build.mkdir(parents=True,exist_ok=True)

    # 如果提供了real-asm参数，使用符号化汇编+PC映射
    if args.real_asm:
        real_asm_path = Path(args.real_asm)
        pcs,pc2line,pc2size,info=parse_sym_asm_with_pc_mapping(Path(args.asm_path), real_asm_path)
    else:
        # 检查是否是符号化汇编文件（没有PC地址格式）
        asm_path = Path(args.asm_path)
        asm_content = asm_path.read_text(encoding="utf-8", errors="ignore")
        # 检查是否有PC地址格式（如 "0x4904: 2c 41 mov"）
        if not re.search(r'^\s*[0-9a-fA-F]+:\s+[0-9a-fA-F ]+\s+[a-zA-Z]', asm_content, re.MULTILINE):
            pcs,pc2line,pc2size,info=parse_sym_asm_without_pc(asm_path)
        else:
            pcs,pc2line,pc2size,info=parse_asm(asm_path)
    
    succ,pred=build_cfg(pcs,pc2line,pc2size,info)
    du=compute_defs_uses(pcs,info)
    IN,OUT,per_use_defs=reaching_definitions_copyprop(pcs,succ,pred,du,info)

    # --- 输出 CFG ---
    cfg_nodes=[{"pc":f"0x{pc:04x}","text":pc2line[pc].strip()} for pc in pcs]
    cfg_edges=[]
    for pc in pcs:
        for e in succ.get(pc,[]): cfg_edges.append({"from":f"0x{pc:04x}","to":f"0x{e['to']:04x}","kind":e["kind"]})
    (build/"cfg.json").write_text(json.dumps({"nodes":cfg_nodes,"edges":cfg_edges},indent=2),encoding="utf-8")

    # --- 输出 DFG（行式） ---
    dfg_rows=[]
    for pc in pcs:
        row={
            "pc":f"0x{pc:04x}",
            "text":pc2line[pc].strip(),
            "defs":du[pc]["defs"],
            "uses":du[pc]["uses"],
            "reaching_defs":{r:[f"0x{x:04x}" for x in xs] for r,xs in per_use_defs[pc].items()}
        }
        dfg_rows.append(row)
    (build/"dfg.json").write_text(json.dumps(dfg_rows,indent=2),encoding="utf-8")

    print(f"[OK] CFG → {build/'cfg.json'}")
    print(f"[OK] DFG → {build/'dfg.json'}")

if __name__=="__main__":
    main()