"""Run the separately installed Piper CLI with bounded ONNX worker threads."""
import runpy
import onnxruntime

_original = onnxruntime.SessionOptions

def bounded_options():
    options = _original()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    return options

onnxruntime.SessionOptions = bounded_options
runpy.run_module('piper', run_name='__main__')
