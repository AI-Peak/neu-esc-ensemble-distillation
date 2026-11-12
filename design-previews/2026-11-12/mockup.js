'use strict';

const FIXTURE_TEXT = 'Nhân viên hỗ trợ thân thiện, nhưng cổng đăng ký học phần rất chậm và báo lỗi liên tục.';
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const format = (number, digits = 1) => new Intl.NumberFormat('vi-VN', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(number);
const signed = (number) => (number < 0 ? '−' : '+') + format(Math.abs(number));
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const announce = (message) => { $('#announcement').textContent = message; };
const goToEvidence = () => $('#evidence').scrollIntoView({ behavior: reducedMotion.matches ? 'instant' : 'smooth', block: 'start' });

const sentimentMeta = {
  positive: { name: 'Tích cực', color: '#39996a' },
  negative: { name: 'Tiêu cực', color: '#c76b5d' },
  neutral: { name: 'Trung tính', color: '#9aa7a0' },
  toxic: { name: 'Toxic', color: '#c88c3d' },
};

// These fixed records are design fixtures. No input is classified by this prototype.
const feedback = [
  [FIXTURE_TEXT, 'negative', 'Dịch vụ'],
  ['Đăng ký học phần rất chậm vào giờ cao điểm, cổng liên tục báo lỗi.', 'negative', 'Dịch vụ'],
  ['Cổng đăng ký học phần báo lỗi nên không vào được môn bắt buộc.', 'negative', 'Dịch vụ'],
  ['Trang đăng ký học phần tải chậm, gửi yêu cầu hỗ trợ vẫn chưa được trả lời.', 'negative', 'Dịch vụ'],
  ['Giờ cao điểm cổng báo lỗi, đăng ký học phần phải thử lại nhiều lần.', 'negative', 'Dịch vụ'],
  ['Phòng hỗ trợ phản hồi chậm về việc đăng ký học phần.', 'negative', 'Dịch vụ'],
  ['Thông tin học phí cập nhật chậm, hỏi bộ phận hỗ trợ chưa được giải đáp.', 'negative', 'Dịch vụ'],
  ['Thủ tục học bổng còn rườm rà, bộ phận hỗ trợ xử lý chậm.', 'negative', 'Dịch vụ'],
  ['Thông báo đổi lịch thi cập nhật quá muộn, hỏi hỗ trợ cũng không rõ.', 'negative', 'Dịch vụ'],
  ['Nhân viên hỗ trợ thân thiện, giải quyết đăng ký học phần nhanh.', 'positive', 'Dịch vụ'],
  ['Thông tin học phí rõ ràng, nhân viên hỗ trợ thân thiện.', 'positive', 'Dịch vụ'],
  ['Trả lời kiểu coi thường người khác, bộ phận hỗ trợ quá thiếu tôn trọng.', 'toxic', 'Dịch vụ'],
  ['Giảng viên giao nhiều bài tập nhưng tài liệu hướng dẫn chưa rõ ràng.', 'negative', 'Học tập'],
  ['Bài tập khó, giảng viên giải thích nhanh nên chưa dễ hiểu.', 'negative', 'Học tập'],
  ['Tài liệu học phần cập nhật chậm, bài tập không khớp nội dung.', 'negative', 'Học tập'],
  ['Giảng viên ít phản hồi bài tập, phần hướng dẫn chưa rõ ràng.', 'negative', 'Học tập'],
  ['Giảng viên trình bày rõ ràng, tài liệu dễ hiểu và bài tập sát nội dung.', 'positive', 'Học tập'],
  ['Bài tập giúp ôn bài tốt, giảng viên hỗ trợ rất thân thiện.', 'positive', 'Học tập'],
  ['Giảng viên giải thích dễ hiểu, tài liệu rõ ràng.', 'positive', 'Học tập'],
  ['Tài liệu và bài tập được giảng viên đăng lên hệ thống.', 'neutral', 'Học tập'],
  ['Thông báo lịch thi cập nhật chậm khiến sinh viên khó sắp xếp.', 'negative', 'Tin tức'],
  ['Thông báo học bổng rõ ràng, cập nhật đầy đủ điều kiện.', 'positive', 'Tin tức'],
  ['Thông báo: lịch thi được công bố vào thứ Hai.', 'neutral', 'Tin tức'],
  ['Thông báo học phí và học bổng đã có trên website.', 'neutral', 'Tin tức'],
].map(([text, sentiment, topic], index) => ({ id: index + 1, text, sentiment, topic, normalized: text.normalize('NFC').toLocaleLowerCase('vi') }));

const communities = [
  { id: 0, name: 'Đăng ký & hỗ trợ', detail: 'đăng ký học phần · chậm · hỗ trợ', color: '#4b9d78' },
  { id: 1, name: 'Giảng dạy & học tập', detail: 'giảng viên · bài tập · tài liệu', color: '#689bbd' },
  { id: 2, name: 'Thông tin & thủ tục', detail: 'thông báo · lịch thi · học phí', color: '#c0a15c' },
];

// Positions and communities are authored for the mockup; counts and links use the fixtures.
const terms = [
  ['registration', 'đăng ký học phần', 0, 300, 200],
  ['error', 'báo lỗi', 0, 160, 90],
  ['slow', 'chậm', 0, 465, 210],
  ['support', 'hỗ trợ', 0, 330, 340],
  ['friendly', 'thân thiện', 0, 185, 290],
  ['peak', 'giờ cao điểm', 0, 320, 65],
  ['lecturer', 'giảng viên', 1, 565, 110],
  ['clear', 'rõ ràng', 1, 660, 200],
  ['exercise', 'bài tập', 1, 590, 330],
  ['materials', 'tài liệu', 1, 690, 70],
  ['understandable', 'dễ hiểu', 1, 713, 295],
  ['notice', 'thông báo', 2, 92, 200],
  ['exam', 'lịch thi', 2, 65, 330],
  ['fees', 'học phí', 2, 165, 390],
  ['scholarship', 'học bổng', 2, 60, 105],
  ['updated', 'cập nhật', 2, 435, 70],
].map(([id, phrase, community, x, y]) => ({ id, phrase, community, x, y, records: feedback.filter((item) => item.normalized.includes(phrase)) }));
const termById = Object.fromEntries(terms.map((term) => [term.id, term]));
const state = { filter: {}, visible: 3, selectedTerm: null, selectedCommunity: null, analysisTimer: null };

function updateInput() {
  const text = $('#feedback').value;
  $('#character-count').textContent = `${text.length} / 5.000`;
  $('#analyze-button').disabled = !text.trim();
}

function showAnalysis(visible) {
  $('#prediction-content').hidden = !visible;
  $('#prediction-empty').hidden = visible;
  $('#attribution-content').hidden = !visible;
  $('#attribution-empty').hidden = visible;
}

function resetAsync() {
  window.clearTimeout(state.analysisTimer);
  state.analysisTimer = null;
  $('#analyze-button span').textContent = 'Phân tích';
}

$('#feedback').addEventListener('input', () => {
  resetAsync();
  updateInput();
  showAnalysis(false);
  $('#input-status').hidden = true;
  $('#restore-button').hidden = false;
});

$('#clear-button').addEventListener('click', () => {
  resetAsync();
  $('#feedback').value = '';
  updateInput();
  showAnalysis(false);
  $('#input-status').hidden = true;
  $('#restore-button').hidden = false;
  $('#feedback').focus();
});

$('#restore-button').addEventListener('click', () => {
  resetAsync();
  $('#feedback').value = FIXTURE_TEXT;
  updateInput();
  showAnalysis(true);
  $('#input-status').hidden = true;
  $('#restore-button').hidden = true;
  announce('Đã khôi phục phản hồi và kết quả minh họa.');
});

$('#analysis-form').addEventListener('submit', (event) => {
  event.preventDefault();
  resetAsync();
  const text = $('#feedback').value.trim();
  if (!text) return;
  if (text !== FIXTURE_TEXT) {
    showAnalysis(false);
    $('#input-status').textContent = 'Mockup chưa phân tích nội dung mới. Khôi phục phản hồi minh họa để xem thiết kế kết quả.';
    $('#input-status').hidden = false;
    $('#restore-button').hidden = false;
    return;
  }
  $('#analyze-button').disabled = true;
  $('#analyze-button span').textContent = 'Đang mở minh họa…';
  $('#input-status').hidden = true;
  showAnalysis(false);
  state.analysisTimer = window.setTimeout(() => {
    showAnalysis(true);
    resetAsync();
    updateInput();
    $('#restore-button').hidden = true;
    announce('Đã hiển thị kết quả dựng sẵn cho phản hồi minh họa.');
  }, 350);
});

const attribution = {
  friendly: { text: 'thân thiện', weight: 12.4 },
  slow: { text: 'rất chậm', weight: -28.6 },
  error: { text: 'báo lỗi liên tục', weight: -48.8 },
};

function selectAttribution(id) {
  const data = attribution[id];
  $$('[data-term]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.term === id)));
  $$('[data-row]').forEach((row) => row.classList.toggle('selected', row.dataset.row === id));
  $('#selection-detail span').textContent = `“${data.text}” · ${signed(data.weight)} điểm % · nghiêng ${data.weight > 0 ? 'tích cực' : 'tiêu cực'}`;
}

$$('[data-term]').forEach((button) => {
  button.addEventListener('click', () => selectAttribution(button.dataset.term));
  button.addEventListener('focus', () => selectAttribution(button.dataset.term));
});

const topicScores = [ ['Dịch vụ', 78.2], ['Học tập', 9.8], ['Hỏi đáp / chia sẻ', 4.1], ['Khác', 2.4], ['Tin tức', 1.8], ['Chuyện cá nhân', 1.2], ['Vấn đề xã hội', 1], ['Việc làm / tuyển dụng', .7], ['Câu lạc bộ / sự kiện', .5], ['Rác / quảng cáo', .3] ];
$('#topic-scores').innerHTML = topicScores.map(([name, score]) => `<div class="topic-score"><span>${name}</span><span class="topic-score-track"><i style="width:${score}%"></i></span><b>${format(score)}%</b></div>`).join('');

function setFilter(filter, scroll = false) {
  state.filter = filter;
  state.visible = 3;
  state.selectedTerm = filter.term || null;
  state.selectedCommunity = filter.community ?? null;
  renderEvidence();
  renderActiveSelection();
  updateNetworkSelection();
  if (scroll) goToEvidence();
}

function svgElement(tag, attributes = {}) {
  const element = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
  return element;
}

function renderDonut() {
  const counts = Object.fromEntries(Object.keys(sentimentMeta).map((key) => [key, feedback.filter((item) => item.sentiment === key).length]));
  const net = 100 * (counts.positive - counts.negative) / feedback.length;
  $('#net-sentiment').textContent = signed(net);
  const svg = $('#sentiment-donut');
  const circumference = 2 * Math.PI * 86;
  let offset = 0;
  Object.entries(sentimentMeta).forEach(([key, meta]) => {
    const fraction = counts[key] / feedback.length;
    const arc = svgElement('circle', { cx: 112, cy: 112, r: 86, stroke: meta.color, 'stroke-dasharray': `${Math.max(0, fraction * circumference - 3)} ${circumference}`, 'stroke-dashoffset': -offset, class: 'donut-segment', 'data-sentiment': key });
    const title = svgElement('title');
    title.textContent = `${meta.name}: ${counts[key]} phản hồi, ${format(100 * fraction)}%`;
    arc.append(title);
    arc.addEventListener('click', () => setFilter({ sentiment: key }, true));
    svg.append(arc);
    offset += fraction * circumference;
  });
  svg.setAttribute('aria-label', Object.entries(sentimentMeta).map(([key, meta]) => `${meta.name}: ${counts[key]} phản hồi`).join('; '));
  $('#distribution-legend').innerHTML = Object.entries(sentimentMeta).map(([key, meta]) => `<button type="button" class="legend-button" data-sentiment="${key}" aria-pressed="false"><i class="dot" style="background:${meta.color}"></i><span>${meta.name}</span><strong>${format(100 * counts[key] / feedback.length)}%</strong><small>${counts[key]} phản hồi</small></button>`).join('');
  $$('.legend-button').forEach((button) => button.addEventListener('click', () => setFilter({ sentiment: button.dataset.sentiment }, true)));
}

function renderAttention() {
  const topics = [...new Set(feedback.map((item) => item.topic))].map((name) => {
    const rows = feedback.filter((item) => item.topic === name);
    return { name, count: rows.length, negative: rows.filter((item) => item.sentiment === 'negative').length, toxic: rows.filter((item) => item.sentiment === 'toxic').length };
  }).sort((a, b) => b.negative - a.negative);
  $('#topic-attention').innerHTML = topics.map((topic) => `<button type="button" class="attention-row" data-topic="${topic.name}" aria-pressed="false"><span class="attention-row-head"><strong>${topic.name}</strong><span><b>${topic.negative}</b> <small>/ ${topic.count}</small></span><span class="attention-chevron" aria-hidden="true">↗</span></span><span class="attention-track"><span style="width:${100 * topic.negative / topic.count}%;background:#c78270"></span>${topic.toxic ? `<span style="width:${100 * topic.toxic / topic.count}%;background:#c39a55"></span>` : ''}</span><span class="attention-row-meta"><span>${format(100 * topic.negative / topic.count)}% tiêu cực</span><span class="toxic-note">${topic.toxic ? `${topic.toxic} Toxic riêng` : ''}</span></span></button>`).join('');
  $$('.attention-row').forEach((button) => button.addEventListener('click', () => setFilter({ sentiment: 'negative', topic: button.dataset.topic }, true)));
}

const edges = [];
terms.forEach((a, index) => {
  terms.slice(index + 1).forEach((b) => {
    const count = a.records.filter((record) => b.records.some((other) => other.id === record.id)).length;
    if (count) edges.push({ a, b, count });
  });
});
edges.sort((a, b) => b.count - a.count || a.a.id.localeCompare(b.a.id) || a.b.id.localeCompare(b.b.id));
const visibleEdges = edges.slice(0, 44);

function renderNetwork() {
  const svg = $('#term-network');
  const defs = svgElement('defs');
  const pattern = svgElement('pattern', { id: 'graph-dots', width: 24, height: 24, patternUnits: 'userSpaceOnUse' });
  pattern.append(svgElement('circle', { cx: 1, cy: 1, r: .65, fill: '#c6d5ca' }));
  defs.append(pattern);
  svg.append(defs, svgElement('rect', { x: 0, y: 0, width: 760, height: 430, fill: 'url(#graph-dots)', opacity: .5 }));
  visibleEdges.forEach((edge) => {
    const line = svgElement('line', { x1: edge.a.x, y1: edge.a.y, x2: edge.b.x, y2: edge.b.y, class: 'graph-edge', 'data-a': edge.a.id, 'data-b': edge.b.id, style: `stroke-width:${.65 + edge.count * .32}px` });
    svg.append(line);
  });
  terms.forEach((term) => {
    const radius = 6 + Math.sqrt(term.records.length) * 5.2;
    const group = svgElement('g', { class: 'graph-node', 'data-node': term.id, role: 'button', tabindex: 0, 'aria-label': `${term.phrase}: ${term.records.length} phản hồi. Chọn để xem liên hệ.`, 'aria-pressed': 'false' });
    const circle = svgElement('circle', { cx: term.x, cy: term.y, r: radius, fill: communities[term.community].color });
    const text = svgElement('text', { x: term.x, y: term.y + radius + 19, 'text-anchor': 'middle' });
    text.textContent = term.phrase;
    const title = svgElement('title');
    title.textContent = `${term.phrase} · ${term.records.length} phản hồi`;
    group.append(title, circle, text);
    group.addEventListener('click', () => setFilter({ term: term.id }));
    group.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setFilter({ term: term.id }); }
    });
    svg.append(group);
  });
  $('#network-count').textContent = `${terms.length} cụm từ · ${visibleEdges.length} liên kết nổi bật`;
  $('#community-list').innerHTML = communities.map((community) => `<button type="button" class="community-button" data-community="${community.id}" aria-pressed="false"><i class="community-swatch" style="background:${community.color}"></i><span><strong>${community.name}</strong><small>${community.detail}</small></span></button>`).join('');
  $('#mobile-term').innerHTML += terms.map((term) => `<option value="${term.id}">${term.phrase} (${term.records.length})</option>`).join('');
  $('#mobile-term').addEventListener('change', (event) => setFilter(event.target.value ? { term: event.target.value } : {}));
  $$('.community-button').forEach((button) => button.addEventListener('click', () => setFilter({ community: Number(button.dataset.community) })));
  $('#network-reset').addEventListener('click', () => setFilter({}));
  $('#show-node-evidence').addEventListener('click', () => {
    if (state.selectedTerm) setFilter({ term: state.selectedTerm }, true);
    else if (state.selectedCommunity !== null) setFilter({ community: state.selectedCommunity }, true);
    else setFilter({ term: 'registration' }, true);
  });
  updateNetworkSelection();
}

