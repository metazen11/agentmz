// chat-git.js - Git operations

import { MAIN_API } from './config.js';
import { state } from './state.js';
import { addMessage } from './chat-core.js';

// Module-local DOM refs (populated in initGitElements)
let gitBranchSelectEl, gitBranchInputEl;
let gitRemoteSelectEl, gitRemoteNameEl, gitRemoteUrlEl;
let gitCurrentBranchEl, gitUserConfigEl, gitRemoteListEl;
let gitUserNameEl, gitUserEmailEl, gitLogEl;

// ============================================================================
// Init
// ============================================================================

export function initGitElements() {
  gitBranchSelectEl = document.getElementById('git-branch-select');
  gitBranchInputEl = document.getElementById('git-branch-input');
  gitRemoteSelectEl = document.getElementById('git-remote-select');
  gitRemoteNameEl = document.getElementById('git-remote-name');
  gitRemoteUrlEl = document.getElementById('git-remote-url');
  gitCurrentBranchEl = document.getElementById('git-current-branch');
  gitUserConfigEl = document.getElementById('git-user-config');
  gitRemoteListEl = document.getElementById('git-remote-list');
  gitUserNameEl = document.getElementById('git-user-name');
  gitUserEmailEl = document.getElementById('git-user-email');
  gitLogEl = document.getElementById('git-log');
}

// ============================================================================
// Git Modal
// ============================================================================

export function showGitModal() {
  if (!state.selectedProject) {
    alert('Select a project first');
    return;
  }
  document.getElementById('git-modal').style.display = 'flex';
  loadGitBranches(state.selectedProject.id);
}

export function hideGitModal() {
  document.getElementById('git-modal').style.display = 'none';
}

// ============================================================================
// Git Log
// ============================================================================

function appendGitLog(payload) {
  if (!gitLogEl || !payload) {
    return;
  }
  const stdout = (payload.stdout || '').trim();
  const stderr = (payload.stderr || '').trim();
  const lines = [];
  if (stdout) lines.push(stdout);
  if (stderr) lines.push(stderr);
  if (!lines.length) {
    lines.push('OK');
  }
  const stamp = new Date().toLocaleTimeString();
  const entry = `[${stamp}] ${lines.join('\\n')}`;
  gitLogEl.textContent = `${entry}\\n\\n${gitLogEl.textContent}`.trim();
}

// ============================================================================
// Git Branches
// ============================================================================

export async function loadGitBranches(projectId) {
  if (!projectId) {
    return;
  }
  gitBranchSelectEl.disabled = true;
  gitBranchSelectEl.innerHTML = '<option value="">Loading...</option>';
  try {
    const res = await fetch(`${MAIN_API}/projects/${projectId}/git/status`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    const branches = data.branches || [];
    if (!branches.length) {
      gitBranchSelectEl.innerHTML = '<option value="">No repo</option>';
      gitRemoteSelectEl.innerHTML = '<option value="">No remotes</option>';
      gitRemoteSelectEl.disabled = true;
      gitRemoteListEl.textContent = 'No remotes';
      gitCurrentBranchEl.textContent = 'Current branch: -';
      gitUserConfigEl.textContent = 'User: -';
      return;
    }
    gitBranchSelectEl.innerHTML = branches.map(branch => (
      `<option value="${branch}">${branch}</option>`
    )).join('');
    if (data.current) {
      gitBranchSelectEl.value = data.current;
    }
    gitBranchSelectEl.disabled = false;

    const remotes = data.remotes || [];
    if (remotes.length) {
      gitRemoteSelectEl.innerHTML = remotes.map(remote => (
        `<option value="${remote.name}">${remote.name}</option>`
      )).join('');
      gitRemoteSelectEl.disabled = false;
      gitRemoteListEl.innerHTML = remotes.map(remote => (
        `<div>${remote.name} → ${remote.url}</div>`
      )).join('');
    } else {
      gitRemoteSelectEl.innerHTML = '<option value="">No remotes</option>';
      gitRemoteSelectEl.disabled = true;
      gitRemoteListEl.textContent = 'No remotes';
    }

    gitCurrentBranchEl.textContent = `Current branch: ${data.current || '-'}`;
    const userName = data.user_name || 'unset';
    const userEmail = data.user_email || 'unset';
    gitUserConfigEl.textContent = `User: ${userName} <${userEmail}>`;
    gitUserNameEl.value = data.user_name || '';
    gitUserEmailEl.value = data.user_email || '';
  } catch (err) {
    gitBranchSelectEl.innerHTML = '<option value="">No repo</option>';
    gitRemoteSelectEl.innerHTML = '<option value="">No remotes</option>';
    gitRemoteSelectEl.disabled = true;
    gitRemoteListEl.textContent = 'No remotes';
    gitCurrentBranchEl.textContent = 'Current branch: -';
    gitUserConfigEl.textContent = 'User: -';
    gitUserNameEl.value = '';
    gitUserEmailEl.value = '';
    console.warn('Failed to load branches:', err.message);
  }
}

export async function checkoutBranch() {
  if (!state.selectedProject) {
    alert('Select a project first');
    return;
  }
  const branch = gitBranchSelectEl.value;
  if (!branch) {
    return;
  }
  try {
    const res = await fetch(`${MAIN_API}/projects/${state.selectedProject.id}/git/checkout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ branch })
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    const data = await res.json();
    addMessage('system', `Checked out branch: ${data.current || branch}`);
    appendGitLog(data);
    await loadGitBranches(state.selectedProject.id);
  } catch (err) {
    alert('Failed to checkout branch: ' + err.message);
  }
}

export async function createBranch() {
  if (!state.selectedProject) {
    alert('Select a project first');
    return;
  }
  const branch = gitBranchInputEl.value.trim();
  if (!branch) {
    return;
  }
  try {
    const res = await fetch(`${MAIN_API}/projects/${state.selectedProject.id}/git/checkout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ branch, create: true })
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    const data = await res.json();
    gitBranchInputEl.value = '';
    addMessage('system', `Created branch: ${data.current || branch}`);
    appendGitLog(data);
    await loadGitBranches(state.selectedProject.id);
  } catch (err) {
    alert('Failed to create branch: ' + err.message);
  }
}

