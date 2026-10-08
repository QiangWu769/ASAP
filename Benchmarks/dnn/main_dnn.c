#include <msp430.h>
#include <stdint.h>
#include <string.h>

#include "libio/log.h"
#include "includes/fixedlib/fixed.h"

#include "headers/conv1.h"
#include "headers/conv2.h"
#include "headers/fc1.h"
#include "headers/fc2.h"
#include "headers/input.h"

#define BITSET(port, val) ((port) |= (val))

static void *my_memcpy(void *dst0, const void *src0, size_t len0) {
    char *dst = (char *)dst0;
    const char *src = (const char *)src0;
    while (len0--)
        *dst++ = *src++;
    return dst0;
}

#ifndef TIMER
#define TIMER 1
#endif

#ifndef TIMER_VALUE
#define TIMER_VALUE 40
#endif

#ifndef LOOP_IDX
#define LOOP_IDX 1
#endif

#define BUF_SIZE 1600

__attribute__((section(".persistent"))) fixed buf1[BUF_SIZE];
__attribute__((section(".persistent"))) fixed buf2[BUF_SIZE];

void init(void) {
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
    UCA0MCTLW = UCOS16 | UCBRF_5 | (0x55 << 8);

    P2SEL1 |= BIT0 | BIT1;
    P2SEL0 &= ~(BIT0 | BIT1);

    UCA0CTLW0 &= ~UCSWRST;

#if TIMER == 1
    BITSET(TBCTL, (TBSSEL_1 | ID_3 | MC_2 | TBCLR));
    BITSET(TBCCTL1, CCIE);
    TBCCR1 = TIMER_VALUE;
#endif

    __enable_interrupt();
}

