"""Keeping the machine awake while a long campaign runs.

A campaign is hours of unattended computation; an operating system that
puts the machine to sleep after an idle hour freezes it halfway (and any
wall-clock limit on the job keeps counting). `keep_system_awake` asks the
OS not to idle-sleep for as long as the calling process lives - the
standard request long-running applications make. It changes no power
setting, is released automatically when the context exits or the process
dies, and does not stop the display from turning off or a lid-close or
low-battery sleep.
"""
from __future__ import annotations

import contextlib
import sys
from collections.abc import Iterator

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


@contextlib.contextmanager
def keep_system_awake(enabled: bool = True) -> Iterator[bool]:
    """Yields True when the request was accepted. A no-op (yielding False)
    when disabled, on other platforms, or if the OS refuses - never an
    error: a campaign must not fail because the machine may sleep."""
    accepted = False
    if enabled and sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetThreadExecutionState.restype = ctypes.c_uint
            accepted = bool(kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED))
        except Exception:  # noqa: BLE001 - see the docstring
            accepted = False
    try:
        yield accepted
    finally:
        if accepted:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
