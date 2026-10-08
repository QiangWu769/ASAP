#!/usr/bin/env python3
"""
Stage 3b: 检测循环数组写入模式

识别以下模式的数组写入：
1. 在循环中通过动态索引写入数组
2. 数组通过指针参数传递（如 filter 传给 insert 函数）

输出：标记哪些写入是"循环数组写入"，需要多槽位保护

输入: build/A_sym.s, build/candidates.json
输出: build/loop_arrays.json
"""

import argparse
import json
import re
from pathlib import Path

def analyze_loop_array_writes(asm_file, candidates_file):
    """分析汇编代码，检测循环数组写入"""
    
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    with open(candidates_file, 'r') as f:
        candidates = json.load(f)
    
    loop_arrays = {
        'arrays': {},  # 数组名 -> {base_func, size, element_size, base_offset}
        'writes': {}   # WID -> {array_name, is_loop_write}
    }
    
    # 已知的循环数组配置（基于benchmark分析）
    known_arrays = {
        # CF benchmark - filter改为全局数组（和CRC的crcTable类似）
        'cf': {
            'filter': {
                'passed_as_param': False,
                'is_global': True,        # 全局数组，地址固定
                'size': 128,              # NUM_BUCKETS = 128
                'element_size': 2,
                'callee_funcs': ['insert']  # insert函数中写入filter
            }
        },
        # AR benchmark - model改为全局数组（和CRC的crcTable类似）
        'ar': {
            'model': {
                'passed_as_param': False,
                'is_global': True,        # 全局数组，地址固定
                'size': 32,               # MODEL_SIZE * 2 (stationary + moving)
                'element_size': 4,        # sizeof(features_t) = 4字节
                'callee_funcs': ['train'] # train函数中写入model
            }
        },
        # CRC benchmark (原版，crcTable在BSS)
        # 注意：element_size会从汇编的.size指令自动检测
        'crc': {
            'crcTable': {
                'passed_as_param': False,
                'is_global': True,
                'size': 256,
                'element_size': 'auto',  # 自动检测：CRC16=2字节, CRC32=4字节
                'callee_funcs': ['crcInit']
            }
        },
        # CONV benchmark - 直接栈访问数组
        # vec[200] 在栈偏移362处（高地址），out[181]在栈偏移0处（低地址）
        'conv': {
            'out_sp362': {
                'passed_as_param': False,
                'is_stack_direct': True,  # 直接栈访问
                'stack_offset': 362,       # vec数组在栈上的偏移
                'size': 200,               # N = 200 (vec数组大小)
                'element_size': 2,         # unsigned
                'index_var_offset': 770,   # 循环变量i在栈上的位置
                'callee_funcs': ['main']   # 在main中直接访问
            },
            'out_sp0': {
                'passed_as_param': False,
                'is_stack_direct': True,
                'stack_offset': 0,         # out数组在栈底
                'size': 181,               # N-K+1 = 200-20+1 = 181 (out数组大小)
                'element_size': 2,
                'index_var_offset': 768,
                'callee_funcs': ['main']
            }
        }
    }
    
    # 检测当前编译的是哪个benchmark
    current_benchmark = detect_benchmark(lines)
    print(f"  检测到 benchmark: {current_benchmark}")
    
    # 首先从candidates中自动检测INDIRECT_STACK写入
    indirect_stack_writes = {}
    for wid, candidate in candidates.items():
        if candidate.get('addr_mode') == 'INDIRECT_STACK':
            logical_addr = candidate.get('logical_addr', '')
            func = candidate.get('function', '')
            base_reg = candidate.get('base_reg', 'R12')
            
            # 解析 main::SP+0 或 main::SP+0+2 格式
            if '::SP+' in logical_addr:
                parts = logical_addr.split('::SP+')
                caller_func = parts[0]
                
                # 处理 "0+2" 这种带额外偏移的格式
                offset_str = parts[1] if len(parts) > 1 else '0'
                if '+' in offset_str:
                    # 解析 "0+2" -> 取基础偏移0
                    base_offset = int(offset_str.split('+')[0])
                else:
                    base_offset = int(offset_str)
                
                # 创建唯一的数组标识（使用基础偏移）
                array_key = f"{caller_func}_SP{base_offset}"
                
                if array_key not in indirect_stack_writes:
                    indirect_stack_writes[array_key] = {
                        'caller_func': caller_func,
                        'caller_offset': base_offset,
                        'callee_funcs': set(),
                        'wids': [],
                        'base_reg': base_reg
                    }
                
                indirect_stack_writes[array_key]['callee_funcs'].add(func)
                indirect_stack_writes[array_key]['wids'].append(wid)
    
    # 打印自动检测结果
    if indirect_stack_writes:
        print(f"  自动检测到 {len(indirect_stack_writes)} 个间接栈写入组:")
        for key, info in indirect_stack_writes.items():
            print(f"    {key}: {len(info['wids'])} 个写入, 函数: {info['callee_funcs']}")
    
    # 从汇编中提取全局数组的实际大小（通过.size指令）
    global_array_sizes = {}
    for i, line in enumerate(lines):
        # 匹配 .size array_name, bytes
        m = re.match(r'\s*\.size\s+(\w+),\s*(\d+)', line)
        if m:
            arr_name = m.group(1)
            total_bytes = int(m.group(2))
            global_array_sizes[arr_name] = total_bytes
    
    # 使用已知配置或自动检测结果
    if current_benchmark in known_arrays:
        arrays_config = known_arrays[current_benchmark]
        
        for array_name, config in arrays_config.items():
            print(f"  发现已知循环数组: {array_name}")
            
            # 获取元素大小（支持自动检测）
            element_size = config['element_size']
            array_size = config['size']
            
            if element_size == 'auto':
                # 从汇编的.size指令自动检测
                if array_name in global_array_sizes:
                    total_bytes = global_array_sizes[array_name]
                    element_size = total_bytes // array_size
                    print(f"    自动检测: .size {array_name}, {total_bytes} → 元素大小={element_size}字节")
                else:
                    # 默认使用2字节
                    element_size = 2
                    print(f"    警告: 无法自动检测元素大小，使用默认值 {element_size} 字节")
            
            total_bytes = array_size * element_size
            
            print(f"    大小: {array_size} 元素")
            print(f"    元素大小: {element_size} 字节")
            print(f"    总大小: {total_bytes} 字节")
            
            loop_arrays['arrays'][array_name] = {
                'size': array_size,
                'element_size': element_size,
                'total_bytes': total_bytes,
                'passed_as_param': config.get('passed_as_param', False),
                'param_reg': config.get('param_reg'),
                'caller_func': config.get('caller_func'),
                'caller_offset': config.get('caller_offset'),
                'callee_funcs': config.get('callee_funcs', []),
                'is_global': config.get('is_global', False),
                'is_stack_direct': config.get('is_stack_direct', False),
                'stack_offset': config.get('stack_offset'),
                'index_var_offset': config.get('index_var_offset')
            }
            
            # 标记相关的写入候选
            for wid, candidate in candidates.items():
                # 跳过已标记的
                if wid in loop_arrays['writes']:
                    continue
                
                # 方法1: 检查是否是间接栈写入且在相关函数中 (INDIRECT_STACK - 通过参数传递)
                if candidate.get('addr_mode') == 'INDIRECT_STACK':
                    func = candidate.get('function', '')
                    if func in config.get('callee_funcs', []):
                        loop_arrays['writes'][wid] = {
                            'array_name': array_name,
                            'is_loop_write': True,
                            'function': func,
                            'logical_addr': candidate.get('logical_addr')
                        }
                        print(f"    标记 {wid} 为循环数组写入 (函数: {func})")
                        continue
                
                # 方法2: 检查logical_addr是否匹配caller的栈地址 (INDIRECT, 通过参数传递)
                if candidate.get('addr_mode') == 'INDIRECT':
                    logical_addr = candidate.get('logical_addr', '')
                    caller_func = config.get('caller_func')
                    caller_offset = config.get('caller_offset', 0)
                    
                    if caller_func and f"{caller_func}::SP+{caller_offset}" == logical_addr:
                        func = candidate.get('function', '')
                        if func in config.get('callee_funcs', []):
                            loop_arrays['writes'][wid] = {
                                'array_name': array_name,
                                'is_loop_write': True,
                                'function': func,
                                'logical_addr': logical_addr
                            }
                            print(f"    标记 {wid} 为循环数组写入 (通过 {logical_addr})")
                            continue
                
                # 方法3: 检查是否是直接栈访问数组 (type=array, is_stack_direct)
                if candidate.get('type') == 'array' and config.get('is_stack_direct'):
                    array_info = candidate.get('array_info', {})
                    candidate_array_base = array_info.get('array_base', '')
                    
                    # 检查array_base是否匹配
                    if candidate_array_base == array_name:
                        func = candidate.get('function', '')
                        loop_arrays['writes'][wid] = {
                            'array_name': array_name,
                            'is_loop_write': True,
                            'function': func,
                            'logical_addr': candidate.get('logical_addr'),
                            'stack_offset': array_info.get('stack_offset'),
                            'index_location': array_info.get('index_location')
                        }
                        print(f"    标记 {wid} 为循环数组写入 (直接栈访问: {array_name})")
                
                # 方法4: 检查是否是全局数组写入 (is_global=True)
                # 全局数组通过INDIRECT或INDEXED模式访问，base_reg通常是R12
                if config.get('is_global', False):
                    func = candidate.get('function', '')
                    if func in config.get('callee_funcs', []):
                        # 检查1: type='array'且array_base匹配
                        if candidate.get('type') == 'array':
                            array_info = candidate.get('array_info', {})
                            if array_info and array_info.get('array_base') == array_name:
                                loop_arrays['writes'][wid] = {
                                    'array_name': array_name,
                                    'is_loop_write': True,
                                    'function': func,
                                    'logical_addr': candidate.get('logical_addr')
                                }
                                print(f"    标记 {wid} 为循环数组写入 (全局数组: {array_name})")
                                continue
                        # 检查2: INDIRECT或INDEXED模式且base_reg是R12（通过R12访问全局数组）
                        addr_mode = candidate.get('addr_mode', '')
                        if addr_mode in ('INDIRECT', 'INDEXED'):
                            base_reg = candidate.get('base_reg', '')
                            # 检查logical_addr是否是func::R12+N格式
                            logical_addr = candidate.get('logical_addr', '')
                            if base_reg == 'R12' and f"{func}::R12+" in logical_addr:
                                loop_arrays['writes'][wid] = {
                                    'array_name': array_name,
                                    'is_loop_write': True,
                                    'function': func,
                                    'logical_addr': logical_addr
                                }
                                print(f"    标记 {wid} 为循环数组写入 (全局数组R12: {array_name}, mode={addr_mode})")
    else:
        # 对于未知benchmark，尝试使用自动检测的结果
        # 但需要估计数组大小（默认使用保守值）
        print(f"  未知benchmark，尝试自动推断数组配置...")
        
        for array_key, info in indirect_stack_writes.items():
            array_name = f"array_{array_key}"
            
            # 尝试从栈帧信息推断大小（保守估计）
            # 默认: 64元素 × 2字节 = 128字节
            estimated_size = 64
            element_size = 2
            
            print(f"  自动创建数组配置: {array_name}")
            print(f"    估计大小: {estimated_size} 元素 × {element_size} 字节")
            
            loop_arrays['arrays'][array_name] = {
                'size': estimated_size,
                'element_size': element_size,
                'total_bytes': estimated_size * element_size,
                'passed_as_param': True,
                'param_reg': info['base_reg'],
                'caller_func': info['caller_func'],
                'caller_offset': info['caller_offset'],
                'callee_funcs': list(info['callee_funcs']),
                'is_global': False,
                'auto_detected': True
            }
            
            # 标记相关写入
            for wid in info['wids']:
                candidate = candidates.get(wid, {})
                loop_arrays['writes'][wid] = {
                    'array_name': array_name,
                    'is_loop_write': True,
                    'function': candidate.get('function', ''),
                    'logical_addr': candidate.get('logical_addr')
                }
                print(f"    标记 {wid} 为循环数组写入")
    
    return loop_arrays


