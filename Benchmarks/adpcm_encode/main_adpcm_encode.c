/* Intel/DVI ADPCM Encoder - MSP430 ASAP 版本 */
/* 原始来源: MiBench2 benchmark suite (adpcm_encode) */
/* Copyright 1992 by Stichting Mathematisch Centrum, Amsterdam */

#include <msp430.h>
#include <stdint.h>

// 使用本地简化版libio
#include "libio/printf.h"

// 简单的BITSET宏
#define BITSET(port, val) ((port) |= (val))

// TIMER配置：0=正常运行，1=定时器模拟断电
#ifndef TIMER
#define TIMER 1
#endif

/*===========================================================================
 * ADPCM 类型定义和状态结构（来自 adpcm.h）
 *===========================================================================*/

struct adpcm_state {
    short valprev;    // 上一个输出值
    char  index;      // stepsize表索引
};

/*===========================================================================
 * ADPCM 查找表（来自 adpcm.c）
 *===========================================================================*/

// Intel ADPCM step variation table
static const int indexTable[16] = {
    -1, -1, -1, -1, 2, 4, 6, 8,
    -1, -1, -1, -1, 2, 4, 6, 8,
};

static const int stepsizeTable[89] = {
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17,
    19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
    50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
    130, 143, 157, 173, 190, 209, 230, 253, 279, 307,
    337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
    876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
    2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358,
    5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
    15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767
};

/*===========================================================================
 * 测试输入数据（8-bit PCM 样本）
 *===========================================================================*/

static const unsigned char test_data[] = {
    0x80, 0x82, 0x84, 0x86, 0x88, 0x8A, 0x8C, 0x8E,
    0x90, 0x92, 0x94, 0x96, 0x98, 0x9A, 0x9C, 0x9E,
    0xA0, 0xA2, 0xA4, 0xA6, 0xA8, 0xAA, 0xAC, 0xAE,
    0xB0, 0xB2, 0xB4, 0xB6, 0xB8, 0xBA, 0xBC, 0xBE,
    0xC0, 0xBE, 0xBC, 0xBA, 0xB8, 0xB6, 0xB4, 0xB2,
    0xB0, 0xAE, 0xAC, 0xAA, 0xA8, 0xA6, 0xA4, 0xA2,
    0xA0, 0x9E, 0x9C, 0x9A, 0x98, 0x96, 0x94, 0x92,
    0x90, 0x8E, 0x8C, 0x8A, 0x88, 0x86, 0x84, 0x82,
    0x80, 0x7E, 0x7C, 0x7A, 0x78, 0x76, 0x74, 0x72,
    0x70, 0x6E, 0x6C, 0x6A, 0x68, 0x66, 0x64, 0x62,
    0x60, 0x5E, 0x5C, 0x5A, 0x58, 0x56, 0x54, 0x52,
    0x50, 0x4E, 0x4C, 0x4A, 0x48, 0x46, 0x44, 0x42,
    0x40, 0x42, 0x44, 0x46, 0x48, 0x4A, 0x4C, 0x4E,
    0x50, 0x52, 0x54, 0x56, 0x58, 0x5A, 0x5C, 0x5E,
    0x60, 0x62, 0x64, 0x66, 0x68, 0x6A, 0x6C, 0x6E,
    0x70, 0x72, 0x74, 0x76, 0x78, 0x7A, 0x7C, 0x7E
};

/*===========================================================================
 * 输出缓冲区（编码后的 4-bit ADPCM 数据）
 *===========================================================================*/

#define NSAMPLES 128
#define NINC     64   // 每次处理的样本数

// 编码输出：每2个样本产生1字节，所以 NSAMPLES/2 字节
unsigned char outbuf[NSAMPLES / 2];

/*===========================================================================
 * 定时器中断（仅TIMER==1时）
 *===========================================================================*/

#if TIMER == 1
__attribute__((interrupt(TIMER0_B1_VECTOR)))
void TimerB1_ISR(void){
    PMMCTL0 = PMMPW | PMMSWPOR;  // 触发软件POR，模拟断电
    BITSET(TBCTL, TBCLR);
}
#endif

/*===========================================================================
 * 硬件初始化
 *===========================================================================*/

static void init(void)
{
    // 1. 关闭看门狗
    WDTCTL = WDTPW | WDTHOLD;
    
    // 6. 解锁GPIO（必须在GPIO操作前）
    PM5CTL0 &= ~LOCKLPM5;
    
    // 7. P1.2初始化并置高（标记程序开始）
    P1DIR |= BIT2;
    P1OUT |= BIT2;

    // 2. 配置时钟为8MHz（必须在UART配置前）
    CSCTL0_H = 0xA5;
    CSCTL1 = DCOFSEL_6;  // DCO = 8MHz
    CSCTL2 = SELA_0 | SELS_3 | SELM_3;  // ACLK=XT1, SMCLK=DCO, MCLK=DCO
    CSCTL3 = DIVA_0 | DIVS_0 | DIVM_0;  // 不分频
    
    // 3. 配置UART: 8MHz / 16 / 4.34 ≈ 115200 bps
    UCA0CTLW0 = UCSWRST;  // 开始配置（设置复位）
    UCA0CTLW0 |= UCSSEL__SMCLK;
    UCA0BR0 = 4;           // 8MHz / 16 / 115200 = 4.34
    UCA0BR1 = 0;
    UCA0MCTLW = UCOS16 | UCBRF_5 | (0x55 << 8);  // 过采样x16, UCBRF=5, UCBRS=0x55
    
    // 4. 配置UART引脚（P2.0=TXD, P2.1=RXD）
    P2SEL1 |= BIT0 | BIT1;
    P2SEL0 &= ~(BIT0 | BIT1);
    
    // 5. 解除UART复位（启用UART）
    UCA0CTLW0 &= ~UCSWRST;
    
    // 8. 定时器配置（如果启用）
#if TIMER == 1
    // 初始化定时器B1用于模拟断电
    BITSET(TBCTL, (TBSSEL_1 | ID_3 | MC_2 | TBCLR));  // ACLK(32768Hz), /8=4096Hz, continuous
    BITSET(TBCCTL1, CCIE);
#ifndef TIMER_VALUE
#define TIMER_VALUE 40
#endif
    TBCCR1 = TIMER_VALUE;
#endif
    
    // 9. 使能中断
    __enable_interrupt();
}