function updateNetworkSelection() {
  $('#mobile-term').value = state.selectedTerm || '';
  $('#term-network').classList.toggle('has-term-selection', Boolean(state.selectedTerm));
  const related = new Set();
  if (state.selectedTerm) {
    related.add(state.selectedTerm);
    visibleEdges.forEach((edge) => {
      if (edge.a.id === state.selectedTerm) related.add(edge.b.id);
      if (edge.b.id === state.selectedTerm) related.add(edge.a.id);
    });
  } else if (state.selectedCommunity !== null) {
    terms.filter((term) => term.community === state.selectedCommunity).forEach((term) => related.add(term.id));
  }
  $$('[data-node]').forEach((group) => {
    const id = group.dataset.node;
    const selected = id === state.selectedTerm || (state.selectedCommunity !== null && termById[id].community === state.selectedCommunity);
    group.classList.toggle('selected', selected);
    group.classList.toggle('dim', related.size > 0 && !related.has(id));
    group.setAttribute('aria-pressed', String(selected));
  });
  $$('.graph-edge').forEach((line) => {
    const connected = state.selectedTerm ? (line.dataset.a === state.selectedTerm || line.dataset.b === state.selectedTerm) : (related.has(line.dataset.a) && related.has(line.dataset.b));
    line.classList.toggle('active', connected);
    line.classList.toggle('dim', related.size > 0 && !connected);
  });
  $$('.community-button').forEach((button) => button.setAttribute('aria-pressed', String(Number(button.dataset.community) === state.selectedCommunity)));
  if (state.selectedCommunity !== null) {
    const community = communities[state.selectedCommunity];
    const matching = filteredFeedback();
    $('.network-insight .field-label').textContent = 'Nhóm từ được chọn';
    $('#selected-node-label').textContent = community.name;
    $('#selected-node-description').textContent = `${matching.length} / ${feedback.length} phản hồi chứa ít nhất một cụm trong nhóm này.`;
  } else {
    const term = termById[state.selectedTerm || 'registration'];
    $('.network-insight .field-label').textContent = state.selectedTerm ? 'Cụm từ được chọn' : 'Một cụm từ nổi bật';
    $('#selected-node-label').textContent = term.phrase;
    const negative = term.records.filter((item) => item.sentiment === 'negative').length;
    $('#selected-node-description').textContent = `Xuất hiện trong ${term.records.length} phản hồi, trong đó có ${negative} phản hồi tiêu cực.`;
  }
}

