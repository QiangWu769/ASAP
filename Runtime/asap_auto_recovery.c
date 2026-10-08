// ==================================================================
// ASAP自动恢复 - 使用__attribute__((constructor))
// 这个函数会在main()之前自动执行，不需要修改源码
// ==================================================================

#include <stdint.h>

// 外部符号
extern uint16_t ASAP_WID_SAVE;
extern uint16_t ASAP_PC_SAVE;
extern uint16_t ASAP_SP_SAVE;
extern void _asap_restore(void);

// 使用constructor属性，让这个函数在main之前自动执行
__attribute__((constructor(101)))  // priority 101，在标准初始化之后执行
void __asap_auto_recovery(void)
{
    uint16_t wid = ASAP_WID_SAVE;
    
    // 检查WID有效性
    if (wid > 0 && wid != 0xFFFF && wid < 64) {
        // 需要恢复
        _asap_restore();  // 设置ASAP_PC_SAVE
        
        // 恢复栈和PC（不会返回）
        __asm__ volatile(
            "mov &ASAP_SP_SAVE, r1\n"   // 恢复栈指针
            "mov &ASAP_PC_SAVE, r15\n"  // 读取恢复点地址
            "br r15\n"                   // 跳转到恢复点
        );
    } else {
        // 冷启动
        ASAP_WID_SAVE = 0;
        ASAP_PC_SAVE = 0;
        ASAP_SP_SAVE = 0;
    }
    
    // 如果是冷启动，函数正常返回，继续执行main
}



























