#ifndef LIBIO_PRINTF_H
#define LIBIO_PRINTF_H

/* Simplified - no complex conditionals */
#include <msp430.h>

/* Simple UART output functions */
static inline void _uart_putc(char c)
{
	while (!(UCA0IFG & UCTXIFG));
	UCA0TXBUF = c;
}

static inline void _uart_puts(const char *s)
{
	while (*s) _uart_putc(*s++);
}

static inline void _uart_print_uint(unsigned int n)
{
	char buf[11];
	int i = 0;
	
	if (n == 0) {
		_uart_putc('0');
		return;
	}
	
	while (n > 0) {
		buf[i++] = '0' + (n % 10);
		n /= 10;
	}
	
	while (i > 0) _uart_putc(buf[--i]);
}

/* Print hex value (for SHA digest output) */
static inline void _uart_print_hex(unsigned long n)
{
	const char hex[] = "0123456789abcdef";
	int i;
	for (i = 7; i >= 0; i--) {
		_uart_putc(hex[(n >> (i * 4)) & 0xF]);
	}
}

#endif // LIBIO_PRINTF_H























