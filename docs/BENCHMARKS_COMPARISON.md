# BC vs AR 基准测试综合对比

## 概述
本文档对比了BC（Bit Count）和AR（Activity Recognition）两个基准测试的配置、编译和ASAP保护特性。

---

## 一、输出优化对比

### BC 输出
**保留**：
- `start` - 程序开始
- `complete` - 一轮完成

**注释掉**：
- ❌ `end` 输出
- ❌ 7个位计数结果（n_0 到 n_6）
- ❌ 所有 LOG 调试输出

**输出格式**：
```
start
complete
start
complete
...
```

### AR 输出
**保留**：
- `start` - 程序开始
- `end` - 一轮完成
- `complete` - 完全完成
- `tr[0]...tr[15]` - 训练进度（16次）
- `rc[0]...rc[7]` - 识别进度（8次）

**注释掉**：
- ❌ 所有 LOG 调试输出（seed、acquire、transform、featurize、classify、stats、mode等）

**输出格式**：
```
start
tr[0] tr[1] tr[2] ... tr[15] 
tr[0] tr[1] tr[2] ... tr[15] 
rc[0] rc[1] rc[2] ... rc[7] 
end
complete
start
...
```

---

## 二、编译版本对比

两个基准测试都编译了相同的三个版本：

| 版本 | BC | AR |
|------|----|----|
| **纯净版** | bc_pure_no_asap.hex | ar_pure_no_asap.hex |
| 大小 | 6.6KB / 36KB | 10KB / 65KB |
| 特性 | 无ASAP，无定时器 | 无ASAP，无定时器 |
| | | |
| **ASAP版** | bc_asap_no_timer.hex | ar_asap_no_timer.hex |
| 大小 | 43KB / 64KB | 50KB / 90KB |
| 特性 | 有ASAP，无定时器 | 有ASAP，无定时器 |
| | | |
| **ASAP+定时器版** | bc_asap_timer.hex | ar_asap_timer.hex |
| 大小 | 43KB / 65KB | 50KB / 91KB |
| 特性 | 有ASAP，有定时器 | 有ASAP，有定时器 |

---

## 三、ASAP 保护特性对比

### BC（Bit Count）
| 指标 | 数值 |
|------|------|
| 总WID数 | 105 |
| 唯一地址数 | 44 |
| FRAM使用 | 106 字节 |
| 覆盖写优化 | 25个地址多次写入 |
| 平均恢复项/WID | 15.1 |
| 间接寻址重定向 | 0 个 |
| 函数数量 | 11-12 |
| 插桩函数 | 9 个子函数 |

### AR（Activity Recognition）
| 指标 | 数值 |
|------|------|
| 总WID数 | 118 |
| 唯一地址数 | 77 |
| FRAM使用 | 196 字节 |
| 覆盖写优化 | 24个地址多次写入 |
| 平均恢复项/WID | 14.6 |
| 间接寻址重定向 | 3 个 |
| 函数数量 | 17-18 |
| 插桩函数 | 15 个子函数 |

### 对比分析
- **AR 更复杂**：更多函数、更多WID、更大的FRAM占用
- **BC 更简洁**：较少的函数调用，代码体积更小
- **AR 需要间接重定向**：有3个间接地址需要特殊处理
- **恢复效率相近**：平均恢复项数相近（14.6 vs 15.1）

---

## 四、系统配置对比

两个基准测试使用**完全相同**的系统配置：

| 配置项 | 值 |
|--------|---|
| **MCU** | msp430fr5969 |
| **时钟频率** | 8MHz (DCO) |
| **UART波特率** | 115200 bps |
| **UART引脚** | P2.0 (TXD), P2.1 (RXD) |
| **定时器** | Timer B1 |
| **定时器源** | SMCLK |
| **定时器模式** | Continuous |
| **定时器比较值** | 40000 (~5ms @ 8MHz) |
| **GPIO标记** | P1.2 |
| **中断向量** | TIMER0_B1_VECTOR |

---

## 五、编译脚本对比

### BC 编译脚本
```bash
./compile_bc_all.sh
```

### AR 编译脚本
```bash
./compile_ar_all.sh
```

两个脚本结构相同：
1. 编译纯净版本（直接gcc）
2. 编译ASAP版本（make + TIMER=0）
3. 编译ASAP+定时器版本（make + TIMER=1）
4. 生成hex和out文件
5. 显示编译统计

