#include <msp430.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>

// BITSET宏定义
#define BITSET(port, val) ((port) |= (val))

// TIMER is defined by Makefile: -DTIMER=0 or -DTIMER=1
#ifndef TIMER
#define TIMER 0
#endif

#if TIMER == 1
// ========== 定时器中断（周期性断电）==========
__attribute__((interrupt(TIMER0_B1_VECTOR)))
void TimerB1_ISR(void){
	PMMCTL0 = PMMPW | PMMSWPOR;  // 触发软件POR，模拟断电
	TBCTL |= TBCLR;              // 清除定时器（POR会复位一切）
}
#endif

/* ================= 配置参数 ================= */
#define NUM_BUCKETS 128         // 必须是2的幂
#define MAX_RELOCATIONS 8       // 插入失败前的最大踢出重试次数
#define NUM_KEYS (NUM_BUCKETS / 4) // 目标占用率 25%
#define INIT_KEY 0x1

/* ================= 类型定义 ================= */
typedef uint16_t value_t;
typedef uint16_t hash_t;
typedef uint16_t fingerprint_t;
typedef uint16_t index_t; // 桶索引

/* ================= 全局变量 ================= */
// 【修复】filter 显式声明为全局变量，确保 ASAP 能正确追踪
fingerprint_t filter[NUM_BUCKETS];

// 【修复】自定义 PRNG 种子，替代 rand()
unsigned cf_rand_seed = 1;

/* ================= 自定义伪随机数生成器 ================= */
// 简单的线性同余生成器 (LCG)，替代 stdlib 的 rand()
// 因为 rand() 的内部状态无法被 ASAP 追踪
static unsigned cf_rand(void)
{
    cf_rand_seed = cf_rand_seed * 1103515245 + 12345;
    return (cf_rand_seed >> 16) & 0x7FFF;
}

/* ================= 哈希算法 ================= */

// DJB Hash 算法
static hash_t djb_hash(uint8_t* data, unsigned len)
{
    uint32_t hash = 5381;
    unsigned int i;

    for(i = 0; i < len; data++, i++) {
        hash = ((hash << 5) + hash) + (*data);
    }

    return hash & 0xFFFF;
}

// 计算指纹的哈希并映射到索引
static index_t hash_fp_to_index(fingerprint_t fp)
{
    hash_t hash = djb_hash((uint8_t *)&fp, sizeof(fingerprint_t));
    return hash & (NUM_BUCKETS - 1); 
}

// 计算 Key 的哈希并映射到索引
static index_t hash_key_to_index(value_t fp)
{
    hash_t hash = djb_hash((uint8_t *)&fp, sizeof(value_t));
    return hash & (NUM_BUCKETS - 1); 
}

// 将 Key 转换为指纹
static fingerprint_t hash_to_fingerprint(value_t key)
{
    return djb_hash((uint8_t *)&key, sizeof(value_t));
}

// 生成伪随机测试数据
static value_t generate_key(value_t prev_key)
{
    // (prev_key + 1) * 17 用于生成确定的伪随机序列以供验证
    return (prev_key + 1) * 17;
}

/* ================= 核心业务逻辑：Cuckoo Filter ================= */

// 插入操作
// 【修复】filter 现在是全局变量，不再作为参数传递
static bool insert(value_t key)
{
    fingerprint_t fp1, fp2, fp_victim, fp_next_victim;
    index_t index_victim, fp_hash_victim;
    unsigned relocation_count = 0;

    fingerprint_t fp = hash_to_fingerprint(key);

    index_t index1 = hash_key_to_index(key);
    index_t fp_hash = hash_fp_to_index(fp);
    index_t index2 = index1 ^ fp_hash;

    fp1 = filter[index1];
    if (!fp1) { // 位置 1 空闲
        filter[index1] = fp;
    } else {
        fp2 = filter[index2];
        if (!fp2) { // 位置 2 空闲
            filter[index2] = fp;
        } else { // 两个位置都被占用，执行踢出（Evict）操作
            
            // 【修复】使用自定义 cf_rand() 替代 rand()
            if (cf_rand() & 0x80) { 
                index_victim = index1;
                fp_victim = fp1;
            } else {
                index_victim = index2;
                fp_victim = fp2;
            }

            filter[index_victim] = fp; // 踢出受害者，放入新指纹

            do { // 重新安置受害者 (Relocate)
                fp_hash_victim = hash_fp_to_index(fp_victim);
                index_victim = index_victim ^ fp_hash_victim;

                fp_next_victim = filter[index_victim];
                filter[index_victim] = fp_victim;

                fp_victim = fp_next_victim;
            } while (fp_victim && ++relocation_count < MAX_RELOCATIONS);

            if (fp_victim) {
                // 达到最大重试次数，插入失败（过滤器太满）
                return false;
            }
        }
    }
    return true;
}

