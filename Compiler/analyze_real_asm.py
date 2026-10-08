#!/usr/bin/env python3
# =============================================================
# ReflexSave: Stage 4 — DFG/CFG-driven Semantic Traceback (mem[] aware)
#   - 使用 Stage 3 的 cfg.json + dfg.json（行式列表）
#   - mov #imm → 常量终止；算术类遇 #imm 继续追 DST_OLD
#   - 仅 &0xXXXX / n(r1) / @rX 视为内存来源（ABS/STACK）
#   - DFG 优先；缺边时用“CFG 反向 BFS + 最近重定义”兜底
#   - 兼容 DFG 中的 mem[...] 写点，并能从中抽取 base 寄存器
#   - 输出：与原 candidates.json 同结构
# =============================================================

import argparse, json, re, subprocess
from pathlib import Path
from collections import defaultdict, deque

# ---------- 正则 ----------
RE_LINE4 = re.compile(r"^\s*([0-9a-fA-F]+):\s+([0-9a-fA-F ]+)\s+([A-Za-z.]+)\s*(.*)$")
RE_LINE3 = re.compile(r"^\s*([0-9a-fA-F]+):\s+([A-Za-z.]+)\s*(.*)$")

RE_ABS  = re.compile(r"&0x([0-9a-fA-F]+)")
RE_IDX  = re.compile(r"(-?\d+)\((r[0-9]+)\)")
RE_IND  = re.compile(r"@r([0-9]+)")
RE_IMM  = re.compile(r"#(-?\d+)")

# mem[...] 节点：mem[55(r12)] / mem[@r12] / mem[&0x1234]
RE_MEM_NODE = re.compile(r"^mem\[(.+)\]\s*$", re.IGNORECASE)
RE_MEM_IDX  = re.compile(r"(-?\d+)\((r[0-9]+)\)", re.IGNORECASE)
RE_MEM_IND  = re.compile(r"@r([0-9]+)", re.IGNORECASE)
RE_MEM_ABS  = re.compile(r"&0x([0-9a-fA-F]+)", re.IGNORECASE)

# ---------- 指令集（只筛“写目的”的候选） ----------
WRITE_DST_MNEMS = {
    "mov","add","sub","xor","and","bis","bic","dadd",
    "inc","dec","clr","inv","swpb","rra","rla","rrc","rlc"
}
STRUCT_STACK_MNEMS = {"push","pushm","pop","popm"}

# ---------- 平台信息 ----------
def find_runtime_root(start: Path) -> Path:
    cur = start.resolve()
    for _ in range(8):
        if (cur / "Runtime").exists():
            return cur / "Runtime"
        cur = cur.parent
    raise SystemExit(f"❌ cannot locate Runtime/ directory from {start}")

def load_platform_config(mcu: str) -> dict:
    runtime_root = find_runtime_root(Path(__file__).parent)
    cfg_path = runtime_root / "config" / f"{mcu}.json"
    parser_path = runtime_root / "src/port/msp430" / "parse_platform.py"
    if not cfg_path.exists():
        subprocess.run(["python3", str(parser_path),
                        "--mcu", mcu,
                        "--config-dir", str(cfg_path.parent)], check=True)
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    # 归一化 memory regions
    norm_regions = {}
    for n, pair in cfg.get("memory_regions", cfg.get("memory_map", {})).items():
        try:
            lo, hi = [int(x,16) if isinstance(x,str) else int(x) for x in pair]
            norm_regions[n] = (lo, hi)
        except:
            continue
    cfg["memory_regions_norm"] = norm_regions

    # 归一化 symbols（用于 ±1 确认 MMIO）
    aset = set()
    for _, val in cfg.get("symbols", {}).items():
        try:
            aset.add(int(val, 16) if isinstance(val, str) else int(val))
        except:
            pass
    cfg["symbols_addr_set"] = aset
    return cfg

