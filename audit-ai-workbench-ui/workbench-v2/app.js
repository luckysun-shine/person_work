const $ = (selector, scope = document) => scope.querySelector(selector);
const $$ = (selector, scope = document) => [...scope.querySelectorAll(selector)];

const state = {
  activeView: 'today',
  apiAvailable: false,
  completedTasks: new Set(JSON.parse(localStorage.getItem('audit-workbench.completed-tasks') || '[]')),
  notes: JSON.parse(localStorage.getItem('audit-workbench.notes') || '[]'),
  requests: [],
  sqlAssets: [],
  procedures: [],
  procedureStatus: 'all',
  selectedNotes: new Set(),
  selectedRequests: new Set(),
  selectedSql: new Set(),
  currentSql: null,
  sqlVersions: [],
  models: [],
  currentModel: null,
  projects: [],
  ledgerCategory: 'all',
  ledgerFocus: 'all',
  ledgerQuery: '',
  ledgerDetailTab: 'overview',
  ledgerDetail: null,
  ledgerModelRelationId: null,
  navigation: [],
  currentProject: null,
  currentDetail: null,
  focusTasks: [],
  focusSummary: null,
  weekReview: null,
  weeklyReport: null,
  reportTemplates: [],
  genericReports: [],
  currentGeneratedReportId: null,
  noteAssist: null,
  sqlAssist: null,
  searchResults: [],
  searchType: 'all',
  searchSelection: -1,
  recentSearches: [],
  savedSearches: [],
  reportVersions: [],
  requestStatus: 'all',
  sqlCategory: 'all',
  noteCategory: 'all',
  noteScope: 'active',
  backups: [],
  settings: { backup_retention: 20, auto_backup_hours: 0, home_layout: ['tasks', 'projects', 'requests', 'quick'] },
  weekOffset: 0,
  weekBucket: 'current',
  weekTasks: [],
  weekBoardEvents: [],
  homeWeekTasks: [],
  calendarEvents: [],
  weekCalendarEvents: [],
  projectTemplates: [],
  stats: null,
  statsPeriod: 'week',
  statsDrill: 'completed',
  notePreviewMode: false,
  homeLayout: ['tasks', 'projects', 'requests', 'quick'],
};

const HOME_LAYOUT_DEFAULT = ['tasks', 'projects', 'requests', 'quick'];

const requestStatus = {
  pending: ['待处理', 'waiting'], waiting: ['待确认', 'waiting'], working: ['处理中', 'working'],
  done: ['已交付', 'done'], archived: ['已归档', 'done'],
};
const sqlStatus = { draft: ['草稿', 'working'], validated: ['已验证', 'done'], archived: ['已归档', 'waiting'] };

function formatApiError(payload, status) {
  const detail = payload?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map(item => {
      if (typeof item === 'string') return item;
      const loc = Array.isArray(item?.loc) ? item.loc.filter(part => part !== 'body').join('.') : '';
      return `${loc ? `${loc}：` : ''}${item?.msg || '参数无效'}`;
    }).join('；');
  }
  if (detail && typeof detail === 'object') return detail.message || JSON.stringify(detail);
  return payload?.message || `请求失败：${status}`;
}

async function apiRequest(path, options = {}) {
  const { headers: extraHeaders, ...rest } = options;
  const headers = { 'Content-Type': 'application/json', ...(extraHeaders || {}) };
  const token = sessionStorage.getItem('workbench_access');
  if (token) headers['X-Workbench-Access'] = token;
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...rest,
    headers,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '请求失败' }));
    throw new Error(formatApiError(error, response.status));
  }
  return response.status === 204 ? null : response.json();
}

function splitValues(value) {
  return value.split(/[,，]/).map(item => item.trim()).filter(Boolean);
}

function formatDate(value) {
  if (!value) return '未设置';
  return String(value).replace('T', ' ').slice(0, 16);
}

function make(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function fillProjectSelect(selectEl, selectedId = '') {
  if (!selectEl) return;
  const current = selectedId || '';
  selectEl.replaceChildren();
  const empty = document.createElement('option');
  empty.value = '';
  empty.textContent = '未关联';
  selectEl.append(empty);
  const seen = new Set();
  (state.projects || []).forEach(project => {
    if (!project?.id || seen.has(project.id)) return;
    seen.add(project.id);
    const opt = document.createElement('option');
    opt.value = project.id;
    const status = project.status === 'active' ? '' : ` · ${project.status || ''}`;
    opt.textContent = `${project.name || project.id}${status}`;
    selectEl.append(opt);
  });
  if (current && !seen.has(current)) {
    const orphan = document.createElement('option');
    orphan.value = current;
    orphan.textContent = `${current}（未在项目列表）`;
    selectEl.append(orphan);
  }
  selectEl.value = current;
}

function fillEntityRelationOptions() {
  const list = $('#entityRelationOptions');
  if (!list) return;
  list.replaceChildren();
  const add = (value, label) => {
    if (!value) return;
    const opt = document.createElement('option');
    opt.value = value;
    opt.label = label || value;
    list.append(opt);
  };
  (state.projects || []).forEach(item => add(item.id, `台账 · ${item.name || item.id}`));
  (state.sqlAssets || []).forEach(item => add(item.id, `SQL · ${item.name || item.id}`));
  (state.models || []).forEach(item => add(item.id, `模型 · ${item.name || item.id}`));
  (state.requests || []).forEach(item => add(item.id, `请求 · ${item.title || item.id}`));
}

function sqlAssetLabel(id) {
  const asset = (state.sqlAssets || []).find(item => item.id === id);
  return asset ? `${asset.name || id}` : id;
}

function projectLabel(id) {
  const project = (state.projects || []).find(item => item.id === id);
  return project ? (project.name || id) : id;
}

function closeTransientUi() {
  closeModal($('#requestModal'));
  closeModal($('#modelModal'));
  closeModal($('#sqlModal'));
  closeModal($('#procedureModal'));
  closeModal($('#taskModal'));
  closeModal($('#recordModal'));
  closeModal($('#projectRelationModal'));
  closeEntityDrawer();
  closeDrawer();
}

async function jumpToSqlAsset(sqlId) {
  if (!sqlId) return;
  try {
    closeTransientUi();
    showView('sql');
    await openSqlDrawer(sqlId);
  } catch (error) {
    showToast(error.message || '无法打开对应 SQL');
  }
}

async function jumpToProject(projectId) {
  if (!projectId) return;
  const local = (state.projects || []).find(item => item.id === projectId);
  try {
    closeTransientUi();
    showView('projects');
    await openProjectRelations(local || { id: projectId });
  } catch (error) {
    showToast(error.message || '无法打开对应项目');
  }
}

function getSqlPickerIds(hiddenId) {
  return splitValues($(`#${hiddenId}`)?.value || '');
}

function setSqlPicker(hiddenId, chipsId, addSelectId, ids = []) {
  const hidden = $(`#${hiddenId}`);
  if (!hidden) return;
  const unique = [...new Set((ids || []).map(item => String(item).trim()).filter(Boolean))];
  hidden.value = unique.join(', ');
  renderSqlPickerChips(chipsId, hiddenId, addSelectId, unique);
  fillSqlAddSelect(addSelectId, unique);
}

function renderSqlPickerChips(chipsId, hiddenId, addSelectId, ids) {
  const wrap = $(`#${chipsId}`);
  if (!wrap) return;
  wrap.replaceChildren();
  ids.forEach(id => {
    const chip = make('span', 'assoc-chip');
    const openBtn = make('button', 'assoc-chip-open', sqlAssetLabel(id));
    openBtn.type = 'button';
    openBtn.title = `打开 ${id}`;
    openBtn.addEventListener('click', () => jumpToSqlAsset(id));
    const removeBtn = make('button', 'assoc-chip-remove', '×');
    removeBtn.type = 'button';
    removeBtn.title = `移除 ${id}`;
    removeBtn.addEventListener('click', () => {
      setSqlPicker(hiddenId, chipsId, addSelectId, getSqlPickerIds(hiddenId).filter(item => item !== id));
    });
    chip.append(openBtn, removeBtn);
    wrap.append(chip);
  });
  if (!ids.length) wrap.append(make('span', 'assoc-empty', '尚未关联 SQL，可从下方选择'));
}

function fillSqlAddSelect(addSelectId, selectedIds = []) {
  const selectEl = $(`#${addSelectId}`);
  if (!selectEl) return;
  const selected = new Set(selectedIds);
  selectEl.replaceChildren();
  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = '添加 SQL 资产…';
  selectEl.append(placeholder);
  (state.sqlAssets || []).forEach(asset => {
    if (!asset?.id || selected.has(asset.id)) return;
    const opt = document.createElement('option');
    opt.value = asset.id;
    const status = asset.status ? ` · ${sqlStatus[asset.status]?.[0] || asset.status}` : '';
    opt.textContent = `${asset.name || asset.id}${status}`;
    selectEl.append(opt);
  });
  selectEl.value = '';
}

function bindSqlPicker(hiddenId, chipsId, addSelectId) {
  const addSelect = $(`#${addSelectId}`);
  if (!addSelect || addSelect.dataset.bound === '1') return;
  addSelect.dataset.bound = '1';
  addSelect.addEventListener('change', () => {
    const id = addSelect.value.trim();
    if (!id) return;
    const next = [...getSqlPickerIds(hiddenId), id];
    setSqlPicker(hiddenId, chipsId, addSelectId, next);
  });
}

let toastTimer;
function showToast(message) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 1800);
}

function updateNavCounts() {
  const todayBadge = $('#navTodayCount');
  if (todayBadge) todayBadge.textContent = String(state.focusTasks?.length || 0);
  const requestBadge = $('#navRequestCount');
  if (requestBadge) {
    const openRequests = (state.requests || []).filter(item => !['done', 'archived'].includes(item.status)).length;
    requestBadge.textContent = String(openRequests);
    requestBadge.hidden = openRequests <= 0;
  }
  const projectBadge = $('#navProjectCount');
  if (projectBadge) {
    const attention = (state.projects || []).reduce((sum, item) => sum + (item.model_attention || 0) + (item.pending_steps || 0), 0);
    projectBadge.textContent = String(attention);
    projectBadge.hidden = attention <= 0;
    projectBadge.classList.toggle('risk', attention > 0);
  }
  const hint = $('#sidebarHealthHint');
  if (hint && state.apiAvailable) {
    const now = new Date();
    hint.textContent = `今日 ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')} 已连接`;
  }
}

function showView(name) {
  let redirectedFromModels = false;
  if (name === 'models') {
    name = 'projects';
    redirectedFromModels = true;
    state.ledgerFocus = 'with_model';
    $$('#ledgerFocusFilters [data-ledger-focus]').forEach(item => {
      item.classList.toggle('active', item.dataset.ledgerFocus === 'with_model');
    });
  }
  const target = $(`#view-${name}`);
  if (!target) return;
  if (typeof drawer !== 'undefined' && drawer.classList.contains('open')) closeDrawer();
  if (typeof entityDrawer !== 'undefined' && entityDrawer.classList.contains('open')) closeEntityDrawer();
  $$('.view').forEach(view => view.classList.toggle('active', view === target));
  $$('.nav-item').forEach(item => {
    const active = item.dataset.view === name;
    item.classList.toggle('active', active);
    if (active) item.setAttribute('aria-current', 'page');
    else item.removeAttribute('aria-current');
  });
  state.activeView = name;
  document.title = `${target.dataset.title} · 数智审监工作台`;
  const workspaceTitle = $('#workspaceTitle');
  if (workspaceTitle) workspaceTitle.textContent = target.dataset.title;
  closeMobileNav();
  syncMobileTabbar(name);
  window.scrollTo({ top: 0, behavior: 'smooth' });
  if (name === 'data' && state.apiAvailable) { refreshBackups(); loadSettings(); maybeAutoBackup(); }
  if (name === 'stats' && state.apiAvailable) refreshStats();
  if (name === 'search') { refreshSearchHelpers(); setTimeout(() => $('#globalSearchInput').focus(), 20); }
  if (redirectedFromModels || name === 'projects') renderProjects();
}

$$('[data-view]').forEach(button => button.addEventListener('click', () => showView(button.dataset.view)));
$$('[data-view-jump]').forEach(button => button.addEventListener('click', () => showView(button.dataset.viewJump)));

function updateTaskProgress() {
  const summary = state.focusSummary || { done: 0, total: state.focusTasks.length, blocked: 0, waiting: 0 };
  const total = summary.total || 0;
  const done = summary.done || 0;
  const waiting = summary.waiting ?? summary.blocked ?? 0;
  const weekDone = summary.week_done_count ?? summary.week_done ?? done;
  const pct = total ? Math.round(done / total * 100) : 0;
  if ($('#todayProgress')) $('#todayProgress').textContent = `${done} / ${total}`;
  if ($('#todayProgressBar')) $('#todayProgressBar').style.width = `${pct}%`;
  if ($('#todayProgressBarHero')) $('#todayProgressBarHero').style.width = `${pct}%`;
  if ($('#todayWeekDoneBar')) $('#todayWeekDoneBar').style.width = `${Math.min(100, weekDone ? Math.max(18, weekDone * 8) : pct)}%`;
  if ($('#todayWaitingBar')) $('#todayWaitingBar').style.width = `${waiting ? Math.min(100, 20 + waiting * 18) : 8}%`;
  if ($('#todayStatTodo')) $('#todayStatTodo').textContent = String(Math.max(0, total - done));
  if ($('#todayStatDone')) $('#todayStatDone').textContent = String(weekDone);
  if ($('#todayStatWait')) $('#todayStatWait').textContent = String(waiting);
}