---

## 六、算法特点对比

### BC（Bit Count）算法
- **功能**：统计32位整数中1的个数
- **算法数量**：7种不同实现
- **计算密集度**：高（大量位运算）
- **内存访问**：中等（查找表 + 栈变量）
- **函数调用**：简单（一层调用）
- **执行时间**：短（100次迭代 × 7种算法）

### AR（Activity Recognition）算法
- **功能**：基于加速度计的活动识别
- **阶段**：训练（2次×16样本）+ 识别（8样本）
- **计算密集度**：高（平方根、累加）
- **内存访问**：高（大量数组、结构体）
- **函数调用**：复杂（多层嵌套调用）
- **执行时间**：长（多阶段处理）

---

## 七、测试场景建议

### BC 适合测试：
- ✅ 位运算密集型计算
- ✅ 查找表访问
- ✅ 简单函数调用
- ✅ 快速迭代计算

### AR 适合测试：
- ✅ 复杂多层函数调用
- ✅ 数组和结构体操作
- ✅ 浮点数模拟运算
- ✅ 状态机切换
- ✅ 长时间运行场景

---

## 八、ASAP 开销对比

### BC ASAP 开销
| 项目 | 纯净版 | ASAP版 | 增长 |
|------|--------|--------|------|
| 代码大小 | 6.6KB | 43KB | **6.5x** |
| 二进制大小 | 36KB | 64KB | **1.8x** |

### AR ASAP 开销
| 项目 | 纯净版 | ASAP版 | 增长 |
|------|--------|--------|------|
| 代码大小 | 10KB | 50KB | **5x** |
| 二进制大小 | 65KB | 90KB | **1.4x** |

### 开销分析
- **BC 开销比例更高**：因为原始代码更小
- **AR 开销比例较低**：原始代码较大，ASAP增量相对较小
- **hex文件增长显著**：主要来自插桩和恢复逻辑
- **out文件增长适中**：包含调试信息

---

## 九、使用建议

### 选择 BC 当：
- 需要快速测试ASAP基本功能
- 测试简单的备份恢复机制
- 评估位运算的断电恢复
- 代码体积受限

### 选择 AR 当：
- 测试复杂的函数调用恢复
- 验证间接寻址重定向
- 评估长时间运行的断电恢复
- 模拟真实应用场景

### 同时使用两者：
- 全面评估ASAP系统
- 对比不同复杂度的开销
- 验证系统的通用性

---

## 十、文档索引

### BC 相关文档
- `BC_COMPILATION_SUMMARY.md` - BC编译总结
- `compile_bc_all.sh` - BC编译脚本
- `bc_pure_no_asap.hex` - BC纯净版
- `bc_asap_no_timer.hex` - BC ASAP版
- `bc_asap_timer.hex` - BC ASAP+定时器版

### AR 相关文档
- `AR_COMPILATION_SUMMARY.md` - AR编译总结
- `compile_ar_all.sh` - AR编译脚本
- `ar_pure_no_asap.hex` - AR纯净版
- `ar_asap_no_timer.hex` - AR ASAP版
- `ar_asap_timer.hex` - AR ASAP+定时器版

### 综合文档
- `BENCHMARKS_COMPARISON.md` - 本文档（综合对比）

---

## 十一、快速开始

### 编译所有版本
```bash
# 编译BC的三个版本
./compile_bc_all.sh

# 编译AR的三个版本
./compile_ar_all.sh
```

### 烧录测试
```bash
# BC纯净版
mspdebug tilib "prog bc_pure_no_asap.hex"

# BC ASAP+定时器版
mspdebug tilib "prog bc_asap_timer.hex"

# AR纯净版
mspdebug tilib "prog ar_pure_no_asap.hex"

# AR ASAP+定时器版
mspdebug tilib "prog ar_asap_timer.hex"
```

---

## 总结

✅ **BC和AR都已配置完成**，使用相同的系统配置  
✅ **输出已优化**，BC最简洁，AR保留进度信息  
✅ **三个版本都已编译**，可用于不同测试场景  
✅ **ASAP保护完整**，支持断电恢复  
✅ **文档齐全**，便于后续使用和维护  

**日期**：2025年11月22日


