/*===========================================================================
 * ADPCM 编码函数（来自 adpcm.c，忠实于原版）
 *===========================================================================*/

// __attribute__((noinline)) 防止编译器内联，确保 ASAP 能正确追踪
__attribute__((noinline))
void adpcm_coder(
    const unsigned char *indata,
    unsigned char *outdata,
    int len,
    struct adpcm_state *state)
{
    const unsigned char *inp;  // 输入缓冲区指针
    unsigned char *outp;       // 输出缓冲区指针
    int val;                   // 当前输入样本值
    int sign;                  // 当前ADPCM符号位
    int delta;                 // 当前ADPCM输出值
    int diff;                  // val和valpred之差
    int step;                  // 步长
    int valpred;               // 预测值
    int vpdiff;                // 预测差值
    int index;                 // 步长表索引
    int outputbuffer;          // 缓存上一个4-bit值
    int bufferstep;            // 在outputbuffer和output之间切换

    outp = outdata;
    inp = indata;

    valpred = state->valprev;
    index = state->index;
    step = stepsizeTable[index];
    
    bufferstep = 1;

    for ( ; len > 0 ; len-- ) {
        val = *inp++;

        /* Step 1 - compute difference with previous value */
        diff = val - valpred;
        sign = (diff < 0) ? 8 : 0;
        if ( sign ) diff = (-diff);

        /* Step 2 - Divide and clamp */
        delta = 0;
        vpdiff = (step >> 3);
        
        if ( diff >= step ) {
            delta = 4;
            diff -= step;
            vpdiff += step;
        }
        step >>= 1;
        if ( diff >= step  ) {
            delta |= 2;
            diff -= step;
            vpdiff += step;
        }
        step >>= 1;
        if ( diff >= step ) {
            delta |= 1;
            vpdiff += step;
        }

        /* Step 3 - Update previous value */
        if ( sign )
            valpred -= vpdiff;
        else
            valpred += vpdiff;

        /* Step 4 - Clamp previous value to 16 bits */
        if ( valpred > 32767 )
            valpred = 32767;
        else if ( valpred < -32768 )
            valpred = -32768;

        /* Step 5 - Assemble value, update index and step values */
        delta |= sign;
        
        index += indexTable[delta];
        if ( index < 0 ) index = 0;
        if ( index > 88 ) index = 88;
        step = stepsizeTable[index];

        /* Step 6 - Output value */
        if ( bufferstep ) {
            outputbuffer = (delta << 4) & 0xf0;
        } else {
            *outp++ = (delta & 0x0f) | outputbuffer;
        }
        bufferstep = !bufferstep;
    }

    /* Output last step, if needed */
    if ( !bufferstep )
        *outp++ = outputbuffer;
    
    state->valprev = valpred;
    state->index = index;
}

/*===========================================================================
 * 主函数
 *===========================================================================*/

int main(void)
{
    init();

    struct adpcm_state state;
    int n;
    const unsigned char *currentN;
    int maxN;
    int bytesIntoRead;
    int testN;
    
    while (1) {
        // 初始化
        state.valprev = 0;
        state.index = 0;
        currentN = test_data;
        maxN = sizeof(test_data);
        
        _uart_puts("Initial valprev=");
        _uart_print_uint(state.valprev);
        _uart_puts(" index=");
        _uart_print_uint(state.index);
        _uart_puts("\r\n");
        
        // 分块编码循环
        while(1) {
            bytesIntoRead = (int)(currentN - test_data);
            testN = bytesIntoRead + NINC;
            n = (testN <= maxN) ? NINC : maxN - bytesIntoRead;

            if ( n == 0 ) break;

            // 编码：输入n个样本，输出n/2字节
            adpcm_coder(currentN, outbuf, n, &state);
            currentN = test_data + bytesIntoRead + n;
        }
        
        _uart_puts("Final valprev=");
        _uart_print_uint((unsigned int)(state.valprev & 0xFFFF));
        _uart_puts(" index=");
        _uart_print_uint(state.index);
        _uart_puts("\r\n");
        
        // P1.2 低脉冲（一轮完成标志）
        P1OUT &= ~BIT2;
        __delay_cycles(8000);  // 1ms @ 8MHz
        P1OUT |= BIT2;
    }
    
    return 0;
}