function escapeHtml(value = '') {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function highlightSql(source = '') {
  const tokens = [];
  const stash = (html) => {
    const index = tokens.length;
    tokens.push(html);
    return `§T${index}§`;
  };
  let text = String(source || '').replace(/\r\n/g, '\n');
  text = text.replace(/\/\*[\s\S]*?\*\//g, match => stash(`<span class="cm">${escapeHtml(match)}</span>`));
  text = text.replace(/--[^\n]*/g, match => stash(`<span class="cm">${escapeHtml(match)}</span>`));
  text = text.replace(/'(?:''|[^'])*'/g, match => stash(`<span class="str">${escapeHtml(match)}</span>`));
  text = text.replace(/(:[A-Za-z_][\w]*)/g, match => stash(`<span class="param">${escapeHtml(match)}</span>`));
  text = text.replace(/\b(\d+(?:\.\d+)?)\b/g, match => stash(`<span class="num">${escapeHtml(match)}</span>`));
  text = escapeHtml(text);
  text = text.replace(
    /\b(WITH|RECURSIVE|SELECT|DISTINCT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|FULL|CROSS|ON|AND|OR|NOT|IN|EXISTS|BETWEEN|AS|CASE|WHEN|THEN|ELSE|END|GROUP|BY|ORDER|HAVING|LIMIT|OFFSET|UNION|ALL|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|ALTER|DROP|TABLE|VIEW|INDEX|PRIMARY|KEY|NULL|IS|LIKE|ILIKE|ASC|DESC|OVER|PARTITION|ROWS|RANGE|UNBOUNDED|PRECEDING|FOLLOWING|CURRENT|ROW|TRUE|FALSE|CAST|COALESCE|NULLIF|COUNT|SUM|AVG|MAX|MIN|ROUND|DATE|TIMESTAMP|INTERVAL|FETCH|FIRST|NEXT|ONLY|QUALIFY|WINDOW|USING|NATURAL|LATERAL|EXCEPT|INTERSECT|MERGE|RETURNING|GRANT|REVOKE|EXPLAIN|ANALYZE|VACUUM|TRUNCATE|REPLACE|UPSERT|CONFLICT|DO|NOTHING|CONSTRAINT|REFERENCES|FOREIGN|CHECK|DEFAULT|UNIQUE|SCHEMA|DATABASE|PROCEDURE|FUNCTION|TRIGGER|BEGIN|COMMIT|ROLLBACK|DECLARE|IF|ELSIF|LOOP|WHILE|FOR|RETURN|RETURNS|LANGUAGE|SQL|PLPGSQL)\b/gi,
    '<span class="kw">$1</span>',
  );
  return text.replace(/§T(\d+)§/g, (_, index) => tokens[Number(index)] || '');
}

function renderSqlCode(target, sqlText = '') {
  const node = typeof target === 'string' ? $(target) : target;
  if (!node) return;
  const code = node.matches('code') ? node : ($('code', node) || node);
  const content = sqlText || '-- 暂未保存 SQL 文本';
  code.innerHTML = highlightSql(content);
}

function renderMarkdown(source = '') {
  const text = String(source || '').replace(/\r\n/g, '\n');
  if (!text.trim()) return '<p class="empty-state">暂无内容</p>';
  const codeBlocks = [];
  let working = text.replace(/```([\s\S]*?)```/g, (_, code) => {
    const token = `@@CODE${codeBlocks.length}@@`;
    codeBlocks.push(`<pre><code>${escapeHtml(code.trim())}</code></pre>`);
    return token;
  });
  working = escapeHtml(working);
  working = working
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*(.+?)\*(?!\*)/g, '$1<em>$2</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[(.+?)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/^(?:- |\* )(.+)$/gm, '<li>$1</li>')
    .replace(/(?:<li>.*<\/li>\n?)+/g, match => `<ul>${match}</ul>`)
    .replace(/^(?!<[hul]|<li|<pre|<p)(.+)$/gm, '<p>$1</p>')
    .replace(/\n{2,}/g, '\n');
  codeBlocks.forEach((block, index) => {
    working = working.replace(`@@CODE${index}@@`, block);
  });
  return working;
}

function applyHomeLayout(order = state.homeLayout) {
  const grid = $('#homeDashboard');
  if (!grid) return;
  const normalized = HOME_LAYOUT_DEFAULT.map(key => (order || []).includes(key) ? null : key)
    .filter(Boolean);
  const finalOrder = [...(order || []).filter(key => HOME_LAYOUT_DEFAULT.includes(key)), ...normalized];
  state.homeLayout = finalOrder;
  // Soft Welcome 固定 bento：中部焦点/节奏/等待，下部请求/日程/待办
  grid.dataset.rail = 'projects-first';
  $$('.home-card', grid).forEach(card => {
    card.style.order = '';
    card.style.gridColumn = '';
    card.draggable = grid.dataset.layoutEdit === 'on';
  });
}

async function saveHomeLayout(order = state.homeLayout) {
  state.homeLayout = order;
  localStorage.setItem('audit-workbench.home-layout', JSON.stringify(order));
  applyHomeLayout(order);
  if (!state.apiAvailable) return;
  try {
    state.settings = await apiRequest('/api/settings', { method: 'PUT', body: JSON.stringify({ home_layout: order }) });
  } catch (_) {}
}

function wireHomeLayoutDrag() {
  const grid = $('#homeDashboard');
  if (!grid || grid.dataset.dragReady) return;
  grid.dataset.dragReady = '1';
  let dragging = null;
  $$('.home-card', grid).forEach(card => {
    card.draggable = false;
    card.addEventListener('dragstart', event => {
      if (grid.dataset.layoutEdit !== 'on') { event.preventDefault(); return; }
      // 仅允许右侧栏互换，主栏任务/请求保持固定
      const key = card.dataset.homeCard;
      if (key !== 'projects' && key !== 'quick') { event.preventDefault(); return; }
      dragging = card;
      card.classList.add('dragging-card');
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', key);
    });
    card.addEventListener('dragend', () => {
      card.classList.remove('dragging-card');
      $$('.home-card', grid).forEach(item => item.classList.remove('drag-over-card'));
      dragging = null;
    });
    card.addEventListener('dragover', event => {
      if (grid.dataset.layoutEdit !== 'on' || !dragging) return;
      const key = card.dataset.homeCard;
      if (key !== 'projects' && key !== 'quick') return;
      event.preventDefault();
      if (dragging === card) return;
      card.classList.add('drag-over-card');
    });
    card.addEventListener('dragleave', () => card.classList.remove('drag-over-card'));
    card.addEventListener('drop', async event => {
      event.preventDefault();
      card.classList.remove('drag-over-card');
      if (grid.dataset.layoutEdit !== 'on' || !dragging || dragging === card) return;
      const fromKey = dragging.dataset.homeCard;
      const toKey = card.dataset.homeCard;
      if (![fromKey, toKey].every(key => key === 'projects' || key === 'quick')) return;
      const order = [...state.homeLayout];
      const from = order.indexOf(fromKey);
      const to = order.indexOf(toKey);
      if (from < 0 || to < 0) return;
      order.splice(to, 0, order.splice(from, 1)[0]);
      await saveHomeLayout(order);
      showToast('右侧栏顺序已保存');
    });
  });
}

$('#toggleHomeEdit')?.addEventListener('click', () => {
  const grid = $('#homeDashboard');
  if (!grid) return;
  const editing = grid.dataset.layoutEdit !== 'on';
  grid.dataset.layoutEdit = editing ? 'on' : 'off';
  $('#toggleHomeEdit').textContent = editing ? '完成调整' : '调整布局';
  if ($('#resetHomeLayout')) $('#resetHomeLayout').hidden = !editing;
  if ($('#homeEditHint')) {
    $('#homeEditHint').textContent = editing
      ? '拖拽「正在推进」与「今日日程」可互换上下位置。'
      : '日常使用保持固定版式；需要时再调整卡片顺序。';
  }
  applyHomeLayout(state.homeLayout);
});

$('#resetHomeLayout')?.addEventListener('click', async () => {
  await saveHomeLayout([...HOME_LAYOUT_DEFAULT]);
  showToast('已恢复默认首页布局');
});

$('#todayNewTask')?.addEventListener('click', () => openTaskForm(null, localIsoDate(new Date())));
$('#todayGotoWeek')?.addEventListener('click', () => showView('week'));
$('#todayTasksToWeek')?.addEventListener('click', () => showView('week'));

function ledgerCycleLabel(cycle) {
  return cycle || '按需';
}

function ledgerExecLabel(result) {
  return ({ success: '成功', partial: '部分完成', failed: '失败' })[result] || result || '—';
}

function ledgerStatusLabel(status) {
  return ({
    active: ['进行中', 'working'],
    paused: ['已暂停', 'waiting'],
    done: ['已完成', 'done'],
    archived: ['已归档', 'waiting'],
  })[status] || [status || '进行中', 'working'];
}

function filteredLedgerProjects() {
  const q = (state.ledgerQuery || '').trim().toLowerCase();
  return (state.projects || []).filter(project => {
    if (state.ledgerCategory !== 'all' && project.category !== state.ledgerCategory) return false;
    if (state.ledgerFocus === 'attention' && !(project.model_attention || project.pending_steps)) return false;
    if (state.ledgerFocus === 'with_model' && !(project.model_count > 0)) return false;
    if (!q) return true;
    const modelText = (project.linked_models || []).map(item => `${item.name || ''} ${item.id || ''}`).join(' ');
    const hay = [project.name, project.goal, project.plan_detail, project.monitor_logic, project.next_action, modelText]
      .filter(Boolean).join(' ').toLowerCase();
    return hay.includes(q);
  });
}

function renderTodayProjects() {
  const list = $('#todayProjects');
  const active = state.projects.filter(project => project.status === 'active');
  const focus = active[0];
  if ($('#todayFocusTitle')) {
    $('#todayFocusTitle').textContent = focus?.name || '暂无进行中的监管项';
  }
  if ($('#todayFocusLead')) {
    $('#todayFocusLead').textContent = focus
      ? `${ledgerCycleLabel(focus.monitor_cycle)} · ${focus.next_action || '待安排下一步'}`
      : '完善台账后，这里会显示周期与下一步。';
  }
  if ($('#todayFocusProgress')) {
    const latest = focus?.latest_execution;
    $('#todayFocusProgress').textContent = latest
      ? ledgerExecLabel(latest.result)
      : (focus ? ledgerCycleLabel(focus.monitor_cycle) : '—');
  }
  const card = $('#todayFocusCard');
  if (card) {
    card.onclick = focus
      ? () => { showView('projects'); openProjectRelations(focus); }
      : () => showView('projects');
  }
  if (!list) return;
  list.replaceChildren();
  active.slice(0, 3).forEach(project => {
    const button = make('button', 'project-progress'); button.type = 'button';
    const latest = project.latest_execution;
    const copy = make('span');
    copy.append(
      make('strong', '', project.name),
      make('small', '', `${ledgerCycleLabel(project.monitor_cycle)} · ${project.next_action || '待安排下一步'}`),
    );
    button.append(copy, make('b', '', latest ? ledgerExecLabel(latest.result) : '待执行'));
    button.addEventListener('click', event => {
      event.stopPropagation();
      showView('projects');
      openProjectRelations(project);
    });
    list.append(button);
  });
  if (!list.children.length) list.append(make('p', 'empty-state', '暂无进行中的监管项'));
}

function renderTodayRequests() {
  const rows = $('#todayRequestRows');
  if (!rows) return;
  rows.replaceChildren();
  const items = state.requests
    .filter(item => !['done', 'archived'].includes(item.status))
    .slice(0, 5);
  items.forEach(item => {
    const status = requestStatus[item.status] || [item.status, 'waiting'];
    const button = make('button', 'soft-acc-item');
    button.type = 'button';
    button.append(
      make('strong', '', item.title),
      make('small', '', `${item.requester || item.department || '未填需求人'} · ${item.sql_current_version || 'v1.0'} · ${status[0]}`),
    );
    button.addEventListener('click', () => { showView('requests'); openEntityDrawer('data_request', item); });
    rows.append(button);
  });
  if (!items.length) {
    rows.append(make('p', 'empty-state home-placeholder', '暂无进行中的数据请求。'));
  }
  const jump = $('#todayRequestsJump');
  if (jump) jump.textContent = `全部 →`;
}

function renderTodaySqlHome() {
  const rows = $('#todaySqlRows');
  if (!rows) return;
  rows.replaceChildren();
  const items = (state.sqlAssets || []).slice(0, 4);
  items.forEach(item => {
    const button = make('button', 'soft-acc-item');
    button.type = 'button';
    button.append(
      make('strong', '', item.name || item.id),
      make('small', '', `${item.current_version || 'v1'} · ${(item.table_names || []).slice(0, 2).join('、') || '未登记表'}`),
    );
    button.addEventListener('click', () => { showView('sql'); openSqlDrawer(item.id); });
    rows.append(button);
  });
  if (!items.length) {
    rows.append(make('p', 'empty-state home-placeholder', '暂无 SQL 资产，去 SQL 库新建。'));
  }
}

function renderTodayModelsHome() {
  const rows = $('#todayModelRows');
  if (!rows) return;
  rows.replaceChildren();
  const statusNames = { normal: '运行正常', update_due: '待更新', paused: '已暂停', archived: '已归档' };
  const items = (state.projects || [])
    .filter(project => (project.linked_models || []).length)
    .flatMap(project => (project.linked_models || []).map(model => ({ project, model })))
    .slice(0, 4);
  items.forEach(({ project, model }) => {
    const button = make('button', 'soft-acc-item');
    button.type = 'button';
    button.append(
      make('strong', '', model.name || model.id),
      make('small', '', `${project.name} · ${statusNames[model.status] || model.status || '未知'}`),
    );
    button.addEventListener('click', async () => {
      showView('projects');
      await openProjectRelations(project);
      setLedgerDetailTab('models');
      await selectModel(model);
    });
    rows.append(button);
  });
  if (!items.length) {
    rows.append(make('p', 'empty-state home-placeholder', '暂无绑定模型的监管项，可在台账详情中新建。'));
  }
}

function renderTodayNotesHome() {
  const rows = $('#todayNoteRows');
  if (!rows) return;
  rows.replaceChildren();
  const items = (state.notes || [])
    .filter(item => !item.isArchived)
    .slice()
    .sort((a, b) => String(b.updatedAt || b.createdAt || '').localeCompare(String(a.updatedAt || a.createdAt || '')))
    .slice(0, 4);
  items.forEach(item => {
    const button = make('button', 'soft-acc-item');
    button.type = 'button';
    button.append(
      make('strong', '', item.title || '未命名记录'),
      make('small', '', `${item.type || '随手记录'} · ${formatDate(item.updatedAt || item.createdAt).slice(0, 10)}`),
    );
    button.addEventListener('click', () => {
      showView('notes');
      openEntityDrawer('note', item);
    });
    rows.append(button);
  });
  if (!items.length) {
    rows.append(make('p', 'empty-state home-placeholder', '暂无工作记录，去记录页新建。'));
  }
}

function nudgeReasonLabel(reason) {
  return ({ overdue: '逾期', blocked: '受阻', remind: '提醒到期', due_soon: '即将截止', high: '高优先' })[reason] || '需关注';
}

async function snoozeTaskRemind(taskId) {
  await apiRequest(`/api/tasks/${taskId}/snooze-remind?days=1`, { method: 'POST' });
  showToast('已推迟到明天再催');
  await refreshTodayTasks();
}

async function completeFocusTask(taskId) {
  await apiRequest(`/api/tasks/${taskId}`, { method: 'PATCH', body: JSON.stringify({ status: 'done' }) });
  await Promise.all([refreshTodayTasks(), refreshWeekTasks()]);
  showToast('任务已完成');
}

function focusTaskInList(taskId) {
  const target = $(`.task-row[data-task-id="${taskId}"]`);
  if (!target) return;
  target.scrollIntoView({ behavior: 'smooth', block: 'center' });
  target.classList.add('nudge-flash');
  setTimeout(() => target.classList.remove('nudge-flash'), 1200);
}

function renderTodayNudges() {
  const panel = $('#todayNudgeBar');
  const list = $('#todayNudgeList');
  if (!panel || !list) return;
  const nudges = state.focusNudges || [];
  list.replaceChildren();
  if (!nudges.length) {
    panel.hidden = true;
    panel.classList.remove('is-calm');
    return;
  }
  panel.hidden = false;
  panel.classList.remove('is-calm');
  const signal = $('#todayAttentionSignal');
  if (signal) signal.className = 'signal risk-signal';
  // 紧凑摘要：不重复整段待办，只给最快动作
  const strip = make('div', 'nudge-compact');
  nudges.slice(0, 4).forEach(task => {
    const chip = make('button', 'nudge-chip');
    chip.type = 'button';
    chip.append(
      make('em', '', nudgeReasonLabel(task.nudge_reason)),
      make('span', '', task.title),
    );
    chip.addEventListener('click', () => {
      focusTaskInList(task.id);
      openEntityDrawer('task', task);
    });
    strip.append(chip);
  });
  if (nudges.length > 4) strip.append(make('span', 'nudge-more', `+${nudges.length - 4}`));
  list.append(strip);
}

function maybeNotifyNudges(nudges) {
  if (!('Notification' in window) || Notification.permission !== 'granted') return;
  const key = `nudge:${(nudges || []).map(item => item.id).join(',')}`;
  if (!nudges?.length || key === state.lastNudgeNotifyKey) return;
  state.lastNudgeNotifyKey = key;
  const top = nudges[0];
  try {
    new Notification('工作台催办', {
      body: `${nudges.length} 项待处理：${top.title}${nudges.length > 1 ? ' 等' : ''}`,
      tag: 'workbench-nudge',
    });
  } catch (_) {}
}

function renderTodayTasks() {
  const list = $('#todayTasks'); list.replaceChildren();
  const summary = state.focusSummary || { total: 0, done: 0, overdue: 0, blocked: 0, high_priority: 0, remind_due: 0, due_soon: 0, nudge_count: 0 };
  state.focusTasks.forEach(task => {
    const row = make('label', `task-row${task.priority === 'high' ? ' priority-high' : ''}${task.is_overdue ? ' overdue-task' : ''}${task.needs_nudge ? ' nudge-task' : ''}`);
    row.dataset.taskId = task.id;
    const checkbox = make('input'); checkbox.type = 'checkbox'; checkbox.checked = task.status === 'done';
    const copy = make('span', 'task-copy');
    const detail = [task.related_entity_id ? `${taskTypeLabel(task.type)} ${task.related_entity_id}` : taskTypeLabel(task.type), task.notes].filter(Boolean).join(' · ');
    copy.append(make('strong', '', task.title), make('small', '', detail || '个人计划'));
    const badge = task.status === 'done' ? '已完成'
      : task.is_overdue ? `逾期 ${task.overdue_days} 天`
      : task.is_remind_due ? '提醒到期'
      : task.is_due_soon ? '即将截止'
      : task.status === 'blocked' ? '受阻'
      : task.priority === 'high' ? '高优先'
      : taskTypeLabel(task.type);
    row.append(checkbox, make('span', 'checkmark'), make('time', '', task.due_at || '全天'), copy, make('em', '', badge));
    if (task.needs_nudge && task.status !== 'done') {
      const quick = make('span', 'task-quick-actions');
      const snooze = make('button', 'text-button', '推迟'); snooze.type = 'button';
      snooze.addEventListener('click', async event => {
        event.preventDefault(); event.stopPropagation();
        try { await snoozeTaskRemind(task.id); } catch (error) { showToast(error.message); }
      });
      const done = make('button', 'text-button', '完成'); done.type = 'button';
      done.addEventListener('click', async event => {
        event.preventDefault(); event.stopPropagation();
        try { await completeFocusTask(task.id); } catch (error) { showToast(error.message); }
      });
      quick.append(snooze, done);
      row.append(quick);
    }
    checkbox.addEventListener('change', async event => {
      event.stopPropagation();
      try {
        await apiRequest(`/api/tasks/${task.id}`, { method: 'PATCH', body: JSON.stringify({ status: checkbox.checked ? 'done' : 'todo' }) });
        await Promise.all([refreshTodayTasks(), refreshWeekTasks()]);
        showToast(checkbox.checked ? '任务已完成并同步到周计划' : '任务已恢复');
      } catch (error) { checkbox.checked = !checkbox.checked; showToast(error.message); }
    });
    copy.addEventListener('click', event => { event.preventDefault(); openEntityDrawer('task', task); });
    list.append(row);
  });
  if (!state.focusTasks.length) list.append(make('p', 'empty-state', '今天没有待办。可以新建任务，或去周计划里排期。'));
  const attentionCount = summary.nudge_count || (state.focusNudges || []).length
    || state.focusTasks.filter(task => task.needs_nudge).length;
  const headline = $('#todayHeadline');
  if (headline) {
    headline.textContent = summary.overdue
      ? '先清掉逾期事项'
      : attentionCount
        ? '先处理催办事项'
        : summary.total
          ? '早上好，准备开工'
          : '今天可以整理与复盘';
  }
  if ($('#todayAttentionCount')) {
    $('#todayAttentionCount').textContent = `${attentionCount} 项需要催办`;
  }
  if ($('#todayAttentionText')) {
    $('#todayAttentionText').textContent = [
      summary.overdue ? `${summary.overdue} 逾期` : null,
      summary.remind_due ? `${summary.remind_due} 提醒` : null,
      summary.due_soon ? `${summary.due_soon} 临近` : null,
      summary.blocked ? `${summary.blocked} 受阻` : null,
      summary.high_priority ? `${summary.high_priority} 高优先` : null,
    ].filter(Boolean).join(' · ') || '点「去处理」定位到对应任务';
  }
  if ($('#todayTasksHint')) {
    $('#todayTasksHint').textContent = summary.total
      ? `${summary.done || 0}/${summary.total} 已完成 · 勾选即可同步到周计划`
      : '按优先级处理，勾选即可完成';
  }
  $('#todayLead').textContent = summary.overdue
    ? `有 ${summary.overdue} 项已逾期，建议先处理后再推进今日计划。`
    : attentionCount
      ? `上方催办区有 ${attentionCount} 项可直接处理或推迟。`
      : summary.total
        ? `今天共有 ${summary.total} 项焦点任务。`
        : '暂无焦点任务，适合做记录整理或复盘。';
  const navBadge = $('[data-view="today"] b'); if (navBadge) navBadge.textContent = summary.total;
  renderTodayNudges();
  updateTaskProgress();
}

async function refreshTodayTasks() {
  if (!state.apiAvailable) { renderTodayTasks(); return; }
  const data = await apiRequest('/api/task-focus');
  state.focusTasks = data.tasks;
  state.focusSummary = data.summary;
  state.focusNudges = data.nudges || data.tasks.filter(task => task.needs_nudge).slice(0, 12);
  renderTodayTasks();
  maybeNotifyNudges(state.focusNudges);
  if (!state._bootstrapping) refreshHomeWeekCalendar().catch(() => {});
}

function localIsoDate(value) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function getWeekDates(offset = 0) {
  const today = new Date();
  today.setHours(12, 0, 0, 0);
  const weekday = today.getDay() || 7;
  const monday = new Date(today);
  monday.setDate(today.getDate() - weekday + 1 + offset * 7);
  return Array.from({ length: 5 }, (_, index) => {
    const value = new Date(monday);
    value.setDate(monday.getDate() + index);
    return value;
  });
}

function getFullWeekDates(offset = 0) {
  const today = new Date();
  today.setHours(12, 0, 0, 0);
  const weekday = today.getDay() || 7;
  const monday = new Date(today);
  monday.setDate(today.getDate() - weekday + 1 + offset * 7);
  return Array.from({ length: 7 }, (_, index) => {
    const value = new Date(monday);
    value.setDate(monday.getDate() + index);
    return value;
  });
}

function eventDateKey(value) {
  return String(value || '').slice(0, 10);
}

function renderHomeWeekCalendar() {
  const root = $('#homeWeekCalendar');
  if (!root) return;
  const dates = getFullWeekDates(0);
  const weekdays = ['一', '二', '三', '四', '五', '六', '日'];
  const todayIso = localIsoDate(new Date());
  const tasks = state.homeWeekTasks || [];
  const events = state.weekCalendarEvents || [];
  const start = dates[0];
  const end = dates[6];
  let taskCount = 0;
  let eventCount = 0;

  root.replaceChildren();
  const grid = make('div', 'home-week-cal-grid');
  dates.forEach((date, index) => {
    const iso = localIsoDate(date);
    const dayTasks = tasks.filter(task => task.planned_date === iso);
    const dayEvents = events.filter(event => eventDateKey(event.start_at) === iso);
    taskCount += dayTasks.length;
    eventCount += dayEvents.length;

    const day = make('div', 'home-week-day');
    if (iso === todayIso) day.classList.add('is-today');
    day.dataset.date = iso;
    day.title = `${date.getMonth() + 1}月${date.getDate()}日`;

    const head = make('header', 'home-week-day-head');
    head.append(make('span', '', weekdays[index]), make('b', '', String(date.getDate())));
    day.append(head);

    const list = make('div', 'home-week-day-list');
    const items = [
      ...dayEvents.map(event => ({ kind: 'event', event })),
      ...dayTasks.map(task => ({ kind: 'task', task })),
    ];
    const visible = items.slice(0, 3);
    visible.forEach(item => {
      if (item.kind === 'event') {
        const chip = make('button', 'home-week-item is-event');
        chip.type = 'button';
        const time = item.event.all_day ? '全天' : String(item.event.start_at || '').slice(11, 16);
        chip.textContent = item.event.title || '日程';
        chip.title = `${time} · ${item.event.title || '日程'}${item.event.location ? ` · ${item.event.location}` : ''}`;
        chip.addEventListener('click', event => {
          event.stopPropagation();
          openEntityDrawer('calendar_event', item.event);
        });
        list.append(chip);
      } else {
        const chip = make('button', `home-week-item is-task${item.task.status === 'done' ? ' is-done' : ''}${item.task.priority === 'high' ? ' is-high' : ''}`);
        chip.type = 'button';
        chip.textContent = item.task.title || '待办';
        chip.title = item.task.title || '待办';
        chip.addEventListener('click', event => {
          event.stopPropagation();
          openEntityDrawer('task', item.task);
        });
        list.append(chip);
      }
    });
    if (items.length > 3) {
      list.append(make('span', 'home-week-more', `+${items.length - 3}`));
    }
    if (!items.length) list.append(make('span', 'home-week-empty', '—'));
    day.append(list);
    day.addEventListener('click', () => showView('week'));
    grid.append(day);
  });
  root.append(grid);

  const hint = $('#todayWeekCalHint');
  if (hint) {
    hint.textContent = `${start.getMonth() + 1}/${start.getDate()}–${end.getMonth() + 1}/${end.getDate()} · ${taskCount} 待办 · ${eventCount} 日程`;
  }
}

async function refreshHomeWeekCalendar() {
  const dates = getFullWeekDates(0);
  const from = localIsoDate(dates[0]);
  const to = localIsoDate(dates[6]);
  if (!state.apiAvailable) {
    state.homeWeekTasks = (state.weekTasks || []).filter(task => {
      const day = task.planned_date || '';
      return day >= from && day <= to;
    });
    if (!state.homeWeekTasks.length && state.focusTasks?.length) {
      state.homeWeekTasks = state.focusTasks.filter(task => {
        const day = task.planned_date || '';
        return day >= from && day <= to;
      });
    }
    state.weekCalendarEvents = (state.calendarEvents || []).filter(event => {
      const day = eventDateKey(event.start_at);
      return day >= from && day <= to;
    });
    renderHomeWeekCalendar();
    return;
  }
  try {
    const [tasks, events] = await Promise.all([
      apiRequest(`/api/tasks?date_from=${from}&date_to=${to}`),
      apiRequest(`/api/calendar/events?date_from=${from}&date_to=${to}`),
    ]);
    state.homeWeekTasks = Array.isArray(tasks) ? tasks : [];
    state.weekCalendarEvents = Array.isArray(events) ? events : [];
  } catch (_) {
    state.homeWeekTasks = state.weekTasks || [];
    state.weekCalendarEvents = state.calendarEvents || [];
  }
  renderHomeWeekCalendar();
}

function updateCurrentDateLabels() {
  const now = new Date();
  const weekdayNames = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  $('.today-label').textContent = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日 · ${weekdayNames[now.getDay()]}`;
  const firstThursday = new Date(now.getFullYear(), 0, 4, 12);
  const weekStart = new Date(now);
  weekStart.setHours(12, 0, 0, 0);
  weekStart.setDate(now.getDate() + 4 - (now.getDay() || 7));
  firstThursday.setDate(firstThursday.getDate() + 4 - (firstThursday.getDay() || 7));
  const weekNumber = 1 + Math.round((weekStart - firstThursday) / 604800000);
  $('#view-today .eyebrow').textContent = `今天 · 第 ${weekNumber} 周`;
}

function taskTypeLabel(type) {
  return ({ task: '任务', model: '模型', request: '数据请求', sql: 'SQL', report: '报告', note: '记录', meeting: '会议' })[type] || '任务';
}

async function toggleWeekTaskDone(task, done) {
  const nextStatus = done ? 'done' : 'todo';
  await apiRequest(`/api/tasks/${task.id}`, { method: 'PATCH', body: JSON.stringify({ status: nextStatus }) });
  await Promise.all([refreshWeekTasks(), refreshTodayTasks()]);
  showToast(done ? '已标记完成' : '已恢复为待办');
}

function makeWeekTaskCard(task) {
  const card = make('article', 'plan-card');
  card.draggable = true;
  card.dataset.taskId = task.id;
  if (task.priority === 'high') card.classList.add('high-card');
  if (task.status === 'done') card.classList.add('done-card');
  if (task.status === 'blocked') card.classList.add('blocked-card');
  card.classList.add(`status-${task.status || 'todo'}`);

  const top = make('div', 'plan-card-top');
  const label = task.status === 'done' ? '已完成'
    : task.status === 'blocked' ? '受阻'
      : task.priority === 'high' ? '高优先'
        : taskTypeLabel(task.type);
  top.append(make('small', '', label));

  const doneBtn = make('button', `plan-done-btn${task.status === 'done' ? ' is-done' : ''}`, task.status === 'done' ? '恢复' : '完成');
  doneBtn.type = 'button';
  doneBtn.title = task.status === 'done' ? '恢复为待办' : '标记完成';
  doneBtn.addEventListener('click', async event => {
    event.preventDefault();
    event.stopPropagation();
    try {
      await toggleWeekTaskDone(task, task.status !== 'done');
    } catch (error) { showToast(error.message); }
  });
  top.append(doneBtn);

  const body = make('button', 'plan-card-body');
  body.type = 'button';
  body.append(make('strong', '', task.title));
  const meta = make('p', 'card-meta');
  meta.append(
    make('span', '', task.due_at || '未设置时间'),
    make('span', 'card-relation', task.related_entity_id || task.notes || '个人计划'),
  );
  body.append(meta);
  body.addEventListener('click', () => openEntityDrawer('task', task));

  card.append(top, body);
  card.addEventListener('dragstart', event => {
    if (event.target.closest('button')) {
      event.preventDefault();
      return;
    }
    event.dataTransfer.setData('text/plain', task.id);
    event.dataTransfer.effectAllowed = 'move';
    card.classList.add('dragging');
  });
  card.addEventListener('dragend', () => card.classList.remove('dragging'));
  return card;
}

function makeWeekEventCard(event) {
  const card = make('button', 'plan-card event-card');
  card.type = 'button';
  const time = event.all_day ? '全天' : String(event.start_at || '').slice(11, 16) || '日程';
  const top = make('div', 'plan-card-top');
  top.append(make('small', '', '日程'));
  card.append(top, make('strong', '', event.title || '未命名日程'));
  const meta = make('p', 'card-meta');
  meta.append(
    make('span', '', time),
    make('span', 'card-relation', event.location || event.calendar_name || '外部日程'),
  );
  card.append(meta);
  card.addEventListener('click', () => openEntityDrawer('calendar_event', event));
  return card;
}

function renderWeekBoard() {
  const dates = getFullWeekDates(state.weekOffset);
  const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
  const todayIso = localIsoDate(new Date());
  const board = $('#weekBoard');
  board.replaceChildren();
  const events = state.weekBoardEvents || [];
  dates.forEach((date, index) => {
    const iso = localIsoDate(date);
    const column = make('div', 'day-column');
    column.dataset.date = iso;
    if (iso === todayIso) column.classList.add('today-column');
    if (index >= 5) column.classList.add('weekend-column');
    const header = make('header', 'day-column-head');
    const labelWrap = make('div', 'day-column-label');
    labelWrap.append(make('span', '', weekdays[index]));
    if (iso === todayIso) labelWrap.append(make('em', 'day-today-tag', '今天'));
    const dayTasks = state.weekTasks.filter(task => task.planned_date === iso);
    const dayEvents = events.filter(event => eventDateKey(event.start_at) === iso);
    header.append(labelWrap, make('b', '', String(date.getDate())));
    column.append(header);
    const count = make('div', 'day-column-count', `${dayTasks.length} 计划 · ${dayEvents.length} 日程`);
    column.append(count);

    dayEvents.forEach(event => column.append(makeWeekEventCard(event)));
    dayTasks.forEach(task => column.append(makeWeekTaskCard(task)));

    if (!dayTasks.length && !dayEvents.length) {
      column.append(make('span', 'day-empty', '拖动任务到这里'));
    }
    column.addEventListener('dragover', event => {
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
      column.classList.add('drag-over');
    });
    column.addEventListener('dragleave', () => column.classList.remove('drag-over'));
    column.addEventListener('drop', async event => {
      event.preventDefault();
      column.classList.remove('drag-over');
      const taskId = event.dataTransfer.getData('text/plain');
      const task = state.weekTasks.find(item => item.id === taskId);
      if (!task || task.planned_date === iso) return;
      try {
        await apiRequest(`/api/tasks/${taskId}`, { method: 'PATCH', body: JSON.stringify({ planned_date: iso }) });
        await Promise.all([refreshWeekTasks(), refreshTodayTasks()]);
        showToast(`任务已调整到${date.getMonth() + 1}月${date.getDate()}日`);
      } catch (error) { showToast(error.message); }
    });
    board.append(column);
  });
  const start = dates[0];
  const end = dates[6];
  const doneCount = state.weekTasks.filter(task => task.status === 'done').length;
  const openCount = state.weekTasks.length - doneCount;
  $('#weekRange').textContent = `${start.getMonth() + 1}月${start.getDate()}日 — ${end.getMonth() + 1}月${end.getDate()}日`;
  $('#weekSummary').textContent = `${state.weekTasks.length} 项计划（待办 ${openCount}）· ${events.length} 项日程 · 已完成 ${doneCount}`;
  $('#copyWeekButton').hidden = state.weekOffset !== 0;
}

function renderWeekBucketList(bucket) {
  const board = $('#weekBoard');
  board.replaceChildren();
  const column = make('div', 'day-column week-bucket-column');
  const head = make('header', 'day-column-head');
  head.append(
    make('strong', '', bucket === 'later' ? '以后' : '本周已完成'),
    make('span', '', `${state.weekTasks.length} 项`),
  );
  column.append(head);
  const list = make('div', 'day-tasks week-bucket-list');
  state.weekTasks.forEach(task => {
    const row = make('div', `week-bucket-row${task.status === 'done' ? ' is-done' : ''}`);
    const body = make('button', 'week-bucket-body');
    body.type = 'button';
    body.append(
      make('strong', '', task.title),
      make('small', '', `${task.planned_date || '未排期'}${task.waiting_on ? ` · 等待 ${task.waiting_on}` : ''}`),
    );
    body.addEventListener('click', () => openEntityDrawer('task', task));
    const doneBtn = make('button', `plan-done-btn${task.status === 'done' ? ' is-done' : ''}`, task.status === 'done' ? '恢复' : '完成');
    doneBtn.type = 'button';
    doneBtn.addEventListener('click', async event => {
      event.preventDefault();
      event.stopPropagation();
      try {
        await toggleWeekTaskDone(task, task.status !== 'done');
      } catch (error) { showToast(error.message); }
    });
    row.append(body, doneBtn);
    list.append(row);
  });
  if (!state.weekTasks.length) {
    list.append(make('p', 'empty-state', bucket === 'later' ? '暂无以后的任务' : '本周还没有已完成任务'));
  }
  column.append(list);
  board.append(column);
  $('#weekRange').textContent = bucket === 'later' ? '以后待办' : '本周已完成';
  $('#weekSummary').textContent = `${state.weekTasks.length} 项`;
  $('#copyWeekButton').hidden = true;
}

async function refreshWeekTasks() {
  const dates = getFullWeekDates(state.weekOffset);
  if (!state.apiAvailable) {
    state.weekTasks = [];
    state.weekBoardEvents = [];
    renderWeekBoard();
    return;
  }
  const bucket = state.weekBucket || 'current';
  if (bucket === 'later' || bucket === 'done') {
    const focus = await apiRequest(`/api/task-focus?bucket=${bucket}`);
    state.weekTasks = focus.tasks || [];
    state.weekBoardEvents = [];
    renderWeekBucketList(bucket);
    return;
  }
  const from = localIsoDate(dates[0]);
  const to = localIsoDate(dates[6]);
  const [tasks, events] = await Promise.all([
    apiRequest(`/api/tasks?date_from=${from}&date_to=${to}`),
    apiRequest(`/api/calendar/events?date_from=${from}&date_to=${to}`).catch(() => []),
  ]);
  state.weekTasks = Array.isArray(tasks) ? tasks : [];
  state.weekBoardEvents = Array.isArray(events) ? events : [];
  renderWeekBoard();
  await refreshWeekReview();
  if (state.weekOffset === 0 && !state._bootstrapping) refreshHomeWeekCalendar().catch(() => {});
}

function renderWeekReview() {
  const review = state.weekReview || {};
  $('#reviewAccomplishments').value = review.accomplishments || '';
  $('#reviewBlockers').value = review.blockers || '';
  $('#reviewNextFocus').value = review.next_week_focus || '';
  $('#reviewEnergy').value = String(review.energy_score || 3);
  $('#weekReviewSaved').textContent = review.updated_at ? `上次保存：${formatDate(review.updated_at)}` : '尚未保存';
  const dates = getWeekDates(state.weekOffset);
  $('#weekReviewHint').textContent = `${localIsoDate(dates[0])} 开始的一周 · 记录成果、阻塞和下周重点`;
}

async function refreshWeekReview() {
  if (!state.apiAvailable) { state.weekReview = null; renderWeekReview(); return; }
  const weekStart = localIsoDate(getWeekDates(state.weekOffset)[0]);
  state.weekReview = await apiRequest(`/api/week-reviews/${weekStart}`); renderWeekReview();
}

$('#weekReviewForm').addEventListener('submit', async event => {
  event.preventDefault();
  const weekStart = localIsoDate(getWeekDates(state.weekOffset)[0]);
  const payload = {
    accomplishments: $('#reviewAccomplishments').value.trim(),
    blockers: $('#reviewBlockers').value.trim(),
    next_week_focus: $('#reviewNextFocus').value.trim(),
    energy_score: Number($('#reviewEnergy').value),
  };
  try {
    state.weekReview = await apiRequest(`/api/week-reviews/${weekStart}`, { method: 'PUT', body: JSON.stringify(payload) });
    renderWeekReview(); showToast('周复盘已保存');
  } catch (error) { showToast(error.message); }
});

$$('[data-week]').forEach(button => button.addEventListener('click', async () => {
  $$('[data-week]').forEach(item => item.classList.toggle('active', item === button));
  const mode = button.dataset.week;
  state.weekBucket = mode;
  state.weekOffset = mode === 'next' ? 1 : 0;
  await refreshWeekTasks();
}));

function reportMonday(value) {
  const current = value ? new Date(`${value}T12:00:00`) : new Date();
  const weekday = current.getDay() || 7;
  current.setDate(current.getDate() - weekday + 1);
  return localIsoDate(current);
}

function reportMarkdown(report = state.weeklyReport) {
  if (!report) return '';
  const labels = currentReportTemplate()?.section_labels || {};
  const start = $('#reportWeekStart').value; const end = $('#reportEndDate').value || start;
  return `# ${$('#reportTitle').value.trim()}\n\n报告周期：${start} 至 ${end}\n\n## ${labels.summary || '总体概览'}\n\n${$('#reportExecutiveSummary').value.trim()}\n\n## ${labels.highlights || '完成与进展'}\n\n${$('#reportHighlights').value.trim()}\n\n## ${labels.risks || '阻塞与风险'}\n\n${$('#reportRisks').value.trim()}\n\n## ${labels.next_plan || '后续计划'}\n\n${$('#reportNextWeek').value.trim()}\n`;
}

function renderWeeklyReport(report) {
  state.weeklyReport = report;
  if (!$('#reportTitle')) return;
  $('#reportTitle').value = report.title || '';
  $('#reportExecutiveSummary').value = report.executive_summary || '';
  $('#reportHighlights').value = report.highlights || '';
  $('#reportRisks').value = report.risks || '';
  $('#reportNextWeek').value = report.next_week_plan || '';
  const metrics = report.metrics || {};
  const values = [
    `${metrics.task_done || 0} / ${metrics.task_total || 0}`,
    `${metrics.request_delivered || 0} / ${metrics.request_total || 0}`,
    `${metrics.model_run_total || 0} 次`,
    `${metrics.active_projects || 0} 个`,
    `${metrics.risk_total || 0} 项`,
  ];
  $$('#reportMetrics strong').forEach((node, index) => { node.textContent = values[index]; });
  const sources = report.source_snapshot || {};
  const sourceCount = ['task_ids', 'request_ids', 'model_run_ids', 'project_ids', 'note_ids']
    .reduce((total, key) => total + (sources[key]?.length || 0), 0);
  if ($('#reportSourceStatus')) {
    $('#reportSourceStatus').textContent = `已汇总 ${sourceCount} 条工作数据 · 数据快照 ${formatDate(sources.generated_at)}`;
  }
  const statusLabel = report.status === 'final' ? '已定稿' : (report.saved ? '已保存草稿' : '自动草稿 · 尚未保存');
  if ($('#reportSaveStatus')) {
    $('#reportSaveStatus').textContent = report.saved || report.status === 'final'
      ? `${statusLabel} · ${formatDate(report.updated_at)}`
      : statusLabel;
  }
  renderAiStatus();
  refreshReportVersions();
}

async function refreshReportVersions() {
  const list = $('#reportVersionHistory');
  if (!list || !state.apiAvailable) return;
  list.replaceChildren();
  try {
    const template = currentReportTemplate();
    if (template && template.type !== 'weekly' && state.currentGeneratedReportId) {
      state.reportVersions = await apiRequest(`/api/reports/${state.currentGeneratedReportId}/versions`);
    } else if (!template || template.type === 'weekly') {
      const weekStart = $('#reportWeekStart').value;
      state.reportVersions = weekStart ? await apiRequest(`/api/weekly-reports/${weekStart}/versions`) : [];
    } else {
      state.reportVersions = [];
    }
  } catch (_) { state.reportVersions = []; }
  state.reportVersions.forEach(item => {
    const row = make('div');
    const copy = make('span');
    copy.append(make('strong', '', `v${item.version} · ${item.title}`), make('small', '', `${item.status === 'final' ? '定稿' : '草稿'} · ${item.change_summary || '保存快照'}`));
    row.append(make('time', '', formatDate(item.created_at).slice(0, 16)), copy);
    list.append(row);
  });
  if (!state.reportVersions.length) list.append(make('p', 'empty-state', '保存报告后将显示版本历史'));
}

async function loadWeeklyReport() {
  const input = $('#reportWeekStart');
  if (!input) return;
  if (!input.value) input.value = reportMonday();
  try {
    const template = currentReportTemplate();
    if (!template || template.type === 'weekly') {
      state.currentGeneratedReportId = null;
      renderWeeklyReport(await apiRequest(`/api/weekly-reports/${input.value}`));
    }
  } catch (error) { showToast(error.message); }
}

async function generateWeeklyReport() {
  try {
    const weekStart = $('#reportWeekStart').value;
    const template = currentReportTemplate();
    state.currentGeneratedReportId = null;
    const aiReady = !!state.settings?.ai?.ready;
    if ((!template || template.type === 'weekly') && aiReady) {
      if (!window.confirm('将使用已配置的 AI 润色周报草稿。仅发送标题与各段落正文，不会上传完整数据库。是否继续？')) return;
    }
    if (!template || template.type === 'weekly') renderWeeklyReport(await apiRequest(`/api/weekly-reports/${weekStart}/generate`, { method: 'POST' }));
    else {
      const report = await apiRequest('/api/reports/generate', { method: 'POST', body: JSON.stringify({ template_id: template.id, period_start: weekStart, period_end: $('#reportEndDate').value || weekStart, related_entity_id: $('#reportRelatedEntity').value || null }) });
      renderGenericReport(report);
    }
    showToast('已根据最新工作数据重新生成');
  } catch (error) { showToast(error.message); }
}

async function polishWeeklyReport() {
  const template = currentReportTemplate();
  if (template && template.type !== 'weekly') {
    showToast('一键润色目前仅支持周工作总结');
    return;
  }
  if (!$('#reportTitle').value.trim()) { showToast('请先填写报告标题'); return; }
  if (!state.settings?.ai?.ready) {
    showToast('请先配置并启用 AI');
    openAiSettings();
    return;
  }
  if (!window.confirm('将把当前编辑区的标题与四段正文发送给 AI 润色（不重新拉数、不上传 SQL）。是否继续？')) return;
  try {
    const weekStart = $('#reportWeekStart').value;
    const polished = await apiRequest(`/api/weekly-reports/${weekStart}/polish`, {
      method: 'POST',
      body: JSON.stringify(weeklyReportPayload(state.weeklyReport?.status || 'draft', 'AI 润色')),
    });
    renderWeeklyReport({ ...state.weeklyReport, ...polished, saved: false });
    showToast('周报已润色，请复核后保存');
  } catch (error) { showToast(error.message); }
}

function weeklyReportPayload(status = state.weeklyReport?.status || 'draft', changeSummary = '') {
  return {
    title: $('#reportTitle').value.trim(),
    executive_summary: $('#reportExecutiveSummary').value.trim(),
    highlights: $('#reportHighlights').value.trim(),
    risks: $('#reportRisks').value.trim(),
    next_week_plan: $('#reportNextWeek').value.trim(),
    metrics: state.weeklyReport?.metrics || {},
    source_snapshot: state.weeklyReport?.source_snapshot || {},
    status,
    change_summary: changeSummary,
  };
}

function genericReportPayload(status = 'draft', changeSummary = '') {
  const template = currentReportTemplate();
  return {
    template_id: template.id,
    title: $('#reportTitle').value.trim(),
    period_start: $('#reportWeekStart').value,
    period_end: $('#reportEndDate').value || $('#reportWeekStart').value,
    related_entity_id: $('#reportRelatedEntity').value || null,
    sections: {
      summary: $('#reportExecutiveSummary').value.trim(),
      highlights: $('#reportHighlights').value.trim(),
      risks: $('#reportRisks').value.trim(),
      next_plan: $('#reportNextWeek').value.trim(),
    },
    metrics: state.weeklyReport?.metrics || {},
    source_snapshot: state.weeklyReport?.source_snapshot || {},
    status,
    change_summary: changeSummary,
  };
}

async function saveWeeklyReport(status = 'draft', changeSummary = '保存草稿') {
  if (!$('#reportTitle').value.trim()) { showToast('请填写报告标题'); return; }
  try {
    const weekStart = $('#reportWeekStart').value; const template = currentReportTemplate();
    if (!template || template.type === 'weekly') {
      renderWeeklyReport(await apiRequest(`/api/weekly-reports/${weekStart}`, { method: 'PUT', body: JSON.stringify(weeklyReportPayload(status, changeSummary)) }));
      showToast(status === 'final' ? '周工作报告已定稿' : '周工作报告已保存');
    } else {
      const path = state.currentGeneratedReportId ? `/api/reports/${state.currentGeneratedReportId}` : '/api/reports';
      const report = await apiRequest(path, { method: state.currentGeneratedReportId ? 'PUT' : 'POST', body: JSON.stringify(genericReportPayload(status, changeSummary)) });
      renderGenericReport(report); state.genericReports = await apiRequest('/api/reports'); renderGenericReportHistory();
      showToast(status === 'final' ? '模板报告已定稿' : '模板报告已保存');
    }
  } catch (error) { showToast(error.message); }
}

async function finalizeCurrentReport() {
  if (!$('#reportTitle').value.trim()) { showToast('请先填写并保存报告内容'); return; }
  if (!window.confirm('确认将当前报告定稿吗？定稿后仍可继续编辑并产生新版本。')) return;
  const template = currentReportTemplate();
  try {
    if (!template || template.type === 'weekly') {
      const weekStart = $('#reportWeekStart').value;
      if (state.weeklyReport?.saved) {
        renderWeeklyReport(await apiRequest(`/api/weekly-reports/${weekStart}/finalize`, { method: 'POST' }));
      } else {
        await saveWeeklyReport('final', '定稿');
        return;
      }
      showToast('周工作报告已定稿');
    } else if (state.currentGeneratedReportId) {
      renderGenericReport(await apiRequest(`/api/reports/${state.currentGeneratedReportId}/finalize`, { method: 'POST' }));
      state.genericReports = await apiRequest('/api/reports'); renderGenericReportHistory();
      showToast('模板报告已定稿');
    } else {
      await saveWeeklyReport('final', '定稿');
    }
  } catch (error) { showToast(error.message); }
}

function currentReportTemplate() {
  const select = $('#reportTemplate');
  if (!select) return null;
  return state.reportTemplates.find(item => item.id === select.value);
}
function renderReportTemplateOptions() {
  const select = $('#reportTemplate');
  if (!select) return;
  select.replaceChildren();
  state.reportTemplates.forEach(template => {
    const option = make('option', '', template.name);
    option.value = template.id;
    select.append(option);
  });
  if (state.reportTemplates.some(template => template.id === 'RT-WEEKLY')) select.value = 'RT-WEEKLY';
  updateReportTemplateControls();
}
function updateReportTemplateControls() {
  if (!$('#reportTemplate')) return;
  const template = currentReportTemplate();
  const generic = template && template.type !== 'weekly';
  if ($('#reportEndLabel')) $('#reportEndLabel').hidden = !generic;
  if ($('#reportEntityLabel')) $('#reportEntityLabel').hidden = !template || !['project', 'model'].includes(template.type);
  if (generic && $('#reportEndDate') && !$('#reportEndDate').value && $('#reportWeekStart')?.value) {
    const end = new Date(`${$('#reportWeekStart').value}T12:00:00`);
    end.setDate(end.getDate() + 6);
    $('#reportEndDate').value = localIsoDate(end);
  }
  const entity = $('#reportRelatedEntity');
  if (!entity) return;
  entity.replaceChildren();
  const source = template?.type === 'project' ? state.projects : template?.type === 'model' ? state.models : [];
  source.forEach(item => {
    const option = make('option', '', `${item.id} · ${item.name}`);
    option.value = item.id;
    entity.append(option);
  });
  const labels = template?.section_labels || {};
  const headings = $$('.report-section-card h2');
  if (headings.length === 3) {
    [labels.highlights || '完成与进展', labels.risks || '阻塞与风险', labels.next_plan || '下周计划']
      .forEach((value, index) => { headings[index].textContent = value; });
  }
}
function renderGenericReport(report) {
  if (!$('#weeklyReportForm')) return;
  state.currentGeneratedReportId = report.id || null;
  renderWeeklyReport({
    ...report,
    week_start: report.period_start,
    executive_summary: report.sections?.summary || '',
    highlights: report.sections?.highlights || '',
    risks: report.sections?.risks || '',
    next_week_plan: report.sections?.next_plan || '',
    saved: !!report.saved,
  });
}
function renderGenericReportHistory() {
  const list = $('#genericReportHistory');
  if (!list) return;
  list.replaceChildren();
  state.genericReports.slice(0, 20).forEach(report => {
    const row = make('div');
    const copy = make('span');
    copy.append(make('strong', '', report.title), make('small', '', `${report.type} · ${report.period_start || '未设置周期'}`));
    row.append(make('time', '', formatDate(report.updated_at).slice(0, 10)), copy);
    list.append(row);
  });
  if (!state.genericReports.length) list.append(make('p', 'empty-state', '暂无模板报告'));
}
function downloadFormattedReport(format) {
  const template = currentReportTemplate();
  if (!template || template.type === 'weekly') {
    downloadData(`/api/weekly-reports/${$('#reportWeekStart')?.value}/${format}`);
    return;
  }
  if (!state.currentGeneratedReportId) {
    showToast('请先保存模板报告，再下载 Word 或 PDF');
    return;
  }
  downloadData(`/api/reports/${state.currentGeneratedReportId}/${format}`);
}
function setReportTemplateEditor() {}
function renderReportTemplateManager() {}

const overlay = $('#overlay');
const drawer = $('#sqlDrawer');
const entityDrawer = $('#entityDrawer');
function closeDrawer() {
  drawer.classList.remove('open');
  drawer.setAttribute('aria-hidden', 'true');
  overlay.classList.remove('open');
}

function closeEntityDrawer() {
  entityDrawer.classList.remove('open');
  entityDrawer.setAttribute('aria-hidden', 'true');
  overlay.classList.remove('open');
}

function addDetailSummary(label, value) {
  const item = make('div');
  item.append(make('span', '', label), make('strong', '', value || '未设置'));
  $('#entityDetailSummary').append(item);
}

function addDetailSection(title, description = '', rows = []) {
  const section = make('section', 'entity-detail-section');
  section.append(make('h3', '', title));
  if (description) section.append(make('p', 'entity-detail-copy', description));
  rows.forEach(([label, value]) => {
    const row = make('div', 'relation-row');
    row.append(make('span', '', label), make('strong', '', value || '未设置'));
    section.append(row);
  });
  $('#entityDetailContent').append(section);
}

async function loadRequestSqlVersions(requestId) {
  if (!requestId || !state.apiAvailable) return [];
  try {
    return await apiRequest(`/api/data-requests/${requestId}/sql-versions`);
  } catch (_) {
    return [];
  }
}

function addRequestSqlSection(item, versions = []) {
  const section = make('section', 'entity-detail-section request-sql-detail');
  const head = make('div', 'section-title');
  const versionLabel = item.sql_current_version || 'v1.0';
  head.append(make('h3', '', `SQL 代码 · ${versionLabel}`));
  const sql = String(item.sql_text || '').trim();
  if (sql) {
    const copy = make('button', 'copy-button');
    copy.type = 'button';
    copy.append(document.createTextNode('复制 SQL'));
    copy.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(item.sql_text || '');
        showToast('SQL 已复制');
      } catch (_) { showToast('复制失败，请手动选择文本'); }
    });
    head.append(copy);
  }
  section.append(head);
  if (!sql) {
    section.append(make('p', 'entity-detail-copy', '尚未记录取数 SQL。编辑请求时可粘贴并另存版本。'));
  } else {
    const shell = make('div', 'sql-code-shell');
    const chrome = make('div', 'sql-code-chrome');
    chrome.append(make('span', ''), make('span', ''), make('span', ''), make('em', '', `${versionLabel}.sql`));
    const pre = make('pre', 'sql-code');
    const code = document.createElement('code');
    code.textContent = item.sql_text || '';
    pre.append(code);
    shell.append(chrome, pre);
    section.append(shell);
  }
  if (versions.length) {
    section.append(make('h3', '', '版本历史'));
    const list = make('div', 'history-list soft-history');
    versions.forEach(version => {
      const row = make('div');
      const copy = make('span');
      copy.append(
        make('strong', '', version.version),
        make('small', '', `${formatDate(version.created_at)} · ${version.change_summary || '无说明'}`),
      );
      row.append(copy);
      list.append(row);
    });
    section.append(list);
  }
  $('#entityDetailContent').append(section);
}

