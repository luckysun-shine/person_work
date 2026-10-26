const $ = (selector, scope = document) => scope.querySelector(selector);
const $$ = (selector, scope = document) => [...scope.querySelectorAll(selector)];

const viewNames = {
  today: ['今日', '今日'], week: ['周计划', '周计划'], reports: ['报告助手', '报告助手'],
  requests: ['数据请求', '数据请求'], sql: ['SQL 资产', 'SQL 资产'], models: ['监测模型', '监测模型'],
  projects: ['项目', '项目'], notes: ['工作记录', '工作记录'], search: ['统一检索', '统一检索'], data: ['数据管理', '数据管理'],
};

let toastTimer;
function toast(message) {
  const node = $('#toast'); node.textContent = message; node.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => node.classList.remove('show'), 1700);
}

function showView(name) {
  $$('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === name));
  $$('.view').forEach(view => view.classList.remove('active'));
  const target = $(`#view-${name}`);
  if (target) target.classList.add('active');
  else {
    $('#view-generic').classList.add('active');
    $('#genericTitle').textContent = viewNames[name]?.[0] || '工作区';
    $('#genericDescription').textContent = `${viewNames[name]?.[0] || '该模块'}将在正式重构阶段应用同一套导航、列表和状态设计。`;
  }
  $('#toolbarTitle').textContent = viewNames[name]?.[1] || '工作区';
  if (window.innerWidth <= 760) document.body.classList.add('sidebar-collapsed');
  closePalette();
}

$$('.nav-item').forEach(button => button.addEventListener('click', () => showView(button.dataset.view)));
$$('[data-go]').forEach(button => button.addEventListener('click', () => showView(button.dataset.go)));
$('#sidebarToggle').addEventListener('click', () => document.body.classList.toggle('sidebar-collapsed'));
$('#themeToggle').addEventListener('click', () => document.documentElement.classList.toggle('dark'));

const palette = $('#commandPalette');
function openPalette() { palette.classList.add('open'); palette.setAttribute('aria-hidden', 'false'); setTimeout(() => $('#paletteInput').focus(), 20); }
function closePalette() { palette.classList.remove('open'); palette.setAttribute('aria-hidden', 'true'); $('#paletteInput').value = ''; }
$('#searchTrigger').addEventListener('click', openPalette);
palette.addEventListener('click', event => { if (event.target === palette) closePalette(); });
$$('[data-open]').forEach(button => button.addEventListener('click', () => showView(button.dataset.open)));
document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); openPalette(); }
  if (event.key === 'Escape') { closePalette(); closeSheet(); }
});

const sheet = $('#noteSheet');
function openSheet() { sheet.classList.add('open'); sheet.setAttribute('aria-hidden', 'false'); setTimeout(() => $('.sheet-card input').focus(), 20); }
function closeSheet() { sheet.classList.remove('open'); sheet.setAttribute('aria-hidden', 'true'); }
$('#newNote').addEventListener('click', openSheet);
$$('.sheet-close').forEach(button => button.addEventListener('click', closeSheet));
sheet.addEventListener('click', event => { if (event.target === sheet) closeSheet(); });
$('.sheet-card').addEventListener('submit', event => { event.preventDefault(); closeSheet(); event.currentTarget.reset(); toast('工作记录已保存'); });

$$('.task-row').forEach(row => row.addEventListener('click', () => {
  row.classList.toggle('done');
  toast(row.classList.contains('done') ? '任务已完成' : '任务已恢复');
}));

$('#closeInspector').addEventListener('click', () => $('#sqlInspector').classList.add('closed'));
$$('.table-row').forEach(row => row.addEventListener('click', () => {
  $$('.table-row').forEach(item => item.classList.toggle('selected', item === row));
  $('#sqlInspector').classList.remove('closed');
}));

$$('.segmented button').forEach(button => button.addEventListener('click', () => {
  $$('.segmented button').forEach(item => item.classList.toggle('active', item === button));
}));

$$('.title-actions button').forEach(button => button.addEventListener('click', () => {
  toast(button.textContent.trim() === '保存报告' ? '报告已保存' : '已生成新的草稿');
}));

function syncCompactState() {
  if (window.innerWidth <= 760) document.body.classList.add('sidebar-collapsed');
}
window.addEventListener('resize', syncCompactState);
syncCompactState();
