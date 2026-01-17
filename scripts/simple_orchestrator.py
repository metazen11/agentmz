#!/usr/bin/env python3
"""
Simple Orchestrator - Run predefined atomic tasks with validation and retry.

Uses hardcoded task sequences for known goals.
Much faster than LLM-based planning.
"""

import os
import sys
import subprocess
from pathlib import Path

WORKSPACE = os.environ.get("WORKSPACE", "workspaces/poc")
MODEL = os.environ.get("MODEL", "deepseek-coder:1.3b")  # Fast model
DOCKER_IMAGE = "agentic-coder:latest"

# Predefined atomic task sequences
TASK_SEQUENCES = {
    "ollama-chat": [
        {
            "name": "Create HTML skeleton",
            "prompt": "Create chat.html with: DOCTYPE, html, head with title 'Ollama Chat', empty body. Dark theme: body background #1e1e1e, color white.",
            "output": "chat.html"
        },
        {
            "name": "Add chat container",
            "prompt": "Edit chat.html: Inside body add a div id='chat-container' with CSS: max-width 800px, margin auto, padding 20px.",
            "output": "chat.html"
        },
        {
            "name": "Add message display",
            "prompt": "Edit chat.html: Inside chat-container add div id='messages' with CSS: height 400px, overflow-y auto, border 1px solid #333, margin-bottom 10px, padding 10px.",
            "output": "chat.html"
        },
        {
            "name": "Add input form",
            "prompt": "Edit chat.html: After messages div add: input id='prompt' type text style='width:80%;padding:10px;background:#333;color:white;border:1px solid #555' and button id='send' onclick='sendMessage()' text 'Send' style='padding:10px 20px;background:#4CAF50;color:white;border:none;cursor:pointer'.",
            "output": "chat.html"
        },
        {
            "name": "Add JavaScript",
            "prompt": """Edit chat.html: Add script tag with this exact JavaScript:
async function sendMessage() {
  const input = document.getElementById('prompt');
  const messages = document.getElementById('messages');
  const text = input.value.trim();
  if (!text) return;

  messages.innerHTML += '<div style="margin:10px 0;padding:10px;background:#2d2d2d;border-radius:5px">You: ' + text + '</div>';
  input.value = '';

  try {
    const res = await fetch('http://localhost:11434/api/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({model: 'qwen2.5-coder:3b', prompt: text, stream: false})
    });
    const data = await res.json();
    messages.innerHTML += '<div style="margin:10px 0;padding:10px;background:#1a3a1a;border-radius:5px">AI: ' + data.response + '</div>';
    messages.scrollTop = messages.scrollHeight;
  } catch(e) {
    messages.innerHTML += '<div style="color:red">Error: ' + e.message + '</div>';
  }
}
document.getElementById('prompt').addEventListener('keypress', e => { if(e.key==='Enter') sendMessage(); });""",
            "output": "chat.html"
        }
    ]
}


def run_task(prompt: str, workspace: str) -> dict:
    """Run single task in container with short timeout."""
    abs_workspace = os.path.abspath(workspace)

    cmd = [
        "docker", "run", "--rm",
        "-e", f"PROMPT={prompt}",
        "-e", "OLLAMA_HOST=http://host.docker.internal:11434",
        "-e", "CONTEXT_SIZE=4096",
        "-e", "MAX_TOKENS=1024",
        "-e", f"MODEL={MODEL}",
        "-v", f"{abs_workspace}:/workspace",
        DOCKER_IMAGE
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def validate_file(workspace: str, filename: str) -> bool:
    """Check if file exists and has content."""
    filepath = Path(workspace) / filename
    return filepath.exists() and filepath.stat().st_size > 0


def run_sequence(sequence_name: str, workspace: str, max_retries: int = 2):
    """Run a predefined task sequence."""
    if sequence_name not in TASK_SEQUENCES:
        print(f"Unknown sequence: {sequence_name}")
        print(f"Available: {list(TASK_SEQUENCES.keys())}")
        return

    tasks = TASK_SEQUENCES[sequence_name]
    print(f"[ORCH] Running sequence: {sequence_name}")
    print(f"[ORCH] Tasks: {len(tasks)}")
    print(f"[ORCH] Model: {MODEL}")
    print()

    for i, task in enumerate(tasks, 1):
        print(f"[{i}/{len(tasks)}] {task['name']}")

        for attempt in range(max_retries):
            result = run_task(task["prompt"], workspace)

            if result["success"]:
                # Check output file exists
                if validate_file(workspace, task["output"]):
                    print(f"  ✓ Created {task['output']}")
                    break
                else:
                    print(f"  ✗ File not created, retrying...")
            else:
                print(f"  ✗ Failed: {result.get('error', 'Unknown')}")

            if attempt < max_retries - 1:
                print(f"  Retry {attempt + 2}/{max_retries}...")
        else:
            print(f"  ✗ Task failed after {max_retries} attempts")

    # Summary
    print()
    print("[ORCH] Complete. Files:")
    for f in Path(workspace).iterdir():
        if not f.name.startswith("."):
            print(f"  {f.name} ({f.stat().st_size} bytes)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <sequence-name> [workspace]")
        print(f"Sequences: {list(TASK_SEQUENCES.keys())}")
        sys.exit(1)

    seq = sys.argv[1]
    ws = sys.argv[2] if len(sys.argv) > 2 else WORKSPACE

    run_sequence(seq, ws)