def classify_addr(addr:int, cfg:dict)->str:
    aset=cfg.get("symbols_addr_set",set())
    if addr in aset or addr-1 in aset or addr+1 in aset:
        return "MMIO"
    
    # MSP430 外设地址范围识别
    if 0x0000 <= addr <= 0x0FFF:  # 外设寄存器区域
        return "MMIO"
    elif 0x1C00 <= addr <= 0x23FF:  # RAM 区域 (根据 msp430fr5969.ld)
        return "RAM"
    elif 0x4400 <= addr <= 0xFF7F:  # FRAM 区域
        return "FRAM_OR_FLASH"
    
    # 原有的内存区域分类逻辑
    for n,(lo,hi) in cfg["memory_regions_norm"].items():
        if lo<=addr<=hi:
            up=n.upper()
            if "RAM" in up: return "RAM"
            if any(x in up for x in ("FRAM","FLASH","ROM","CODE")): return "FRAM_OR_FLASH"
            if any(x in up for x in ("SFR","IO","PERIPH","PORT")): return "MMIO"
    return "OTHER"

# ---------- 反汇编解析 ----------
def parse_asm(path:Path):
    lines=path.read_text(encoding="utf-8",errors="ignore").splitlines()
    pcs,pc2line={},{}
    order=[]
    for ln in lines:
        m4=RE_LINE4.match(ln)
        if m4:
            pc=int(m4.group(1),16); pc2line[pc]=ln; order.append(pc); continue
        m3=RE_LINE3.match(ln)
        if m3:
            pc=int(m3.group(1),16); pc2line[pc]=ln; order.append(pc)
    return lines, pc2line, sorted(order)

def parse_mnem_ops_from_line(line:str):
    m4=RE_LINE4.match(line)
    if m4: return m4.group(3).lower(), m4.group(4).split(";")[0].strip()
    m3=RE_LINE3.match(line)
    if m3: return m3.group(2).lower(), m3.group(3).split(";")[0].strip()
    return None, None

# ---------- CFG/DFG 载入 ----------
def to_int_pc(v): 
    return int(v,16) if isinstance(v,str) and v.lower().startswith("0x") else int(v)

def load_cfg(cfg_json: Path):
    obj=json.loads(cfg_json.read_text(encoding="utf-8"))
    nodes=set(to_int_pc(n["pc"]) for n in obj.get("nodes",[]))
    adj,radj=defaultdict(list),defaultdict(list)
    for e in obj.get("edges",[]):
        u,v=to_int_pc(e["from"]),to_int_pc(e["to"])
        adj[u].append(v); radj[v].append(u)
    return nodes,adj,radj

def parse_mem_base(mem_expr: str):
    """
    从 'mem[... ]' 内容里抽取 base 寄存器/绝对地址类型：
      - mem[55(r12)]  → ("IDX","r12", 55)
      - mem[@r10]     → ("IND","r10", None)
      - mem[&0x020b]  → ("ABS",None, 0x020b)
    如无法识别，返回 ("UNK", None, None)
    """
    inner = mem_expr.strip()
    if m := RE_MEM_IDX.search(inner):
        return ("IDX", m.group(2).lower(), int(m.group(1)))
    if m := RE_MEM_IND.search(inner):
        return ("IND", "r"+m.group(1), None)
    if m := RE_MEM_ABS.search(inner):
        return ("ABS", None, int(m.group(1),16))
    return ("UNK", None, None)

