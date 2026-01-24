// chat-agent.js - Agent execution, task runs, prompt building

import { MAIN_API } from './config.js';
import { COOKIE_KEYS, setCookie, deleteCookie, getWorkspaceName } from './cookies.js';
import { state, setVisionModel } from './state.js';
import {
  addMessage,
  buildVisionImageLayer,
  clearImages,
  setStatus,
  disableSendUI,
  getPromptValue,
  setPromptValue,
  getModelSelectValue,
  truncateText
} from './chat-core.js';
import {
  findTaskById,
  loadFileTree,
  loadTaskComments,
  loadTaskRuns,
  getEditingTaskId,
  hideModals,
  renderTasks
} from './chat-sidebar.js';

// Module-local DOM refs
let promptEl, sendBtn, statusEl, taskRunPreviewEl, visionModelSelectEl;

// ============================================================================
// Init
// ============================================================================

export function initAgentElements() {
  promptEl = document.getElementById('prompt');
  sendBtn = document.getElementById('send');
  statusEl = document.getElementById('status');
  taskRunPreviewEl = document.getElementById('task-run-preview');
  visionModelSelectEl = document.getElementById('vision-model-select');
}

// ============================================================================
// Task Context
// ============================================================================

export async function fetchTaskContext(taskId) {
  try {
    const res = await fetch(`${MAIN_API}/tasks/${taskId}/context`);
    if (!res.ok) {
      return null;
    }
    return await res.json();
  } catch (err) {
    console.warn('Failed to load task context:', err.message);
    return null;
  }
}

export function buildTaskRequest(task) {
  if (!task) return 'Execute the task using the provided context.';
  const title = (task.title || '').trim();
  const description = (task.description || '').trim();
  if (title && description) {
    return `${title}\n\n${description}`;
  }
  return title || description || 'Execute the task using the provided context.';
}

export async function buildPromptForRequest(taskId, requestText, imageLayer, concise = false) {
  const normalizedRequest = (requestText || '').trim()
    || 'Execute the task using the provided context.';
  if (!taskId) {
    return imageLayer
      ? `${imageLayer}\n\nREQUEST:\n${normalizedRequest}`
      : `REQUEST:\n${normalizedRequest}`;
  }
  try {
    const res = await fetch(`${MAIN_API}/tasks/${taskId}/prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        request: normalizedRequest,
        image_context: imageLayer || null,
        concise
      })
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    return data.prompt || '';
  } catch (err) {
    console.warn('Failed to build prompt:', err.message);
    const fallbackSections = [];
    try {
      const taskContext = await fetchTaskContext(taskId);
      if (taskContext?.node?.agent_prompt) {
        fallbackSections.push(`NODE_ROLE:\n${taskContext.node.agent_prompt}`);
      }
    } catch {
      // ignore
    }
    if (imageLayer) {
      fallbackSections.push(imageLayer);
    }
    fallbackSections.push(`REQUEST:\n${normalizedRequest}`);
    return fallbackSections.join('\n\n');
  }
}

// ============================================================================
// Task Runs
// ============================================================================

export async function createTaskRun(taskId, nodeId) {
  try {
    const res = await fetch(`${MAIN_API}/tasks/${taskId}/runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_id: nodeId })
    });
    if (!res.ok) {
      return null;
    }
    const run = await res.json();
    await refreshTaskRuns(taskId);
    return run;
  } catch (err) {
    console.warn('Failed to create task run:', err.message);
    return null;
  }
}

async function refreshTaskRuns(taskId) {
  if (getEditingTaskId() !== taskId) return;
  await loadTaskRuns(taskId);
}

