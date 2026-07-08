"""
Eval-only shim for `autogen`.

The installed `pyautogen` in venv311 is corrupted (missing its top-level
__init__.py after a machine migration), so `from autogen import AssistantAgent,
UserProxyAgent, register_function` at the top of agents/spec_interpreter.py
raises ImportError before the module can even be loaded.

The `--dry-run` / `parse_specification()` path used by this evaluation does NOT
use autogen at all — it calls the OpenAI client directly. So we put this stub
earlier on PYTHONPATH (via eval/_shims) to satisfy the top-level import and let
the real parser run unchanged. It is intentionally inert; it must never be used
for the live Jira-creating agent path.
"""


class _Inert:
    """A do-nothing stand-in for the AutoGen agent classes."""

    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "autogen is stubbed for eval (--dry-run) only; the real AutoGen "
            "agent path is unavailable in this environment."
        )


class AssistantAgent(_Inert):
    pass


class UserProxyAgent(_Inert):
    pass


def register_function(*args, **kwargs):  # noqa: D401
    raise RuntimeError("autogen.register_function is stubbed for eval only.")
