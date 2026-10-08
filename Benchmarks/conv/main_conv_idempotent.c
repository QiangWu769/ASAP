#include <msp430.h>
#include <stdio.h>

#define PRINTF printf
#define TIMER 0
#define LOOP_IDX 0

void init() {
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
}

#define N 500
#define K 20

unsigned vec[N];
const unsigned kernel[K] = {
	1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
	1, 1, 1, 1, 1, 1, 1, 1, 1, 1
};
unsigned out[N-K+1];

int main()
{
	init();

	while (1) {
		// Initialize input vector
		for (unsigned i = 0; i < N; ++i)
			vec[i] = i;

		// Initialize output array
		for (unsigned i = 0; i < N-K+1; ++i)
			out[i] = 0;

		// Convolution: 幂等版本
		for (unsigned i = 0; i < N-K+1; ++i) {
			unsigned temp = 0;
			for (unsigned j = 0; j < K; ++j)
				temp += vec[i+j] * kernel[K-(j+1)];
			out[i] = temp;
		}
	}

	return 0;
}





