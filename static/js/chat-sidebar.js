// chat-sidebar.js - Projects, tasks, file tree, comments, criteria, attachments, settings, nodes

import { MAIN_API, AIDER_API } from './config.js';
import { COOKIE_KEYS, setCookie, getCookie, deleteCookie, getWorkspaceName } from './cookies.js';
import {
  state,
  setProjects,
  setTasks,
  setSelectedProject,
  setSelectedTask,
  setEditingProjectId,
  setEditingTaskId,
  setTaskComments,
  setTaskAttachments,
  setTaskRuns,
  setTaskCriteria,
  setNewTaskCriteria,
  setEditingCommentId,
  setPendingParentTaskId,
  setEnvEntries,
  setNodes,
  setSelectedNodeId,
  setAvailableNodes,
  setCurrentSettingsTab
} from './state.js';
import {
  addMessage,
  formatDate,
  truncateText,
  escapeHtml,
  renderTooltip,
  wireTooltipHandlers,
  hideGlobalTooltip,
  addFileReference
} from './chat-core.js';
import { loadGitBranches } from './chat-git.js';

// Module-local DOM refs
let projectListEl, taskListEl, fileTreeEl, fileTreeContent;
let settingsListEl, settingsFilterEl;
let restartMainEl, restartAiderEl, restartOllamaEl, restartDbEl;
let taskCommentsListEl, commentAuthorEl, commentBodyEl, commentIdEl;
let taskAttachmentsListEl, attachmentFileEl, attachmentUploadedByEl, attachmentCommentIdEl;
let taskRunsListEl, taskRunPreviewEl, subtaskListEl;
let criteriaListEl, criteriaDescEl, criteriaAuthorEl;
let newTaskCriteriaListEl, newTaskCriteriaDescEl;
let newTaskParentRowEl, newTaskParentSelectEl, editTaskParentRowEl, editTaskParentLinkEl;
let newTaskNodeSelectEl, editTaskNodeSelectEl;

// ============================================================================
// Init
// ============================================================================

export function initSidebarElements() {
  projectListEl = document.getElementById('project-list');
  taskListEl = document.getElementById('task-list');
  fileTreeEl = document.getElementById('file-tree');
  fileTreeContent = document.getElementById('file-tree-content');
  settingsListEl = document.getElementById('settings-list');
  settingsFilterEl = document.getElementById('settings-filter');
  restartMainEl = document.getElementById('restart-main');
  restartAiderEl = document.getElementById('restart-aider');
  restartOllamaEl = document.getElementById('restart-ollama');
  restartDbEl = document.getElementById('restart-db');
  taskCommentsListEl = document.getElementById('task-comments-list');
  commentAuthorEl = document.getElementById('comment-author');
  commentBodyEl = document.getElementById('comment-body');
  commentIdEl = document.getElementById('comment-id');
  taskAttachmentsListEl = document.getElementById('task-attachments-list');
  attachmentFileEl = document.getElementById('attachment-file');
  attachmentUploadedByEl = document.getElementById('attachment-uploaded-by');
  attachmentCommentIdEl = document.getElementById('attachment-comment-id');
  taskRunsListEl = document.getElementById('task-runs-list');
  taskRunPreviewEl = document.getElementById('task-run-preview');
  subtaskListEl = document.getElementById('subtask-list');
  criteriaListEl = document.getElementById('task-criteria-list');
  criteriaDescEl = document.getElementById('criteria-desc');
  criteriaAuthorEl = document.getElementById('criteria-author');
  newTaskCriteriaListEl = document.getElementById('new-task-criteria-list');
  newTaskCriteriaDescEl = document.getElementById('new-criteria-desc');
  newTaskParentRowEl = document.getElementById('new-task-parent-row');
  newTaskParentSelectEl = document.getElementById('new-task-parent-id');
  editTaskParentRowEl = document.getElementById('edit-task-parent-row');
  editTaskParentLinkEl = document.getElementById('edit-task-parent-link');
  newTaskNodeSelectEl = document.getElementById('new-task-node');
  editTaskNodeSelectEl = document.getElementById('edit-task-node');

  // Add filter listener for settings
  if (settingsFilterEl) {
    settingsFilterEl.addEventListener('input', renderSettings);
  }
}

// ============================================================================
// Helper functions
// ============================================================================

export function flattenTasks(taskList, depth = 0, out = []) {
  taskList.forEach(task => {
    out.push({ id: task.id, title: task.title || `Task ${task.id}`, depth });
    if (Array.isArray(task.children) && task.children.length > 0) {
      flattenTasks(task.children, depth + 1, out);
    }
  });
  return out;
}

export function findTaskById(taskId, list = state.tasks) {
  for (const task of list) {
    if (task.id === taskId) {
      return task;
    }
    if (task.children && task.children.length > 0) {
      const child = findTaskById(taskId, task.children);
      if (child) {
        return child;
      }
    }
  }
  return null;
}

export function populateParentTaskOptions(selectedId = null) {
  if (!newTaskParentSelectEl) return;
  const tasks = flattenTasks(state.tasks);
  const options = ['<option value="">No parent</option>'];
  tasks.forEach(task => {
    const prefix = task.depth > 0 ? `${'-'.repeat(task.depth * 2)} ` : '';
    options.push(`<option value="${task.id}">${prefix}#${task.id} ${escapeHtml(task.title)}</option>`);
  });
  newTaskParentSelectEl.innerHTML = options.join('');
  if (selectedId) {
    newTaskParentSelectEl.value = String(selectedId);
  }
}

export function getEditingTaskId() {
  return state.editingTaskId;
}

// ============================================================================
// Modals
// ============================================================================

export function hideModals() {
  document.getElementById('new-project-modal').style.display = 'none';
  document.getElementById('edit-project-modal').style.display = 'none';
  document.getElementById('new-task-modal').style.display = 'none';
  document.getElementById('edit-task-modal').style.display = 'none';
  document.getElementById('git-modal').style.display = 'none';
  document.getElementById('settings-modal').style.display = 'none';
  setEditingProjectId(null);
  setEditingTaskId(null);
  setPendingParentTaskId(null);
  resetNewTaskCriteria();
}

export function showNewProjectModal() {
  document.getElementById('new-project-modal').style.display = 'flex';
}

export function showNewTaskModal() {
  if (!state.selectedProject) {
    alert('Select a project first');
    return;
  }
  document.getElementById('new-task-status').value = 'backlog';
  if (newTaskNodeSelectEl) {
    newTaskNodeSelectEl.value = getDefaultNodeId();
  }
  populateParentTaskOptions(state.pendingParentTaskId);
  if (newTaskParentRowEl) {
    newTaskParentRowEl.style.display = state.pendingParentTaskId ? 'none' : 'block';
  }
  resetNewTaskCriteria();
  document.getElementById('new-task-modal').style.display = 'flex';
}

