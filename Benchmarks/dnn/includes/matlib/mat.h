#ifndef MAT_H
#define MAT_H

#include <stdint.h>
#include "includes/fixedlib/fixed.h"

#define MAT_MAX_DIMS 4

typedef struct {
    uint16_t dims[MAT_MAX_DIMS];
    uint16_t len_dims;
    uint16_t strides[MAT_MAX_DIMS];
    fixed *data;
    struct {
        uint16_t dims[MAT_MAX_DIMS];
        uint16_t len_dims;
        uint16_t *offsets;
        uint16_t *sizes;
    } sparse;
} mat_t;

#define MAT_NUMARGS(...) (sizeof((uint16_t[]){__VA_ARGS__}) / sizeof(uint16_t))

#define MAT_RESHAPE(m, ...) \
    (mat_reshape(m, ((uint16_t[]){__VA_ARGS__}), MAT_NUMARGS(__VA_ARGS__)))

#define MAT_CONSTRAIN(m, ...) \
    (mat_constrain(m, ((uint16_t[]){__VA_ARGS__}), MAT_NUMARGS(__VA_ARGS__)))

#define MAT_GET(m, ...) \
    ((MAT_NUMARGS(__VA_ARGS__) == 1) \
        ? *(m->data + ((uint16_t[]){__VA_ARGS__})[0]) \
        : (MAT_NUMARGS(__VA_ARGS__) == 2) \
            ? *(m->data + ((uint16_t[]){__VA_ARGS__})[0] * m->strides[0] + \
                ((uint16_t[]){__VA_ARGS__})[1]) \
            : *(m->data + \
                ((uint16_t[]){__VA_ARGS__})[0] * m->strides[0] + \
                m->strides[1] * ((uint16_t[]){__VA_ARGS__})[1] + \
                ((uint16_t[]){__VA_ARGS__})[2]))

#define MAT_PTR(m, ...) \
    ((MAT_NUMARGS(__VA_ARGS__) == 1) \
        ? (m->data + ((uint16_t[]){__VA_ARGS__})[0]) \
        : (MAT_NUMARGS(__VA_ARGS__) == 2) \
            ? (m->data + ((uint16_t[]){__VA_ARGS__})[0] * m->strides[0] + \
                ((uint16_t[]){__VA_ARGS__})[1]) \
            : (m->data + \
                ((uint16_t[]){__VA_ARGS__})[0] * m->strides[0] + \
                m->strides[1] * ((uint16_t[]){__VA_ARGS__})[1] + \
                ((uint16_t[]){__VA_ARGS__})[2]))

#define MAT_SET(m, val, ...) \
    ((MAT_NUMARGS(__VA_ARGS__) == 1) \
        ? *(m->data + ((uint16_t[]){__VA_ARGS__})[0]) = val \
        : (MAT_NUMARGS(__VA_ARGS__) == 2) \
            ? *(m->data + ((uint16_t[]){__VA_ARGS__})[0] * m->strides[0] + \
                ((uint16_t[]){__VA_ARGS__})[1]) = val \
            : *(m->data + \
                ((uint16_t[]){__VA_ARGS__})[0] * m->strides[0] + \
                m->strides[1] * ((uint16_t[]){__VA_ARGS__})[1] + \
                ((uint16_t[]){__VA_ARGS__})[2]) = val)

#define MAT_GET_DIM(m, axis) ((m)->dims[axis])

void mat_reshape(mat_t *, uint16_t[], uint16_t);
mat_t mat_constrain(mat_t *, uint16_t[], uint16_t);

#endif
