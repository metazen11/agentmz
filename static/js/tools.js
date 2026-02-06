// Tool call rendering utilities

// JSON syntax highlighter
export function highlightJson(obj, indent = 0) {
  const spaces = '  '.repeat(indent);

  if (obj === null) {
    return `<span class="null">null</span>`;
  }
  if (typeof obj === 'boolean') {
    return `<span class="boolean">${obj}</span>`;
  }
  if (typeof obj === 'number') {
    return `<span class="number">${obj}</span>`;
  }
  if (typeof obj === 'string') {
    // Escape HTML and handle long strings
    const escaped = obj
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
    return `<span class="string">"${escaped}"</span>`;
  }
  if (Array.isArray(obj)) {
    if (obj.length === 0) return '[]';
    const items = obj.map(item => spaces + '  ' + highlightJson(item, indent + 1));
    return '[\n' + items.join(',\n') + '\n' + spaces + ']';
  }
  if (typeof obj === 'object') {
    const keys = Object.keys(obj);
    if (keys.length === 0) return '{}';
    const items = keys.map(key => {
      const keyHtml = `<span class="key">"${key}"</span>`;
      const valueHtml = highlightJson(obj[key], indent + 1);
      return spaces + '  ' + keyHtml + ': ' + valueHtml;
    });
    return '{\n' + items.join(',\n') + '\n' + spaces + '}';
  }
  return String(obj);
}

// Get a summary for a tool call (collapsed view)
export function getToolCallSummary(tc) {
  const args = tc.args || {};
  if (tc.tool === 'write') {
    const bytes = args.content ? args.content.length : 0;
    return `path="${args.path || '?'}", ${bytes} bytes`;
  }
  if (tc.tool === 'read') {
    return `path="${args.path || '?'}"`;
  }
  if (tc.tool === 'glob') {
    return `pattern="${args.pattern || '?'}"`;
  }
  if (tc.tool === 'grep') {
    return `pattern="${args.pattern || '?'}"`;
  }
  if (tc.tool === 'bash') {
    const cmd = args.command || '';
    return cmd.length > 40 ? cmd.slice(0, 40) + '...' : cmd;
  }
  if (tc.tool === 'edit') {
    const prompt = args.prompt || '';
    return prompt.length > 40 ? prompt.slice(0, 40) + '...' : prompt;
  }
  if (tc.tool === 'done') {
    return `status="${args.status || '?'}"`;
  }
  // Fallback: show first arg
  const firstKey = Object.keys(args)[0];
  if (firstKey) {
    const val = String(args[firstKey]);
    return `${firstKey}="${val.length > 30 ? val.slice(0, 30) + '...' : val}"`;
  }
  return '';
}

// Render tool calls as expandable HTML
export function renderToolCalls(toolCalls) {
  if (!toolCalls || toolCalls.length === 0) return '';

  let html = '<div class="tool-calls">';
  html += '<div class="tool-calls-header">Actions taken</div>';

  toolCalls.forEach((tc, idx) => {
    const summary = getToolCallSummary(tc);
    const output = tc.output || '';
    const isSuccess = !output.includes('"success": false') && !output.includes("'success': False");

    html += `<div class="tool-call" id="tool-call-${idx}">`;
    html += `<div class="tool-call-header" onclick="document.getElementById('tool-call-${idx}').classList.toggle('expanded')">`;
    html += `<span class="tool-call-toggle">▶</span>`;
    html += `<span class="tool-call-name">${tc.tool}</span>`;
    html += `<span class="tool-call-summary">${summary}</span>`;
    html += `<span class="tool-call-status ${isSuccess ? 'success' : 'error'}">${isSuccess ? 'OK' : 'ERR'}</span>`;
    html += '</div>';

    html += '<div class="tool-call-body">';

    // Arguments section
    html += '<div class="tool-call-section">';
    html += '<div class="tool-call-section-title">Arguments</div>';
    html += `<div class="tool-json">${highlightJson(tc.args || {})}</div>`;
    html += '</div>';

    // Output section (if available)
    if (output) {
      html += '<div class="tool-call-section">';
      html += '<div class="tool-call-section-title">Output</div>';
      // Try to parse output as JSON for highlighting
      let outputHtml;
      try {
        const outputObj = typeof output === 'string' ? JSON.parse(output.replace(/'/g, '"')) : output;
        outputHtml = highlightJson(outputObj);
      } catch {
        // Plain text fallback
        outputHtml = output.replace(/</g, '&lt;').replace(/>/g, '&gt;');
      }
      html += `<div class="tool-json">${outputHtml}</div>`;
      html += '</div>';
    }

    html += '</div>'; // tool-call-body
    html += '</div>'; // tool-call
  });

  html += '</div>';
  return html;
}
