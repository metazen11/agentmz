"""LangGraph StateGraph definition for agent orchestration with subtask delegation."""
import json
import os
import time
from typing import Annotated, Any, Literal, Optional, TypedDict

import httpx
from langgraph.graph import END, StateGraph

from .circuit_breaker import subtask_circuit_breaker
from .constants import (
    MAX_DELEGATION_DEPTH,
    MAX_ITERATIONS,
    MAX_SUBTASKS_PER_TASK,
    SUBTASK_TIMEOUT_SECONDS,
)
from .tools import TOOL_DEFINITIONS, run_tool

# Configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL = os.getenv("AGENT_MODEL", "qwen2.5-coder:7b")
TIMEOUT = int(os.getenv("AGENT_TIMEOUT", "120"))
MAIN_API_URL = os.getenv("MAIN_API_URL", "http://localhost:8002")


def add_messages(left: list, right: list) -> list:
    """Reducer that appends messages."""
    return left + right


def add_results(left: list, right: list) -> list:
    """Reducer that appends subtask results."""
    return left + right


class AgentState(TypedDict):
    """State for the agent graph."""
    task_id: int
    parent_task_id: Optional[int]
    depth: int
    workspace_path: str
    messages: Annotated[list[dict], add_messages]
    subtasks: list[dict]  # Pending subtasks to create
    subtask_results: Annotated[list[dict], add_results]
    tool_calls_log: list[dict]  # All tool calls made
    iteration: int
    status: str  # running, done, failed
    final_result: Optional[dict]


def call_ollama(messages: list, tools: list) -> Optional[dict]:
    """Call Ollama API with messages and tools."""
    try:
        response = httpx.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": MODEL,
                "messages": messages,
                "tools": tools,
                "stream": False,
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error calling Ollama: {type(e).__name__}: {e}")
        return None


def parse_tool_calls_from_content(content: str) -> list:
    """Parse tool calls from content when model returns JSON instead of tool_calls."""
    import re

    tool_calls = []
    content = content.strip()

    try:
        data = json.loads(content)
        if isinstance(data, dict) and "name" in data:
            tool_calls.append({
                "function": {
                    "name": data.get("name"),
                    "arguments": data.get("arguments", {}),
                }
            })
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "name" in item:
                    tool_calls.append({
                        "function": {
                            "name": item.get("name"),
                            "arguments": item.get("arguments", {}),
                        }
                    })
    except json.JSONDecodeError:
        json_pattern = r'\{[^{}]*"name"\s*:\s*"[^"]+"\s*[^{}]*\}'
        matches = re.findall(json_pattern, content)
        for match in matches:
            try:
                data = json.loads(match)
                if "name" in data:
                    tool_calls.append({
                        "function": {
                            "name": data.get("name"),
                            "arguments": data.get("arguments", {}),
                        }
                    })
            except json.JSONDecodeError:
                pass

    return tool_calls


def get_all_tools(depth: int) -> list:
    """Get tool definitions, including delegate_subtask if depth allows."""
    tools = TOOL_DEFINITIONS.copy()

    # Only add delegation tool if we haven't reached max depth
    if depth < MAX_DELEGATION_DEPTH:
        tools.append({
            "type": "function",
            "function": {
                "name": "delegate_subtask",
                "description": "Delegate a subtask to another agent. Use this when a task can be broken into independent pieces that can be handled separately.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Title of the subtask",
                        },
                        "description": {
                            "type": "string",
                            "description": "Detailed description of what the subtask should accomplish",
                        },
                        "wait": {
                            "type": "boolean",
                            "description": "Whether to wait for subtask completion (default: true)",
                        },
                    },
                    "required": ["title", "description"],
                },
            },
        })

    return tools


def supervisor_node(state: AgentState) -> dict:
    """Supervisor node that calls the LLM and decides next action."""
    print(f"\n--- Supervisor (iteration {state['iteration']}) ---")

    # Check iteration limit
    if state["iteration"] >= MAX_ITERATIONS:
        return {
            "status": "failed",
            "final_result": {
                "status": "FAIL",
                "summary": f"Exceeded max iterations ({MAX_ITERATIONS})",
            },
        }

    # Get tools based on depth
    tools = get_all_tools(state["depth"])

    # Call LLM
    response = call_ollama(state["messages"], tools)

    if not response:
        return {
            "status": "failed",
            "final_result": {
                "status": "FAIL",
                "summary": "Failed to get response from Ollama",
            },
        }

    message = response.get("message", {})
    content = message.get("content", "")
    tool_calls = message.get("tool_calls", [])

    if content:
        print(f"Agent: {content[:200]}...")

    # Parse tool calls from content if needed
    if not tool_calls and content:
        tool_calls = parse_tool_calls_from_content(content)

    # Add assistant message to history
    new_messages = [{
        "role": "assistant",
        "content": content,
        "tool_calls": tool_calls if tool_calls else None,
    }]

    return {
        "messages": new_messages,
        "iteration": state["iteration"] + 1,
    }


