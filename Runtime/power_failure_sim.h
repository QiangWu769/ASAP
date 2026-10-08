/* 
 * 断电模拟 - 简单版本
 * 通过计数备份次数，在指定次数后触发软件复位
 */

#ifndef POWER_FAILURE_SIM_H
#define POWER_FAILURE_SIM_H

#include <msp430.h>

/* 配置：在第几次备份后触发断电 (0=禁用) */
#define POWER_FAIL_AT_BACKUP  50

/* FRAM中的计数器地址 */
#define BACKUP_COUNTER_ADDR  0x7002

/* 触发软件复位（模拟断电） */
static inline void trigger_power_failure(void) {
    /* 方式1: 触发看门狗复位 */
    WDTCTL = 0x0000;  // 错误的密码，触发复位
    
    /* 方式2: 触发PUC (Power-Up Clear) */
    // PMMCTL0 = PMMPW | PMMSWPOR;
    
    while(1);  // 等待复位
}

/* 在每次备份后调用 */
static inline void check_power_failure(void) {
#if POWER_FAIL_AT_BACKUP > 0
    /* 读取并递增计数器 */
    unsigned int count = *(unsigned int*)BACKUP_COUNTER_ADDR;
    count++;
    *(unsigned int*)BACKUP_COUNTER_ADDR = count;
    
    /* 检查是否触发断电 */
    if (count >= POWER_FAIL_AT_BACKUP) {
        /* 清空计数器（下次重新计数） */
        *(unsigned int*)BACKUP_COUNTER_ADDR = 0;
        
        /* 触发断电 */
        trigger_power_failure();
    }
#endif
}

#endif // POWER_FAILURE_SIM_H





































