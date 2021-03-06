""" Provides the evaluator backends for Numexpr and the Python interpreter """


from expression_builder import Visitor
import blaze
import math

def evaluate(expression,
             chunk_size,
             vm='python', 
             out_flavor='blaze', 
             user_dict={}, 
             **kwargs):
    """
    evaluate(expression,
             vm=None,
             out_flavor=None,
             chunk_size=None,
             user_dict=None,
             **kwargs)

    Evaluate an `expression` and return the result.

    Parameters
    ----------
    expression : string
        A string forming an expression, like '2*a+3*b'. The values for 'a' and
        'b' are variable names to be taken from the calling function's frame.
        These variables may be scalars, carrays or NumPy arrays.
    vm : string
        The virtual machine to be used in computations.  It can be 'numexpr'
        or 'python'.  The default is to use 'numexpr' if it is installed.
    chunk_size : size of the chunk for chunked evaluation. If None, use some
                 heuristics to infer it.
    out_flavor : string
        The flavor for the `out` object.  It can be 'Blaze' or 'numpy'.
    user_dict : dict
        An user-provided dictionary where the variables in expression
        can be found by name.    
    kwargs : list of parameters or dictionary
        Any parameter supported by the carray constructor.

    Returns
    -------
    out : Blaze object
        The outcome of the expression.  You can tailor the
        properties of this Blaze array by passing additional arguments
        supported by carray constructor in `kwargs`.

    """

    if vm not in ('numexpr', 'python'):
        raiseValue, "`vm` must be either 'numexpr' or 'python'"

    if out_flavor not in ('blaze', 'numpy'):
        raiseValue, "`out_flavor` must be either 'blaze' or 'numpy'"

    # Get variables and column names participating in expression
    vars = user_dict

    # Gather info about sizes and lengths
    typesize, vlen = 0, 1
    for var in vars.itervalues():
        if not hasattr(var, "datashape"):
            # scalar detection
            continue
        else:  # blaze arrays
            shape, dtype = blaze.to_numpy(var.datashape)
            typesize += dtype.itemsize
            lvar = shape[0]
            if vlen > 1 and vlen != lvar:
                raise ValueError, "arrays must have the same length"
            vlen = lvar

    if typesize == 0:
        # All scalars
        if vm == "python":
            return eval(expression, vars)
        else:
            import numexpr
            return numexpr.evaluate(expression, local_dict=vars)

    return _eval_blocks(expression,
                        chunk_size,
                        vars,
                        vlen,
                        typesize,
                        vm,
                        out_flavor,
                        **kwargs)
def _ndims_var(a_var):
    if hasattr(a_var, 'datashape'):
        # a blaze array
        return len(a_var.datashape.shape)
    elif hasattr(a_var, 'shape'):
        # a numpy array
        return len(a_var.shape)
    elif hasattr(a_var, '__get_item__'):
        # neither a blaze nor a numpy array, but indexable: 
        # assume just 1 dimension :-/
        return 1
    else:
        # not indexable: a scalar
        return 0

def _max_ndims_vars(a_dict_of_vars):
    return max([_ndims_var(var) for var in a_dict_of_vars.itervalues()])


class _ResultGatherer(object):
    def __init__(self, vlen, maxndims, flavour):
        self.vlen = vlen
        self.flavour = flavour
        self.maxndims = maxndims
        self.accumulate = self._entry

    def _entry(self, chunk_result, curr_slice):
        self.scalar = False
        self.dim_reduction = False
        l = len(chunk_result.shape)
        if l < self.maxndims:
            self.accumulate = self._reduce
            self.result = (self._scalar_result 
                           if l == 0 
                           else self._array_result)
            self._result = chunk_result
        else:
            if out_flavor == "blaze":
                self._result = blaze.array(chunk_result, **kwargs)
                self.accumulate = self._blaze_append
                self.result = self._array_result
            else:
                out_shape = list(res_block.shape)
                out_shape[0] = self.vlen
                self._result = np.empty(chunk_result,
                                        dtype=chunk_result.dtype)
                self._result[curr_slice] = chunk_result

    def _reduce(self, chunk_result, curr_slice):
        self._result += chunk_result

    def _blaze_append(self, chunk_result, curr_slice):
        self._result.append(chunk_result)

    def _np_append(self, chunk_result, slice_, curr_slice):
        self._result[slice_] = chunk_result

    def _array_result(self):
        return self._result

    def _scalar_result(self):
        return self._result[()]


