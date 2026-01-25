// terminal.js - WebSocket terminal access for containers

import { getMainApiBase } from './config.js';
import { state } from './state.js';

let terminalBodyEl;
let terminalOutputEl;
let terminalInputEl;
let terminalStatusEl;
let terminalContainerEl;

let terminalSocket = null;
let terminalConnected = false;

const MAX_TERMINAL_BUFFER = 200000;

export function initTerminalElements() {
  terminalBodyEl = document.getElementById('terminal-body');
  terminalOutputEl = document.getElementById('terminal-output');
  terminalInputEl = document.getElementById('terminal-input');
  terminalStatusEl = document.getElementById('terminal-connection');
  terminalContainerEl = document.getElementById('terminal-container');
}

function buildTerminalQuery(container) {
  const params = new URLSearchParams();
  if (state.currentWorkspacePath) {
    params.set('workspace', state.currentWorkspacePath);
  }
  if (container === 'ollama' || container === 'db') {
    params.set('shell', 'sh');
  }
  return params.toString();
}

function updateTerminalStatus(status, label) {
  if (!terminalStatusEl) return;
  terminalStatusEl.classList.remove('connected', 'disconnected', 'connecting');
  terminalStatusEl.classList.add(status);
  terminalStatusEl.textContent = label || status;
}

function appendTerminalOutput(text) {
  if (!terminalOutputEl) return;
  terminalOutputEl.textContent += text;
  if (terminalOutputEl.textContent.length > MAX_TERMINAL_BUFFER) {
    terminalOutputEl.textContent = terminalOutputEl.textContent.slice(-MAX_TERMINAL_BUFFER);
  }
  terminalOutputEl.scrollTop = terminalOutputEl.scrollHeight;
}

export function toggleTerminal() {
  if (!terminalBodyEl) return;
  terminalBodyEl.classList.toggle('collapsed');
}

export function connectTerminal() {
  if (!terminalContainerEl) return;
  if (terminalSocket && terminalSocket.readyState <= 1) {
    return;
  }

  const container = terminalContainerEl.value || 'aider';
  const baseUrl = new URL(getMainApiBase());
  const wsProtocol = baseUrl.protocol === 'https:' ? 'wss:' : 'ws:';
  const query = buildTerminalQuery(container);
  const wsUrl = `${wsProtocol}//${baseUrl.host}/ws/terminal/${container}${query ? `?${query}` : ''}`;

  updateTerminalStatus('connecting', 'connecting');
  appendTerminalOutput(`\n[connecting] ${container}\n`);

  try {
    terminalSocket = new WebSocket(wsUrl);
  } catch (err) {
    updateTerminalStatus('disconnected', 'disconnected');
    appendTerminalOutput(`[error] ${err.message}\n`);
    return;
  }

  terminalSocket.onopen = () => {
    terminalConnected = true;
    updateTerminalStatus('connected', 'connected');
  };

  terminalSocket.onmessage = (event) => {
    appendTerminalOutput(event.data);
  };

  terminalSocket.onclose = () => {
    terminalConnected = false;
    updateTerminalStatus('disconnected', 'disconnected');
    appendTerminalOutput('\n[disconnected]\n');
  };

  terminalSocket.onerror = () => {
    terminalConnected = false;
    updateTerminalStatus('disconnected', 'disconnected');
  };
}

export function disconnectTerminal() {
  if (terminalSocket) {
    terminalSocket.close();
    terminalSocket = null;
  }
  terminalConnected = false;
  updateTerminalStatus('disconnected', 'disconnected');
}

export function clearTerminal() {
  if (terminalOutputEl) {
    terminalOutputEl.textContent = '';
  }
}

export function sendTerminalInput() {
  if (!terminalInputEl) return;
  const value = terminalInputEl.value;
  if (!value.trim()) return;

  if (!terminalSocket || terminalSocket.readyState !== WebSocket.OPEN) {
    appendTerminalOutput('[error] terminal not connected\n');
    return;
  }

  const payload = JSON.stringify({ type: 'input', data: `${value}\n` });
  terminalSocket.send(payload);
  terminalInputEl.value = '';
}

export function handleTerminalInput(event) {
  if (event.key === 'Enter') {
    event.preventDefault();
    sendTerminalInput();
  }
}