function formatCalendarEventWhen(event) {
  const start = String(event?.start_at || '');
  const end = String(event?.end_at || '');
  const day = start.slice(0, 10);
  if (event?.all_day || (!start.includes('T') && day)) {
    if (end && end.slice(0, 10) && end.slice(0, 10) !== day) {
      return `${day} – ${end.slice(0, 10)} · 全天`;
    }
    return `${day || '未安排'} · 全天`;
  }
  const startTime = start.slice(11, 16);
  const endTime = end.slice(11, 16);
  if (startTime && endTime) return `${day} ${startTime} – ${endTime}`;
  if (startTime) return `${day} ${startTime}`;
  return day || formatDate(start) || '未安排';
}

async function openEntityDrawer(type, item) {
  if (!item) return;
  closeDrawer();
  state.currentDetail = { type, item };
  $('#entityDetailSummary').replaceChildren();
  $('#entityDetailContent').replaceChildren();
  const editBtn = $('#editEntityDetailButton');
  const deleteBtn = $('#deleteEntityDetailButton');
  if (editBtn) editBtn.hidden = false;
  if (deleteBtn) deleteBtn.hidden = false;

  if (type === 'task') {
    const taskStatuses = { todo: '待处理', doing: '进行中', done: '已完成', blocked: '受阻' };
    const priorities = { high: '高', medium: '中', low: '低' };
    $('#entityDetailEyebrow').textContent = `TASK / ${item.id}`;
    $('#entityDetailTitle').textContent = item.title;
    addDetailSummary('状态', taskStatuses[item.status] || item.status);
    addDetailSummary('优先级', `${priorities[item.priority] || item.priority || '中'}优先级`);
    addDetailSummary('计划时间', `${item.planned_date || '未安排'}${item.due_at ? ` ${item.due_at}` : ''}`);
    addDetailSection('任务说明', item.notes || '暂未补充任务说明。');
    addDetailSection('关联对象', '', [
      ['任务类型', taskTypeLabel(item.type)],
      ['关联类型', item.related_entity_type || '未关联'],
      ['关联编号', item.related_entity_id || '未关联'],
    ]);
    addDetailSection('记录信息', '', [
      ['任务编号', item.id],
      ['创建时间', formatDate(item.created_at)],
      ['更新时间', formatDate(item.updated_at)],
    ]);
  } else if (type === 'data_request') {
    const status = requestStatus[item.status] || [item.status, 'waiting'];
    let detail = item;
    let versions = item.sql_versions || [];
    if (state.apiAvailable) {
      try {
        detail = await apiRequest(`/api/data-requests/${item.id}`);
        versions = detail.sql_versions || [];
        state.currentDetail = { type, item: detail };
      } catch (_) {}
    }
    $('#entityDetailEyebrow').textContent = `DATA REQUEST / ${detail.id}`;
    $('#entityDetailTitle').textContent = detail.title;
    addDetailSummary('状态', status[0]);
    addDetailSummary('需求人', detail.requester || '未填写');
    addDetailSummary('SQL 版本', detail.sql_current_version || 'v1.0');
    addDetailSection('数据范围', detail.scope || '暂未填写数据范围。');
    addDetailSection('口径说明', detail.caliber_notes || '暂未填写统计口径。');
    addRequestSqlSection(detail, versions);
    addDetailSection('存档信息', '', [
      ['用途说明', detail.purpose || '未填写'],
      ['部门', detail.department || '未填写'],
      ['期望日期', detail.due_at ? formatDate(detail.due_at).slice(0, 10) : '未设置'],
      ['请求编号', detail.id],
    ]);
  } else if (type === 'note') {
    $('#entityDetailEyebrow').textContent = `WORKING NOTE / ${item.id}`;
    $('#entityDetailTitle').textContent = item.title;
    addDetailSummary('记录类型', item.type || '随手记录');
    addDetailSummary('标签', `${(item.tags || []).length} 个`);
    addDetailSummary('更新时间', formatDate(item.updatedAt || item.createdAt).slice(0, 10));
    const body = make('section');
    body.append(make('h3', '', '记录正文'));
    const markdown = make('div', 'note-markdown markdown-preview');
    markdown.innerHTML = renderMarkdown(item.content || '');
    body.append(markdown);
    $('#entityDetailContent').append(body);
    addDetailSection('分类与关联', '', [
      ['标签', (item.tags || []).map(tag => `#${tag}`).join(' ') || '未添加'],
      ['关联对象', item.relation || '未关联'],
      ['收藏', item.isFavorite ? '是' : '否'],
      ['归档', item.isArchived ? '是' : '否'],
      ['记录编号', item.id],
      ['创建时间', formatDate(item.createdAt)],
    ]);
  } else if (type === 'calendar_event') {
    if (editBtn) editBtn.hidden = true;
    if (deleteBtn) deleteBtn.hidden = true;
    const sourceLabel = item.source === 'caldav' ? 'CalDAV' : item.source === 'ics' ? 'ICS' : (item.source || '日历');
    $('#entityDetailEyebrow').textContent = `CALENDAR / ${item.id || item.external_id || 'EVENT'}`;
    $('#entityDetailTitle').textContent = item.title || '未命名日程';
    addDetailSummary('时间', formatCalendarEventWhen(item));
    addDetailSummary('地点', item.location || '未填写');
    addDetailSummary('来源', sourceLabel);
    addDetailSection('日程说明', item.description || '暂无详细说明。');
    addDetailSection('同步信息', '', [
      ['外部编号', item.external_id || '无'],
      ['订阅编号', item.subscription_id || '无'],
      ['开始', item.start_at || '未设置'],
      ['结束', item.end_at || '未设置'],
    ]);
  } else {
    return;
  }

  entityDrawer.classList.add('open');
  entityDrawer.setAttribute('aria-hidden', 'false');
  overlay.classList.add('open');
  setTimeout(() => $('#closeEntityDrawer').focus(), 20);
}

async function openSqlDrawer(assetOrId) {
  try {
    closeEntityDrawer();
    const asset = typeof assetOrId === 'string' && state.apiAvailable
      ? await apiRequest(`/api/sql-assets/${assetOrId}`)
      : (typeof assetOrId === 'string' ? state.sqlAssets.find(item => item.id === assetOrId) : assetOrId);
    if (!asset) {
      showToast('未找到对应 SQL 资产');
      return;
    }
    state.currentSql = asset;
    state.sqlVersions = state.apiAvailable ? await apiRequest(`/api/sql-assets/${asset.id}/versions`) : [];
    $('#drawerTitle').textContent = asset.name;
    $('#sqlDrawer .eyebrow').textContent = `SQL ASSET / ${asset.id}`;
    $$('#sqlDrawer .detail-summary strong')[0].textContent = asset.current_version;
    $$('#sqlDrawer .detail-summary strong')[1].textContent = formatDate(asset.updated_at).slice(0, 10);
    $$('#sqlDrawer .detail-summary strong')[2].textContent = asset.reuse_count || 0;
    $('#sqlDrawer .drawer-body section > p').textContent = asset.purpose || '暂无用途说明。';
    renderSqlCode($('#sqlCodeView') || $('#sqlDrawer pre'), asset.sql_text);
    $('#sqlVersion').innerHTML = '';
    state.sqlVersions.forEach(version => $('#sqlVersion').append(new Option(
      `${version.version}${version.version === asset.current_version ? ' 当前' : ''}`,
      version.id,
    )));
    const currentVersion = state.sqlVersions.find(version => version.version === asset.current_version);
    if (currentVersion) $('#sqlVersion').value = currentVersion.id;
    renderSqlVersionHistory();
    const relationStrongs = $$('#sqlDrawer .relation-row strong');
    const projectStrong = relationStrongs[0];
    if (projectStrong) {
      projectStrong.replaceChildren();
      if (asset.related_project_id) {
        const btn = make('button', 'assoc-jump', projectLabel(asset.related_project_id));
        btn.type = 'button';
        btn.title = `打开项目 ${asset.related_project_id}`;
        btn.addEventListener('click', () => jumpToProject(asset.related_project_id));
        projectStrong.append(btn);
      } else {
        projectStrong.textContent = '未关联项目';
      }
    }
    if (relationStrongs[1]) relationStrongs[1].textContent = '可在数据请求中关联此 SQL';
    if (relationStrongs[2]) relationStrongs[2].textContent = `${(asset.table_names || []).join('、') || '未登记'}（${(asset.table_names || []).length} 张表）`;
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
    overlay.classList.add('open');
  } catch (error) { showToast(error.message); }
}

function renderSqlVersionHistory() {
  const list = $('#sqlVersionHistory'); list.replaceChildren();
  if (!state.sqlVersions.length) { list.append(make('p', 'empty-state', '暂无版本记录')); return; }
  state.sqlVersions.forEach(version => {
    const row = make('div');
    const status = sqlStatus[version.validation_status] || [version.validation_status, 'waiting'];
    const copy = make('span');
    copy.append(make('strong', '', version.change_summary || '未填写变更说明'), make('small', '', formatDate(version.created_at)));
    row.append(make('b', '', version.version), copy, make('em', `status ${status[1]}`, status[0]));
    list.append(row);
  });
}

$('#closeDrawer').addEventListener('click', closeDrawer);
$('#closeEntityDrawer').addEventListener('click', closeEntityDrawer);
overlay.addEventListener('click', () => { closeDrawer(); closeEntityDrawer(); });
$('#editEntityDetailButton').addEventListener('click', () => {
  const detail = state.currentDetail;
  if (!detail) return;
  closeEntityDrawer();
  if (detail.type === 'task') openTaskForm(detail.item);
  if (detail.type === 'data_request') openRequestForm(detail.item);
  if (detail.type === 'note') openRecord(detail.item);
});
$('#deleteEntityDetailButton').addEventListener('click', () => {
  const detail = state.currentDetail;
  if (!detail) return;
  if (detail.type === 'task') deleteTask(detail.item.id);
  if (detail.type === 'data_request') deleteRequest(detail.item.id);
  if (detail.type === 'note') deleteNote(detail.item.id);
});
function extractSqlParameters(sqlText = '') {
  const found = new Set();
  const patterns = [
    /:([A-Za-z_][A-Za-z0-9_]*)/g,
    /@([A-Za-z_][A-Za-z0-9_]*)/g,
    /\$\{([A-Za-z_][A-Za-z0-9_]*)\}/g,
  ];
  patterns.forEach(pattern => {
    let match;
    while ((match = pattern.exec(sqlText))) found.add(match[1]);
  });
  return [...found];
}

$('#copySql').addEventListener('click', async () => {
  const sqlText = $('.drawer pre')?.innerText || '';
  const params = extractSqlParameters(sqlText);
  const clipboard = params.length
    ? `${sqlText}\n\n-- 参数清单\n${params.map(name => `-- ${name}=`).join('\n')}`
    : sqlText;
  try { await navigator.clipboard.writeText(clipboard); } catch (_) {}
  $('#copySql span').textContent = '已复制';
  showToast(params.length ? `已复制 SQL 与 ${params.length} 个参数` : 'SQL 已复制到剪贴板');
  setTimeout(() => { $('#copySql span').textContent = '复制 SQL'; }, 1600);
});
$('#sqlVersion').addEventListener('change', event => {
  const version = state.sqlVersions.find(item => String(item.id) === event.target.value);
  if (!version) return;
  renderSqlCode($('#sqlCodeView') || $('#sqlDrawer pre'), version.sql_text);
  $$('.detail-summary strong')[0].textContent = version.version;
  showToast(`已切换至 ${version.version}`);
});
$('#newSqlVersionButton').addEventListener('click', () => {
  if (!state.currentSql) return;
  $('#sqlVersionForm').reset();
  $('#versionSqlText').value = state.currentSql.sql_text || '';
  closeDrawer(); openModal($('#sqlVersionModal'));
  setTimeout(() => $('#versionName').focus(), 20);
});

function fillSqlDiffSelectors() {
  const left = $('#sqlDiffLeft');
  const right = $('#sqlDiffRight');
  if (!left || !right) return;
  left.replaceChildren();
  right.replaceChildren();
  state.sqlVersions.forEach(version => {
    left.append(new Option(version.version, version.version));
    right.append(new Option(version.version, version.version));
  });
  if (state.sqlVersions.length >= 2) {
    left.value = state.sqlVersions[1].version;
    right.value = state.sqlVersions[0].version;
  } else if (state.sqlVersions.length === 1) {
    left.value = state.sqlVersions[0].version;
    right.value = state.sqlVersions[0].version;
  }
}

async function runSqlDiff() {
  if (!state.currentSql) return;
  const left = $('#sqlDiffLeft')?.value;
  const right = $('#sqlDiffRight')?.value;
  if (!left || !right) { showToast('请选择两个版本'); return; }
  try {
    const result = await apiRequest(`/api/sql-assets/${state.currentSql.id}/versions/diff?left=${encodeURIComponent(left)}&right=${encodeURIComponent(right)}`);
    const hint = $('#sqlDiffSensitiveHint');
    if (hint) {
      hint.textContent = result.sensitive_findings?.length
        ? `右侧版本疑似含 ${result.sensitive_findings.length} 处敏感信息，请确认是否需要脱敏。`
        : '未在右侧版本中检测到明显敏感信息。';
    }
    $('#sqlDiffOutput').textContent = result.changed
      ? (result.diff || []).join('\n')
      : '两个版本内容相同。';
  } catch (error) { showToast(error.message); }
}

$('#compareSqlVersionsButton')?.addEventListener('click', () => {
  if (!state.currentSql) return;
  if ((state.sqlVersions || []).length < 2) { showToast('至少需要两个版本才能对比'); return; }
  fillSqlDiffSelectors();
  $('#sqlDiffOutput').textContent = '点击「生成差异」查看 unified diff';
  if ($('#sqlDiffSensitiveHint')) $('#sqlDiffSensitiveHint').textContent = '';
  openModal($('#sqlDiffModal'));
});
$('#runSqlDiffButton')?.addEventListener('click', runSqlDiff);

function openModal(modal) {
  if (!modal) return;
  const openCount = $$('.modal.open').filter(item => item !== modal).length;
  modal.style.zIndex = String(60 + openCount * 20);
  modal.classList.add('open');
  modal.setAttribute('aria-hidden', 'false');
  document.body.classList.add('modal-open');
}
function closeModal(modal) {
  if (!modal) return;
  modal.classList.remove('open');
  modal.setAttribute('aria-hidden', 'true');
  modal.style.zIndex = '';
  const stillOpen = $$('.modal.open');
  stillOpen.forEach((item, index) => {
    item.style.zIndex = String(60 + index * 20);
  });
  if (!stillOpen.length) document.body.classList.remove('modal-open');
}
$$('.modal-close').forEach(button => button.addEventListener('click', () => closeModal(button.closest('.modal'))));
$$('.modal').forEach(modal => modal.addEventListener('click', event => { if (event.target === modal) closeModal(modal); }));

function taskRelationType(type) {
  return ({ model: 'model', request: 'data_request', sql: 'sql_asset', report: 'project', note: 'project' })[type] || null;
}

function openTaskForm(task = null, plannedDate = null) {
  $('#taskForm').reset();
  const dates = getWeekDates(state.weekOffset);
  const today = localIsoDate(new Date());
  const defaultDate = dates.some(date => localIsoDate(date) === today) ? today : localIsoDate(dates[0]);
  $('#taskId').value = task?.id || '';
  $('#taskModalTitle').textContent = task ? '编辑任务' : '新建任务';
  $('#taskTitle').value = task?.title || '';
  $('#taskDate').value = task?.planned_date || plannedDate || defaultDate;
  $('#taskTime').value = task?.due_at || '';
  $('#taskStatus').value = task?.status || 'todo';
  $('#taskPriority').value = task?.priority || 'medium';
  $('#taskType').value = task?.type || 'task';
  fillEntityRelationOptions();
  $('#taskRelation').value = task?.related_entity_id || '';
  $('#taskNotes').value = task?.notes || '';
  if ($('#taskWaitingOn')) $('#taskWaitingOn').value = task?.waiting_on || '';
  if ($('#taskRecurrence')) $('#taskRecurrence').value = task?.recurrence || 'none';
  if ($('#taskRecurrenceInterval')) $('#taskRecurrenceInterval').value = task?.recurrence_interval || 7;
  if ($('#taskRemindAt')) $('#taskRemindAt').value = task?.remind_at?.slice(0, 10) || '';
  if ($('#taskActualMinutes')) $('#taskActualMinutes').value = task?.actual_minutes || 0;
  if ($('#taskCompletionResult')) $('#taskCompletionResult').value = task?.completion_result || '';
  $('#copyTaskButton').hidden = !task?.planned_date;
  $('#deleteTaskButton').hidden = !task;
  openModal($('#taskModal'));
  setTimeout(() => $('#taskTitle').focus(), 20);
}

