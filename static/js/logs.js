// Log streaming and display

import { getMainApiBase, MAIN_API } from './config.js';

// DOM elements (initialized after DOMContentLoaded)
let logsContentEl = null;
let logsConnectionEl = null;
let logPanes = {};

// State
let currentLogTab = 'ollama_http';
let logsCollapsed = false;
const logSockets = {};
const reconnectTimers = {};
const reconnectAttempts = {};
const MAX_RECONNECT_ATTEMPTS = 5;
const logSocketConnected = {};
const logPollingTimers = {};
const logLoadedOnce = {};
const LOG_POLL_INTERVAL_MS = 30000;

export function initLogElements() {
  logsContentEl = document.getElementById('logs-content');
  logsConnectionEl = document.getElementById('logs-connection');
  logPanes = {
    ollama: document.getElementById('log-pane-ollama'),
    ollama_http: document.getElementById('log-pane-ollama_http'),
    aider: document.getElementById('log-pane-aider'),
    main: document.getElementById('log-pane-main')
  };
}

export function getCurrentLogTab() {
  return currentLogTab;
}

export function toggleLogs() {
  logsCollapsed = !logsCollapsed;
  logsContentEl.classList.toggle('collapsed', logsCollapsed);
}

export function switchLogTab(tab) {
  // Update tab UI
  document.querySelectorAll('.logs-tabs button').forEach(btn => {
    btn.classList.remove('active');
  });
  document.getElementById(`tab-${tab}`).classList.add('active');

  Object.keys(logPanes).forEach(key => {
    logPanes[key].style.display = key === tab ? 'block' : 'none';
  });

  currentLogTab = tab;
  updateLogConnectionStatus(tab);

  if (!logLoadedOnce[tab]) {
    logPanes[tab].innerHTML = '<div class="log-line info">Loading recent logs for ' + tab + '...</div>';
    loadRecentLogs(tab, true);
  }

  if (!logSockets[tab] || logSockets[tab].readyState > 1) {
    connectLogStream(tab);
  }
}

export function connectLogStream(container) {
  if (logSockets[container] && logSockets[container].readyState <= 1) {
    return;
  }
  const baseUrl = new URL(getMainApiBase());
  const wsProtocol = baseUrl.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${wsProtocol}//${baseUrl.host}/ws/logs/${container}`;
  console.log('Connecting to WebSocket:', wsUrl);

  logSocketConnected[container] = false;
  updateLogConnectionStatus(container, 'connecting');

  try {
    logSockets[container] = new WebSocket(wsUrl);

    logSockets[container].onopen = () => {
      console.log('WebSocket connected:', container);
      reconnectAttempts[container] = 0;
      logSocketConnected[container] = true;
      updateLogConnectionStatus(container, 'connected');
    };

    logSockets[container].onmessage = (event) => {
      appendLogLine(event.data, '', container);
    };

    logSockets[container].onclose = (event) => {
      console.log('WebSocket closed:', container, event.code, event.reason);
      logSocketConnected[container] = false;
      updateLogConnectionStatus(container, 'disconnected');
      startLogPolling(container);

      // Auto-reconnect if not intentionally closed
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

    logSockets[container].onerror = (error) => {
      console.error('WebSocket error:', error);
      appendLogLine('WebSocket connection error - check if main-api can access Docker socket', 'error', container);
      logSocketConnected[container] = false;
      updateLogConnectionStatus(container, 'disconnected');
      startLogPolling(container);
    };
  } catch (err) {
    console.error('Failed to create WebSocket:', err);
    appendLogLine(`Failed to connect: ${err.message}`, 'error', container);
    logSocketConnected[container] = false;
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

export function startLogPolling(container) {
  if (logSocketConnected[container]) {
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

export function stopLogPolling(container) {
  const timer = logPollingTimers[container];
  if (timer) {
    clearInterval(timer);
    logPollingTimers[container] = null;
  }
}

export function appendLogLine(text, type = '', container = currentLogTab) {
  const line = document.createElement('div');
  line.className = 'log-line';

  // Auto-detect log level
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

  // Auto-scroll to bottom
  logsContentEl.scrollTop = logsContentEl.scrollHeight;

  // Keep only last 500 lines
  while (pane.children.length > 500) {
    pane.removeChild(pane.firstChild);
  }
}

export function updateLogConnectionStatus(container, forcedState = null) {
  if (container !== currentLogTab) {
    return;
  }
  const isConnected = forcedState === 'connected' || logSocketConnected[container];
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