def load_dfg(dfg_json: Path):
    """
    兼容行式 DFG：
      [
        {
          "pc":"0x5c96",
          "text":"...",
          "defs":[ "r12", "mem[55(r12)]", ... ],
          "uses":[ "r12", "r10", ... ],
          "reaching_defs": { "r12": ["0x5c92", ...], ... }
        }, ...
      ]
    生成：
      node_meta[pc] = {
        "mnem": <mnemonic from text>,
        "ops" : <ops from text>,
        "writes": [... raw defs ...],
        "writes_bases": set of base regs extracted from mem[...] defs,
        "reads": [... raw uses ...]  # 寄存器名
      }
      incoming[(use_pc, reg)] = list of (def_pc, reg)  # 来自 reaching_defs
    """
    data=json.loads(dfg_json.read_text(encoding="utf-8"))
    node_meta={}
    incoming=defaultdict(list)

    for n in data:
        pc=to_int_pc(n["pc"])
        text = (n.get("text") or "").strip()
        # 尝试从 text 解析 mnem/ops（防御）
        mnem, ops = None, None
        m4 = RE_LINE4.search(text)
        if m4:
            mnem = m4.group(3).strip().lower()
            ops  = m4.group(4).split(";")[0].strip()
        else:
            m3 = RE_LINE3.search(text)
            if m3:
                mnem = m3.group(2).strip().lower()
                ops  = m3.group(3).split(";")[0].strip()
        mnem = mnem or (n.get("mnem") or "").lower()
        ops  = ops  or (n.get("ops")  or "")

        writes = [w.lower() for w in n.get("defs",[])]
        reads  = [r.lower() for r in n.get("uses",[])]

        # 抽取 mem[...] 的 base regs
        writes_bases=set()
        for w in writes:
            m = RE_MEM_NODE.match(w)
            if m:
                kind, base, _ = parse_mem_base(m.group(1))
                if base: writes_bases.add(base)

        node_meta[pc]={
            "mnem": mnem,
            "ops": ops,
            "writes": writes,            # 包括 rX / mem[...]
            "writes_bases": sorted(writes_bases),  # 仅 mem[...] 的 base reg
            "reads": reads               # 仅寄存器名
        }

        # reaching_defs：只对寄存器
        for reg, defs in (n.get("reaching_defs") or {}).items():
            reg_l = reg.lower()
            for d in defs:
                try:
                    dp = to_int_pc(d)
                    incoming[(pc, reg_l)].append((dp, reg_l))
                except:
                    pass

    return node_meta, incoming

# ---------- CFG 反向可达 ----------
def cfg_backward_reachable(radj,start,limit=20000):
    seen=set(); q=deque([start])
    while q and len(seen)<limit:
        u=q.popleft()
        for p in radj.get(u,[]):
            if p not in seen: seen.add(p); q.append(p)
    return seen

# ---------- 查找函数入口 ----------
def find_function_entry(pc, asm_map, limit=0x100):
    """向前查找最近的函数入口（pushm 指令）"""
    for i in range(limit):
        check_pc = pc - i
        if check_pc in asm_map:
            line = asm_map[check_pc]
            if "pushm" in line.lower():
                return check_pc
    return None