async function deleteTask(id) {
  if (!id || !window.confirm('确认删除这个任务吗？')) return;
  try {
    await apiRequest(`/api/tasks/${id}`, { method: 'DELETE' });
    closeModal($('#taskModal')); closeEntityDrawer(); await Promise.all([refreshWeekTasks(), refreshTodayTasks()]); showToast('任务已删除');
  } catch (error) { showToast(error.message); }
}

$('#addTaskButton').addEventListener('click', () => openTaskForm());
$('#deleteTaskButton').addEventListener('click', () => deleteTask($('#taskId').value));
$('#copyTaskButton').addEventListener('click', async () => {
  const id = $('#taskId').value;
  if (!id) return;
  try {
    const result = await apiRequest(`/api/tasks/${id}/copy-next-week`, { method: 'POST' });
    closeModal($('#taskModal'));
    showToast(result.created ? '任务已复制到下周' : '下周已有相同任务，未重复创建');
  } catch (error) { showToast(error.message); }
});
$('#copyWeekButton').addEventListener('click', async () => {
  const ids = state.weekTasks.filter(task => task.status !== 'done').map(task => task.id);
  if (!ids.length) { showToast('本周没有需要复制的未完成任务'); return; }
  try {
    const result = await apiRequest('/api/tasks/batch-copy-next-week', { method: 'POST', body: JSON.stringify({ ids }) });
    showToast(`已复制 ${result.copied_count} 项，跳过 ${result.skipped_count} 项`);
  } catch (error) { showToast(error.message); }
});
$('#taskForm').addEventListener('submit', async event => {
  event.preventDefault();
  const id = $('#taskId').value;
  const type = $('#taskType').value;
  const relation = $('#taskRelation').value.trim();
  const payload = {
    title: $('#taskTitle').value.trim(), planned_date: $('#taskDate').value,
    due_at: $('#taskTime').value || null, status: $('#taskStatus').value,
    priority: $('#taskPriority').value, type, notes: $('#taskNotes').value.trim(),
    waiting_on: $('#taskWaitingOn')?.value.trim() || '',
    recurrence: $('#taskRecurrence')?.value || 'none',
    recurrence_interval: Number($('#taskRecurrenceInterval')?.value || 7),
    remind_at: $('#taskRemindAt')?.value || null,
    actual_minutes: Number($('#taskActualMinutes')?.value || 0),
    completion_result: $('#taskCompletionResult')?.value.trim() || '',
    related_entity_type: relation ? taskRelationType(type) : null,
    related_entity_id: relation || null,
  };
  try {
    const saved = await apiRequest(id ? `/api/tasks/${id}` : '/api/tasks', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) });
    closeModal($('#taskModal')); await Promise.all([refreshWeekTasks(), refreshTodayTasks()]);
    showToast(saved?.spawned_next ? '任务已完成，并生成了下一次重复任务' : (id ? '任务已更新' : '任务已加入周计划'));
  } catch (error) { showToast(error.message); }
});

function normalizeNote(note) {
  return {
    id: note.id, type: note.type, title: note.title, content: note.content,
    tags: note.tags || [], relation: note.related_entity_id || note.relation || '',
    isFavorite: !!(note.is_favorite ?? note.isFavorite),
    isArchived: !!(note.is_archived ?? note.isArchived),
    revisions: note.revisions || [],
    createdAt: note.created_at || note.createdAt,
    updatedAt: note.updated_at || note.updatedAt || note.created_at || note.createdAt,
  };
}

function updateBatchButtons() {
  $('#noteBatchDelete').disabled = !state.selectedNotes.size;
  $('#requestBatchDone').disabled = !state.selectedRequests.size;
  $('#requestBatchDelete').disabled = !state.selectedRequests.size;
  $('#sqlBatchValidate').disabled = !state.selectedSql.size;
  $('#sqlBatchDelete').disabled = !state.selectedSql.size;
}

function setNotePreviewMode(enabled) {
  state.notePreviewMode = !!enabled;
  const editor = $('#recordContent');
  const preview = $('#recordPreview');
  const toggle = $('#toggleNotePreview');
  if (!editor || !preview || !toggle) return;
  preview.hidden = !enabled;
  editor.hidden = !!enabled;
  toggle.textContent = enabled ? '编辑' : '预览';
  if (enabled) preview.innerHTML = renderMarkdown(editor.value);
}

function insertMarkdownSnippet(kind) {
  const textarea = $('#recordContent');
  if (!textarea || state.notePreviewMode) { showToast('请先切换到编辑模式'); return; }
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const selected = textarea.value.slice(start, end) || '文本';
  const snippets = {
    bold: `**${selected}**`,
    italic: `*${selected}*`,
    ul: `- ${selected}`,
    code: selected.includes('\n') ? `\`\`\`\n${selected}\n\`\`\`` : `\`${selected}\``,
    link: `[${selected}](https://)`,
    h2: `## ${selected}`,
  };
  const insert = snippets[kind] || selected;
  textarea.setRangeText(insert, start, end, 'end');
  textarea.focus();
}

$$('#markdownToolbar [data-md]').forEach(button => {
  button.addEventListener('click', () => insertMarkdownSnippet(button.dataset.md));
});
$('#toggleNotePreview')?.addEventListener('click', () => setNotePreviewMode(!state.notePreviewMode));

async function openRecord(note = null) {
  $('#recordForm').reset();
  state.noteAssist = null; $('#noteAssistPanel').hidden = true;
  setNotePreviewMode(false);
  $('#recordId').value = note?.id || '';
  $('#recordModalTitle').textContent = note ? '编辑工作记录' : '新建工作记录';
  $('#recordType').value = note?.type || '随手记录';
  $('#recordTitle').value = note?.title || '';
  $('#recordContent').value = note?.content || '';
  $('#recordTags').value = (note?.tags || []).join(', ');
  fillEntityRelationOptions();
  $('#recordRelation').value = note?.relation || note?.related_entity_id || '';
  if ($('#recordFavorite')) $('#recordFavorite').checked = !!note?.isFavorite;
  if ($('#recordArchived')) $('#recordArchived').checked = !!note?.isArchived;
  $('#deleteNoteButton').hidden = !note;
  const revisionPanel = $('#noteRevisionPanel');
  const revisionList = $('#noteRevisionList');
  if (revisionPanel && revisionList) {
    revisionList.replaceChildren();
    let revisions = note?.revisions || [];
    if (note?.id && state.apiAvailable && !revisions.length) {
      try { revisions = await apiRequest(`/api/notes/${note.id}/revisions`); } catch (_) { revisions = []; }
    }
    if (revisions.length) {
      revisionPanel.hidden = false;
      revisions.forEach(item => {
        const row = make('div');
        const copy = make('span');
        copy.append(make('strong', '', item.title || '无标题'), make('small', '', formatDate(item.created_at)));
        row.append(make('time', '', formatDate(item.created_at).slice(0, 10)), copy);
        revisionList.append(row);
      });
    } else {
      revisionPanel.hidden = true;
    }
  }
  openModal($('#recordModal'));
  setTimeout(() => $('#recordTitle').focus(), 20);
}

function renderNoteAssist(result) {
  state.noteAssist = result;
  $('#noteAssistPanel').hidden = false;
  $('#noteAssistConfidence').textContent = `置信度 ${result.confidence}%`;
  const summary = $('#noteAssistSummary'); summary.replaceChildren();
  [["推荐类型", result.suggested_type], ["建议标签", result.suggested_tags.join('、') || '暂无'], ["关联编号", result.suggested_relation || '未识别']]
    .forEach(([label, value]) => { const item = make('div'); item.append(make('span', '', label), make('strong', '', value)); summary.append(item); });
  const similar = $('#similarNoteList'); similar.replaceChildren();
  if (result.similar_notes.length) {
    similar.append(make('strong', '', '相似记录'));
    result.similar_notes.forEach(note => {
      const row = make('div'); row.append(make('span', '', `${note.id} · ${note.title}`), make('em', '', `${note.score}% 相似`)); similar.append(row);
    });
  } else {
    similar.append(make('span', 'assistant-empty', '未发现明显相似记录'));
  }
}

$('#analyzeNoteButton').addEventListener('click', async () => {
  const title = $('#recordTitle').value.trim(); const content = $('#recordContent').value.trim();
  if (!title && !content) { showToast('请先填写标题或内容'); return; }
  try {
    renderNoteAssist(await apiRequest('/api/notes/assist', { method: 'POST', body: JSON.stringify({ title, content, exclude_id: $('#recordId').value || null }) }));
  } catch (error) { showToast(error.message); }
});

$('#applyNoteAssist').addEventListener('click', () => {
  const result = state.noteAssist; if (!result) return;
  $('#recordType').value = result.suggested_type;
  const tags = [...new Set([...splitValues($('#recordTags').value), ...result.suggested_tags])];
  $('#recordTags').value = tags.join(', ');
  if (!$('#recordRelation').value.trim() && result.suggested_relation) $('#recordRelation').value = result.suggested_relation;
  showToast('整理建议已填入，请确认后保存');
});

function renderSavedNotes() {
  const feed = $('.note-feed');
  feed.replaceChildren();
  renderNoteFilters();
  const query = ($('#noteSearch')?.value || '').trim().toLowerCase();
  const items = state.notes.filter(note => {
    const scope = state.noteScope || 'active';
    const scopeMatch = scope === 'favorite' ? note.isFavorite
      : scope === 'archived' ? note.isArchived
      : !note.isArchived;
    const categoryMatch = state.noteCategory === 'all' || note.type === state.noteCategory;
    const searchMatch = !query || `${note.title} ${note.content} ${(note.tags || []).join(' ')}`.toLowerCase().includes(query);
    return scopeMatch && categoryMatch && searchMatch;
  });
  const countHint = $('#notesResultHint');
  if (countHint) countHint.textContent = items.length ? `${items.length} 条记录` : '无匹配记录';

  items.forEach(note => {
    const article = make('article', 'saved-note');
    article.tabIndex = 0;
    article.setAttribute('role', 'button');
    article.setAttribute('aria-label', `查看工作记录：${note.title}`);
    article.classList.toggle('selected', state.selectedNotes.has(note.id));
    const header = make('header');
    const headerLeft = make('div');
    const select = make('label', 'note-select');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox'; checkbox.checked = state.selectedNotes.has(note.id);
    checkbox.addEventListener('change', () => {
      checkbox.checked ? state.selectedNotes.add(note.id) : state.selectedNotes.delete(note.id);
      article.classList.toggle('selected', checkbox.checked); updateBatchButtons();
    });
    select.append(checkbox);
    headerLeft.append(select, make('span', 'note-type', note.type));
    if (note.isFavorite) headerLeft.append(make('span', 'note-type is-fav', '收藏'));
    if (note.isArchived) headerLeft.append(make('span', 'note-type is-archived', '归档'));
    header.append(headerLeft, make('time', '', formatDate(note.createdAt)));
    const title = make('h2', '', note.title);
    const content = make('div', 'note-markdown note-excerpt');
    content.innerHTML = renderMarkdown(note.content || '暂未补充详细内容。');
    const footer = make('footer');
    const tagRow = make('div', 'note-tag-row');
    (note.tags.length ? note.tags : ['个人记录']).forEach(tag => tagRow.append(make('span', '', `#${tag}`)));
    if (note.relation) tagRow.append(make('b', '', `关联 ${note.relation}`));
    const actions = make('div', 'note-actions');
    const edit = make('button', '', '编辑'); edit.type = 'button'; edit.addEventListener('click', () => openRecord(note));
    const remove = make('button', 'delete-note', '删除'); remove.type = 'button'; remove.addEventListener('click', () => deleteNote(note.id));
    actions.append(edit, remove);
    footer.append(tagRow, actions);
    article.append(header, title, content, footer);
    article.addEventListener('click', event => {
      if (event.target.closest('button, input, label')) return;
      openEntityDrawer('note', note);
    });
    article.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openEntityDrawer('note', note); }
    });
    feed.append(article);
  });
  if (!items.length) feed.append(make('p', 'empty-state', '没有符合条件的工作记录'));
  renderTodayNotesHome();
}

function renderNoteFilters() {
  const container = $('#noteCategoryFilters');
  if (!container) return;
  const types = ['口径说明', '问题排查', '项目复盘', '模型维护', '随手记录'];
  container.replaceChildren();
  [['all', '全部记录'], ...types.map(type => [type, type])].forEach(([value, label]) => {
    const count = value === 'all' ? state.notes.length : state.notes.filter(note => note.type === value).length;
    const button = make('button', state.noteCategory === value ? 'active' : '');
    button.type = 'button'; button.append(document.createTextNode(`${label} `), make('b', '', count));
    button.addEventListener('click', () => { state.noteCategory = value; renderSavedNotes(); });
    container.append(button);
  });
}

$('#noteSearch')?.addEventListener('input', renderSavedNotes);
$$('#noteScopeFilters button').forEach(button => button.addEventListener('click', async () => {
  state.noteScope = button.dataset.noteScope;
  $$('#noteScopeFilters button').forEach(item => item.classList.toggle('active', item === button));
  if (state.apiAvailable) await refreshNotes();
  else renderSavedNotes();
}));

async function refreshNotes() {
  if (!state.apiAvailable) { renderSavedNotes(); return; }
  const scope = state.noteScope || 'active';
  const params = new URLSearchParams();
  if (scope === 'favorite') params.set('favorite', 'true');
  else if (scope === 'archived') params.set('archived', 'true');
  else params.set('archived', 'false');
  const notes = await apiRequest(`/api/notes?${params.toString()}`);
  state.notes = notes.map(normalizeNote);
  renderSavedNotes();
  updateBatchButtons();
}

async function deleteNote(id) {
  if (!window.confirm('确认删除这条工作记录吗？')) return;
  try {
    if (state.apiAvailable) await apiRequest(`/api/notes/${id}`, { method: 'DELETE' });
    state.notes = state.notes.filter(note => note.id !== id);
    state.selectedNotes.delete(id);
    if (!state.apiAvailable) localStorage.setItem('audit-workbench.notes', JSON.stringify(state.notes));
    closeModal($('#recordModal')); closeEntityDrawer(); renderSavedNotes(); updateBatchButtons(); showToast('工作记录已删除');
  } catch (error) { showToast(error.message); }
}

$('#quickCreate').addEventListener('click', () => openRecord());
$('#newNoteButton').addEventListener('click', () => openRecord());
$('#deleteNoteButton').addEventListener('click', () => deleteNote($('#recordId').value));
$('#recordForm').addEventListener('submit', async event => {
  event.preventDefault();
  const id = $('#recordId').value;
  const title = $('#recordTitle').value.trim();
  const content = $('#recordContent').value;
  if (!title) { showToast('请填写标题'); $('#recordTitle').focus(); return; }
  if (content.length > 100000) { showToast('正文过长，请压缩后再保存'); return; }
  const payload = {
    type: $('#recordType').value,
    title,
    content,
    tags: splitValues($('#recordTags').value),
    related_entity_id: $('#recordRelation').value.trim() || null,
    is_favorite: !!$('#recordFavorite')?.checked,
    is_archived: !!$('#recordArchived')?.checked,
  };
  const submitButton = $('#recordForm button[type="submit"]');
  if (submitButton) { submitButton.disabled = true; submitButton.textContent = '保存中…'; }
  try {
    if (state.apiAvailable) {
      await apiRequest(id ? `/api/notes/${id}` : '/api/notes', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) });
      state.noteScope = payload.is_archived ? 'archived' : 'active';
      $$('#noteScopeFilters button').forEach(button => {
        button.classList.toggle('active', button.dataset.noteScope === state.noteScope);
      });
      await refreshNotes();
      showView('notes');
    } else {
      const note = {
        ...payload, id: id || `N-${Date.now()}`, relation: payload.related_entity_id || '',
        isFavorite: payload.is_favorite, isArchived: payload.is_archived,
        createdAt: new Date().toISOString(),
      };
      state.notes = id ? state.notes.map(item => item.id === id ? note : item) : [note, ...state.notes];
      localStorage.setItem('audit-workbench.notes', JSON.stringify(state.notes));
      renderSavedNotes();
      showView('notes');
    }
    closeModal($('#recordModal'));
    showToast(payload.is_archived
      ? (id ? '已更新并放入归档' : '已保存到归档')
      : (id ? '工作记录已更新' : '工作记录已保存'));
  } catch (error) { showToast(error.message || '保存失败'); }
  finally {
    if (submitButton) { submitButton.disabled = false; submitButton.textContent = '保存记录'; }
  }
});

$('#noteBatchDelete').addEventListener('click', async () => {
  const ids = [...state.selectedNotes];
  if (!ids.length || !window.confirm(`确认删除所选 ${ids.length} 条工作记录吗？`)) return;
  try {
    if (state.apiAvailable) await apiRequest('/api/notes/batch-delete', { method: 'POST', body: JSON.stringify({ ids }) });
    state.notes = state.notes.filter(note => !state.selectedNotes.has(note.id));
    state.selectedNotes.clear(); renderSavedNotes(); updateBatchButtons(); showToast(`已删除 ${ids.length} 条记录`);
  } catch (error) { showToast(error.message); }
});

function bumpRequestSqlVersionLabel(current = 'v1.0') {
  const match = String(current || 'v1.0').match(/^(.*?)(\d+)(\D*)$/);
  if (!match) return 'v1.1';
  const next = String(Number(match[2]) + 1);
  return `${match[1]}${next.padStart(match[2].length, '0')}${match[3]}`;
}

function syncRequestSqlVersionHint(version) {
  const label = version || $('#requestSqlVersion')?.value?.trim() || 'v1.0';
  if ($('#requestSqlVersionHint')) $('#requestSqlVersionHint').textContent = `当前 ${label}`;
  if ($('#requestSqlVersion') && !$('#requestSqlVersion').value.trim()) $('#requestSqlVersion').value = label;
}

function renderRequestSqlVersionList(versions = []) {
  const panel = $('#requestSqlVersionPanel');
  const list = $('#requestSqlVersionList');
  if (!panel || !list) return;
  list.replaceChildren();
  if (!versions.length) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  const current = $('#requestSqlVersion')?.value?.trim() || '';
  versions.forEach(version => {
    const row = make('div');
    const copy = make('span');
    const mark = version.version === current ? ' · 当前' : '';
    copy.append(
      make('strong', '', `${version.version}${mark}`),
      make('small', '', `${formatDate(version.created_at)} · ${version.change_summary || '无说明'}`),
    );
    const actions = make('div', 'batch-actions');
    const restore = make('button', 'secondary-button');
    restore.type = 'button';
    restore.textContent = '恢复此版本';
    restore.disabled = version.version === current;
    restore.addEventListener('click', async () => {
      const requestId = $('#requestId')?.value;
      if (!requestId) return;
      try {
        const updated = await apiRequest(`/api/data-requests/${requestId}/sql-versions/${version.id}/restore`, { method: 'POST' });
        $('#requestSqlText').value = updated.sql_text || '';
        $('#requestSqlVersion').value = updated.sql_current_version || version.version;
        syncRequestSqlVersionHint(updated.sql_current_version || version.version);
        await refreshRequestSqlVersions(requestId);
        const idx = state.requests.findIndex(item => item.id === requestId);
        if (idx >= 0) state.requests[idx] = { ...state.requests[idx], ...updated };
        renderRequests();
        renderTodayRequests();
        showToast(`已恢复 ${version.version}`);
      } catch (error) {
        showToast(error.message);
      }
    });
    actions.append(restore);
    row.append(copy, actions);
    list.append(row);
  });
}

async function refreshRequestSqlVersions(requestId) {
  if (!requestId || !state.apiAvailable) {
    renderRequestSqlVersionList([]);
    return [];
  }
  const versions = await loadRequestSqlVersions(requestId);
  renderRequestSqlVersionList(versions);
  return versions;
}

async function openRequestForm(request = null) {
  $('#requestForm').reset();
  let detail = request;
  if (request?.id && state.apiAvailable) {
    try {
      detail = await apiRequest(`/api/data-requests/${request.id}`);
    } catch (_) {
      detail = request;
    }
  }
  $('#requestId').value = detail?.id || '';
  $('#requestModalTitle').textContent = detail?.id ? '编辑数据请求' : '新建数据请求';
  $('#requestTitle').value = detail?.title || '';
  $('#requestPurpose').value = detail?.purpose || '';
  $('#requestDue').value = detail?.due_at?.slice(0, 10) || '';
  $('#requestScope').value = detail?.scope || '';
  $('#requestCaliber').value = detail?.caliber_notes || '';
  $('#requestStatus').value = detail?.status || 'pending';
  if ($('#requestRequester')) $('#requestRequester').value = detail?.requester || '';
  if ($('#requestDepartment')) $('#requestDepartment').value = detail?.department || '';
  if ($('#requestSqlText')) $('#requestSqlText').value = detail?.sql_text || '';
  const version = detail?.sql_current_version || 'v1.0';
  if ($('#requestSqlVersion')) $('#requestSqlVersion').value = version;
  syncRequestSqlVersionHint(version);
  const saveVersionBtn = $('#saveRequestSqlVersionButton');
  if (saveVersionBtn) saveVersionBtn.hidden = !detail?.id;
  $('#deleteRequestButton').hidden = !detail?.id;
  if (detail?.id) await refreshRequestSqlVersions(detail.id);
  else renderRequestSqlVersionList([]);
  openModal($('#requestModal'));
  setTimeout(() => $('#requestTitle').focus(), 20);
}

function renderRequests() {
  const rows = $('#requestRows'); rows.replaceChildren();
  const query = $('#requestSearch').value.trim().toLowerCase();
  const requester = ($('#requestFilterRequester')?.value || '').trim().toLowerCase();
  const department = ($('#requestFilterDepartment')?.value || '').trim().toLowerCase();
  const from = $('#requestFilterFrom')?.value || '';
  const to = $('#requestFilterTo')?.value || '';
  const items = state.requests.filter(item => {
    const statusMatch = state.requestStatus === 'all' || item.status === state.requestStatus;
    const searchMatch = !query || `${item.id} ${item.title} ${item.purpose} ${item.scope} ${item.requester || ''} ${item.department || ''} ${item.sql_text || ''}`.toLowerCase().includes(query);
    const requesterMatch = !requester || String(item.requester || '').toLowerCase().includes(requester);
    const departmentMatch = !department || String(item.department || '').toLowerCase().includes(department);
    const day = String(item.created_at || '').slice(0, 10);
    const fromMatch = !from || day >= from;
    const toMatch = !to || day <= to;
    return statusMatch && searchMatch && requesterMatch && departmentMatch && fromMatch && toMatch;
  });
  if (!items.length) rows.append(make('p', 'empty-state', '没有符合条件的数据请求'));
  items.forEach(item => {
    const row = make('div', 'data-list-row');
    const checkLabel = make('label', 'row-check');
    const check = document.createElement('input'); check.type = 'checkbox'; check.checked = state.selectedRequests.has(item.id);
    check.addEventListener('change', () => { check.checked ? state.selectedRequests.add(item.id) : state.selectedRequests.delete(item.id); updateBatchButtons(); });
    checkLabel.append(check);
    const meta = [item.id, item.requester || item.department, item.scope || '未填写数据范围'].filter(Boolean).join(' · ');
    const title = make('span', 'row-click'); title.append(make('strong', '', item.title), make('small', '', meta));
    const status = requestStatus[item.status] || [item.status, 'waiting'];
    row.append(
      checkLabel,
      title,
      make('span', 'row-click', item.purpose || '未填用途'),
      make('span', 'row-click', formatDate(item.created_at).slice(0, 10)),
      make('span', 'row-click', item.sql_current_version || 'v1.0'),
      make('span', `status ${status[1]}`, status[0]),
    );
    $$('.row-click', row).forEach(cell => cell.addEventListener('click', () => openEntityDrawer('data_request', item)));
    rows.append(row);
  });
  const metrics = $$('.summary-line > div strong', $('#view-requests'));
  if (metrics.length >= 4) {
    metrics[0].textContent = state.requests.length;
    metrics[1].textContent = state.requests.filter(item => item.status === 'working').length;
    metrics[2].textContent = state.requests.filter(item => item.status === 'waiting').length;
    const month = new Date().toISOString().slice(0, 7);
    const delivered = state.requests.filter(item => item.status === 'done' && String(item.updated_at || '').startsWith(month));
    metrics[3].textContent = delivered.length;
    const durations = delivered.map(item => Math.max(0, (new Date(item.updated_at) - new Date(item.created_at)) / 86400000)).filter(Number.isFinite);
    $('#requestAverageDays').textContent = durations.length ? `${(durations.reduce((sum, value) => sum + value, 0) / durations.length).toFixed(1)} 天` : '—';
  }
}

async function refreshRequests() {
  const params = new URLSearchParams();
  if (state.requestStatus !== 'all') params.set('status', state.requestStatus);
  const requester = $('#requestFilterRequester')?.value.trim();
  const department = $('#requestFilterDepartment')?.value.trim();
  const from = $('#requestFilterFrom')?.value;
  const to = $('#requestFilterTo')?.value;
  const q = $('#requestSearch')?.value.trim();
  if (requester) params.set('requester', requester);
  if (department) params.set('department', department);
  if (from) params.set('date_from', from);
  if (to) params.set('date_to', to);
  if (q) params.set('q', q);
  const query = params.toString();
  state.requests = await apiRequest(`/api/data-requests${query ? `?${query}` : ''}`);
  state.selectedRequests.clear(); renderRequests(); renderTodayRequests(); updateBatchButtons(); updateNavCounts();
}

async function deleteRequest(id) {
  if (!window.confirm('确认删除这个数据请求吗？')) return;
  try { await apiRequest(`/api/data-requests/${id}`, { method: 'DELETE' }); closeModal($('#requestModal')); closeEntityDrawer(); await refreshRequests(); showToast('数据请求已删除'); }
  catch (error) { showToast(error.message); }
}

$('#newRequestButton').addEventListener('click', () => openRequestForm());
$('#requestSearch').addEventListener('input', () => { if (state.apiAvailable) refreshRequests().catch(() => renderRequests()); else renderRequests(); });
$$('#requestStatusFilters button').forEach(button => button.addEventListener('click', () => {
  state.requestStatus = button.dataset.status;
  $$('#requestStatusFilters button').forEach(item => item.classList.toggle('active', item === button));
  if (state.apiAvailable) refreshRequests().catch(() => renderRequests());
  else renderRequests();
}));
$('#requestFilterApply')?.addEventListener('click', () => {
  if (state.apiAvailable) refreshRequests().catch(() => renderRequests());
  else renderRequests();
});
$('#requestFilterReset')?.addEventListener('click', () => {
  ['requestFilterRequester', 'requestFilterDepartment', 'requestFilterFrom', 'requestFilterTo', 'requestSearch'].forEach(id => { if ($(`#${id}`)) $(`#${id}`).value = ''; });
  state.requestStatus = 'all';
  $$('#requestStatusFilters button').forEach(item => item.classList.toggle('active', item.dataset.status === 'all'));
  if (state.apiAvailable) refreshRequests().catch(() => renderRequests());
  else renderRequests();
});
$('#deleteRequestButton').addEventListener('click', () => deleteRequest($('#requestId').value));
$('#requestForm').addEventListener('submit', async event => {
  event.preventDefault();
  const id = $('#requestId').value;
  const payload = {
    title: $('#requestTitle').value.trim(),
    purpose: $('#requestPurpose').value.trim(),
    scope: $('#requestScope').value.trim(),
    caliber_notes: $('#requestCaliber').value.trim(),
    due_at: $('#requestDue').value || null,
    status: $('#requestStatus').value,
    requester: $('#requestRequester')?.value.trim() || '',
    department: $('#requestDepartment')?.value.trim() || '',
    sql_text: $('#requestSqlText')?.value || '',
    sql_current_version: $('#requestSqlVersion')?.value.trim() || 'v1.0',
  };
  try {
    await apiRequest(id ? `/api/data-requests/${id}` : '/api/data-requests', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) });
    closeModal($('#requestModal')); await refreshRequests(); showToast(id ? '数据请求已更新' : '数据请求已创建');
  } catch (error) { showToast(error.message); }
});

$('#requestSqlVersion')?.addEventListener('input', () => syncRequestSqlVersionHint($('#requestSqlVersion').value.trim()));

$('#copyRequestSql')?.addEventListener('click', async () => {
  const text = $('#requestSqlText')?.value || '';
  if (!text.trim()) { showToast('暂无 SQL 可复制'); return; }
  try {
    await navigator.clipboard.writeText(text);
    showToast('SQL 已复制');
  } catch (_) { showToast('复制失败，请手动选择文本'); }
});

