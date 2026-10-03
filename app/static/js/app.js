/**
 * Autonomous Agent Hub - Frontend Application Controller
 */

// State
let agentsState = [];
let activeAgentForChat = null;
let activeAgentForSkill = null;
let activeAgentForEdit = null;

// Color Mapping Helper for Tailwind
const AVATAR_COLORS = {
  emerald: { bg: 'bg-emerald-500/20', text: 'text-emerald-400', border: 'border-emerald-500/40', badge: 'bg-emerald-500' },
  cyan: { bg: 'bg-cyan-500/20', text: 'text-cyan-400', border: 'border-cyan-500/40', badge: 'bg-cyan-500' },
  amber: { bg: 'bg-amber-500/20', text: 'text-amber-400', border: 'border-amber-500/40', badge: 'bg-amber-500' },
  violet: { bg: 'bg-violet-500/20', text: 'text-violet-400', border: 'border-violet-500/40', badge: 'bg-violet-500' },
  rose: { bg: 'bg-rose-500/20', text: 'text-rose-400', border: 'border-rose-500/40', badge: 'bg-rose-500' },
  indigo: { bg: 'bg-indigo-500/20', text: 'text-indigo-400', border: 'border-indigo-500/40', badge: 'bg-indigo-500' },
  blue: { bg: 'bg-blue-500/20', text: 'text-blue-400', border: 'border-blue-500/40', badge: 'bg-blue-500' },
  fuchsia: { bg: 'bg-fuchsia-500/20', text: 'text-fuchsia-400', border: 'border-fuchsia-500/40', badge: 'bg-fuchsia-500' }
};