// 查找操作
// 【修复】filter 现在是全局变量，不再作为参数传递
static bool lookup(value_t key)
{
    fingerprint_t fp = hash_to_fingerprint(key);

    index_t index1 = hash_key_to_index(key);
    index_t fp_hash = hash_fp_to_index(fp);
    index_t index2 = index1 ^ fp_hash;

    // 检查两个可能的桶位置
    return filter[index1] == fp || filter[index2] == fp;
}

void init()
{
	WDTCTL = WDTPW | WDTHOLD;
	PM5CTL0 &= ~LOCKLPM5;

	// P1.2: Performance indicator (init开始时置高)
	P1DIR |= BIT2;
	P1OUT |= BIT2;  // 使用|=避免清除P1.3
	
	// Clock: 8MHz DCO
	CSCTL0_H = 0xA5;
	CSCTL1 = DCOFSEL_6;
	CSCTL2 = SELA_0 | SELS_3 | SELM_3;
	CSCTL3 = DIVA_0 | DIVS_0 | DIVM_0;
	
	// UART: 115200 baud @ 8MHz
	UCA0CTLW0 = UCSWRST;
	UCA0CTLW0 |= UCSSEL__SMCLK;
	UCA0BR0 = 4;
	UCA0BR1 = 0;
	UCA0MCTLW = UCOS16 | UCBRF_4 | (0x55 << 8);
	
	P2SEL1 |= BIT0 | BIT1;
	P2SEL0 &= ~(BIT0 | BIT1);
	
	UCA0CTLW0 &= ~UCSWRST;

#if TIMER == 1
    // ===== 定时器在 init() 之后启动（确保外设初始化完成）=====
    TBCTL = TBSSEL_1 | ID_3 | MC_2 | TBCLR;  // ACLK(32768Hz), /8=4096Hz, continuous
    TBCCTL1 = CCIE;
#ifndef TIMER_VALUE
#define TIMER_VALUE 40
#endif
    TBCCR1 = TIMER_VALUE;
    __enable_interrupt();                     // 使能全局中断
#endif
}

/* ================= 主程序 (验证逻辑) ================= */

int main()
{
    init();
    unsigned i;
    value_t key;

    // ===== 无限循环（和 CONV 保持一致）=====
    while(1) {
        // 1. 初始化过滤器 (清零)
        // 【修复】不使用 memset（库函数不被 ASAP 追踪）
        // 改用 for 循环，让每次写入都被 ASAP 追踪
        for (i = 0; i < NUM_BUCKETS; ++i) {
            filter[i] = 0;
        }
        
        // 重置随机数种子（确保每轮相同的随机序列，保持确定性）
        cf_rand_seed = 1;

        // 2. 插入阶段
        key = INIT_KEY;
        unsigned inserts = 0;
        for (i = 0; i < NUM_KEYS; ++i) {
            key = generate_key(key);
            bool success = insert(key);
            if (success) {
                inserts++;
            }
        }

        // 3. 查找/验证阶段
        key = INIT_KEY;
        unsigned members = 0;
        for (i = 0; i < NUM_KEYS; ++i) {
            key = generate_key(key);
            bool member = lookup(key);
            if (member) {
                members++;
            }
        }

        // 一轮完成：P1.2置低再置高（生成脉冲，和 CONV 一致）
        P1OUT &= ~BIT2;  // 置低
        __delay_cycles(8000); // 延迟1ms
        P1OUT |= BIT2;   // 置高
        
        // 继续下一轮
    }

    return 0;  // 实际上不会执行到这里
}