# ---------- DFG 驱动溯源 ----------
def trace_via_dfg(use_pc, base_reg, asm_map, node_meta, incoming, radj, visited, plat_cfg, depth=0, max_depth=400):
    """
    重点：base_reg 一定是寄存器名（如 r12）。先用 reaching_defs，
    没边就用 CFG 反向可达 + 最近"写该寄存器"的指令兜底。
    """
    key=(use_pc, base_reg)
    if key in visited or depth>max_depth:
        return ("UNKNOWN",[{"reason":f"stop recursion depth={depth} base={base_reg}"}],None)
    visited.add(key)

    # 检查特殊寄存器
    if base_reg == "r1":
        # r1 是栈指针，总是可用的
        return ("STACK", [{"reason": f"{base_reg} is the stack pointer"}], None)
    
    # 检查是否是函数参数寄存器（r10-r15）在函数入口附近
    if base_reg in ["r10", "r11", "r12", "r13", "r14", "r15"]:
        # 检查是否在函数入口附近（向前查找 pushm 指令）
        func_entry = find_function_entry(use_pc, asm_map)
        if func_entry and use_pc - func_entry < 0x50:  # 增加阈值到 0x50
            return ("FUNC_PARAM", [{"reason": f"{base_reg} is a function parameter at entry"}], None)

    # 1) DFG incoming（reaching_defs）
    preds=incoming.get((use_pc, base_reg), [])
    if preds:
        # 可能多条；优先返回强命中
        branch=[]
        for def_pc,_ in preds:
            mnem,ops = _mnem_ops_at(def_pc, asm_map, node_meta)
            if not mnem or not ops: 
                continue
            # 处理单操作数和双操作数指令
            if "," in ops:
                s_txt,d_txt=[x.strip() for x in ops.rsplit(",",1)]
            else:
                # 单操作数指令（inc, dec, clr 等）
                s_txt = ""
                d_txt = ops.strip()
            if d_txt.lower()!=base_reg:
                # DFG 里也许只是"到达定义"的寄存器，不一定是同一条指令写了 base_reg；
                # 这里放宽约束：若该指令确实写了 base_reg，也行
                meta = node_meta.get(def_pc,{})
                if base_reg not in (meta.get("writes") or []):
                    continue
            r=handle_one_def_node(def_pc,mnem,ops,mnem.split(".")[0],s_txt,d_txt,
                                  asm_map,node_meta,incoming,radj,visited,plat_cfg,depth,max_depth)
            branch.append(r)
            if r[0] in ("ABS","STACK"): return r
        if branch:
            # 优先选择能成功追踪的定义（非 UNKNOWN）
            success = [r for r in branch if r[0] not in ("UNKNOWN",)]
            if success:
                for r in success:
                    if r[0]=="REG_CONST": return r
                return success[0]
            # 否则返回第一个
            for r in branch:
                if r[0]=="REG_CONST": return r
            return branch[0]

    # 2) 兜底：CFG 反向可达范围内，最近“定义了 base_reg”的指令
    reachable=cfg_backward_reachable(radj,use_pc)
    for pc in sorted(reachable,reverse=True):
        meta=node_meta.get(pc)
        if not meta: continue
        # 该点是否定义了这个寄存器？
        if base_reg not in (meta.get("writes") or []):
            continue
        mnem,ops=_mnem_ops_at(pc, asm_map, node_meta)
        if not mnem or not ops or "," not in (ops or ""): 
            continue
        s_txt,d_txt=[x.strip() for x in ops.rsplit(",",1)]
        if d_txt.lower()!=base_reg:
            # 再次放宽：只要写了 base_reg 就认为是该寄存器最近定义点
            pass
        return handle_one_def_node(pc,mnem,ops,mnem.split(".")[0],s_txt,d_txt,
                                   asm_map,node_meta,incoming,radj,visited,plat_cfg,depth,max_depth)

    # 最后的兜底：如果是函数参数寄存器但没有找到定义，认为是函数参数
    if base_reg in ["r10", "r11", "r12", "r13", "r14", "r15"]:
        return ("FUNC_PARAM", [{"reason": f"{base_reg} has no reaching definitions, likely function parameter"}], None)
    
    return ("UNKNOWN",[{"reason":f"no def for {base_reg} @0x{use_pc:04x}"}],None)

def _mnem_ops_at(pc, asm_map, node_meta):
    meta=node_meta.get(pc)
    mnem=meta.get("mnem") if meta else None
    ops =meta.get("ops")  if meta else None
    if (not mnem) or (not ops):
        line=asm_map.get(pc,"")
        mnem2,ops2=parse_mnem_ops_from_line(line)
        mnem=mnem or mnem2; ops=ops or ops2
    return mnem, ops

