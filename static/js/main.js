// Main entry point - imports all modules and initializes the application

// Import modules
import { MAIN_API, AIDER_API, HEALTH_CHECK_INTERVAL_MS, getMainApiBase, initDom, dom } from './config.js';
import { state, setProjects, setTasks, setSelectedProject, setSelectedTask, setReferencedFiles, setAttachedImages, setEnvEntries, setEditingProjectId, setEditingTaskId } from './state.js';
import { COOKIE_KEYS, setCookie, getCookie, deleteCookie, getWorkspaceName, getDisplayWorkspaceName } from './cookies.js';
import { renderMarkdown } from './markdown.js';
import { highlightJson, getToolCallSummary, renderToolCalls } from './tools.js';
import { showNewProjectModal, showNewTaskModal, showEditProjectModal, showEditTaskModal, showGitModal, hideGitModal, showSettingsModal, hideSettingsModal, hideModals } from './modals.js';
import { initImageElements, setupImageDropzone, openImagePicker, handleImageFiles, renderImageList, removeImage, clearImages, describeImages } from './images.js';
import { initLogElements, getCurrentLogTab, toggleLogs, switchLogTab, connectLogStream, loadRecentLogs, appendLogLine, updateLogConnectionStatus } from './logs.js';
import { checkHealth, loadModels, applyModelSelection, runFullHealthCheck, restartService, toAiderModel } from './api.js';

// Re-export everything to window for onclick handlers
window.MAIN_API = MAIN_API;
window.AIDER_API = AIDER_API;
window.getMainApiBase = getMainApiBase;
window.state = state;
window.setCookie = setCookie;
window.getCookie = getCookie;
window.deleteCookie = deleteCookie;
window.getWorkspaceName = getWorkspaceName;
window.getDisplayWorkspaceName = getDisplayWorkspaceName;
window.renderMarkdown = renderMarkdown;
window.highlightJson = highlightJson;
window.renderToolCalls = renderToolCalls;
window.showNewProjectModal = showNewProjectModal;
window.showNewTaskModal = showNewTaskModal;
window.showEditProjectModal = (projectId) => {
  const project = state.projects.find(p => p.id === projectId);
  if (project) showEditProjectModal(project);
};
window.showEditTaskModal = (taskId) => {
  const task = findTaskById(taskId, state.tasks);
  if (task) showEditTaskModal(task);
};
window.showGitModal = () => {
  showGitModal();
  if (state.selectedProject) loadGitBranches(state.selectedProject.id);
};
window.hideGitModal = hideGitModal;
window.showSettingsModal = () => {
  showSettingsModal();
  loadSettings();
};
window.hideSettingsModal = hideSettingsModal;
window.hideModals = hideModals;
window.openImagePicker = openImagePicker;
window.removeImage = removeImage;
window.clearImages = clearImages;
window.toggleLogs = toggleLogs;
window.switchLogTab = switchLogTab;
window.checkHealth = checkHealth;
window.loadModels = loadModels;
window.applyModelSelection = () => applyModelSelection(addMessage);
window.runFullHealthCheck = runFullHealthCheck;

// These functions will be defined in the inline script
// and attached to window there for now

console.log('main.js loaded - modules initialized');
