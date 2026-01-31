

Python

\# Define the content for the final, comprehensive architecture file  
forge\_md\_content \= """\# ARCHITECTURE.md: Forge TUI Coding Agent

\#\# 1\. System Vision  
\*\*Forge\*\* is a local-first, agentic coding environment built for 2026 developer workflows. It focuses on high-speed terminal interaction, verifiable tool execution, and deep project-level memory.

\- \*\*Primary Goal:\*\* A private, keyboard-driven alternative to cloud-based coding assistants.  
\- \*\*Key Philosophy:\*\* \*\*Controllable Autonomy.\*\* The agent proposes; the user disposes.

\---

\#\# 2\. Technical Stack  
| Component         | Technology                  | Role                                                                 |  
|:------------------|:----------------------------|:---------------------------------------------------------------------|  
| \*\*UI Framework\*\* | \*\*Textual\*\* | Cross-platform Python TUI for high-speed terminal rendering.          |  
| \*\*Orchestration\*\* | \*\*LangGraph\*\* | Cyclic, stateful graph for complex multi-turn coding logic.          |  
| \*\*Inference\*\* | \*\*Ollama\*\* | Local execution of coding LLMs (e.g., Qwen3-Coder, DeepSeek-R1).      |  
| \*\*Memory\*\* | \*\*Postgres \+ pgvector\*\* | Persistent episodic and semantic memory for project context.         |  
| \*\*Protocols\*\* | \*\*MCP\*\* | Model Context Protocol for secure, standardized tool usage.           |

\---

\#\# 3\. Detailed Component Architecture

\#\#\# A. The TUI (Textual) \- \`/tui\`  
\- \*\*\`ForgeApp\`\*\*: Inherits from \`textual.app.App\`. Manages the main event loop and CSS styling.  
\- \*\*\`ChatDisplay\`\*\*: A custom widget using \`Rich\` for real-time streaming of syntax-highlighted Markdown.  
\- \*\*\`ControlPanel\`\*\*: Side-bar for dynamic model switching and URL configuration.  
\- \*\*Worker Management\*\*: Uses \`@work\` decorators to handle non-blocking agent threads.

\#\#\# B. The Brain (LangGraph) \- \`/agent\`  
The graph manages the lifecycle of a request:  
1\. \*\*Context Node\*\*: Queries the Memory layer using current prompt embeddings.  
2\. \*\*Model Node\*\*: Generates the next response or tool-call from Ollama.  
3\. \*\*Pre-Tool Hook\*\*: A specialized node that checks tool safety and prompts the TUI for confirmation on sensitive actions (e.g., \`bash\`, \`fs\_write\`).  
4\. \*\*Tool Executor\*\*: Connects to MCP servers to execute actions.  
5\. \*\*Post-Tool Hook\*\*: Injects execution logs/errors back into the state for LLM reflection.

\#\#\# C. The Memory (Postgres) \- \`/memory\`  
\- \*\*Table: \`conversations\`\*\*: Stores stateful checkpoints for LangGraph (PostgresSaver).  
\- \*\*Table: \`project\_knowledge\`\*\*: Stores \`pgvector\` embeddings of code snippets and documentation.  
\- \*\*Strategy\*\*:   
    \- \*\*Short-term\*\*: Sliding window of chat messages.  
    \- \*\*Long-term\*\*: Semantic retrieval of past solutions and architectural patterns.

\---

\#\# 4\. Directory Structure

Code output

\# ARCHITECTURE.md: Forge TUI Coding Agent

\#\# 1\. System Vision  
\*\*Forge\*\* is a local-first, agentic coding environment built for 2026 developer workflows. It focuses on high-speed terminal interaction, verifiable tool execution, and deep project-level memory.

\- \*\*Primary Goal:\*\* A private, keyboard-driven alternative to cloud-based coding assistants.  
\- \*\*Key Philosophy:\*\* \*\*Controllable Autonomy.\*\* The agent proposes; the user disposes.

\---

\#\# 2\. Technical Stack  
| Component         | Technology                  | Role                                                                 |  
|:------------------|:----------------------------|:---------------------------------------------------------------------|  
| \*\*UI Framework\*\* | \*\*Textual\*\* | Cross-platform Python TUI for high-speed terminal rendering.          |  
| \*\*Orchestration\*\* | \*\*LangGraph\*\* | Cyclic, stateful graph for complex multi-turn coding logic.          |  
| \*\*Inference\*\* | \*\*Ollama\*\* | Local execution of coding LLMs (e.g., Qwen3-Coder, DeepSeek-R1).      |  
| \*\*Memory\*\* | \*\*Postgres \+ pgvector\*\* | Persistent episodic and semantic memory for project context.         |  
| \*\*Protocols\*\* | \*\*MCP\*\* | Model Context Protocol for secure, standardized tool usage.           |

\---

\#\# 3\. Detailed Component Architecture

\#\#\# A. The TUI (Textual) \- \`/tui\`  
\- \*\*\`ForgeApp\`\*\*: Inherits from \`textual.app.App\`. Manages the main event loop and CSS styling.  
\- \*\*\`ChatDisplay\`\*\*: A custom widget using \`Rich\` for real-time streaming of syntax-highlighted Markdown.  
\- \*\*\`ControlPanel\`\*\*: Side-bar for dynamic model switching and URL configuration.  
\- \*\*Worker Management\*\*: Uses \`@work\` decorators to handle non-blocking agent threads.

\#\#\# B. The Brain (LangGraph) \- \`/agent\`  
The graph manages the lifecycle of a request:  
1\. \*\*Context Node\*\*: Queries the Memory layer using current prompt embeddings.  
2\. \*\*Model Node\*\*: Generates the next response or tool-call from Ollama.  
3\. \*\*Pre-Tool Hook\*\*: A specialized node that checks tool safety and prompts the TUI for confirmation on sensitive actions (e.g., \`bash\`, \`fs\_write\`).  
4\. \*\*Tool Executor\*\*: Connects to MCP servers to execute actions.  
5\. \*\*Post-Tool Hook\*\*: Injects execution logs/errors back into the state for LLM reflection.

\#\#\# C. The Memory (Postgres) \- \`/memory\`  
\- \*\*Table: \`conversations\`\*\*: Stores stateful checkpoints for LangGraph (PostgresSaver).  
\- \*\*Table: \`project\_knowledge\`\*\*: Stores \`pgvector\` embeddings of code snippets and documentation.  
\- \*\*Strategy\*\*:   
    \- \*\*Short-term\*\*: Sliding window of chat messages.  
    \- \*\*Long-term\*\*: Semantic retrieval of past solutions and architectural patterns.

\---

\#\# 4\. Directory Structure  
\`\`\`text  
/forge  
├── main.py              \# CLI Entrypoint (Typer/Click)  
├── ARCHITECTURE.md      \# This document  
├── forge.css            \# TUI Stylesheet  
├── tui/  
│   ├── app.py           \# Main App Logic  
│   └── widgets.py       \# Custom Chat & Input components  
├── agent/  
│   ├── graph.py         \# LangGraph Definition  
│   ├── nodes.py         \# LLM & Logic Nodes  
│   └── hooks.py         \# Pre/Post Tool Execution Triggers  
├── memory/  
│   ├── manager.py       \# Postgres/pgvector client  
│   └── embeddings.py    \# Local embedding logic (via Ollama)  
└── tools/               \# Local "Skills" and MCP adapters

## ---

**5\. Implementation Roadmap for Codex**

### **Phase 1: The Core Loop**

* Initialize a Textual app with an input field and a display log.  
* Connect a basic LangGraph that sends user input to Ollama and renders the result.

### **Phase 2: Tooling & Hooks**

* Integrate MCP filesystem tools.  
* Add a "Pre-Hook" node that prints "Forge is preparing to write to file..." in the TUI before execution.

### **Phase 3: Project Memory**

* Set up Postgres with pgvector.  
* Implement a retrieval step that injects context into the system prompt based on similarity.

## ---

**6\. License**

**Apache License 2.0.**

This project is open-source. Modification and redistribution are permitted under the terms of the Apache 2.0 license.

Plaintext

/forge  
├── main.py              \# CLI Entrypoint (Typer/Click)  
├── ARCHITECTURE.md      \# This document  
├── forge.css            \# TUI Stylesheet  
├── tui/  
│   ├── app.py           \# Main App Logic  
│   └── widgets.py       \# Custom Chat & Input components  
├── agent/  
│   ├── graph.py         \# LangGraph Definition  
│   ├── nodes.py         \# LLM & Logic Nodes  
│   └── hooks.py         \# Pre/Post Tool Execution Triggers  
├── memory/  
│   ├── manager.py       \# Postgres/pgvector client  
│   └── embeddings.py    \# Local embedding logic (via Ollama)  
└── tools/               \# Local "Skills" and MCP adapters

## ---

**5\. Implementation Roadmap for Codex**

### **Phase 1: The Core Loop**

* Initialize a Textual app with an input field and a display log.  
* Connect a basic LangGraph that sends user input to Ollama and renders the result.

### **Phase 2: Tooling & Hooks**

* Integrate MCP filesystem tools.  
* Add a "Pre-Hook" node that prints "Forge is preparing to write to file..." in the TUI before execution.

### **Phase 3: Project Memory**

* Set up Postgres with pgvector.  
* Implement a retrieval step that injects context into the system prompt based on similarity.

## ---

**6\. License**

**Apache License 2.0.**

This project is open-source. Modification and redistribution are permitted under the terms of the Apache 2.0 license.

"""

