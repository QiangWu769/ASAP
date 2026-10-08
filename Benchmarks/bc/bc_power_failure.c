// bc_power_failure.c - 带软件断电模拟的bc测试
// 参考ImmortalThreads和Chinchilla的方式

#include <msp430.h>
#include <stdint.h>
#include "libio/log.h"

// 软件断电模拟配置
#define ENABLE_POWER_FAILURE 1
#define POWER_FAILURE_AT_WID 20  // 在WID=20时触发断电

// Timer中断：模拟断电
#if ENABLE_POWER_FAILURE
volatile uint16_t pf_trigger = 0;

__attribute__((interrupt(TIMER0_B1_VECTOR)))
void TimerB0_ISR(void) {
    // 触发软件复位（模拟断电）
    PMMCTL0 = PMMPW | PMMSWPOR;
}
#endif

// [这里插入bc_clean_debug.c的全部内容，但修改main函数]

// ... (bits数组等保持不变) ...

