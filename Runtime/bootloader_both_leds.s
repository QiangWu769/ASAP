; 双LED闪烁测试 - 同时闪烁P1.0(红)和P4.6(绿)
    .arch msp430x
    .cpu msp430x
    
    .global bootloader_entry
    
    .section .bootloader, "ax"

bootloader_entry:
    ; 初始化栈
    MOV.W #0x2400, R1
    
    ; 禁用看门狗
    MOV.W #0x5A80, &0x015C
    
    ; 配置P1.0为输出（红色LED）
    BIS.B #0x01, &0x0204          ; P1DIR |= BIT0
    
    ; 配置P4.6为输出（绿色LED）
    BIS.B #0x40, &0x0225          ; P4DIR |= BIT6
    
    ; 解锁GPIO
    BIC.W #0x0001, &0x0130        ; PM5CTL0 &= ~LOCKLPM5
    
    ; 先全部点亮2秒（验证两个LED都工作）
    BIS.B #0x01, &0x0202          ; P1OUT |= BIT0 (红灯亮)
    BIS.B #0x40, &0x0223          ; P4OUT |= BIT6 (绿灯亮)
    
    ; 长延时（约2秒）
    MOV.W #0x08, R14
long_delay:
    MOV.W #0xFFFF, R15
delay1:
    DEC.W R15
    JNZ delay1
    DEC.W R14
    JNZ long_delay
    
    ; 然后开始交替闪烁
led_loop:
    ; 红灯亮，绿灯灭
    BIS.B #0x01, &0x0202          ; P1OUT |= BIT0
    BIC.B #0x40, &0x0223          ; P4OUT &= ~BIT6
    
    ; 延时
    MOV.W #0xFFFF, R15
delay2:
    DEC.W R15
    JNZ delay2
    
    ; 红灯灭，绿灯亮
    BIC.B #0x01, &0x0202          ; P1OUT &= ~BIT0
    BIS.B #0x40, &0x0223          ; P4OUT |= BIT6
    
    ; 延时
    MOV.W #0xFFFF, R15
delay3:
    DEC.W R15
    JNZ delay3
    
    JMP led_loop

    .section .resetvec, "a"
    .word bootloader_entry
