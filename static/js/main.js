// Main entry point - imports all modules and initializes the application

// Import config and state
import { MAIN_API, AIDER_API, HEALTH_CHECK_INTERVAL_MS, getMainApiBase, initDom, dom } from './config.js';
import { state, setProjects, setTasks, setSelectedProject, setSelectedTask, setReferencedFiles, setAttachedImages, setEnvEntries, setEditingProjectId, setEditingTaskId } from './state.js';
import { COOKIE_KEYS, setCookie, getCookie, deleteCookie, getWorkspaceName, getDisplayWorkspaceName } from './cookies.js';
import { renderMarkdown } from './markdown.js';
import { highlightJson, getToolCallSummary, renderToolCalls } from './tools.js';

// Import chat modules
import {
  initCoreElements,
  addMessage,
  formatDate,
  truncateText,
  escapeHtml,
  renderTooltip,
  wireTooltipHandlers,
  hideGlobalTooltip,
  checkHealth,
  runFullHealthCheck,
  restartService,
  loadModels,
  applyModelSelection,
  switchAgentModel,
  describeImages,
  buildImageContextLayer,
  buildVisionImageLayer,
  setupImageDropzone,
  openImagePicker,
  handleImageFiles,
  renderImageList,
  removeImage,
  clearImages,
  addFileReference,
  removeFileReference,
  syncReferencedFilesFromPrompt,
  renderFileReferences,
  toggleLogs,
  switchLogTab,
  connectLogStream,
  loadRecentLogs,
  appendLogLine,
  updateLogConnectionStatus
} from './chat-core.js';

import {
  initGitElements,
  showGitModal,
  hideGitModal,
  loadGitBranches,
  checkoutBranch,
  createBranch,
  pullBranch,
  pushBranch,
  addRemote,
  initGitRepo,
  saveGitUser
} from './chat-git.js';

import {
  initSidebarElements,
  flattenTasks,
  findTaskById,
  populateParentTaskOptions,
  getEditingTaskId,
  hideModals,
  showNewProjectModal,
  showNewTaskModal,
  showSettingsModal,
  hideSettingsModal,
  loadProjects,
  renderProjects,
  selectProject,
  createProject,
  showEditProjectModal,
  updateProject,
  deleteProject,
  loadTasks,
  renderTasks,
  selectTask,
  openTaskEditor,
  createSubtask,
  showEditTaskModal,
  createTask,
  updateTask,
  deleteTask,
  loadFileTree,
  renderFileTree,
  toggleTreeNode,
  handleFileClick,
  openFileInVSCode,
  loadTaskAcceptanceCriteria,
  renderAcceptanceCriteria,
  resetNewTaskCriteria,
  renderNewTaskCriteria,
  addNewTaskCriteria,
  removeNewTaskCriteria,
  addAcceptanceCriteria,
  toggleAcceptanceCriteria,
  deleteAcceptanceCriteria,
  loadTaskComments,
  renderTaskComments,
  startEditComment,
  resetCommentForm,
  saveTaskComment,
  deleteTaskComment,
  loadTaskAttachments,
  renderTaskAttachments,
  uploadTaskAttachment,
  deleteTaskAttachment,
  loadTaskRuns,
  renderTaskRuns,
  refreshTaskRuns,
  loadSettings,
  renderSettings,
  applySettings,
  switchSettingsTab,
  getDefaultNodeId,
  renderNodeOptions,
  loadNodes,
  loadNodesForEditor,
  renderNodeList,
  selectNode,
  renderNodeEditor,
  createNewNode,
  cancelNodeEdit,
  saveNode,
  saveNewNode,
  deleteNode,
  restoreSelectionsFromCookies
} from './chat-sidebar.js';

import {
  initAgentElements,
  fetchTaskContext,
  buildTaskRequest,
  buildPromptForRequest,
  createTaskRun,
  updateTaskRun,
  postAgentComment,
  runAgentRequest,
  buildTaskPromptPreview,
  runTaskFromList,
  runTaskFromModal,
  sendMessage,
  setupAgentEventListeners
} from './chat-agent.js';

import { showIntegrationWizard, hideIntegrationWizard } from './integrations.js';

// ============================================================================
// Init function - orchestrates all module initialization
// ============================================================================

async function init() {
  console.log('init() called');

  // Initialize DOM refs for all modules
  initDom();
  initCoreElements();
  initGitElements();
  initSidebarElements();
  initAgentElements();

  // Setup event listeners
  setupAgentEventListeners();

  // Run health check and load initial data
  await runFullHealthCheck(true);
  await checkHealth();
  await loadModels();
  await loadNodes();
  await loadProjects();
  setupImageDropzone();

  // Restore project and model selections from cookies (or fall back to first project)
  await restoreSelectionsFromCookies();

  // Start log streaming for default tab only
  switchLogTab(state.currentLogTab);

  console.log('init() complete');

  // Start periodic health checks
  setInterval(() => runFullHealthCheck(false), HEALTH_CHECK_INTERVAL_MS);
}

// ============================================================================
// Expose everything to window for onclick handlers
// ============================================================================

Object.assign(window, {
  // Config
  MAIN_API,
  AIDER_API,
  getMainApiBase,
  state,

  // Cookies
  setCookie,
  getCookie,
  deleteCookie,
  getWorkspaceName,
  getDisplayWorkspaceName,

  // Markdown/Tools
  renderMarkdown,
  highlightJson,
  renderToolCalls,

  // Core functions
  addMessage,
  formatDate,
  truncateText,
  escapeHtml,
  checkHealth,
  runFullHealthCheck,
  loadModels,
  applyModelSelection,

  // Image functions
  openImagePicker,
  removeImage,
  clearImages,
  handleImageFiles,

  // File references
  addFileReference,
  removeFileReference,
  syncReferencedFilesFromPrompt,

  // Logs
  toggleLogs,
  switchLogTab,

  // Git functions
  showGitModal,
  hideGitModal,
  initGitRepo,
  saveGitUser,
  checkoutBranch,
  createBranch,
  pullBranch,
  pushBranch,
  addRemote,
  loadGitBranches,

  // Modal functions
  showNewProjectModal,
  showNewTaskModal,
  showSettingsModal,
  hideSettingsModal,
  hideModals,

  // Project functions
  selectProject,
  showEditProjectModal,
  createProject,
  updateProject,
  deleteProject,

  // Task functions
  openTaskEditor,
  createTask,
  updateTask,
  deleteTask,
  createSubtask,
  getEditingTaskId,
  findTaskById,

  // Acceptance criteria
  addAcceptanceCriteria,
  toggleAcceptanceCriteria,
  deleteAcceptanceCriteria,
  addNewTaskCriteria,
  removeNewTaskCriteria,

  // Comments
  saveTaskComment,
  resetCommentForm,
  startEditComment,
  deleteTaskComment,

  // Attachments
  uploadTaskAttachment,
  deleteTaskAttachment,

  // Task runs
  buildTaskPromptPreview,
  runTaskFromList,
  runTaskFromModal,

  // File tree
  handleFileClick,
  toggleTreeNode,
  openFileInVSCode,

  // Settings
  applySettings,
  switchSettingsTab,

  // Node Editor
  loadNodesForEditor,
  selectNode,
  createNewNode,
  cancelNodeEdit,
  saveNode,
  saveNewNode,
  deleteNode,

  // Integration wizard
  showIntegrationWizard,
  hideIntegrationWizard
});

// ============================================================================
// Initialize on load
// ============================================================================

init();

console.log('main.js loaded - modules initialized');