// ==========================================
// Toast Notification Engine
// ==========================================
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  const typeStyles = {
    success: 'bg-emerald-950/90 border-emerald-500/50 text-emerald-200',
    error: 'bg-rose-950/90 border-rose-500/50 text-rose-200',
    warning: 'bg-amber-950/90 border-amber-500/50 text-amber-200',
    info: 'bg-slate-900/90 border-slate-700 text-slate-200'
  };

  const icons = {
    success: '<i data-lucide="check-circle-2" class="w-4 h-4 text-emerald-400 shrink-0"></i>',
    error: '<i data-lucide="alert-circle" class="w-4 h-4 text-rose-400 shrink-0"></i>',
    warning: '<i data-lucide="alert-triangle" class="w-4 h-4 text-amber-400 shrink-0"></i>',
    info: '<i data-lucide="info" class="w-4 h-4 text-blue-400 shrink-0"></i>'
  };

  toast.className = `flex items-center gap-2.5 px-4 py-3 rounded-xl border backdrop-blur-md shadow-2xl text-xs font-medium transition-all duration-300 transform translate-y-2 opacity-0 ${typeStyles[type] || typeStyles.info}`;
  toast.innerHTML = `${icons[type] || icons.info}<span>${escapeHtml(message)}</span>`;

  container.appendChild(toast);
  lucide.createIcons();

  requestAnimationFrame(() => {
    toast.classList.remove('translate-y-2', 'opacity-0');
  });

  setTimeout(() => {
    toast.classList.add('opacity-0', 'translate-y-2');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Helper to escape HTML safely
function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.innerText = str;
  return div.innerHTML;
}

// Helper to format Markdown basics (bold, italics, code blocks, lists)
function renderMarkdown(text) {
  if (!text) return '';
  let escaped = escapeHtml(text);
  
  // Code blocks ```code```
  escaped = escaped.replace(/```([\s\S]*?)```/g, '<pre class="bg-slate-950 p-3 rounded-lg my-2 font-mono text-xs overflow-x-auto border border-slate-800 text-emerald-300"><code>$1</code></pre>');
  // Inline code `code`
  escaped = escaped.replace(/`([^`]+)`/g, '<code class="bg-slate-950/80 px-1.5 py-0.5 rounded text-indigo-300 font-mono text-[11px] border border-slate-800">$1</code>');
  // Bold **text**
  escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold text-slate-100">$1</strong>');
  // Italic *text*
  escaped = escaped.replace(/\*([^*]+)\*/g, '<em class="italic text-slate-300">$1</em>');
  // Blockquotes
  escaped = escaped.replace(/^>\s*(.+)$/gm, '<blockquote class="border-l-2 border-indigo-500 pl-3 py-1 text-slate-400 my-1 bg-indigo-950/20 rounded-r">$1</blockquote>');
  // Line breaks
  escaped = escaped.replace(/\n/g, '<br/>');

  return escaped;
}

// ==========================================
// API Handlers
// ==========================================

async function loadAgents() {
  const loadingEl = document.getElementById('agents-loading');
  const gridEl = document.getElementById('agents-grid');
  const emptyEl = document.getElementById('agents-empty');

  if (loadingEl) loadingEl.classList.remove('hidden');

  try {
    const res = await fetch('/api/agents/');
    if (!res.ok) throw new Error('Failed to fetch agents');
    agentsState = await res.json();
    renderStats();
    renderAgentGrid();
  } catch (err) {
    console.error(err);
    showToast('Failed to load agents list', 'error');
  } finally {
    if (loadingEl) loadingEl.classList.add('hidden');
  }
}

function renderStats() {
  const totalCount = agentsState.length;
  const activeCount = agentsState.filter(a => a.is_active).length;
  const mcpsCount = agentsState.reduce((acc, curr) => acc + (curr.skills ? curr.skills.length : 0), 0);

  const totalEl = document.getElementById('stat-total-agents');
  const activeEl = document.getElementById('stat-active-agents');
  const mcpsEl = document.getElementById('stat-total-mcps');

  if (totalEl) totalEl.textContent = totalCount;
  if (activeEl) activeEl.textContent = activeCount;
  if (mcpsEl) mcpsEl.textContent = mcpsCount;
}

function renderAgentGrid() {
  const gridEl = document.getElementById('agents-grid');
  const emptyEl = document.getElementById('agents-empty');
  const searchInput = document.getElementById('search-input');
  const filterActive = document.getElementById('filter-active');

  if (!gridEl) return;

  const searchQuery = (searchInput?.value || '').toLowerCase().trim();
  const filterActiveVal = filterActive?.value || 'all';

  let filtered = agentsState.filter(agent => {
    const matchesSearch = agent.name.toLowerCase().includes(searchQuery) ||
                          agent.role.toLowerCase().includes(searchQuery) ||
                          agent.system_prompt.toLowerCase().includes(searchQuery);

    if (!matchesSearch) return false;
    if (filterActiveVal === 'active') return agent.is_active;
    if (filterActiveVal === 'inactive') return !agent.is_active;
    return true;
  });

  if (filtered.length === 0) {
    gridEl.innerHTML = '';
    if (emptyEl) emptyEl.classList.remove('hidden');
    return;
  }

  if (emptyEl) emptyEl.classList.add('hidden');

  gridEl.innerHTML = filtered.map(agent => {
    const colorKey = AVATAR_COLORS[agent.avatar_color] ? agent.avatar_color : 'emerald';
    const colorStyle = AVATAR_COLORS[colorKey];
    const initial = agent.name.charAt(0).toUpperCase() || 'A';
    const skillsList = agent.skills || [];

    return `
      <div class="glass-card rounded-2xl p-5 flex flex-col justify-between relative overflow-hidden group">
        <!-- Top Status Gradient Bar -->
        <div class="absolute top-0 left-0 right-0 h-1 ${agent.is_active ? colorStyle.badge : 'bg-slate-700'}"></div>
        
        <div>
          <!-- Card Header -->
          <div class="flex items-start justify-between gap-3 mb-4">
            <div class="flex items-center gap-3">
              <!-- Avatar Initial Badge -->
              <div class="w-11 h-11 rounded-xl ${colorStyle.bg} ${colorStyle.border} border flex items-center justify-center font-bold text-base ${colorStyle.text} shadow-inner">
                ${initial}
              </div>
              <div>
                <h3 class="font-semibold text-slate-100 text-sm md:text-base leading-tight group-hover:text-indigo-400 transition-colors">
                  ${escapeHtml(agent.name)}
                </h3>
                <span class="inline-flex items-center gap-1.5 text-[11px] font-medium text-slate-400">
                  <span class="w-1.5 h-1.5 rounded-full ${colorStyle.badge}"></span>
                  ${escapeHtml(agent.role)}
                </span>
              </div>
            </div>

            <!-- Active / Inactive Switch -->
            <label class="relative inline-flex items-center cursor-pointer select-none" title="${agent.is_active ? 'Active Fleet' : 'Inactive Agent'}">
              <input type="checkbox" ${agent.is_active ? 'checked' : ''} onchange="toggleAgentActive('${agent.id}', this.checked)" class="sr-only peer">
              <div class="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-600 border border-slate-700"></div>
            </label>
          </div>

          <!-- Persona Snippet -->
          <div class="mb-4">
            <p class="text-xs text-slate-300/90 line-clamp-2 leading-relaxed bg-slate-950/40 p-2.5 rounded-xl border border-slate-800/80 font-mono">
              "${escapeHtml(agent.system_prompt)}"
            </p>
            <button onclick="viewFullPrompt('${agent.id}')" class="text-[11px] text-indigo-400 hover:text-indigo-300 font-medium mt-1 flex items-center gap-1 transition-colors">
              <i data-lucide="eye" class="w-3 h-3"></i> Inspect Full Instructions
            </button>
          </div>

          <!-- Connected Skills / MCP Endpoints -->
          <div class="mb-4">
            <div class="flex items-center justify-between text-[11px] text-slate-400 font-semibold mb-2">
              <span class="flex items-center gap-1">
                <i data-lucide="plug-zap" class="w-3 h-3 text-amber-400"></i> Connected MCP Endpoints (${skillsList.length})
              </span>
              <button onclick="openAddSkillModal('${agent.id}')" class="text-indigo-400 hover:text-indigo-300 flex items-center gap-0.5 text-[11px] font-medium transition-colors">
                <i data-lucide="plus" class="w-3 h-3"></i> Add
              </button>
            </div>

            <div class="flex flex-wrap gap-1.5 min-h-[32px]">
              ${skillsList.length === 0 ? `
                <span class="text-[11px] text-slate-500 italic flex items-center gap-1 py-1">
                  <i data-lucide="radio" class="w-3 h-3"></i> Standalone Autonomous Cognition
                </span>
              ` : skillsList.map(skill => `
                <div class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-mono font-medium ${skill.is_enabled ? 'bg-slate-900 border-slate-700 text-slate-300' : 'bg-slate-950 border-slate-800 text-slate-500 opacity-60'} border group/skill">
                  <span class="w-1.5 h-1.5 rounded-full ${skill.is_enabled ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'}"></span>
                  <span title="${escapeHtml(skill.skill_url)}">${escapeHtml(skill.skill_name)}</span>
                  <button onclick="detachSkill('${agent.id}', '${skill.id}', event)" title="Detach Skill" class="text-slate-500 hover:text-rose-400 ml-1 transition-colors">
                    <i data-lucide="x" class="w-2.5 h-2.5"></i>
                  </button>
                </div>
              `).join('')}
            </div>
          </div>
        </div>

        <!-- Card Action Footer -->
        <div class="pt-3 mt-2 border-t border-slate-800/80 flex items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <button onclick="openChatDrawer('${agent.id}')" class="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all shadow-md shadow-indigo-900/30">
              <i data-lucide="message-square" class="w-3.5 h-3.5"></i> Chat / Test
            </button>
            <button onclick="openEditModal('${agent.id}')" class="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 rounded-lg text-xs transition-colors" title="Edit Agent">
              <i data-lucide="settings-2" class="w-4 h-4"></i>
            </button>
          </div>

          <button onclick="deleteAgent('${agent.id}', '${escapeHtml(agent.name)}')" class="p-1.5 text-slate-500 hover:text-rose-400 hover:bg-rose-950/30 rounded-lg text-xs transition-colors" title="Delete Agent">
            <i data-lucide="trash-2" class="w-4 h-4"></i>
          </button>
        </div>
      </div>
    `;
  }).join('');

  lucide.createIcons();
}

// ==========================================
// Agent Operations (Create, Update, Delete, Toggle)
// ==========================================

async function toggleAgentActive(agentId, isActive) {
  try {
    const res = await fetch(`/api/agents/${agentId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: isActive })
    });

    if (!res.ok) throw new Error('Failed to update agent status');
    
    // Update local state
    const agent = agentsState.find(a => a.id === agentId);
    if (agent) agent.is_active = isActive;

    renderStats();
    renderAgentGrid();
    showToast(`Agent status updated to ${isActive ? 'ACTIVE' : 'INACTIVE'}`, 'info');
  } catch (err) {
    console.error(err);
    showToast('Failed to toggle agent state', 'error');
    loadAgents(); // Reload to restore actual state
  }
}

