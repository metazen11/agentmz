"""Pre-hook that refines user prompts before LLM processing.

Runs BEFORE context_inject to clarify intent and add specifications,
so knowledge retrieval uses the refined query for better results.

Order: User Prompt → prompt_refine → context_inject → LLM
"""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Tools that send prompts to the LLM
LLM_TOOLS = {"chat", "generate", "ask_llm", "complete", "agent_run"}

# Project conventions (could be loaded from AGENTS.md)
DEFAULT_CONVENTIONS = """
- Follow existing code patterns in the codebase
- Write tests for new functionality
- Use structured JSON responses for APIs
- Validate all inputs
- Handle errors gracefully with try/except
"""


def pre_tool(tool_name: str, args: dict) -> bool:
    """Refine prompts before LLM processing.

    Args:
        tool_name: Name of the tool about to execute
        args: Arguments that will be passed to the tool (mutable)

    Returns:
        True to proceed with execution (always returns True)
    """
    if tool_name not in LLM_TOOLS:
        return True

    # Get the prompt from args
    prompt_key = _get_prompt_key(args)
    if not prompt_key:
        return True

    original_prompt = args[prompt_key]
    if not original_prompt or len(original_prompt.strip()) < 5:
        return True

    try:
        refined = refine_prompt(original_prompt)
        if refined and refined != original_prompt:
            args[prompt_key] = refined
            # Store original for reference
            args["_original_prompt"] = original_prompt
            logger.debug(f"Refined prompt for {tool_name}")
    except Exception as e:
        logger.warning(f"Prompt refinement failed: {e}")

    return True


def _get_prompt_key(args: dict) -> Optional[str]:
    """Find which key contains the prompt."""
    for key in ("prompt", "message", "query", "request"):
        if key in args and args[key]:
            return key
    return None


def refine_prompt(prompt: str, conventions: Optional[str] = None) -> str:
    """Refine a user prompt with specifications and clarity.

    Args:
        prompt: Original user prompt
        conventions: Project conventions to include (defaults to DEFAULT_CONVENTIONS)

    Returns:
        Refined prompt with added specifications
    """
    conventions = conventions or _load_conventions()

    # Detect prompt type and add appropriate refinements
    refinements = []

    # Check for vague requests and add specificity
    prompt_lower = prompt.lower()

    # Code generation requests
    if any(word in prompt_lower for word in ["add", "create", "implement", "write", "build"]):
        refinements.append("Determine the appropriate file location based on existing project structure")
        refinements.append("Match existing code style and patterns")
        if "test" not in prompt_lower:
            refinements.append("Include unit tests if adding new functionality")

    # Bug fix requests
    if any(word in prompt_lower for word in ["fix", "bug", "error", "broken", "issue"]):
        refinements.append("Identify root cause before implementing fix")
        refinements.append("Ensure fix doesn't introduce regressions")

    # Refactoring requests
    if any(word in prompt_lower for word in ["refactor", "improve", "optimize", "clean"]):
        refinements.append("Maintain existing behavior (no functional changes unless specified)")
        refinements.append("Keep changes minimal and focused")

    # Question/explanation requests - minimal refinement
    if any(word in prompt_lower for word in ["what", "how", "why", "explain", "?"]):
        # Don't over-refine questions
        return prompt

    # Build the refined prompt
    if not refinements:
        return prompt

    refined_parts = [
        "## Task",
        prompt,
        "",
        "## Requirements",
    ]
    refined_parts.extend(f"- {r}" for r in refinements)

    if conventions:
        refined_parts.extend([
            "",
            "## Project Conventions",
            conventions.strip(),
        ])

    return "\n".join(refined_parts)


def _load_conventions() -> str:
    """Load project conventions from AGENTS.md or use defaults."""
    agents_md_path = os.environ.get("AGENTS_MD_PATH", "AGENTS.md")

    try:
        if os.path.exists(agents_md_path):
            with open(agents_md_path, "r") as f:
                content = f.read()
                # Extract key conventions (simplified - could parse more intelligently)
                if "## 5. Rules of Engagement" in content:
                    # Extract MUST DO section
                    start = content.find("### MUST DO")
                    end = content.find("### MUST NOT", start)
                    if start > 0 and end > start:
                        must_do = content[start:end]
                        return must_do
    except Exception:
        pass

    return DEFAULT_CONVENTIONS


def set_conventions(conventions: str) -> None:
    """Set custom conventions for prompt refinement.

    Args:
        conventions: Custom conventions text
    """
    global _custom_conventions
    _custom_conventions = conventions


_custom_conventions: Optional[str] = None