function filteredFeedback() {
  return feedback.filter((item) => {
    if (state.filter.sentiment && item.sentiment !== state.filter.sentiment) return false;
    if (state.filter.topic && item.topic !== state.filter.topic) return false;
    if (state.filter.term && !termById[state.filter.term].records.some((record) => record.id === item.id)) return false;
    if (state.filter.community !== undefined && !terms.some((term) => term.community === state.filter.community && term.records.some((record) => record.id === item.id))) return false;
    return true;
  });
}

function renderActiveSelection() {
  $$('[data-sentiment]').forEach((element) => {
    const selected = element.dataset.sentiment === state.filter.sentiment;
    element.classList.toggle('selected', selected);
    if (element.tagName === 'BUTTON') element.setAttribute('aria-pressed', String(selected));
  });
  $$('.attention-row').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.topic === state.filter.topic)));
}

function highlightedText(item) {
  if (!state.filter.term) return escapeHtml(item.text);
  const phrase = termById[state.filter.term].phrase;
  const index = item.normalized.indexOf(phrase);
  if (index < 0) return escapeHtml(item.text);
  return `${escapeHtml(item.text.slice(0, index))}<mark>${escapeHtml(item.text.slice(index, index + phrase.length))}</mark>${escapeHtml(item.text.slice(index + phrase.length))}`;
}