async function handleCreateAgent(e) {
  e.preventDefault();
  const form = document.getElementById('create-agent-form');
  const name = form.elements['name'].value.trim();
  const role = form.elements['role'].value.trim();
  const avatar_color = form.elements['avatar_color'].value;
  const system_prompt = form.elements['system_prompt'].value.trim();
  const is_active = form.elements['is_active'].checked;

  if (!name || !role || !system_prompt) {
    showToast('Please fill all required fields', 'warning');
    return;
  }

  const submitBtn = document.getElementById('create-agent-submit-btn');
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i> Deploying...';
    lucide.createIcons();
  }

  try {
    const res = await fetch('/api/agents/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, role, avatar_color, system_prompt, is_active })
    });

    if (!res.ok) throw new Error('Failed to create agent');
    
    closeModal('create-agent-modal');
    form.reset();
    showToast(`Autonomous Agent '${name}' deployed!`, 'success');
    await loadAgents();
  } catch (err) {
    console.error(err);
    showToast('Failed to deploy new agent', 'error');
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = 'Deploy Agent';
    }
  }
}

async function handleUpdateAgent(e) {
  e.preventDefault();
  if (!activeAgentForEdit) return;

  const form = document.getElementById('edit-agent-form');
  const name = form.elements['edit-name'].value.trim();
  const role = form.elements['edit-role'].value.trim();
  const avatar_color = form.elements['edit-avatar_color'].value;
  const system_prompt = form.elements['edit-system_prompt'].value.trim();
  const is_active = form.elements['edit-is_active'].checked;

  try {
    const res = await fetch(`/api/agents/${activeAgentForEdit.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, role, avatar_color, system_prompt, is_active })
    });

    if (!res.ok) throw new Error('Failed to update agent');

    closeModal('edit-agent-modal');
    showToast(`Agent '${name}' configuration saved!`, 'success');
    await loadAgents();
  } catch (err) {
    console.error(err);
    showToast('Failed to save agent changes', 'error');
  }
}

async function deleteAgent(agentId, agentName) {
  if (!confirm(`Are you sure you want to delete autonomous agent '${agentName}'?\nAll associated MCP skills and task history will be permanently deleted.`)) {
    return;
  }

  try {
    const res = await fetch(`/api/agents/${agentId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete agent');

    showToast(`Agent '${agentName}' deleted`, 'info');
    await loadAgents();
  } catch (err) {
    console.error(err);
    showToast('Error deleting agent', 'error');
  }
}

// ==========================================
// Skills (MCP Endpoints) Operations
// ==========================================

function openAddSkillModal(agentId) {
  const agent = agentsState.find(a => a.id === agentId);
  if (!agent) return;

  activeAgentForSkill = agent;
  const titleEl = document.getElementById('add-skill-agent-title');
  if (titleEl) titleEl.textContent = agent.name;

  const form = document.getElementById('add-skill-form');
  if (form) form.reset();

  populateFleetSkillPickup();
  openModal('add-skill-modal');
}

async function handleAddSkill(e) {
  e.preventDefault();
  if (!activeAgentForSkill) return;

  const form = document.getElementById('add-skill-form');
  const skill_name = form.elements['skill_name'].value.trim();
  const skill_url = form.elements['skill_url'].value.trim();

  if (!skill_name || !skill_url) {
    showToast('Skill name and endpoint URL are required', 'warning');
    return;
  }

  try {
    const res = await fetch(`/api/agents/${activeAgentForSkill.id}/skills`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skill_name, skill_url, is_enabled: true })
    });

    if (!res.ok) throw new Error('Failed to attach MCP skill');

    closeModal('add-skill-modal');
    showToast(`MCP Tool '${skill_name}' attached to ${activeAgentForSkill.name}!`, 'success');
    await loadAgents();

    // If chat drawer is open with this agent, update its skills bar
    if (activeAgentForChat && activeAgentForChat.id === activeAgentForSkill.id) {
      const updatedAgent = agentsState.find(a => a.id === activeAgentForChat.id);
      if (updatedAgent) {
        activeAgentForChat = updatedAgent;
        renderChatHeaderSkills();
      }
    }
  } catch (err) {
    console.error(err);
    showToast('Error attaching MCP skill', 'error');
  }
}

