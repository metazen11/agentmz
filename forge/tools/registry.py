"""Dynamic tool registry for Forge agent.

Allows runtime tool registration and discovery.
Forge can add its own tools during a session.
"""
import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from langchain_core.tools import tool as langchain_tool, StructuredTool
except ImportError:
    langchain_tool = None
    StructuredTool = None


class ToolRegistry:
    """Registry for dynamic tool management."""

    def __init__(self, workspace: str = "."):
        self.workspace = workspace
        self._custom_tools: dict[str, Callable] = {}
        self._tool_metadata: dict[str, dict] = {}
        self._tools_dir = Path(workspace) / ".forge" / "tools"

    def register(
        self,
        name: str,
        func: Callable,
        description: str = "",
        schema: Optional[dict] = None,
    ) -> None:
        """Register a tool dynamically.

        Args:
            name: Tool name (unique identifier)
            func: The callable function
            description: Human-readable description
            schema: JSON schema for arguments (optional)
        """
        self._custom_tools[name] = func
        self._tool_metadata[name] = {
            "name": name,
            "description": description or func.__doc__ or f"Tool: {name}",
            "schema": schema or {},
        }

    def unregister(self, name: str) -> bool:
        """Remove a registered tool."""
        if name in self._custom_tools:
            del self._custom_tools[name]
            del self._tool_metadata[name]
            return True
        return False

    def get(self, name: str) -> Optional[Callable]:
        """Get a registered tool by name."""
        return self._custom_tools.get(name)

    def list_tools(self) -> list[dict]:
        """List all registered custom tools with metadata."""
        return list(self._tool_metadata.values())

    def to_langchain_tools(self) -> list:
        """Convert custom tools to LangChain tool format."""
        if langchain_tool is None:
            raise RuntimeError("langchain-core not available")

        lc_tools = []
        for name, func in self._custom_tools.items():
            meta = self._tool_metadata.get(name, {})
            # Wrap in langchain tool decorator
            wrapped = langchain_tool(func)
            wrapped.name = name
            wrapped.description = meta.get("description", func.__doc__ or "")
            lc_tools.append(wrapped)
        return lc_tools

    def save_tool(self, name: str, code: str) -> dict:
        """Save a tool definition to the workspace.

        Args:
            name: Tool name
            code: Python code defining the tool function

        Returns:
            Success/error dict
        """
        self._tools_dir.mkdir(parents=True, exist_ok=True)
        tool_file = self._tools_dir / f"{name}.py"

        try:
            tool_file.write_text(code, encoding="utf-8")
            return {"success": True, "path": str(tool_file)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def load_tools_from_workspace(self) -> list[str]:
        """Load custom tools from workspace .forge/tools directory.

        Returns:
            List of loaded tool names
        """
        if not self._tools_dir.exists():
            return []

        loaded = []
        for tool_file in self._tools_dir.glob("*.py"):
            try:
                name = tool_file.stem
                # Load module from file without using exec
                import importlib.util
                module_name = f"forge_tool_{name}"
                spec = importlib.util.spec_from_file_location(module_name, tool_file)
                if spec is None or spec.loader is None:
                    raise RuntimeError(f"Unable to load tool module: {tool_file}")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                # Look for a function with the tool name or 'main'
                func = getattr(module, name, None) or getattr(module, "main", None)
                if callable(func):
                    self.register(
                        name=name,
                        func=func,
                        description=func.__doc__ or f"Custom tool: {name}",
                    )
                    loaded.append(name)
            except Exception as e:
                print(f"[registry] Failed to load {tool_file.name}: {e}")
        return loaded


# Global registry instance
_registry: Optional[ToolRegistry] = None


def get_registry(workspace: str = ".") -> ToolRegistry:
    """Get or create the global tool registry."""
    global _registry
    if _registry is None or _registry.workspace != workspace:
        _registry = ToolRegistry(workspace)
    return _registry


def register_tool(
    name: str,
    description: str = "",
    schema: Optional[dict] = None,
):
    """Decorator to register a function as a Forge tool.

    Usage:
        @register_tool("my_tool", "Does something useful")
        def my_tool(arg1: str, arg2: int = 0) -> dict:
            return {"success": True, "result": arg1 * arg2}
    """
    def decorator(func: Callable) -> Callable:
        registry = get_registry()
        registry.register(name, func, description, schema)
        return func
    return decorator
