/* Offline UI. Club snapshot and historical Event Lab have independent timelines. */
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const finite = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
const num = (value, digits = 2) => finite(value) ? Number(value).toFixed(digits) : '—';
const pct = value => finite(value) ? (100 * Number(value)).toFixed(1) + '%' : '—';
const normalize = value => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g,'d').replace(/Đ/g,'D').toLowerCase();
const clamp = value => finite(value) ? Math.max(0, Math.min(1, Number(value))) : 0;
const MEDIA = {...(DATA.media || {}), leagues:DATA.media?.leagues || {}, teams:DATA.media?.teams || {}, players:Array.isArray(DATA.media?.players) ? DATA.media.players : [], coverage:DATA.media?.coverage || {}};
const leagues = DATA.leagues || {};
const leagueSelect = $('league');
let page = 'overview', playerLimit = 24, playerLeague = null, searchTimer;
const pages = {overview:'Một góc nhìn trước trận.', match:'Trận đấu của bạn. Góc nhìn của bạn.', race:'Ai sẽ về đích đầu tiên?', players:'Những gương mặt của trận đấu.', expert:'Hiểu trận đấu từ từng sự kiện.', ops:'Mỗi dự đoán đều có dấu vết.'};
const allowedImageHosts = new Set(['r2.thesportsdb.com','www.thesportsdb.com','raw.githubusercontent.com']);
function safeHref(value, hosts = new Set(['www.thesportsdb.com','thesportsdb.com','github.com','raw.githubusercontent.com'])) {
  try { const url = new URL(value); return url.protocol === 'https:' && hosts.has(url.hostname) && !url.username && !url.password ? url.href : ''; } catch { return ''; }
}
function safeSrc(value) {
  if (typeof value !== 'string') return '';
  if (/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(value)) return value;
  return safeHref(value, allowedImageHosts);
}
function imageBox(record, label, kind = '') {
  const source = safeSrc(record?.image_data) || safeSrc(record?.image_url);
  const initials = String(label).split(/\s+/).map(x => x[0]).slice(0,2).join('').toUpperCase();
  return `<span class="media-box ${kind}">${source ? `<img src="${esc(source)}" alt="${esc(label)}" width="150" height="150" loading="lazy" decoding="async" referrerpolicy="no-referrer">` : ''}<span class="media-placeholder" ${source ? 'hidden' : ''}>${esc(initials)}</span></span>`;
}
function badge(name, kind = '', code = leagueSelect.value) { return imageBox(MEDIA.teams[code + '|' + name], name, kind); }
document.addEventListener('error', event => {
  if (event.target.tagName === 'IMG') { event.target.hidden = true; const placeholder = event.target.nextElementSibling; if (placeholder) placeholder.hidden = false; }
}, true);
function table(headers, rows) {
  return '<table><thead><tr>' + headers.map(h => '<th scope="col">' + esc(h) + '</th>').join('') + '</tr></thead><tbody>' + rows.map(row => '<tr>' + row.map(v => '<td>' + esc(v) + '</td>').join('') + '</tr>').join('') + '</tbody></table>';
}
function download(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  $('ui-status').textContent = 'Đã chuẩn bị tệp ' + name;
}
function csvCell(value) {
  let text = String(value ?? '');
  // Keep spreadsheet applications from interpreting source-supplied names as formulas.
  if (typeof value === 'string' && /^[\s]*[=+@-]/.test(text)) text = "'" + text;
  return '"' + text.replaceAll('"','""') + '"';
}
function current() { return leagues[leagueSelect.value]; }
for (const [code, league] of Object.entries(leagues)) leagueSelect.add(new Option(league.name, code));
if (leagues.E0) leagueSelect.value = 'E0';
$('league-switcher').innerHTML = Object.entries(leagues).map(([code, league]) => `<button class="league-choice" data-league="${esc(code)}" aria-pressed="false">${imageBox(MEDIA.leagues[code], league.name)}<span>${esc(league.name)}</span></button>`).join('');
const icons = {
  overview:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  match:'<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M12 5v14M2 9h4v6H2m20-6h-4v6h4"/><circle cx="12" cy="12" r="3"/>',
  race:'<path d="M8 3h8v6a4 4 0 0 1-8 0V3Zm0 2H4v2a4 4 0 0 0 4 4m8-6h4v2a4 4 0 0 1-4 4M12 13v7m-4 1h8"/>',
  players:'<circle cx="9" cy="7" r="3"/><path d="M3 21v-2a6 6 0 0 1 12 0v2m1-17a3 3 0 0 1 0 6m2 4a6 6 0 0 1 3 5v2"/>',
  expert:'<path d="M9 3h6m-5 0v6l-6 10a1.5 1.5 0 0 0 1 2h14a1.5 1.5 0 0 0 1-2L14 9V3M8 15h8"/>',
  ops:'<path d="M4 20h16M5 16v-4m7 4V8m7 8V4M4 7l6-3 5 2 5-4"/>'
};
document.querySelectorAll('[data-icon]').forEach(node => { node.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true">' + icons[node.dataset.icon] + '</svg>'; });

function updateContext() {
  const m = DATA.meta || {}, l = current(), historical = page === 'expert', r = DATA.research;
  $('league-context').classList.toggle('hidden', historical || !l);
  $('page-title').textContent = pages[page];
  $('page-kicker').textContent = historical ? 'EVENT INTELLIGENCE / HISTORICAL REPLAY' : 'THE GAME, IN NUMBERS';
  $('asof').textContent = historical ? (r ? `${r.competition} · Cutoff ${r.as_of} · ${r.matches_observed}/${r.matches_total} trận quan sát` : 'Chưa có bộ nghiên cứu sự kiện. Chạy Event Research trong Colab.') : l ? `Trận đấu đến ${m.training_through || '—'} · Snapshot ${String(m.created_at || '').slice(0,10)} · Mùa ${String(l.season).slice(0,2)}/${String(l.season).slice(2)}` : 'Chưa có dữ liệu CLB.';
  $('snapshot-state').textContent = historical ? 'Replay lịch sử · không phải live' : 'Snapshot · không phải live';
  $('side-model').textContent = (m.persistent_drive ? 'DRIVE / AUTO SAVE' : 'LOCAL SNAPSHOT') + ' · ' + String(DATA.metrics?.selected || 'RESEARCH').toUpperCase();
  $('footer-run').textContent = 'RUN ' + (m.run_id || '—');
  document.querySelectorAll('[data-league]').forEach(button => { const selected = button.dataset.league === leagueSelect.value; button.classList.toggle('active', selected); button.setAttribute('aria-pressed', String(selected)); });
}
function chooseTeams(home, away) {
  const l = current(); if (!l) return;
  const teams = l.teams || [];
  for (const id of ['home','away']) $(id).replaceChildren(...teams.map(team => new Option(team,team)));
  if (teams.includes(home)) $('home').value = home;
  $('away').value = teams.includes(away) && away !== $('home').value ? away : teams.find(team => team !== $('home').value) || '';
  $('swap').disabled = teams.length < 2;
  $('season').textContent = l.name;
  playerLeague = null;
}
function selectedForecast() {
  const l = current(); if (!l) return null;
  if ($('home').value === $('away').value) $('away').value = l.teams.find(team => team !== $('home').value) || '';
  return l.forecasts?.[$('home').value + '|' + $('away').value] || null;
}
function renderOverview() {
  const l = current(), m = DATA.meta || {}, report = DATA.metrics || {};
  const kpis = [
    ['TRẬN ĐÃ HỌC', Number(m.matches || 0).toLocaleString('vi-VN'), 'Dữ liệu trận đấu đã quan sát'],
    ['ĐỘI TRONG GIẢI', (l.teams || []).length, `${l.matches || 0} trận ở mùa đang chọn`],
    ['TEST LOG LOSS', num(report.test?.log_loss,4), `Baseline ${num(report.test_baseline?.log_loss,4)} · ${report.test?.matches || 0} trận test`],
    ['LƯỢT MÔ PHỎNG', Number(l.race?.simulations || 0).toLocaleString('vi-VN'), 'Kịch bản mùa giải · seed 42']
  ];
  $('kpis').innerHTML = kpis.map(([label,value,note]) => `<div class="kpi"><div class="kpi-label">${esc(label)}</div><strong>${esc(value)}</strong><small>${esc(note)}</small></div>`).join('');
  const home = $('home').value, away = $('away').value;
  $('hero-fixture').innerHTML = home && away ? `<span class="team-name">${badge(home)}${esc(home)}</span><span class="fixture-vs">VS</span><span class="team-name">${esc(away)}${badge(away)}</span>` : '<span>Chưa có cặp đấu đủ dữ liệu</span>';
}
function renderMatch() {
  const l = current(), d = selectedForecast(), home = $('home').value, away = $('away').value;
  if (!d) { $('match-result').innerHTML = '<div class="empty">Chưa có dự báo cho cặp đấu này. Chọn hai đội khác hoặc cập nhật snapshot trong Colab.</div>'; $('side-card').innerHTML = '<div class="empty">Chưa đủ dữ liệu để hiển thị.</div>'; return; }
  const stat = (left,title,right) => `<div class="stat"><b>${esc(left)}</b><span class="title">${esc(title)}</span><b>${esc(right)}</b></div>`;
  $('match-result').innerHTML = `<div class="match-score"><div>${badge(home,'large')}<div class="club">${esc(home)}</div></div><div><div class="expected">${num(d.goals?.[0])} : ${num(d.goals?.[1])}</div><div class="xg-label">BÀN KỲ VỌNG / 90 PHÚT</div></div><div>${badge(away,'large')}<div class="club">${esc(away)}</div></div></div><div class="outcome-bar" aria-hidden="true"><div style="background:#214e33;width:${clamp(d.home_win)*100}%"></div><div style="background:#d7e1be;width:${clamp(d.draw)*100}%"></div><div style="background:#93b454;width:${clamp(d.away_win)*100}%"></div></div><div class="legend"><span>Chủ thắng <b>${pct(d.home_win)}</b></span><span>Hòa <b>${pct(d.draw)}</b></span><span>Khách thắng <b>${pct(d.away_win)}</b></span></div>${stat(num(d.corners?.[0]),'Phạt góc kỳ vọng',num(d.corners?.[1]))}${stat(num(d.shots?.[0]),'Cú sút kỳ vọng',num(d.shots?.[1]))}<div class="chance-grid"><div class="chance">Tổng bàn từ 3 trở lên<strong>${pct(d.over25)}</strong></div><div class="chance">Hai đội cùng ghi bàn<strong>${pct(d.btts)}</strong></div></div>`;
  if (page === 'match') {
    let cells = '<table class="score-table"><caption>Hàng: bàn chủ nhà · cột: bàn khách. Hiển thị 0–6 bàn mỗi đội; còn xác suất ngoài bảng.</caption><thead><tr><th scope="col">Nhà / Khách</th>' + Array.from({length:7},(_,i) => '<th scope="col">'+i+'</th>').join('') + '</tr></thead><tbody>';
    for (let i=0;i<7;i++) cells += '<tr><th scope="row">'+i+'</th>' + Array.from({length:7},(_,j) => { const v = d.score_grid?.[i]?.[j]; return `<td style="background:rgba(157,195,87,${Math.min(1,clamp(v)*5+.04)})">${pct(v)}</td>`; }).join('') + '</tr>';
    $('side-card').innerHTML = '<div class="card-head"><div><div class="eyebrow">SCORE EXPLORER</div><h3>Không chỉ có một tỉ số.</h3><p class="muted">Xác suất cho từng kết quả có thể xảy ra.</p></div><span class="badge">POISSON</span></div>' + cells + '</tbody></table><div class="note">Màu đậm hơn biểu thị xác suất lớn hơn. Các ô đều có giá trị số để so sánh.</div>';
  } else {
    let side = '<div class="card-head"><div><div class="eyebrow">TITLE RACE</div><h3>Đường đua đang mở.</h3><p class="muted">Khả năng vô địch theo mô phỏng mùa giải.</p></div><span class="badge">TOP 5</span></div>';
    if (l.race?.table?.length) side += l.race.table.slice(0,5).map((row,i) => `<div class="race-row"><span class="rank">${String(i+1).padStart(2,'0')}</span><div class="team-row"><span class="team-name">${badge(row.team)}${esc(row.team)}</span><div class="track" aria-hidden="true"><span style="width:${clamp(row.title)*100}%"></span></div></div><span class="pct">${pct(row.title)}</span></div>`).join('') + '<button class="card-link" data-go="race">Toàn bộ cuộc đua <span aria-hidden="true">→</span></button>';
    else side += '<div class="empty">'+esc(l.race?.reason || 'Chưa đủ thành viên mùa giải để mô phỏng.')+'</div>';
    $('side-card').innerHTML = side + '<div class="note">Mô phỏng giữ sức mạnh đội bóng cố định; chưa áp dụng mọi luật đối đầu hoặc playoff.</div>';
  }
}
function renderRace() {
  const l = current(), race = l.race || {}, rows = race.table || [];
  $('csv').disabled = !rows.length;
  $('race-search').disabled = $('race-sort').disabled = !rows.length;
  $('race-sub').textContent = rows.length ? `${Number(race.simulations || 0).toLocaleString('vi-VN')} mô phỏng · ${race.remaining_matches} cặp đấu còn lại được suy ra` : 'Chưa đủ dữ liệu để mô phỏng mùa giải.';
  const query = normalize($('race-search').value), sort = $('race-sort').value;
  const filtered = rows.filter(row => normalize(row.team).includes(query)).slice().sort((a,b) => sort === 'team' ? a.team.localeCompare(b.team) : Number(b[sort])-Number(a[sort]));
  $('race-table').innerHTML = filtered.length ? '<table class="race-table"><thead><tr>'+['Đội bóng','Đã đá','Điểm','Vô địch','Top 4','Nhóm 3 cuối','Điểm kỳ vọng','P10 – P90'].map(header => '<th scope="col">'+header+'</th>').join('')+'</tr></thead><tbody>'+filtered.map(row => `<tr><td><span class="team-name">${badge(row.team)}${esc(row.team)}</span></td><td>${esc(row.played)}</td><td><strong>${esc(row.points)}</strong></td><td class="title-cell">${pct(row.title)}</td><td>${pct(row.top4)}</td><td>${pct(row.bottom3)}</td><td>${num(row.expected_points)}</td><td>${num(row.points_p10)} – ${num(row.points_p90)}</td></tr>`).join('')+'</tbody></table>' : '<div class="empty">'+esc(rows.length ? 'Không có đội phù hợp. Xóa tên tìm kiếm để xem lại bảng.' : race.reason || 'Chưa có dữ liệu mùa giải.')+'</div>';
  $('race-note').textContent = rows.length ? 'Kịch bản vòng tròn hai lượt; cặp đấu còn lại suy ra từ dữ liệu, chưa có ngày đấu chính thức. Top 4 và nhóm 3 cuối là nhóm thứ hạng, không khẳng định suất châu Âu hoặc xuống hạng. Khoảng P10–P90 phản ánh bất định kết quả theo mô hình cố định.' : 'Không hiển thị xác suất vô địch khi thiếu thành viên của mùa giải.';
}

// Pre-index source text once. Search never rebuilds league options or hidden screens.
const playersByLeague = new Map();
for (const player of MEDIA.players) {
  if (!playersByLeague.has(player.league)) playersByLeague.set(player.league, []);
  playersByLeague.get(player.league).push({...player, id:String(player.id), searchName:normalize(player.name)});
}
let favoritePlayers = new Set(), favoritesPersistent = false;
try {
  const saved = JSON.parse(localStorage.getItem('pitchops-favorites') || '[]');
  if (Array.isArray(saved)) favoritePlayers = new Set(saved.filter(id => typeof id === 'string'));
  localStorage.setItem('pitchops-favorites', JSON.stringify([...favoritePlayers])); favoritesPersistent = true;
} catch { /* Colab's isolated iframe intentionally disallows persistent browser storage. */ }
function positionGroup(player) {
  const value = (player.position || '').toLowerCase();
  if (value === 'gk' || value.includes('goalkeeper')) return 'GK';
  if (value === 'df' || /back|defen|sweeper/.test(value)) return 'DF';
  if (value === 'mf' || /midfield/.test(value)) return 'MF';
  if (value === 'fw' || /wing|forward|striker|attack/.test(value)) return 'FW';
  return 'other';
}
function renderPlayers(reset = false) {
  if (reset) playerLimit = 24;
  const code = leagueSelect.value, list = playersByLeague.get(code) || [], select = $('player-team');
  if (playerLeague !== code) {
    select.replaceChildren(new Option('Tất cả đội','all'), ...[...new Set(list.map(p => p.team))].sort().map(team => new Option(team,team)));
    playerLeague = code;
  }
  const query = normalize($('player-search').value), position = $('player-position').value;
  const filtered = list.filter(p => (select.value === 'all' || p.team === select.value) && (position === 'all' || positionGroup(p) === position) && p.searchName.includes(query) && (!$('favorite-only').checked || favoritePlayers.has(p.id)));
  $('player-grid').innerHTML = filtered.slice(0,playerLimit).map(p => `<article class="player-card">${imageBox(p,p.name,'face')}<h3>${esc(p.name)}</h3><div class="muted">${badge(p.team)} ${esc(p.team)}</div><span class="position-tag">${esc(p.position)} · #${esc(p.number || '—')}</span><div class="player-actions"><button class="profile-btn" data-profile="${esc(p.id)}">Xem hồ sơ ↗</button><button class="favorite ${favoritePlayers.has(p.id) ? 'selected' : ''}" data-favorite="${esc(p.id)}" aria-label="${favoritePlayers.has(p.id) ? 'Bỏ theo dõi' : 'Theo dõi'} ${esc(p.name)}" aria-pressed="${favoritePlayers.has(p.id)}">☆</button></div></article>`).join('') || `<div class="empty full">${list.length ? 'Không có cầu thủ phù hợp. Hãy đổi bộ lọc hoặc chọn Xóa bộ lọc.' : 'Chưa có hồ sơ cầu thủ của giải này. Đồng bộ danh mục trong Colab để cập nhật.'}</div>`;
  $('player-grid').querySelectorAll('.favorite.selected').forEach(button => { button.textContent = '★'; });
  $('more-players').classList.toggle('hidden', filtered.length <= playerLimit);
  $('player-coverage').textContent = `${filtered.length} / ${list.length} hồ sơ ở ${current().name} · ${favoritesPersistent ? 'Theo dõi lưu trên trình duyệt này' : 'Theo dõi chỉ giữ trong phiên xem này'} · Danh mục một phần theo API nguồn.`;
  $('artwork-credit').innerHTML = 'Ảnh: <a href="https://www.thesportsdb.com" target="_blank" rel="noopener noreferrer">TheSportsDB</a> và <a href="https://github.com/luukhopman/football-logos" target="_blank" rel="noopener noreferrer">Football Logos</a>. Quyền ảnh thuộc chủ sở hữu tương ứng. Cập nhật ' + esc(String(MEDIA.retrieved_at || 'chưa đồng bộ').slice(0,19).replace('T',' ')) + ' UTC.';
}
function openPlayer(id) {
  const player = (playersByLeague.get(leagueSelect.value) || []).find(p => p.id === id); if (!player) return;
  const url = safeHref(player.source_url, new Set(['www.thesportsdb.com','thesportsdb.com']));
  $('player-detail').innerHTML = imageBox(player,player.name,'face') + `<h2 id="profile-name">${esc(player.name)}</h2><div class="muted">${badge(player.team)} ${esc(player.team)} · ${esc(player.position)}</div>` + table(['Thông tin','Giá trị'], [['Quốc tịch',player.nationality || '—'],['Ngày sinh',player.born || '—'],['Chiều cao',player.height || '—'],['Số áo',player.number || '—']]) + '<p class="profile-credit">'+esc(player.credit || '')+'</p>' + (url ? `<a class="source-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Hồ sơ nguồn ↗</a>` : '');
  $('player-dialog').showModal();
}
function resetPlayers() {
  clearTimeout(searchTimer); $('player-search').value = ''; $('player-team').value = 'all'; $('player-position').value = 'all'; $('favorite-only').checked = false; renderPlayers(true);
}
function renderOps() {
  const report = DATA.metrics || {}, m = DATA.meta || {}, quality = DATA.quality || {};
  $('ops-summary').textContent = `Model: ${report.selected || '—'} · ${report.test?.matches || 0} trận test · Log loss ${num(report.test?.log_loss)} / baseline ${num(report.test_baseline?.log_loss)}. Lịch nền và phiên snapshot là hai trạng thái riêng; xem Actions để biết kết quả mới nhất.`;
  $('metrics-table').innerHTML = table(['Chỉ số test','Được chọn','Baseline'], ['log_loss','brier','goals_mae','accuracy'].map(key => [key,key === 'accuracy' ? pct(report.test?.[key]) : num(report.test?.[key]),key === 'accuracy' ? pct(report.test_baseline?.[key]) : num(report.test_baseline?.[key])]));
  const bins = report.test?.reliability || [];
  $('reliability').innerHTML = bins.length ? bins.map(bin => `<div class="bin" title="n=${esc(bin.n)}; dự báo ${pct(bin.predicted)}; quan sát ${pct(bin.observed)}"><span style="height:${clamp(bin.predicted)*100}%;background:#214e33"></span><span style="height:${clamp(bin.observed)*100}%;background:#b5d073"></span></div>`).join('') : '<div class="empty">Chưa có dữ liệu reliability.</div>';
  $('quality-table').innerHTML = table(['Kiểm tra','Giá trị'], [['Trùng trận',quality.duplicate_matches ?? '—'],['Thiếu nhãn bàn thắng',quality.missing_goal_labels ?? '—'],['Độ phủ phạt góc',pct(quality.optional_corner_coverage)],['Độ phủ cú sút',pct(quality.optional_shot_coverage)],['Ngày từ trận cuối',quality.snapshot_age_days ?? '—'],...(DATA.drift || []).map(row => ['Dịch chuyển '+row.feature,num(row.standardized_mean_shift)+' σ'])]);
  $('run-info').textContent = `RUN ${m.run_id || '—'}\nMODEL CODE ${m.code_commit || '—'}\nVIEW CODE ${m.view_code_commit || '—'}\nDATA SHA256 ${m.data_sha256 || '—'}\nPYTHON ${m.python || '—'} / SKLEARN ${m.sklearn || '—'}\nVALIDATION FROM ${report.validation_from || '—'}\nTEST FROM ${report.test_from || '—'}\nWORKSPACE ${m.workspace || 'runtime'}\nDRIVE ${m.persistent_drive ? 'write path configured' : 'not configured'}\nEXECUTION ${JSON.stringify(m.execution_context || {})}\nDELIVERY ${m.delivery || 'local snapshot'}`;
}
function renderActive() {
  updateContext();
  const l = current(); $('global-empty').classList.toggle('hidden', !!l || page === 'expert' || page === 'ops');
  if (page === 'ops') renderOps();
  if (!l) return;
  if (page === 'overview') renderOverview();
  if (page === 'overview' || page === 'match') renderMatch();
  if (page === 'race') renderRace();
  if (page === 'players') renderPlayers();
}
function routeHash() {
  const params = new URLSearchParams({page,league:leagueSelect.value});
  if (page !== 'expert' && $('home').value && $('away').value) { params.set('home',$('home').value); params.set('away',$('away').value); }
  return '#' + params.toString();
}
function saveRoute(push = false) {
  try { if (location.hash !== routeHash()) history[push ? 'pushState' : 'replaceState'](null,'',routeHash()); } catch { /* Isolated srcdoc still works without browser history access. */ }
}
function nav(next, focus = true, save = true) {
  page = Object.hasOwn(pages,next) ? next : 'overview';
  for (const id of ['overview-page','match-section','race-page','players-page','expert-page','ops-page']) $(id).classList.add('hidden');
  const hasClubData = !!current();
  if (page === 'overview' && hasClubData) { $('overview-page').classList.remove('hidden'); $('match-section').classList.remove('hidden'); }
  else if (page === 'match' && hasClubData) $('match-section').classList.remove('hidden');
  else if ((hasClubData || page === 'expert' || page === 'ops') && $(page+'-page')) $(page+'-page').classList.remove('hidden');
  document.querySelectorAll('.nav [data-page]').forEach(button => { const selected = button.dataset.page === page; button.classList.toggle('active',selected); if (selected) button.setAttribute('aria-current','page'); else button.removeAttribute('aria-current'); });
  renderActive(); if (save) saveRoute(true); if (focus) $('page-title').focus({preventScroll:true});
}
function restoreRoute() {
  if (location.hash === '#main-content') return;
  const params = new URLSearchParams(location.hash.slice(1));
  if (leagues[params.get('league')]) leagueSelect.value = params.get('league');
  chooseTeams(params.get('home'), params.get('away')); nav(params.get('page') || 'overview',false,false);
}
document.addEventListener('click', event => {
  const profile = event.target.closest('[data-profile]'), favorite = event.target.closest('[data-favorite]'), league = event.target.closest('[data-league]'), go = event.target.closest('[data-page],[data-go]');
  if (profile) openPlayer(profile.dataset.profile);
  if (favorite) {
    const id = favorite.dataset.favorite, wasFollowing = favoritePlayers.has(id); if (wasFollowing) favoritePlayers.delete(id); else favoritePlayers.add(id);
    try { localStorage.setItem('pitchops-favorites',JSON.stringify([...favoritePlayers])); } catch { favoritesPersistent = false; }
    renderPlayers();
    Array.from($('player-grid').querySelectorAll('[data-favorite]')).find(button => button.dataset.favorite === id)?.focus({preventScroll:true});
    $('ui-status').textContent = (wasFollowing ? 'Đã bỏ theo dõi.' : 'Đã thêm vào danh sách theo dõi.') + (favoritesPersistent ? '' : ' Chỉ lưu trong phiên xem hiện tại.');
  }
  if (league && leagues[league.dataset.league]) { leagueSelect.value = league.dataset.league; chooseTeams(); renderActive(); saveRoute(); }
  if (go) nav(go.dataset.page || go.dataset.go);
});
$('close-player').onclick = () => $('player-dialog').close();
$('more-players').onclick = () => { playerLimit += 24; renderPlayers(); };
$('reset-players').onclick = resetPlayers;
$('player-search').oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => renderPlayers(true),180); };
for (const id of ['player-team','player-position','favorite-only']) $(id).onchange = () => renderPlayers(true);
$('race-search').oninput = renderRace; $('race-sort').onchange = renderRace;
leagueSelect.onchange = () => { chooseTeams(); renderActive(); saveRoute(); };
function changeMatch() { if (page === 'overview') renderOverview(); renderMatch(); saveRoute(); }
for (const id of ['home','away']) $(id).onchange = changeMatch;
$('swap').onclick = () => { const home = $('home').value; $('home').value = $('away').value; $('away').value = home; changeMatch(); };
$('export').onclick = () => download('pitchops-'+(DATA.meta?.run_id || 'snapshot')+'.json',JSON.stringify(DATA,null,2),'application/json');
$('csv').onclick = () => { const rows = current()?.race?.table; if (!rows?.length) return; const headers = Object.keys(rows[0]); download('pitchops-title-race.csv','\uFEFF'+[headers.map(csvCell).join(','),...rows.map(row => headers.map(key => csvCell(row[key])).join(','))].join('\r\n'),'text/csv;charset=utf-8'); };
window.addEventListener('popstate',restoreRoute); window.addEventListener('hashchange',restoreRoute);
restoreRoute();