# **Outputting as a code block for the user**

print(forge\_md\_content)

Understood. Let's pivot to a much more industrial name: \*\*Forge\*\*.

Since I can't force a separate "canvas" window to persist on your specific interface, the most reliable way to get this into your local environment is via the \*\*Raw Markdown code block\*\* below. You can click the "Copy" button on the top right of the code block and paste it directly into a file named \`ARCHITECTURE.md\` in your project root.

\#\#\# The Forge Architecture Blueprint

\`\`\`markdown  
\# ARCHITECTURE.md: Forge TUI Coding Agent

\#\# 1\. System Vision  
\*\*Forge\*\* is a local-first, agentic coding environment built for 2026 developer workflows. It focuses on high-speed terminal interaction, verifiable tool execution, and deep project-level memory.

\- \*\*Primary Goal:\*\* A private, keyboard-driven alternative to cloud-based coding assistants.  
\- \*\*Key Philosophy:\*\* \*\*Controllable Autonomy.\*\* The agent proposes; the user disposes.

\---

\#\# 2\. Technical Stack  
| Component         | Technology                  | Role                                                                 |  
|:------------------|:----------------------------|:---------------------------------------------------------------------|  
| \*\*UI Framework\*\* | \*\*Textual\*\* | Cross-platform Python TUI for high-speed terminal rendering.          |  
| \*\*Orchestration\*\* | \*\*LangGraph\*\* | Cyclic, stateful graph for complex multi-turn coding logic.          |  
| \*\*Inference\*\* | \*\*Ollama\*\* | Local execution of coding LLMs (e.g., Qwen3-Coder, DeepSeek-R1).      |  
| \*\*Memory\*\* | \*\*Postgres \+ pgvector\*\* | Persistent episodic and semantic memory for project context.         |  
| \*\*Protocols\*\* | \*\*MCP\*\* | Model Context Protocol for secure, standardized tool usage.           |

\---

\#\# 3\. Detailed Component Architecture

\#\#\# A. The TUI (Textual) \- \`/tui\`  
\- \*\*\`ForgeApp\`\*\*: Manages the main event loop, global keybindings, and reactive styling.  
\- \*\*\`ChatDisplay\`\*\*: Uses \`Rich\` for real-time streaming of syntax-highlighted Markdown and diffs.  
\- \*\*\`ControlPanel\`\*\*: A sidebar allowing you to switch models (e.g., from \`Qwen3\` to \`Llama4\`) and update the Ollama URL mid-session.  
\- \*\*Worker Management\*\*: Uses \`@work\` decorators to handle non-blocking agent threads, keeping the terminal responsive during long generations.

\#\#\# B. The Brain (LangGraph) \- \`/agent\`  
The graph manages the lifecycle of every request:  
1\. \*\*Context Node\*\*: Generates an embedding of the user's prompt and queries Postgres for relevant snippets.  
2\. \*\*Model Node\*\*: The primary LLM call.  
3\. \*\*Pre-Tool Hook\*\*: Intercepts tool calls. For "unsafe" actions (shell commands), it triggers a UI modal for user confirmation.  
4\. \*\*Tool Executor\*\*: Standardized \`ToolNode\` that talks to MCP servers.  
5\. \*\*Post-Tool Hook\*\*: Injects execution logs or stack traces back into the conversation for the LLM to analyze.

\#\#\# C. The Memory (Postgres) \- \`/memory\`  
\- \*\*Semantic Path\*\*: Uses \`pgvector\` for "Project Knowledge." It remembers how your specific codebase is structured.  
\- \*\*Episodic Path\*\*: Uses LangGraph's \`PostgresSaver\` to store session checkpoints. You can close the TUI and resume your "thought" exactly where you left off.

\---

\#\# 4\. Directory Structure  
\`\`\`text  
/forge  
├── main.py              \# CLI Entrypoint (Typer-based)  
├── ARCHITECTURE.md      \# This document  
├── forge.css            \# TUI Stylesheet  
├── tui/  
│   ├── app.py           \# Main App Logic  
│   └── widgets.py       \# Custom Chat & Status components  
├── agent/  
│   ├── graph.py         \# LangGraph Definition  
│   ├── nodes.py         \# LLM & Logic Nodes  
│   └── hooks.py         \# Pre/Post Tool Execution Triggers  
├── memory/  
│   ├── manager.py       \# Postgres/pgvector client  
│   └── embeddings.py    \# Local embedding logic (via Ollama)  
└── tools/               \# Local "Skills" and MCP adapters

## ---

**5\. Implementation Roadmap for Codex**

### **Phase 1: The Core Loop**

* Initialize a Textual app with an input field and a display log.  
* Connect a basic LangGraph that sends user input to Ollama and renders the result.

### **Phase 2: Tooling & Hooks**

* Integrate MCP filesystem tools.  
* Add a "Pre-Hook" node that prints "Forge is preparing to write to file..." in the TUI before execution.

### **Phase 3: Project Memory**

* Set up Postgres with pgvector.  
* Implement a retrieval step that injects context into the system prompt based on similarity.

## ---

**6\. License**

**Apache License 2.0.**

Forge is open-source. Modification and redistribution are permitted, provided the original copyright and license are included.

\---

\#\#\# Why "Forge"?  
It fits the "Coding Agent" vibe—it's where you shape, hammer, and build your code. 

\*\*Next Step:\*\* Would you like me to write the \*\*\`main.py\`\*\* entry point for \*\*Forge\*\* so you can start testing the CLI flags and the basic TUI initialization?  