export function showSettingsModal() {
  document.getElementById('settings-modal').style.display = 'flex';
  loadSettings();
}

export function hideSettingsModal() {
  document.getElementById('settings-modal').style.display = 'none';
}

// ============================================================================
// Projects
// ============================================================================

export async function loadProjects() {
  console.log('loadProjects() called, fetching from', `${MAIN_API}/projects`);
  try {
    const res = await fetch(`${MAIN_API}/projects`);
    console.log('loadProjects response status:', res.status);
    const projectList = await res.json();
    setProjects(projectList);
    console.log('loadProjects got projects:', projectList);
    renderProjects();
  } catch (err) {
    console.error('loadProjects error:', err);
    projectListEl.innerHTML = '<li style="color: #ff6b6b;">Failed to load</li>';
  }
}

export function renderProjects() {
  if (state.projects.length === 0) {
    projectListEl.innerHTML = '<li style="color: #666;">No projects yet</li>';
    return;
  }
  projectListEl.innerHTML = state.projects.map(p => `
    <li class="${state.selectedProject?.id === p.id ? 'selected' : ''} has-tooltip"
        onclick="selectProject(${p.id})">
      <div class="project-row">
        <span class="project-title">${escapeHtml(p.name || 'Untitled project')}</span>
        <div class="project-actions">
          <button onclick="event.stopPropagation(); showEditProjectModal(${p.id})">Edit</button>
          <button class="delete" onclick="event.stopPropagation(); deleteProject(${p.id})">Delete</button>
        </div>
      </div>
      ${renderTooltip([
        { label: 'ID', value: p.id ?? '-' },
        { label: 'Workspace', value: p.workspace_path || '-' },
        { label: 'Environment', value: p.environment || '-' },
        { label: 'Created', value: formatDate(p.created_at) }
      ])}
    </li>
  `).join('');
  wireTooltipHandlers(projectListEl);
}

export async function selectProject(projectId) {
  hideGlobalTooltip();
  console.log('selectProject called with:', projectId);
  const project = state.projects.find(p => p.id === projectId);
  if (!project) {
    return;
  }
  setSelectedProject(project);
  setSelectedTask(null);
  renderProjects();

  setCookie(COOKIE_KEYS.PROJECT_ID, projectId);

  const workspaceName = getWorkspaceName(project.workspace_path);
  fetch(`${AIDER_API}/api/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace: workspaceName })
  }).then(() => {
    addMessage('system', `Switched to workspace: ${workspaceName}`);
    logAiderWorkspaceAccess();
  }).catch(err => {
    console.warn('Workspace switch failed:', err.message);
    addMessage('system', `Using workspace: ${workspaceName} (offline mode)`);
  });

  console.log('Loading tasks and file tree for project:', projectId);
  try {
    await Promise.all([
      loadTasks(projectId),
      loadFileTree(projectId),
      loadGitBranches(projectId)
    ]);
  } catch (err) {
    console.error('Error loading project data:', err);
  }
}

async function logAiderWorkspaceAccess() {
  try {
    const res = await fetch(`${AIDER_API}/api/config`);
    if (!res.ok) return;
    const data = await res.json();
    const root = data.config?.workspaces_dir || '';
    const current = data.config?.current_workspace || '';
    if (root && current) {
      let displayRoot = root;
      let displayCurrent = current;
      if (state.selectedProject?.workspace_path?.startsWith('[%root%]')) {
        displayRoot = '/mnt/c/dropbox/_coding/agentic/v2';
        const subPath = state.selectedProject.workspace_path.replace('[%root%]', '').replace(/^\//, '');
        displayCurrent = subPath ? subPath : '[%root%]';
      }
      addMessage('system', `Aider workspace root: ${displayRoot} (current: ${displayCurrent})`);
    }
  } catch (err) {
    console.warn('Failed to fetch aider config:', err.message);
  }
}

export async function createProject() {
  const name = document.getElementById('new-project-name').value.trim();
  const workspace = document.getElementById('new-project-workspace').value.trim();

  console.log('createProject called', { name, workspace });

  if (!name || !workspace) {
    alert('Please fill in both project name and workspace path');
    return;
  }

  try {
    console.log('Sending POST to', `${MAIN_API}/projects`);
    const res = await fetch(`${MAIN_API}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, workspace_path: workspace, environment: 'local' })
    });

    console.log('Response status:', res.status);

    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }

    const project = await res.json();
    console.log('Created project:', project);

    setProjects([...state.projects, project]);
    renderProjects();
    hideModals();
    document.getElementById('new-project-name').value = '';
    document.getElementById('new-project-workspace').value = '';
  } catch (err) {
    console.error('createProject error:', err);
    alert('Failed to create project: ' + err.message);
  }
}

export function showEditProjectModal(projectId) {
  const project = state.projects.find(p => p.id === projectId);
  if (!project) {
    alert('Project not found');
    return;
  }
  setEditingProjectId(projectId);
  document.getElementById('edit-project-name').value = project.name || '';
  document.getElementById('edit-project-workspace').value = getWorkspaceName(project.workspace_path);
  document.getElementById('edit-project-environment').value = project.environment || 'local';
  document.getElementById('edit-project-modal').style.display = 'flex';
}

