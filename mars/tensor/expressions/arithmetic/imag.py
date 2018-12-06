#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 1999-2018 Alibaba Group Holding Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import numpy as np

from .... import operands
from ..utils import infer_dtype
from .core import TensorUnaryOp


class TensorImag(operands.Imag, TensorUnaryOp):
    def __init__(self, casting='same_kind', err=None, dtype=None, sparse=False, **kw):
        err = err if err is not None else np.geterr()
        super(TensorImag, self).__init__(_casting=casting, _err=err,
                                         _dtype=dtype, _sparse=sparse, **kw)

    @classmethod
    def _is_sparse(cls, x):
        return x.issparse()


@infer_dtype(np.imag)
def imag(val, **kwargs):
    """
    Return the imaginary part of the complex argument.

    Parameters
    ----------
    val : array_like
        Input tensor.

    Returns
    -------
    out : Tensor or scalar
        The imaginary component of the complex argument. If `val` is real,
        the type of `val` is used for the output.  If `val` has complex
        elements, the returned type is float.

    See Also
    --------
    real, angle, real_if_close

    Examples
    --------
    >>> import mars.tensor as mt

    >>> a = mt.array([1+2j, 3+4j, 5+6j])
    >>> a.imag.execute()
    array([ 2.,  4.,  6.])
    >>> a.imag = mt.array([8, 10, 12])
    >>> a.execute()
    array([ 1. +8.j,  3.+10.j,  5.+12.j])
    >>> mt.imag(1 + 1j).execute()
    1.0

    """
    op = TensorImag(**kwargs)
    return op(val)