async function detachSkill(agentId, skillId, event) {
  if (event) event.stopPropagation();

  if (!confirm('Detach this MCP skill endpoint from the agent?')) return;

  try {
    const res = await fetch(`/api/agents/${agentId}/skills/${skillId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to detach skill');

    showToast('Skill endpoint detached', 'info');
    await loadAgents();

    if (activeAgentForChat && activeAgentForChat.id === agentId) {
      const updatedAgent = agentsState.find(a => a.id === agentId);
      if (updatedAgent) {
        activeAgentForChat = updatedAgent;
        renderChatHeaderSkills();
      }
    }
  } catch (err) {
    console.error(err);
    showToast('Error detaching skill', 'error');
  }
}

function applySkillPreset(name, url) {
  const form = document.getElementById('add-skill-form');
  if (!form) return;
  form.elements['skill_name'].value = name;
  form.elements['skill_url'].value = url;
}

// ==========================================
// Chat / Test Interactive Slide-over Drawer
// ==========================================

async function openChatDrawer(agentId) {
  try {
    let agent = agentsState.find(a => String(a.id) === String(agentId));
    if (!agent) {
      // Fallback fetch from API if not yet in state
      try {
        const res = await fetch(`/api/agents/${agentId}`);
        if (res.ok) {
          agent = await res.json();
          agentsState.push(agent);
        }
      } catch (e) {
        console.warn("Could not fetch agent directly:", e);
      }
    }

    if (!agent) {
      showToast('Agent not found', 'error');
      return;
    }

    activeAgentForChat = agent;

    // Immediately unhide and slide in Drawer UI
    const backdrop = document.getElementById('chat-drawer-backdrop');
    const panel = document.getElementById('chat-drawer-panel');

    if (backdrop && panel) {
      backdrop.classList.remove('hidden');
      setTimeout(() => {
        backdrop.classList.remove('opacity-0');
        panel.classList.remove('translate-x-full');
      }, 10);
    }

    // Set Agent Info in Drawer
    const colorKey = (agent.avatar_color && AVATAR_COLORS[agent.avatar_color]) ? agent.avatar_color : 'emerald';
    const colorStyle = AVATAR_COLORS[colorKey] || AVATAR_COLORS['emerald'];
    const agentName = agent.name || 'Autonomous Agent';
    const agentRole = agent.role || 'Specialist';
    const initial = (agentName.charAt(0) || 'A').toUpperCase();

    const avatarEl = document.getElementById('drawer-agent-avatar');
    const nameEl = document.getElementById('drawer-agent-name');
    const roleEl = document.getElementById('drawer-agent-role');

    if (avatarEl) {
      avatarEl.className = `w-9 h-9 rounded-xl ${colorStyle.bg} ${colorStyle.border} border flex items-center justify-center font-bold text-sm ${colorStyle.text}`;
      avatarEl.textContent = initial;
    }
    if (nameEl) nameEl.textContent = agentName;
    if (roleEl) roleEl.textContent = agentRole;

    renderChatHeaderSkills();

    // Reset/Load Message History
    const messagesContainer = document.getElementById('chat-messages-container');
    if (messagesContainer) {
      messagesContainer.innerHTML = `
        <div class="flex flex-col items-center justify-center py-12 text-slate-500">
          <i data-lucide="loader-2" class="w-6 h-6 animate-spin text-indigo-400 mb-2"></i>
          <p class="text-xs">Connecting to cognitive task log...</p>
        </div>
      `;
      if (window.lucide && lucide.createIcons) lucide.createIcons();
    }

    // Fetch past logs asynchronously
    await loadAgentChatLogs(agentId);
  } catch (err) {
    console.error("Error opening chat drawer:", err);
    showToast('Failed to open chat window', 'error');
  }
}

function closeChatDrawer() {
  const backdrop = document.getElementById('chat-drawer-backdrop');
  const panel = document.getElementById('chat-drawer-panel');

  if (backdrop && panel) {
    backdrop.classList.add('opacity-0');
    panel.classList.add('translate-x-full');
    setTimeout(() => {
      backdrop.classList.add('hidden');
      activeAgentForChat = null;
    }, 300);
  }
}

function renderChatHeaderSkills() {
  const skillsContainer = document.getElementById('drawer-skills-bar');
  if (!skillsContainer || !activeAgentForChat) return;

  const skills = activeAgentForChat.skills || [];
  if (skills.length === 0) {
    skillsContainer.innerHTML = `
      <span class="text-[11px] text-slate-400 flex items-center gap-1">
        <i data-lucide="cpu" class="w-3.5 h-3.5 text-indigo-400"></i> Standalone Reasoning Core
      </span>
    `;
  } else {
    skillsContainer.innerHTML = `
      <span class="text-[11px] text-slate-400 flex items-center gap-1 mr-1 shrink-0">
        <i data-lucide="plug-zap" class="w-3.5 h-3.5 text-amber-400"></i> Active MCPs:
      </span>
      ${skills.map(s => `
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-900 text-slate-300 text-[10px] font-mono border border-slate-700">
          <span class="w-1.5 h-1.5 rounded-full ${s.is_enabled ? 'bg-emerald-400' : 'bg-slate-600'}"></span>
          ${escapeHtml(s.skill_name)}
        </span>
      `).join('')}
    `;
  }
  lucide.createIcons();
}

async function loadAgentChatLogs(agentId) {
  const messagesContainer = document.getElementById('chat-messages-container');
  if (!messagesContainer) return;

  try {
    const res = await fetch(`/api/agents/${agentId}/logs`);
    if (!res.ok) throw new Error('Failed to load logs');
    const logs = await res.json();

    messagesContainer.innerHTML = '';

    // Welcome message from agent
    appendMessageToChat('system', `Initialized communication with **${activeAgentForChat.name}** (*${activeAgentForChat.role}*). Submit test prompts or execution directives below.`);

    if (logs.length > 0) {
      logs.forEach(log => {
        appendMessageToChat('user', log.user_input, log.created_at);
        appendMessageToChat('agent', log.agent_response, log.created_at, log.status);
      });
    }

    scrollChatToBottom();
  } catch (err) {
    console.error(err);
    messagesContainer.innerHTML = `<div class="p-4 text-xs text-rose-400">Failed to load conversation history.</div>`;
  }
}

function appendMessageToChat(sender, text, timestamp = null, status = 'success') {
  const container = document.getElementById('chat-messages-container');
  if (!container) return;

  const msgDiv = document.createElement('div');
  const timeStr = timestamp ? new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  if (sender === 'user') {
    msgDiv.className = 'flex justify-end mb-4 animate-fadeIn';
    msgDiv.innerHTML = `
      <div class="max-w-[85%] flex flex-col items-end">
        <div class="chat-bubble-user px-4 py-2.5 rounded-2xl rounded-tr-none text-xs leading-relaxed shadow-lg">
          ${renderMarkdown(text)}
        </div>
        <span class="text-[10px] text-slate-500 mt-1 font-mono">${timeStr}</span>
      </div>
    `;
  } else if (sender === 'agent') {
    const colorKey = activeAgentForChat ? activeAgentForChat.avatar_color : 'emerald';
    const colorStyle = AVATAR_COLORS[colorKey] || AVATAR_COLORS.emerald;

    msgDiv.className = 'flex justify-start mb-4 gap-2.5 animate-fadeIn';
    msgDiv.innerHTML = `
      <div class="w-7 h-7 rounded-lg ${colorStyle.bg} ${colorStyle.border} border flex items-center justify-center font-bold text-xs ${colorStyle.text} shrink-0 mt-0.5">
        ${activeAgentForChat ? activeAgentForChat.name.charAt(0).toUpperCase() : 'A'}
      </div>
      <div class="max-w-[85%] flex flex-col items-start">
        <div class="chat-bubble-agent px-4 py-3 rounded-2xl rounded-tl-none text-xs text-slate-200 leading-relaxed shadow-lg border">
          ${renderMarkdown(text)}
          ${status === 'failed' ? '<div class="mt-2 text-[10px] text-rose-400 font-semibold flex items-center gap-1"><i data-lucide="alert-circle" class="w-3 h-3"></i> Task Execution Flagged with Errors</div>' : ''}
        </div>
        <span class="text-[10px] text-slate-500 mt-1 font-mono">${timeStr}</span>
      </div>
    `;
  } else {
    // System message
    msgDiv.className = 'flex justify-center my-3';
    msgDiv.innerHTML = `
      <div class="px-3 py-1.5 rounded-full bg-slate-900/80 border border-slate-800 text-[11px] text-slate-400 text-center max-w-[90%]">
        ${renderMarkdown(text)}
      </div>
    `;
  }

  container.appendChild(msgDiv);
  lucide.createIcons();
  scrollChatToBottom();
}

function scrollChatToBottom() {
  const container = document.getElementById('chat-messages-container');
  if (container) {
    container.scrollTop = container.scrollHeight;
  }
}

async function sendChatMessage() {
  if (!activeAgentForChat) return;

  const inputEl = document.getElementById('chat-input-text');
  const message = (inputEl?.value || '').trim();

  if (!message) return;

  // Clear input
  inputEl.value = '';

  // Append user message immediately
  appendMessageToChat('user', message);

  // Show dynamic execution status stepper indicator
  const container = document.getElementById('chat-messages-container');
  const typingDiv = document.createElement('div');
  typingDiv.id = 'chat-typing-indicator';
  typingDiv.className = 'flex justify-start mb-4 gap-2.5 animate-fadeIn';
  
  const colorKey = activeAgentForChat.avatar_color || 'emerald';
  const colorStyle = AVATAR_COLORS[colorKey] || AVATAR_COLORS.emerald;

  typingDiv.innerHTML = `
    <div class="w-7 h-7 rounded-lg ${colorStyle.bg} ${colorStyle.border} border flex items-center justify-center font-bold text-xs ${colorStyle.text} shrink-0 mt-0.5">
      <i data-lucide="sparkles" class="w-3.5 h-3.5 animate-spin"></i>
    </div>
    <div class="chat-bubble-agent px-4 py-3 rounded-2xl rounded-tl-none text-xs text-slate-200 shadow-xl border border-slate-800/90 flex flex-col gap-1.5 min-w-[260px] max-w-[85%] bg-slate-900/90 backdrop-blur-md">
      <div class="flex items-center gap-2.5">
        <div class="relative flex items-center justify-center w-4 h-4 shrink-0">
          <span class="w-3.5 h-3.5 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin"></span>
          <span class="absolute w-1.5 h-1.5 rounded-full bg-indigo-400 animate-ping opacity-75"></span>
        </div>
        <span id="chat-progress-step" class="font-mono text-xs font-semibold text-indigo-300 transition-all duration-200">
          🧠 Analyzing prompt & selecting MCP tool...
        </span>
      </div>
      <div class="flex items-center justify-between text-[10px] text-slate-500 font-mono border-t border-slate-800/80 pt-1.5 mt-0.5">
        <span class="flex items-center gap-1">
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> MCP Pipeline Active
        </span>
        <span class="text-slate-600">Autonomous Cycle</span>
      </div>
    </div>
  `;
  container.appendChild(typingDiv);
  lucide.createIcons();
  scrollChatToBottom();

  const sendBtn = document.getElementById('chat-send-btn');
  if (sendBtn) sendBtn.disabled = true;

  try {
    const res = await fetch(`/api/agents/${activeAgentForChat.id}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message })
    });

    if (!res.ok) {
      throw new Error(`Server returned HTTP ${res.status}`);
    }

    if (res.body && res.body.getReader) {
      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let receivedFinal = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop(); // keep last incomplete chunk

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data:')) continue;

          try {
            const data = JSON.parse(trimmed.replace(/^data:\s*/, ''));
            if (data.type === 'status') {
              const stepEl = document.getElementById('chat-progress-step');
              if (stepEl) {
                stepEl.style.opacity = '0.5';
                setTimeout(() => {
                  stepEl.textContent = data.text;
                  stepEl.style.opacity = '1';
                }, 100);
                scrollChatToBottom();
              }
            } else if (data.type === 'final') {
              receivedFinal = true;
              if (typingDiv) typingDiv.remove();
              appendMessageToChat('agent', data.response, data.created_at, data.status);
            }
          } catch (e) {
            console.warn('Error parsing SSE event:', e);
          }
        }
      }

      if (!receivedFinal && typingDiv) {
        typingDiv.remove();
      }
    } else {
      // Fallback if reader not supported
      const data = await res.json();
      if (typingDiv) typingDiv.remove();
      appendMessageToChat('agent', data.response, data.created_at, data.status);
    }
  } catch (err) {
    if (typingDiv) typingDiv.remove();
    console.error(err);
    appendMessageToChat('agent', `⚠️ **Error communicating with agent**: ${err.message}`, null, 'failed');
  } finally {
    if (sendBtn) sendBtn.disabled = false;
    inputEl?.focus();
  }
}

