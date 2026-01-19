// Centralized application state

export const state = {
  // Projects
  projects: [],
  selectedProject: null,
  editingProjectId: null,

  // Tasks
  tasks: [],
  selectedTask: null,
  editingTaskId: null,

  // Models
  availableModels: [],
  isModelSwitching: false,
  visionModel: '',

  // Files
  fileTree: [],
  referencedFiles: [],
  currentWorkspacePath: '',

  // Images
  attachedImages: [],

  // Settings
  envEntries: [],

  // Logs
  currentLogTab: 'ollama_http',
  logsCollapsed: false,
  logSockets: {},
  logSocketConnected: {}
};

// Legacy variable exports for gradual migration
// These allow direct access during transition
export let projects = state.projects;
export let tasks = state.tasks;
export let selectedProject = state.selectedProject;
export let selectedTask = state.selectedTask;
export let availableModels = state.availableModels;
export let isModelSwitching = state.isModelSwitching;
export let visionModel = state.visionModel;
export let referencedFiles = state.referencedFiles;
export let attachedImages = state.attachedImages;
export let envEntries = state.envEntries;
export let currentLogTab = state.currentLogTab;
export let editingProjectId = state.editingProjectId;
export let editingTaskId = state.editingTaskId;

// State setters for controlled updates
export function setProjects(value) {
  state.projects = value;
  projects = value;
}

export function setTasks(value) {
  state.tasks = value;
  tasks = value;
}

export function setSelectedProject(value) {
  state.selectedProject = value;
  selectedProject = value;
}

export function setSelectedTask(value) {
  state.selectedTask = value;
  selectedTask = value;
}

export function setAvailableModels(value) {
  state.availableModels = value;
  availableModels = value;
}

export function setIsModelSwitching(value) {
  state.isModelSwitching = value;
  isModelSwitching = value;
}

export function setVisionModel(value) {
  state.visionModel = value;
  visionModel = value;
}

export function setReferencedFiles(value) {
  state.referencedFiles = value;
  referencedFiles = value;
}

export function setAttachedImages(value) {
  state.attachedImages = value;
  attachedImages = value;
}

export function setEnvEntries(value) {
  state.envEntries = value;
  envEntries = value;
}

export function setCurrentLogTab(value) {
  state.currentLogTab = value;
  currentLogTab = value;
}

export function setEditingProjectId(value) {
  state.editingProjectId = value;
  editingProjectId = value;
}

export function setEditingTaskId(value) {
  state.editingTaskId = value;
  editingTaskId = value;
}
