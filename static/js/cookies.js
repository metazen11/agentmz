// Cookie persistence utilities

export const COOKIE_KEYS = {
  PROJECT_ID: 'agentic_project_id',
  MODEL: 'agentic_model'
};

export function setCookie(name, value, days = 365) {
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
}

export function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
  return match ? decodeURIComponent(match[2]) : null;
}

export function deleteCookie(name) {
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
}

// Extract workspace name from path (handles trailing slashes, bare names, etc.)
export function getWorkspaceName(path) {
  if (!path) return 'poc';
  // Handle [%root%] - pass through to API (it will resolve)
  if (path.startsWith('[%root%]')) {
    return path;
  }
  // Remove trailing slashes and get last segment
  const cleaned = path.replace(/\/+$/, '');
  const parts = cleaned.split('/').filter(p => p && p !== '.');
  return parts.pop() || 'poc';
}

// Get display name for workspace (friendly name for UI)
export function getDisplayWorkspaceName(path) {
  if (!path) return 'poc';
  if (path.startsWith('[%root%]')) {
    return path === '[%root%]' ? 'v2 (self)' : path.replace('[%root%]/', 'v2/');
  }
  return getWorkspaceName(path);
}