function sendQuickPrompt(promptText) {
  const inputEl = document.getElementById('chat-input-text');
  if (inputEl) {
    inputEl.value = promptText;
    sendChatMessage();
  }
}

// ==========================================
// Modal Helpers
// ==========================================

function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove('hidden');
    requestAnimationFrame(() => modal.classList.remove('opacity-0'));
  }
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add('opacity-0');
    setTimeout(() => modal.classList.add('hidden'), 200);
  }
}

function viewFullPrompt(agentId) {
  const agent = agentsState.find(a => a.id === agentId);
  if (!agent) return;

  const titleEl = document.getElementById('view-prompt-title');
  const roleEl = document.getElementById('view-prompt-role');
  const bodyEl = document.getElementById('view-prompt-body');

  if (titleEl) titleEl.textContent = agent.name;
  if (roleEl) roleEl.textContent = agent.role;
  if (bodyEl) bodyEl.textContent = agent.system_prompt;

  openModal('view-prompt-modal');
}

function openEditModal(agentId) {
  const agent = agentsState.find(a => a.id === agentId);
  if (!agent) return;

  activeAgentForEdit = agent;
  const form = document.getElementById('edit-agent-form');
  if (!form) return;

  form.elements['edit-name'].value = agent.name;
  form.elements['edit-role'].value = agent.role;
  form.elements['edit-avatar_color'].value = agent.avatar_color;
  form.elements['edit-system_prompt'].value = agent.system_prompt;
  form.elements['edit-is_active'].checked = agent.is_active;

  openModal('edit-agent-modal');
}