def handle_one_def_node(pc,mnem,ops,mb,src,dst,asm_map,node_meta,incoming,radj,visited,plat_cfg,depth,max_depth):
    trace=[]; e={"pc":f"0x{pc:04x}","mnemonic":mnem,"operands":ops}

    # --- 单操作数指令：inc/dec 等需要追踪 dst 的旧值 ---
    if mb in ("inc","dec","rra","rla","rrc","rlc","swpb","sxt") and not src:
        e["reason"]=f"{dst} modified by {mb} — continue tracing old {dst}"
        trace.append(e)
        sub=trace_via_dfg(pc,(dst or "").strip().lower(),asm_map,node_meta,incoming,radj,visited,plat_cfg,depth+1,max_depth)
        trace+=sub[1]
        return sub

    # --- 立即数：mov 终止；算术类继续追 DST_OLD ---
    if RE_IMM.fullmatch((src or "").strip()):
        if mb=="mov":
            e["reason"]=f"{dst} := {src} (immediate constant) — terminate"
            trace.append(e)
            return ("REG_CONST",trace,None)
        else:
            e["reason"]=f"{dst} modified by {src} via {mb} — continue tracing old {dst}"
            trace.append(e)
            sub=trace_via_dfg(pc,(dst or "").strip().lower(),asm_map,node_meta,incoming,radj,visited,plat_cfg,depth+1,max_depth)
            trace+=sub[1]
            return sub

    # --- 绝对地址读取 &0xXXXX → 终止 ---
    if m := RE_ABS.search(src or ""):
        addr=int(m.group(1),16)
        e["reason"]=f"{dst} loaded from &0x{addr:04x}"
        trace.append(e)
        return ("ABS",trace,addr)

    # --- 栈相对寻址 n(r1) → 终止；其余 n(rX) 继续追 base ---
    if m := RE_IDX.search(src or ""):
        disp, base = int(m.group(1)), m.group(2).lower()
        e["reason"]=f"{dst} loaded from {disp}({base})"
        trace.append(e)
        if base=="r1":
            return ("STACK",trace,None)
        sub=trace_via_dfg(pc,base,asm_map,node_meta,incoming,radj,visited,plat_cfg,depth+1,max_depth)
        trace+=sub[1]
        return sub

    # --- 间接 @rX → 继续追寄存器来源（不终止） ---
    if m := RE_IND.search(src or ""):
        base="r"+m.group(1)
        e["reason"]=f"{dst} indirectly loaded from {base}"
        trace.append(e)
        sub=trace_via_dfg(pc,base,asm_map,node_meta,incoming,radj,visited,plat_cfg,depth+1,max_depth)
        trace+=sub[1]
        return sub

    # --- 算术指令：对于 add/sub 等，dst 的值 = 旧 dst 值 + src 值
    # 所以我们需要同时追踪 dst 的旧值和 src 的来源
    if mb in ("add","sub","xor","and","bis","bic") and re.fullmatch(r"r[0-9]+",(src or "").strip().lower()):
        # 对于间接寻址溯源，我们主要关心 dst 的旧值能否追溯到内存/栈
        e["reason"]=f"{dst} modified by {src} via {mb} — trace old {dst}"
        trace.append(e)
        sub=trace_via_dfg(pc,(dst or "").strip().lower(),asm_map,node_meta,incoming,radj,visited,plat_cfg,depth+1,max_depth)
        trace+=sub[1]
        return sub
    
    # --- 纯寄存器传递（mov 等） ---
    if re.fullmatch(r"r[0-9]+",(src or "").strip().lower()):
        e["reason"]=f"{dst} ← {src} via {mnem}"
        trace.append(e)
        sub=trace_via_dfg(pc,(src or "").strip().lower(),asm_map,node_meta,incoming,radj,visited,plat_cfg,depth+1,max_depth)
        trace+=sub[1]
        # 如果追踪失败但是在函数入口附近，可能是函数参数
        if sub[0] == "UNKNOWN" and len(sub[1]) == 1 and "no def for" in sub[1][0].get("reason", ""):
            # 检查是否是函数入口附近的寄存器（r12-r15 通常是参数寄存器）
            if src.strip().lower() in ["r12", "r13", "r14", "r15"]:
                trace.append({"reason": f"{src} is likely a function parameter"})
                return ("FUNC_PARAM", trace, None)
        return sub

    # --- 清零类 ---
    if mb=="clr":
        e["reason"]=f"{dst} cleared"
        trace.append(e)
        return ("REG_CONST",trace,None)

    e["reason"]=f"unhandled source pattern for {dst}"
    trace.append(e)
    return ("UNKNOWN",trace,None)

