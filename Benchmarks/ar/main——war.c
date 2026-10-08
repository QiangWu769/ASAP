/* Intel/DVI ADPCM Decoder - MSP430 ASAP 版本 */
/* 原始来源: MiBench2 benchmark suite (adpcm_decode) */
/* Copyright 1992 by Stichting Mathematisch Centrum, Amsterdam */

//#include <msp430.h>
#include <stdint.h>

// 使用本地简化版libio（与ar/sha一致）
//#include "libio/printf.h"

// 简单的BITSET宏
//#define BITSET(port, val) ((port) |= (val))

// TIMER配置：0=正常运行，1=定时器模拟断电
// #ifndef TIMER
// #define TIMER 1
// #endif

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
 * 测试输入数据（精简版 input.h - 原始太大）
 * 每字节包含两个4-bit样本
 *===========================================================================*/

static const unsigned char test_data[] = {
    0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xF0,
    0x0F, 0x1E, 0x2D, 0x3C, 0x4B, 0x5A, 0x69, 0x78,
    0x87, 0x96, 0xA5, 0xB4, 0xC3, 0xD2, 0xE1, 0xF0,
    0x12, 0x21, 0x34, 0x43, 0x56, 0x65, 0x78, 0x87,
    0xAB, 0xBA, 0xCD, 0xDC, 0xEF, 0xFE, 0x01, 0x10,
    0x23, 0x32, 0x45, 0x54, 0x67, 0x76, 0x89, 0x98,
    0xAB, 0xBA, 0xCD, 0xDC, 0xEF, 0xFE, 0x01, 0x10,
    0xF0, 0xE1, 0xD2, 0xC3, 0xB4, 0xA5, 0x96, 0x87
};

/*===========================================================================
 * 输出缓冲区（来自 rawdaudio.c）
 *===========================================================================*/

// 【修复】减小缓冲区大小，避免栈溢出
// 原始: NSAMPLES=1000 会占用 2000 字节，几乎用完整个 SRAM
// test_data 只有 64 字节，最多产生 128 个样本，256 足够
#define NSAMPLES 256
#define NINC     64   // 每次处理的字节数

short sbuf[NSAMPLES];  // 解码输出缓冲区（16-bit PCM）


/*===========================================================================
 * ADPCM 解码函数（来自 adpcm.c，忠实于原版）
 *===========================================================================*/

// __attribute__((noinline)) 防止编译器内联，确保 ASAP 能正确追踪
//__attribute__((noinline))
void adpcm_decoder(
    const unsigned char *indata,
    short *outdata,
    int len,
    struct adpcm_state *state)
{
    const unsigned char *inp;  // 输入缓冲区指针
    short *outp;               // 输出缓冲区指针
    int sign;                  // 当前ADPCM符号位
    int delta;                 // 当前ADPCM输出值
    int step;                  // 步长
    int valpred;               // 预测值
    int vpdiff;                // 预测差值
    int index;                 // 步长表索引
    int inputbuffer;           // 缓存下一个4-bit值
    int bufferstep;            // 在inputbuffer和input之间切换

    outp = outdata;
    inp = indata;

    valpred = state->valprev;
    index = state->index;
    step = stepsizeTable[index];

    bufferstep = 0;
    
    for ( ; len > 0 ; len-- ) {
        
        /* Step 1 - get the delta value */
        if ( bufferstep ) {
            delta = inputbuffer & 0xf;
        } else {
            inputbuffer = *inp++;
            delta = (inputbuffer >> 4) & 0xf;
        }
        bufferstep = !bufferstep;

        /* Step 2 - Find new index value (for later) */
        index += indexTable[delta];
        if ( index < 0 ) index = 0;
        if ( index > 88 ) index = 88;

        /* Step 3 - Separate sign and magnitude */
        sign = delta & 8;
        delta = delta & 7;

        /* Step 4 - Compute difference and new predicted value */
        vpdiff = step >> 3;
        if ( delta & 4 ) vpdiff += step;
        if ( delta & 2 ) vpdiff += step>>1;
        if ( delta & 1 ) vpdiff += step>>2;

        if ( sign )
            valpred -= vpdiff;
        else
            valpred += vpdiff;

        /* Step 5 - clamp output value */
        if ( valpred > 32767 )
            valpred = 32767;
        else if ( valpred < -32768 )
            valpred = -32768;

        /* Step 6 - Update step value */
        step = stepsizeTable[index];

        /* Step 7 - Output value */
        *outp++ = valpred;
    }

    state->valprev = valpred;
    state->index = index;
}

/*===========================================================================
 * 主函数（忠实于 rawdaudio.c 结构）
 *===========================================================================*/

int main(void)
{


    struct adpcm_state state;
    int n;
    const unsigned char *currentN;
    int maxN;
    int bytesIntoRead;
    int testN;
    

    
    // P1.2 初始置高
    //P1OUT |= BIT2;
    
    //while (1) {
        // 初始化（对应原版 struct adpcm_state state = {}）
        state.valprev = 0;
        state.index = 0;
        currentN = test_data;
        maxN = sizeof(test_data);
        
        
        // 分块解码循环（忠实于原版 rawdaudio.c）
        while(1) {
            bytesIntoRead = (int)(currentN - test_data);
            testN = bytesIntoRead + NINC;
            n = (testN <= maxN) ? NINC : maxN - bytesIntoRead;

            if ( n == 0 ) break;

            adpcm_decoder(currentN, sbuf, n*2, &state);
            currentN = test_data + bytesIntoRead + n;
        }
        
    //}
    
    return 0;
}