def route_supervisor(state: AgentState) -> Literal["run_tool", "delegate", "end"]:
    """Route based on supervisor output."""
    # Check if already done/failed
    if state["status"] in ("done", "failed"):
        return "end"

    if state.get("final_result"):
        return "end"

    # Get the last message
    if not state["messages"]:
        return "end"

    last_msg = state["messages"][-1]
    if last_msg.get("role") != "assistant":
        return "end"

    tool_calls = last_msg.get("tool_calls") or []

    if not tool_calls:
        # No tools called, check if naturally done
        content = last_msg.get("content", "")
        if "done" in content.lower():
            return "end"
        return "end"

    # Check if any tool call is delegate_subtask
    for tc in tool_calls:
        tool_name = tc.get("function", {}).get("name")
        if tool_name == "delegate_subtask":
            return "delegate"

    return "run_tool"


def run_tool_node(state: AgentState) -> dict:
    """Execute non-delegation tool calls."""
    last_msg = state["messages"][-1]
    tool_calls = last_msg.get("tool_calls") or []

    tool_results = []
    tool_calls_log = []
    final_result = None

    for tool_call in tool_calls:
        tool_name = tool_call.get("function", {}).get("name")
        tool_args = tool_call.get("function", {}).get("arguments", {})

        # Skip delegate_subtask here (handled by delegate node)
        if tool_name == "delegate_subtask":
            continue

        print(f"Tool: {tool_name}({json.dumps(tool_args)[:100]})")

        # Execute the tool
        tool_output = run_tool(tool_name, tool_args)
        tool_calls_log.append({
            "tool": tool_name,
            "args": tool_args,
            "output": tool_output[:500] if tool_output else "",
        })

        # Check for done signal
        if tool_output and tool_output.startswith("__DONE__"):
            parts = tool_output.split("|")
            final_result = {
                "status": parts[1] if len(parts) > 1 else "PASS",
                "summary": parts[2] if len(parts) > 2 else "",
            }
            return {
                "status": "done",
                "final_result": final_result,
                "tool_calls_log": tool_calls_log,
            }

        tool_results.append({
            "tool_call_id": tool_call.get("id", ""),
            "role": "tool",
            "content": tool_output,
        })

    return {
        "messages": tool_results,
        "tool_calls_log": tool_calls_log,
    }


def delegate_node(state: AgentState) -> dict:
    """Create subtask via API for delegation."""
    last_msg = state["messages"][-1]
    tool_calls = last_msg.get("tool_calls") or []

    subtasks_to_create = []

    for tool_call in tool_calls:
        tool_name = tool_call.get("function", {}).get("name")
        if tool_name != "delegate_subtask":
            continue

        tool_args = tool_call.get("function", {}).get("arguments", {})
        subtasks_to_create.append({
            "title": tool_args.get("title", "Subtask"),
            "description": tool_args.get("description", ""),
            "wait": tool_args.get("wait", True),
        })

    return {"subtasks": subtasks_to_create}


def wait_subtask_node(state: AgentState) -> dict:
    """Create subtasks via API and wait for completion."""
    subtasks = state.get("subtasks", [])
    if not subtasks:
        return {"subtasks": [], "messages": [{"role": "tool", "content": "No subtasks to process"}]}

    # Check circuit breaker
    if not subtask_circuit_breaker.can_run():
        breaker_state = subtask_circuit_breaker.get_state()
        return {
            "subtasks": [],
            "messages": [{
                "role": "tool",
                "content": f"Circuit breaker open: too many subtask failures. State: {breaker_state}",
            }],
        }

    results = []
    tool_messages = []

    for subtask in subtasks:
        try:
            # Create subtask via API
            response = httpx.post(
                f"{MAIN_API_URL}/tasks/{state['task_id']}/subtasks",
                json={
                    "title": subtask["title"],
                    "description": subtask["description"],
                },
                timeout=30,
            )

            if response.status_code != 200:
                error_msg = f"Failed to create subtask: {response.status_code}"
                subtask_circuit_breaker.record_failure()
                tool_messages.append({"role": "tool", "content": error_msg})
                continue

            subtask_data = response.json()
            subtask_id = subtask_data.get("id")

            if not subtask["wait"]:
                # Don't wait, just record that it was created
                results.append({
                    "subtask_id": subtask_id,
                    "title": subtask["title"],
                    "status": "created",
                    "result": None,
                })
                tool_messages.append({
                    "role": "tool",
                    "content": f"Subtask '{subtask['title']}' created with ID {subtask_id} (not waiting)",
                })
                continue

            # Wait for subtask completion by polling
            start_time = time.time()
            while True:
                elapsed = time.time() - start_time
                if elapsed > SUBTASK_TIMEOUT_SECONDS:
                    subtask_circuit_breaker.record_failure()
                    tool_messages.append({
                        "role": "tool",
                        "content": f"Subtask '{subtask['title']}' timed out after {SUBTASK_TIMEOUT_SECONDS}s",
                    })
                    break

                # Poll subtask status
                status_response = httpx.get(
                    f"{MAIN_API_URL}/tasks/{subtask_id}",
                    timeout=10,
                )

                if status_response.status_code == 200:
                    status_data = status_response.json()
                    task_status = status_data.get("status")

                    if task_status == "done":
                        subtask_circuit_breaker.record_success()
                        results.append({
                            "subtask_id": subtask_id,
                            "title": subtask["title"],
                            "status": "completed",
                            "result": status_data,
                        })
                        tool_messages.append({
                            "role": "tool",
                            "content": f"Subtask '{subtask['title']}' completed successfully",
                        })
                        break

                    elif task_status == "failed":
                        subtask_circuit_breaker.record_failure()
                        results.append({
                            "subtask_id": subtask_id,
                            "title": subtask["title"],
                            "status": "failed",
                            "result": status_data,
                        })
                        tool_messages.append({
                            "role": "tool",
                            "content": f"Subtask '{subtask['title']}' failed",
                        })
                        break

                # Wait before polling again
                time.sleep(2)

        except Exception as e:
            subtask_circuit_breaker.record_failure()
            tool_messages.append({
                "role": "tool",
                "content": f"Error processing subtask '{subtask.get('title', 'unknown')}': {e}",
            })

    return {
        "subtasks": [],
        "subtask_results": results,
        "messages": tool_messages,
    }