export async function updateTaskRun(taskId, runId, payload) {
  if (!runId) return;
  try {
    await fetch(`${MAIN_API}/tasks/${taskId}/runs/${runId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    await refreshTaskRuns(taskId);
  } catch (err) {
    console.warn('Failed to update task run:', err.message);
  }
}

export async function postAgentComment(taskId, nodeLabel, runSummary = '', requestText = '') {
  const context = await fetchTaskContext(taskId);
  if (!context) return;
  const gitInfo = context.git || {};
  const gitSummary = gitInfo.last_commit_summary;
  const files = Array.isArray(gitInfo.last_commit_files) ? gitInfo.last_commit_files : [];
  const working = Array.isArray(gitInfo.working_changes) ? gitInfo.working_changes : [];

  const lines = [`Agent run (${nodeLabel})`];
  if (requestText) {
    lines.push(`Request: ${truncateText(requestText, 500)}`);
  }
  if (runSummary) lines.push(`Summary: ${runSummary}`);
  if (gitSummary) lines.push(`Last commit: ${gitSummary}`);
  if (files.length) lines.push(`Last commit files: ${files.join(', ')}`);
  if (working.length) {
    const workingList = working.map(item => `${item.status} ${item.path}`).join(', ');
    lines.push(`Working changes: ${workingList}`);
  }
  const body = lines.join('\n');

  try {
    const res = await fetch(`${MAIN_API}/tasks/${taskId}/comments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        author: `agent.${nodeLabel}`,
        body
      })
    });
    if (!res.ok) {
      return;
    }
    if (state.selectedTask?.id === taskId) {
      await loadTaskComments(taskId);
    }
  } catch (err) {
    console.warn('Failed to post agent comment:', err.message);
  }
}

// ============================================================================
// Agent Request
// ============================================================================

