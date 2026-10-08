#!/usr/bin/env python3
"""
LLVM IR 解析器 — 从 .ll 文件提取函数、store、alloca、call、br 等信息

输入: .ll 文件 (clang --target=msp430 -S -emit-llvm 生成)
输出: 结构化的 IR 数据 (JSON)

支持解析:
  - 全局变量 (@name = ... global ...)
  - 函数定义 (define ... @func_name(...) { ... })
  - store 指令 (写操作)
  - load 指令 (读操作)
  - alloca 指令 (栈分配)
  - call 指令 (函数调用)
  - br 指令 (分支/跳转)
  - getelementptr 指令 (数组/结构体索引)
"""

import re
import json
import argparse
from collections import OrderedDict


# MSP430 外设地址映射（用于识别外设写入）
MSP430_PERIPHERALS = {
    'WDTCTL', 'PMMCTL0', 'PM5CTL0',
    'CSCTL0_H', 'CSCTL1', 'CSCTL2', 'CSCTL3',
    'PAOUT_L', 'PADIR_L', 'PASEL0_H', 'PASEL1_H',
    'PBOUT_L', 'PBDIR_L',
    'UCA0CTLW0', 'UCA0BRW_L', 'UCA0BRW_H', 'UCA0MCTLW',
    'UCA0IFG', 'UCA0TXBUF', 'UCA0RXBUF',
    'TB0CTL', 'TB0CCTL0', 'TB0CCTL1', 'TB0CCR0', 'TB0CCR1',
}

INIT_FUNCTIONS = {
    'clock_init', 'uart_init', 'init', 'init_hw',
    'INIT_CONSOLE', 'mspconsole_init', 'UART_init',
}

ISR_FUNCTIONS = {
    'TimerB1_ISR', 'TimerB0_ISR', 'Timer0_B1_ISR', 'Timer_B0_ISR',
}


