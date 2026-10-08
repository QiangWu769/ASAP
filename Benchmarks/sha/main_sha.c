/* NIST Secure Hash Algorithm - MSP430 ASAP 版本 */
/* 原始来源: MiBench2 benchmark suite (sha) */
/* heavily modified by Uwe Hollerbach uh@alumni.caltech edu */
/* from Peter C. Gutmann's implementation as found in */
/* Applied Cryptography by Bruce Schneier */

#include <msp430.h>
#include <stdint.h>
#include <string.h>

// 使用本地简化版libio
#include "libio/printf.h"

// 简单的BITSET宏
#define BITSET(port, val) ((port) |= (val))

// TIMER配置：0=正常运行，1=定时器模拟断电
#ifndef TIMER
#define TIMER 1
#endif

/*===========================================================================
 * SHA 类型定义和常量
 *===========================================================================*/

typedef unsigned char BYTE;
typedef unsigned long LONG;

#define SHA_BLOCKSIZE   64
#define SHA_DIGESTSIZE  20

typedef struct {
    LONG digest[5];         /* message digest */
    LONG count_lo, count_hi; /* 64-bit bit count */
    LONG data[16];          /* SHA data buffer */
} SHA_INFO;

/* SHA f()-functions */
#define f1(x,y,z)   ((x & y) | (~x & z))
#define f2(x,y,z)   (x ^ y ^ z)
#define f3(x,y,z)   ((x & y) | (x & z) | (y & z))
#define f4(x,y,z)   (x ^ y ^ z)

/* SHA constants */
#define CONST1      0x5a827999L
#define CONST2      0x6ed9eba1L
#define CONST3      0x8f1bbcdcL
#define CONST4      0xca62c1d6L

/* 32-bit rotate */
#define ROT32(x,n)  ((x << n) | (x >> (32 - n)))

/* 注意：MSP430头文件定义了C,D,E等宏，需要使用不同的变量名 */
#define FUNC(n,i)                                       \
    temp = ROT32(sA,5) + f##n(sB,sC,sD) + sE + W[i] + CONST##n;  \
    sE = sD; sD = sC; sC = ROT32(sB,30); sB = sA; sA = temp

/*===========================================================================
 * 测试输入数据（精简版，用于嵌入式测试）
 *===========================================================================*/

// 测试字符串 - 经典SHA测试向量
static const char test_input_1[] = "abc";
static const char test_input_2[] = "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
static const char test_input_3[] = "The quick brown fox jumps over the lazy dog";

// 当前使用的测试输入
#define TEST_INPUT test_input_3
#define TEST_INPUT_LEN (sizeof(test_input_3) - 1)

// 分块处理大小（每次处理的字节数）
#define BLOCK_SIZE  64

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

__attribute__((noinline, used, noclone))
void init(void)
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
    BITSET(TBCTL, (TBSSEL_2 | ID_0 | MC_2 | TBCLR));  // SMCLK, /1, continuous mode
    BITSET(TBCCTL1, CCIE);   // 使能CCR1中断
#ifndef TIMER_VALUE
#define TIMER_VALUE 40000  // 默认值：约5ms @8MHz
#endif
    TBCCR1 = TIMER_VALUE;  // 设置比较值
#endif
    
    // 9. 使能中断
    __enable_interrupt();
}

/*===========================================================================
 * SHA 核心算法实现
 *===========================================================================*/

/* do SHA transformation */
static void sha_transform(SHA_INFO *sha_info)
{
    int i;
    LONG temp, sA, sB, sC, sD, sE, W[80];

    for (i = 0; i < 16; ++i) {
        W[i] = sha_info->data[i];
    }
    for (i = 16; i < 80; ++i) {
        W[i] = W[i-3] ^ W[i-8] ^ W[i-14] ^ W[i-16];
        /* USE_MODIFIED_SHA would add: W[i] = ROT32(W[i], 1); */
    }
    sA = sha_info->digest[0];
    sB = sha_info->digest[1];
    sC = sha_info->digest[2];
    sD = sha_info->digest[3];
    sE = sha_info->digest[4];
    
    for (i = 0; i < 20; ++i) {
        FUNC(1,i);
    }
    for (i = 20; i < 40; ++i) {
        FUNC(2,i);
    }
    for (i = 40; i < 60; ++i) {
        FUNC(3,i);
    }
    for (i = 60; i < 80; ++i) {
        FUNC(4,i);
    }
    
    sha_info->digest[0] += sA;
    sha_info->digest[1] += sB;
    sha_info->digest[2] += sC;
    sha_info->digest[3] += sD;
    sha_info->digest[4] += sE;
}