export async function updateProject() {
  if (!state.editingProjectId) {
    alert('Select a project first');
    return;
  }
  const name = document.getElementById('edit-project-name').value.trim();
  const workspace = document.getElementById('edit-project-workspace').value.trim();
  const environment = document.getElementById('edit-project-environment').value.trim();

  try {
    const res = await fetch(`${MAIN_API}/projects/${state.editingProjectId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, workspace_path: workspace, environment })
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    const updated = await res.json();
    setProjects(state.projects.map(p => p.id === updated.id ? updated : p));
    if (state.selectedProject?.id === updated.id) {
      setSelectedProject(updated);
      await selectProject(updated.id);
    } else {
      renderProjects();
    }
    hideModals();
  } catch (err) {
    alert('Failed to update project: ' + err.message);
  }
}

export async function deleteProject(projectId) {
  if (!confirm('Delete this project?')) {
    return;
  }
  try {
    const res = await fetch(`${MAIN_API}/projects/${projectId}`, { method: 'DELETE' });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    await res.json();
    setProjects(state.projects.filter(p => p.id !== projectId));
    if (state.selectedProject?.id === projectId) {
      setSelectedProject(null);
      setSelectedTask(null);
      setTasks([]);
      taskListEl.innerHTML = '<li style="color: #666;">Select a project</li>';
      fileTreeContent.innerHTML = '<span style="color: #666;">Select a project</span>';
      deleteCookie(COOKIE_KEYS.PROJECT_ID);
    }
    renderProjects();
  } catch (err) {
    alert('Failed to delete project: ' + err.message);
  }
}

// ============================================================================
// Tasks
// ============================================================================

export async function loadTasks(projectId) {
  try {
    const res = await fetch(`${MAIN_API}/projects/${projectId}/tasks`);
    const taskList = await res.json();
    setTasks(taskList);
    renderTasks();
    populateParentTaskOptions();
  } catch (err) {
    taskListEl.innerHTML = '<li style="color: #ff6b6b;">Failed to load</li>';
  }
}

export function renderTasks() {
  if (state.tasks.length === 0) {
    taskListEl.innerHTML = '<li style="color: #666;">No tasks yet</li>';
    return;
  }
  taskListEl.innerHTML = state.tasks.map(t => {
    const title = t.title || 'Untitled task';
    const status = t.status || 'backlog';
    const nodeLabel = t.node_name || (t.node_id ? `#${t.node_id}` : 'unknown');
    const tooltipRows = [
      { label: 'ID', value: t.id ?? '-' },
      { label: 'Title', value: title },
      { label: 'Project', value: t.project_id ?? '-' },
      t.parent_id ? { label: 'Parent', value: `#${t.parent_id}` } : null,
      { label: 'Node', value: nodeLabel },
      { label: 'Status', value: status },
      { label: 'Created', value: formatDate(t.created_at) }
    ];
    return `
    <li class="${state.selectedTask?.id === t.id ? 'selected' : ''} has-tooltip"
        onclick="openTaskEditor(${t.id})">
      <div class="task-row">
        <span class="task-title" title="${escapeHtml(title)}">${escapeHtml(title)}</span>
        <div class="task-actions">
          <button onclick="event.stopPropagation(); openTaskEditor(${t.id})">Edit</button>
          <button class="delete" onclick="event.stopPropagation(); deleteTask(${t.id})">Delete</button>
          <button onclick="event.stopPropagation(); runTaskFromList(this, ${t.id})">Run</button>
        </div>
      </div>
      ${renderTooltip(tooltipRows)}
    </li>
  `;
  }).join('');
  wireTooltipHandlers(taskListEl);
}

export function selectTask(taskId) {
  const task = findTaskById(taskId);
  setSelectedTask(task);
  renderTasks();
  if (task) {
    addMessage('system', `Selected task: ${task.title}`);
  }
}

export function openTaskEditor(taskId) {
  hideGlobalTooltip();
  selectTask(taskId);
  showEditTaskModal(taskId);
}

export function createSubtask(parentTaskId) {
  if (!parentTaskId) return;
  setPendingParentTaskId(parentTaskId);
  showNewTaskModal();
}

export function showEditTaskModal(taskId) {
  const task = findTaskById(taskId);
  if (!task) {
    alert('Task not found');
    return;
  }
  setEditingTaskId(taskId);
  document.getElementById('edit-task-title').value = task.title || '';
  document.getElementById('edit-task-desc').value = task.description || '';
  document.getElementById('edit-task-status').value = task.status || 'backlog';
  if (editTaskNodeSelectEl) {
    editTaskNodeSelectEl.value = task.node_id ? String(task.node_id) : getDefaultNodeId();
  }
  if (task.parent_id) {
    const parent = findTaskById(task.parent_id);
    if (editTaskParentRowEl && editTaskParentLinkEl) {
      editTaskParentRowEl.style.display = 'block';
      const label = parent
        ? `#${parent.id} ${parent.title || 'Untitled task'}`
        : `#${task.parent_id}`;
      editTaskParentLinkEl.textContent = label;
      editTaskParentLinkEl.onclick = (event) => {
        event.preventDefault();
        openTaskEditor(task.parent_id);
      };
    }
  } else if (editTaskParentRowEl) {
    editTaskParentRowEl.style.display = 'none';
    if (editTaskParentLinkEl) {
      editTaskParentLinkEl.textContent = '';
      editTaskParentLinkEl.onclick = null;
    }
  }
  document.getElementById('edit-task-modal').style.display = 'flex';
  resetCommentForm();
  renderSubtasks(taskId);
  loadTaskAcceptanceCriteria(taskId);
  loadTaskComments(taskId);
  loadTaskAttachments(taskId);
  loadTaskRuns(taskId);
  if (taskRunPreviewEl) {
    taskRunPreviewEl.value = '';
  }
}

export function renderSubtasks(taskId) {
  if (!subtaskListEl) return;
  const task = findTaskById(taskId);
  const children = Array.isArray(task?.children) ? task.children : [];
  if (!children.length) {
    subtaskListEl.textContent = 'No subtasks';
    return;
  }
  subtaskListEl.innerHTML = children.map(child => {
    const title = escapeHtml(child.title || `Task ${child.id}`);
    const status = escapeHtml(child.status || 'backlog');
    const nodeLabel = child.node_name ? escapeHtml(child.node_name) : (child.node_id ? `node ${child.node_id}` : '');
    const meta = [status, nodeLabel].filter(Boolean).join(' · ');
    return `
      <div class="subtask-item" onclick="openTaskEditor(${child.id})">
        <div class="subtask-title">#${child.id} ${title}</div>
        <div class="subtask-meta">${escapeHtml(meta)}</div>
      </div>
    `;
  }).join('');
}

export async function createTask() {
  const title = document.getElementById('new-task-title').value.trim();
  const description = document.getElementById('new-task-desc').value.trim();
  const parentRaw = newTaskParentSelectEl ? newTaskParentSelectEl.value : '';
  const status = document.getElementById('new-task-status').value;
  const nodeIdRaw = newTaskNodeSelectEl ? newTaskNodeSelectEl.value : '';
  if (!title) return;
  if (!state.newTaskCriteria.length) {
    alert('Add at least one acceptance criteria');
    return;
  }

  let parentId = state.pendingParentTaskId;
  if (!parentId && parentRaw) {
    parentId = parseInt(parentRaw, 10);
    if (Number.isNaN(parentId)) parentId = null;
  }
  const nodeId = nodeIdRaw ? parseInt(nodeIdRaw, 10) : null;

  try {
    const res = await fetch(`${MAIN_API}/tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: state.selectedProject.id,
        parent_id: parentId,
        node_id: nodeId,
        title,
        description,
        status,
        acceptance_criteria: state.newTaskCriteria
      })
    });
    await res.json();
    await loadTasks(state.selectedProject.id);
    hideModals();
    document.getElementById('new-task-title').value = '';
    document.getElementById('new-task-desc').value = '';
    if (newTaskParentSelectEl) newTaskParentSelectEl.value = '';
    setPendingParentTaskId(null);
    resetNewTaskCriteria();
  } catch (err) {
    alert('Failed to create task: ' + err.message);
  }
}

export async function updateTask() {
  if (!state.editingTaskId || !state.selectedProject) {
    alert('Select a task first');
    return;
  }
  const title = document.getElementById('edit-task-title').value.trim();
  const description = document.getElementById('edit-task-desc').value.trim();
  const status = document.getElementById('edit-task-status').value;
  const nodeIdRaw = editTaskNodeSelectEl ? editTaskNodeSelectEl.value : '';
  const nodeId = nodeIdRaw ? parseInt(nodeIdRaw, 10) : null;

  try {
    const res = await fetch(`${MAIN_API}/tasks/${state.editingTaskId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description, status, node_id: nodeId })
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    await res.json();
    await loadTasks(state.selectedProject.id);
    hideModals();
  } catch (err) {
    alert('Failed to update task: ' + err.message);
  }
}

