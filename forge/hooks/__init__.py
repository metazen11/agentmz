"""Hook manager for Forge tooling hooks.

Hooks live under `forge/hooks/*.py` and may expose `pre_tool`
and/or `post_tool` callables. The manager eagerly imports any
module in this package the first time a hook is fired, then
reuses the registered callables on subsequent tool runs.
"""
from __future__ import annotations

import inspect
import logging
import pkgutil
from importlib import import_module
from pathlib import Path
from typing import Any, Callable

HookCallable = Callable[..., Any]


class HookManager:
    """Load and run Forge hooks before and after each tool call."""

    def __init__(self, hooks_dir: Path | None = None) -> None:
        self._builtin_dir = Path(__file__).parent
        self._user_dir = Path.home() / ".forge" / "hooks"
        self._extra_dir = hooks_dir  # Optional extra hooks directory
        self._package = __package__
        self._logger = logging.getLogger(__name__)
        self._pre_hooks: list[HookCallable] = []
        self._post_hooks: list[HookCallable] = []
        self._loaded = False

    def pre_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> bool:
        """Run all registered pre-tool hooks.

        Returns:
            True if execution should proceed, False to abort.
        """
        self._ensure_hooks_loaded()
        args = args or {}
        return self._run_pre_hooks(self._pre_hooks, tool_name=tool_name, args=args)

    def post_tool(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        result: Any | None = None,
    ) -> None:
        """Run all registered post-tool hooks."""
        self._ensure_hooks_loaded()
        args = args or {}
        self._run_hooks(
            self._post_hooks,
            tool_name=tool_name,
            args=args,
            result=result,
        )

    def _ensure_hooks_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        # Load builtin hooks from package
        self._load_from_dir(self._builtin_dir, package=self._package)
        # Load user hooks from ~/.forge/hooks/
        self._load_from_dir(self._user_dir, package=None)
        # Load extra hooks if specified
        if self._extra_dir:
            self._load_from_dir(self._extra_dir, package=None)

    def _load_from_dir(self, hooks_dir: Path, package: str | None) -> None:
        """Load hooks from a directory."""
        if not hooks_dir.exists():
            return
        for finder, name, _ispkg in pkgutil.iter_modules([str(hooks_dir)]):
            if name.startswith("_"):
                continue
            try:
                if package:
                    module = import_module(f"{package}.{name}")
                else:
                    # Load standalone .py file
                    import importlib.util
                    spec = importlib.util.spec_from_file_location(
                        name, hooks_dir / f"{name}.py"
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                    else:
                        continue
            except Exception as exc:  # pragma: no cover - best effort
                self._logger.warning("could not import hook %s: %s", name, exc)
                continue
            self._register_module(module)

    def _register_module(self, module: Any) -> None:
        if callable(getattr(module, "pre_tool", None)):
            self._pre_hooks.append(module.pre_tool)
        if callable(getattr(module, "post_tool", None)):
            self._post_hooks.append(module.post_tool)

    def _run_pre_hooks(self, hooks: list[HookCallable], **data: Any) -> bool:
        """Run pre-hooks. Returns False if any hook returns False (abort)."""
        for hook in hooks:
            try:
                result = self._call_with_matching_args(hook, data)
                if result is False:
                    return False
            except Exception:  # pragma: no cover - hooks are best-effort
                self._logger.exception("hook %s failed", getattr(hook, "__name__", repr(hook)))
        return True

    def _run_hooks(self, hooks: list[HookCallable], **data: Any) -> None:
        for hook in hooks:
            try:
                self._call_with_matching_args(hook, data)
            except Exception:  # pragma: no cover - hooks are best-effort
                self._logger.exception("hook %s failed", getattr(hook, "__name__", repr(hook)))

    @staticmethod
    def _call_with_matching_args(hook: HookCallable, data: dict[str, Any]) -> Any:
        sig = inspect.signature(hook)
        if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values()):
            return hook(**data)
        matched = {
            key: value
            for key, value in data.items()
            if key in sig.parameters
        }
        return hook(**matched)


__all__ = ["HookManager"]
