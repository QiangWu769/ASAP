#!/usr/bin/env python3
"""
内存映射表管理器
维护MSP430FR系列的内存区间分类

用途：
1. 判断地址属于SRAM/FRAM/MMIO
2. 识别易失/非易失存储区域
3. 用于指令重写决策
"""


class MemoryMapper:
    """内存映射表"""
    
    # MSP430FR5969内存映射
    MSP430FR5969_MAP = {
        # SRAM区域 (易失)
        'SRAM': [
            (0x1C00, 0x23FF, 'volatile', 'RAM'),  # 2KB SRAM
        ],
        
        # FRAM区域 (非易失，但RMW非幂等)
        'FRAM': [
            (0x4400, 0x13FFF, 'persistent', 'FRAM'),  # 64KB FRAM
            # .text通常在0x4400开始
            # .data/.bss可能在FRAM高地址
        ],
        
        # 外设寄存器 (MMIO)
        'MMIO': [
            (0x0100, 0x01FF, 'io', 'Peripheral 8-bit'),
            (0x0200, 0x02FF, 'io', 'Peripheral 16-bit'),
            (0x0300, 0x09FF, 'io', 'Extended Peripherals'),
        ],
        
        # 特殊功能寄存器
        'SFR': [
            (0x0000, 0x000F, 'io', 'Special Function Registers'),
        ],
        
        # 信息存储区
        'INFO': [
            (0x1800, 0x19FF, 'persistent', 'Information Memory'),
        ],
    }
    
    def __init__(self, chip='MSP430FR5969'):
        """
        初始化内存映射
        
        Args:
            chip: 芯片型号
        """
        self.chip = chip
        self.regions = []
        
        # 加载内存映射
        if chip == 'MSP430FR5969':
            for category, ranges in self.MSP430FR5969_MAP.items():
                for start, end, volatility, description in ranges:
                    self.regions.append({
                        'start': start,
                        'end': end,
                        'category': category,
                        'volatility': volatility,
                        'description': description
                    })
        
        # 排序
        self.regions.sort(key=lambda r: r['start'])
    
    def get_region(self, address):
        """
        查询地址所属区域
        
        Args:
            address: 目标地址
        
        Returns:
            dict: 区域信息，或None
        """
        for region in self.regions:
            if region['start'] <= address <= region['end']:
                return region
        return None
    
    def classify_address(self, address):
        """
        分类地址
        
        Args:
            address: 目标地址
        
        Returns:
            str: 'SRAM' | 'FRAM' | 'MMIO' | 'UNKNOWN'
        """
        region = self.get_region(address)
        if region:
            return region['category']
        return 'UNKNOWN'
    
    def is_fram(self, address):
        """地址是否在FRAM范围"""
        return self.classify_address(address) == 'FRAM'
    
    def is_sram(self, address):
        """地址是否在SRAM范围"""
        return self.classify_address(address) == 'SRAM'
    
    def is_volatile(self, address):
        """地址是否易失"""
        region = self.get_region(address)
        if region:
            return region['volatility'] == 'volatile'
        return True  # 保守：未知区域视为易失
    
    def is_persistent(self, address):
        """地址是否持久化"""
        region = self.get_region(address)
        if region:
            return region['volatility'] == 'persistent'
        return False
    
    def print_memory_map(self):
        """打印内存映射表"""
        print("="*70)
        print(f"  {self.chip} 内存映射")
        print("="*70)
        
        for region in self.regions:
            addr_range = f"0x{region['start']:04X}-0x{region['end']:04X}"
            size = region['end'] - region['start'] + 1
            size_str = f"{size//1024}KB" if size >= 1024 else f"{size}B"
            
            print(f"  {addr_range:20s}  {size_str:8s}  {region['category']:8s}  "
                  f"{region['volatility']:12s}  {region['description']}")
        
        print("="*70)


if __name__ == '__main__':
    # 测试
    mapper = MemoryMapper()
    mapper.print_memory_map()
    
    # 测试地址
    test_addrs = [0x1c00, 0x4800, 0x0240, 0x441E]
    print("\n地址分类测试:")
    for addr in test_addrs:
        category = mapper.classify_address(addr)
        is_vol = mapper.is_volatile(addr)
        print(f"  0x{addr:04X}: {category:8s} ({'易失' if is_vol else '持久'})")





