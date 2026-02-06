// chat-agent.js - Agent execution, task runs, prompt building

import { MAIN_API } from './config.js';
import { COOKIE_KEYS, setCookie, deleteCookie, getCookie, getWorkspaceName } from './cookies.js';
import { state, setVisionModel, setUseAiderCli } from './state.js';
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
let promptEl, sendBtn, statusEl, taskRunPreviewEl, visionModelSelectEl, aiderCliToggleEl;

// ============================================================================
// Init
// ============================================================================

export function initAgentElements() {
  promptEl = document.getElementById('prompt');
  sendBtn = document.getElementById('send');
  statusEl = document.getElementById('status');
  taskRunPreviewEl = document.getElementById('task-run-preview');
  visionModelSelectEl = document.getElementById('vision-model-select');
  aiderCliToggleEl = document.getElementById('aider-cli-toggle');
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

// Animated status for long-running tasks
let statusAnimationInterval = null;
function startWorkingAnimation() {
  const frames = ['Agent is working', 'Agent is working.', 'Agent is working..', 'Agent is working...'];
  let frameIndex = 0;
  stopWorkingAnimation();
  statusAnimationInterval = setInterval(() => {
    setStatus(frames[frameIndex % frames.length], 'status connected');
    frameIndex++;
  }, 500);
}

function stopWorkingAnimation() {
  if (statusAnimationInterval) {
    clearInterval(statusAnimationInterval);
    statusAnimationInterval = null;
  }
}

// Check if agent is still active by pinging logs
async function isAgentStillWorking() {
  try {
    const res = await fetch(`${MAIN_API}/api/logs/aider?tail=5`, { timeout: 2000 });
    if (res.ok) {
      const data = await res.json();
      // If there are recent log entries (within last 30s), agent is likely working
      return data.lines && data.lines.length > 0;
    }
  } catch {
    // Ignore - just assume not working
  }
  return false;
}

export async function runAgentRequest(requestText, task = null, imageLayer = '', options = {}) {
  const workspace = state.selectedProject
    ? getWorkspaceName(state.selectedProject.workspace_path)
    : 'poc';

  let runId = null;
  if (task?.id) {
    const run = await createTaskRun(task.id, task.node_id);
    runId = run?.id || null;
  }

  startWorkingAnimation();

  try {
    const concise = options.concise === true;
    const fullPrompt = options.promptOverride
      || await buildPromptForRequest(task?.id, requestText, imageLayer, concise);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 300000); // 5 min timeout

    const res = await fetch(`${MAIN_API}/api/agent/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: fullPrompt,
        workspace,
        project_id: state.selectedProject?.id,
        chat_mode: options.chat_mode || false,
        use_aider_cli: state.useAiderCli === true
      }),
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    const data = await res.json();
    console.log('Agent response:', data);

    // Consider response OK if: explicit success, PASS status, or has a summary (chat responses)
    const ok = data.success || data.status === 'PASS' || (data.summary && !data.error);
    if (ok) {
      stopWorkingAnimation();
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
      stopWorkingAnimation();
      const errorMsg = data.error || data.summary || 'Request failed - check logs for details';
      addMessage('error', `Error: ${errorMsg}`);
      setStatus('Error - see output', 'status error');
      if (task?.id && runId) {
        await updateTaskRun(task.id, runId, {
          status: 'fail',
          error: errorMsg,
          tool_calls: data.tool_calls || null,
          finished_at: new Date().toISOString()
        });
      }
    }
    return { ok: false, data };
  } catch (err) {
    stopWorkingAnimation();
    console.error('Fetch error:', err);

    // Handle different error types
    let errorMsg;
    let statusMsg;

    if (err.name === 'AbortError') {
      // Timeout - check if agent is still working
      const stillWorking = await isAgentStillWorking();
      if (stillWorking) {
        errorMsg = 'Request is taking longer than expected. The agent is still working - check the logs panel for progress.';
        statusMsg = 'Still working - check logs';
      } else {
        errorMsg = 'Request timed out. The agent may have encountered an issue - check the logs for details.';
        statusMsg = 'Timeout - check logs';
      }
    } else if (err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
      errorMsg = 'Connection lost. Check if the server is running.';
      statusMsg = 'Connection lost';
    } else {
      errorMsg = err.message || 'An unexpected error occurred';
      statusMsg = 'Error - see output';
    }

    addMessage('error', errorMsg);
    setStatus(statusMsg, 'status error');

    if (task?.id && runId) {
      await updateTaskRun(task.id, runId, {
        status: 'fail',
        error: errorMsg,
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
  if (aiderCliToggleEl) {
    const saved = getCookie(COOKIE_KEYS.AIDER_CLI);
    const enabled = saved === null ? true : saved === '1';
    aiderCliToggleEl.checked = enabled;
    setUseAiderCli(enabled);
    if (saved === null && enabled) {
      setCookie(COOKIE_KEYS.AIDER_CLI, '1');
    }
    aiderCliToggleEl.addEventListener('change', () => {
      const isEnabled = aiderCliToggleEl.checked;
      setUseAiderCli(isEnabled);
      if (isEnabled) {
        setCookie(COOKIE_KEYS.AIDER_CLI, '1');
      } else {
        deleteCookie(COOKIE_KEYS.AIDER_CLI);
      }
    });
  }
  // Close modals on escape
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') hideModals();
  });
}
