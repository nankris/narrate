"""Narrate: gap-constrained English and Hindi audio description."""

import os
# Bound native worker pools on the shared CPU host.
for _name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[_name] = '2'