function renderEvidence() {
  const records = filteredFeedback();
  const chips = [];
  if (state.filter.sentiment) chips.push(sentimentMeta[state.filter.sentiment].name);
  if (state.filter.topic) chips.push(`Chủ đề: ${state.filter.topic}`);
  if (state.filter.term) chips.push(`Có cụm “${termById[state.filter.term].phrase}”`);
  if (state.filter.community !== undefined) chips.push(`Nhóm: ${communities[state.filter.community].name}`);
  $('#active-filters').innerHTML = chips.map((label) => `<span class="filter-chip">${escapeHtml(label)}</span>`).join('');
  $('#clear-filters').hidden = chips.length === 0;
  $('#evidence-description').textContent = chips.length ? `${records.length} phản hồi khớp lựa chọn · trong bộ 24 phản hồi minh họa` : '24 phản hồi minh họa · chọn biểu đồ hoặc cụm từ để lọc';
  $('#evidence-list').innerHTML = records.slice(0, state.visible).map((item) => `<article class="evidence-row"><span class="evidence-id">#${String(item.id).padStart(2, '0')}</span><p class="evidence-text">${highlightedText(item)}</p><div class="evidence-meta"><span class="sentiment-badge badge-${item.sentiment}"><i class="dot ${item.sentiment}-dot"></i>${sentimentMeta[item.sentiment].name}</span><span>${item.topic}</span></div></article>`).join('') || '<p class="no-evidence">Không có phản hồi phù hợp với lựa chọn này.</p>';
  $('#load-more').hidden = state.visible >= records.length;
  if (chips.length) announce(`Có ${records.length} phản hồi khớp lựa chọn. Xem tại phần Phản hồi để đối chiếu.`);
}

$('#clear-filters').addEventListener('click', () => setFilter({}));
$('#load-more').addEventListener('click', () => { state.visible += 3; renderEvidence(); });
updateInput();
renderDonut();
renderAttention();
renderNetwork();
renderEvidence();

// Local anchors keep the mockup independent from the production app routes.
const navObserver = new IntersectionObserver((entries) => {
  entries.filter((entry) => entry.isIntersecting).forEach((entry) => {
    $$('.header-inner nav a').forEach((link) => link.classList.toggle('nav-current', link.hash === '#' + entry.target.id));
  });
}, { rootMargin: '-10% 0px -65% 0px', threshold: 0 });
['analysis', 'overview', 'network'].forEach((id) => navObserver.observe(document.getElementById(id)));
