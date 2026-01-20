/**
 * External Task Integration Module
 *
 * Provides UI functionality for importing tasks from external providers
 * like Asana, Jira, Linear, and GitHub Issues.
 */

import { MAIN_API } from '/static/js/config.js';
import { state } from '/static/js/state.js';

// Current wizard state
let wizardState = {
  step: 1,
  providers: [],
  selectedProvider: null,
  credentials: [],
  selectedCredential: null,
  externalProjects: [],
  selectedExternalProject: null,
  localProject: null,
  externalTasks: [],
  selectedTaskIds: new Set(),
  includeSubtasks: true,
  includeAttachments: false,
  integration: null,
};

/**
 * Reset wizard state for a fresh start
 */
function resetWizardState() {
  wizardState = {
    step: 1,
    providers: [],
    selectedProvider: null,
    credentials: [],
    selectedCredential: null,
    externalProjects: [],
    selectedExternalProject: null,
    localProject: null,
    externalTasks: [],
    selectedTaskIds: new Set(),
    includeSubtasks: true,
    includeAttachments: false,
    integration: null,
  };
}

/**
 * Show the integration wizard modal
 */
export function showIntegrationWizard() {
  resetWizardState();
  const modal = document.getElementById('integration-modal');
  if (!modal) {
    console.error('Integration modal not found');
    return;
  }
  modal.style.display = 'flex';
  loadProviders();
}

/**
 * Hide the integration wizard modal
 */
export function hideIntegrationWizard() {
  const modal = document.getElementById('integration-modal');
  if (modal) {
    modal.style.display = 'none';
  }
}

/**
 * Go to a specific wizard step
 */
function goToStep(step) {
  wizardState.step = step;
  renderWizardStep();
}

/**
 * Load available providers from API
 */