$('#saveRequestSqlVersionButton')?.addEventListener('click', () => {
  const requestId = $('#requestId')?.value;
  if (!requestId) { showToast('请先保存数据请求，再另存 SQL 版本'); return; }
  const sqlText = $('#requestSqlText')?.value || '';
  if (!sqlText.trim()) { showToast('请先填写 SQL 代码'); return; }
  $('#requestSqlVersionForm').reset();
  $('#requestNewSqlVersion').value = bumpRequestSqlVersionLabel($('#requestSqlVersion')?.value || 'v1.0');
  $('#requestSqlChangeSummary').value = '';
  openModal($('#requestSqlVersionModal'));
  setTimeout(() => $('#requestNewSqlVersion').focus(), 20);
});

$('#requestSqlVersionForm')?.addEventListener('submit', async event => {
  event.preventDefault();
  const requestId = $('#requestId')?.value;
  if (!requestId) return;
  const version = $('#requestNewSqlVersion')?.value.trim();
  const changeSummary = $('#requestSqlChangeSummary')?.value.trim() || '';
  const sqlText = $('#requestSqlText')?.value || '';
  if (!version) { showToast('请填写版本号'); return; }
  try {
    await apiRequest(`/api/data-requests/${requestId}/sql-versions`, {
      method: 'POST',
      body: JSON.stringify({ version, sql_text: sqlText, change_summary: changeSummary }),
    });
    $('#requestSqlVersion').value = version;
    syncRequestSqlVersionHint(version);
    closeModal($('#requestSqlVersionModal'));
    await refreshRequestSqlVersions(requestId);
    await refreshRequests();
    showToast(`已保存 SQL 版本 ${version}`);
  } catch (error) {
    showToast(error.message);
  }
});

async function batchRequest(path, success) {
  const ids = [...state.selectedRequests]; if (!ids.length) return;
  try { await apiRequest(path, { method: 'POST', body: JSON.stringify({ ids, ...(path.endsWith('status') ? { status: 'done' } : {}) }) }); await refreshRequests(); showToast(success); }
  catch (error) { showToast(error.message); }
}
$('#requestBatchDone').addEventListener('click', () => batchRequest('/api/data-requests/batch-status', '所选请求已标记为已交付'));
$('#requestBatchDelete').addEventListener('click', () => { if (window.confirm(`确认删除所选 ${state.selectedRequests.size} 个请求吗？`)) batchRequest('/api/data-requests/batch-delete', '所选请求已删除'); });

function openSqlForm(asset = null) {
  $('#sqlForm').reset();
  state.sqlAssist = null; $('#sqlAssistPanel').hidden = true;
  $('#sqlId').value = asset?.id || '';
  $('#sqlModalTitle').textContent = asset ? '编辑 SQL 资产' : '新建 SQL 资产';
  $('#sqlName').value = asset?.name || '';
  $('#sqlCurrentVersion').value = asset?.current_version || 'v1.0';
  $('#sqlStatus').value = asset?.status || 'draft';
  $('#sqlPurpose').value = asset?.purpose || '';
  $('#sqlTags').value = (asset?.tags || []).join(', ');
  $('#sqlTables').value = (asset?.table_names || []).join(', ');
  fillProjectSelect($('#sqlProject'), asset?.related_project_id || '');
  $('#sqlValidationNote').value = asset?.validation_note || '';
  $('#sqlText').value = asset?.sql_text || '';
  openModal($('#sqlModal'));
  setTimeout(() => $('#sqlName').focus(), 20);
}

function renderSqlAssist(result) {
  state.sqlAssist = result; $('#sqlAssistPanel').hidden = false;
  const levelNames = { low: '低风险', medium: '需关注', high: '高风险' };
  $('#sqlAssistLevel').className = `assist-level ${result.risk_level}`;
  $('#sqlAssistLevel').textContent = levelNames[result.risk_level] || result.risk_level;
  const summary = $('#sqlAssistSummary'); summary.replaceChildren();
  [["语句类型", result.operation], ["识别表", result.tables.join('、') || '未识别'], ["参数", result.parameters.join('、') || '未识别']]
    .forEach(([label, value]) => { const item = make('div'); item.append(make('span', '', label), make('strong', '', value)); summary.append(item); });
  const risks = $('#sqlRiskList'); risks.replaceChildren();
  const notes = [...(result.risk_notes || [])];
  (result.sensitive_findings || []).forEach(item => {
    notes.push(`敏感信息疑似命中：${item.type || item.kind || 'unknown'}（${item.snippet || '已遮罩'}）`);
  });
  (notes.length ? notes : ['未发现明显结构性风险，仍需进行样本验证。'])
    .forEach(item => risks.append(make('li', '', item)));
}

$('#analyzeSqlButton').addEventListener('click', async () => {
  const sqlText = $('#sqlText').value.trim();
  if (!sqlText) { showToast('请先填写 SQL 文本'); return; }
  const ai = state.settings?.ai || {};
  if (ai.ready && ai.include_sql_text !== false) {
    if (!window.confirm('当前允许向模型发送 SQL 正文。将发送：资产名称 + 完整 SQL。若只想发结构摘要，请先在数据管理关闭「允许向模型发送 SQL 正文」。是否继续？')) return;
  } else if (ai.ready) {
    if (!window.confirm('将调用 AI 辅助（已关闭 SQL 正文外发，仅发送名称与本地规则摘要）。是否继续？')) return;
  }
  try {
    renderSqlAssist(await apiRequest('/api/sql-assets/assist', { method: 'POST', body: JSON.stringify({ name: $('#sqlName').value.trim(), sql_text: sqlText }) }));
  } catch (error) { showToast(error.message); }
});

$('#applySqlAssist').addEventListener('click', () => {
  const result = state.sqlAssist; if (!result) return;
  if (!$('#sqlPurpose').value.trim()) $('#sqlPurpose').value = result.purpose;
  const tags = [...new Set([...splitValues($('#sqlTags').value), ...result.tags])];
  const tables = [...new Set([...splitValues($('#sqlTables').value), ...result.tables])];
  $('#sqlTags').value = tags.join(', '); $('#sqlTables').value = tables.join(', ');
  if (!$('#sqlValidationNote').value.trim()) $('#sqlValidationNote').value = result.validation_note;
  showToast('SQL 说明建议已填入，请确认后保存');
});

function renderSqlSummary() {
  const root = $('#sqlSummary');
  if (!root) return;
  const all = state.sqlAssets || [];
  const validated = all.filter(item => item.status === 'validated').length;
  const draft = all.filter(item => item.status === 'draft').length;
  const archived = all.filter(item => item.status === 'archived').length;
  const reuse = all.reduce((sum, item) => sum + (item.reuse_count || 0), 0);
  root.replaceChildren();
  [
    [all.length, '全部资产'],
    [validated, '已验证'],
    [draft, '草稿'],
    [reuse, '累计复用'],
  ].forEach(([value, label]) => {
    const cell = make('div');
    cell.append(make('strong', '', String(value)), make('span', '', label));
    root.append(cell);
  });
  if (archived) {
    const hint = make('p', '', `另有 ${archived} 条已归档`);
    root.append(hint);
  }
}

function renderSqlAssets() {
  const rows = $('#sqlRows'); rows.replaceChildren();
  const query = $('#sqlSearch').value.trim().toLowerCase();
  renderSqlSummary();
  renderSqlCategoryFilters();
  const selectedStatuses = new Set($$('.sql-status-filter:checked').map(input => input.value));
  const items = state.sqlAssets.filter(item => {
    const categoryMatch = state.sqlCategory === 'all' || (item.tags || []).includes(state.sqlCategory);
    const statusMatch = selectedStatuses.has(item.status);
    return categoryMatch && statusMatch && (!query || `${item.id} ${item.name} ${item.purpose} ${(item.tags || []).join(' ')} ${(item.table_names || []).join(' ')} ${item.sql_text || ''}`.toLowerCase().includes(query));
  });
  if (!items.length) rows.append(make('p', 'empty-state', '没有符合条件的 SQL 资产'));
  items.forEach(item => {
    const card = make('article', 'sql-asset-card');
    const checkLabel = make('label', 'row-check');
    const check = document.createElement('input'); check.type = 'checkbox'; check.checked = state.selectedSql.has(item.id);
    check.addEventListener('click', event => event.stopPropagation());
    check.addEventListener('change', () => { check.checked ? state.selectedSql.add(item.id) : state.selectedSql.delete(item.id); updateBatchButtons(); });
    checkLabel.append(check);
    const meta = make('div', 'sql-asset-meta');
    const head = make('header');
    head.append(make('strong', '', item.name));
    meta.append(head);
    meta.append(make('p', 'sql-asset-purpose', item.purpose || '暂无用途说明'));
    if ((item.tags || []).length || (item.table_names || []).length) {
      const tags = make('div', 'sql-tags');
      (item.tags || []).slice(0, 4).forEach(tag => tags.append(make('i', '', tag)));
      (item.table_names || []).slice(0, 2).forEach(table => tags.append(make('i', 'is-table', table)));
      meta.append(tags);
    }
    const side = make('div', 'sql-asset-side');
    const status = sqlStatus[item.status] || [item.status, 'waiting'];
    side.append(
      make('span', `status ${status[1]}`, status[0]),
      make('span', '', item.current_version || 'v1.0'),
      make('span', '', `${formatDate(item.updated_at).slice(0, 10)} · 复用 ${item.reuse_count || 0}`),
    );
    const previewSource = String(item.sql_text || '')
      .replace(/\r\n/g, '\n')
      .split('\n')
      .filter(line => line.trim())
      .slice(0, 6)
      .join('\n') || '-- 暂无 SQL 文本';
    const preview = make('pre', 'sql-preview');
    const chrome = make('div', 'sql-preview-chrome');
    chrome.append(make('span', ''), make('span', ''), make('span', ''), make('em', '', item.id || 'query.sql'));
    const code = make('code');
    code.innerHTML = highlightSql(previewSource);
    preview.append(chrome, code);
    card.append(checkLabel, meta, side, preview);
    card.addEventListener('click', () => openSqlDrawer(item.id));
    rows.append(card);
  });
}

function renderSqlCategoryFilters() {
  const container = $('#sqlCategoryFilters');
  const counts = new Map();
  state.sqlAssets.forEach(item => (item.tags || []).forEach(tag => counts.set(tag, (counts.get(tag) || 0) + 1)));
  const categories = [...counts.entries()].sort((left, right) => right[1] - left[1]).slice(0, 8);
  container.replaceChildren();
  [['all', '全部 SQL', state.sqlAssets.length], ...categories.map(([tag, count]) => [tag, tag, count])].forEach(([value, label, count]) => {
    const button = make('button', state.sqlCategory === value ? 'active' : ''); button.type = 'button';
    button.append(document.createTextNode(`${label} `), make('b', '', count));
    button.addEventListener('click', () => { state.sqlCategory = value; renderSqlAssets(); });
    container.append(button);
  });
}

async function refreshSqlAssets() {
  state.sqlAssets = await apiRequest('/api/sql-assets');
  state.selectedSql.clear(); renderSqlAssets(); renderTodaySqlHome(); updateBatchButtons();
}

async function deleteSql(id) {
  if (!id || !window.confirm('确认删除这个 SQL 资产吗？')) return;
  try { await apiRequest(`/api/sql-assets/${id}`, { method: 'DELETE' }); closeDrawer(); await refreshSqlAssets(); showToast('SQL 资产已删除'); }
  catch (error) { showToast(error.message); }
}

$('#newSqlButton').addEventListener('click', () => openSqlForm());
$('#sqlSearch').addEventListener('input', renderSqlAssets);
$$('.sql-status-filter').forEach(input => input.addEventListener('change', renderSqlAssets));
$('#editSqlButton').addEventListener('click', () => { closeDrawer(); openSqlForm(state.currentSql); });
$('#deleteSqlButton').addEventListener('click', () => deleteSql(state.currentSql?.id));
$('#sqlForm').addEventListener('submit', async event => {
  event.preventDefault();
  const id = $('#sqlId').value;
  const payload = {
    name: $('#sqlName').value.trim(), current_version: $('#sqlCurrentVersion').value.trim() || 'v1.0', status: $('#sqlStatus').value,
    purpose: $('#sqlPurpose').value.trim(), tags: splitValues($('#sqlTags').value), table_names: splitValues($('#sqlTables').value),
    related_project_id: $('#sqlProject').value.trim() || null, validation_note: $('#sqlValidationNote').value.trim(), sql_text: $('#sqlText').value,
  };
  try {
    if (state.apiAvailable && payload.sql_text.trim()) {
      const check = await apiRequest('/api/sql-assets/sensitive-check', { method: 'POST', body: JSON.stringify({ sql_text: payload.sql_text }) });
      if (check.count > 0 && !window.confirm(`检测到 ${check.count} 处疑似敏感信息，确认仍要保存吗？`)) return;
    }
    await apiRequest(id ? `/api/sql-assets/${id}` : '/api/sql-assets', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) });
    closeModal($('#sqlModal')); await refreshSqlAssets(); showToast(id ? 'SQL 资产已更新' : 'SQL 资产已创建');
  } catch (error) { showToast(error.message); }
});

$('#sqlVersionForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (!state.currentSql) return;
  const payload = {
    version: $('#versionName').value.trim(),
    validation_status: $('#versionStatus').value,
    change_summary: $('#versionSummary').value.trim(),
    sql_text: $('#versionSqlText').value,
  };
  try {
    await apiRequest(`/api/sql-assets/${state.currentSql.id}/versions`, { method: 'POST', body: JSON.stringify(payload) });
    closeModal($('#sqlVersionModal')); await refreshSqlAssets();
    const refreshed = await apiRequest(`/api/sql-assets/${state.currentSql.id}`);
    await openSqlDrawer(refreshed); showToast(`版本 ${payload.version} 已创建`);
  } catch (error) { showToast(error.message); }
});

async function batchSql(path, success) {
  const ids = [...state.selectedSql]; if (!ids.length) return;
  try { await apiRequest(path, { method: 'POST', body: JSON.stringify({ ids, ...(path.endsWith('status') ? { status: 'validated' } : {}) }) }); await refreshSqlAssets(); showToast(success); }
  catch (error) { showToast(error.message); }
}
$('#sqlBatchValidate').addEventListener('click', () => batchSql('/api/sql-assets/batch-status', '所选 SQL 已标记为已验证'));
$('#sqlBatchDelete').addEventListener('click', () => { if (window.confirm(`确认删除所选 ${state.selectedSql.size} 个 SQL 资产吗？`)) batchSql('/api/sql-assets/batch-delete', '所选 SQL 已删除'); });

const procedureStatusNames = { draft: '草稿', testing: '测试中', active: '生产启用', paused: '已暂停', archived: '已归档' };
function renderProcedures() {
  const rows = $('#procedureRows'); rows.replaceChildren();
  const query = $('#procedureSearch').value.trim().toLowerCase();
  const items = state.procedures.filter(item => (state.procedureStatus === 'all' || item.status === state.procedureStatus) && (!query || `${item.name} ${item.database_name} ${item.schema_name} ${item.purpose} ${(item.tags || []).join(' ')}`.toLowerCase().includes(query)));
  items.forEach(item => {
    const row = make('button', 'data-list-row'); row.type = 'button';
    const title = make('span'); title.append(make('strong', '', item.name), make('small', '', `${item.id} · ${item.purpose || '暂无用途说明'}`));
    row.append(title, make('span', '', [item.database_name, item.schema_name].filter(Boolean).join(' / ') || '未设置'), make('span', '', item.current_version), make('span', '', item.owner || '未设置'), make('span', '', item.related_project_id || '未关联'), make('em', `status ${item.status === 'active' ? 'done' : item.status === 'testing' ? 'working' : 'waiting'}`, procedureStatusNames[item.status] || item.status));
    row.addEventListener('click', () => openProcedureForm(item.id)); rows.append(row);
  });
  if (!items.length) rows.append(make('p', 'empty-state', '没有符合条件的存储过程资产'));
  const metrics = $$('#procedureSummary strong'); [state.procedures.length, state.procedures.filter(x => x.status === 'active').length, state.procedures.filter(x => x.status === 'testing').length, state.procedures.filter(x => x.status === 'draft').length].forEach((value, index) => { metrics[index].textContent = value; });
}

function renderProcedureLifecycle(item) {
  const versions = $('#procedureVersionList'); versions.replaceChildren();
  (item.versions || []).forEach((version, index) => { const row = make('div'); const copy = make('span'); copy.append(make('strong', '', version.version), make('small', '', version.change_summary || '未填写变更说明')); row.append(make('time', '', formatDate(version.created_at).slice(0, 10)), copy); if (!index) row.append(make('em', '', '当前')); versions.append(row); });
  const deployments = $('#procedureDeploymentList'); deployments.replaceChildren();
  const environmentNames = { development: '开发', testing: '测试', production: '生产' };
  (item.deployments || []).forEach(deployment => { const row = make('div'); const copy = make('span'); copy.append(make('strong', '', `${environmentNames[deployment.environment] || deployment.environment} · ${deployment.version}`), make('small', '', `${deployment.validation_result || deployment.notes || '未填写验证结果'}${deployment.rollback_executed ? ' · 已回滚' : ''}`)); row.append(make('time', '', formatDate(deployment.deployed_at || deployment.created_at)), copy, make('em', '', deployment.status)); deployments.append(row); });
  if (!(item.deployments || []).length) deployments.append(make('p', 'empty-state', '暂无环境发布记录'));
}

async function openProcedureForm(id = null) {
  let item = null; if (id) { try { item = await apiRequest(`/api/procedures/${id}`); } catch (error) { showToast(error.message); return; } }
  $('#procedureForm').reset(); $('#procedureId').value = item?.id || ''; $('#procedureModalTitle').textContent = item ? '存储过程详情与维护' : '新建存储过程';
  $('#procedureName').value = item?.name || ''; $('#procedureDatabase').value = item?.database_name || ''; $('#procedureSchema').value = item?.schema_name || ''; $('#procedureVersion').value = item?.current_version || 'v1.0'; $('#procedureStatus').value = item?.status || 'draft'; $('#procedureOwner').value = item?.owner || ''; fillProjectSelect($('#procedureProject'), item?.related_project_id || ''); $('#procedureTags').value = (item?.tags || []).join(', '); $('#procedurePurpose').value = item?.purpose || ''; $('#procedureDefinition').value = item?.definition_text || ''; $('#procedureRollback').value = item?.rollback_text || ''; $('#procedureChangeSummary').value = '';
  $('#procedureLifecycle').hidden = !item; $('#deleteProcedureButton').hidden = !item; if (item) renderProcedureLifecycle(item); openModal($('#procedureModal'));
}
async function refreshProcedures() { state.procedures = await apiRequest('/api/procedures'); renderProcedures(); }
$('#newProcedureButton').addEventListener('click', () => openProcedureForm()); $('#procedureSearch').addEventListener('input', renderProcedures);
$$('#procedureStatusFilters button').forEach(button => button.addEventListener('click', () => { state.procedureStatus = button.dataset.status; $$('#procedureStatusFilters button').forEach(item => item.classList.toggle('active', item === button)); renderProcedures(); }));
$('#procedureForm').addEventListener('submit', async event => {
  event.preventDefault(); const id = $('#procedureId').value; const payload = { name: $('#procedureName').value.trim(), database_name: $('#procedureDatabase').value.trim(), schema_name: $('#procedureSchema').value.trim(), purpose: $('#procedurePurpose').value.trim(), status: $('#procedureStatus').value, current_version: $('#procedureVersion').value.trim() || 'v1.0', owner: $('#procedureOwner').value.trim(), tags: splitValues($('#procedureTags').value), definition_text: $('#procedureDefinition').value, rollback_text: $('#procedureRollback').value, related_project_id: $('#procedureProject').value.trim() || null, change_summary: $('#procedureChangeSummary').value.trim() || (id ? '更新过程定义' : '创建存储过程资产') };
  try { const saved = await apiRequest(id ? `/api/procedures/${id}` : '/api/procedures', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) }); await refreshProcedures(); if (id) await openProcedureForm(saved.id); else closeModal($('#procedureModal')); showToast(id ? '存储过程已更新' : '存储过程已创建'); } catch (error) { showToast(error.message); }
});
$('#saveDeploymentButton').addEventListener('click', async () => { const id = $('#procedureId').value; if (!id) return; const payload = { version: $('#procedureVersion').value.trim(), environment: $('#deploymentEnvironment').value, status: $('#deploymentStatus').value, deployed_at: $('#deploymentAt').value || null, validation_result: $('#deploymentValidation').value.trim(), rollback_executed: $('#deploymentRollback').checked, notes: $('#deploymentNotes').value.trim() }; try { await apiRequest(`/api/procedures/${id}/deployments`, { method: 'POST', body: JSON.stringify(payload) }); await openProcedureForm(id); showToast('环境发布记录已保存'); } catch (error) { showToast(error.message); } });
$('#deleteProcedureButton').addEventListener('click', async () => { const id = $('#procedureId').value; if (!id || !window.confirm('确认删除该存储过程及其版本、发布记录吗？')) return; try { await apiRequest(`/api/procedures/${id}`, { method: 'DELETE' }); closeModal($('#procedureModal')); await refreshProcedures(); showToast('存储过程已删除'); } catch (error) { showToast(error.message); } });

$$('[data-model-tab]').forEach(button => button.addEventListener('click', () => {
  $$('[data-model-tab]').forEach(item => item.classList.toggle('active', item === button));
  $$('.model-tab').forEach(tab => tab.classList.toggle('active', tab.id === `model-tab-${button.dataset.modelTab}`));
}));
function renderModelCards() {
  // 独立模型页已并入台账；保留函数供 refreshModels 调用。
  const normal = state.models.filter(model => model.status === 'normal').length;
  if ($('#modelHealthSummary')) $('#modelHealthSummary').textContent = `${normal} / ${state.models.length} 模型运行正常`;
  if ($('#modelHitSummary')) $('#modelHitSummary').textContent = state.models.reduce((sum, model) => sum + (model.hit_count || 0), 0);
  if ($('#modelPendingSummary')) $('#modelPendingSummary').textContent = state.models.reduce((sum, model) => sum + (model.pending_review_count || 0), 0);
  if ($('#modelUpdateSummary')) $('#modelUpdateSummary').textContent = state.models.filter(model => model.status === 'update_due').length;
  const lastRun = state.models.map(model => model.last_run_at).filter(Boolean).sort().at(-1);
  if ($('#modelLastRun')) $('#modelLastRun').textContent = lastRun ? `最近运行：${formatDate(lastRun)}` : '尚无运行记录';
}

async function selectModel(model) {
  if (!model?.id) return;
  try { model = await apiRequest(`/api/models/${model.id}`); } catch (_) {}
  state.currentModel = model;
  renderModelCards();
  const detail = $('#ledgerModelDetail');
  if (detail) detail.hidden = false;
  if ($('#modelDetailCode')) $('#modelDetailCode').textContent = `${model.id} / VERSION ${model.current_version}`;
  if ($('#modelDetailName')) $('#modelDetailName').textContent = model.name;
  if ($('#modelDetailPurpose')) $('#modelDetailPurpose').textContent = model.purpose || '暂无用途说明';
  const rules = $('#modelRuleList');
  if (rules) {
    rules.replaceChildren();
    (model.rule_definitions || []).forEach(rule => {
      const row = make('div'); const copy = make('span');
      copy.append(make('strong', '', rule.name), make('small', '', rule.description || '规则说明待补充'));
      row.append(make('b', '', rule.id), copy, make('em', '', '规则')); rules.append(row);
    });
    if (!(model.rule_definitions || []).length) rules.append(make('p', 'empty-state', '暂无规则定义'));
  }
  const deps = $('#modelDependencies');
  if (deps) {
    deps.replaceChildren();
    (model.dependency_ids || []).forEach((dependency, index, items) => {
      deps.append(make('span', '', dependency)); if (index < items.length - 1) deps.append(make('i', '', '→'));
    });
    if ((model.dependency_ids || []).length) { deps.append(make('i', '', '→'), make('strong', '', model.id)); }
    else deps.append(make('span', '', '暂无依赖对象'));
  }
  renderModelSteps(model);
  renderModelVersions(model);
  try { renderModelRuns(await apiRequest(`/api/models/${model.id}/runs`)); }
  catch (error) { showToast(error.message); }
  $$('#ledgerModelList .soft-ledger-model-card').forEach(card => {
    card.classList.toggle('active', card.dataset.modelId === model.id);
  });
  if (state.ledgerDetail?.relations) {
    const relation = state.ledgerDetail.relations.find(item => item.entity_type === 'model' && item.entity_id === model.id);
    state.ledgerModelRelationId = relation?.id || null;
  }
}

function renderModelSteps(model) {
  const list = $('#modelStepList'); list.replaceChildren();
  (model.update_steps || []).forEach((step, index) => {
    const label = make('label'); const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = step.done;
    const copy = make('span'); copy.append(make('strong', '', step.title), make('small', '', step.description || '未填写步骤说明'));
    checkbox.addEventListener('change', async () => {
      const steps = (model.update_steps || []).map((item, itemIndex) => ({ ...item, done: itemIndex === index ? checkbox.checked : item.done }));
      try { await apiRequest(`/api/models/${model.id}`, { method: 'PATCH', body: JSON.stringify({ update_steps: steps }) }); model.update_steps = steps; showToast('更新步骤已保存'); }
      catch (error) { checkbox.checked = !checkbox.checked; showToast(error.message); }
    });
    label.append(checkbox, copy); list.append(label);
  });
  if (!(model.update_steps || []).length) list.append(make('p', 'empty-state', '暂无更新步骤，可在编辑模型时添加。'));
}

function renderModelVersions(model) {
  const list = $('#modelVersionList'); list.replaceChildren();
  (model.versions || []).forEach((version, index) => {
    const row = make('div'); const copy = make('span');
    copy.append(make('strong', '', version.version), make('small', '', version.change_summary || '未填写变更说明'));
    row.append(make('time', '', formatDate(version.created_at).slice(0, 10)), copy);
    if (index === 0) row.append(make('em', '', '当前'));
    list.append(row);
  });
  if (!(model.versions || []).length) list.append(make('p', 'empty-state', '暂无版本记录'));
}

function openModelForm(model = null) {
  $('#modelForm').reset(); $('#modelId').value = model?.id || '';
  $('#modelModalTitle').textContent = model ? '编辑监测模型' : '新建监测模型';
  $('#modelName').value = model?.name || ''; $('#modelVersion').value = model?.current_version || 'v1.0';
  $('#modelStatus').value = model?.status || 'normal'; $('#modelSchedule').value = model?.schedule || '';
  $('#modelPurpose').value = model?.purpose || '';
  bindSqlPicker('modelSqlIds', 'modelSqlChips', 'modelSqlAdd');
  setSqlPicker('modelSqlIds', 'modelSqlChips', 'modelSqlAdd', model?.related_sql_ids || []);
  $('#modelDependenciesInput').value = (model?.dependency_ids || []).join(', ');
  $('#modelRules').value = (model?.rule_definitions || []).map(rule => `${rule.name || rule.id || ''} | ${rule.description || ''}`).join('\n');
  $('#modelSteps').value = (model?.update_steps || []).map(step => `${step.title} | ${step.description || ''} | ${step.done ? '完成' : '未完成'}`).join('\n');
  $('#modelChangeSummary').value = ''; openModal($('#modelModal'));
}

function parseModelLines(value, type) {
  return value.split(/\r?\n/).map(line => line.trim()).filter(Boolean).map((line, index) => {
    const parts = line.split('|').map(item => item.trim());
    if (type === 'rule') return { id: `R-${String(index + 1).padStart(2, '0')}`, name: parts[0], description: parts[1] || '' };
    return { title: parts[0], description: parts[1] || '', done: /^(完成|done|true|是)$/i.test(parts[2] || '') };
  });
}

async function refreshModels(selectedId = null) {
  state.models = await apiRequest('/api/models');
  renderModelCards();
  renderTodayModelsHome();
  updateNavCounts();
  const selected = state.models.find(model => model.id === selectedId) || (state.currentModel && state.models.find(model => model.id === state.currentModel.id));
  if (selected && $('#ledgerModelDetail') && !$('#ledgerModelDetail').hidden) await selectModel(selected);
  else if (!selected) state.currentModel = null;
}

