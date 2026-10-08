/* msp430fr_ASAP.ld - ASAP专用链接器脚本 */
/* 入口点设置为bootloader，而不是main */

MEMORY
{
    /* FRAM内存布局 */
    FRAM : ORIGIN = 0x4400, LENGTH = 0xBB80  /* 48KB FRAM */
    RAM  : ORIGIN = 0x1C00, LENGTH = 0x0400  /* 1KB RAM */
    
    /* 中断向量表区域（包含reset vector） */
    RESETVEC : ORIGIN = 0xFFFE, LENGTH = 0x0002  /* Reset Vector 在 0xFFFE */
    
    /* ASAP专用区域 */
    ASAP_METADATA : ORIGIN = 0x4400, LENGTH = 0x1000  /* 4KB元数据区 */
    ASAP_SLOTS    : ORIGIN = 0x5000, LENGTH = 0x2800  /* 10KB槽位区 (扩大以容纳更多slots) */
    ASAP_COMMITS  : ORIGIN = 0x7400, LENGTH = 0x0400  /* 1KB提交位区 (修改到0x7400与fram_layout_symbolic.py一致) */
    
    /* 程序代码区 */
    TEXT : ORIGIN = 0x7800, LENGTH = 0x8800  /* 剩余FRAM用于代码 (调整起始地址避开ASAP区域) */
}

SECTIONS
{
    /* Reset Vector - 必须在地址 0xFFFE */
    ._reset_vector : {
        KEEP(*(.resetvec))
    } > RESETVEC
    
    /* 中断向量表 */
    .intvec : {
        *(.intvec)
    } > FRAM
    
    /* 初始化段 - bootloader在这里 */
    .init9 : {
        *(.init9)
        *bootloader.o(.text)
    } > TEXT
    
    /* 主程序代码 */
    .text : {
        *(.text)
        *(.text.*)
        *main.o(.text)
    } > TEXT
    
    /* 只读数据 */
    .rodata : {
        *(.rodata)
        *(.rodata.*)
        *asap_metadata.o(.rodata)
    } > TEXT
    
    /* 全局变量 */
    .data : {
        *(.data)
        *(.data.*)
    } > RAM AT > TEXT
    
    /* 未初始化变量 */
    .bss : {
        *(.bss)
        *(.bss.*)
        *(COMMON)
    } > RAM
    
    /* ASAP元数据段 */
    .asap_metadata : {
        *asap_metadata.o(.rodata)
    } > ASAP_METADATA
    
    /* ASAP槽位段 */
    .asap_slots : {
        *asap_slots.o(.data)
    } > ASAP_SLOTS
    
    /* ASAP提交位段 */
    .asap_commits : {
        *asap_commit_bits.o(.data)
        *asap_commit_bits.o(.lifecycle)
    } > ASAP_COMMITS
}

/* 入口点设置为bootloader */
ENTRY(_bootloader_entry)

/* 符号定义 */
PROVIDE(_stack = 0x2000);
PROVIDE(_min_stack_size = 0x100);