def _eval_blocks(expression, chunk_size, vars, vlen, typesize, vm, 
                 out_flavor, **kwargs):
    """Perform the evaluation in blocks."""

    if vm == 'python':
        def eval_flavour(expr, vars_):
            return eval(expr, None, vars_)
    else:
        import numexpr
        def eval_flavour(expr, vars_):
            return numexpr.evaluate(expr, local_dict=vars_)

    # Get temporaries for vars
    maxndims = _max_ndims_vars(vars)
    vars_ = { name: var 
              for name, var in vars.iteritems()
              if not hasattr(var, '__getitem__') }

    arrays = [ (name, var)
               for name, var in vars.iteritems()
               if hasattr(var, '__getitem__') ]

    result = _ResultGatherer(vlen, maxndims, out_flavor)
    offset = 0
    while offset < vlen:
        # Get buffers for vars
        curr_slice = slice(offset, min(vlen, offset+chunk_size))
        for name, array in arrays:
            vars_[name] = array[curr_slice]

        # Perform the evaluation for this block
        result.accumulate(eval_flavour(expression, vars_), curr_slice)
        offset = curr_slice.stop #for next iteration
                           
    return result.result()

# End of machinery for evaluating expressions via python or numexpr
# ---------------

class _ExpressionBuilder(Visitor):
    def accept_operation(self, node):
        str_lhs = self.accept(node.lhs)
        str_rhs = self.accept(node.rhs)
        if node.op == "dot":
            # Re-express dot product in terms of a product and an sum()
            return 'sum' + "(" + str_lhs + "*" + str_rhs + ")"
        else:
            return "(" + str_lhs + node.op + str_rhs + ')'

    def accept_terminal(self, node):
        return node.source


# ================================================================ 

class NumexprEvaluator(object):
    """ Evaluates expressions using numexpr """
    name = 'numexpr'

    def __init__(self, root_node, operands=None):
        assert(operands)
        self.str_expr = _ExpressionBuilder().accept(root_node)
        self.operands = operands

    def eval(self, chunk_size=None):
        chunk_size = (chunk_size 
                      if chunk_size is not None 
                      else self._infer_chunksize())
        return evaluate(self.str_expr,
                        chunk_size,
                        vm='numexpr',
                        user_dict=self.operands)
    
    def _infer_chunksize(self):
        typesize = _per_element_size(self.operands)
        vlen = _array_length(self.operands)
        bsize = 2**20
        bsize //= typesize
        bsize = 2 ** (int(math.log(bsize,2)))
        if vlen < 100*1000:
            bsize //= 8
        elif vlen < 1000*1000:
            bsize //= 4
        elif vlen < 10*1000*1000:
            bsize //= 2

        return bsize if bsize > 0 else 1


class NumpyEvaluator(object):
    name = 'python interpreter with numpy'
    def __init__(self, root_node, operands=None):
        assert(operands)
        self.str_expr = _ExpressionBuilder().accept(root_node)
        self.operands = operands

    def eval(self, chunk_size=None):
        chunk_size = (chunk_size 
                      if chunk_size is not None 
                      else self._infer_chunksize())
        return evaluate(self.str_expr, 
                        chunk_size,
                        vm='python',
                        user_dict=self.operands)

    def _infer_chunksize(self):
        """this is somehow similar to the numexpr version, but the
        heuristics are slightly changed as there will be temporaries
        """
        typesize = _per_element_size(self.operands)
        vlen = _array_length(self.operands)
        bsize = 2**17
        bsize //= typesize
        bsize = 2 ** (int(math.log(bsize,2)))
        if vlen < 100*1000:
            bsize //= 8
        elif vlen < 1000*1000:
            bsize //= 4
        elif vlen < 10*1000*1000:
            bsize //= 2

        return bsize if bsize > 0 else 1