class LLVMIRParser:
    """LLVM IR (.ll) 文件解析器"""

    def __init__(self, ll_path):
        self.ll_path = ll_path
        self.globals = {}
        self.functions = OrderedDict()
        self.struct_types = {}
        self.raw_lines = []

    def parse(self):
        with open(self.ll_path, 'r') as f:
            self.raw_lines = f.readlines()

        self._parse_globals()
        self._parse_struct_types()
        self._parse_functions()

        return {
            'source': self.ll_path,
            'globals': self.globals,
            'struct_types': self.struct_types,
            'functions': self.functions,
        }

    # ------------------------------------------------------------------
    # globals
    # ------------------------------------------------------------------
    def _parse_globals(self):
        for line in self.raw_lines:
            line = line.strip()
            m = re.match(
                r'@(\w+)\s*=\s*(?:dso_local\s+)?(?:external\s+)?'
                r'(?:(?:unnamed_addr\s+)?(?:constant|global))\s+(.*)',
                line)
            if m:
                name = m.group(1)
                rest = m.group(2)
                is_external = 'external' in line
                self.globals[name] = {
                    'name': name,
                    'is_external': is_external,
                    'is_peripheral': name in MSP430_PERIPHERALS,
                    'type_str': rest.split(',')[0].strip(),
                }

    def _parse_struct_types(self):
        for line in self.raw_lines:
            m = re.match(r'(%struct\.\w+)\s*=\s*type\s*\{(.*)\}', line.strip())
            if m:
                name = m.group(1)
                fields_str = m.group(2).strip()
                self.struct_types[name] = fields_str

    # ------------------------------------------------------------------
    # functions
    # ------------------------------------------------------------------
    def _parse_functions(self):
        i = 0
        while i < len(self.raw_lines):
            line = self.raw_lines[i].strip()
            m = re.match(r'define\s+.*@(\w+)\s*\(([^)]*)\)\s*(.*)\{', line)
            if m:
                func_name = m.group(1)
                params_str = m.group(2).strip()
                attrs = m.group(3).strip()
                func, end_i = self._parse_function_body(func_name, params_str, attrs, i + 1)
                self.functions[func_name] = func
                i = end_i + 1
            else:
                i += 1

    def _parse_function_body(self, func_name, params_str, attrs, start_line):
        func = {
            'name': func_name,
            'params': self._parse_params(params_str),
            'is_isr': 'msp430_intrcc' in attrs or func_name in ISR_FUNCTIONS,
            'is_init': func_name in INIT_FUNCTIONS,
            'blocks': OrderedDict(),
            'stores': [],
            'loads': [],
            'allocas': [],
            'calls': [],
            'branches': [],
            'geps': [],
            'line_start': start_line,
            'line_end': None,
        }

        current_block = 'entry'
        func['blocks'][current_block] = {'instructions': [], 'label_line': start_line}

        i = start_line
        while i < len(self.raw_lines):
            line = self.raw_lines[i].rstrip()
            stripped = line.strip()

            if stripped == '}':
                func['line_end'] = i
                return func, i

            # basic block label
            lbl = re.match(r'^(\w[\w.]*):\s*(?:;.*)?$', stripped)
            if lbl:
                current_block = lbl.group(1)
                func['blocks'][current_block] = {'instructions': [], 'label_line': i}
                i += 1
                continue

            if not stripped or stripped.startswith(';'):
                i += 1
                continue

            inst = self._parse_instruction(stripped, i, func_name, current_block)
            if inst:
                func['blocks'][current_block]['instructions'].append(inst)
                cat = inst['category']
                if cat == 'store':
                    func['stores'].append(inst)
                elif cat == 'load':
                    func['loads'].append(inst)
                elif cat == 'alloca':
                    func['allocas'].append(inst)
                elif cat == 'call':
                    func['calls'].append(inst)
                elif cat == 'br':
                    func['branches'].append(inst)
                elif cat == 'gep':
                    func['geps'].append(inst)

            i += 1

        func['line_end'] = i
        return func, i

    @staticmethod
    def _parse_params(params_str):
        if not params_str.strip():
            return []
        params = []
        for p in params_str.split(','):
            p = p.strip()
            parts = p.rsplit(None, 1)
            if len(parts) == 2:
                params.append({'type': parts[0], 'name': parts[1]})
            else:
                params.append({'type': p, 'name': ''})
        return params

    # ------------------------------------------------------------------
    # instruction parser
    # ------------------------------------------------------------------
    def _parse_instruction(self, line, line_no, func_name, block):
        base = {'raw': line, 'line': line_no, 'function': func_name, 'block': block}

        # ---- store ----
        m = re.match(
            r'store\s+(volatile\s+)?(\S+)\s+(.+?),\s+ptr\s+(.+?)(?:,\s+align\s+(\d+))?$',
            line)
        if m:
            return {**base,
                    'category': 'store',
                    'is_volatile': m.group(1) is not None,
                    'value_type': m.group(2),
                    'value': m.group(3).strip(),
                    'dest': m.group(4).strip(),
                    'align': int(m.group(5)) if m.group(5) else 2,
                    'dest_is_peripheral': self._is_peripheral_ptr(m.group(4).strip()),
                    'dest_is_global': m.group(4).strip().startswith('@'),
                    }

        # ---- load ----
        m = re.match(
            r'(%\S+)\s*=\s*load\s+(volatile\s+)?(\S+),\s+ptr\s+(.+?)(?:,\s+align\s+(\d+))?$',
            line)
        if m:
            return {**base,
                    'category': 'load',
                    'result': m.group(1),
                    'is_volatile': m.group(2) is not None,
                    'value_type': m.group(3),
                    'src': m.group(4).strip(),
                    'align': int(m.group(5)) if m.group(5) else 2,
                    }

        # ---- alloca ----
        m = re.match(r'(%\S+)\s*=\s*alloca\s+(.+?)(?:,\s+align\s+(\d+))?$', line)
        if m:
            return {**base,
                    'category': 'alloca',
                    'result': m.group(1),
                    'alloc_type': m.group(2).strip(),
                    'align': int(m.group(3)) if m.group(3) else 2,
                    }

        # ---- call ----
        m = re.match(r'(?:(%\S+)\s*=\s*)?call\s+.*@(\w+)\s*\(([^)]*)\)', line)
        if m:
            return {**base,
                    'category': 'call',
                    'result': m.group(1) or '',
                    'callee': m.group(2),
                    'args_raw': m.group(3).strip(),
                    }

        # ---- br ----
        m = re.match(r'br\s+i1\s+(\S+),\s+label\s+%(\S+),\s+label\s+%(\S+)', line)
        if m:
            return {**base,
                    'category': 'br',
                    'is_conditional': True,
                    'condition': m.group(1),
                    'true_label': m.group(2),
                    'false_label': m.group(3),
                    }
        m = re.match(r'br\s+label\s+%(\S+)', line)
        if m:
            return {**base,
                    'category': 'br',
                    'is_conditional': False,
                    'target': m.group(1),
                    }

        # ---- getelementptr ----
        m = re.match(r'(%\S+)\s*=\s*getelementptr\s+(?:inbounds\s+)?(?:nuw\s+)?(.+)', line)
        if m:
            return {**base,
                    'category': 'gep',
                    'result': m.group(1),
                    'detail': m.group(2).strip(),
                    }

        # ---- ret ----
        if line.startswith('ret '):
            return {**base, 'category': 'ret'}

        # ---- icmp / trunc / zext / sext / or / and / add / sub / mul ----
        m = re.match(r'(%\S+)\s*=\s*(\w+)\s+(.*)', line)
        if m:
            return {**base,
                    'category': 'arith',
                    'result': m.group(1),
                    'op': m.group(2),
                    'operands_raw': m.group(3).strip(),
                    }

        return None

    def _is_peripheral_ptr(self, dest):
        if dest.startswith('@'):
            name = dest.lstrip('@').split(',')[0].strip()
            return name in MSP430_PERIPHERALS or self.globals.get(name, {}).get('is_peripheral', False)
        return False


# ======================================================================
# CLI
# ======================================================================
def main():
    ap = argparse.ArgumentParser(description='LLVM IR 解析器')
    ap.add_argument('ll_file', help='.ll 文件路径')
    ap.add_argument('--output', '-o', default=None, help='输出JSON路径')
    ap.add_argument('--summary', action='store_true', help='仅打印摘要')
    args = ap.parse_args()

    parser = LLVMIRParser(args.ll_file)
    data = parser.parse()

    if args.summary or not args.output:
        print(f"解析完成: {args.ll_file}")
        print(f"  全局变量: {len(data['globals'])}")
        print(f"  结构体:   {len(data['struct_types'])}")
        print(f"  函数:     {len(data['functions'])}")
        for fname, finfo in data['functions'].items():
            tag = ''
            if finfo['is_isr']:
                tag = ' [ISR]'
            elif finfo['is_init']:
                tag = ' [INIT]'
            print(f"    {fname}{tag}: {len(finfo['stores'])} stores, "
                  f"{len(finfo['loads'])} loads, {len(finfo['calls'])} calls")

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        print(f"  输出: {args.output}")


if __name__ == '__main__':
    main()
