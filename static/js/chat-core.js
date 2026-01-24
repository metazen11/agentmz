// chat-core.js - Core messaging, initialization, health, models, and image handling

import { MAIN_API, AIDER_API, HEALTH_CHECK_INTERVAL_MS, getMainApiBase, initDom, dom } from './config.js';
import { COOKIE_KEYS, setCookie, getCookie, deleteCookie, getWorkspaceName } from './cookies.js';
import { renderMarkdown } from './markdown.js';
import { renderToolCalls } from './tools.js';
import { getResizedImageBase64 } from './images.js';
import {
  state,
  setAvailableModels,
  setIsModelSwitching,
  setVisionModel,
  setVisionImageMaxSize,
  setVisionModelRegex,
  setAttachedImages,
  setReferencedFiles,
  setIsSyncingReferencedFiles,
  setLogsCollapsed,
  setCurrentLogTab
} from './state.js';

// Module-local DOM refs (populated in initCoreElements)
let messagesEl, promptEl, sendBtn, statusEl;
let modelSelectEl, modelApplyBtn, visionModelSelectEl;
let fileTreeEl, imageListEl;
let logsContentEl, logsConnectionEl;
let logPanes = {};

// Log streaming state
const reconnectTimers = {};
const reconnectAttempts = {};
const MAX_RECONNECT_ATTEMPTS = 5;
const logPollingTimers = {};
const logLoadedOnce = {};
const LOG_POLL_INTERVAL_MS = 30000;

// ============================================================================
// Init & DOM
// ============================================================================

export function initCoreElements() {
  messagesEl = document.getElementById('messages');
  promptEl = document.getElementById('prompt');
  sendBtn = document.getElementById('send');
  statusEl = document.getElementById('status');
  modelSelectEl = document.getElementById('model-select');
  modelApplyBtn = document.getElementById('model-apply');
  visionModelSelectEl = document.getElementById('vision-model-select');
  fileTreeEl = document.getElementById('file-tree');
  imageListEl = document.getElementById('image-list');
  logsContentEl = document.getElementById('logs-content');
  logsConnectionEl = document.getElementById('logs-connection');
  logPanes = {
    ollama: document.getElementById('log-pane-ollama'),
    ollama_http: document.getElementById('log-pane-ollama_http'),
    aider: document.getElementById('log-pane-aider'),
    main: document.getElementById('log-pane-main')
  };
}

// ============================================================================
// Helper functions
// ============================================================================