export async function deleteTask(taskId) {
  if (!state.selectedProject) {
    alert('Select a project first');
    return;
  }
  if (!confirm('Delete this task?')) {
    return;
  }
  try {
    const res = await fetch(`${MAIN_API}/tasks/${taskId}`, { method: 'DELETE' });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    await res.json();
    if (state.selectedTask?.id === taskId) {
      setSelectedTask(null);
    }
    await loadTasks(state.selectedProject.id);
    hideModals();
  } catch (err) {
    alert('Failed to delete task: ' + err.message);
  }
}

// ============================================================================
// File Tree
// ============================================================================

export async function loadFileTree(projectId) {
  console.log('loadFileTree called with projectId:', projectId);
  fileTreeContent.innerHTML = '<span style="color: #888;">Loading files...</span>';
  try {
    const url = `${MAIN_API}/projects/${projectId}/files`;
    console.log('Fetching file tree from:', url);
    const res = await fetch(url);
    console.log('File tree response status:', res.status);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    console.log('File tree data:', data);
    state.currentWorkspacePath = data.workspace || 'unknown';
    state.fileTree = data.files || [];
    console.log('Workspace:', state.currentWorkspacePath, 'Files count:', state.fileTree.length);
    renderFileTree();
  } catch (err) {
    console.error('loadFileTree error:', err);
    fileTreeContent.innerHTML = '<span style="color: #ff6b6b;">Failed to load: ' + err.message + '</span>';
  }
}

export function renderFileTree() {
  const displayPath = state.currentWorkspacePath.startsWith('[%root%]')
    ? state.currentWorkspacePath.replace('[%root%]', 'v2 (self)')
    : `/workspaces/${state.currentWorkspacePath}`;
  let html = `<div style="color: #888; font-size: 11px; margin-bottom: 8px;">📂 ${displayPath}</div>`;

  if (state.fileTree.length === 0) {
    fileTreeContent.innerHTML = html + '<span style="color: #666;">No files found</span>';
    return;
  }

  fileTreeContent.innerHTML = html + renderTreeNode(state.fileTree);
}

function renderTreeNode(nodes, level = 0) {
  return nodes.map(node => {
    const isDir = node.type === 'directory';
    const icon = isDir ? '📁' : '📄';
    const hasChildren = isDir && node.children && node.children.length > 0;

    const doubleClick = node.type === 'file'
      ? `ondblclick="openFileInVSCode('${node.path}')"`
      : '';
    let html = `
      <div class="tree-item ${node.type}" onclick="handleFileClick('${node.path}', '${node.type}')" ${doubleClick}>
        ${hasChildren ? '<span class="tree-toggle" onclick="event.stopPropagation(); toggleTreeNode(this)">▶</span>' : '<span class="tree-toggle"></span>'}
        <span class="icon">${icon}</span>
        <span>${escapeHtml(node.name)}</span>
      </div>
    `;

    if (hasChildren) {
      html += `<div class="tree-children" style="display: none;">${renderTreeNode(node.children, level + 1)}</div>`;
    }

    return html;
  }).join('');
}

export function toggleTreeNode(el) {
  const children = el.parentElement.nextElementSibling;
  if (children && children.classList.contains('tree-children')) {
    const isHidden = children.style.display === 'none';
    children.style.display = isHidden ? 'block' : 'none';
    el.textContent = isHidden ? '▼' : '▶';
  }
}

export function handleFileClick(path, type) {
  if (type === 'file') {
    addFileReference(path);
  }
}

export function openFileInVSCode(path) {
  if (!state.selectedProject || !path) {
    return;
  }
  let workspacePath = state.selectedProject.workspace_path || '';
  let fullPath;

  if (workspacePath.startsWith('[%root%]')) {
    const basePath = '/mnt/c/dropbox/_coding/agentic/v2';
    const subPath = workspacePath.replace('[%root%]', '').replace(/^\//, '');
    if (subPath) {
      fullPath = `${basePath}/${subPath}/${path}`.replace(/\/+/g, '/');
    } else {
      fullPath = `${basePath}/${path}`.replace(/\/+/g, '/');
    }
  } else {
    workspacePath = workspacePath.replace(/^\.?\/?(workspaces\/)?/, '').replace(/\/+$/, '');
    const basePath = '/mnt/c/dropbox/_coding/agentic/v2/workspaces';
    fullPath = `${basePath}/${workspacePath}/${path}`.replace(/\/+/g, '/');
  }

  if (fullPath.startsWith('/mnt/')) {
    const parts = fullPath.split('/');
    const drive = parts[2].toUpperCase();
    fullPath = `${drive}:/${parts.slice(3).join('/')}`;
  }

  window.location.href = `vscode://file/${fullPath}`;
}

// ============================================================================
// Acceptance Criteria
// ============================================================================

export async function loadTaskAcceptanceCriteria(taskId) {
  if (!criteriaListEl) return;
  criteriaListEl.textContent = 'Loading...';
  try {
    const res = await fetch(`${MAIN_API}/tasks/${taskId}/acceptance`);
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(errorText || `HTTP ${res.status}`);
    }
    setTaskCriteria(await res.json());
    renderAcceptanceCriteria();
  } catch (err) {
    criteriaListEl.textContent = `Failed to load criteria: ${err.message}`;
  }
}

