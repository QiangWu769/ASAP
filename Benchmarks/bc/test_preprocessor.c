#include <stdio.h>

// 模拟 libio/printf.h 的逻辑
#if defined(USE_REAL_PRINTF)
    #define MYPRINTF(...) printf(__VA_ARGS__)
#else
    #define MYPRINTF(...)  // 空定义
#endif

int main() {
    MYPRINTF("This is a test\n");
    return 0;
}





































