// API and health check functions

import { MAIN_API, AIDER_API, getMainApiBase, dom } from './config.js';
import { state, setAvailableModels, setIsModelSwitching } from './state.js';
import { setCookie, COOKIE_KEYS } from './cookies.js';

export function toAiderModel(model) {
  if (!model) return '';
  if (model.startsWith('ollama_chat/') || model.startsWith('ollama/')) {
    return model;
  }
  return `ollama_chat/${model}`;
}

export async function checkHealth() {
  const healBtn = dom.healBtn || document.getElementById('heal-btn');
  const statusEl = dom.statusEl || document.getElementById('status');

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

export async function loadModels() {
  const modelSelectEl = dom.modelSelectEl || document.getElementById('model-select');
  const modelApplyBtn = dom.modelApplyBtn || document.getElementById('model-apply');

  modelSelectEl.disabled = true;
  modelApplyBtn.disabled = true;
  modelSelectEl.innerHTML = '<option value="">Loading...</option>';

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
    if (configRes && configRes.ok) {
      const configData = await configRes.json();
      currentAgentModel = configData.config?.agent_model || '';
    }

    if (!models.length) {
      modelSelectEl.innerHTML = '<option value="">No models found</option>';
      return;
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
  } catch (err) {
    console.warn('Failed to load models:', err.message);
    modelSelectEl.innerHTML = '<option value="">Model list unavailable</option>';
  }
}

export async function applyModelSelection(addMessage) {
  const modelSelectEl = dom.modelSelectEl || document.getElementById('model-select');
  const modelApplyBtn = dom.modelApplyBtn || document.getElementById('model-apply');
  const sendBtn = dom.sendBtn || document.getElementById('send');
  const promptEl = dom.promptEl || document.getElementById('prompt');
  const statusEl = dom.statusEl || document.getElementById('status');

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

export async function runFullHealthCheck(allowHeal) {
  const statusEl = dom.statusEl || document.getElementById('status');

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
