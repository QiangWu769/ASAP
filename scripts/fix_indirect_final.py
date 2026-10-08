#!/usr/bin/env python3
"""
最终方案：基于备份逻辑重定向间接寻址

关键洞察：
1. 间接寻址WID在备份时，已经通过正确的R12值访问了正确的内存
2. 备份的不是R12的值，而是@R12指向的内存内容
3. 恢复时不需要重建R12，而是直接恢复那块内存

策略：
- 查找间接寻址WID对应的备份代码
- 找出它实际备份到哪个FRAM槽位
- 恢复时直接从那个槽位恢复，不管R12是什么

但问题是：同一个槽位可能被多个WID使用（因为是按地址分配的）
所以无法简单重定向...

更好的方案：
- 间接寻址WID使用独立的FRAM槽位（已经有了）
- 恢复时：**不要尝试恢复间接寻址变量**
- 依赖：调用者的栈变量会被恢复，然后重新执行业务逻辑会重新设置R12

但这会导致数据丢失...

实际上最好的方案是：
- 保留间接寻址WID的备份（已经备份到独立槽位）
- 恢复时跳过这些WID（让代码重新执行）
- 依赖调用者栈变量的恢复
"""
import json

# 加载数据
candidates = json.load(open('build/candidates.json'))
fram_slots = json.load(open('build/fram_slots.json'))
pc_ranges = json.load(open('build/pc_ranges_full.json'))

# 策略1：检查间接寻址WID是否有独立的FRAM槽位
print("=== 检查间接寻址WID的FRAM槽位分配 ===")
addr_to_slot = fram_slots.get('addr_to_slot', {})

indirect_wids = [(wid, info) for wid, info in candidates.items() 
                 if info.get('base_reg') in ['R12', 'R13', 'R14', 'R15']]

print(f"间接寻址WID数量: {len(indirect_wids)}")

for wid, info in indirect_wids[:10]:
    logical_addr = info['logical_addr']
    if logical_addr in addr_to_slot:
        slot_info = addr_to_slot[logical_addr]
        print(f"  {wid}: {logical_addr} → {slot_info['slot_symbol']}")
    else:
        print(f"  {wid}: {logical_addr} → 无槽位！")

# 策略2：对于恢复，我们有几个选择：
print("\n=== 恢复策略选择 ===")
print("方案A（保守）：不恢复间接寻址变量")
print("  - 优点：不会恢复错误")
print("  - 缺点：这些变量的值会丢失，依赖重新执行")
print("  - 适用：如果这些变量会被重新计算\n")

print("方案B（激进）：恢复间接寻址变量但使用固定地址")
print("  - 问题：R12的值在恢复时是未知的")
print("  - 需要：在恢复代码中重建R12的值")
print("  - 复杂度：高\n")

print("方案C（最佳）：备份时不通过间接寻址，直接备份目标地址")
print("  - 需要：修改stage5的备份插桩")
print("  - 在备份前，计算R12+offset的实际地址")
print("  - 直接备份那个地址的内容\n")

# 实施方案C的思路：
print("=== 方案C实施思路 ===")
print("在stage5备份插桩时，对于间接寻址WID：")
print("1. 不插入：MOV.W @R12, &SLOT_xxx")
print("2. 改为：")
print("   MOV.W R12, R15       ; 保存R12")
print("   ADD.W #offset, R15   ; 计算实际地址")
print("   MOV.W @R15, &SLOT_xxx; 从实际地址备份")
print("3. 恢复时同样计算地址恢复\n")

# 临时方案：标记哪些WID可以安全映射
print("=== 生成可映射的间接寻址列表 ===")
safe_redirects = {}
for wid, info in indirect_wids:
    logical_addr = info['logical_addr']
    # 检查是否在call_sites中找到了映射
    # （由improved_stage5d.py生成的）
    
print("建议：使用improved_stage5d.py找到的3个映射，其余不恢复")