async function bindModelToCurrentProject(modelId, note = '台账绑定监测模型') {
  if (!state.currentProject?.id || !modelId) return;
  const exists = (state.ledgerDetail?.relations || []).some(item => item.entity_type === 'model' && item.entity_id === modelId);
  if (exists) return;
  await apiRequest(`/api/projects/${state.currentProject.id}/relations`, {
    method: 'POST',
    body: JSON.stringify({
      entity_type: 'model',
      entity_id: modelId,
      relation_type: 'dependency',
      note,
    }),
  });
}

$('#newModelButton')?.addEventListener('click', () => openModelForm());
$('#editModelButton')?.addEventListener('click', () => state.currentModel && openModelForm(state.currentModel));
$('#deleteModelButton')?.addEventListener('click', async () => {
  if (!state.currentModel || !window.confirm(`确认删除模型“${state.currentModel.name}”及其运行、版本记录吗？`)) return;
  try {
    await apiRequest(`/api/models/${state.currentModel.id}`, { method: 'DELETE' });
    state.currentModel = null;
    if ($('#ledgerModelDetail')) $('#ledgerModelDetail').hidden = true;
    await refreshModels();
    if (state.currentProject) await openProjectRelations(state.currentProject);
    showToast('监测模型已删除');
  } catch (error) { showToast(error.message); }
});
$('#unbindLedgerModelButton')?.addEventListener('click', async () => {
  if (!state.currentProject || !state.currentModel) return;
  const relationId = state.ledgerModelRelationId
    || (state.ledgerDetail?.relations || []).find(item => item.entity_type === 'model' && item.entity_id === state.currentModel.id)?.id;
  if (!relationId) { showToast('未找到绑定关系'); return; }
  if (!window.confirm(`确认解除监管项与模型“${state.currentModel.name}”的绑定吗？模型本身不会删除。`)) return;
  try {
    await apiRequest(`/api/projects/${state.currentProject.id}/relations/${relationId}`, { method: 'DELETE' });
    state.currentModel = null;
    state.ledgerModelRelationId = null;
    if ($('#ledgerModelDetail')) $('#ledgerModelDetail').hidden = true;
    await refreshProjects();
    await openProjectRelations(state.currentProject);
    setLedgerDetailTab('models');
    showToast('已解除模型绑定');
  } catch (error) { showToast(error.message); }
});
$('#bindExistingModelButton')?.addEventListener('click', async () => {
  if (!state.currentProject) return;
  const linkedIds = new Set((state.ledgerDetail?.relations || []).filter(item => item.entity_type === 'model').map(item => item.entity_id));
  const candidates = (state.models || []).filter(model => !linkedIds.has(model.id));
  if (!candidates.length) { showToast('没有可绑定的未关联模型，可先新建'); return; }
  const pick = window.prompt(`输入要绑定的模型编号：\n${candidates.map(item => `${item.id} ${item.name}`).join('\n')}`, candidates[0].id);
  if (!pick) return;
  try {
    await bindModelToCurrentProject(pick.trim());
    await refreshProjects();
    await openProjectRelations(state.currentProject);
    setLedgerDetailTab('models');
    const model = state.models.find(item => item.id === pick.trim());
    if (model) await selectModel(model);
    showToast('模型已绑定到监管项');
  } catch (error) { showToast(error.message); }
});
$('#modelForm').addEventListener('submit', async event => {
  event.preventDefault(); const id = $('#modelId').value;
  const payload = {
    name: $('#modelName').value.trim(), purpose: $('#modelPurpose').value.trim(), status: $('#modelStatus').value,
    schedule: $('#modelSchedule').value.trim(), current_version: $('#modelVersion').value.trim() || 'v1.0',
    rule_definitions: parseModelLines($('#modelRules').value, 'rule'), dependency_ids: splitValues($('#modelDependenciesInput').value),
    related_sql_ids: splitValues($('#modelSqlIds').value), update_steps: parseModelLines($('#modelSteps').value, 'step'),
    change_summary: $('#modelChangeSummary').value.trim() || (id ? '更新模型配置' : '创建监测模型'),
  };
  try {
    const saved = await apiRequest(id ? `/api/models/${id}` : '/api/models', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) });
    closeModal($('#modelModal'));
    if (!id && state.currentProject) {
      try { await bindModelToCurrentProject(saved.id, '新建模型并绑定台账'); } catch (_) {}
    }
    await refreshModels(saved.id);
    await refreshProjects();
    if (state.currentProject) {
      await openProjectRelations(state.currentProject);
      setLedgerDetailTab('models');
      await selectModel(saved);
    }
    showToast(id ? '监测模型已更新' : '监测模型已创建并绑定');
  } catch (error) { showToast(error.message); }
});

function renderModelRuns(runs) {
  const list = $('#modelRunList'); list.replaceChildren();
  if (!runs.length) { list.append(make('p', 'empty-state', '暂无运行记录')); return; }
  runs.forEach(run => {
    const row = make('div');
    const summary = make('span'); summary.append(make('strong', '', run.result_summary || '未填写运行摘要'), make('small', '', `扫描 ${run.scanned_count} · 命中 ${run.hit_count} · 已复核 ${run.reviewed_count}`));
    row.append(make('b', run.status === 'failed' ? 'run-failed' : '', run.status === 'success' ? '成功' : run.status), summary, make('em', '', formatDate(run.started_at)));
    list.append(row);
  });
}