// Preset Agent Templates for Quick Testing
function applyAgentPreset(type) {
  const form = document.getElementById('create-agent-form');
  if (!form) return;

  const presets = {
    procurement: {
      name: 'Rohan - Vendor Negotiation Lead',
      role: 'Procurement Specialist',
      color: 'emerald',
      prompt: 'You are Rohan, an expert procurement negotiator. You analyze multi-supplier quotations, enforce strict milestone SLAs, calculate volumetric discounts, and draft ironclad purchase agreements with complete audit compliance.'
    },
    cad: {
      name: 'Aria - BIM & CAD Engine Specialist',
      role: 'Civil CAD Engineer',
      color: 'cyan',
      prompt: 'You are Aria, an autonomous CAD computation specialist. You evaluate DWG/DXF layers, verify beam structural stress limits, optimize parametric BIM geometry, and ensure regional building code tolerances.'
    },
    cyber: {
      name: 'Sentinel - Threat Detection Agent',
      role: 'Cybersecurity Analyst',
      color: 'amber',
      prompt: 'You are Sentinel, an autonomous security operations agent. You correlate syslog events, identify zero-day vulnerability signatures, query CVE indices, and automate incident response runbooks with surgical precision.'
    },
    code: {
      name: 'Kavita - Core Architecture Reviewer',
      role: 'Principal Software Architect',
      color: 'violet',
      prompt: 'You are Kavita, a Principal Code Architect. You review distributed backend codebases, audit database query indices, enforce microservice idempotency, and design resilient event-driven architectures.'
    }
  };

  const selected = presets[type];
  if (selected) {
    form.elements['name'].value = selected.name;
    form.elements['role'].value = selected.role;
    form.elements['avatar_color'].value = selected.color;
    form.elements['system_prompt'].value = selected.prompt;
    showToast(`Loaded '${selected.role}' preset template`, 'info');
  }
}

