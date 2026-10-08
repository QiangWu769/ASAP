#!/usr/bin/env python3
"""
Stage 1c: Inject function entry checkpoints

Detects functions where a CALL to an uninstrumented library function happens
before the first data write (stack or memory). Inserts a dummy stack write
after the function prologue to ensure ASAP creates a WID checkpoint, preventing
"blind spots" during library function calls like memcpy.

Usage:
    python3 stage1c_inject_entry_checkpoint.py A_idempotent.s \
        --functions function_info.json \
        --output A_patched.s
"""
import argparse
import json
import re
import sys


EXCLUDED_FUNCTIONS = {
    'main', 'init', '__msp430_init', '__crt0_start',
    'Timer_B1_ISR', '__isr_', '_isr_',
}

EXCLUDED_CALL_TARGETS = {
    'main', 'init', '__msp430_init',
}

WRITE_PATTERNS = [
    re.compile(r'^\s*MOV\.[BW]\s+.+,\s+\d+\(R1\)', re.I),
    re.compile(r'^\s*MOV\.[BW]\s+.+,\s+@R1', re.I),
    re.compile(r'^\s*MOV\.[BW]\s+.+,\s+&\w+', re.I),
]

CALL_PATTERN = re.compile(r'^\s*CALL\s+#(\w+)', re.I)


def is_data_write(line):
    stripped = line.strip()
    if not stripped or stripped.startswith(';') or stripped.startswith('.'):
        return False
    for pat in WRITE_PATTERNS:
        if pat.match(stripped):
            return True
    return False


def is_call_instruction(line):
    stripped = line.strip()
    m = CALL_PATTERN.match(stripped)
    if m:
        return m.group(1)
    return None


def should_exclude_function(name):
    if name in EXCLUDED_FUNCTIONS:
        return True
    for excl in ('__isr_', '_isr_'):
        if excl in name:
            return True
    return False


def find_functions_needing_checkpoint(lines, function_info):
    results = []

    for func_name, info in function_info.items():
        if should_exclude_function(func_name):
            continue

        stack_size = info.get('stack_size', 0)
        if stack_size < 2:
            continue

        start_line = info.get('start_line', 0)
        end_line = info.get('end_line', len(lines))

        prologue_end = None
        for i in range(start_line, min(end_line, len(lines))):
            if '; end of prologue' in lines[i]:
                prologue_end = i
                break

        if prologue_end is None:
            continue

        found_call = None
        found_write = False
        insert_point = prologue_end + 1

        for i in range(prologue_end + 1, min(end_line, len(lines))):
            stripped = lines[i].strip()

            if not stripped or stripped.startswith(';') or stripped.startswith('.'):
                continue
            if stripped.startswith('.L') and stripped.endswith(':'):
                continue

            if is_data_write(lines[i]):
                found_write = True
                break

            call_target = is_call_instruction(lines[i])
            if call_target and call_target not in EXCLUDED_CALL_TARGETS:
                found_call = call_target
                break

        if found_call and not found_write:
            results.append({
                'function': func_name,
                'insert_line': insert_point,
                'call_target': found_call,
                'stack_size': stack_size,
            })

    return results


def inject_checkpoints(lines, checkpoints):
    checkpoints_sorted = sorted(checkpoints, key=lambda c: c['insert_line'], reverse=True)

    for cp in checkpoints_sorted:
        insert_idx = cp['insert_line']
        func_name = cp['function']
        call_target = cp['call_target']

        inject_lines = [
            f'\t; === ASAP entry checkpoint (before {call_target}) ===\n',
            f'\tMOV.W\t#0, 0(R1)\n',
        ]

        for j, line in enumerate(inject_lines):
            lines.insert(insert_idx + j, line)

    return lines


def main():
    parser = argparse.ArgumentParser(description='Stage 1c: Inject function entry checkpoints')
    parser.add_argument('input', help='Input assembly file')
    parser.add_argument('--functions', required=True, help='function_info.json')
    parser.add_argument('--output', required=True, help='Output assembly file')
    args = parser.parse_args()

    with open(args.input) as f:
        lines = f.readlines()

    with open(args.functions) as f:
        function_info = json.load(f)

    checkpoints = find_functions_needing_checkpoint(lines, function_info)

    if checkpoints:
        print(f'  Found {len(checkpoints)} function(s) needing entry checkpoint:')
        for cp in checkpoints:
            print(f'    {cp["function"]}: CALL #{cp["call_target"]} before first write '
                  f'(insert at line {cp["insert_line"]})')
        lines = inject_checkpoints(lines, checkpoints)
    else:
        print('  No functions need entry checkpoints')

    with open(args.output, 'w') as f:
        f.writelines(lines)

    print(f'  ✓ Output: {args.output}')


if __name__ == '__main__':
    main()