export function formatDate(value) {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

export function truncateText(value, maxLength = 800) {
  if (!value) return '';
  return value;
}

export function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function renderTooltip(rows) {
  const items = rows.filter(Boolean).map(row => `
    <div class="tooltip-row">
      <span class="tooltip-label">${escapeHtml(row.label)}</span>
      <span class="tooltip-value">${escapeHtml(row.value)}</span>
    </div>
  `).join('');
  return `<div class="tooltip tooltip-source">${items}</div>`;
}

export function wireTooltipHandlers(container) {
  if (!container) return;
  const globalTooltipEl = document.getElementById('global-tooltip');
  if (!globalTooltipEl) return;
  container.querySelectorAll('.has-tooltip').forEach(item => {
    const tooltip = item.querySelector('.tooltip');
    if (!tooltip) return;
    item.addEventListener('mouseenter', () => {
      globalTooltipEl.innerHTML = tooltip.innerHTML;
      positionTooltip(item, globalTooltipEl);
      globalTooltipEl.classList.add('visible');
    });
    item.addEventListener('mouseleave', () => {
      globalTooltipEl.classList.remove('visible');
    });
  });
}

export function positionTooltip(item, tooltip) {
  const itemRect = item.getBoundingClientRect();
  const tooltipRect = tooltip.getBoundingClientRect();
  const padding = 12;
  const left = Math.min(
    itemRect.right + padding,
    window.innerWidth - tooltipRect.width - padding
  );
  const top = Math.min(
    itemRect.top,
    window.innerHeight - tooltipRect.height - padding
  );
  tooltip.style.left = `${Math.max(padding, left)}px`;
  tooltip.style.top = `${Math.max(padding, top)}px`;
}

export function hideGlobalTooltip() {
  const globalTooltipEl = document.getElementById('global-tooltip');
  if (globalTooltipEl) globalTooltipEl.classList.remove('visible');
}

// ============================================================================
// Messages
// ============================================================================

export function addMessage(type, content, toolCalls = null) {
  const div = document.createElement('div');
  div.className = 'message ' + type;

  if (type === 'assistant') {
    div.innerHTML = renderMarkdown(content);
    if (toolCalls && toolCalls.length > 0) {
      div.innerHTML += renderToolCalls(toolCalls);
    }
  } else {
    div.textContent = content;
  }

  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// ============================================================================
// Health Check
// ============================================================================

export async function checkHealth() {
  const healBtn = document.getElementById('heal-btn');
  try {
    const [mainRes, aiderRes] = await Promise.all([
      fetch(`${getMainApiBase()}/projects`).catch(() => null),
      fetch(`${AIDER_API}/health`).catch(() => null)
    ]);

    const mainOk = mainRes && mainRes.ok;
    const aiderOk = aiderRes && aiderRes.ok;

    if (mainOk && aiderOk) {
      const aiderData = await aiderRes.json();
      const modelLabel = aiderData.agent_model || aiderData.aider_model || 'ready';
      statusEl.textContent = state.isModelSwitching
        ? `Switching model...`
        : `Connected - Model: ${modelLabel}`;
      statusEl.className = 'status connected';
      healBtn.classList.remove('show');
    } else {
      const missing = [];
      if (!mainOk) missing.push('main-api:8002');
      if (!aiderOk) missing.push('aider-api:8001');
      statusEl.textContent = `Missing: ${missing.join(', ')}`;
      statusEl.className = 'status error';
      healBtn.classList.add('show');
    }
  } catch (err) {
    statusEl.textContent = 'Connection error';
    statusEl.className = 'status error';
    healBtn.classList.add('show');
  }
}

export async function runFullHealthCheck(allowHeal) {
  try {
    const res = await fetch(`${getMainApiBase()}/health/full`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    if (data.overall_status === 'ok') {
      return;
    }

    const autoHealTargets = [];
    if (data.aider_api?.status !== 'ok') {
      autoHealTargets.push('aider');
    }
    if (data.ollama?.status !== 'ok') {
      autoHealTargets.push('ollama');
    }

    if (allowHeal && autoHealTargets.length > 0) {
      statusEl.textContent = `Healing: ${autoHealTargets.join(', ')}`;
      statusEl.className = 'status error';
      await Promise.all(autoHealTargets.map(service => restartService(service)));
      await checkHealth();
    }
  } catch (err) {
    console.warn('Full health check failed:', err.message);
  }
}

export async function restartService(service) {
  try {
    const res = await fetch(`${getMainApiBase()}/ops/restart/${service}`, { method: 'POST' });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    return await res.json();
  } catch (err) {
    console.warn(`Restart ${service} failed:`, err.message);
    return null;
  }
}

// ============================================================================
// Models
// ============================================================================

function toAiderModel(model) {
  if (!model) return '';
  if (model.startsWith('ollama_chat/') || model.startsWith('ollama/')) {
    return model;
  }
  return `ollama_chat/${model}`;
}

function isLikelyVisionModel(model) {
  if (!model) return false;
  if (state.visionModelRegex) {
    try {
      const regex = new RegExp(state.visionModelRegex, 'i');
      return regex.test(model);
    } catch (err) {
      return false;
    }
  }
  return /(^|[\\/:_-])(vl|vision|llava|mllama|moondream|minicpm-v|qwen2\\.5vl|qwen2-vl|qwen-vl|clip)/i.test(model);
}

export async function loadModels() {
  modelSelectEl.disabled = true;
  modelApplyBtn.disabled = true;
  modelSelectEl.innerHTML = '<option value="">Loading...</option>';
  if (visionModelSelectEl) {
    visionModelSelectEl.disabled = true;
    visionModelSelectEl.innerHTML = '<option value="">Loading...</option>';
  }

  try {
    const [modelsRes, configRes] = await Promise.all([
      fetch(`${AIDER_API}/api/models`).catch(() => null),
      fetch(`${AIDER_API}/api/config`).catch(() => null)
    ]);

    let models = [];
    if (modelsRes && modelsRes.ok) {
      const modelsData = await modelsRes.json();
      if (modelsData.success && Array.isArray(modelsData.models)) {
        models = modelsData.models;
      }
    }

    let currentAgentModel = '';
    let currentVisionModel = '';
    let visionAllowlist = [];
    if (configRes && configRes.ok) {
      const configData = await configRes.json();
      currentAgentModel = configData.config?.agent_model || '';
      currentVisionModel = configData.config?.vision_model || '';
      visionAllowlist = Array.isArray(configData.config?.vision_models)
        ? configData.config.vision_models
        : [];
      setVisionImageMaxSize(parseInt(configData.config?.vision_image_max_size, 10) || state.visionImageMaxSize);
      setVisionModelRegex(configData.config?.vision_model_regex || state.visionModelRegex);
    }

    if (!models.length) {
      modelSelectEl.innerHTML = '<option value="">No models found</option>';
      if (visionModelSelectEl) {
        visionModelSelectEl.innerHTML = '<option value="">No models found</option>';
        visionModelSelectEl.disabled = true;
        setVisionModel('');
      }
      return;
    }

    if (currentAgentModel && models.includes(currentAgentModel)) {
      models = [currentAgentModel, ...models.filter(model => model !== currentAgentModel)];
    }
    setAvailableModels(models);
    modelSelectEl.innerHTML = models.map(model => (
      `<option value="${model}">${model}</option>`
    )).join('');
    modelSelectEl.disabled = false;
    modelApplyBtn.disabled = false;

    if (currentAgentModel && models.includes(currentAgentModel)) {
      modelSelectEl.value = currentAgentModel;
    }

    if (visionModelSelectEl) {
      const visionModels = visionAllowlist.length
        ? models.filter(model => visionAllowlist.includes(model))
        : models.filter(model => isLikelyVisionModel(model));

      if (!visionModels.length) {
        visionModelSelectEl.innerHTML = '<option value="">No vision models found</option>';
        visionModelSelectEl.disabled = true;
        setVisionModel('');
        return;
      }

      visionModelSelectEl.innerHTML = visionModels.map(model => (
        `<option value="${model}">${model}</option>`
      )).join('');
      visionModelSelectEl.disabled = false;

      const savedVisionModel = getCookie(COOKIE_KEYS.VISION_MODEL);
      const selectedVisionModel = (
        (savedVisionModel && visionModels.includes(savedVisionModel) && savedVisionModel)
        || (currentVisionModel && visionModels.includes(currentVisionModel) && currentVisionModel)
        || visionModels[0]
      );
      visionModelSelectEl.value = selectedVisionModel;
      setVisionModel(selectedVisionModel);
    }
  } catch (err) {
    console.warn('Failed to load models:', err.message);
    modelSelectEl.innerHTML = '<option value="">Model list unavailable</option>';
    if (visionModelSelectEl) {
      visionModelSelectEl.innerHTML = '<option value="">Model list unavailable</option>';
      visionModelSelectEl.disabled = true;
      setVisionModel('');
    }
  }
}

export async function applyModelSelection() {
  const selectedModel = modelSelectEl.value;
  if (!selectedModel) {
    return;
  }

  setIsModelSwitching(true);
  modelApplyBtn.disabled = true;
  modelSelectEl.disabled = true;
  sendBtn.disabled = true;
  promptEl.disabled = true;
  statusEl.textContent = 'Switching model...';
  statusEl.className = 'status connected';
  try {
    const res = await fetch(`${AIDER_API}/api/model/switch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: selectedModel,
        timeout: 120
      })
    });

    const data = await res.json();
    if (!res.ok || data.success === false) {
      throw new Error(data.error || `HTTP ${res.status}`);
    }

    const loadedModel = data.loaded_model || selectedModel;
    const prevModel = data.previous_model || 'unknown';
    addMessage('system', `Model switched: ${prevModel} → ${loadedModel}\nAgent: ${data.agent_model}\nAider: ${data.aider_model}`);

    setCookie(COOKIE_KEYS.MODEL, loadedModel);
    setIsModelSwitching(false);
    await checkHealth();
  } catch (err) {
    addMessage('error', `Failed to set model: ${err.message}`);
    setIsModelSwitching(false);
    await checkHealth();
  } finally {
    modelApplyBtn.disabled = false;
    modelSelectEl.disabled = false;
    sendBtn.disabled = false;
    promptEl.disabled = false;
  }
}

export async function switchAgentModel(model, label) {
  const res = await fetch(`${AIDER_API}/api/model/switch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, timeout: 120 })
  });
  const data = await res.json();
  if (!res.ok || data.success === false) {
    throw new Error(data.error || `HTTP ${res.status}`);
  }
  addMessage('system', `${label} model loaded: ${data.loaded_model || model}`);
  return data;
}

// ============================================================================
// Vision / Images
// ============================================================================

export async function describeImages(images) {
  const results = [];
  for (const img of images) {
    const base64 = await getResizedImageBase64(img.dataUrl || '', state.visionImageMaxSize);
    if (!base64) {
      results.push({
        name: img.name,
        location: img.name,
        description: null,
        error: 'invalid data'
      });
      continue;
    }
    try {
      const payload = {
        filename: img.name,
        data: base64,
        compact: true
      };
      if (state.visionModel) {
        payload.model = state.visionModel;
      }
      const res = await fetch(`${AIDER_API}/api/vision/describe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok && data.success && data.description) {
        results.push({
          name: img.name,
          location: img.name,
          description: data.description,
          error: null
        });
      } else {
        results.push({
          name: img.name,
          location: img.name,
          description: null,
          error: data.error || 'vision model not configured'
        });
      }
    } catch (err) {
      results.push({
        name: img.name,
        location: img.name,
        description: null,
        error: err.message
      });
    }
  }
  return results;
}

export function buildImageContextLayer(descriptions) {
  const context = {};
  descriptions.forEach((entry, index) => {
    const key = entry.name || `image_${index + 1}`;
    const description = entry.description
      ? entry.description
      : `Description unavailable (${entry.error || 'unknown'})`;
    context[key] = {
      location: entry.location || entry.name || key,
      description
    };
  });
  return `IMAGE_CONTEXT:\n${JSON.stringify(context, null, 2)}`;
}

export async function buildVisionImageLayer() {
  if (state.attachedImages.length === 0) return '';
  const activeModel = modelSelectEl.value || '';
  const visionModel = state.visionModel || '';
  let switched = false;
  if (visionModel && activeModel && visionModel !== activeModel) {
    statusEl.textContent = `Loading vision model: ${visionModel}...`;
    statusEl.className = 'status connected';
    try {
      await switchAgentModel(visionModel, 'Vision');
      switched = true;
    } catch (err) {
      addMessage('error', `Vision model switch failed: ${err.message}`);
    }
  }

  const imageDescriptions = await describeImages(state.attachedImages);
  let imageLayer = '';
  if (imageDescriptions.length > 0) {
    imageLayer = buildImageContextLayer(imageDescriptions);
  }

  if (switched && activeModel) {
    statusEl.textContent = `Restoring model: ${activeModel}...`;
    statusEl.className = 'status connected';
    try {
      await switchAgentModel(activeModel, 'Primary');
    } catch (err) {
      addMessage('error', `Failed to restore model: ${err.message}`);
    }
  }

  return imageLayer;
}

// ============================================================================
// Image handling
// ============================================================================

export function setupImageDropzone() {
  const imageDropzoneEl = document.getElementById('image-dropzone');
  const imageInputEl = document.getElementById('image-input');
  if (!imageDropzoneEl || !imageInputEl) {
    return;
  }
  imageDropzoneEl.addEventListener('dragover', (event) => {
    event.preventDefault();
    imageDropzoneEl.classList.add('dragover');
  });
  imageDropzoneEl.addEventListener('dragleave', () => {
    imageDropzoneEl.classList.remove('dragover');
  });
  imageDropzoneEl.addEventListener('drop', (event) => {
    event.preventDefault();
    imageDropzoneEl.classList.remove('dragover');
    const files = Array.from(event.dataTransfer.files || []);
    handleImageFiles(files);
  });
  imageInputEl.addEventListener('change', (event) => {
    const files = Array.from(event.target.files || []);
    handleImageFiles(files);
    imageInputEl.value = '';
  });
}

export function openImagePicker() {
  const imageInputEl = document.getElementById('image-input');
  if (imageInputEl) {
    imageInputEl.click();
  }
}

export function handleImageFiles(files) {
  const images = files.filter(file => file.type.startsWith('image/'));
  images.forEach(file => {
    const reader = new FileReader();
    reader.onload = () => {
      setAttachedImages([
        ...state.attachedImages,
        {
          name: file.name,
          dataUrl: reader.result
        }
      ]);
      renderImageList();
    };
    reader.readAsDataURL(file);
  });
}

export function renderImageList() {
  if (!imageListEl) return;
  if (state.attachedImages.length === 0) {
    imageListEl.innerHTML = '';
    return;
  }
  imageListEl.innerHTML = state.attachedImages.map((img, idx) => `
    <span class="image-chip">
      ${escapeHtml(img.name)}
      <button onclick="removeImage(${idx})">×</button>
    </span>
  `).join('');
}

export function removeImage(index) {
  setAttachedImages(state.attachedImages.filter((_, idx) => idx !== index));
  renderImageList();
}

export function clearImages() {
  setAttachedImages([]);
  renderImageList();
}

// ============================================================================
// File references
// ============================================================================

export function addFileReference(path) {
  if (!path) {
    return;
  }
  if (state.referencedFiles.includes(path)) {
    return;
  }
  setReferencedFiles([...state.referencedFiles, path]);
  renderFileReferences();
}

export function removeFileReference(path) {
  setReferencedFiles(state.referencedFiles.filter(item => item !== path));
  renderFileReferences();
}

function extractReferencedFileNames(text = '') {
  const matches = [];
  const regex = /@([^\s]+)/g;
  let match;
  while ((match = regex.exec(text)) !== null) {
    matches.push(match[1]);
  }
  return Array.from(new Set(matches));
}

function areReferenceListsEqual(a, b) {
  if (a.length !== b.length) {
    return false;
  }
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) {
      return false;
    }
  }
  return true;
}

export function syncReferencedFilesFromPrompt() {
  if (state.isSyncingReferencedFiles) {
    return;
  }
  const parsed = extractReferencedFileNames(promptEl.value);
  if (areReferenceListsEqual(parsed, state.referencedFiles)) {
    return;
  }
  setReferencedFiles(parsed);
  renderFileReferences();
}

export function renderFileReferences() {
  let refsEl = document.getElementById('file-references');
  if (!refsEl) {
    refsEl = document.createElement('div');
    refsEl.id = 'file-references';
    refsEl.className = 'file-references';
    fileTreeEl.appendChild(refsEl);
  }

  if (state.referencedFiles.length === 0) {
    refsEl.innerHTML = '';
    return;
  }

  refsEl.innerHTML = `
    <div class="file-references-title">File References</div>
    <div class="file-references-list">
      ${state.referencedFiles.map(path => `
        <span class="file-ref-chip" title="${escapeHtml(path)}">
          ${escapeHtml(path)}
          <button class="file-ref-remove" onclick="removeFileReference('${path}')">×</button>
        </span>
      `).join('')}
    </div>
  `;

  const tokens = state.referencedFiles.map(path => `@${path}`).join(' ');
  const text = promptEl.value.trim();
  const cleaned = text
    .replace(/(^|\s)@[^\s]+/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
  const prevSyncFlag = state.isSyncingReferencedFiles;
  setIsSyncingReferencedFiles(true);
  promptEl.value = cleaned ? `${cleaned} ${tokens}` : tokens;
  setIsSyncingReferencedFiles(prevSyncFlag);
}

// ============================================================================
// Logs
// ============================================================================

export function toggleLogs() {
  setLogsCollapsed(!state.logsCollapsed);
  logsContentEl.classList.toggle('collapsed', state.logsCollapsed);
}

export function switchLogTab(tab) {
  document.querySelectorAll('.logs-tabs button').forEach(btn => {
    btn.classList.remove('active');
  });
  document.getElementById(`tab-${tab}`).classList.add('active');

  Object.keys(logPanes).forEach(key => {
    logPanes[key].style.display = key === tab ? 'block' : 'none';
  });

  setCurrentLogTab(tab);
  updateLogConnectionStatus(tab);

  if (!logLoadedOnce[tab]) {
    logPanes[tab].innerHTML = '<div class="log-line info">Loading recent logs for ' + tab + '...</div>';
    loadRecentLogs(tab, true);
  }

  if (!state.logSockets[tab] || state.logSockets[tab].readyState > 1) {
    connectLogStream(tab);
  }
}

export function connectLogStream(container) {
  if (state.logSockets[container] && state.logSockets[container].readyState <= 1) {
    return;
  }
  const baseUrl = new URL(getMainApiBase());
  const wsProtocol = baseUrl.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${wsProtocol}//${baseUrl.host}/ws/logs/${container}`;
  console.log('Connecting to WebSocket:', wsUrl);

  state.logSocketConnected[container] = false;
  updateLogConnectionStatus(container, 'connecting');

  try {
    state.logSockets[container] = new WebSocket(wsUrl);

    state.logSockets[container].onopen = () => {
      console.log('WebSocket connected:', container);
      reconnectAttempts[container] = 0;
      state.logSocketConnected[container] = true;
      updateLogConnectionStatus(container, 'connected');
    };

    state.logSockets[container].onmessage = (event) => {
      appendLogLine(event.data, '', container);
    };

    state.logSockets[container].onclose = (event) => {
      console.log('WebSocket closed:', container, event.code, event.reason);
      state.logSocketConnected[container] = false;
      updateLogConnectionStatus(container, 'disconnected');
      startLogPolling(container);

      if ((reconnectAttempts[container] || 0) < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttempts[container] = (reconnectAttempts[container] || 0) + 1;
        const delay = Math.min(1000 * reconnectAttempts[container], 5000);
        appendLogLine(
          `Connection lost. Reconnecting in ${delay/1000}s... (attempt ${reconnectAttempts[container]}/${MAX_RECONNECT_ATTEMPTS})`,
          'warn',
          container
        );
        reconnectTimers[container] = setTimeout(() => connectLogStream(container), delay);
      }
    };

    state.logSockets[container].onerror = (error) => {
      console.error('WebSocket error:', error);
      appendLogLine('WebSocket connection error - check if main-api can access Docker socket', 'error', container);
      state.logSocketConnected[container] = false;
      updateLogConnectionStatus(container, 'disconnected');
      startLogPolling(container);
    };
  } catch (err) {
    console.error('Failed to create WebSocket:', err);
    appendLogLine(`Failed to connect: ${err.message}`, 'error', container);
    state.logSocketConnected[container] = false;
    updateLogConnectionStatus(container, 'disconnected');
    startLogPolling(container);
  }
}

export async function loadRecentLogs(container, replace = false) {
  try {
    const res = await fetch(`${MAIN_API}/logs/${container}?lines=200`);
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    const data = await res.json();
    const lines = (data.logs || '').split('\n').filter(Boolean);
    if (replace) {
      logPanes[container].innerHTML = '';
    }
    if (lines.length === 0) {
      appendLogLine('No recent logs available.', 'info', container);
    } else if (replace) {
      lines.forEach(line => appendLogLine(line, '', container));
    }
    logLoadedOnce[container] = true;
  } catch (err) {
    logPanes[container].innerHTML = '';
    appendLogLine(`Failed to load logs: ${err.message}`, 'error', container);
  }
}

function startLogPolling(container) {
  if (state.logSocketConnected[container]) {
    return;
  }
  if (logPollingTimers[container]) {
    return;
  }
  loadRecentLogs(container, true);
  logPollingTimers[container] = setInterval(
    () => loadRecentLogs(container, true),
    LOG_POLL_INTERVAL_MS
  );
}

export function appendLogLine(text, type = '', container = state.currentLogTab) {
  const line = document.createElement('div');
  line.className = 'log-line';

  if (!type) {
    if (text.includes('ERROR') || text.includes('error') || text.includes('Error')) {
      type = 'error';
    } else if (text.includes('WARN') || text.includes('warn') || text.includes('Warning')) {
      type = 'warn';
    } else if (text.includes('INFO') || text.includes('===')) {
      type = 'info';
    }
  }

  if (type) {
    line.classList.add(type);
  }

  line.textContent = text;
  const pane = logPanes[container] || logsContentEl;
  pane.appendChild(line);

  logsContentEl.scrollTop = logsContentEl.scrollHeight;

  while (pane.children.length > 500) {
    pane.removeChild(pane.firstChild);
  }
}

export function updateLogConnectionStatus(container, forcedState = null) {
  if (container !== state.currentLogTab) {
    return;
  }
  const isConnected = forcedState === 'connected' || state.logSocketConnected[container];
  const isConnecting = forcedState === 'connecting';
  if (isConnecting) {
    logsConnectionEl.textContent = `${container} connecting...`;
    logsConnectionEl.className = 'connection-status connecting';
  } else if (isConnected) {
    logsConnectionEl.textContent = `${container} connected`;
    logsConnectionEl.className = 'connection-status connected';
  } else {
    logsConnectionEl.textContent = 'disconnected';
    logsConnectionEl.className = 'connection-status disconnected';
  }
}

// ============================================================================
// Exports for use by other modules
// ============================================================================

export function getPromptValue() {
  return promptEl?.value || '';
}

export function setPromptValue(value) {
  if (promptEl) promptEl.value = value;
}

export function setStatus(text, className = 'status connected') {
  if (statusEl) {
    statusEl.textContent = text;
    statusEl.className = className;
  }
}

export function disableSendUI(disabled) {
  if (sendBtn) sendBtn.disabled = disabled;
  if (promptEl) promptEl.disabled = disabled;
}

export function getModelSelectValue() {
  return modelSelectEl?.value || '';
}