// ==========================================
// Initialization
// ==========================================

document.addEventListener('DOMContentLoaded', () => {
  // Load Agents
  loadAgents();

  // Search & Filter Listeners
  const searchInput = document.getElementById('search-input');
  const filterActive = document.getElementById('filter-active');

  if (searchInput) {
    searchInput.addEventListener('input', () => renderAgentGrid());
  }
  if (filterActive) {
    filterActive.addEventListener('change', () => renderAgentGrid());
  }

  // Create Agent Form
  const createForm = document.getElementById('create-agent-form');
  if (createForm) {
    createForm.addEventListener('submit', handleCreateAgent);
  }

  // Edit Agent Form
  const editForm = document.getElementById('edit-agent-form');
  if (editForm) {
    editForm.addEventListener('submit', handleUpdateAgent);
  }

  // Add Skill Form
  const addSkillForm = document.getElementById('add-skill-form');
  if (addSkillForm) {
    addSkillForm.addEventListener('submit', handleAddSkill);
  }

  // Chat Input Keyboard Listener (Enter to send, Shift+Enter for newline)
  const chatInput = document.getElementById('chat-input-text');
  if (chatInput) {
    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
      }
    });
  }

  // Initialize Lucide icons
  lucide.createIcons();
});


// ==========================================
// Fleet Skill Pickup & Edit Skill Controllers
// ==========================================

