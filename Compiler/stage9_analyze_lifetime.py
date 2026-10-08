#!/usr/bin/env python3
"""
Stage 9: 生命周期分析（基于地址）
分析每个逻辑地址的生命周期
输入: build/reads_writes.json, build/wid_pc_map.json, build/candidates.json
输出: build/lifetime_data.json
"""
import argparse
import json

def analyze_lifetime(reads_writes, wid_pc_map, candidates):
    """分析变量生命周期"""
    
    # 1. 为每个写操作关联WID和PC
    writes_with_wid = []
    for wid, pc in wid_pc_map.items():
        if wid in candidates:
            info = candidates[wid]
            writes_with_wid.append({
                'wid': wid,
                'write_pc': pc,
                'logical_addr': info['logical_addr'],
                'function': info['function']
            })
    
    # 2. 按地址分组
    addr_groups = {}
    for w in writes_with_wid:
        addr = w['logical_addr']
        if addr not in addr_groups:
            addr_groups[addr] = []
        addr_groups[addr].append(w)
    
    # 3. 对每个地址，分析生命周期
    lifetime_data = {'addresses': {}}
    
    for logical_addr, addr_writes in addr_groups.items():
        # 按PC排序
        addr_writes.sort(key=lambda x: int(x['write_pc'], 16))
        
        lifetimes = []
        
        for i, write in enumerate(addr_writes):
            wid = write['wid']
            write_pc = write['write_pc']
            func = write['function']
            
            # 找下一次写入该地址的PC
            if i + 1 < len(addr_writes):
                next_write_pc = addr_writes[i + 1]['write_pc']
            else:
                next_write_pc = None
            
            # 找该地址在范围内的所有读
            reads_in_range = []
            for r in reads_writes['reads']:
                if r['logical_addr'] != logical_addr:
                    continue
                
                # 读必须在写之后
                if 'pc' in r:
                    read_pc = r['pc']
                else:
                    # 如果没有PC，跳过（后续会从反汇编中获取）
                    continue
                
                if int(read_pc, 16) <= int(write_pc, 16):
                    continue
                
                # 如果有下次写，读必须在下次写之前
                if next_write_pc and int(read_pc, 16) >= int(next_write_pc, 16):
                    continue
                
                reads_in_range.append(read_pc)
            
            # 确定生命周期结束PC
            if reads_in_range:
                # 有读：到最后一次读
                end_pc = max(reads_in_range, key=lambda x: int(x, 16))
            elif next_write_pc:
                # 无读但有下次写：到下次写之前
                end_pc = hex(int(next_write_pc, 16) - 2)
            else:
                # 无读无下次写：到函数结束（估算为写PC+0x100）
                end_pc = hex(int(write_pc, 16) + 0x100)
            
            lifetimes.append({
                'wid': wid,
                'write_pc': write_pc,
                'reads': reads_in_range,
                'end_pc': end_pc,
                'lifetime_range': [write_pc, end_pc]
            })
        
        lifetime_data['addresses'][logical_addr] = lifetimes
    
    return lifetime_data

def main():
    parser = argparse.ArgumentParser(description='Stage 9: 生命周期分析')
    parser.add_argument('--reads-writes', required=True, help='读写操作JSON')
    parser.add_argument('--wid-pc-map', required=True, help='WID→PC映射JSON')
    parser.add_argument('--candidates', required=True, help='候选写操作JSON')
    parser.add_argument('--output', default='build/lifetime_data.json', help='输出JSON')
    
    args = parser.parse_args()
    
    # 加载数据
    with open(args.reads_writes, 'r') as f:
        reads_writes = json.load(f)
    
    with open(args.wid_pc_map, 'r') as f:
        wid_pc_map = json.load(f)
    
    with open(args.candidates, 'r') as f:
        candidates = json.load(f)
    
    # 分析生命周期
    lifetime_data = analyze_lifetime(reads_writes, wid_pc_map, candidates)
    
    # 输出JSON
    with open(args.output, 'w') as f:
        json.dump(lifetime_data, f, indent=2)
    
    print(f"  ✓ 生命周期分析完成:")
    print(f"    - 分析了 {len(lifetime_data['addresses'])} 个唯一地址")
    
    total_lifetimes = sum(len(lts) for lts in lifetime_data['addresses'].values())
    print(f"    - 总生命周期数: {total_lifetimes}")
    
    # 显示前5个地址
    for addr, lifetimes in list(lifetime_data['addresses'].items())[:5]:
        print(f"    {addr}: {len(lifetimes)} 个生命周期")
    
    print(f"  ✓ 输出: {args.output}")

if __name__ == '__main__':
    main()




