function localDateTimeValue(date = new Date()) {
  const pad = value => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

$('#newModelRunButton').addEventListener('click', () => {
  if (!state.currentModel) return;
  $('#modelRunForm').reset(); $('#runModelId').value = state.currentModel.id;
  $('#runStartedAt').value = localDateTimeValue(); openModal($('#modelRunModal'));
});
$('#modelRunForm').addEventListener('submit', async event => {
  event.preventDefault();
  const modelId = $('#runModelId').value;
  const payload = {
    started_at: $('#runStartedAt').value, finished_at: $('#runFinishedAt').value || null,
    status: $('#runStatus').value, scanned_count: Number($('#runScanned').value || 0),
    hit_count: Number($('#runHits').value || 0), reviewed_count: Number($('#runReviewed').value || 0),
    result_summary: $('#runSummary').value.trim(),
  };
  try {
    await apiRequest(`/api/models/${modelId}/runs`, { method: 'POST', body: JSON.stringify(payload) });
    state.models = await apiRequest('/api/models');
    const model = state.models.find(item => item.id === modelId); closeModal($('#modelRunModal'));
    await selectModel(model); showToast('模型运行记录已保存');
  } catch (error) { showToast(error.message); }
});

const LEDGER_CATEGORY_ORDER = ['员工监管类', '经销商监管类', '合作商监管类', 'AI助力管理类'];

async function refreshProjects() {
  state.projects = await apiRequest('/api/projects');
  renderProjects();
  renderTodayProjects();
}

function renderLedgerOverview() {
  const all = state.projects || [];
  const active = all.filter(item => item.status === 'active').length;
  const modelBound = all.filter(item => (item.model_count || 0) > 0).length;
  const attention = all.reduce((sum, item) => sum + (item.model_attention || 0), 0);
  const pending = all.reduce((sum, item) => sum + (item.pending_steps || 0), 0);
  if ($('#ledgerTotalCount')) $('#ledgerTotalCount').textContent = String(all.length);
  if ($('#ledgerActiveCount')) $('#ledgerActiveCount').textContent = String(active);
  if ($('#ledgerModelCount')) $('#ledgerModelCount').textContent = String(modelBound);
  if ($('#ledgerAttentionCount')) $('#ledgerAttentionCount').textContent = String(attention);
  if ($('#ledgerPendingSteps')) $('#ledgerPendingSteps').textContent = String(pending);
}

function modelStatusLabel(status) {
  return ({
    normal: ['运行正常', 'done'],
    update_due: ['待更新', 'waiting'],
    paused: ['已暂停', 'waiting'],
    archived: ['已归档', 'waiting'],
  })[status] || [status || '未知', 'waiting'];
}

function renderProjects() {
  const board = $('#projectBoard');
  if (!board) return;
  board.replaceChildren();
  renderLedgerOverview();
  const items = filteredLedgerProjects();
  const hint = $('#ledgerResultHint');
  if (hint) hint.textContent = `${items.length} 项`;
  if (!items.length) {
    board.append(make('p', 'empty-state', state.projects.length
      ? '当前筛选下没有监管项。'
      : '台账为空。可点击「新增监管项」补录，或确认后端种子已写入。'));
    return;
  }
  const groups = new Map();
  items.forEach(project => {
    const key = project.category || '其他';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(project);
  });
  const orderedKeys = [
    ...LEDGER_CATEGORY_ORDER.filter(key => groups.has(key)),
    ...[...groups.keys()].filter(key => !LEDGER_CATEGORY_ORDER.includes(key)),
  ];
  orderedKeys.forEach(category => {
    const section = make('section', 'soft-ledger-section');
    const title = make('div', 'soft-ledger-section-head');
    title.append(make('h2', '', category), make('span', '', `${groups.get(category).length} 项`));
    const grid = make('div', 'soft-ledger-grid');
    groups.get(category).forEach(project => {
      const card = make('article', 'soft-ledger-card');
      if (project.model_attention) card.classList.add('needs-attention');
      card.tabIndex = 0;
      card.setAttribute('role', 'button');
      card.setAttribute('aria-label', `查看监管项 ${project.name}`);
      const status = ledgerStatusLabel(project.status);
      const header = make('header');
      header.append(
        make('span', 'soft-ledger-cycle', ledgerCycleLabel(project.monitor_cycle)),
        make('em', `status ${status[1]}`, status[0]),
      );
      const models = project.linked_models || [];
      if (models.length) {
        const chip = make('div', 'soft-ledger-model-chip');
        const primary = models[0];
        const mStatus = modelStatusLabel(primary.status);
        chip.append(
          make('strong', '', primary.name || primary.id),
          make('em', `status ${mStatus[1]}`, mStatus[0]),
        );
        if (models.length > 1) chip.append(make('span', '', `+${models.length - 1}`));
        card.append(header, chip);
      } else {
        card.append(header);
      }
      const latest = project.latest_execution;
      const meta = make('div', 'project-meta soft-ledger-meta');
      [
        ['最近执行', latest ? `${ledgerExecLabel(latest.result)} · ${(latest.executed_at || '').slice(0, 10) || '—'}` : '尚未登记'],
        ['待办步骤', `${project.pending_steps || 0}`],
        ['监测模型', models.length ? `${models.length} 个` : '未绑定'],
      ].forEach(([label, value]) => {
        const item = make('span');
        item.append(make('small', '', label), document.createTextNode(value));
        meta.append(item);
      });
      const footer = make('footer');
      footer.append(make('span', '', '下一步'), make('strong', '', project.next_action || '待安排'));
      card.append(
        make('h3', '', project.name),
        make('p', '', project.goal || project.plan_detail || '暂未填写规划摘要。'),
        meta,
        footer,
      );
      card.addEventListener('click', () => openProjectRelations(project));
      card.addEventListener('keydown', event => { if (event.key === 'Enter') openProjectRelations(project); });
      grid.append(card);
    });
    section.append(title, grid);
    board.append(section);
  });
}

function setLedgerDetailTab(tab) {
  state.ledgerDetailTab = tab || 'overview';
  $$('#ledgerDetailTabs [data-ledger-tab]').forEach(button => {
    const active = button.dataset.ledgerTab === state.ledgerDetailTab;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', active ? 'true' : 'false');
  });
  $$('#projectRelationModal [data-ledger-panel]').forEach(panel => {
    panel.hidden = panel.dataset.ledgerPanel !== state.ledgerDetailTab;
  });
}

async function renderLedgerModels(models = []) {
  const list = $('#ledgerModelList');
  const detail = $('#ledgerModelDetail');
  if (!list) return;
  list.replaceChildren();
  if (!models.length) {
    if (detail) detail.hidden = true;
    state.currentModel = null;
    list.append(make('p', 'empty-state', '本监管项尚未绑定监测模型。可新建并绑定，或绑定已有模型。'));
    return;
  }
  models.forEach(model => {
    const card = make('button', 'soft-ledger-model-card');
    card.type = 'button';
    card.dataset.modelId = model.id;
    const status = modelStatusLabel(model.status);
    card.append(
      make('strong', '', model.name || model.id),
      make('small', '', `${model.id} · ${model.current_version || 'v1.0'} · 命中 ${model.hit_count || 0}`),
      make('em', `status ${status[1]}`, status[0]),
    );
    card.classList.toggle('active', state.currentModel?.id === model.id);
    card.addEventListener('click', () => selectModel(model));
    list.append(card);
  });
  const preferred = models.find(item => item.id === state.currentModel?.id) || models[0];
  if (preferred) await selectModel(preferred);
  else if (detail) detail.hidden = true;
}

async function openProjectRelations(project, preferredTab = null) {
  try {
    const data = await apiRequest(`/api/projects/${project.id}`);
    state.currentProject = data.project;
    state.ledgerDetail = data;
    $('#relationProjectId').value = data.project.id;
    $('#projectRelationTitle').textContent = data.project.name;
    renderProjectDetail(data);
    renderProjectRelations(data.relations || []);
    renderLedgerSteps(data.update_steps || []);
    renderLedgerExecutions(data.executions || []);
    await renderLedgerModels(data.models || data.project.linked_models || []);
    fillRelationEntityPick($('#relationEntityType')?.value || 'sql_asset');
    setLedgerDetailTab(preferredTab || state.ledgerDetailTab || 'overview');
    openModal($('#projectRelationModal'));
  } catch (error) { showToast(error.message); }
}

function renderProjectDetail(data) {
  const project = data.project;
  const summary = $('#projectDetailSummary');
  summary.replaceChildren();
  const latest = project.latest_execution;
  [
    ['分类', project.category || '—'],
    ['周期', ledgerCycleLabel(project.monitor_cycle)],
    ['监测模型', `${project.model_count || 0}`],
    ['待办步骤', `${project.pending_steps || 0}`],
    ['最近执行', latest ? ledgerExecLabel(latest.result) : '尚未登记'],
  ].forEach(([label, value]) => {
    const item = make('div');
    item.append(make('span', '', label), make('strong', '', String(value)));
    summary.append(item);
  });
  $('#projectName').value = project.name || '';
  $('#projectCategory').value = project.category || '员工监管类';
  $('#projectStatus').value = project.status || 'active';
  $('#projectCycle').value = project.monitor_cycle || '按需';
  $('#projectSortOrder').value = project.sort_order ?? 0;
  $('#projectCycleNote').value = project.cycle_note || '';
  $('#projectNextAction').value = project.next_action || '';
  $('#projectGoal').value = project.goal || '';
  $('#projectPlanDetail').value = project.plan_detail || '';
  $('#projectMonitorLogic').value = project.monitor_logic || '';
  $('#projectCodeNote').value = project.code_note || '';
  $('#projectCodeBackup').value = project.code_backup || '';
}

function renderLedgerSteps(steps) {
  const list = $('#ledgerStepList');
  if (!list) return;
  list.replaceChildren();
  if (!steps.length) {
    list.append(make('p', 'empty-state', '暂无更新步骤。添加后可勾选完成。'));
    return;
  }
  steps.forEach(step => {
    const row = make('div', `soft-ledger-step${step.status === 'done' ? ' is-done' : ''}`);
    const check = make('input');
    check.type = 'checkbox';
    check.checked = step.status === 'done';
    check.addEventListener('change', async () => {
      try {
        await apiRequest(`/api/projects/${state.currentProject.id}/steps/${step.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ status: check.checked ? 'done' : 'pending' }),
        });
        await openProjectRelations(state.currentProject);
        await refreshProjects();
        showToast(check.checked ? '步骤已完成' : '步骤已重开');
      } catch (error) { showToast(error.message); check.checked = !check.checked; }
    });
    const copy = make('div');
    copy.append(make('strong', '', step.title), make('p', '', step.detail || '无补充说明'));
    const remove = make('button', 'text-button', '删除');
    remove.type = 'button';
    remove.addEventListener('click', async () => {
      if (!window.confirm(`确认删除步骤“${step.title}”吗？`)) return;
      try {
        await apiRequest(`/api/projects/${state.currentProject.id}/steps/${step.id}`, { method: 'DELETE' });
        await openProjectRelations(state.currentProject);
        await refreshProjects();
        showToast('步骤已删除');
      } catch (error) { showToast(error.message); }
    });
    row.append(check, copy, remove);
    list.append(row);
  });
}

function renderLedgerExecutions(executions) {
  const list = $('#ledgerExecList');
  if (!list) return;
  list.replaceChildren();
  if (!executions.length) {
    list.append(make('p', 'empty-state', '暂无执行记录。完成一次监管后在此登记。'));
    return;
  }
  executions.forEach(item => {
    const row = make('article', 'soft-ledger-exec');
    const head = make('header');
    head.append(
      make('strong', '', ledgerExecLabel(item.result)),
      make('span', '', (item.executed_at || '').replace('T', ' ').slice(0, 16) || '—'),
    );
    row.append(head, make('p', '', item.summary || '无摘要'));
    if (item.evidence_note) row.append(make('small', '', item.evidence_note));
    const remove = make('button', 'text-button', '删除');
    remove.type = 'button';
    remove.addEventListener('click', async () => {
      if (!window.confirm('确认删除这条执行记录吗？')) return;
      try {
        await apiRequest(`/api/projects/${state.currentProject.id}/executions/${item.id}`, { method: 'DELETE' });
        await openProjectRelations(state.currentProject);
        await refreshProjects();
        showToast('执行记录已删除');
      } catch (error) { showToast(error.message); }
    });
    row.append(remove);
    list.append(row);
  });
}

$('#ledgerCategoryFilters')?.addEventListener('click', event => {
  const button = event.target.closest('[data-ledger-category]');
  if (!button) return;
  state.ledgerCategory = button.dataset.ledgerCategory || 'all';
  $$('#ledgerCategoryFilters [data-ledger-category]').forEach(item => {
    item.classList.toggle('active', item === button);
  });
  renderProjects();
});

$('#ledgerFocusFilters')?.addEventListener('click', event => {
  const button = event.target.closest('[data-ledger-focus]');
  if (!button) return;
  state.ledgerFocus = button.dataset.ledgerFocus || 'all';
  $$('#ledgerFocusFilters [data-ledger-focus]').forEach(item => {
    item.classList.toggle('active', item === button);
  });
  renderProjects();
});

$('#ledgerSearch')?.addEventListener('input', () => {
  state.ledgerQuery = $('#ledgerSearch').value || '';
  renderProjects();
});

$('#ledgerDetailTabs')?.addEventListener('click', event => {
  const button = event.target.closest('[data-ledger-tab]');
  if (!button) return;
  setLedgerDetailTab(button.dataset.ledgerTab);
});

$('#saveProjectButton')?.addEventListener('click', async () => {
  if (!state.currentProject) return;
  const payload = {
    name: $('#projectName').value.trim(),
    category: $('#projectCategory').value,
    status: $('#projectStatus').value,
    monitor_cycle: $('#projectCycle').value,
    sort_order: Number($('#projectSortOrder').value || 0),
    cycle_note: $('#projectCycleNote').value.trim(),
    next_action: $('#projectNextAction').value.trim(),
    goal: $('#projectGoal').value.trim(),
  };
  try {
    await apiRequest(`/api/projects/${state.currentProject.id}`, { method: 'PATCH', body: JSON.stringify(payload) });
    await refreshProjects();
    const project = state.projects.find(item => item.id === state.currentProject.id) || state.currentProject;
    await openProjectRelations(project);
    showToast('概览已保存');
  } catch (error) { showToast(error.message); }
});

$('#saveLedgerLogicButton')?.addEventListener('click', async () => {
  if (!state.currentProject) return;
  try {
    await apiRequest(`/api/projects/${state.currentProject.id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        plan_detail: $('#projectPlanDetail').value,
        monitor_logic: $('#projectMonitorLogic').value,
      }),
    });
    await refreshProjects();
    await openProjectRelations(state.currentProject);
    showToast('规划与监管逻辑已保存');
  } catch (error) { showToast(error.message); }
});

$('#saveLedgerCodeButton')?.addEventListener('click', async () => {
  if (!state.currentProject) return;
  try {
    await apiRequest(`/api/projects/${state.currentProject.id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        code_note: $('#projectCodeNote').value.trim(),
        code_backup: $('#projectCodeBackup').value,
      }),
    });
    await refreshProjects();
    await openProjectRelations(state.currentProject);
    showToast('代码备份已保存');
  } catch (error) { showToast(error.message); }
});

$('#copyLedgerCodeButton')?.addEventListener('click', async () => {
  const text = $('#projectCodeBackup')?.value || '';
  if (!text.trim()) { showToast('暂无代码可复制'); return; }
  try {
    await navigator.clipboard.writeText(text);
    showToast('代码已复制');
  } catch (_) { showToast('复制失败，请手动选择文本'); }
});

$('#ledgerStepForm')?.addEventListener('submit', async event => {
  event.preventDefault();
  if (!state.currentProject) return;
  const title = $('#ledgerStepTitle').value.trim();
  if (!title) return;
  try {
    await apiRequest(`/api/projects/${state.currentProject.id}/steps`, {
      method: 'POST',
      body: JSON.stringify({
        title,
        detail: $('#ledgerStepDetail').value.trim(),
        status: 'pending',
      }),
    });
    $('#ledgerStepForm').reset();
    await openProjectRelations(state.currentProject);
    await refreshProjects();
    showToast('步骤已添加');
  } catch (error) { showToast(error.message); }
});

$('#ledgerExecForm')?.addEventListener('submit', async event => {
  event.preventDefault();
  if (!state.currentProject) return;
  const executedAt = $('#ledgerExecAt').value;
  try {
    await apiRequest(`/api/projects/${state.currentProject.id}/executions`, {
      method: 'POST',
      body: JSON.stringify({
        executed_at: executedAt ? new Date(executedAt).toISOString() : null,
        result: $('#ledgerExecResult').value,
        summary: $('#ledgerExecSummary').value.trim(),
        evidence_note: $('#ledgerExecEvidence').value.trim(),
      }),
    });
    $('#ledgerExecForm').reset();
    await openProjectRelations(state.currentProject);
    await refreshProjects();
    showToast('执行记录已登记');
  } catch (error) { showToast(error.message); }
});

$('#newProjectButton')?.addEventListener('click', () => {
  $('#projectForm')?.reset();
  if ($('#newProjectCategory')) $('#newProjectCategory').value = state.ledgerCategory !== 'all' ? state.ledgerCategory : '员工监管类';
  if ($('#newProjectCycle')) $('#newProjectCycle').value = '按需';
  openModal($('#projectModal'));
});

$('#projectForm')?.addEventListener('submit', async event => {
  event.preventDefault();
  const payload = {
    name: $('#newProjectName').value.trim(),
    type: 'monitor',
    category: $('#newProjectCategory').value,
    monitor_cycle: $('#newProjectCycle').value,
    next_action: $('#newProjectNextAction').value.trim(),
    goal: $('#newProjectGoal').value.trim(),
  };
  try {
    const project = await apiRequest('/api/projects', { method: 'POST', body: JSON.stringify(payload) });
    closeModal($('#projectModal'));
    await refreshProjects();
    await openProjectRelations(project);
    showToast('监管项已加入台账');
  } catch (error) { showToast(error.message); }
});

$('#archiveProjectButton')?.addEventListener('click', async () => {
  if (!state.currentProject) return;
  try {
    await apiRequest(`/api/projects/${state.currentProject.id}`, { method: 'PATCH', body: JSON.stringify({ status: 'archived' }) });
    closeModal($('#projectRelationModal'));
    await refreshProjects();
    showToast('监管项已归档');
  } catch (error) { showToast(error.message); }
});

$('#deleteProjectButton')?.addEventListener('click', async () => {
  if (!state.currentProject || !window.confirm(`确认删除监管项“${state.currentProject.name}”吗？步骤、执行记录与关联将一并删除。`)) return;
  try {
    await apiRequest(`/api/projects/${state.currentProject.id}`, { method: 'DELETE' });
    closeModal($('#projectRelationModal'));
    await refreshProjects();
    showToast('监管项已删除');
  } catch (error) { showToast(error.message); }
});

function renderProjectRelations(relations) {
  const list = $('#projectRelationList');
  if (!list) return;
  list.replaceChildren();
  if (!relations.length) { list.append(make('p', 'empty-state', '暂无关联对象')); return; }
  const typeNames = { task: '任务', data_request: '请求', sql_asset: 'SQL', model: '模型', note: '记录' };
  relations.forEach(relation => {
    const row = make('div');
    const copy = make('span');
    copy.append(make('strong', '', relation.entity_label), make('small', '', `${relation.entity_id} · ${relation.note || relation.relation_type}`));
    const remove = make('button', '', '移除'); remove.type = 'button';
    remove.addEventListener('click', async event => {
      event.stopPropagation();
      if (!window.confirm(`确认移除与 ${relation.entity_id} 的关联吗？`)) return;
      try {
        await apiRequest(`/api/projects/${state.currentProject.id}/relations/${relation.id}`, { method: 'DELETE' });
        await refreshProjects();
        await openProjectRelations(state.currentProject);
        showToast('关联已移除');
      } catch (error) { showToast(error.message); }
    });
    if (relation.entity_type === 'model') {
      row.addEventListener('click', async () => {
        setLedgerDetailTab('models');
        const model = state.models.find(item => item.id === relation.entity_id) || { id: relation.entity_id, name: relation.entity_label };
        await selectModel(model);
      });
      row.style.cursor = 'pointer';
    }
    row.append(make('b', 'relation-badge', typeNames[relation.entity_type] || '对象'), copy, remove);
    list.append(row);
  });
}

function fillRelationEntityPick(entityType) {
  const pick = $('#relationEntityPick');
  const idInput = $('#relationEntityId');
  const pickLabel = $('#relationEntityPickLabel');
  const idLabel = $('#relationEntityIdLabel');
  if (!pick) return;
  pick.replaceChildren(make('option', '', '请选择…'));
  pick.querySelector('option').value = '';
  const sources = {
    sql_asset: (state.sqlAssets || []).map(item => [item.id, item.name || item.id]),
    model: (state.models || []).map(item => [item.id, item.name || item.id]),
    task: (state.focusTasks || state.tasks || []).map(item => [item.id, item.title || item.id]),
    data_request: (state.requests || []).map(item => [item.id, item.title || item.id]),
    note: (state.notes || []).map(item => [item.id, item.title || item.id]),
  };
  const options = sources[entityType] || [];
  options.forEach(([id, label]) => {
    const option = document.createElement('option');
    option.value = id;
    option.textContent = `${id} · ${label}`;
    pick.append(option);
  });
  const hasOptions = options.length > 0;
  if (pickLabel) pickLabel.hidden = !hasOptions;
  if (idLabel) idLabel.hidden = hasOptions;
  if (idInput && hasOptions) idInput.value = '';
}

$('#relationEntityType')?.addEventListener('change', () => {
  fillRelationEntityPick($('#relationEntityType').value);
});

$('#relationEntityPick')?.addEventListener('change', () => {
  if ($('#relationEntityId')) $('#relationEntityId').value = $('#relationEntityPick').value || '';
});

$('#ledgerRelationAddForm')?.addEventListener('submit', async event => {
  event.preventDefault();
  const projectId = $('#relationProjectId').value;
  const entityId = ($('#relationEntityPick')?.value || $('#relationEntityId')?.value || '').trim();
  if (!entityId) { showToast('请选择或填写关联对象'); return; }
  const payload = {
    entity_type: $('#relationEntityType').value,
    entity_id: entityId,
    relation_type: $('#relationType').value,
    note: $('#relationNote').value.trim(),
  };
  try {
    await apiRequest(`/api/projects/${projectId}/relations`, { method: 'POST', body: JSON.stringify(payload) });
    if ($('#relationEntityId')) $('#relationEntityId').value = '';
    if ($('#relationEntityPick')) $('#relationEntityPick').value = '';
    $('#relationNote').value = '';
    await refreshProjects();
    state.currentProject = state.projects.find(item => item.id === projectId) || state.currentProject;
    await openProjectRelations(state.currentProject, payload.entity_type === 'model' ? 'models' : null);
    showToast('关联已添加');
  } catch (error) { showToast(error.message); }
});

const entityNames = { task: '任务', data_request: '数据请求', sql_asset: 'SQL', procedure: '存储过程', model: '模型', project: '台账', generated_report: '报告', note: '记录' };
const entityIcons = { task: 'i-calendar', data_request: 'i-inbox', sql_asset: 'i-code', procedure: 'i-code', model: 'i-model', project: 'i-project', generated_report: 'i-note', note: 'i-note' };

async function openSearchResult(result) {
  closeCommand();
  if (result.entity_type === 'sql_asset') { showView('sql'); await openSqlDrawer(result.id); return; }
  if (result.entity_type === 'procedure') { showView('procedures'); await openProcedureForm(result.id); return; }
  if (result.entity_type === 'task') { showView('week'); openEntityDrawer('task', await apiRequest(`/api/tasks/${result.id}`)); return; }
  if (result.entity_type === 'model') {
    showView('projects');
    let detail = null;
    try { detail = await apiRequest(`/api/models/${result.id}`); } catch (_) {}
    const projectId = detail?.linked_project_id || detail?.linked_projects?.[0]?.id;
    const project = state.projects.find(item => item.id === projectId)
      || state.projects.find(item => (item.linked_models || []).some(model => model.id === result.id));
    if (project) {
      await openProjectRelations(project, 'models');
      const model = state.models.find(item => item.id === result.id) || detail || { id: result.id };
      await selectModel(model);
    } else {
      showToast('该模型尚未绑定台账，请先在监管项中绑定');
      state.ledgerFocus = 'all';
      renderProjects();
    }
    return;
  }
  if (result.entity_type === 'project') {
    showView('projects'); const project = state.projects.find(item => item.id === result.id); if (project) await openProjectRelations(project); return;
  }
  if (result.entity_type === 'data_request') {
    showView('requests'); const request = state.requests.find(item => item.id === result.id); if (request) openEntityDrawer('data_request', request); return;
  }
  if (result.entity_type === 'note') {
    showView('notes'); const note = state.notes.find(item => item.id === result.id); if (note) openEntityDrawer('note', note); return;
  }
  if (result.entity_type === 'generated_report') {
    showToast('报告助手已下线，历史报告仍可在数据导出中查看');
    return;
  }
  showView(result.view);
}

function makeSearchResult(result, compact = false) {
  const button = make('button', compact ? '' : 'unified-result'); button.type = 'button';
  const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); const use = document.createElementNS('http://www.w3.org/2000/svg', 'use'); use.setAttribute('href', `#${entityIcons[result.entity_type] || 'i-search'}`); icon.append(use);
  const copy = make('span'); copy.append(make('strong', '', result.title), make('small', '', `${result.id} · ${result.subtitle || '暂无摘要'}`));
  button.append(icon, copy, make('em', '', entityNames[result.entity_type] || result.entity_type));
  button.addEventListener('click', () => openSearchResult(result));
  return button;
}

function visibleSearchResults() {
  return state.searchType === 'all' ? state.searchResults : state.searchResults.filter(item => item.entity_type === state.searchType);
}

function renderGlobalSearch() {
  const list = $('#globalSearchResults'); list.replaceChildren();
  const visible = visibleSearchResults();
  state.searchSelection = Math.min(state.searchSelection, visible.length - 1);
  $('#globalSearchSummary').textContent = `找到 ${visible.length} 条结果 · ↑↓ 选择 · Enter 打开`;
  visible.forEach((result, index) => {
    const button = makeSearchResult(result);
    if (index === state.searchSelection) button.classList.add('is-selected');
    button.dataset.searchIndex = String(index);
    list.append(button);
  });
  if (!visible.length) list.append(make('p', 'empty-state', '没有匹配结果，请尝试编号、表名或更短的关键词。'));
}

function renderSearchHelpers() {
  const recent = $('#recentSearchList'); const saved = $('#savedSearchList');
  if (!recent || !saved) return;
  recent.replaceChildren();
  state.recentSearches.forEach(item => {
    const button = make('button', 'chip-button', item.query); button.type = 'button';
    button.addEventListener('click', () => {
      $('#globalSearchInput').value = item.query;
      if (item.types) {
        state.searchType = item.types.split(',')[0] || 'all';
        $$('[data-search-type]').forEach(node => node.classList.toggle('active', node.dataset.searchType === state.searchType));
      }
      performGlobalSearch(item.query);
    });
    recent.append(button);
  });
  if (!state.recentSearches.length) recent.append(make('p', 'empty-state', '暂无最近搜索'));

  saved.replaceChildren();
  state.savedSearches.forEach(item => {
    const row = make('div', 'saved-search-row');
    const open = make('button', 'chip-button', item.name); open.type = 'button';
    open.title = item.query;
    open.addEventListener('click', () => {
      $('#globalSearchInput').value = item.query;
      state.searchType = item.types || 'all';
      $$('[data-search-type]').forEach(node => node.classList.toggle('active', node.dataset.searchType === state.searchType));
      performGlobalSearch(item.query, item.types || '');
    });
    const remove = make('button', 'text-button danger-text', '删除'); remove.type = 'button';
    remove.addEventListener('click', async () => {
      try {
        await apiRequest(`/api/saved-searches/${item.id}`, { method: 'DELETE' });
        await refreshSearchHelpers();
        showToast('已删除保存的检索');
      } catch (error) { showToast(error.message); }
    });
    row.append(open, remove); saved.append(row);
  });
  if (!state.savedSearches.length) saved.append(make('p', 'empty-state', '暂无保存的检索'));
}

async function refreshSearchHelpers() {
  if (!state.apiAvailable) return;
  try {
    state.recentSearches = await apiRequest('/api/recent-searches');
    state.savedSearches = await apiRequest('/api/saved-searches');
    renderSearchHelpers();
  } catch (error) { showToast(error.message); }
}

async function performGlobalSearch(query = $('#globalSearchInput').value.trim(), types = '') {
  if (!query) {
    state.searchResults = [];
    state.searchSelection = -1;
    $('#globalSearchSummary').textContent = '输入关键词开始检索';
    $('#globalSearchResults').innerHTML = '<p class="empty-state">支持按业务编号、标题、说明、标签和 SQL 内容检索。可用 ↑↓ 选择结果，Enter 打开。</p>';
    return;
  }
  try {
    const typeQuery = types || (state.searchType !== 'all' ? state.searchType : '');
    const data = await apiRequest(`/api/search?q=${encodeURIComponent(query)}${typeQuery ? `&types=${encodeURIComponent(typeQuery)}` : ''}`);
    state.searchResults = data.results;
    state.searchSelection = data.results.length ? 0 : -1;
    renderGlobalSearch();
    refreshSearchHelpers();
  } catch (error) { showToast(error.message); }
}

$('#globalSearchForm').addEventListener('submit', event => { event.preventDefault(); performGlobalSearch(); });
$('#saveSearchButton').addEventListener('click', async () => {
  const query = $('#globalSearchInput').value.trim();
  if (!query) { showToast('请先输入检索词'); return; }
  const name = window.prompt('为当前检索条件命名', query.slice(0, 40));
  if (!name) return;
  try {
    await apiRequest('/api/saved-searches', { method: 'POST', body: JSON.stringify({ name: name.trim(), query, types: state.searchType === 'all' ? '' : state.searchType }) });
    await refreshSearchHelpers();
    showToast('检索条件已保存');
  } catch (error) { showToast(error.message); }
});
$('#clearRecentSearches').addEventListener('click', async () => {
  try {
    await apiRequest('/api/recent-searches', { method: 'DELETE' });
    await refreshSearchHelpers();
    showToast('最近搜索已清空');
  } catch (error) { showToast(error.message); }
});
$$('[data-search-type]').forEach(button => button.addEventListener('click', () => {
  $$('[data-search-type]').forEach(item => item.classList.toggle('active', item === button));
  state.searchType = button.dataset.searchType;
  state.searchSelection = 0;
  renderGlobalSearch();
}));
$('#globalSearchResults').addEventListener('keydown', event => {
  const visible = visibleSearchResults();
  if (!visible.length) return;
  if (event.key === 'ArrowDown') {
    event.preventDefault();
    state.searchSelection = (state.searchSelection + 1) % visible.length;
    renderGlobalSearch();
  } else if (event.key === 'ArrowUp') {
    event.preventDefault();
    state.searchSelection = (state.searchSelection - 1 + visible.length) % visible.length;
    renderGlobalSearch();
  } else if (event.key === 'Enter' && state.searchSelection >= 0) {
    event.preventDefault();
    openSearchResult(visible[state.searchSelection]);
  }
});
$('#globalSearchInput').addEventListener('keydown', event => {
  if (['ArrowDown', 'ArrowUp'].includes(event.key)) {
    event.preventDefault();
    $('#globalSearchResults').focus();
    if (state.searchSelection < 0 && visibleSearchResults().length) state.searchSelection = 0;
    renderGlobalSearch();
  }
});

const command = $('#command');
const commandInput = $('#commandInput');
const commandResults = $('#commandResults');
const commandDefaultHtml = commandResults.innerHTML;
let commandTimer;
function wireCommandPages() { $$('[data-command-view]', commandResults).forEach(button => button.addEventListener('click', () => { showView(button.dataset.commandView); closeCommand(); })); }
function openCommand() { command.classList.add('open'); command.setAttribute('aria-hidden', 'false'); commandResults.innerHTML = commandDefaultHtml; $('#commandShowAll').hidden = true; wireCommandPages(); setTimeout(() => commandInput.focus(), 20); }
function closeCommand() { command.classList.remove('open'); command.setAttribute('aria-hidden', 'true'); commandInput.value = ''; clearTimeout(commandTimer); }
$('#searchButton').addEventListener('click', openCommand);
command.addEventListener('click', event => { if (event.target === command) closeCommand(); });
commandInput.addEventListener('input', () => {
  clearTimeout(commandTimer); const query = commandInput.value.trim();
  if (!query) { commandResults.innerHTML = commandDefaultHtml; $('#commandShowAll').hidden = true; wireCommandPages(); return; }
  commandTimer = setTimeout(async () => {
    try {
      const data = await apiRequest(`/api/search?q=${encodeURIComponent(query)}`); commandResults.replaceChildren();
      commandResults.append(make('p', '', `检索结果 · ${data.total} 条`));
      data.results.slice(0, 6).forEach(result => commandResults.append(makeSearchResult(result, true)));
      if (!data.results.length) commandResults.append(make('p', 'empty-state', '没有匹配结果'));
      $('#commandShowAll').hidden = false;
    } catch (error) { showToast(error.message); }
  }, 220);
});
$('#commandShowAll').addEventListener('click', () => {
  const query = commandInput.value.trim(); closeCommand(); showView('search'); $('#globalSearchInput').value = query; performGlobalSearch(query);
});
wireCommandPages();

function downloadData(url) {
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = ''; document.body.append(anchor); anchor.click(); anchor.remove();
}

function formatBytes(size) {
  if (size < 1024) return `${size} B`;
  if (size < 1048576) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1048576).toFixed(1)} MB`;
}

const RESTORE_TABLE_OPTIONS = [
  ['tasks', '任务'], ['data_requests', '数据请求'], ['sql_assets', 'SQL 资产'], ['sql_versions', 'SQL 版本'],
  ['stored_procedures', '存储过程'], ['monitoring_models', '监测模型'], ['projects', '项目'],
  ['work_notes', '工作记录'], ['weekly_reports', '周报'], ['generated_reports', '模板报告'],
  ['navigation_items', '常用导航'], ['saved_searches', '保存的检索'],
];

function updateDataHealthSummary() {
  const settings = state.settings || {};
  const backups = state.backups || [];
  const ai = settings.ai || {};
  const calendar = settings.dingtalk_calendar || {};
  if ($('#dataStatBackups')) $('#dataStatBackups').textContent = String(backups.length || settings.backups?.count || 0);
  if ($('#dataStatAi')) {
    $('#dataStatAi').textContent = ai.ready ? '已就绪' : (ai.enabled ? '待完善' : '未配置');
  }
  if ($('#dataStatAccess')) {
    $('#dataStatAccess').textContent = settings.access_password_enabled ? '已启用' : '关闭';
  }
  if ($('#dataStatCalendar')) {
    const on = !!calendar.enabled && (
      (calendar.provider === 'ics' && calendar.ics_url)
      || ((calendar.provider || 'caldav') === 'caldav' && calendar.caldav_username)
    );
    $('#dataStatCalendar').textContent = on ? '已配置' : (calendar.enabled ? '待完善' : '关闭');
  }
}

function renderBackups() {
  const list = $('#backupList');
  if (!list) return;
  list.replaceChildren();
  state.backups.forEach((backup, index) => {
    const row = make('div', `backup-row${index === 0 ? ' is-latest' : ''}`);
    const mark = make('span', 'backup-mark', index === 0 ? '新' : '库');
    const copy = make('span', 'backup-copy');
    copy.append(
      make('strong', '', backup.name),
      make('small', '', `${formatBytes(backup.size)} · ${formatDate(backup.created_at)}`),
    );
    const actions = make('span', 'backup-actions');
    const download = make('button', 'secondary-button', '下载');
    download.type = 'button';
    download.addEventListener('click', () => downloadData(`/api/backups/${encodeURIComponent(backup.name)}/download`));
    const restoreTables = make('button', 'secondary-button', '按表恢复');
    restoreTables.type = 'button';
    restoreTables.addEventListener('click', () => openTableRestoreModal(backup.name));
    const restore = make('button', 'secondary-button danger-button', '整库恢复');
    restore.type = 'button';
    restore.addEventListener('click', async () => {
      if (!window.confirm(`确认整库恢复备份 ${backup.name} 吗？当前数据库会先自动备份。`)) return;
      try {
        await apiRequest(`/api/backups/${encodeURIComponent(backup.name)}/restore`, { method: 'POST' });
        showToast('数据库已恢复，正在重新载入');
        setTimeout(() => location.reload(), 700);
      } catch (error) { showToast(error.message); }
    });
    const remove = make('button', 'text-button danger-link', '删除');
    remove.type = 'button';
    remove.addEventListener('click', async () => {
      if (!window.confirm(`确认删除备份 ${backup.name} 吗？`)) return;
      try {
        await apiRequest(`/api/backups/${encodeURIComponent(backup.name)}`, { method: 'DELETE' });
        await refreshBackups();
        showToast('备份已删除');
      } catch (error) { showToast(error.message); }
    });
    actions.append(download, restoreTables, restore, remove);
    row.append(mark, copy, actions);
    list.append(row);
  });
  if (!state.backups.length) {
    list.append(make('p', 'empty-state', '还没有备份，建议在首次导入前创建一个。'));
  }
  updateDataHealthSummary();
}

function openTableRestoreModal(backupName) {
  $('#tableRestoreBackupName').value = backupName;
  $('#tableRestoreHint').textContent = `将从 ${backupName} 按所选表写回当前数据库。恢复前会自动创建安全备份。`;
  const box = $('#tableRestoreOptions'); box.replaceChildren();
  RESTORE_TABLE_OPTIONS.forEach(([value, label]) => {
    const item = make('label', 'table-restore-option');
    const input = document.createElement('input');
    input.type = 'checkbox'; input.value = value; input.name = 'restoreTable';
    item.append(input, document.createTextNode(` ${label}`));
    box.append(item);
  });
  openModal($('#tableRestoreModal'));
}

function isAiReady() {
  return !!state.settings?.ai?.ready;
}

function openAiSettings() {
  showView('data');
  window.setTimeout(() => {
    const panel = $('#aiSettingsPanel');
    if (panel) panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    $('#aiBaseUrl')?.focus();
  }, 80);
}

function renderAiStatus() {
  const ai = state.settings?.ai || {};
  const ready = !!ai.ready;
  const chip = $('#aiStatusChip');
  const chipLabel = $('#aiStatusChipLabel');
  if (chip) {
    chip.classList.toggle('is-ready', ready);
    chip.classList.toggle('is-off', !ready);
  }
  if (chipLabel) {
    chipLabel.textContent = ready
      ? `AI · ${ai.model || '已就绪'}`
      : (ai.enabled ? 'AI 配置不完整' : 'AI 未配置');
  }
  const foot = $('.sidebar-foot small');
  if (foot && state.apiAvailable) {
    foot.textContent = ready ? 'AI 已就绪' : 'AI 未启用或未配置';
  }
  const panel = $('#aiCapabilityPanel');
  if (panel) panel.classList.toggle('is-ready', ready);
  if ($('#aiCapabilityTitle')) {
    $('#aiCapabilityTitle').textContent = ready ? 'AI 已就绪' : 'AI 能力（本地规则可用）';
  }
  if ($('#aiCapabilityLead')) {
    $('#aiCapabilityLead').textContent = ready
      ? `当前模型 ${ai.model || '—'}，可用于记录整理与 SQL 说明。`
      : '尚未配置模型。可先用本地规则；点「去配置」填写兼容 OpenAI 的地址、模型与密钥。';
  }
  if ($('#aiCapabilityConfig')) {
    $('#aiCapabilityConfig').textContent = ready ? '管理配置' : '去配置';
  }
  if ($('#reportAiModeLabel')) {
    $('#reportAiModeLabel').textContent = ready ? 'AI 智能汇总' : '本地智能汇总';
  }
  const signal = $('#reportAiSignal');
  if (signal) {
    signal.classList.toggle('ok-signal', ready);
    signal.classList.toggle('risk-signal', !ready);
  }
  const polish = $('#polishReportButton');
  if (polish) {
    polish.disabled = !ready;
    polish.title = ready ? '用 AI 润色当前周报正文' : '请先在数据管理中配置并启用 AI';
  }
}

function fillAiSettingsForm(settings = state.settings) {
  const ai = settings?.ai || {};
  if ($('#aiEnabled')) $('#aiEnabled').checked = !!ai.enabled;
  if ($('#aiBaseUrl')) $('#aiBaseUrl').value = ai.base_url || '';
  if ($('#aiModel')) $('#aiModel').value = ai.model || '';
  if ($('#aiApiKey')) $('#aiApiKey').value = '';
  if ($('#aiIncludeSql')) $('#aiIncludeSql').checked = ai.include_sql_text !== false;
  if ($('#aiSettingsStatus')) {
    $('#aiSettingsStatus').textContent = ai.ready
      ? `AI 已就绪 · 模型 ${ai.model}${ai.has_api_key ? ` · Key ${ai.api_key_masked}` : ''}`
      : (ai.enabled ? '已启用但配置不完整，请填写地址、模型和密钥。' : 'AI 已关闭，智能整理将使用本地规则。');
  }
  renderAiStatus();
  if ($('#accessPasswordStatus')) {
    const days = settings?.session_days || 14;
    $('#accessPasswordStatus').textContent = settings?.access_password_enabled
      ? `已启用访问密码；解锁会话约 ${days} 天，修改密码会使旧会话立即失效。`
      : '当前未启用访问密码。';
  }
  const backupHint = $('#backupVisibilityHint');
  if (backupHint) {
    const info = settings?.backups;
    if (info?.latest) {
      backupHint.textContent = `当前 ${info.count} 份备份 · 最近 ${info.latest.name}（${formatDate(info.latest.created_at)}）· 保留上限 ${info.retention}`;
    } else {
      backupHint.textContent = '还没有备份文件，建议先手动创建一份。';
    }
  }
  const secretHint = $('#secretWarningHint');
  if (secretHint) {
    if (settings?.secret_warning) {
      secretHint.hidden = false;
      secretHint.textContent = settings.secret_warning;
    } else {
      secretHint.hidden = true;
      secretHint.textContent = '';
    }
  }
  const calendar = settings?.dingtalk_calendar || {};
  if ($('#calendarEnabled')) $('#calendarEnabled').checked = !!calendar.enabled;
  if ($('#calendarProvider')) $('#calendarProvider').value = calendar.provider === 'ics' ? 'ics' : 'caldav';
  if ($('#calendarIcsUrl')) $('#calendarIcsUrl').value = calendar.ics_url || '';
  if ($('#calendarCaldavUrl')) $('#calendarCaldavUrl').value = calendar.caldav_url || 'https://calendar.dingtalk.com';
  if ($('#calendarCaldavUsername')) $('#calendarCaldavUsername').value = calendar.caldav_username || '';
  if ($('#calendarCaldavPath')) $('#calendarCaldavPath').value = calendar.caldav_path || '';
  if ($('#calendarCaldavPassword')) {
    $('#calendarCaldavPassword').value = '';
    $('#calendarCaldavPassword').placeholder = calendar.has_caldav_password ? '已保存，留空表示不修改' : '钉钉生成的专用密码';
  }
  updateCalendarProviderFields();
  if ($('#calendarSettingsStatus')) {
    if ((calendar.provider || 'caldav') === 'caldav') {
      $('#calendarSettingsStatus').textContent = calendar.caldav_username
        ? `已配置 CalDAV：${calendar.caldav_username}${calendar.has_caldav_password ? ' · 密码已保存' : ' · 尚未保存密码'}`
        : '配置钉钉 CalDAV 账号后可同步到本地日历事件。';
    } else {
      $('#calendarSettingsStatus').textContent = calendar.ics_url
        ? `已配置 ICS：${calendar.ics_url.slice(0, 64)}${calendar.ics_url.length > 64 ? '…' : ''}`
        : '保存 ICS 链接后可同步到本地日历事件。';
    }
  }
  updateDataHealthSummary();
}

function updateCalendarProviderFields() {
  const provider = $('#calendarProvider')?.value || 'caldav';
  if ($('#calendarCaldavFields')) $('#calendarCaldavFields').hidden = provider !== 'caldav';
  if ($('#calendarIcsFields')) $('#calendarIcsFields').hidden = provider !== 'ics';
}

async function loadSettings() {
  try {
    state.settings = await apiRequest('/api/settings');
    $('#backupRetention').value = state.settings.backup_retention || 20;
    if ($('#autoBackupHours')) $('#autoBackupHours').value = state.settings.auto_backup_hours || 0;
    const auto = state.settings.auto_backup_hours
      ? `；自动备份每 ${state.settings.auto_backup_hours} 小时`
      : '；自动备份已关闭';
    $('#settingsStatus').textContent = `当前保留最近 ${state.settings.backup_retention} 份备份${auto}。`;
    if (Array.isArray(state.settings.home_layout)) {
      state.homeLayout = state.settings.home_layout;
      applyHomeLayout(state.homeLayout);
    }
    fillAiSettingsForm(state.settings);
    await refreshCalendarSubscriptions();
  } catch (error) { showToast(error.message); }
}

async function maybeAutoBackup() {
  if (!state.apiAvailable) return;
  try {
    const result = await apiRequest('/api/backups/auto-check', { method: 'POST' });
    if (result.created) {
      showToast('已执行定时自动备份');
      await refreshBackups();
      await loadSettings();
    }
  } catch (_) {}
}

async function refreshStats() {
  if (!state.apiAvailable) return;
  try {
    state.stats = await apiRequest(`/api/stats?period=${state.statsPeriod || 'week'}`);
    renderStats();
  } catch (error) { showToast(error.message); }
}

function renderStats() {
  const stats = state.stats;
  if (!stats) return;
  $('#statsCompleted').textContent = stats.tasks.completed;
  $('#statsOverdue').textContent = stats.tasks.overdue;
  $('#statsCreated').textContent = stats.tasks.created;
  $('#statsMinutes').textContent = stats.tasks.minutes_total;
  $('#statsOnTime').textContent = stats.requests.on_time_rate == null
    ? '—'
    : `${Math.round(stats.requests.on_time_rate * 100)}%（${stats.requests.delivered}/${stats.requests.total}）`;
  const typeList = $('#statsTypeList'); typeList.replaceChildren();
  (stats.tasks.by_type || []).forEach(item => {
    const row = make('div');
    const copy = make('span');
    copy.append(make('strong', '', item.type), make('small', '', `${item.count} 项 · ${item.minutes} 分钟`));
    row.append(copy); typeList.append(row);
  });
  if (!(stats.tasks.by_type || []).length) typeList.append(make('p', 'empty-state', '本周期暂无完成任务耗时'));
  const themeList = $('#statsThemeList'); themeList.replaceChildren();
  (stats.requests.top_themes || []).forEach(item => {
    const row = make('div');
    const copy = make('span');
    copy.append(make('strong', '', item.theme), make('small', '', `${item.count} 次`));
    row.append(copy); themeList.append(row);
  });
  if (!(stats.requests.top_themes || []).length) themeList.append(make('p', 'empty-state', '本周期暂无数据请求'));
  renderStatsDrill();
}

function renderStatsDrill() {
  const stats = state.stats; if (!stats) return;
  const drill = state.statsDrill || 'completed';
  const list = $('#statsDrillList'); list.replaceChildren();
  const labels = { completed: '已完成任务', overdue: '逾期任务', created: '新增任务', requests: '数据请求' };
  if ($('#statsDrillHint')) $('#statsDrillHint').textContent = `${stats.period.start} ~ ${stats.period.end} · ${labels[drill] || ''}`;
  let items = [];
  if (drill === 'requests') items = stats.requests.items || [];
  else items = (stats.tasks.drilldown || {})[drill] || [];
  items.forEach(item => {
    const row = make('button'); row.type = 'button';
    const copy = make('span');
    copy.append(
      make('strong', '', item.title),
      make('small', '', drill === 'requests'
        ? `${item.id} · ${item.status}${item.requester ? ` · ${item.requester}` : ''}`
        : `${item.id || ''} · ${item.planned_date || '未排期'}${item.actual_minutes ? ` · ${item.actual_minutes} 分钟` : ''}${item.completion_result ? ` · ${item.completion_result}` : ''}`),
    );
    row.append(copy);
    row.addEventListener('click', () => {
      if (drill === 'requests') openEntityDrawer('data_request', item);
      else openEntityDrawer('task', item);
    });
    list.append(row);
  });
  if (!items.length) list.append(make('p', 'empty-state', '该类别暂无明细'));
}

$$('#statsPeriodTabs button').forEach(button => button.addEventListener('click', async () => {
  state.statsPeriod = button.dataset.period;
  $$('#statsPeriodTabs button').forEach(item => item.classList.toggle('active', item === button));
  await refreshStats();
}));
$$('#statsDrillTabs button').forEach(button => button.addEventListener('click', () => {
  state.statsDrill = button.dataset.drill;
  $$('#statsDrillTabs button').forEach(item => item.classList.toggle('active', item === button));
  renderStatsDrill();
}));

function renderTodayQuickLinks() {
  const container = $('#todayQuickLinks') || $('.quick-links');
  if (!container) return;
  const homeItems = (state.navigation || []).filter(item => item.show_on_home !== 0 && item.show_on_home !== false).slice(0, 6);
  if (!homeItems.length) return;
  container.replaceChildren();
  homeItems.forEach(item => {
    const button = make('button');
    button.type = 'button';
    button.append(make('strong', '', item.title), make('small', '', item.category || '外部入口'));
    button.addEventListener('click', () => openNavigationItem(item));
    container.append(button);
  });
}

function renderCalendarSubscriptions(items = []) {
  const list = $('#calendarSubscriptionList');
  if (!list) return;
  list.replaceChildren();
  items.forEach(item => {
    const row = make('div');
    const copy = make('span');
    const providerLabel = item.provider === 'caldav' ? 'CalDAV' : item.provider === 'ics' ? 'ICS' : item.provider;
    const account = item.provider === 'caldav' && item.caldav_username ? ` · ${item.caldav_username}` : '';
    copy.append(
      make('strong', '', item.name),
      make('small', '', `${providerLabel}${account} · ${item.last_synced_at ? formatDate(item.last_synced_at) : '未同步'}${item.last_error ? ` · ${item.last_error}` : ''}`),
    );
    const sync = make('button', 'text-button', '同步'); sync.type = 'button';
    sync.addEventListener('click', async () => {
      try {
        const result = await apiRequest(`/api/calendar/subscriptions/${item.id}/sync`, { method: 'POST' });
        showToast(`已同步 ${result.synced} 条日程`);
        await Promise.all([refreshCalendarSubscriptions(), refreshTodayCalendar(), refreshHomeWeekCalendar()]);
      } catch (error) { showToast(error.message); }
    });
    row.append(copy, sync); list.append(row);
  });
  if (!items.length) list.append(make('p', 'empty-state', '暂无订阅'));
}

async function refreshCalendarSubscriptions() {
  if (!state.apiAvailable) return;
  try { renderCalendarSubscriptions(await apiRequest('/api/calendar/subscriptions')); }
  catch (error) { showToast(error.message); }
}

async function refreshTodayCalendar() {
  const list = $('#todayCalendarEvents');
  if (!list || !state.apiAvailable) {
    if (!state._bootstrapping) await refreshHomeWeekCalendar();
    return;
  }
  try {
    const today = localIsoDate(new Date());
    state.calendarEvents = await apiRequest(`/api/calendar/events?date_from=${today}&date_to=${today}`);
    list.replaceChildren();
    state.calendarEvents.forEach(event => {
      const row = make('button', 'today-cal-row');
      row.type = 'button';
      const copy = make('span');
      const time = event.all_day ? '全天' : String(event.start_at || '').slice(11, 16);
      copy.append(make('strong', '', event.title), make('small', '', `${time}${event.location ? ` · ${event.location}` : ''}`));
      row.append(make('time', '', time || '日程'), copy);
      row.title = '查看日程详情';
      row.addEventListener('click', () => openEntityDrawer('calendar_event', event));
      list.append(row);
    });
    if (!state.calendarEvents.length) list.append(make('p', 'empty-state', '暂无日程，可在数据管理中配置日历订阅'));
  } catch (_) {
    list.replaceChildren(make('p', 'empty-state', '日程暂不可用'));
  }
  if (!state._bootstrapping) await refreshHomeWeekCalendar();
}

async function ensureAccessUnlocked() {
  try {
    const status = await apiRequest('/api/access/status');
    if (status.required && !status.unlocked) {
      const hint = $('#accessUnlockHint');
      if (hint) {
        hint.textContent = status.locked
          ? `尝试过多，请 ${status.lock_remaining_seconds || 0} 秒后再试。`
          : `此工作台已启用访问保护；会话约 ${status.session_days || 14} 天，连续失败会被短暂锁定。`;
      }
      const errNode = $('#accessUnlockError');
      if (errNode) { errNode.hidden = true; errNode.textContent = ''; }
      openModal($('#accessModal'));
      return new Promise(resolve => {
        const form = $('#accessForm');
        const handler = async event => {
          event.preventDefault();
          try {
            const unlocked = await apiRequest('/api/access/unlock', { method: 'POST', body: JSON.stringify({ password: $('#accessUnlockPassword').value }) });
            if (unlocked?.token) sessionStorage.setItem('workbench_access', unlocked.token);
            form.removeEventListener('submit', handler);
            closeModal($('#accessModal'));
            if (unlocked?.expires_at) showToast(`已解锁，会话至 ${formatDate(unlocked.expires_at)}`);
            resolve(true);
          } catch (error) {
            if (errNode) { errNode.hidden = false; errNode.textContent = error.message; }
            showToast(error.message);
          }
        };
        form.addEventListener('submit', handler);
      });
    }
  } catch (_) {}
  return true;
}

async function refreshBackups() {
  try { state.backups = await apiRequest('/api/backups'); renderBackups(); }
  catch (error) { showToast(error.message); }
}

$('#createBackupButton').addEventListener('click', async () => {
  try { await apiRequest('/api/backups', { method: 'POST' }); await refreshBackups(); showToast('SQLite 备份已创建'); }
  catch (error) { showToast(error.message); }
});
$('#refreshBackupsButton').addEventListener('click', refreshBackups);
$('#saveSettingsButton').addEventListener('click', async () => {
  try {
    state.settings = await apiRequest('/api/settings', {
      method: 'PUT',
      body: JSON.stringify({
        backup_retention: Number($('#backupRetention').value),
        auto_backup_hours: Number($('#autoBackupHours')?.value || 0),
      }),
    });
    const auto = state.settings.auto_backup_hours
      ? `；自动备份每 ${state.settings.auto_backup_hours} 小时`
      : '；自动备份已关闭';
    $('#settingsStatus').textContent = `已更新：保留最近 ${state.settings.backup_retention} 份备份${auto}。`;
    fillAiSettingsForm(state.settings);
    await refreshBackups();
    fillAiSettingsForm(state.settings);
    showToast('备份策略已保存');
  } catch (error) { showToast(error.message); }
});
$('#saveAiSettingsButton')?.addEventListener('click', async () => {
  const payload = {
    ai: {
      enabled: $('#aiEnabled').checked,
      base_url: $('#aiBaseUrl').value.trim(),
      model: $('#aiModel').value.trim(),
      include_sql_text: $('#aiIncludeSql').checked,
    },
  };
  const key = $('#aiApiKey').value.trim();
  if (key) payload.ai.api_key = key;
  try {
    state.settings = await apiRequest('/api/settings', { method: 'PUT', body: JSON.stringify(payload) });
    fillAiSettingsForm(state.settings);
    showToast('AI 配置已保存');
  } catch (error) { showToast(error.message); }
});
$('#clearAiKeyButton')?.addEventListener('click', async () => {
  try {
    state.settings = await apiRequest('/api/settings', { method: 'PUT', body: JSON.stringify({ ai: { clear_api_key: true } }) });
    fillAiSettingsForm(state.settings);
    showToast('AI 密钥已清除');
  } catch (error) { showToast(error.message); }
});
$('#saveAccessPasswordButton')?.addEventListener('click', async () => {
  const password = $('#accessPassword').value;
  if (!password) { showToast('请输入新访问密码'); return; }
  try {
    state.settings = await apiRequest('/api/settings', { method: 'PUT', body: JSON.stringify({ access_password: password }) });
    $('#accessPassword').value = '';
    fillAiSettingsForm(state.settings);
    showToast('访问密码已保存');
  } catch (error) { showToast(error.message); }
});
$('#clearAccessPasswordButton')?.addEventListener('click', async () => {
  try {
    state.settings = await apiRequest('/api/settings', { method: 'PUT', body: JSON.stringify({ clear_access_password: true }) });
    fillAiSettingsForm(state.settings);
    showToast('访问密码已清除');
  } catch (error) { showToast(error.message); }
});
$('#calendarProvider')?.addEventListener('change', updateCalendarProviderFields);
$('#saveCalendarSettingsButton')?.addEventListener('click', async () => {
  const provider = $('#calendarProvider')?.value || 'caldav';
  const name = $('#calendarName')?.value.trim() || (provider === 'caldav' ? '钉钉 CalDAV' : '钉钉日程');
  const ics = $('#calendarIcsUrl')?.value.trim() || '';
  const caldavUrl = $('#calendarCaldavUrl')?.value.trim() || 'https://calendar.dingtalk.com';
  const caldavUsername = $('#calendarCaldavUsername')?.value.trim() || '';
  const caldavPassword = $('#calendarCaldavPassword')?.value || '';
  const caldavPath = $('#calendarCaldavPath')?.value.trim() || '';
  try {
    const dingtalk_calendar = {
      enabled: !!$('#calendarEnabled')?.checked,
      provider,
      ics_url: ics,
      caldav_url: caldavUrl,
      caldav_username: caldavUsername,
      caldav_path: caldavPath,
    };
    if (caldavPassword.trim()) dingtalk_calendar.caldav_password = caldavPassword.trim();
    state.settings = await apiRequest('/api/settings', {
      method: 'PUT',
      body: JSON.stringify({ dingtalk_calendar }),
    });
    if (provider === 'caldav') {
      if (!caldavUsername) throw new Error('请填写 CalDAV 用户名');
      if (!caldavPassword.trim() && !state.settings?.dingtalk_calendar?.has_caldav_password) {
        throw new Error('请填写 CalDAV 密码');
      }
      const existing = (await apiRequest('/api/calendar/subscriptions')).find(item => item.provider === 'caldav');
      const payload = {
        name,
        provider: 'caldav',
        enabled: true,
        caldav_url: caldavUrl,
        caldav_username: caldavUsername,
        caldav_path: caldavPath,
      };
      if (caldavPassword.trim()) payload.caldav_password = caldavPassword.trim();
      if (existing?.id) {
        await apiRequest(`/api/calendar/subscriptions/${existing.id}`, { method: 'PATCH', body: JSON.stringify(payload) });
      } else {
        if (!caldavPassword.trim()) throw new Error('首次保存请填写 CalDAV 密码');
        await apiRequest('/api/calendar/subscriptions', { method: 'POST', body: JSON.stringify(payload) });
      }
    } else if (ics) {
      await apiRequest('/api/calendar/subscriptions', { method: 'POST', body: JSON.stringify({ name, provider: 'ics', ics_url: ics, enabled: true }) });
    }
    fillAiSettingsForm(state.settings);
    await refreshCalendarSubscriptions();
    showToast('日程订阅已保存');
  } catch (error) { showToast(error.message); }
});
async function syncCalendarSubscriptions(options = {}) {
  const { refreshWeek = false, button } = options;
  if (button) {
    button.disabled = true;
    button.dataset.syncLabel = button.textContent;
    button.textContent = '同步中…';
  }
  try {
    const result = await apiRequest('/api/calendar/sync', { method: 'POST' });
    const total = (result.results || []).reduce((sum, item) => sum + (item.synced || 0), 0);
    const failed = (result.results || []).filter(item => item.error || item.last_error);
    if (failed.length && !total) {
      showToast(failed[0].error || failed[0].last_error || '日历同步失败');
    } else {
      showToast(`已同步 ${total} 条日程${failed.length ? `，${failed.length} 个订阅有错误` : ''}`);
    }
    const jobs = [refreshCalendarSubscriptions(), refreshTodayCalendar(), refreshHomeWeekCalendar()];
    if (refreshWeek) jobs.push(refreshWeekTasks());
    await Promise.all(jobs);
    return result;
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = button.dataset.syncLabel || '同步日历';
    }
  }
}

$('#syncCalendarButton')?.addEventListener('click', async () => {
  try {
    await syncCalendarSubscriptions({ button: $('#syncCalendarButton') });
  } catch (error) { showToast(error.message); }
});
$('#syncWeekCalendarButton')?.addEventListener('click', async () => {
  try {
    await syncCalendarSubscriptions({ refreshWeek: true, button: $('#syncWeekCalendarButton') });
  } catch (error) { showToast(error.message); }
});
$('#refreshCalendarToday')?.addEventListener('click', refreshTodayCalendar);
$('#tableRestoreForm').addEventListener('submit', async event => {
  event.preventDefault();
  const tables = $$('input[name="restoreTable"]:checked').map(input => input.value);
  if (!tables.length) { showToast('请至少选择一张表'); return; }
  const name = $('#tableRestoreBackupName').value;
  if (!window.confirm(`确认从 ${name} 恢复 ${tables.length} 张表吗？`)) return;
  try {
    const result = await apiRequest(`/api/backups/${encodeURIComponent(name)}/restore-tables`, { method: 'POST', body: JSON.stringify({ tables }) });
    closeModal($('#tableRestoreModal'));
    showToast(`已按表恢复，安全备份 ${result.safety_backup}`);
    setTimeout(() => location.reload(), 800);
  } catch (error) { showToast(error.message); }
});
$('#exportJsonButton').addEventListener('click', () => downloadData('/api/data/export.json'));
$('#exportCsvButton').addEventListener('click', () => downloadData(`/api/data/export.csv?entity=${encodeURIComponent($('#csvExportEntity').value)}`));

function renderImportDiff(preview) {
  const panel = $('#importDiff');
  if (!panel) return;
  if (!preview.diff) { panel.hidden = true; panel.textContent = ''; return; }
  const lines = [`合计：新增 ${preview.summary.new} · 更新 ${preview.summary.updated} · 不变 ${preview.summary.unchanged}`];
  Object.entries(preview.diff).forEach(([table, info]) => {
    lines.push(`${table}: 入站 ${info.incoming}，新增 ${info.new}，更新 ${info.updated}，不变 ${info.unchanged}`);
    if (info.sample_new?.length) lines.push(`  新增示例：${info.sample_new.join(', ')}`);
    if (info.sample_updated?.length) lines.push(`  更新示例：${info.sample_updated.join(', ')}`);
  });
  panel.hidden = false;
  panel.textContent = lines.join('\n');
}

async function importJsonFile(file) {
  try {
    const payload = JSON.parse(await file.text()); payload.mode = $('#dataImportMode').value;
    const preview = await apiRequest('/api/data/import/preview', { method: 'POST', body: JSON.stringify(payload) });
    renderImportDiff(preview);
    $('#importStatus').textContent = `已校验 ${preview.total} 条记录：新增 ${preview.summary.new}，更新 ${preview.summary.updated}，不变 ${preview.summary.unchanged}。`;
    if (!window.confirm(`已校验 ${preview.total} 条记录（新增 ${preview.summary.new} / 更新 ${preview.summary.updated}）。确认按“${payload.mode === 'merge' ? '合并更新' : '仅新增'}”模式导入吗？`)) return;
    const result = await apiRequest('/api/data/import', { method: 'POST', body: JSON.stringify(payload) });
    $('#importStatus').textContent = `导入完成；安全备份：${result.safety_backup}。即将刷新数据。`; showToast('JSON 数据已导入'); setTimeout(() => location.reload(), 900);
  } catch (error) { $('#importStatus').textContent = error.message; showToast(error.message); }
}

async function importCsvFile(file) {
  try {
    const payload = { entity: $('#csvImportEntity').value, csv_text: await file.text(), mode: $('#dataImportMode').value };
    if (!window.confirm(`确认导入 ${file.name} 吗？导入前会自动创建安全备份。`)) return;
    const result = await apiRequest('/api/data/import.csv', { method: 'POST', body: JSON.stringify(payload) });
    $('#importStatus').textContent = `CSV 导入完成；安全备份：${result.safety_backup}。即将刷新数据。`; showToast('CSV 数据已导入'); setTimeout(() => location.reload(), 900);
  } catch (error) { $('#importStatus').textContent = error.message; showToast(error.message); }
}

$('#jsonImportFile').addEventListener('change', event => { const [file] = event.target.files; if (file) importJsonFile(file); event.target.value = ''; });
$('#csvImportFile').addEventListener('change', event => { const [file] = event.target.files; if (file) importCsvFile(file); event.target.value = ''; });

function isMobileShell() {
  return window.matchMedia('(max-width: 760px)').matches;
}

function setMobileNavOpen(open) {
  const sidebar = $('#sidebar');
  const backdrop = $('#navBackdrop');
  if (!sidebar) return;
  sidebar.classList.toggle('open', open);
  document.body.classList.toggle('nav-open', open);
  if (backdrop) {
    backdrop.hidden = !open;
    backdrop.classList.toggle('is-visible', open);
  }
}

function closeMobileNav() {
  setMobileNavOpen(false);
}

function syncMobileTabbar(viewName = state.activeView) {
  $$('#mobileTabbar [data-mobile-view]').forEach(button => {
    button.classList.toggle('active', button.dataset.mobileView === viewName);
  });
}

$('#menuButton')?.addEventListener('click', () => {
  if (isMobileShell()) setMobileNavOpen(!$('#sidebar')?.classList.contains('open'));
  else document.body.classList.toggle('sidebar-collapsed');
});
$('#navBackdrop')?.addEventListener('click', closeMobileNav);
$('#mobileMoreButton')?.addEventListener('click', () => {
  if (!isMobileShell()) {
    showView('data');
    return;
  }
  setMobileNavOpen(true);
});
$$('#mobileTabbar [data-mobile-view]').forEach(button => {
  button.addEventListener('click', () => showView(button.dataset.mobileView));
});
window.addEventListener('resize', () => {
  if (!isMobileShell()) closeMobileNav();
});

function applyAppearance(mode) {
  const dark = mode === 'dark';
  document.documentElement.classList.toggle('dark', dark);
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
  $('#appearanceButton').setAttribute('aria-pressed', String(dark));
}

function navigationCategorySuggestions() {
  const defaults = ['常用工具', '数据平台', '审计系统', '协作沟通', '知识文档'];
  const existing = [...new Set((state.navigation || []).map(item => item.category).filter(Boolean))];
  return [...new Set([...existing, ...defaults])];
}

function setNavigationColor(color = 'blue') {
  const value = color || 'blue';
  if ($('#navigationColor')) $('#navigationColor').value = value;
  $$('#navigationColorSwatches .nav-color-swatch').forEach(button => {
    const active = button.dataset.color === value;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  updateNavigationPreview();
}

function renderNavigationCategoryChips(selected = '') {
  const chips = $('#navigationCategoryChips');
  const list = $('#navigationCategoryOptions');
  if (!chips) return;
  const categories = navigationCategorySuggestions();
  if (list) {
    list.replaceChildren();
    categories.forEach(name => list.append(new Option(name, name)));
  }
  chips.replaceChildren();
  categories.slice(0, 8).forEach(name => {
    const button = make('button', `nav-preset${name === selected ? ' is-active' : ''}`, name);
    button.type = 'button';
    button.addEventListener('click', () => {
      $('#navigationCategory').value = name;
      renderNavigationCategoryChips(name);
      updateNavigationPreview();
    });
    chips.append(button);
  });
}

function updateNavigationPreview() {
  const title = ($('#navigationTitle')?.value || '').trim() || '导航名称';
  const description = ($('#navigationDescription')?.value || '').trim();
  const url = ($('#navigationUrl')?.value || '').trim();
  const icon = ($('#navigationIcon')?.value || '').trim().slice(0, 2) || '链';
  const color = $('#navigationColor')?.value || 'blue';
  const category = ($('#navigationCategory')?.value || '').trim() || '未分类';
  const onHome = !!$('#navigationShowOnHome')?.checked;
  const logo = $('#navigationPreviewLogo');
  if (logo) {
    logo.className = `link-logo ${color}`;
    logo.textContent = icon;
  }
  $$('#navigationColorSwatches .link-logo').forEach(node => { node.textContent = icon; });
  if ($('#navigationPreviewTitle')) $('#navigationPreviewTitle').textContent = title;
  if ($('#navigationPreviewDesc')) {
    $('#navigationPreviewDesc').textContent = description || url || '说明或地址会显示在这里';
  }
  if ($('#navigationPreviewCategory')) $('#navigationPreviewCategory').textContent = category;
  if ($('#navigationPreviewHome')) {
    $('#navigationPreviewHome').textContent = onHome ? '首页展示' : '仅导航页';
    $('#navigationPreviewHome').classList.toggle('is-off', !onHome);
  }
  $$('#navigationIconPresets .nav-preset').forEach(button => {
    button.classList.toggle('is-active', button.dataset.icon === icon);
  });
  if ($('#saveNavigationButton')) {
    $('#saveNavigationButton').textContent = $('#navigationId')?.value ? '更新导航' : '保存导航';
  }
}

function openNavigationForm(item = null) {
  $('#navigationForm').reset();
  $('#navigationId').value = item?.id || '';
  $('#navigationModalTitle').textContent = item ? '编辑导航' : '添加导航';
  $('#navigationTitle').value = item?.title || '';
  $('#navigationUrl').value = item?.url || '';
  $('#navigationDescription').value = item?.description || '';
  const category = item?.category || '常用工具';
  $('#navigationCategory').value = category;
  $('#navigationIcon').value = item?.icon_text || '链';
  $('#navigationOrder').value = item?.sort_order ?? 0;
  $('#deleteNavigationButton').hidden = !item;
  if ($('#navigationShowOnHome')) $('#navigationShowOnHome').checked = item ? !!item.show_on_home : true;
  setNavigationColor(item?.color || 'blue');
  renderNavigationCategoryChips(category);
  updateNavigationPreview();
  openModal($('#navigationModal'));
  setTimeout(() => $('#navigationTitle')?.focus(), 30);
}

async function openNavigationItem(item) {
  const target = window.open(item.url, '_blank', 'noopener,noreferrer');
  try { await apiRequest(`/api/navigation/${item.id}/visit`, { method: 'POST' }); await refreshNavigation(); }
  catch (_) {}
  if (!target) showToast('浏览器阻止了新窗口，请允许弹出窗口');
}

function renderNavigation() {
  const root = $('#navigationSections'); root.replaceChildren();
  const query = $('#navigationSearch').value.trim().toLowerCase();
  const items = state.navigation.filter(item => !query || `${item.title} ${item.description} ${item.category} ${item.url}`.toLowerCase().includes(query));
  const categories = [...new Set(items.map(item => item.category))];
  categories.forEach(category => {
    const section = make('div', 'link-section'); const heading = make('div', 'section-title');
    const categoryItems = items.filter(item => item.category === category);
    heading.append(make('h2', '', category), make('span', '', `${categoryItems.length} 个入口`));
    const grid = make('div', 'link-grid');
    categoryItems.forEach(item => {
      const card = make('div', 'navigation-card');
      const open = make('button', 'navigation-open'); open.type = 'button';
      const copy = make('span'); copy.append(make('strong', '', item.title), make('small', '', item.description || item.url));
      open.append(make('span', `link-logo ${item.color}`, item.icon_text), copy, make('b', '', '↗'));
      open.addEventListener('click', () => openNavigationItem(item));
      const edit = make('button', 'navigation-edit', '编辑'); edit.type = 'button'; edit.addEventListener('click', () => openNavigationForm(item));
      card.append(open, edit); grid.append(card);
    });
    section.append(heading, grid); root.append(section);
  });
  if (!items.length) root.append(make('p', 'empty-state', '没有符合条件的导航入口'));
  const recent = state.navigation.filter(item => item.last_visited_at).sort((left, right) => String(right.last_visited_at).localeCompare(String(left.last_visited_at))).slice(0, 5);
  if (recent.length && !query) {
    const section = make('div', 'link-section'); const heading = make('div', 'section-title'); heading.append(make('h2', '', '最近使用'), make('span', '', '按访问时间排序'));
    const list = make('div', 'recent-links'); recent.forEach(item => { const button = make('button'); button.type = 'button'; const copy = make('span'); copy.append(make('strong', '', item.title), make('small', '', formatDate(item.last_visited_at))); button.append(make('span', `link-logo ${item.color}`, item.icon_text), copy, make('b', '', '→')); button.addEventListener('click', () => openNavigationItem(item)); list.append(button); });
    section.append(heading, list); root.append(section);
  }
}

async function refreshNavigation() { state.navigation = await apiRequest('/api/navigation'); renderNavigation(); }
$('#newNavigationButton').addEventListener('click', () => openNavigationForm());
$('#navigationSearch').addEventListener('input', renderNavigation);
['navigationTitle', 'navigationUrl', 'navigationDescription', 'navigationCategory', 'navigationIcon', 'navigationOrder']
  .forEach(id => $(`#${id}`)?.addEventListener('input', () => {
    if (id === 'navigationCategory') renderNavigationCategoryChips($('#navigationCategory').value.trim());
    if (id === 'navigationIcon') {
      const value = $('#navigationIcon').value.slice(0, 2);
      if ($('#navigationIcon').value !== value) $('#navigationIcon').value = value;
    }
    updateNavigationPreview();
  }));
$('#navigationShowOnHome')?.addEventListener('change', updateNavigationPreview);
$$('#navigationColorSwatches .nav-color-swatch').forEach(button => {
  button.addEventListener('click', () => setNavigationColor(button.dataset.color));
});
$$('#navigationIconPresets .nav-preset').forEach(button => {
  button.addEventListener('click', () => {
    $('#navigationIcon').value = button.dataset.icon || '链';
    updateNavigationPreview();
  });
});
$('#navigationForm').addEventListener('submit', async event => {
  event.preventDefault();
  const id = $('#navigationId').value;
  const payload = {
    title: $('#navigationTitle').value.trim(),
    url: $('#navigationUrl').value.trim(),
    description: $('#navigationDescription').value.trim(),
    category: $('#navigationCategory').value.trim() || '常用工具',
    icon_text: ($('#navigationIcon').value.trim() || '链').slice(0, 2),
    color: $('#navigationColor').value || 'blue',
    sort_order: Number($('#navigationOrder').value || 0),
    show_on_home: !!$('#navigationShowOnHome')?.checked,
  };
  try {
    await apiRequest(id ? `/api/navigation/${id}` : '/api/navigation', {
      method: id ? 'PATCH' : 'POST',
      body: JSON.stringify(payload),
    });
    closeModal($('#navigationModal'));
    await refreshNavigation();
    renderTodayQuickLinks();
    showToast(id ? '导航已更新' : '导航已添加');
  } catch (error) { showToast(error.message); }
});
$('#deleteNavigationButton').addEventListener('click', async () => {
  const id = $('#navigationId').value;
  if (!id || !window.confirm('确认删除这个导航入口吗？')) return;
  try {
    await apiRequest(`/api/navigation/${id}`, { method: 'DELETE' });
    closeModal($('#navigationModal'));
    await refreshNavigation();
    renderTodayQuickLinks();
    showToast('导航已删除');
  } catch (error) { showToast(error.message); }
});

const savedAppearance = localStorage.getItem('audit-workbench.appearance');
applyAppearance(savedAppearance || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
$('#appearanceButton').addEventListener('click', () => {
  const mode = document.documentElement.classList.contains('dark') ? 'light' : 'dark';
  localStorage.setItem('audit-workbench.appearance', mode);
  applyAppearance(mode);
});
$('#aiStatusChip')?.addEventListener('click', () => openAiSettings());
$('#aiCapabilityConfig')?.addEventListener('click', event => {
  event.preventDefault();
  event.stopPropagation();
  openAiSettings();
});
$$('[data-ai-jump]').forEach(button => button.addEventListener('click', () => {
  const jump = button.dataset.aiJump;
  if (jump === 'notes') {
    showView('notes');
    openRecord();
    return;
  }
  if (jump === 'sql') {
    showView('sql');
    openSqlForm();
  }
}));
document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); openCommand(); }
  if (event.key === 'Escape') { closeCommand(); closeDrawer(); closeEntityDrawer(); $$('.modal.open').forEach(closeModal); }
});