function populateFleetSkillPickup() {
  const select = document.getElementById('fleet-skill-pickup-select');
  if (!select) return;

  const uniqueSkillsMap = new Map();
  agentsState.forEach(ag => {
    (ag.skills || []).forEach(s => {
      if (!uniqueSkillsMap.has(s.skill_name)) {
        uniqueSkillsMap.set(s.skill_name, { name: s.skill_name, url: s.skill_url, fromAgent: ag.name });
      }
    });
  });

  select.innerHTML = '<option value="">-- Choose an existing skill to duplicate --</option>';
  uniqueSkillsMap.forEach(item => {
    const opt = document.createElement('option');
    opt.value = JSON.stringify({ name: item.name, url: item.url });
    opt.textContent = `${item.name} (${item.url})`;
    select.appendChild(opt);
  });
}

function onFleetSkillPickupSelected(jsonVal) {
  if (!jsonVal) return;
  try {
    const parsed = JSON.parse(jsonVal);
    applySkillPreset(parsed.name, parsed.url);
  } catch (e) {
    console.error(e);
  }
}

function openEditSkillModal(agentId, skillId, event) {
  if (event) event.stopPropagation();

  const agent = agentsState.find(a => a.id === agentId);
  if (!agent) return;

  const skill = (agent.skills || []).find(s => s.id === skillId);
  if (!skill) return;

  document.getElementById('edit-skill-agent-title').textContent = agent.name;
  document.getElementById('edit-skill-id').value = skill.id;
  document.getElementById('edit-skill-agent-id').value = agent.id;
  document.getElementById('edit-skill-name').value = skill.skill_name;
  document.getElementById('edit-skill-url').value = skill.skill_url;
  document.getElementById('edit-skill-is-enabled').checked = skill.is_enabled;

  openModal('edit-skill-modal');
}

async function handleUpdateSkill(e) {
  e.preventDefault();
  const form = document.getElementById('edit-skill-form');
  const agentId = form.elements['agent_id'].value;
  const skillId = form.elements['skill_id'].value;
  const skill_name = form.elements['skill_name'].value.trim();
  const skill_url = form.elements['skill_url'].value.trim();
  const is_enabled = form.elements['is_enabled'].checked;

  if (!skill_name || !skill_url) {
    showToast('Please fill all skill fields', 'warning');
    return;
  }

  const submitBtn = document.getElementById('edit-skill-submit-btn');
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i> Saving...';
    lucide.createIcons();
  }

  try {
    const res = await fetch(`/api/agents/${agentId}/skills/${skillId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skill_name, skill_url, is_enabled })
    });

    if (!res.ok) throw new Error('Failed to update skill configuration');

    closeModal('edit-skill-modal');
    showToast(`Skill '${skill_name}' updated successfully!`, 'success');
    await loadAgents();
  } catch (err) {
    console.error(err);
    showToast('Failed to update MCP skill', 'error');
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = 'Save Skill Changes';
    }
  }
}