export async function runAgentRequest(requestText, task = null, imageLayer = '', options = {}) {
  const workspace = state.selectedProject
    ? getWorkspaceName(state.selectedProject.workspace_path)
    : 'poc';

  let runId = null;
  if (task?.id) {
    const run = await createTaskRun(task.id, task.node_id);
    runId = run?.id || null;
  }

  setStatus('Agent is working...', 'status connected');

  try {
    const concise = options.concise === true;
    const fullPrompt = options.promptOverride
      || await buildPromptForRequest(task?.id, requestText, imageLayer, concise);
    const res = await fetch(`${MAIN_API}/api/agent/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: fullPrompt,
        workspace,
        project_id: state.selectedProject?.id,
        chat_mode: options.chat_mode || false
      })
    });

    const data = await res.json();
    console.log('Agent response:', data);

    // Consider response OK if: explicit success, PASS status, or has a summary (chat responses)
    const ok = data.success || data.status === 'PASS' || (data.summary && !data.error);
    if (ok) {
      const responseText = data.summary || 'Task completed';
      addMessage('assistant', responseText, data.tool_calls);
      setStatus('Ready', 'status connected');
      if (state.selectedProject) loadFileTree(state.selectedProject.id);
      if (task?.id) {
        const nodeLabel = task.node_name || 'dev';
        await postAgentComment(task.id, nodeLabel, data.summary || '', requestText);
      }
      if (task?.id && runId) {
        await updateTaskRun(task.id, runId, {
          status: 'pass',
          summary: data.summary || null,
          tool_calls: data.tool_calls || null,
          finished_at: new Date().toISOString()
        });
      }
      return { ok: true, data };
    } else {
      addMessage('error', `Error: ${data.error || data.summary || 'Unknown error'}`);
      setStatus('Error - see output', 'status error');
      if (task?.id && runId) {
        await updateTaskRun(task.id, runId, {
          status: 'fail',
          error: data.error || data.summary || 'Unknown error',
          tool_calls: data.tool_calls || null,
          finished_at: new Date().toISOString()
        });
      }
    }
    return { ok: false, data };
  } catch (err) {
    console.error('Fetch error:', err);
    addMessage('error', 'Connection error: ' + err.message);
    setStatus('Connection failed', 'status error');
    if (task?.id && runId) {
      await updateTaskRun(task.id, runId, {
        status: 'fail',
        error: err.message,
        finished_at: new Date().toISOString()
      });
    }
    return { ok: false, error: err };
  }
}

// ============================================================================
// Task Execution
// ============================================================================

export async function buildTaskPromptPreview(buttonOrTaskId = null, taskId = null) {
  let buttonEl = null;
  let targetId = null;

  if (buttonOrTaskId instanceof HTMLElement) {
    buttonEl = buttonOrTaskId;
    targetId = taskId || getEditingTaskId();
  } else {
    targetId = buttonOrTaskId || getEditingTaskId();
  }

  if (!targetId) {
    alert('Select a task first');
    return '';
  }
  const task = findTaskById(targetId);
  if (!task) return '';
  const requestText = buildTaskRequest(task);
  const imageLayer = await buildVisionImageLayer();
  try {
    if (buttonEl) {
      buttonEl.disabled = true;
    }
    const prompt = await buildPromptForRequest(targetId, requestText, imageLayer, true);
    if (taskRunPreviewEl) {
      taskRunPreviewEl.value = prompt;
    }
    return prompt;
  } finally {
    if (buttonEl) {
      buttonEl.disabled = false;
    }
  }
}

export async function runTaskFromList(runButton, taskId) {
  if (state.isModelSwitching) {
    addMessage('system', 'Model is switching. Please wait...');
    return;
  }
  const buttonEl = runButton instanceof HTMLElement ? runButton : null;
  if (buttonEl) {
    buttonEl.disabled = true;
  }
  try {
    const task = findTaskById(taskId);
    if (!task) {
      addMessage('error', 'Task not found.');
      return;
    }
    // Import setSelectedTask dynamically to avoid circular dependency
    const { setSelectedTask } = await import('./state.js');
    setSelectedTask(task);
    renderTasks();
    const requestText = buildTaskRequest(task);
    addMessage('system', `Running task #${task.id}: ${task.title || 'Untitled task'}`);
    const imageLayer = await buildVisionImageLayer();
    const prompt = await buildPromptForRequest(task.id, requestText, imageLayer, true);
    if (getEditingTaskId() === task.id && taskRunPreviewEl) {
      taskRunPreviewEl.value = prompt;
    }
    return await runAgentRequest(requestText, task, imageLayer, {
      concise: true,
      promptOverride: prompt
    });
  } finally {
    if (buttonEl) {
      buttonEl.disabled = false;
    }
  }
}

export async function runTaskFromModal(taskId) {
  if (!taskId) return;
  const runBtn = document.getElementById('edit-task-run-btn');
  try {
    const result = await runTaskFromList(runBtn, taskId);
    if (result) {
      hideModals();
    }
  } finally {
    if (runBtn) {
      runBtn.disabled = false;
    }
  }
}

// ============================================================================
// Chat Message
// ============================================================================

export async function sendMessage() {
  if (state.isModelSwitching) {
    addMessage('system', 'Model is switching. Please wait...');
    return;
  }
  const text = getPromptValue().trim();
  if (!text) return;

  addMessage('user', text);
  setPromptValue('');
  disableSendUI(true);
  try {
    const imageLayer = await buildVisionImageLayer();
    await runAgentRequest(text, null, imageLayer, { chat_mode: true });
  } catch (err) {
    console.error('Send error:', err);
    addMessage('error', 'Connection error: ' + err.message);
  }

  disableSendUI(false);
  clearImages();
}

// ============================================================================
// Event Setup
// ============================================================================

export function setupAgentEventListeners() {
  if (sendBtn) {
    sendBtn.addEventListener('click', sendMessage);
  }
  if (promptEl) {
    promptEl.addEventListener('keypress', e => {
      if (e.key === 'Enter') sendMessage();
    });
    // Import syncReferencedFilesFromPrompt dynamically
    import('./chat-core.js').then(({ syncReferencedFilesFromPrompt }) => {
      promptEl.addEventListener('input', syncReferencedFilesFromPrompt);
    });
  }
  if (visionModelSelectEl) {
    visionModelSelectEl.addEventListener('change', () => {
      const selected = visionModelSelectEl.value;
      setVisionModel(selected);
      if (selected) {
        setCookie(COOKIE_KEYS.VISION_MODEL, selected);
      } else {
        deleteCookie(COOKIE_KEYS.VISION_MODEL);
      }
    });
  }
  // Close modals on escape
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') hideModals();
  });
}
