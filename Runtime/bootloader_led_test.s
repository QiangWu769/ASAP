; 最简单的LED闪烁测试 - 验证bootloader是否执行
    .arch msp430x
    .cpu msp430x
    
    .global bootloader_entry
    
    .section .bootloader, "ax"

bootloader_entry:
    ; 初始化栈
    MOV.W #0x2400, R1
    
    ; 禁用看门狗
    MOV.W #0x5A80, &0x015C
    
    ; 配置P1.0为输出（LED）
    BIS.B #0x01, &0x0204          ; P1DIR |= BIT0
    
    ; 解锁GPIO
    BIC.W #0x0001, &0x0130        ; PM5CTL0 &= ~LOCKLPM5
    
    ; 死循环闪烁LED
led_loop:
    XOR.B #0x01, &0x0202          ; P1OUT ^= BIT0 (翻转LED)
    
    ; 延时
    MOV.W #0xFFFF, R15
delay:
    DEC.W R15
    JNZ delay
    
    JMP led_loop

    .section .resetvec, "a"
    .word bootloader_entry