static void dnn_main(void) {
    uint16_t fi, r, c, i;
    fixed f, val, max;

    my_memcpy(buf2, input, 784 * sizeof(fixed));

    /* Conv1_D: buf2[1x28x28] -> buf1[2x28x28] */
    for (fi = 0; fi < 2; fi++) {
        f = conv1_wmd[fi];
        for (i = 0; i < 784; i++)
            buf1[fi * 784 + i] = F_MUL(f, buf2[i]);
    }

    /* Conv1_H: buf1[2x28x28] -> buf2[2x28x24] */
    for (fi = 0; fi < 2; fi++) {
        uint16_t src_off = fi * 784;
        uint16_t out_base = fi * 672;
        for (i = 0; i < 672; i++)
            buf2[out_base + i] = 0;
        for (uint16_t fn = 0; fn < 5; fn++) {
            f = conv1_wmh[fi * 5 + fn];
            uint16_t di = 0;
            for (r = 0; r < 28; r++)
                for (c = 0; c < 24; c++) {
                    buf2[out_base + di] += F_MUL(f, buf1[src_off + r * 28 + fn + c]);
                    di++;
                }
        }
    }

    /* Conv1_V + bias: buf2[2x28x24] -> buf1[2x24x24] */
    for (fi = 0; fi < 2; fi++) {
        uint16_t src_off = fi * 672;
        uint16_t out_base = fi * 576;
        for (i = 0; i < 576; i++)
            buf1[out_base + i] = 0;
        for (uint16_t fl = 0; fl < 5; fl++) {
            f = conv1_wmv[fi * 5 + fl];
            uint16_t di = 0;
            for (r = 0; r < 24; r++)
                for (c = 0; c < 24; c++) {
                    buf1[out_base + di] += F_MUL(f, buf2[src_off + (r + fl) * 24 + c]);
                    di++;
                }
        }
        f = conv1_b[fi];
        for (i = 0; i < 576; i++)
            buf1[out_base + i] += f;
    }

    /* ReLU */
    for (i = 0; i < 1152; i++)
        buf2[i] = (buf1[i] < 0) ? 0 : buf1[i];

    /* Pool 2x2: buf2[2x24x24] -> buf1[2x12x12] */
    for (fi = 0; fi < 2; fi++) {
        uint16_t sbase = fi * 576;
        uint16_t dbase = fi * 144;
        for (r = 0; r < 24; r += 2)
            for (c = 0; c < 24; c += 2) {
                max = buf2[sbase + r * 24 + c];
                val = buf2[sbase + r * 24 + c + 1];       if (val > max) max = val;
                val = buf2[sbase + (r+1) * 24 + c];       if (val > max) max = val;
                val = buf2[sbase + (r+1) * 24 + c + 1];   if (val > max) max = val;
                buf1[dbase + (r/2) * 12 + c/2] = max;
            }
    }

    /* Conv2 + bias: buf1[2x12x12] -> buf2[4x8x8] */
    for (fi = 0; fi < 4; fi++) {
        uint16_t out_base = fi * 64;
        for (i = 0; i < 64; i++)
            buf2[out_base + i] = 0;
        for (uint16_t kk = 0; kk < 2; kk++)
            for (uint16_t lr = 0; lr < 5; lr++)
                for (uint16_t nc = 0; nc < 5; nc++) {
                    f = conv2_w[fi * 50 + kk * 25 + lr * 5 + nc];
                    uint16_t di = 0;
                    for (r = 0; r < 8; r++)
                        for (c = 0; c < 8; c++) {
                            buf2[out_base + di] += F_MUL(f, buf1[kk * 144 + (r+lr) * 12 + nc + c]);
                            di++;
                        }
                }
        f = conv2_b[fi];
        for (i = 0; i < 64; i++)
            buf2[out_base + i] += f;
    }

    /* ReLU */
    for (i = 0; i < 256; i++)
        buf1[i] = (buf2[i] < 0) ? 0 : buf2[i];

    /* Pool 2x2: buf1[4x8x8] -> buf2[4x4x4] */
    for (fi = 0; fi < 4; fi++) {
        uint16_t sbase = fi * 64;
        uint16_t dbase = fi * 16;
        for (r = 0; r < 8; r += 2)
            for (c = 0; c < 8; c += 2) {
                max = buf1[sbase + r * 8 + c];
                val = buf1[sbase + r * 8 + c + 1];       if (val > max) max = val;
                val = buf1[sbase + (r+1) * 8 + c];       if (val > max) max = val;
                val = buf1[sbase + (r+1) * 8 + c + 1];   if (val > max) max = val;
                buf2[dbase + (r/2) * 4 + c/2] = max;
            }
    }

    /* FC1: buf2[64] -> buf1[16] */
    for (i = 0; i < 16; i++) {
        buf1[i] = fc1_b[i];
        for (uint16_t j = 0; j < 64; j++)
            buf1[i] += F_MUL(fc1_w[i * 64 + j], buf2[j]);
    }

    /* ReLU */
    for (i = 0; i < 16; i++)
        buf2[i] = (buf1[i] < 0) ? 0 : buf1[i];

    /* FC2: buf2[16] -> buf1[10] */
    for (i = 0; i < 10; i++) {
        buf1[i] = fc2_b[i];
        for (uint16_t j = 0; j < 16; j++)
            buf1[i] += F_MUL(fc2_w[i * 16 + j], buf2[j]);
    }

    /* Prediction */
    uint16_t predict = 0;
    max = 0;
    for (i = 0; i < 10; i++) {
        if (buf1[i] > max) { predict = i; max = buf1[i]; }
    }
}

unsigned count = 0;

int main(void) {
    init();

    while (1) {
        for (unsigned cnt = 0; cnt < LOOP_IDX; cnt++) {
            if (count == 0) {
                PRINTF("start\r\n");
            }

            dnn_main();

            P1OUT &= ~BIT2;
            __delay_cycles(8000);
            P1OUT |= BIT2;

            count++;
        }
    }

    return 0;
}

#if TIMER == 1
void __attribute__((interrupt(TIMER0_B1_VECTOR))) Timer_B1_ISR(void) {
    TBCCTL1 &= ~CCIFG;
    TBCCR1 += TIMER_VALUE;
    PMMCTL0 = PMMPW | PMMSWBOR;
}
#endif