# ---------- 主分析 ----------
def analyze_asm(asm_path,cfg_path,dfg_path,plat_cfg,out_json):
    lines,pc2line,pcs=parse_asm(asm_path)
    asm_map={pc:pc2line[pc] for pc in pcs}
    cfg_nodes,cfg_adj,cfg_radj=load_cfg(cfg_path)
    dfg_nodes,dfg_incoming=load_dfg(dfg_path)

    # 加载A_sym.s中的指令，只分析在源码中存在的指令
    sym_asm_path = Path("build/A_sym.s")
    sym_instructions = set()
    if sym_asm_path.exists():
        sym_lines = sym_asm_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for ln in sym_lines:
            if ln.startswith('\t') and not ln.startswith('\t.'):
                parts = ln.strip().split(None, 1)
                if len(parts) >= 1:
                    mnem = parts[0].lower()
                    ops = parts[1] if len(parts) > 1 else ""
                    sym_instructions.add((mnem, ops))
    
    # 加载符号地址到绝对地址的映射
    symbol_map = {}
    symbols_ld_path = Path("Runtime/src/port/msp430/msp430fr5969_symbols.ld")
    if symbols_ld_path.exists():
        symbols_content = symbols_ld_path.read_text(encoding="utf-8", errors="ignore")
        for line in symbols_content.splitlines():
            if "PROVIDE(" in line and "=" in line:
                # 解析 PROVIDE(SYMBOL = 0xXXXX);
                match = re.search(r'PROVIDE\((\w+)\s*=\s*(0x[0-9a-fA-F]+)\)', line)
                if match:
                    symbol = match.group(1)
                    addr = int(match.group(2), 16)
                    symbol_map[symbol] = addr

    results=[]
    filtered_count = 0
    total_count = 0

    for pc in pcs:
        line=asm_map[pc]; mnem,ops=parse_mnem_ops_from_line(line)
        if not mnem or not ops or "," not in ops: 
            continue
        mnem_l=mnem.lower(); base_m=mnem_l.split(".")[0]
        if base_m not in WRITE_DST_MNEMS or base_m in STRUCT_STACK_MNEMS:
            continue
        
        total_count += 1
        
        # 只分析在A_sym.s中存在的指令
        # 将绝对地址转换为符号地址进行匹配
        sym_ops = ops
        for symbol, addr in symbol_map.items():
            sym_ops = sym_ops.replace(f"&0x{addr:04x}", f"&{symbol}")
        
        # 标准化操作数格式（移除多余空格，统一寄存器大小写）
        sym_ops = re.sub(r'\s+', ' ', sym_ops.strip())
        # 将寄存器名称统一为大写
        sym_ops = re.sub(r'\br([0-9]+)\b', lambda m: f'R{m.group(1)}', sym_ops)
        
        src,dst=[x.strip() for x in ops.rsplit(",",1)]
        
        # 只过滤掉明显不在源码中的指令（如库函数）
        # 如果指令是写内存/外设的，就分析它
        is_memory_write = False
        if dst.startswith('&0x'):  # 绝对地址
            is_memory_write = True
        elif re.match(r'\d+\(r1\)', dst):  # 栈相对寻址
            is_memory_write = True
        elif dst.startswith('@'):  # 间接寻址
            is_memory_write = True
        
        if not is_memory_write:
            filtered_count += 1
            continue
        ws={"mode":"REG","base":None,"disp":None,"effective_addr":None}
        dst_mode="REG"; base=None; abs_addr=None

        if m:=RE_ABS.search(dst):
            dst_mode="ABS"; abs_addr=int(m.group(1),16)
            ws.update({"mode":"ABS","effective_addr":f"0x{abs_addr:04x}"})
        elif m:=RE_IDX.search(dst):
            dst_mode="IDX"; base=m.group(2).lower()
            ws.update({"mode":"IDX","base":base,"disp":int(m.group(1))})
        elif m:=RE_IND.search(dst):
            dst_mode="IND"; base="r"+m.group(1)
            ws.update({"mode":"IND","base":base})
        else:
            # 非内存写（dst 不是 ABS/IDX/IND）跳过
            continue

        width=1 if ".b" in mnem_l else 2
        entry={"pc":f"0x{pc:04x}","mnemonic":mnem_l,"operands":ops,
               "width":width,"is_memory_write":True,"requires_backup":False,
               "write_site":ws,"value_origin":{"kind":"UNKNOWN"},"trace_chain":[]}

        # 绝对地址直接写
        if dst_mode=="ABS":
            region=classify_addr(abs_addr,plat_cfg)
            # 暂时允许MMIO备份（某些程序需要外设状态）
            # TODO: 更精细的过滤策略
            entry["target"]=region; entry["requires_backup"]=(region in ("RAM","MMIO"))
            results.append(entry); continue

        # 栈写（以 r1 为基址）
        if ws["base"]=="r1":
            entry["target"]="STACK"; entry["requires_backup"]=True
            entry["trace_chain"].append({"reason":"stack frame write via r1"})
            
            # 溯源源操作数
            ops = entry.get("operands", "")
            if "," in ops:
                src, dst = ops.split(",", 1)
                src = src.strip()
                # 如果源是寄存器，需要溯源
                if re.fullmatch(r"r\d+", src.lower()):
                    visited = set()
                    mode, trace, addr = trace_via_dfg(pc, src.lower(), asm_map, dfg_nodes, dfg_incoming, cfg_radj, visited, plat_cfg)
                    entry["trace_chain"].extend(trace)
                    entry["value_origin"] = {"kind": mode}
                    if mode == "ABS" and addr is not None:
                        region = classify_addr(addr, plat_cfg)
                        entry["value_origin"]["addr"] = f"0x{addr:04x}"
                        entry["value_origin"]["region"] = region
                elif src.startswith("#"):
                    entry["value_origin"] = {"kind": "IMMEDIATE"}
                else:
                    entry["value_origin"] = {"kind": "UNKNOWN"}
            else:
                entry["value_origin"] = {"kind": "UNKNOWN"}
                
            results.append(entry); continue

        # 其它基址：DFG 溯源 base_reg（如 r12）
        if ws["base"]:
            visited=set()
            mode,trace,addr=trace_via_dfg(pc,ws["base"],asm_map,dfg_nodes,dfg_incoming,cfg_radj,visited,plat_cfg)
            entry["trace_chain"]=trace

            if mode=="ABS" and addr is not None:
                region=classify_addr(addr,plat_cfg)
                entry["value_origin"]={"kind":"ABS","addr":f"0x{addr:04x}","region":region}
                entry["target"]=f"{region}_DERIVED"; entry["requires_backup"]=(region in ("RAM","MMIO"))
            elif mode=="STACK":
                entry["value_origin"]={"kind":"STACK"}; entry["target"]="STACK_DERIVED"; entry["requires_backup"]=True
            elif mode=="REG_CONST":
                entry["value_origin"]={"kind":"REG_CONST"}; entry["target"]="REG_CONST_DERIVED"
            elif mode=="FUNC_PARAM":
                entry["value_origin"]={"kind":"FUNC_PARAM"}; entry["target"]="FUNC_PARAM_DERIVED"; entry["requires_backup"]=True
            else:
                entry["value_origin"]={"kind":"UNKNOWN"}; entry["target"]="MEM_UNKNOWN"; entry["requires_backup"]=True

            results.append(entry)

    out_json.write_text(json.dumps(results,indent=2),encoding="utf-8")
    print(f"[stage4] analyzed writes: {len(results)} → {out_json}")
    print(f"[stage4] 统计: 总写指令={total_count}, 过滤掉={filtered_count}, 分析={len(results)}")

# ---------- 入口 ----------
def main():
    ap=argparse.ArgumentParser(description="Stage 4: Semantic Traceback (CFG+DFG, mem[] aware)")
    ap.add_argument("asm_path"); ap.add_argument("--cfg",default="build/cfg.json")
    ap.add_argument("--dfg",default="build/dfg.json")
    ap.add_argument("--out",default="build/candidates.json")
    ap.add_argument("--mcu",default="msp430fr5969")
    args=ap.parse_args()
    plat_cfg=load_platform_config(args.mcu)
    analyze_asm(Path(args.asm_path),Path(args.cfg),Path(args.dfg),plat_cfg,Path(args.out))

if __name__=="__main__":
    main()