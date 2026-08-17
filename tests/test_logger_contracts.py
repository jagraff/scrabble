"""Loggers must survive the calls their callees actually make.

`tier3` passed `log=lambda *x: None` to `refute_parallel`, which logs its
per-depth progress with `flush=True`. A positional-only lambda raises
TypeError on the first such call, and that crash landed at the end of a
multi-hour run in the step that closes the last open case. Nothing in the
suite could have caught it, because the only caller was reachable through a
four-hour pipeline.

This is a static check instead. It reads the package, finds every function
that calls its own `log` parameter with keyword arguments, then finds every
call site that passes a logger into one of those functions, and requires the
logger to accept an arbitrary call. No solving, no imports of heavy modules,
milliseconds.

Deliberately narrow. A `lambda s: None` handed to something that only ever
logs one positional string is fine and there are several; flagging those
would make the check noisy and it would be silenced. What is forbidden is
the mismatch that actually crashes.
"""

import ast
import glob
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = sorted(glob.glob(os.path.join(ROOT, 'scrabble_max', '*.py'))
                 + glob.glob(os.path.join(ROOT, 'tests', '*.py')))


def _tree(path):
    with open(path) as f:
        return ast.parse(f.read())


def kwargs_logging_functions():
    """Functions that call their `log` parameter with keyword arguments."""
    out = set()
    for path in SOURCES:
        for fn in [n for n in ast.walk(_tree(path))
                   if isinstance(n, ast.FunctionDef)]:
            names = ({a.arg for a in fn.args.args}
                     | {a.arg for a in fn.args.kwonlyargs})
            if 'log' not in names:
                continue
            for call in ast.walk(fn):
                if (isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Name)
                        and call.func.id == 'log' and call.keywords):
                    out.add(fn.name)
                    break
    return out


def _accepts_anything(node):
    """Does this expression evaluate to something that takes any call?

    Lambdas are checked structurally. Anything else -- a named function, an
    attribute, a variable -- is given the benefit of the doubt, because
    resolving it statically is a different and much larger problem, and the
    crash this guards against comes from inline lambdas.
    """
    if isinstance(node, ast.Lambda):
        return node.args.vararg is not None and node.args.kwarg is not None
    return True


def unsafe_call_sites():
    targets = kwargs_logging_functions()
    bad = []
    for path in SOURCES:
        for call in [n for n in ast.walk(_tree(path))
                     if isinstance(n, ast.Call)]:
            name = (getattr(call.func, 'id', None)
                    or getattr(call.func, 'attr', None))
            if name not in targets:
                continue
            kw = next((k for k in call.keywords if k.arg == 'log'), None)
            if kw is None or _accepts_anything(kw.value):
                continue
            bad.append((os.path.relpath(path, ROOT), call.lineno, name,
                        ast.unparse(kw.value)))
    return bad


def test_the_scan_finds_the_functions_it_is_meant_to():
    """Vacuity guard. If the scan found nothing, every assertion below
    would hold trivially and the check would be decoration."""
    fns = kwargs_logging_functions()
    assert 'refute_parallel' in fns, (
        'refute_parallel logs with flush=True; the scan must see it')
    assert 'enumerate_configs' in fns
    assert 'check_configs' in fns
    assert len(fns) >= 5


def test_no_logger_is_passed_where_it_cannot_be_called():
    bad = unsafe_call_sites()
    assert not bad, 'loggers that cannot take the calls their callee makes:\n' \
        + '\n'.join(f'  {p}:{ln}  {fn}(log={src})' for p, ln, fn, src in bad)


def test_the_check_would_have_caught_the_tier3_bug(tmp_path):
    """The exact regression, reconstructed. Without this the scan could
    quietly stop matching -- a renamed parameter, a changed AST shape --
    and keep passing."""
    src = tmp_path / 'mod.py'
    src.write_text(
        'def refute_parallel(a, log=print):\n'
        '    log("depth 0", flush=True)\n'
        '\n'
        'def caller():\n'
        '    refute_parallel(1, log=lambda *x: None)\n')
    tree = ast.parse(src.read_text())
    fn = [n for n in ast.walk(tree)
          if isinstance(n, ast.FunctionDef) and n.name == 'refute_parallel'][0]
    logs_with_kwargs = any(
        isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
        and c.func.id == 'log' and c.keywords for c in ast.walk(fn))
    assert logs_with_kwargs, 'the scan must recognise a flushed log call'

    call = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
            and getattr(n.func, 'id', None) == 'refute_parallel'][0]
    kw = next(k for k in call.keywords if k.arg == 'log')
    assert not _accepts_anything(kw.value), (
        'the scan must reject `lambda *x: None`, which is the bug')


@pytest.mark.parametrize('src,ok', [
    ('lambda *a, **k: None', True),
    ('lambda *x: None', False),
    ('lambda s: None', False),
    ('lambda: None', False),
    ('print', True),
    ('some_named_function', True),
])
def test_accepts_anything_classifies_loggers(src, ok):
    assert _accepts_anything(ast.parse(src, mode='eval').body) is ok
