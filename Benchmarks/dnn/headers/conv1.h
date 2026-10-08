#ifndef CONV1_H
#define CONV1_H
#include "includes/fixedlib/fixed.h"

const fixed conv1_wmd[2] = {
    F_LIT(0.5514001), F_LIT(-0.6771312)
};

const fixed conv1_wmh[10] = {
    F_LIT(0.42195162),  F_LIT(0.607521),    F_LIT(0.7214888),
    F_LIT(0.7699961),   F_LIT(0.5149403),   F_LIT(0.73833525),
    F_LIT(0.7471793),   F_LIT(0.62391305),  F_LIT(0.4999502),
    F_LIT(0.30073732)
};

const fixed conv1_wmv[10] = {
    F_LIT(0.09034854),  F_LIT(0.7444282),   F_LIT(0.73090804),
    F_LIT(-0.027014952),F_LIT(-0.72026634), F_LIT(-0.6302),
    F_LIT(-0.59967935), F_LIT(-0.15395786), F_LIT(0.48952276),
    F_LIT(0.6799719)
};

const fixed conv1_b[2] = {
    F_LIT(-5.98718688707e-05), F_LIT(0.0763346850872)
};

#endif