def detect_benchmark(lines):
    """从汇编代码检测当前编译的benchmark"""
    asm_text = ''.join(lines)
    
    # 检测特征函数名
    if 'insert:' in asm_text and 'lookup:' in asm_text and 'hash_fp_to_index' in asm_text:
        return 'cf'
    elif 'train:' in asm_text and 'recognize:' in asm_text and 'featurize:' in asm_text:
        return 'ar'
    elif 'crcInit:' in asm_text and 'crcSlow:' in asm_text and 'crcFast:' in asm_text:
        return 'crc'
    elif 'bitcount:' in asm_text:
        return 'bc'
    elif 'convolve:' in asm_text or 'vec' in asm_text:
        return 'conv'
    
    return 'unknown'


def main():
    parser = argparse.ArgumentParser(description='Stage 3b: 检测循环数组写入')
    parser.add_argument('--asm', default='build/A_sym.s', help='汇编文件')
    parser.add_argument('--candidates', default='build/candidates.json', help='候选写入')
    parser.add_argument('--output', default='build/loop_arrays.json', help='输出文件')
    
    args = parser.parse_args()
    
    print("Stage 3b: 检测循环数组写入...")
    
    loop_arrays = analyze_loop_array_writes(args.asm, args.candidates)
    
    with open(args.output, 'w') as f:
        json.dump(loop_arrays, f, indent=2)
    
    print(f"  ✓ 检测到 {len(loop_arrays['arrays'])} 个循环数组")
    print(f"  ✓ 标记 {len(loop_arrays['writes'])} 个循环数组写入")
    print(f"  ✓ 输出: {args.output}")


if __name__ == '__main__':
    main()

