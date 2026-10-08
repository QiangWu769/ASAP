#include <msp430.h>

void bootloader_entry() __attribute__((section(".init9")));

void bootloader_entry() {
    // 1. Unlock GPIO
    PM5CTL0 &= ~LOCKLPM5;
    
    // 2. Init Stack
    __asm__("mov #0x2400, r1");
    
    // 3. Set LED direction and turn ON
    P1DIR |= BIT0;  // 绿灯输出
    P1OUT |= BIT0;  // 绿灯亮
    
    // 4. Dead loop - LED should stay ON
    while(1);
}