/* change endianness of data (little endian to big endian) */
static void byte_reverse(LONG *buffer, int count)
{
    int i;
    BYTE ct[4], *cp;

    count /= sizeof(LONG);
    cp = (BYTE *) buffer;
    for (i = 0; i < count; ++i) {
        ct[0] = cp[0];
        ct[1] = cp[1];
        ct[2] = cp[2];
        ct[3] = cp[3];
        cp[0] = ct[3];
        cp[1] = ct[2];
        cp[2] = ct[1];
        cp[3] = ct[0];
        cp += sizeof(LONG);
    }
}

/* initialize the SHA digest */
__attribute__((noinline))
void sha_init(SHA_INFO *sha_info)
{
    sha_info->digest[0] = 0x67452301L;
    sha_info->digest[1] = 0xefcdab89L;
    sha_info->digest[2] = 0x98badcfeL;
    sha_info->digest[3] = 0x10325476L;
    sha_info->digest[4] = 0xc3d2e1f0L;
    sha_info->count_lo = 0L;
    sha_info->count_hi = 0L;
}

/* update the SHA digest */
__attribute__((noinline))
void sha_update(SHA_INFO *sha_info, const BYTE *buffer, int count)
{
    if ((sha_info->count_lo + ((LONG) count << 3)) < sha_info->count_lo) {
        ++sha_info->count_hi;
    }
    sha_info->count_lo += (LONG) count << 3;
    sha_info->count_hi += (LONG) count >> 29;
    
    while (count >= SHA_BLOCKSIZE) {
        memcpy(sha_info->data, buffer, SHA_BLOCKSIZE);
        byte_reverse(sha_info->data, SHA_BLOCKSIZE);
        sha_transform(sha_info);
        buffer += SHA_BLOCKSIZE;
        count -= SHA_BLOCKSIZE;
    }
    memcpy(sha_info->data, buffer, count);
}

/* finish computing the SHA digest */
__attribute__((noinline))
void sha_final(SHA_INFO *sha_info)
{
    int count;
    LONG lo_bit_count, hi_bit_count;

    lo_bit_count = sha_info->count_lo;
    hi_bit_count = sha_info->count_hi;
    count = (int) ((lo_bit_count >> 3) & 0x3f);
    ((BYTE *) sha_info->data)[count++] = 0x80;
    if (count > 56) {
        memset((BYTE *) sha_info->data + count, 0, 64 - count);
        byte_reverse(sha_info->data, SHA_BLOCKSIZE);
        sha_transform(sha_info);
        memset(sha_info->data, 0, 56);
    } else {
        memset((BYTE *) sha_info->data + count, 0, 56 - count);
    }
    byte_reverse(sha_info->data, SHA_BLOCKSIZE);
    sha_info->data[14] = hi_bit_count;
    sha_info->data[15] = lo_bit_count;
    sha_transform(sha_info);
}

/* print a SHA digest */
static void sha_print(SHA_INFO *sha_info)
{
    _uart_print_hex(sha_info->digest[0]);
    _uart_putc(' ');
    _uart_print_hex(sha_info->digest[1]);
    _uart_putc(' ');
    _uart_print_hex(sha_info->digest[2]);
    _uart_putc(' ');
    _uart_print_hex(sha_info->digest[3]);
    _uart_putc(' ');
    _uart_print_hex(sha_info->digest[4]);
    _uart_puts("\r\n");
}

/*===========================================================================
 * 主函数
 *===========================================================================*/

int main(void)
{
    init();

    SHA_INFO sha_info;
    const BYTE *current_ptr;
    int remaining;
    int chunk_size;
    
    while (1) {
        // 初始化SHA状态
        sha_init(&sha_info);
        
        _uart_puts("SHA-1 Input: \"");
        _uart_puts(TEST_INPUT);
        _uart_puts("\"\r\n");
        
        // 设置输入指针
        current_ptr = (const BYTE *)TEST_INPUT;
        remaining = TEST_INPUT_LEN;
        
        // 分块处理输入数据（类似adpcm_encode的分块模式）
        while (remaining > 0) {
            // 计算本次处理的块大小
            chunk_size = (remaining > BLOCK_SIZE) ? BLOCK_SIZE : remaining;
            
            // 更新SHA摘要
            sha_update(&sha_info, current_ptr, chunk_size);
            
            // 更新指针和剩余计数
            current_ptr += chunk_size;
            remaining -= chunk_size;
        }
        
        // 完成SHA计算
        sha_final(&sha_info);
        
        // 输出结果
        _uart_puts("SHA-1 Digest: ");
        sha_print(&sha_info);
        
        // P1.2 低脉冲（一轮完成标志）
        P1OUT &= ~BIT2;
        __delay_cycles(8000);  // 1ms @ 8MHz
        P1OUT |= BIT2;
    }
    
    return 0;
}
