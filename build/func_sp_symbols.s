; 函数返回地址FRAM槽位符号（用于调用栈重建）
    .section .text
    .global RET_ADDR__UART_PUTC
    .equ RET_ADDR__UART_PUTC, 0x6520
    .global RET_ADDR__UART_PUTS
    .equ RET_ADDR__UART_PUTS, 0x6522
    .global RET_ADDR_F_MUL
    .equ RET_ADDR_F_MUL, 0x6524
    .global RET_ADDR_MY_MEMCPY
    .equ RET_ADDR_MY_MEMCPY, 0x6526
    .global RET_ADDR_DNN_MAIN
    .equ RET_ADDR_DNN_MAIN, 0x6528