export function renderAcceptanceCriteria() {
  if (!criteriaListEl) return;
  if (!state.taskCriteria.length) {
    criteriaListEl.textContent = 'No criteria';
    return;
  }
  criteriaListEl.innerHTML = state.taskCriteria.map(criteria => `
    <div class="criteria-item">
      <label class="criteria-main">
        <input type="checkbox" ${criteria.passed ? 'checked' : ''} onchange="toggleAcceptanceCriteria(${criteria.id}, this.checked)">
        <span class="criteria-desc">${escapeHtml(criteria.description)}</span>
      </label>
      <div class="criteria-meta">By ${escapeHtml(criteria.author)} | ${formatDate(criteria.updated_at)}</div>
      <div class="criteria-actions">
        <button class="delete" onclick="deleteAcceptanceCriteria(${criteria.id})">Delete</button>
      </div>
    </div>
  `).join('');
}

export function resetNewTaskCriteria() {
  setNewTaskCriteria([]);
  renderNewTaskCriteria();
}

export function renderNewTaskCriteria() {
  if (!newTaskCriteriaListEl) return;
  if (!state.newTaskCriteria.length) {
    newTaskCriteriaListEl.textContent = 'No criteria';
    return;
  }
  newTaskCriteriaListEl.innerHTML = state.newTaskCriteria.map((criteria, idx) => `
    <div class="criteria-item">
      <div class="criteria-main">
        <span class="criteria-desc">${escapeHtml(criteria.description)}</span>
      </div>
      <div class="criteria-actions">
        <button class="delete" onclick="removeNewTaskCriteria(${idx})">Remove</button>
      </div>
    </div>
  `).join('');
}

export function addNewTaskCriteria() {
  const description = newTaskCriteriaDescEl?.value.trim() || '';
  if (!description) {
    alert('Criteria description is required');
    return;
  }
  setNewTaskCriteria([
    ...state.newTaskCriteria,
    {
      description,
      passed: false,
      author: 'user'
    }
  ]);
  if (newTaskCriteriaDescEl) newTaskCriteriaDescEl.value = '';
  renderNewTaskCriteria();
}

export function removeNewTaskCriteria(index) {
  setNewTaskCriteria(state.newTaskCriteria.filter((_, idx) => idx !== index));
  renderNewTaskCriteria();
}

export async function addAcceptanceCriteria() {
  if (!state.selectedTask) {
    alert('Select a task first');
    return;
  }
  const description = criteriaDescEl?.value.trim() || '';
  const author = criteriaAuthorEl?.value.trim() || '';
  if (!description) {
    alert('Criteria description is required');
    return;
  }
  try {
    const res = await fetch(`${MAIN_API}/tasks/${state.selectedTask.id}/acceptance`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        description,
        author: author || null
      })
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(errorText || `HTTP ${res.status}`);
    }
    await res.json();
    if (criteriaDescEl) criteriaDescEl.value = '';
    if (criteriaAuthorEl) criteriaAuthorEl.value = '';
    await loadTaskAcceptanceCriteria(state.selectedTask.id);
  } catch (err) {
    alert('Failed to add criteria: ' + err.message);
  }
}

export async function toggleAcceptanceCriteria(criteriaId, passed) {
  if (!state.selectedTask) return;
  try {
    const res = await fetch(`${MAIN_API}/tasks/${state.selectedTask.id}/acceptance/${criteriaId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ passed })
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(errorText || `HTTP ${res.status}`);
    }
    await res.json();
    await loadTaskAcceptanceCriteria(state.selectedTask.id);
  } catch (err) {
    alert(`Failed to update criteria: ${err.message}`);
  }
}

export async function deleteAcceptanceCriteria(criteriaId) {
  if (!state.selectedTask) return;
  if (!confirm('Delete this criteria?')) return;
  try {
    const res = await fetch(`${MAIN_API}/tasks/${state.selectedTask.id}/acceptance/${criteriaId}`, {
      method: 'DELETE'
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(errorText || `HTTP ${res.status}`);
    }
    await res.json();
    await loadTaskAcceptanceCriteria(state.selectedTask.id);
  } catch (err) {
    alert(`Failed to delete criteria: ${err.message}`);
  }
}

// ============================================================================
// Comments
// ============================================================================

export async function loadTaskComments(taskId) {
  if (!taskCommentsListEl) return;
  taskCommentsListEl.textContent = 'Loading...';
  try {
    const res = await fetch(`${MAIN_API}/tasks/${taskId}/comments`);
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    setTaskComments(await res.json());
    renderTaskComments();
    updateAttachmentCommentOptions();
  } catch (err) {
    taskCommentsListEl.textContent = `Failed to load comments: ${err.message}`;
  }
}

export function renderTaskComments() {
  if (!taskCommentsListEl) return;
  if (!state.taskComments.length) {
    taskCommentsListEl.textContent = 'No comments';
    return;
  }
  taskCommentsListEl.innerHTML = state.taskComments.map(comment => `
    <div class="comment-item">
      <div class="comment-meta">
        <div>ID: ${escapeHtml(comment.id)} | Task: ${escapeHtml(comment.task_id)}</div>
        <div>Author: ${escapeHtml(comment.author || 'human')}</div>
        <div>Created: ${escapeHtml(formatDate(comment.created_at))} | Updated: ${escapeHtml(formatDate(comment.updated_at))}</div>
      </div>
      <div>${escapeHtml(comment.body || '')}</div>
      <div class="comment-actions">
        <button onclick="startEditComment(${comment.id})">Edit</button>
        <button class="delete" onclick="deleteTaskComment(${comment.id})">Delete</button>
      </div>
    </div>
  `).join('');
}

function updateAttachmentCommentOptions() {
  if (!attachmentCommentIdEl) return;
  const current = attachmentCommentIdEl.value;
  const options = ['<option value="">Attach to task</option>'];
  state.taskComments.forEach(comment => {
    const preview = escapeHtml((comment.body || '').slice(0, 40));
    options.push(`<option value="${comment.id}">Comment #${comment.id} - ${preview}</option>`);
  });
  attachmentCommentIdEl.innerHTML = options.join('');
  if (current && [...attachmentCommentIdEl.options].some(opt => opt.value === current)) {
    attachmentCommentIdEl.value = current;
  }
}

export function startEditComment(commentId) {
  const comment = state.taskComments.find(item => item.id === commentId);
  if (!comment) return;
  setEditingCommentId(commentId);
  if (commentIdEl) commentIdEl.value = String(commentId);
  if (commentAuthorEl) commentAuthorEl.value = comment.author || '';
  if (commentBodyEl) commentBodyEl.value = comment.body || '';
}

export function resetCommentForm() {
  setEditingCommentId(null);
  if (commentIdEl) commentIdEl.value = '';
  if (commentAuthorEl) commentAuthorEl.value = '';
  if (commentBodyEl) commentBodyEl.value = '';
}

