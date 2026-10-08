#include <msp430.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>

// 使用BC的简化库（代替chinchilla库）
// #include "../bc/libio/log.h"     // 【注释】不使用printf
// #include "../bc/libio/printf.h"  // 【注释】不使用printf

// BITSET宏定义
#define BITSET(port, val) ((port) |= (val))

// TIMER is defined by Makefile: -DTIMER=0 or -DTIMER=1
#ifndef TIMER
#define TIMER 0
#endif

// #ifdef PF_SIMULATION
// #define min_pf 10
// __attribute__((section(".upper.noinit"))) int timer_count = 500;
// __attribute__((section(".upper.noinit"))) volatile unsigned int random_num; // read temperature value
// __attribute__((section(".upper.noinit"))) int mod5_rand;
// #endif

#if TIMER == 1
// ========== 定时器中断（周期性断电）==========
__attribute__((interrupt(TIMER0_B1_VECTOR)))
void TimerB1_ISR(void){
	PMMCTL0 = PMMPW | PMMSWPOR;  // 触发软件POR，模拟断电
	TBCTL |= TBCLR;              // 清除定时器（POR会复位一切）
}
#endif

#define NUM_BUCKETS 64 // must be a power of 2
#define MAX_RELOCATIONS 8
#define NUM_KEYS (NUM_BUCKETS / 4) // shoot for 25% occupancy
#define INIT_KEY 0x1

typedef uint16_t value_t;
typedef uint16_t hash_t;
typedef uint16_t fingerprint_t;
typedef uint16_t index_t; // bucket index

// filter改为局部变量（在main中），让ASAP保护
// __attribute__((section(".upper.noinit"))) static fingerprint_t filter[NUM_BUCKETS];

// print_stats 函数已删除（未使用）

static hash_t djb_hash(uint8_t* data, unsigned len)
{
    uint32_t hash = 5381;
    unsigned int i;

    for(i = 0; i < len; data++, i++) {
        hash = ((hash << 5) + hash) + (*data);
    }

    return hash & 0xFFFF;
}

static index_t hash_fp_to_index(fingerprint_t fp)
{
    hash_t hash = djb_hash((uint8_t *)&fp, sizeof(fingerprint_t));
    return hash & (NUM_BUCKETS - 1);
}

static index_t hash_key_to_index(value_t fp)
{
    hash_t hash = djb_hash((uint8_t *)&fp, sizeof(value_t));
    return hash & (NUM_BUCKETS - 1);
}

static fingerprint_t hash_to_fingerprint(value_t key)
{
    return djb_hash((uint8_t *)&key, sizeof(value_t));
}

static value_t generate_key(value_t prev_key)
{
    return (prev_key + 1) * 17;
}

static bool insert(fingerprint_t *filter, value_t key)
{
    fingerprint_t fp1, fp2, fp_victim, fp_next_victim;
    index_t index_victim, fp_hash_victim;
    unsigned relocation_count = 0;

    fingerprint_t fp = hash_to_fingerprint(key);
    index_t index1 = hash_key_to_index(key);
    index_t fp_hash = hash_fp_to_index(fp);
    index_t index2 = index1 ^ fp_hash;

    fp1 = filter[index1];
    if (!fp1) {
        filter[index1] = fp;
    } else {
        fp2 = filter[index2];
        if (!fp2) {
            filter[index2] = fp;
        } else {
            if (rand() & 0x80) {
                index_victim = index1;
                fp_victim = fp1;
            } else {
                index_victim = index2;
                fp_victim = fp2;
            }

            filter[index_victim] = fp;

            do {
                fp_hash_victim = hash_fp_to_index(fp_victim);
                index_victim = index_victim ^ fp_hash_victim;

                fp_next_victim = filter[index_victim];
                filter[index_victim] = fp_victim;

                fp_victim = fp_next_victim;
            } while (fp_victim && ++relocation_count < MAX_RELOCATIONS);

            if (fp_victim) {
                return false;
            }
        }
    }
    return true;
}

static bool lookup(fingerprint_t *filter, value_t key)
{
    fingerprint_t fp = hash_to_fingerprint(key);
    index_t index1 = hash_key_to_index(key);
    index_t fp_hash = hash_fp_to_index(fp);
    index_t index2 = index1 ^ fp_hash;

    return filter[index1] == fp || filter[index2] == fp;
}




