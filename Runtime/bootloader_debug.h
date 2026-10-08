; Bootloader调试输出宏
; 使用轮询UART输出调试信息

.macro PRINT_STR str
    ; 保存寄存器
    PUSH R12
    PUSH R13
    
    ; 加载字符串地址
    MOV #\str, R13
1:
    MOV.B @R13+, R12
    CMP.B #0, R12
    JEQ 2f
    
    ; 等待UART就绪
3:
    BIT.B #2, &0x05DC
    JZ 3b
    
    ; 发送字符
    MOV.B R12, &0x05CE
    JMP 1b
    
2:
    ; 恢复寄存器
    POP R13
    POP R12
.endm

.macro PRINT_HEX16 reg
    PUSH R12
    PUSH R13
    PUSH R14
    
    MOV \reg, R14
    MOV #4, R13
    
1:
    MOV R14, R12
    SWPB R12
    RRA R12
    RRA R12
    RRA R12
    RRA R12
    AND #0x000F, R12
    
    CMP #10, R12
    JHS 2f
    ADD #'0', R12
    JMP 3f
2:
    ADD #('A'-10), R12
3:
    ; 等待UART
4:
    BIT.B #2, &0x05DC
    JZ 4b
    MOV.B R12, &0x05CE
    
    RLA R14
    RLA R14
    RLA R14
    RLA R14
    DEC R13
    JNZ 1b
    
    POP R14
    POP R13
    POP R12
.endm





































