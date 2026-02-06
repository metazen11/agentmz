#!/usr/bin/env python3
"""
Template Builder - Algorithmic code generation using templates.

No AI required for generation - just template composition.
AI is only used to UNDERSTAND what the user wants, then templates do the work.
"""

import os
import sys
from pathlib import Path

# Base HTML template
TEMPLATE_HTML_BASE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
body {{
  background: #1e1e1e;
  color: #fff;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  margin: 0;
  padding: 20px;
  min-height: 100vh;
}}
.container {{
  max-width: 800px;
  margin: 0 auto;
}}
{css}
</style>
</head>
<body>
<div class="container">
  <h1>{title}</h1>
  {body}
</div>
{scripts}
</body>
</html>'''

# Component templates
TEMPLATE_MESSAGES_DIV = '''<div id="messages" style="
  height: 400px;
  overflow-y: auto;
  border: 1px solid #333;
  border-radius: 8px;
  padding: 15px;
  margin-bottom: 15px;
  background: #252525;
"></div>'''

TEMPLATE_INPUT_FORM = '''<div id="input-form" style="display: flex; gap: 10px;">
  <input type="text" id="prompt" placeholder="{placeholder}" style="
    flex: 1;
    padding: 12px;
    background: #333;
    border: 1px solid #444;
    border-radius: 6px;
    color: #fff;
    font-size: 14px;
  ">
  <button id="send" style="
    padding: 12px 24px;
    background: #4CAF50;
    color: #fff;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
  ">Send</button>
</div>'''

TEMPLATE_MESSAGE_CSS = '''
.message {
  margin: 10px 0;
  padding: 12px;
  border-radius: 6px;
}
.message.user {
  background: #2d2d2d;
}
.message.assistant {
  background: #1a3a1a;
}
.message.error {
  background: #3a1a1a;
  color: #ff6b6b;
}'''

TEMPLATE_OLLAMA_SCRIPT = '''<script>
const messagesEl = document.getElementById('messages');
const promptEl = document.getElementById('prompt');
const sendBtn = document.getElementById('send');

async function sendMessage() {{
  const text = promptEl.value.trim();
  if (!text) return;

  // Show user message
  addMessage('user', text);
  promptEl.value = '';
  sendBtn.disabled = true;

  try {{
    const res = await fetch('{api_url}', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        model: '{model}',
        prompt: text,
        stream: false
      }})
    }});

    if (!res.ok) throw new Error('API error: ' + res.status);

    const data = await res.json();
    addMessage('assistant', data.response || 'No response');
  }} catch (err) {{
    addMessage('error', 'Error: ' + err.message);
  }}

  sendBtn.disabled = false;
}}

function addMessage(type, content) {{
  const div = document.createElement('div');
  div.className = 'message ' + type;
  div.textContent = content;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}}

sendBtn.addEventListener('click', sendMessage);
promptEl.addEventListener('keypress', e => {{
  if (e.key === 'Enter') sendMessage();
}});
</script>'''


def build_ollama_chat(
    output_path: str,
    title: str = "Ollama Chat",
    api_url: str = "http://localhost:11434/api/generate",
    model: str = "qwen2.5-coder:3b",
    placeholder: str = "Type your message..."
):
    """Build a complete Ollama chat HTML file algorithmically."""

    body = TEMPLATE_MESSAGES_DIV + "\n  " + TEMPLATE_INPUT_FORM.format(placeholder=placeholder)
    css = TEMPLATE_MESSAGE_CSS
    scripts = TEMPLATE_OLLAMA_SCRIPT.format(api_url=api_url, model=model)

    html = TEMPLATE_HTML_BASE.format(
        title=title,
        css=css,
        body=body,
        scripts=scripts
    )

    Path(output_path).write_text(html)
    print(f"Created: {output_path} ({len(html)} bytes)")
    return html


def build_from_recipe(recipe: dict, workspace: str):
    """Build files from a recipe dictionary."""
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    for filename, config in recipe.get("files", {}).items():
        file_type = config.get("type", "custom")

        if file_type == "ollama-chat":
            build_ollama_chat(
                output_path=str(workspace / filename),
                title=config.get("title", "Ollama Chat"),
                api_url=config.get("api_url", "http://localhost:11434/api/generate"),
                model=config.get("model", "qwen2.5-coder:3b")
            )
        elif file_type == "custom":
            content = config.get("content", "")
            (workspace / filename).write_text(content)
            print(f"Created: {filename} ({len(content)} bytes)")


# Predefined recipes
RECIPES = {
    "ollama-chat": {
        "files": {
            "chat.html": {
                "type": "ollama-chat",
                "title": "Ollama Chat",
                "api_url": "http://localhost:11434/api/generate",
                "model": "qwen2.5-coder:3b"
            }
        }
    }
}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python template_builder.py <recipe-name> <workspace>")
        print(f"Recipes: {list(RECIPES.keys())}")
        sys.exit(1)

    recipe_name = sys.argv[1]
    workspace = sys.argv[2]

    if recipe_name not in RECIPES:
        print(f"Unknown recipe: {recipe_name}")
        sys.exit(1)

    build_from_recipe(RECIPES[recipe_name], workspace)
    print("Done!")