def create_agent_graph() -> StateGraph:
    """Create the LangGraph StateGraph for agent orchestration."""
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("run_tool", run_tool_node)
    graph.add_node("delegate", delegate_node)
    graph.add_node("wait_subtask", wait_subtask_node)

    # Add edges
    graph.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {
            "run_tool": "run_tool",
            "delegate": "delegate",
            "end": END,
        }
    )
    graph.add_edge("run_tool", "supervisor")
    graph.add_edge("delegate", "wait_subtask")
    graph.add_edge("wait_subtask", "supervisor")

    # Set entry point
    graph.set_entry_point("supervisor")

    return graph


def run_agent_graph(
    workspace_path: str,
    task_title: str,
    task_description: str,
    task_id: int,
    node_name: str = "dev",
    depth: int = 0,
    parent_task_id: Optional[int] = None,
) -> dict:
    """Run the agent graph to complete a task.

    Args:
        workspace_path: Path to the workspace directory
        task_title: Title of the task
        task_description: Description of what to do
        task_id: Database ID of the task
        node_name: Current pipeline node (pm, dev, qa, security, documentation)
        depth: Current delegation depth (0 = root task)
        parent_task_id: ID of parent task if this is a subtask

    Returns:
        dict with status (PASS/FAIL), summary, and details
    """
    from .tools import set_workspace

    set_workspace(workspace_path)

    # Build system prompt based on node
    node_prompts = {
        "pm": "You are a project planner. Clarify scope, break down work, and outline risks.",
        "dev": "You are a developer agent. Implement the requested feature or fix the bug. Write clean, working code.",
        "qa": "You are a QA agent. Test the implementation. Run any tests, check for edge cases, verify functionality works.",
        "security": "You are a security reviewer. Identify risks and verify protections.",
        "documentation": "You are a technical writer. Document changes and how to validate them.",
    }
    system_prompt = node_prompts.get(node_name, node_prompts["dev"])

    # Add delegation context if allowed
    if depth < MAX_DELEGATION_DEPTH:
        system_prompt += f"""

You have the ability to delegate subtasks to other agents using the delegate_subtask tool.
Use this when a task can be broken into independent pieces.
Current depth: {depth}/{MAX_DELEGATION_DEPTH}. You can create up to {MAX_SUBTASKS_PER_TASK} subtasks."""

    # Build initial message
    user_message = f"""Task: {task_title}

Description: {task_description}

Workspace: {workspace_path}

Instructions:
1. First, explore the workspace to understand the codebase
2. Then implement the required changes
3. Use edit_file with search/replace for precise edits (or empty search to create new files)
4. When done, call the 'done' tool with status PASS (success) or FAIL (if you couldn't complete it)

Start by listing the files in the workspace."""

    # Create initial state
    initial_state: AgentState = {
        "task_id": task_id,
        "parent_task_id": parent_task_id,
        "depth": depth,
        "workspace_path": workspace_path,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "subtasks": [],
        "subtask_results": [],
        "tool_calls_log": [],
        "iteration": 0,
        "status": "running",
        "final_result": None,
    }

    # Create and compile the graph
    graph = create_agent_graph()
    app = graph.compile()

    # Run the graph
    final_state = None
    for state in app.stream(initial_state):
        final_state = state
        # Get the actual state from the node output
        for node_name_key, node_state in state.items():
            if isinstance(node_state, dict):
                # Merge node state into our tracking
                if node_state.get("final_result"):
                    final_state = node_state

    # Extract result
    if final_state and isinstance(final_state, dict):
        result = final_state.get("final_result")
        if result:
            result["details"] = json.dumps(
                final_state.get("tool_calls_log", []), indent=2
            )
            return result

    return {
        "status": "FAIL",
        "summary": "Agent did not complete normally",
        "details": json.dumps(final_state.get("tool_calls_log", []) if final_state else [], indent=2),
    }
