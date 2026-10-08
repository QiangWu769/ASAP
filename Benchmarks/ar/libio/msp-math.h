#ifndef _MSPMATH_H
#define _MSPMATH_H

#include <stdint.h>

// Simple integer square root using Newton's method
static inline uint16_t sqrt16(uint32_t x)
{
	if (x == 0) return 0;
	if (x == 1) return 1;
	
	uint32_t guess = x >> 1;
	uint32_t prev;
	
	// Newton iteration: guess = (guess + x/guess) / 2
	for (int i = 0; i < 10; i++) {
		prev = guess;
		guess = (guess + x / guess) >> 1;
		if (guess == prev) break;
	}
	
	return (uint16_t)guess;
}

static inline uint32_t mult16(uint16_t a, uint16_t b)
{
	return (uint32_t)a * (uint32_t)b;
}

#endif // _MSPMATH_H
