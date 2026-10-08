#ifndef FC2_H
#define FC2_H
#include "includes/fixedlib/fixed.h"

/* FC2: 16 inputs -> 10 outputs = 160 weights */
const fixed fc2_w[160] = {
    F_LIT(0.15), F_LIT(-0.22), F_LIT(0.31), F_LIT(-0.18), F_LIT(0.25),
    F_LIT(-0.12), F_LIT(0.33), F_LIT(-0.28), F_LIT(0.19), F_LIT(-0.14),
    F_LIT(0.27), F_LIT(-0.21), F_LIT(0.35), F_LIT(-0.16), F_LIT(0.23),
    F_LIT(-0.29),
    F_LIT(-0.15), F_LIT(0.22), F_LIT(-0.31), F_LIT(0.18), F_LIT(-0.25),
    F_LIT(0.12), F_LIT(-0.33), F_LIT(0.28), F_LIT(-0.19), F_LIT(0.14),
    F_LIT(-0.27), F_LIT(0.21), F_LIT(-0.35), F_LIT(0.16), F_LIT(-0.23),
    F_LIT(0.29),
    F_LIT(0.20), F_LIT(-0.15), F_LIT(0.28), F_LIT(-0.22), F_LIT(0.33),
    F_LIT(-0.11), F_LIT(0.25), F_LIT(-0.30), F_LIT(0.18), F_LIT(-0.24),
    F_LIT(0.31), F_LIT(-0.16), F_LIT(0.27), F_LIT(-0.21), F_LIT(0.35),
    F_LIT(-0.13),
    F_LIT(0.35), F_LIT(-0.10), F_LIT(0.25), F_LIT(-0.30), F_LIT(0.18),
    F_LIT(-0.24), F_LIT(0.31), F_LIT(-0.16), F_LIT(0.27), F_LIT(-0.21),
    F_LIT(0.33), F_LIT(-0.13), F_LIT(0.23), F_LIT(-0.29), F_LIT(0.17),
    F_LIT(-0.26),
    F_LIT(-0.20), F_LIT(0.15), F_LIT(-0.28), F_LIT(0.22), F_LIT(-0.33),
    F_LIT(0.11), F_LIT(-0.25), F_LIT(0.30), F_LIT(-0.18), F_LIT(0.24),
    F_LIT(-0.31), F_LIT(0.16), F_LIT(-0.27), F_LIT(0.21), F_LIT(-0.35),
    F_LIT(0.13),
    F_LIT(0.12), F_LIT(-0.25), F_LIT(0.30), F_LIT(-0.18), F_LIT(0.24),
    F_LIT(-0.31), F_LIT(0.16), F_LIT(-0.27), F_LIT(0.21), F_LIT(-0.35),
    F_LIT(0.13), F_LIT(-0.23), F_LIT(0.29), F_LIT(-0.17), F_LIT(0.26),
    F_LIT(-0.32),
    F_LIT(-0.18), F_LIT(0.24), F_LIT(-0.31), F_LIT(0.16), F_LIT(-0.27),
    F_LIT(0.21), F_LIT(-0.35), F_LIT(0.13), F_LIT(-0.23), F_LIT(0.29),
    F_LIT(-0.17), F_LIT(0.26), F_LIT(-0.32), F_LIT(0.14), F_LIT(-0.22),
    F_LIT(0.19),
    F_LIT(0.24), F_LIT(-0.31), F_LIT(0.16), F_LIT(-0.27), F_LIT(0.21),
    F_LIT(-0.35), F_LIT(0.13), F_LIT(-0.23), F_LIT(0.29), F_LIT(-0.17),
    F_LIT(0.26), F_LIT(-0.32), F_LIT(0.14), F_LIT(-0.22), F_LIT(0.19),
    F_LIT(-0.34),
    F_LIT(-0.24), F_LIT(0.31), F_LIT(-0.16), F_LIT(0.27), F_LIT(-0.21),
    F_LIT(0.35), F_LIT(-0.13), F_LIT(0.23), F_LIT(-0.29), F_LIT(0.17),
    F_LIT(-0.26), F_LIT(0.32), F_LIT(-0.14), F_LIT(0.22), F_LIT(-0.19),
    F_LIT(0.34),
    F_LIT(0.30), F_LIT(-0.17), F_LIT(0.24), F_LIT(-0.33), F_LIT(0.11),
    F_LIT(-0.22), F_LIT(0.29), F_LIT(-0.18), F_LIT(0.26), F_LIT(-0.31),
    F_LIT(0.16), F_LIT(-0.27), F_LIT(0.21), F_LIT(-0.35), F_LIT(0.13),
    F_LIT(-0.23)
};

const fixed fc2_b[10] = {
    F_LIT(0.01), F_LIT(-0.02), F_LIT(0.03), F_LIT(-0.01), F_LIT(0.02),
    F_LIT(-0.03), F_LIT(0.01), F_LIT(-0.02), F_LIT(0.03), F_LIT(-0.01)
};

#endif