export async function pullBranch() {
  if (!state.selectedProject) {
    alert('Select a project first');
    return;
  }
  const remote = gitRemoteSelectEl.value;
  try {
    const res = await fetch(`${MAIN_API}/projects/${state.selectedProject.id}/git/pull`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ remote })
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    const data = await res.json();
    addMessage('system', `Pulled from ${remote || 'origin'}`);
    appendGitLog(data);
  } catch (err) {
    alert('Failed to pull: ' + err.message);
  }
}

export async function pushBranch() {
  if (!state.selectedProject) {
    alert('Select a project first');
    return;
  }
  const remote = gitRemoteSelectEl.value;
  try {
    const res = await fetch(`${MAIN_API}/projects/${state.selectedProject.id}/git/push`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ remote })
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    const data = await res.json();
    addMessage('system', `Pushed to ${remote || 'origin'}`);
    appendGitLog(data);
  } catch (err) {
    alert('Failed to push: ' + err.message);
  }
}

export async function addRemote() {
  if (!state.selectedProject) {
    alert('Select a project first');
    return;
  }
  const name = gitRemoteNameEl.value.trim();
  const url = gitRemoteUrlEl.value.trim();
  if (!name || !url) {
    alert('Remote name and URL required');
    return;
  }
  try {
    const res = await fetch(`${MAIN_API}/projects/${state.selectedProject.id}/git/remote`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, url })
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    const data = await res.json();
    gitRemoteNameEl.value = '';
    gitRemoteUrlEl.value = '';
    addMessage('system', `Added remote: ${name}`);
    appendGitLog(data);
    await loadGitBranches(state.selectedProject.id);
  } catch (err) {
    alert('Failed to add remote: ' + err.message);
  }
}

export async function initGitRepo() {
  if (!state.selectedProject) {
    alert('Select a project first');
    return;
  }
  try {
    const res = await fetch(`${MAIN_API}/projects/${state.selectedProject.id}/git/init`, {
      method: 'POST'
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    const data = await res.json();
    addMessage('system', 'Initialized git repo');
    appendGitLog(data);
    await loadGitBranches(state.selectedProject.id);
  } catch (err) {
    alert('Failed to init repo: ' + err.message);
  }
}

export async function saveGitUser() {
  if (!state.selectedProject) {
    alert('Select a project first');
    return;
  }
  const name = gitUserNameEl.value.trim();
  const email = gitUserEmailEl.value.trim();
  if (!name || !email) {
    alert('User name and email required');
    return;
  }
  try {
    const res = await fetch(`${MAIN_API}/projects/${state.selectedProject.id}/git/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email })
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    const data = await res.json();
    addMessage('system', `Git user set: ${name} <${email}>`);
    appendGitLog(data);
    await loadGitBranches(state.selectedProject.id);
  } catch (err) {
    alert('Failed to save git user: ' + err.message);
  }
}
