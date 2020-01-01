import os
import tempfile

from dmoj.error import CompileError, InternalError
from dmoj.result import Result
from dmoj.utils.os_ext import strsignal


def mktemp(data):
    tmp = tempfile.NamedTemporaryFile()
    tmp.write(data or b'')
    tmp.flush()
    return tmp


def compile_with_auxiliary_files(filenames, lang=None, compiler_time_limit=None):
    from dmoj.executors import executors
    from dmoj.executors.compiled_executor import CompiledExecutor

    sources = {}

    for filename in filenames:
        with open(filename, 'rb') as f:
            sources[os.path.basename(filename)] = f.read()

    def find_runtime(languages):
        for grader in languages:
            if grader in executors:
                return grader
        return None

    use_cpp = any(map(lambda name: os.path.splitext(name)[1] in ['.cpp', '.cc'], filenames))
    use_c = any(map(lambda name: os.path.splitext(name)[1] in ['.c'], filenames))
    if lang is None:
        best_choices = ('CPP17', 'CPP14', 'CPP11', 'CPP03') if use_cpp else ('C11', 'C')
        lang = find_runtime(best_choices)

    executor = executors.get(lang)
    if not executor:
        raise IOError('could not find an appropriate C++ executor')

    executor = executor.Executor

    fs = executor.fs + [tempfile.gettempdir()]
    executor = type('Executor', (executor,), {'fs': fs})

    if issubclass(executor, CompiledExecutor):
        executor = type('Executor', (executor,), {'compiler_time_limit': compiler_time_limit})

    try:
        # Optimize the common case.
        if use_cpp or use_c:
            # Some auxiliary files take an extremely long time to compile, so we cache them.
            executor = executor('_aux_file', None, aux_sources=sources, cached=True)
        else:
            if len(sources) > 1:
                raise InternalError('non-C/C++ auxiliary programs cannot be multi-file')
            executor = executor('_aux_file', list(sources.values())[0])
    except CompileError as err:
        raise InternalError('Failed to compile auxiliary program with error %s' % err)

    return executor


def check_aux_file_error(proc, executor, name, stderr, time_limit, memory_limit):
    if proc.tle:
        error = '%s timed out (> %d seconds)' % (name, time_limit)
    elif proc.mle:
        error = '%s ran out of memory (> %s Kb)' % (name, memory_limit)
    elif proc.protection_fault:
        syscall, callname, args = proc.protection_fault
        error = '%s invoked disallowed syscall %s (%s)' % (name, syscall, callname)
    elif proc.returncode:
        if proc.returncode > 0:
            error = '%s exited with nonzero code %d' % (name, proc.returncode)
        else:
            error = '%s exited with %s' % (name, strsignal(proc.signal))
        # To get the feedback, we need a Result object, but we lack a Case object
        # So we set it to None because we don't need to access it
        result = Result(None)
        result.set_result_flag(proc)
        result.update_feedback(stderr, proc, executor)
        if result.feedback:
            error += ' with feedback %s' % result.feedback
    else:
        return

    raise InternalError(error)
