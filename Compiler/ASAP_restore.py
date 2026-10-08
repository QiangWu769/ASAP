#!/usr/bin/env python3
"""
ASAP运行时恢复逻辑

实现断电后的状态恢复算法：
1. 选择最大安全继续点W*
2. 按需恢复U(W*)
3. FRAM恢复逻辑：从S0/S1槽位恢复数据
"""

import json
import argparse
from typing import Dict, List, Set, Tuple, Optional
from pathlib import Path

class ASAPRestore:
    """ASAP运行时恢复类"""
    
    def __init__(self, metadata_path: str):
        """初始化恢复器，加载元数据"""
        with open(metadata_path, 'r') as f:
            self.metadata = json.load(f)
        
        # 提取关键数据
        self.nextpc_table = self.metadata.get("nextpc_table", {})
        self.lifetime_data = self.metadata.get("lifetime_data", {})
        self.wid_mapping = self.metadata.get("wid_mapping", {})
        self.fram_layout = self.metadata.get("fram_layout", {})
        self.writewids = self.metadata.get("writewids", {})
        self.address_metadata = self.metadata.get("address_metadata", {})
        
        # 提取子组件
        self.pc_ranges = self.lifetime_data.get("pc_ranges", {})
        self.lifetimes_by_addr = self.lifetime_data.get("lifetimes_by_addr", {})
        self.wid_to_info = self.wid_mapping.get("wid_to_info", {})
        self.pc_to_wid = self.wid_mapping.get("pc_to_wid", {})
        self.slot_mapping = self.fram_layout.get("slot_mapping", {})
        self.slot_addresses = self.fram_layout.get("slot_addresses", {})
        self.commit_addresses = self.fram_layout.get("commit_addresses", {})
        
        print(f"[ASAP恢复] 加载元数据完成")
        print(f"  - WID总数: {len(self.wid_to_info)}")
        print(f"  - PC范围: {len(self.pc_ranges)}")
        print(f"  - 地址数: {len(self.writewids)}")
        print(f"  - 槽位映射: {len(self.slot_mapping)}")
    
    def get_lifetime_at_wid(self, wid: str) -> Set[str]:
        """获取WID对应的生命周期地址集合"""
        # 从lifetimes_by_addr中查找包含该WID的地址
        alive_addresses = set()
        
        for addr, lifetime_ranges in self.lifetimes_by_addr.items():
            # lifetime_ranges是一个列表，包含该地址的所有生命周期信息
            for range_info in lifetime_ranges:
                range_wid = range_info.get("wid", "")
                
                # 检查WID是否匹配
                if range_wid == wid:
                    alive_addresses.add(addr)
                    break
        
        return alive_addresses
    
    def _wid_in_range(self, wid: str, start_wid: str, end_wid: str) -> bool:
        """检查WID是否在指定范围内"""
        wid_num = int(wid.replace("W", ""))
        start_num = int(start_wid.replace("W", "")) if start_wid else 0
        end_num = int(end_wid.replace("W", "")) if end_wid else float('inf')
        
        return start_num <= wid_num <= end_num
    
    def is_committed(self, wid: str) -> bool:
        """检查WID是否已提交"""
        commit_addr = self.commit_addresses.get(wid, "")
        if not commit_addr:
            return False
        
        # 模拟读取提交位（实际实现中需要从硬件读取）
        # 这里返回True表示已提交，实际应该读取commit_addr的值
        return True
    
    def get_last_write_of(self, addr: str, max_wid: str) -> Optional[str]:
        """获取地址addr在max_wid之前的最近一次写WID"""
        if addr not in self.writewids:
            return None
        
        addr_wids = self.writewids[addr]
        max_wid_num = int(max_wid.replace("W", ""))
        
        # 找到小于等于max_wid的最大WID
        last_wid = None
        for wid in addr_wids:
            wid_num = int(wid.replace("W", ""))
            if wid_num <= max_wid_num:
                last_wid = wid
            else:
                break
        
        return last_wid
    
    def find_max_safe_continuation_point(self) -> Optional[str]:
        """选择最大安全继续点W*"""
        print(f"[ASAP恢复] 开始寻找最大安全继续点...")
        
        # 获取所有WID，按降序排列
        all_wids = list(self.wid_to_info.keys())
        all_wids.sort(key=lambda x: int(x.replace("W", "")), reverse=True)
        
        for wid in all_wids:
            print(f"[ASAP恢复] 检查WID {wid}...")
            
            # 获取该WID的生命周期地址集合
            alive_addresses = self.get_lifetime_at_wid(wid)
            print(f"  - 生命周期地址: {len(alive_addresses)}个")
            
            if not alive_addresses:
                print(f"  - 无生命周期地址，跳过")
                continue
            
            # 检查所有生命周期地址是否都已提交
            all_committed = True
            for addr in alive_addresses:
                last_write_wid = self.get_last_write_of(addr, wid)
                if last_write_wid and not self.is_committed(last_write_wid):
                    print(f"  - 地址 {addr} 的最后写 {last_write_wid} 未提交")
                    all_committed = False
                    break
            
            if all_committed:
                print(f"[ASAP恢复] 找到安全继续点: {wid}")
                return wid
        
        print(f"[ASAP恢复] 未找到安全继续点")
        return None
    
    def restore_address(self, addr: str, wid: str) -> bool:
        """恢复单个地址的数据"""
        print(f"[ASAP恢复] 恢复地址 {addr} 到WID {wid}...")
        
        # 获取该地址的最后写WID
        last_write_wid = self.get_last_write_of(addr, wid)
        if not last_write_wid:
            print(f"  - 未找到最后写WID")
            return False
        
        # 获取槽位映射
        slot_key = f"{addr}_{last_write_wid}"
        slot_choice = self.slot_mapping.get(slot_key, 0)
        
        # 获取槽位地址
        slot_info = self.slot_addresses.get(addr, {})
        if slot_choice == 0:
            slot_addr = slot_info.get("s0", "")
            slot_name = f"__RS_S0_{addr.replace('0x', '')}"
        else:
            slot_addr = slot_info.get("s1", "")
            slot_name = f"__RS_S1_{addr.replace('0x', '')}"
        
        if not slot_addr:
            print(f"  - 未找到槽位地址")
            return False
        
        # 模拟从槽位恢复数据（实际实现中需要从硬件读取）
        print(f"  - 从槽位 {slot_name} (地址: {slot_addr}) 恢复数据")
        print(f"  - 恢复到地址 {addr}")
        
        return True
    
    def restore_state(self) -> bool:
        """执行完整的状态恢复"""
        print(f"[ASAP恢复] 开始状态恢复...")
        
        # 1. 寻找最大安全继续点
        safe_wid = self.find_max_safe_continuation_point()
        if not safe_wid:
            print(f"[ASAP恢复] 无法找到安全继续点，恢复失败")
            return False
        
        # 2. 获取需要恢复的地址集合
        alive_addresses = self.get_lifetime_at_wid(safe_wid)
        print(f"[ASAP恢复] 需要恢复 {len(alive_addresses)} 个地址")
        
        # 3. 按需恢复每个地址
        restored_count = 0
        for addr in alive_addresses:
            if self.restore_address(addr, safe_wid):
                restored_count += 1
        
        # 4. 获取继续执行的PC
        next_pc = self.nextpc_table.get(safe_wid, "")
        if not next_pc:
            print(f"[ASAP恢复] 未找到WID {safe_wid} 的NextPC")
            return False
        
        print(f"[ASAP恢复] 恢复完成!")
        print(f"  - 安全继续点: {safe_wid}")
        print(f"  - 恢复地址数: {restored_count}/{len(alive_addresses)}")
        print(f"  - 继续执行PC: {next_pc}")
        
        return True

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="ASAP运行时恢复逻辑")
    parser.add_argument("--metadata", default="build/asap_metadata.json", 
                       help="元数据文件路径")
    parser.add_argument("--simulate", action="store_true", 
                       help="模拟恢复过程（不实际执行硬件操作）")
    
    args = parser.parse_args()
    
    # 创建恢复器
    restore = ASAPRestore(args.metadata)
    
    # 执行恢复
    success = restore.restore_state()
    
    if success:
        print(f"[ASAP恢复] 恢复成功!")
        return 0
    else:
        print(f"[ASAP恢复] 恢复失败!")
        return 1

if __name__ == "__main__":
    exit(main())