/* Initialize UART */
void init()
{
	WDTCTL = WDTPW | WDTHOLD;

	PM5CTL0 &= ~LOCKLPM5;

	P1DIR |= BIT2;
	P1OUT |= BIT2;
	
	CSCTL0_H = 0xA5;
	CSCTL1 = DCOFSEL_6;
	CSCTL2 = SELA_0 | SELS_3 | SELM_3;
	CSCTL3 = DIVA_0 | DIVS_0 | DIVM_0;
	
	UCA0CTLW0 = UCSWRST;
	UCA0CTLW0 |= UCSSEL__SMCLK;
	UCA0BR0 = 4;
	UCA0BR1 = 0;
	UCA0MCTLW = UCOS16 | UCBRF_4 | (0x55 << 8);
	
	P2SEL1 |= BIT0 | BIT1;
	P2SEL0 &= ~(BIT0 | BIT1);
	
	UCA0CTLW0 &= ~UCSWRST;

    // 定时器初始化移到了 main() 中，在 init() 之后启动
#if TIMER == 1
    // ===== 定时器在 init() 之后启动（确保外设初始化完成）=====
    TBCTL = TBSSEL_2 | ID_0 | MC_2 | TBCLR;  // SMCLK, 不分频, 连续模式
    TBCCTL1 = CCIE;                           // 使能CCR1中断
    TBCCR1 = 40000;                           // 定时器周期
    __enable_interrupt();                     // 使能全局中断
#endif
	
}

int main()
{
    init();
    
    //while (1) {
        unsigned i;
        value_t key;
        unsigned iteration = 0;
        fingerprint_t filter[NUM_BUCKETS];  // 局部变量，让ASAP保护

        iteration++;
        
        // PRINTF("start\r\n");  // 【注释】测试无输出版本
        
        // Initialize filter - 全部展开（128个元素）
        filter[0] = 0; filter[1] = 0; filter[2] = 0; filter[3] = 0;
        filter[4] = 0; filter[5] = 0; filter[6] = 0; filter[7] = 0;
        filter[8] = 0; filter[9] = 0; filter[10] = 0; filter[11] = 0;
        filter[12] = 0; filter[13] = 0; filter[14] = 0; filter[15] = 0;
        filter[16] = 0; filter[17] = 0; filter[18] = 0; filter[19] = 0;
        filter[20] = 0; filter[21] = 0; filter[22] = 0; filter[23] = 0;
        filter[24] = 0; filter[25] = 0; filter[26] = 0; filter[27] = 0;
        filter[28] = 0; filter[29] = 0; filter[30] = 0; filter[31] = 0;
        filter[32] = 0; filter[33] = 0; filter[34] = 0; filter[35] = 0;
        filter[36] = 0; filter[37] = 0; filter[38] = 0; filter[39] = 0;
        filter[40] = 0; filter[41] = 0; filter[42] = 0; filter[43] = 0;
        filter[44] = 0; filter[45] = 0; filter[46] = 0; filter[47] = 0;
        filter[48] = 0; filter[49] = 0; filter[50] = 0; filter[51] = 0;
        filter[52] = 0; filter[53] = 0; filter[54] = 0; filter[55] = 0;
        filter[56] = 0; filter[57] = 0; filter[58] = 0; filter[59] = 0;
        filter[60] = 0; filter[61] = 0; filter[62] = 0; filter[63] = 0;

        // Insert phase
        key = INIT_KEY;
        unsigned inserts = 0;
        for (i = 0; i < NUM_KEYS; ++i) {
            key = generate_key(key);
            bool success = insert(filter, key);
            inserts += success;
        }

        // Lookup phase
        key = INIT_KEY;
        unsigned members = 0;
        for (i = 0; i < NUM_KEYS; ++i) {
            key = generate_key(key);
            bool member = lookup(filter, key);
            members += member;
        }
        
        
        // 【P1.2标志】一个迭代完成
        P1OUT &= ~BIT2;
      //  P1OUT |= BIT2;
    //}

    return 0;
}