async function bootstrapApi() {
  try {
    const health = await apiRequest('/api/health');
    state.apiAvailable = true;
    if (health.access_required) await ensureAccessUnlocked();
    $('.sidebar-foot strong').textContent = '本地数据库已连接';
    $('.sidebar-foot small').textContent = health.ai_ready ? 'AI 已就绪' : 'AI 未启用或未配置';
    const [notes, requests, sqlAssets, procedures, models, projects, navigation, reportTemplates, genericReports, projectTemplates] = await Promise.all([
      apiRequest('/api/notes?archived=false'), apiRequest('/api/data-requests'), apiRequest('/api/sql-assets'),
      apiRequest('/api/procedures'), apiRequest('/api/models'), apiRequest('/api/projects'), apiRequest('/api/navigation'),
      apiRequest('/api/report-templates'), apiRequest('/api/reports'), apiRequest('/api/project-templates'),
    ]);
    state.notes = notes.map(normalizeNote); state.requests = requests; state.sqlAssets = sqlAssets;
    state.procedures = procedures; state.models = models; state.projects = projects; state.navigation = navigation;
    state.reportTemplates = reportTemplates; state.genericReports = genericReports; state.projectTemplates = projectTemplates;
    state.currentModel = null;
    try {
      const settings = await apiRequest('/api/settings');
      state.settings = settings;
      if (Array.isArray(settings.home_layout)) state.homeLayout = settings.home_layout;
      fillAiSettingsForm(settings);
    } catch (_) {
      const cached = localStorage.getItem('audit-workbench.home-layout');
      if (cached) {
        try { state.homeLayout = JSON.parse(cached); } catch (_) {}
      }
      renderAiStatus();
    }
    applyHomeLayout(state.homeLayout);
    wireHomeLayoutDrag();
    renderSavedNotes(); renderRequests(); renderTodayRequests(); renderSqlAssets(); renderTodaySqlHome(); renderProcedures(); renderProjects(); renderTodayProjects(); renderTodayModelsHome(); renderTodayNotesHome(); renderNavigation(); renderTodayQuickLinks(); renderReportTemplateOptions(); renderGenericReportHistory(); updateBatchButtons();
    state._bootstrapping = true;
    try {
      await Promise.all([refreshWeekTasks(), refreshTodayTasks(), refreshTodayCalendar(), maybeAutoBackup()]);
      await refreshHomeWeekCalendar();
    } finally {
      state._bootstrapping = false;
    }
    updateNavCounts();
    if (!state.nudgeTimer) {
      state.nudgeTimer = setInterval(() => {
        if (state.apiAvailable && state.activeView === 'today') refreshTodayTasks().catch(() => {});
      }, 5 * 60 * 1000);
    }
    $('#enableNotifyButton')?.addEventListener('click', async () => {
      if (!('Notification' in window)) { showToast('当前浏览器不支持桌面通知'); return; }
      const permission = await Notification.requestPermission();
      showToast(permission === 'granted' ? '桌面催办已开启' : '未获得通知权限');
      if (permission === 'granted') maybeNotifyNudges(state.focusNudges || []);
    });
    $('#refreshNudgesButton')?.addEventListener('click', async () => {
      try { await refreshTodayTasks(); showToast('催办已刷新'); } catch (error) { showToast(error.message); }
    });
  } catch (_) {
    state.apiAvailable = false;
    $('.sidebar-foot strong').textContent = '离线演示模式';
    $('.sidebar-foot small').textContent = '启动后端后自动连接';
    renderAiStatus();
    renderSavedNotes(); renderWeekBoard();
  }
}

{
  const cached = localStorage.getItem('audit-workbench.home-layout');
  if (cached) {
    try { state.homeLayout = JSON.parse(cached); } catch (_) {}
  }
}
applyHomeLayout(state.homeLayout);
wireHomeLayoutDrag();
updateCurrentDateLabels(); renderSavedNotes(); renderWeekBoard(); renderTodayTasks(); renderTodayProjects(); renderTodayRequests(); renderTodaySqlHome(); renderTodayModelsHome(); renderTodayNotesHome(); renderHomeWeekCalendar(); updateBatchButtons(); bootstrapApi();
window.addEventListener('resize', () => applyHomeLayout(state.homeLayout));