async function loadProviders() {
  try {
    const res = await fetch(`${MAIN_API}/integrations/providers`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    wizardState.providers = await res.json();
    renderWizardStep();
  } catch (err) {
    console.error('Failed to load providers:', err);
    showWizardError('Failed to load providers: ' + err.message);
  }
}

/**
 * Load stored credentials
 */
async function loadCredentials() {
  try {
    const res = await fetch(`${MAIN_API}/integrations/credentials`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    wizardState.credentials = await res.json();
    renderWizardStep();
  } catch (err) {
    console.error('Failed to load credentials:', err);
    showWizardError('Failed to load credentials: ' + err.message);
  }
}

/**
 * Load external projects from a credential
 */
async function loadExternalProjects(credentialId) {
  try {
    const res = await fetch(`${MAIN_API}/integrations/credentials/${credentialId}/projects`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    wizardState.externalProjects = data.projects || [];
    renderWizardStep();
  } catch (err) {
    console.error('Failed to load external projects:', err);
    showWizardError('Failed to load external projects: ' + err.message);
  }
}

/**
 * Load tasks from external project
 */
async function loadExternalTasks(integrationId) {
  try {
    const res = await fetch(`${MAIN_API}/integrations/${integrationId}/tasks`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    wizardState.externalTasks = data.tasks || [];
    renderWizardStep();
  } catch (err) {
    console.error('Failed to load external tasks:', err);
    showWizardError('Failed to load external tasks: ' + err.message);
  }
}

/**
 * Create a new credential
 */
async function createCredential(providerId, name, token) {
  try {
    const res = await fetch(`${MAIN_API}/integrations/credentials`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider_id: providerId, name, token }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const credential = await res.json();
    wizardState.selectedCredential = credential;
    goToStep(3); // Move to project selection
    loadExternalProjects(credential.id);
  } catch (err) {
    console.error('Failed to create credential:', err);
    showWizardError('Failed to authenticate: ' + err.message);
  }
}

/**
 * Create project mapping
 */
async function createProjectMapping() {
  if (!wizardState.selectedExternalProject || !wizardState.localProject) {
    showWizardError('Please select both external and local projects');
    return;
  }

  try {
    const res = await fetch(`${MAIN_API}/integrations/project-mapping`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: wizardState.localProject.id,
        credential_id: wizardState.selectedCredential.id,
        external_project_id: wizardState.selectedExternalProject.external_id,
        external_project_name: wizardState.selectedExternalProject.name,
        sync_direction: 'import',
      }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    wizardState.integration = await res.json();
    goToStep(5); // Move to task selection
    loadExternalTasks(wizardState.integration.id);
  } catch (err) {
    console.error('Failed to create mapping:', err);
    showWizardError('Failed to create project mapping: ' + err.message);
  }
}

/**
 * Import selected tasks
 */
async function importSelectedTasks() {
  if (wizardState.selectedTaskIds.size === 0) {
    showWizardError('Please select at least one task to import');
    return;
  }

  try {
    const res = await fetch(`${MAIN_API}/integrations/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        integration_id: wizardState.integration.id,
        task_ids: Array.from(wizardState.selectedTaskIds),
        include_subtasks: wizardState.includeSubtasks,
        include_attachments: wizardState.includeAttachments,
      }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const result = await res.json();
    showImportSuccess(result);
  } catch (err) {
    console.error('Failed to import tasks:', err);
    showWizardError('Failed to import tasks: ' + err.message);
  }
}

/**
 * Show import success and close wizard
 */
function showImportSuccess(result) {
  const content = document.getElementById('integration-content');
  if (!content) return;

  content.innerHTML = `
    <div class="wizard-success">
      <h3>Import Complete!</h3>
      <p>Successfully imported <strong>${result.imported_count}</strong> tasks.</p>
      ${result.skipped_count > 0 ? `<p>Skipped ${result.skipped_count} tasks (already imported or errors).</p>` : ''}
      <button onclick="window.integrationModule.hideIntegrationWizard()">Close</button>
    </div>
  `;
}

/**
 * Show error message in wizard
 */
function showWizardError(message) {
  const errorEl = document.getElementById('integration-error');
  if (errorEl) {
    errorEl.textContent = message;
    errorEl.style.display = 'block';
    setTimeout(() => { errorEl.style.display = 'none'; }, 5000);
  }
}

/**
 * Render the current wizard step
 */
function renderWizardStep() {
  const content = document.getElementById('integration-content');
  if (!content) return;

  switch (wizardState.step) {
    case 1:
      renderProviderSelection(content);
      break;
    case 2:
      renderAuthentication(content);
      break;
    case 3:
      renderExternalProjectSelection(content);
      break;
    case 4:
      renderLocalProjectSelection(content);
      break;
    case 5:
      renderTaskSelection(content);
      break;
    default:
      content.innerHTML = '<p>Unknown step</p>';
  }
}

/**
 * Step 1: Provider selection
 */
function renderProviderSelection(content) {
  const providerButtons = wizardState.providers.map(p => `
    <button class="provider-btn ${p.name === wizardState.selectedProvider?.name ? 'selected' : ''}"
            onclick="window.integrationModule.selectProvider('${p.name}')">
      <span class="provider-name">${escapeHtml(p.display_name)}</span>
      <span class="provider-auth">${escapeHtml(p.auth_type.toUpperCase())}</span>
    </button>
  `).join('');

  content.innerHTML = `
    <h3>Step 1: Select Provider</h3>
    <p>Choose which service to import tasks from:</p>
    <div class="provider-list">${providerButtons || '<p>No providers available</p>'}</div>
    <div class="wizard-nav">
      <button class="secondary" onclick="window.integrationModule.hideIntegrationWizard()">Cancel</button>
      <button ${!wizardState.selectedProvider ? 'disabled' : ''} onclick="window.integrationModule.goToStep(2)">Next</button>
    </div>
  `;
}

/**
 * Step 2: Authentication
 */
function renderAuthentication(content) {
  const provider = wizardState.selectedProvider;
  const existingCreds = wizardState.credentials.filter(c => c.provider_id === provider?.id);

  let credsHtml = '';
  if (existingCreds.length > 0) {
    credsHtml = `
      <div class="existing-creds">
        <p>Use existing credential:</p>
        ${existingCreds.map(c => `
          <button class="cred-btn ${c.id === wizardState.selectedCredential?.id ? 'selected' : ''}"
                  onclick="window.integrationModule.selectCredential(${c.id})">
            ${escapeHtml(c.name)} ${c.is_valid ? '✓' : '⚠'}
          </button>
        `).join('')}
      </div>
      <hr>
      <p>Or add a new credential:</p>
    `;
  }

  content.innerHTML = `
    <h3>Step 2: Authenticate with ${provider?.display_name || 'Provider'}</h3>
    ${credsHtml}
    <div class="auth-form">
      <label>Credential Name</label>
      <input type="text" id="cred-name" placeholder="My ${provider?.display_name} Account">
      <label>Personal Access Token</label>
      <input type="password" id="cred-token" placeholder="Paste your token here">
      <small>Generate a PAT at your provider's developer settings.</small>
    </div>
    <div class="wizard-nav">
      <button class="secondary" onclick="window.integrationModule.goToStep(1)">Back</button>
      <button onclick="window.integrationModule.submitCredential()">Authenticate</button>
    </div>
  `;
}

/**
 * Step 3: External project selection
 */
function renderExternalProjectSelection(content) {
  const projectItems = wizardState.externalProjects.map(p => `
    <div class="project-item ${p.external_id === wizardState.selectedExternalProject?.external_id ? 'selected' : ''}"
         onclick="window.integrationModule.selectExternalProject('${escapeAttr(p.external_id)}')">
      <span class="project-name">${escapeHtml(p.name)}</span>
      ${p.metadata?.workspace_name ? `<small>${escapeHtml(p.metadata.workspace_name)}</small>` : ''}
    </div>
  `).join('');

  content.innerHTML = `
    <h3>Step 3: Select External Project</h3>
    <p>Choose which project to import from:</p>
    <div class="project-list">${projectItems || '<p>Loading projects...</p>'}</div>
    <div class="wizard-nav">
      <button class="secondary" onclick="window.integrationModule.goToStep(2)">Back</button>
      <button ${!wizardState.selectedExternalProject ? 'disabled' : ''} onclick="window.integrationModule.goToStep(4)">Next</button>
    </div>
  `;
}

/**
 * Step 4: Local project selection
 */
function renderLocalProjectSelection(content) {
  const projects = state.projects || [];
  const projectItems = projects.map(p => `
    <div class="project-item ${p.id === wizardState.localProject?.id ? 'selected' : ''}"
         onclick="window.integrationModule.selectLocalProject(${p.id})">
      <span class="project-name">${escapeHtml(p.name)}</span>
      <small>${escapeHtml(p.workspace_path)}</small>
    </div>
  `).join('');

  content.innerHTML = `
    <h3>Step 4: Select Local Project</h3>
    <p>Choose which local project to import tasks into:</p>
    <div class="project-list">${projectItems || '<p>No projects available</p>'}</div>
    <div class="wizard-nav">
      <button class="secondary" onclick="window.integrationModule.goToStep(3)">Back</button>
      <button ${!wizardState.localProject ? 'disabled' : ''} onclick="window.integrationModule.createMapping()">Create Mapping</button>
    </div>
  `;
}

/**
 * Step 5: Task selection
 */
function renderTaskSelection(content) {
  const taskItems = wizardState.externalTasks.map(t => `
    <div class="task-item ${t.already_imported ? 'imported' : ''}"
         onclick="window.integrationModule.toggleTask('${escapeAttr(t.external_id)}')">
      <input type="checkbox" ${wizardState.selectedTaskIds.has(t.external_id) ? 'checked' : ''}
             ${t.already_imported ? 'disabled' : ''}>
      <div class="task-info">
        <span class="task-title">${escapeHtml(t.title)}</span>
        ${t.completed ? '<span class="task-done">Done</span>' : ''}
        ${t.already_imported ? '<span class="task-imported">Already imported</span>' : ''}
      </div>
    </div>
  `).join('');

  content.innerHTML = `
    <h3>Step 5: Select Tasks to Import</h3>
    <p>Select tasks from ${escapeHtml(wizardState.selectedExternalProject?.name || 'external project')}:</p>
    <div class="import-options">
      <label>
        <input type="checkbox" ${wizardState.includeSubtasks ? 'checked' : ''}
               onchange="window.integrationModule.toggleSubtasks(this.checked)">
        Include subtasks
      </label>
    </div>
    <div class="task-list">${taskItems || '<p>Loading tasks...</p>'}</div>
    <div class="wizard-nav">
      <button class="secondary" onclick="window.integrationModule.goToStep(4)">Back</button>
      <button ${wizardState.selectedTaskIds.size === 0 ? 'disabled' : ''}
              onclick="window.integrationModule.importTasks()">
        Import ${wizardState.selectedTaskIds.size} Tasks
      </button>
    </div>
  `;
}

/**
 * Helper: Escape HTML
 */
function escapeHtml(str) {
  return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/**
 * Helper: Escape attribute
 */
function escapeAttr(str) {
  return String(str || '').replace(/'/g, "\\'").replace(/"/g, '\\"');
}

// Public API exposed to window for onclick handlers
export function selectProvider(name) {
  wizardState.selectedProvider = wizardState.providers.find(p => p.name === name);
  loadCredentials();
  renderWizardStep();
}

export function selectCredential(id) {
  wizardState.selectedCredential = wizardState.credentials.find(c => c.id === id);
  if (wizardState.selectedCredential) {
    goToStep(3);
    loadExternalProjects(id);
  }
}

export function submitCredential() {
  const name = document.getElementById('cred-name')?.value?.trim();
  const token = document.getElementById('cred-token')?.value?.trim();
  if (!name || !token) {
    showWizardError('Please enter both name and token');
    return;
  }
  createCredential(wizardState.selectedProvider.id, name, token);
}

export function selectExternalProject(externalId) {
  wizardState.selectedExternalProject = wizardState.externalProjects.find(p => p.external_id === externalId);
  renderWizardStep();
}

export function selectLocalProject(id) {
  wizardState.localProject = state.projects.find(p => p.id === id);
  renderWizardStep();
}

export function createMapping() {
  createProjectMapping();
}

export function toggleTask(externalId) {
  const task = wizardState.externalTasks.find(t => t.external_id === externalId);
  if (task?.already_imported) return;

  if (wizardState.selectedTaskIds.has(externalId)) {
    wizardState.selectedTaskIds.delete(externalId);
  } else {
    wizardState.selectedTaskIds.add(externalId);
  }
  renderWizardStep();
}

export function toggleSubtasks(checked) {
  wizardState.includeSubtasks = checked;
}

export function importTasks() {
  importSelectedTasks();
}

// Expose module to window for onclick handlers
window.integrationModule = {
  showIntegrationWizard,
  hideIntegrationWizard,
  goToStep,
  selectProvider,
  selectCredential,
  submitCredential,
  selectExternalProject,
  selectLocalProject,
  createMapping,
  toggleTask,
  toggleSubtasks,
  importTasks,
};
