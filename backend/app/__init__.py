"""Snappsense API package."""

import os

# Native maths libraries (OpenMP/OpenBLAS/MKL) default to one thread per host
# core. On small cloud instances (e.g. 0.1 vCPU) that oversubscription makes
# analysis many times slower, so pin them to one thread before numpy loads.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "1")
