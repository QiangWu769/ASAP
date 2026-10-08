#include <stdio.h>

// 函数1：单参数模运算（对固定值取模，例如 10）
int mod_single(int x) {
    return x % 10;
}

// 函数2：双参数模运算（先计算 a%b，然后内部再进行一次自定义模运算）
int mod_double(int a, int b) {
    int result = a % b;        // 第一次模运算
    result = result % 3;       // 第二次模运算（内部再取一次模3）
    return result;
}

int main(void) {
    int x = 27;
    int a = 35, b = 6;

    int single_result = mod_single(x);
    int double_result = mod_double(a, b);

    printf("mod_single(%d) = %d\n", x, single_result);
    printf("mod_double(%d, %d) = %d\n", a, b, double_result);

    return 0;
}