// Modal show/hide utilities

import { state } from './state.js';

export function showNewProjectModal() {
  document.getElementById('new-project-modal').style.display = 'flex';
}

export function showNewTaskModal() {
  if (!state.selectedProject) {
    alert('Select a project first');
    return;
  }
  document.getElementById('new-task-modal').style.display = 'flex';
}

export function showGitModal() {
  if (!state.selectedProject) {
    alert('Select a project first');
    return;
  }
  document.getElementById('git-modal').style.display = 'flex';
  // loadGitBranches will be called from the caller
}

export function hideGitModal() {
  document.getElementById('git-modal').style.display = 'none';
}

export function showSettingsModal() {
  document.getElementById('settings-modal').style.display = 'flex';
  // loadSettings will be called from the caller
}

export function hideSettingsModal() {
  document.getElementById('settings-modal').style.display = 'none';
}

export function hideModals() {
  document.getElementById('new-project-modal').style.display = 'none';
  document.getElementById('edit-project-modal').style.display = 'none';
  document.getElementById('new-task-modal').style.display = 'none';
  document.getElementById('edit-task-modal').style.display = 'none';
  document.getElementById('git-modal').style.display = 'none';
  document.getElementById('settings-modal').style.display = 'none';
  state.editingProjectId = null;
  state.editingTaskId = null;
}

export function showEditProjectModal(project) {
  state.editingProjectId = project.id;
  document.getElementById('edit-project-name').value = project.name || '';
  document.getElementById('edit-project-workspace').value = project.workspace_path || '';
  document.getElementById('edit-project-environment').value = project.environment || 'local';
  document.getElementById('edit-project-modal').style.display = 'flex';
}

export function showEditTaskModal(task) {
  state.editingTaskId = task.id;
  document.getElementById('edit-task-title').value = task.title || '';
  document.getElementById('edit-task-desc').value = task.description || '';
  const nodeSelect = document.getElementById('edit-task-node');
  if (nodeSelect) {
    nodeSelect.value = task.node_id || '';
  }
  document.getElementById('edit-task-status').value = task.status || 'backlog';
  document.getElementById('edit-task-modal').style.display = 'flex';
}
