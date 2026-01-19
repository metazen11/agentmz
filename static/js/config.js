// Configuration and API endpoints

// API endpoints - use HTTPS proxy when served via *.localhost (Caddy)
export const IS_LOCAL_DOMAIN = window.location.hostname.endsWith('.localhost');
export const MAIN_API = IS_LOCAL_DOMAIN ? window.location.origin : 'http://localhost:8002';
export const AIDER_API = IS_LOCAL_DOMAIN ? `${window.location.origin}/aider` : 'http://localhost:8001';
export const HEALTH_CHECK_INTERVAL_MS = 30000;

export function getMainApiBase() {
  return MAIN_API;
}

// DOM element references - populated after DOMContentLoaded
export const dom = {};

export function initDom() {
  dom.messagesEl = document.getElementById('messages');
  dom.promptEl = document.getElementById('prompt');
  dom.sendBtn = document.getElementById('send');
  dom.statusEl = document.getElementById('status');
  dom.modelSelectEl = document.getElementById('model-select');
  dom.modelApplyBtn = document.getElementById('model-apply');
  dom.projectListEl = document.getElementById('project-list');
  dom.taskListEl = document.getElementById('task-list');
  dom.fileTreeEl = document.getElementById('file-tree');
  dom.gitBranchSelectEl = document.getElementById('git-branch-select');
  dom.gitBranchInputEl = document.getElementById('git-branch-input');
  dom.gitRemoteSelectEl = document.getElementById('git-remote-select');
  dom.gitRemoteNameEl = document.getElementById('git-remote-name');
  dom.gitRemoteUrlEl = document.getElementById('git-remote-url');
  dom.gitCurrentBranchEl = document.getElementById('git-current-branch');
  dom.gitUserConfigEl = document.getElementById('git-user-config');
  dom.gitRemoteListEl = document.getElementById('git-remote-list');
  dom.gitUserNameEl = document.getElementById('git-user-name');
  dom.gitUserEmailEl = document.getElementById('git-user-email');
  dom.gitLogEl = document.getElementById('git-log');
  dom.imageDropzoneEl = document.getElementById('image-dropzone');
  dom.imageInputEl = document.getElementById('image-input');
  dom.imageListEl = document.getElementById('image-list');
  dom.settingsListEl = document.getElementById('settings-list');
  dom.settingsFilterEl = document.getElementById('settings-filter');
  dom.restartMainEl = document.getElementById('restart-main');
  dom.restartAiderEl = document.getElementById('restart-aider');
  dom.restartOllamaEl = document.getElementById('restart-ollama');
  dom.restartDbEl = document.getElementById('restart-db');
  dom.healBtn = document.getElementById('heal-btn');
  dom.logsConnectionEl = document.getElementById('logs-connection');
  dom.logsContentEl = document.getElementById('logs-content');
}
