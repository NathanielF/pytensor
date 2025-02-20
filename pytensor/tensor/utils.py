from typing import Sequence, Union

import numpy as np

import pytensor
from pytensor.utils import hash_from_code


def hash_from_ndarray(data):
    """
    Return a hash from an ndarray.

    It takes care of the data, shapes, strides and dtype.

    """
    # We need to hash the shapes and strides as hash_from_code only hashes
    # the data buffer. Otherwise, this will cause problem with shapes like:
    # (1, 0) and (2, 0) and problem with inplace transpose.
    # We also need to add the dtype to make the distinction between
    # uint32 and int32 of zeros with the same shape and strides.

    # python hash are not strong, so use sha256 (md5 is not
    # FIPS compatible). To not have too long of hash, I call it again on
    # the concatenation of all parts.
    if not data.flags["C_CONTIGUOUS"]:
        # hash_from_code needs a C-contiguous array.
        data = np.ascontiguousarray(data)
    return hash_from_code(
        hash_from_code(data)
        + hash_from_code(str(data.shape))
        + hash_from_code(str(data.strides))
        + hash_from_code(str(data.dtype))
    )


def shape_of_variables(fgraph, input_shapes):
    """
    Compute the numeric shape of all intermediate variables given input shapes.

    Parameters
    ----------
    fgraph
        The FunctionGraph in question.
    input_shapes : dict
        A dict mapping input to shape.

    Returns
    -------
    shapes : dict
        A dict mapping variable to shape

    .. warning:: This modifies the fgraph. Not pure.

    Examples
    --------
    >>> import pytensor
    >>> x = pytensor.tensor.matrix('x')
    >>> y = x[512:]; y.name = 'y'
    >>> fgraph = FunctionGraph([x], [y], clone=False)
    >>> d = shape_of_variables(fgraph, {x: (1024, 1024)})
    >>> d[y]
    (array(512), array(1024))
    >>> d[x]
    (array(1024), array(1024))
    """

    if not hasattr(fgraph, "shape_feature"):
        from pytensor.tensor.rewriting.shape import ShapeFeature

        fgraph.attach_feature(ShapeFeature())

    input_dims = [
        dimension
        for inp in fgraph.inputs
        for dimension in fgraph.shape_feature.shape_of[inp]
    ]

    output_dims = [
        dimension
        for shape in fgraph.shape_feature.shape_of.values()
        for dimension in shape
    ]

    compute_shapes = pytensor.function(input_dims, output_dims)

    if any(i not in fgraph.inputs for i in input_shapes.keys()):
        raise ValueError(
            "input_shapes keys aren't in the fgraph.inputs. FunctionGraph()"
            " interface changed. Now by default, it clones the graph it receives."
            " To have the old behavior, give it this new parameter `clone=False`."
        )

    numeric_input_dims = [dim for inp in fgraph.inputs for dim in input_shapes[inp]]
    numeric_output_dims = compute_shapes(*numeric_input_dims)

    sym_to_num_dict = dict(zip(output_dims, numeric_output_dims))

    l = {}
    for var in fgraph.shape_feature.shape_of:
        l[var] = tuple(
            sym_to_num_dict[sym] for sym in fgraph.shape_feature.shape_of[var]
        )
    return l


def as_list(x):
    """Convert x to a list if it is an iterable; otherwise, wrap it in a list."""
    try:
        return list(x)
    except TypeError:
        return [x]


def import_func_from_string(func_string: str):  # -> Optional[Callable]:
    func = getattr(np, func_string, None)
    if func is not None:
        return func

    # Not inside NumPy or Scipy. So probably another package like scipy.
    module = None
    items = func_string.split(".")
    for idx in range(1, len(items)):
        try:
            module = __import__(".".join(items[:idx]))
        except ImportError:
            break

    if module:
        for sub in items[1:]:
            try:
                module = getattr(module, sub)
            except AttributeError:
                module = None
                break
        return module


def broadcast_static_dim_lengths(
    dim_lengths: Sequence[Union[int, None]]
) -> Union[int, None]:
    """Apply static broadcast given static dim length of inputs (obtained from var.type.shape).

    Raises
    ------
    ValueError
        When static dim lengths are incompatible
    """

    dim_lengths_set = set(dim_lengths)
    # All dim_lengths are the same
    if len(dim_lengths_set) == 1:
        return tuple(dim_lengths_set)[0]

    # Only valid indeterminate case
    if dim_lengths_set == {None, 1}:
        return None

    dim_lengths_set.discard(1)
    dim_lengths_set.discard(None)
    if len(dim_lengths_set) > 1:
        raise ValueError
    return tuple(dim_lengths_set)[0]