export async function saveTaskComment() {
  if (!state.selectedTask) {
    alert('Select a task first');
    return;
  }
  const author = (commentAuthorEl?.value || '').trim();
  const body = (commentBodyEl?.value || '').trim();
  if (!body) {
    alert('Comment body is required');
    return;
  }
  const payload = { body };
  if (author) payload.author = author;

  const taskId = state.selectedTask.id;
  const url = state.editingCommentId
    ? `${MAIN_API}/tasks/${taskId}/comments/${state.editingCommentId}`
    : `${MAIN_API}/tasks/${taskId}/comments`;
  const method = state.editingCommentId ? 'PATCH' : 'POST';

  try {
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    await res.json();
    resetCommentForm();
    await loadTaskComments(taskId);
  } catch (err) {
    alert(`Failed to save comment: ${err.message}`);
  }
}

export async function deleteTaskComment(commentId) {
  if (!state.selectedTask) return;
  if (!confirm('Delete this comment?')) return;
  try {
    const res = await fetch(`${MAIN_API}/tasks/${state.selectedTask.id}/comments/${commentId}`, {
      method: 'DELETE'
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    await res.json();
    if (state.editingCommentId === commentId) resetCommentForm();
    await loadTaskComments(state.selectedTask.id);
  } catch (err) {
    alert(`Failed to delete comment: ${err.message}`);
  }
}

// ============================================================================
// Attachments
// ============================================================================

export async function loadTaskAttachments(taskId) {
  if (!taskAttachmentsListEl) return;
  taskAttachmentsListEl.textContent = 'Loading...';
  try {
    const res = await fetch(`${MAIN_API}/tasks/${taskId}/attachments`);
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    setTaskAttachments(await res.json());
    renderTaskAttachments();
  } catch (err) {
    taskAttachmentsListEl.textContent = `Failed to load attachments: ${err.message}`;
  }
}

export function renderTaskAttachments() {
  if (!taskAttachmentsListEl) return;
  if (!state.taskAttachments.length) {
    taskAttachmentsListEl.textContent = 'No attachments';
    return;
  }
  taskAttachmentsListEl.innerHTML = state.taskAttachments.map(attachment => `
    <div class="attachment-item">
      <div class="attachment-row">
        <a class="attachment-link" href="${MAIN_API}${attachment.url}" target="_blank">${escapeHtml(attachment.filename)}</a>
        <div class="attachment-meta">ID: ${escapeHtml(attachment.id)} | Task: ${escapeHtml(attachment.task_id)} | Comment: ${escapeHtml(attachment.comment_id ?? '-')}</div>
        <div class="attachment-meta">Type: ${escapeHtml(attachment.mime_type)} | Size: ${escapeHtml(attachment.size_bytes)} bytes</div>
        <div class="attachment-meta">Storage: ${escapeHtml(attachment.storage_path)}</div>
        <div class="attachment-meta">URL: ${escapeHtml(attachment.url)}</div>
        <div class="attachment-meta">Uploaded by: ${escapeHtml(attachment.uploaded_by)} | Created: ${escapeHtml(formatDate(attachment.created_at))}</div>
      </div>
      <div class="attachment-actions">
        <button class="delete" onclick="deleteTaskAttachment(${attachment.id})">Delete</button>
      </div>
    </div>
  `).join('');
}

export async function uploadTaskAttachment() {
  if (!state.selectedTask) {
    alert('Select a task first');
    return;
  }
  const file = attachmentFileEl?.files?.[0];
  if (!file) {
    alert('Select a file to upload');
    return;
  }
  const formData = new FormData();
  formData.append('file', file);
  if (attachmentUploadedByEl?.value) {
    formData.append('uploaded_by', attachmentUploadedByEl.value.trim());
  }
  if (attachmentCommentIdEl?.value) {
    formData.append('comment_id', attachmentCommentIdEl.value);
  }
  try {
    const res = await fetch(`${MAIN_API}/tasks/${state.selectedTask.id}/attachments`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    await res.json();
    if (attachmentFileEl) attachmentFileEl.value = '';
    if (attachmentUploadedByEl) attachmentUploadedByEl.value = '';
    if (attachmentCommentIdEl) attachmentCommentIdEl.value = '';
    await loadTaskAttachments(state.selectedTask.id);
  } catch (err) {
    alert(`Failed to upload attachment: ${err.message}`);
  }
}

export async function deleteTaskAttachment(attachmentId) {
  if (!state.selectedTask) return;
  if (!confirm('Delete this attachment?')) return;
  try {
    const res = await fetch(`${MAIN_API}/tasks/${state.selectedTask.id}/attachments/${attachmentId}`, {
      method: 'DELETE'
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    await res.json();
    await loadTaskAttachments(state.selectedTask.id);
  } catch (err) {
    alert(`Failed to delete attachment: ${err.message}`);
  }
}

// ============================================================================
// Runs
// ============================================================================

export async function loadTaskRuns(taskId) {
  if (!taskRunsListEl) return;
  taskRunsListEl.textContent = 'Loading...';
  try {
    const res = await fetch(`${MAIN_API}/tasks/${taskId}/runs`);
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    setTaskRuns(await res.json());
    renderTaskRuns();
  } catch (err) {
    taskRunsListEl.textContent = `Failed to load runs: ${err.message}`;
  }
}

export function renderTaskRuns() {
  if (!taskRunsListEl) return;
  if (!state.taskRuns.length) {
    taskRunsListEl.textContent = 'No runs yet';
    return;
  }
  taskRunsListEl.innerHTML = state.taskRuns.map(run => {
    const status = run.status || 'unknown';
    const summary = truncateText(run.summary || run.error || '', 160);
    const started = formatDate(run.started_at);
    const finished = run.finished_at ? formatDate(run.finished_at) : '-';
    return `
      <div class="run-item">
        <div class="run-item-header">
          <span>#${run.id} · ${escapeHtml(status)}</span>
          <span>${escapeHtml(started)}</span>
        </div>
        <div class="run-item-meta">Node ${run.node_id} · Finished ${escapeHtml(finished)}</div>
        ${summary ? `<div class="run-item-meta">${escapeHtml(summary)}</div>` : ''}
      </div>
    `;
  }).join('');
}

export async function refreshTaskRuns(taskId) {
  if (getEditingTaskId() !== taskId) return;
  await loadTaskRuns(taskId);
}

// ============================================================================
// Settings
// ============================================================================

export async function loadSettings() {
  settingsListEl.textContent = 'Loading...';
  try {
    const res = await fetch(`${MAIN_API}/api/env`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    setEnvEntries(data.entries || []);
    renderSettings();
  } catch (err) {
    settingsListEl.textContent = `Failed to load settings: ${err.message}`;
  }
}

export function renderSettings() {
  const filter = (settingsFilterEl?.value || '').toLowerCase();
  const rows = state.envEntries.map((entry, idx) => {
    if (entry.type === 'pair') {
      if (filter && !entry.key.toLowerCase().includes(filter)) {
        return '';
      }
      return `
        <div class="settings-row">
          <label>${escapeHtml(entry.key)}</label>
          <input data-env-index="${idx}" value="${escapeHtml(entry.value || '')}">
        </div>
      `;
    }
    if (entry.type === 'comment' && entry.value) {
      if (filter) return '';
      return `<div class="settings-comment">${escapeHtml(entry.value)}</div>`;
    }
    return '';
  }).join('');
  settingsListEl.innerHTML = rows || '<div class="settings-comment">No settings</div>';
}

export async function applySettings() {
  const updates = {};
  settingsListEl.querySelectorAll('input[data-env-index]').forEach(input => {
    const index = Number(input.dataset.envIndex);
    const entry = state.envEntries[index];
    if (entry && entry.type === 'pair') {
      updates[entry.key] = input.value;
    }
  });

  const restartServices = [];
  if (restartMainEl?.checked) restartServices.push('main');
  if (restartAiderEl?.checked) restartServices.push('aider');
  if (restartOllamaEl?.checked) restartServices.push('ollama');
  if (restartDbEl?.checked) restartServices.push('db');

  try {
    const res = await fetch(`${MAIN_API}/api/env`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ updates, restart_services: restartServices })
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errorText}`);
    }
    const data = await res.json();
    addMessage('system', `Settings updated: ${data.updated_keys?.length || 0} keys`);
    hideSettingsModal();
  } catch (err) {
    alert('Failed to apply settings: ' + err.message);
  }
}

export function switchSettingsTab(tab) {
  document.querySelectorAll('.settings-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tab);
  });

  document.getElementById('settings-tab-env').classList.toggle('active', tab === 'env');
  document.getElementById('settings-tab-nodes').classList.toggle('active', tab === 'nodes');

  setCurrentSettingsTab(tab);

  if (tab === 'nodes') {
    loadNodesForEditor();
  }
}

// ============================================================================
// Nodes
// ============================================================================

export function getDefaultNodeId() {
  const node = state.availableNodes.find(item => item.name === 'dev') || state.availableNodes[0];
  return node ? String(node.id) : '';
}

export function renderNodeOptions(selectedId = '') {
  if (newTaskNodeSelectEl) {
    const options = state.availableNodes.map(node => (
      `<option value="${node.id}">${escapeHtml(node.name)}</option>`
    ));
    newTaskNodeSelectEl.innerHTML = options.join('') || '<option value="">No nodes</option>';
    newTaskNodeSelectEl.value = selectedId || getDefaultNodeId();
  }
  if (editTaskNodeSelectEl) {
    const options = state.availableNodes.map(node => (
      `<option value="${node.id}">${escapeHtml(node.name)}</option>`
    ));
    editTaskNodeSelectEl.innerHTML = options.join('') || '<option value="">No nodes</option>';
    if (selectedId) {
      editTaskNodeSelectEl.value = selectedId;
    }
  }
}

export async function loadNodes() {
  try {
    const res = await fetch(`${MAIN_API}/nodes`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const nodeList = await res.json();
    setAvailableNodes(Array.isArray(nodeList) ? nodeList : []);
    renderNodeOptions();
  } catch (err) {
    console.warn('Failed to load nodes:', err.message);
    setAvailableNodes([]);
    renderNodeOptions();
  }
}

export async function loadNodesForEditor() {
  const nodeListEl = document.getElementById('node-list');
  nodeListEl.textContent = 'Loading...';
  try {
    const res = await fetch(`${MAIN_API}/nodes`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const nodes = await res.json();
    setNodes(nodes);
    renderNodeList();
  } catch (err) {
    nodeListEl.textContent = `Failed to load nodes: ${err.message}`;
  }
}

export function renderNodeList() {
  const nodeListEl = document.getElementById('node-list');
  if (!state.nodes || state.nodes.length === 0) {
    nodeListEl.innerHTML = '<div style="color: #6b7280; padding: 8px;">No nodes</div>';
    return;
  }
  nodeListEl.innerHTML = state.nodes.map(node => {
    const isSelected = state.selectedNodeId === node.id;
    const hasRouting = node.pass_node_id || node.fail_node_id;
    return `
      <div class="node-list-item ${isSelected ? 'selected' : ''}"
           onclick="selectNode(${node.id})">
        <span>${escapeHtml(node.name)}</span>
        ${hasRouting ? '<span class="routing-indicator">→</span>' : ''}
      </div>
    `;
  }).join('');
}

export function selectNode(nodeId) {
  setSelectedNodeId(nodeId);
  renderNodeList();
  renderNodeEditor();
}

export function renderNodeEditor() {
  const panelEl = document.getElementById('node-editor-panel');
  const node = state.nodes.find(n => n.id === state.selectedNodeId);

  if (!node) {
    panelEl.innerHTML = '<div class="node-editor-placeholder">Select a node to edit</div>';
    return;
  }

  const routingOptions = state.nodes
    .filter(n => n.id !== node.id)
    .map(n => `<option value="${n.id}">${escapeHtml(n.name)}</option>`)
    .join('');

  panelEl.innerHTML = `
    <form class="node-editor-form" onsubmit="saveNode(event)">
      <div class="node-form-row">
        <label for="node-name">Name</label>
        <input type="text" id="node-name" value="${escapeHtml(node.name)}" required>
      </div>

      <div class="node-form-row">
        <label for="node-prompt">Agent Prompt</label>
        <textarea id="node-prompt" rows="6">${escapeHtml(node.agent_prompt)}</textarea>
      </div>

      <div class="node-form-row">
        <label for="node-pre-hooks">Pre Hooks (one per line)</label>
        <textarea id="node-pre-hooks" rows="3" placeholder="npm install&#10;./setup.sh">${(node.pre_hooks || []).join('\n')}</textarea>
      </div>

      <div class="node-form-row">
        <label for="node-post-hooks">Post Hooks (one per line)</label>
        <textarea id="node-post-hooks" rows="3" placeholder="npm test&#10;./cleanup.sh">${(node.post_hooks || []).join('\n')}</textarea>
      </div>

      <div class="node-form-row-inline">
        <div class="node-form-row">
          <label for="node-pass">On Success</label>
          <select id="node-pass">
            <option value="">None</option>
            ${routingOptions}
          </select>
        </div>
        <div class="node-form-row">
          <label for="node-fail">On Failure</label>
          <select id="node-fail">
            <option value="">None</option>
            ${routingOptions}
          </select>
        </div>
      </div>

      <div class="node-form-row">
        <label for="node-max-iter">Max Iterations</label>
        <input type="number" id="node-max-iter" min="1" max="100" value="${node.max_iterations || 20}">
      </div>

      <div class="node-form-actions">
        <button type="submit">Save</button>
        <button type="button" class="secondary" onclick="cancelNodeEdit()">Cancel</button>
        <button type="button" class="secondary delete" onclick="deleteNode(${node.id})">Delete</button>
      </div>
    </form>
  `;

  document.getElementById('node-pass').value = node.pass_node_id || '';
  document.getElementById('node-fail').value = node.fail_node_id || '';
}

export function createNewNode() {
  setSelectedNodeId(null);
  renderNodeList();

  const panelEl = document.getElementById('node-editor-panel');
  const routingOptions = state.nodes
    .map(n => `<option value="${n.id}">${escapeHtml(n.name)}</option>`)
    .join('');

  panelEl.innerHTML = `
    <form class="node-editor-form" onsubmit="saveNewNode(event)">
      <div class="node-form-row">
        <label for="node-name">Name</label>
        <input type="text" id="node-name" value="" placeholder="new_node" required>
      </div>

      <div class="node-form-row">
        <label for="node-prompt">Agent Prompt</label>
        <textarea id="node-prompt" rows="6" placeholder="You are an agent that..."></textarea>
      </div>

      <div class="node-form-row">
        <label for="node-pre-hooks">Pre Hooks (one per line)</label>
        <textarea id="node-pre-hooks" rows="3" placeholder="npm install&#10;./setup.sh"></textarea>
      </div>

      <div class="node-form-row">
        <label for="node-post-hooks">Post Hooks (one per line)</label>
        <textarea id="node-post-hooks" rows="3" placeholder="npm test&#10;./cleanup.sh"></textarea>
      </div>

      <div class="node-form-row-inline">
        <div class="node-form-row">
          <label for="node-pass">On Success</label>
          <select id="node-pass">
            <option value="">None</option>
            ${routingOptions}
          </select>
        </div>
        <div class="node-form-row">
          <label for="node-fail">On Failure</label>
          <select id="node-fail">
            <option value="">None</option>
            ${routingOptions}
          </select>
        </div>
      </div>

      <div class="node-form-row">
        <label for="node-max-iter">Max Iterations</label>
        <input type="number" id="node-max-iter" min="1" max="100" value="20">
      </div>

      <div class="node-form-actions">
        <button type="submit">Create</button>
        <button type="button" class="secondary" onclick="cancelNodeEdit()">Cancel</button>
      </div>
    </form>
  `;
}

export function cancelNodeEdit() {
  setSelectedNodeId(null);
  renderNodeList();
  document.getElementById('node-editor-panel').innerHTML =
    '<div class="node-editor-placeholder">Select a node to edit</div>';
}

function parseHooks(text) {
  return text.split('\n')
    .map(line => line.trim())
    .filter(line => line.length > 0);
}

export async function saveNode(event) {
  event.preventDefault();

  const nodeId = state.selectedNodeId;
  if (!nodeId) return;

  const name = document.getElementById('node-name').value.trim();
  const agentPrompt = document.getElementById('node-prompt').value;
  const preHooks = parseHooks(document.getElementById('node-pre-hooks').value);
  const postHooks = parseHooks(document.getElementById('node-post-hooks').value);
  const passNodeId = parseInt(document.getElementById('node-pass').value) || 0;
  const failNodeId = parseInt(document.getElementById('node-fail').value) || 0;
  const maxIterations = parseInt(document.getElementById('node-max-iter').value) || 20;

  try {
    const res = await fetch(`${MAIN_API}/nodes/${nodeId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        agent_prompt: agentPrompt,
        pre_hooks: preHooks,
        post_hooks: postHooks,
        pass_node_id: passNodeId,
        fail_node_id: failNodeId,
        max_iterations: maxIterations,
      }),
    });

    if (!res.ok) {
      const data = await res.json();
      alert(`Error: ${data.detail || 'Failed to save node'}`);
      return;
    }

    await loadNodes();
    selectNode(nodeId);
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

export async function saveNewNode(event) {
  event.preventDefault();

  const name = document.getElementById('node-name').value.trim();
  const agentPrompt = document.getElementById('node-prompt').value;
  const preHooks = parseHooks(document.getElementById('node-pre-hooks').value);
  const postHooks = parseHooks(document.getElementById('node-post-hooks').value);
  const passNodeId = parseInt(document.getElementById('node-pass').value) || 0;
  const failNodeId = parseInt(document.getElementById('node-fail').value) || 0;
  const maxIterations = parseInt(document.getElementById('node-max-iter').value) || 20;

  if (!name) {
    alert('Node name is required');
    return;
  }

  try {
    const res = await fetch(`${MAIN_API}/nodes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        agent_prompt: agentPrompt || '',
        pre_hooks: preHooks,
        post_hooks: postHooks,
        pass_node_id: passNodeId,
        fail_node_id: failNodeId,
        max_iterations: maxIterations,
      }),
    });

    if (!res.ok) {
      const data = await res.json();
      alert(`Error: ${data.detail || 'Failed to create node'}`);
      return;
    }

    const newNode = await res.json();
    await loadNodes();
    selectNode(newNode.id);
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

export async function deleteNode(nodeId) {
  const node = state.nodes.find(n => n.id === nodeId);
  if (!node) return;

  if (!confirm(`Delete node "${node.name}"? This cannot be undone.`)) {
    return;
  }

  try {
    const res = await fetch(`${MAIN_API}/nodes/${nodeId}`, {
      method: 'DELETE',
    });

    if (!res.ok) {
      const data = await res.json();
      alert(`Error: ${data.detail || 'Failed to delete node'}`);
      return;
    }

    setSelectedNodeId(null);
    await loadNodes();
    document.getElementById('node-editor-panel').innerHTML =
      '<div class="node-editor-placeholder">Select a node to edit</div>';
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

// ============================================================================
// Cookie restoration
// ============================================================================

export async function restoreSelectionsFromCookies() {
  const savedProjectId = getCookie(COOKIE_KEYS.PROJECT_ID);
  let projectRestored = false;

  if (savedProjectId) {
    const projectId = parseInt(savedProjectId, 10);
    const projectExists = state.projects.some(p => p.id === projectId);
    if (projectExists) {
      await selectProject(projectId);
      projectRestored = true;
    } else {
      deleteCookie(COOKIE_KEYS.PROJECT_ID);
    }
  }

  if (!projectRestored && state.projects.length > 0) {
    await selectProject(state.projects[0].id);
  }
}
