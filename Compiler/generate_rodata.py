#!/usr/bin/env python3
"""
生成完整的元数据JSON文件

整合所有数据：NextPC、L翻转点、WriteWIDs、slot_of、地址元数据
生成JSON格式的元数据文件，用于运行时恢复。
"""

import json
import argparse
from typing import Dict, List, Set, Tuple

def load_json_file(file_path: str) -> Dict:
    """加载JSON文件"""
    with open(file_path, 'r') as f:
        return json.load(f)

def generate_metadata_json(nextpc_data: Dict, lifetime_data: Dict, wid_map: Dict, fram_layout: Dict) -> Dict:
    """生成完整的元数据JSON"""
    
    # 1. NextPC表
    nextpc_table = nextpc_data.get("nextpc_table", {})
    
    # 2. 生命周期数据
    pc_ranges = lifetime_data.get("pc_ranges", {})
    lifetimes_by_addr = lifetime_data.get("lifetimes_by_addr", {})
    
    # 3. WID映射
    wid_to_info = wid_map.get("wid_to_info", {})
    pc_to_wid = wid_map.get("pc_to_wid", {})
    
    # 4. FRAM布局
    slot_mapping = fram_layout.get("slot_mapping", {})
    s0_slots = fram_layout.get("s0_slots", {})
    s1_slots = fram_layout.get("s1_slots", {})
    commit_bits = fram_layout.get("commit_bits", {})
    
    # 合并S0和S1槽位地址
    slot_addresses = {}
    for addr, s0_addr in s0_slots.items():
        slot_addresses[addr] = {
            "s0": s0_addr,
            "s1": s1_slots.get(addr, "")
        }
    
    # 5. 生成WriteWIDs[A]：每个地址的WID升序列表
    writewids = {}
    for wid, info in wid_to_info.items():
        target_addr = info.get("target_addr", "")
        if target_addr:
            if target_addr not in writewids:
                writewids[target_addr] = []
            writewids[target_addr].append(wid)
    
    # 对每个地址的WID列表进行排序
    for addr in writewids:
        writewids[addr].sort(key=lambda x: int(x.replace("W", "")))
    
    # 6. 地址元数据
    address_metadata = {}
    for addr, info in slot_addresses.items():
        if addr not in address_metadata:
            address_metadata[addr] = {
                "width": 2,  # 默认2字节
                "type": "MMIO" if addr.startswith("0x0") else "RAM",
                "s0_address": info.get("s0", ""),
                "s1_address": info.get("s1", "")
            }
    
    # 组合所有元数据
    metadata = {
        "asap_metadata": {
            "version": "1.0",
            "description": "ASAP (Atomic State Preservation) Runtime Metadata",
            "generated_at": "2024-01-01T00:00:00Z"
        },
        "nextpc_table": nextpc_table,
        "lifetime_data": {
            "pc_ranges": pc_ranges,
            "lifetimes_by_addr": lifetimes_by_addr
        },
        "wid_mapping": {
            "wid_to_info": wid_to_info,
            "pc_to_wid": pc_to_wid
        },
        "fram_layout": {
            "slot_mapping": slot_mapping,
            "slot_addresses": slot_addresses,
            "commit_addresses": commit_bits
        },
        "writewids": writewids,
        "address_metadata": address_metadata,
        "statistics": {
            "total_wids": len(wid_to_info),
            "total_pc_ranges": len(pc_ranges),
            "total_addresses": len(address_metadata),
            "total_slots": len(slot_addresses)
        }
    }
    
    return metadata

def main():
    parser = argparse.ArgumentParser(description="生成ASAP元数据JSON文件")
    parser.add_argument("--nextpc", required=True, help="NextPC表JSON文件")
    parser.add_argument("--lifetime", required=True, help="生命周期数据JSON文件")
    parser.add_argument("--wid-map", required=True, help="WID映射JSON文件")
    parser.add_argument("--fram-layout", required=True, help="FRAM布局JSON文件")
    parser.add_argument("--out", required=True, help="输出JSON文件")
    
    args = parser.parse_args()
    
    print("[RODATA生成] 加载数据文件...")
    
    # 加载所有数据文件
    nextpc_data = load_json_file(args.nextpc)
    lifetime_data = load_json_file(args.lifetime)
    wid_map = load_json_file(args.wid_map)
    fram_layout = load_json_file(args.fram_layout)
    
    print("[RODATA生成] 生成元数据JSON...")
    
    # 生成元数据
    metadata = generate_metadata_json(nextpc_data, lifetime_data, wid_map, fram_layout)
    
    print("[RODATA生成] 保存元数据文件...")
    
    # 保存到文件
    with open(args.out, 'w') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    print(f"[RODATA生成] 元数据JSON生成完成")
    print(f"[RODATA生成] 结果保存到: {args.out}")
    
    # 打印统计信息
    stats = metadata["statistics"]
    print(f"[RODATA生成] 统计信息:")
    print(f"  - WID总数: {stats['total_wids']}")
    print(f"  - PC范围总数: {stats['total_pc_ranges']}")
    print(f"  - 地址总数: {stats['total_addresses']}")
    print(f"  - 槽位总数: {stats['total_slots']}")

if __name__ == "__main__":
    main()