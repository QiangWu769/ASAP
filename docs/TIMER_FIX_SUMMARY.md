# 🔧 定时器断电模拟问题修复总结

## ❌ 问题现象

用户反馈：
- ✅ 程序正常运行，输出了100次完整循环（"start" + "stats" + "end"）
- ❌ **从未亮灯**（LED应该在热启动时闪3次）
- ❌ **定时器从未触发复位**

## 🔍 根因分析

### 1. ACLK 时钟源配置错误

**原始代码**：
```c
CSCTL2 = SELA_0 | SELS_3 | SELM_3;  // ACLK = XT1CLK
```

**问题**：
- `SELA_0` 选择 XT1CLK 作为 ACLK 源
- XT1 晶振未连接或未启动
- **ACLK 无时钟 → TimerB 无法工作**

### 2. 验证步骤

检查中断向量表：
```bash
$ msp430-elf-objdump -s --section=__interrupt_vector_51 ar_0pure_asap_timer1_loop100.out
 fff4 12ba    # ✅ 正确指向 TimerB1_ISR (0xba12)
```

检查 TimerB1_ISR 函数：
```bash
$ msp430-elf-objdump -d ar_0pure_asap_timer1_loop100.out | grep TimerB1_ISR
0000ba12 <TimerB1_ISR>:  # ✅ 函数存在
```

**结论**：中断向量和 ISR 都正确，但 ACLK 无时钟导致定时器不工作。

---

## ✅ 修复方案

### 1. 修复 ACLK 时钟源

```c
// ⭐ 修改前：使用外部晶振（可能不存在）
CSCTL2 = SELA_0 | SELS_3 | SELM_3;

// ⭐ 修改后：使用内部低频振荡器
CSCTL2 = SELA__VLOCLK | SELS_3 | SELM_3;  // ACLK = VLOCLK (10kHz)
```

### 2. 调整定时器周期

**时钟计算**：
- VLOCLK ≈ 10kHz（内部低频振荡器）
- TimerB 分频：/8
- 实际频率：10000 / 8 = **1250 Hz**

**周期调整**：
```c
// ⭐ 修改前：
#define min_pf 100
int timer_count = 500;  // 500/1250 = 0.4秒（太长）

// ⭐ 修改后：
#define min_pf 50   // 50/1250 = 0.04秒 = 40ms
int timer_count = 125;  // 125/1250 = 0.1秒
```

**随机范围**：
```c
// ⭐ 修改前：
mod5_rand = random_num % 51;
random_num = min_pf + mod5_rand * 8;  // 100~500 (0.08~0.4s)

// ⭐ 修改后：
mod5_rand = random_num % 31;          // 0~30
random_num = min_pf + mod5_rand * 5;  // 50~200 (0.04~0.16s)
```

---

## 📦 固件信息

**文件名**：`ar_0pure_asap_timer1_loop100_v2.out` / `.hex`

**关键配置**：
- ✅ **ACLK = VLOCLK** (10kHz内部振荡器)
- ✅ **LOOP_IDX = 100** (100次完整循环)
- ✅ **TIMER = 1** (随机断电：0.04s~0.16s)
- ✅ **热启动LED闪烁** (应该看到红色LED快速闪3次)

---

## 🔍 预期输出

### 正常情况（带断电模拟）

```
Init OK
start
[F]<WID编号>        ← 🎉 热启动标记
-+OK                ← LED闪3次
stats: s 4 (50%) m 4 (50%) sum/tot 8/8: V
end
start
[F]<WID编号>        ← 又一次断电恢复
-+OK
stats: s 4 (50%) m 4 (50%) sum/tot 8/8: V
end
...
(重复100次)
end
(程序停止)
```

### 判断标准

| 现象 | 说明 |
|------|------|
| ✅ 看到 `[F]<数字>` | 热启动成功 |
| ✅ LED 闪烁 | 热启动LED指示 |
| ✅ 多次 "start" 但未断电 | 定时器仍未触发（继续调试） |
| ❌ 只有 "Init OK" 然后卡住 | 可能在 init 中就触发断电 |

---

## 🎯 验证步骤

1. **Mass Erase** 清空 FRAM
2. **烧录** `ar_0pure_asap_timer1_loop100_v2.hex`
3. **观察输出**：
   - 应该看到 `[F]<数字>` 和 LED 闪烁
   - 每次循环可能被打断 3-10 次
4. **检查 FRAM**：
   - `0x6510` = 热启动计数器（应该 >0）
   - `0x7000` = WID（应该非 0xFFFF/0x0000）

---

## 📝 代码变更

| 文件 | 修改内容 |
|------|---------|
| `main0pure.c` | ✅ ACLK 时钟源：`SELA_0` → `SELA__VLOCLK` |
| `main0pure.c` | ✅ 定时器周期：`500` → `125` |
| `main0pure.c` | ✅ 最小间隔：`100` → `50` |
| `main0pure.c` | ✅ 随机范围：`100~500` → `50~200` |
| `param.h` | ✅ 循环次数：`LOOP_IDX = 1` → `100` |

---

## 🚀 下一步

**立即测试这个固件！** 如果还是没有看到 LED 闪烁：

1. **增加调试输出**：在 `TimerB1_ISR` 中输出调试信息
2. **检查寄存器**：查看 TBCTL, TBCCR1, TBCCTL1 的值
3. **降低周期**：进一步减小 `timer_count` 到 25-50

