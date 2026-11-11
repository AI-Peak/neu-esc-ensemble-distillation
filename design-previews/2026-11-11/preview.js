const icons = {
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  file:'<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>',
  review:'<path d="M9 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4M9 3h6v4H9zM15 12l5-5 2 2-5 5-3 1zM7 12h3M7 16h3"/>',
  zap:'<path d="m13 2-9 12h7l-1 8 10-12h-7z"/>',
  chart:'<path d="M4 3v17h17M8 15v-4M13 15V7M18 15V4"/>',
  arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
  right:'<path d="m9 5 7 7-7 7"/>',
  left:'<path d="m15 5-7 7 7 7"/>',
  shield:'<path d="m12 3 8 3v6c0 4-4 7-8 9-4-2-8-5-8-9V6z"/><path d="m8 12 3 3 5-6"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  download:'<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  search:'<circle cx="10" cy="10" r="6.5"/><path d="m15 15 6 6"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v1"/>',
  signal:'<path d="m3 15 4-4 4 3 5-8 5 3M3 21h18"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
  folder:'<path d="M3 7V5h7l2 2h9v13H3z"/>',
  chat:'<path d="M21 11a8 8 0 0 1-8 8H6l-4 3V11a9 9 0 0 1 19 0zM7 10h10M7 14h6"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.file}</svg>`;
const page = document.body.dataset.page || 'overview';
const pageTitle = {overview:'Tổng quan',review:'Rà soát phản hồi',quick:'Thử một câu'}[page];
const nav = (id,href,label,name,count='') => `<a href="${href}" ${page===id?'class="active" aria-current="page"':''}>${icon(name)}<span>${label}</span>${count?`<span class="nav-count">${count}</span>`:''}</a>`;
const tag = (text,tone='') => `<span class="tag ${tone}">${text}</span>`;
const footer = `<footer class="page-foot"><span>Thiết kế xem trước · NEU-ESC Feedback Workspace</span><span>Dữ liệu minh họa, chưa kết nối model.</span></footer>`;

function shell(content) {
  return `<a href="#main" class="skip">Đến nội dung chính</a>
  <div class="preview-bar"><strong>MOCKUP · Phong cách sáng / xanh teal</strong><span>${icon('info')} Bạn có thể chuyển màn và thử các nút minh họa.</span></div>
  <div class="shell">
    <aside class="sidebar">
      <a class="brand" href="index.html"><span>NE</span><span><strong>NEU—ESC</strong><small>Không gian phản hồi</small></span></a>
      <div><p class="nav-label">Không gian làm việc</p><nav class="nav-items" aria-label="Điều hướng mockup">
        ${nav('overview','index.html','Tổng quan','grid')}
        ${nav('review','review.html','Rà soát phản hồi','review','9')}
        ${nav('quick','quick-analysis.html','Thử một câu','zap')}
        <button data-toast="Mockup này tập trung vào ba màn làm việc chính. Báo cáo nghiên cứu sẽ giữ nội dung hiện có.">${icon('chart')}<span>Báo cáo nghiên cứu</span></button>
      </nav></div>
      <div class="sidebar-dataset"><p class="nav-label">Bộ phản hồi đang xem</p><a href="index.html" class="dataset-mini">${icon('folder')}<span><strong>Phản hồi sinh viên</strong><small>24 phản hồi · dữ liệu mẫu</small></span></a></div>
      <div class="sidebar-bottom"><div>${icon('shield')}Không gian riêng của bạn</div><p>Thiết kế cho ứng dụng chạy local.<br>Bạn quyết định nhãn cuối cùng.</p></div>
    </aside>
    <div class="workspace"><header class="topbar"><div class="breadcrumbs"><a href="index.html">Bộ phản hồi</a>${icon('right')}<strong>${pageTitle}</strong></div><div class="top-tools"><span>Bản thiết kế chờ duyệt</span><span class="avatar" aria-label="Tài khoản mẫu">NE</span></div></header>
      <main id="main">${content}${footer}</main>
    </div>
  </div><div class="toast" role="status" aria-live="polite" hidden></div>`;
}

function overview() {
  const topics=[['Dịch vụ',6,4,'66,7%',67],['Học tập',8,2,'25,0%',25],['Việc làm / tuyển dụng',3,1,'33,3%',33],['Câu lạc bộ / sự kiện',4,0,'0%',0],['Khác',3,0,'0%',0]];
  return `<header class="page-head"><div><h1>Tổng quan phản hồi</h1><p>Phản hồi sinh viên <span aria-hidden="true">/</span> Học kỳ I · 2026–2027 ${tag('Bộ mẫu','outline')}</p></div><div class="actions"><button data-toast="Đây là bản thiết kế. Chức năng xuất CSV của app thật vẫn được giữ.">${icon('download')}Xuất CSV</button><a class="btn primary" href="review.html">Xem phản hồi ${icon('arrow')}</a></div></header>
  <section class="metrics" aria-label="Tóm tắt dữ liệu minh họa">
    <div class="metric"><div class="metric-top">${icon('chat')}Tổng phản hồi</div><div class="metric-value"><strong>24</strong><span>câu tiếng Việt</span></div><div class="metric-foot">24/24 đã phân tích</div></div>
    <div class="metric"><div class="metric-top">${icon('signal')}Cần đối chiếu tín hiệu</div><div class="metric-value"><strong>9</strong><span>phản hồi</span></div><a class="metric-foot text-link" href="review.html">Mở hàng chờ ${icon('arrow')}</a></div>
    <div class="metric"><div class="metric-top">${icon('chart')}Cảm xúc tiêu cực</div><div class="metric-value"><strong>7</strong><span>/ 24 câu có nhãn</span></div><div class="metric-foot">29,2% trong bộ dữ liệu mẫu</div></div>
    <div class="metric"><div class="metric-top">${icon('check')}Đã rà soát</div><div class="metric-value"><strong>5</strong><span>phản hồi</span></div><div class="metric-foot">Nhãn duyệt được lưu riêng</div></div>
  </section>
  <div class="insight"><span class="icon-wrap">${icon('signal')}</span><div><strong>Bắt đầu từ chủ đề Dịch vụ</strong><p>4 trong 6 phản hồi có cảm xúc tiêu cực. Mở từng câu để xem nội dung cụ thể.</p></div><a class="text-link" href="review.html?topic=service">Rà soát 4 phản hồi ${icon('arrow')}</a></div>
  <div class="overview-grid">
    <section class="panel"><header class="panel-head"><div><h2>Chủ đề cần chú ý</h2><p>Ưu tiên theo số phản hồi tiêu cực.</p></div><label class="sr-only" for="label-source">Nguồn nhãn</label><select id="label-source"><option>Đã duyệt + AI</option><option>Chỉ dự đoán AI gốc</option></select></header>
      <div class="table-scroll"><table><thead><tr><th>Chủ đề</th><th>Số câu</th><th>Tiêu cực</th><th>Tỷ lệ</th><th><span class="sr-only">Thao tác</span></th></tr></thead><tbody>${topics.map(([name,count,negative,percent,width])=>`<tr><td><span class="topic-name"><span class="topic-mark"></span>${name}</span>${count<5?'<span class="small muted">Ít dữ liệu</span>':''}</td><td>${count}</td><td>${negative}</td><td><div class="bar-cell"><span class="mini-bar"><span style="width:${width}%"></span></span>${percent}</div></td><td><a class="table-link" href="review.html${name==='Dịch vụ'?'?topic=service':''}" aria-label="Xem phản hồi chủ đề ${name}">${icon('right')}</a></td></tr>`).join('')}</tbody></table></div>
      <div class="panel-foot">24/24 câu có đủ hai nhãn. Toxic: 0 · Đếm riêng, không gộp vào Tiêu cực.</div>
    </section>
    <section class="panel sentiment-panel"><header class="panel-head"><div><h2>Phân bố cảm xúc</h2><p>Cái nhìn chung về bộ phản hồi</p></div></header><div class="panel-content"><div class="donut-row"><div class="donut" role="img" aria-label="11 tích cực, 6 trung tính, 7 tiêu cực"><div class="donut-inner"><strong>24</strong><span>phản hồi</span></div></div></div><div class="legend">${[['Tích cực','11','45,8%','#198774'],['Trung tính','6','25,0%','#d5b57b'],['Tiêu cực','7','29,2%','#cd7768']].map(([name,n,p,c])=>`<div class="legend-row"><span class="legend-dot" style="background:${c}"></span><span>${name}</span><strong>${n}</strong><small>${p}</small></div>`).join('')}</div><p class="note">Đọc phản hồi cụ thể trước khi kết luận. Một tỷ lệ cao với ít mẫu có thể chưa phản ánh toàn bộ vấn đề.</p></div></section>
  </div>
  <section class="panel followup"><header class="panel-head"><div><h2>Nên xem tiếp</h2><p>Các phản hồi có tín hiệu cần người đối chiếu.</p></div><a class="text-link small" href="review.html">Xem hàng chờ ${icon('arrow')}</a></header>
    <a class="feedback-link" href="review.html"><span class="row-id">D06</span><div><p>Cổng đăng ký học phần báo lỗi liên tục, mình chưa đăng ký được môn bắt buộc.</p><small>Dịch vụ · Nhãn cảm xúc dẫn đầu có điểm dưới ngưỡng</small></div>${tag('Model phân vân','amber')}${icon('right')}</a>
    <a class="feedback-link" href="review.html?item=D08"><span class="row-id">D08</span><div><p>Nhân viên hỗ trợ nhiệt tình nhưng thời gian chờ xử lý khá lâu.</p><small>Dịch vụ · Hai nhãn cảm xúc có điểm gần nhau</small></div>${tag('Cần đối chiếu','amber')}${icon('right')}</a>
  </section>`;
}

const feedback=[
 {id:'D06',topic:'Dịch vụ',label:'Tiêu cực',text:'Cổng đăng ký học phần báo lỗi liên tục, mình chưa đăng ký được môn bắt buộc.',reason:'Điểm nhãn dẫn đầu thấp',flagged:true,score:'59,5%',topicScore:'69,8%'},
 {id:'D08',topic:'Dịch vụ',label:'Tiêu cực',text:'Nhân viên hỗ trợ nhiệt tình nhưng thời gian chờ xử lý khá lâu.',reason:'Hai nhãn có điểm gần nhau',flagged:true,score:'52,1%',topicScore:'78,0%'},
 {id:'D10',topic:'Dịch vụ',label:'Tiêu cực',text:'Cổng thanh toán học phí hay bị ngắt kết nối vào buổi tối.',reason:'Chưa rà soát',flagged:false,score:'91,2%',topicScore:'88,4%'},
 {id:'D22',topic:'Dịch vụ',label:'Tiêu cực',text:'Mình đã gửi yêu cầu cấp giấy xác nhận nhưng chưa nhận được phản hồi.',reason:'Chưa rà soát',flagged:false,score:'87,3%',topicScore:'82,0%'},
 {id:'D14',topic:'Học tập',label:'Trung tính',text:'Nội dung học phần khá hữu ích, mình mong có thêm bài tập thực hành.',reason:'Hai nhãn có điểm gần nhau',flagged:true,score:'48,5%',topicScore:'70,2%'},
 {id:'D01',topic:'Học tập',label:'Tích cực',text:'Giảng viên giải thích bài tập rõ ràng, mình hiểu bài dễ hơn.',reason:'Đã rà soát',flagged:false,reviewed:true,score:'92,4%',topicScore:'88,6%'},
];
let selectedId=new URLSearchParams(location.search).get('item') || 'D06';
let listMode=new URLSearchParams(location.search).get('topic')==='service'?'service':'all';
let reviewSearch='';
let detailTab='review';
const draftNotes=new Map();

function review() {
 return `<header class="page-head"><div><h1>Rà soát phản hồi</h1><p>Đọc ngữ cảnh, đối chiếu dự đoán và lưu quyết định của bạn.</p></div>${tag('<span class="dot"></span> Phản hồi sinh viên · bộ mẫu','green')}</header>
 <div class="review-toolbar"><div class="tabs" role="tablist" aria-label="Lọc phản hồi"><button role="tab" data-filter="all" aria-selected="true">Tất cả <span class="count">6 mẫu</span></button><button role="tab" data-filter="flagged" aria-selected="false">Cần đối chiếu <span class="count">3</span></button><button role="tab" data-filter="reviewed" aria-selected="false">Đã duyệt</button></div><label class="searchbox">${icon('search')}<span class="sr-only">Tìm trong phản hồi mẫu</span><input id="review-search" placeholder="Tìm trong phản hồi…" type="search"></label></div>
 <div class="review-grid"><section class="panel"><div class="review-list-head"><strong id="list-title">Danh sách phản hồi mẫu</strong><span id="list-count"></span></div><div class="review-list" id="review-list"></div><div class="panel-foot">Chọn một câu để xem và rà soát ở bên cạnh.</div></section><section class="panel" id="detail-panel" aria-label="Chi tiết phản hồi"></section></div>`;
}

function renderList() {
 const visible=feedback.filter(r=>(listMode==='all'||(listMode==='service'&&r.topic==='Dịch vụ')||(listMode==='flagged'&&r.flagged&&!r.reviewed)||(listMode==='reviewed'&&r.reviewed))&&r.text.toLocaleLowerCase('vi').includes(reviewSearch.toLocaleLowerCase('vi')));
 document.getElementById('list-title').textContent=listMode==='service'?'Dịch vụ · phản hồi tiêu cực':'Danh sách phản hồi mẫu';
 document.getElementById('list-count').textContent=visible.length+' câu';
 document.getElementById('review-list').innerHTML=visible.length?visible.map(r=>`<button class="feedback-row ${r.id===selectedId?'active':''}" data-item="${r.id}" aria-pressed="${r.id===selectedId}"><div class="feedback-row-top"><span class="row-id">${r.id}</span>${tag(r.topic)}</div><p>${r.text}</p><div class="feedback-row-bottom">${icon(r.reviewed?'check':r.flagged?'signal':'clock')}<span>${r.reviewed?'Đã rà soát':r.reason}</span></div></button>`).join(''):'<p class="list-empty">Không có phản hồi phù hợp.</p>';
 document.querySelectorAll('[data-filter]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.filter===listMode)));
}

function renderDetail() {
 const r=feedback.find(r=>r.id===selectedId)||feedback[0];selectedId=r.id;
 document.getElementById('detail-panel').innerHTML=`<header class="detail-heading"><div><h2>Phản hồi ${r.id}</h2>${tag(r.reviewed?'Đã rà soát':'Chưa đối chiếu',r.reviewed?'green':'amber')}</div><div><small>${feedback.indexOf(r)+1} / 6 mẫu</small><button class="icon-btn" data-step="-1" aria-label="Phản hồi trước">${icon('left')}</button><button class="icon-btn" data-step="1" aria-label="Phản hồi tiếp theo">${icon('right')}</button></div></header>
 <div class="detail-body"><div class="source-label"><span>Văn bản gốc</span><span>NEU · Thảo luận sinh viên</span></div><p class="source-quote">${r.id==='D06'?r.text.replace('báo lỗi liên tục','<mark>báo lỗi liên tục</mark>'):r.text}</p>
 <div class="detail-tabs" role="tablist" aria-label="Công cụ đối chiếu"><button role="tab" data-detail-tab="review" aria-selected="${detailTab==='review'}">Dự đoán & rà soát</button><button role="tab" data-detail-tab="explore" aria-selected="${detailTab==='explore'}">${icon('zap')}Khám phá dự đoán</button></div>
 <div class="tab-content" ${detailTab!=='review'?'hidden':''}><div class="predictions"><div class="prediction-box ${r.label==='Tiêu cực'?'negative':''}"><label>AI dự đoán · Cảm xúc</label><div class="value"><strong>${r.label}</strong><span>${r.score}</span></div></div><div class="prediction-box"><label>AI dự đoán · Chủ đề</label><div class="value"><strong>${r.topic}</strong><span>${r.topicScore}</span></div></div></div>
 ${r.flagged?`<div class="signal-callout">${icon('info')}<div><strong>Cảm xúc cần đối chiếu</strong>${r.reason}. Đọc toàn bộ câu để quyết định nhãn phù hợp.</div></div>`:'<p class="model-disclaimer">Điểm model chưa hiệu chuẩn. Không có cờ không đồng nghĩa dự đoán đúng.</p>'}
 <div class="form-heading"><h3>Quyết định của bạn</h3><span>Lưu tách riêng dự đoán AI</span></div><div class="form-grid"><label>Nhãn cảm xúc<select id="review-sentiment">${['Trung tính','Tích cực','Tiêu cực','Ngôn từ độc hại'].map(x=>`<option ${x===(r.manualLabel||r.label)?'selected':''}>${x}</option>`).join('')}</select></label><label>Nhãn chủ đề<select id="review-topic">${['Dịch vụ','Học tập','Việc làm / tuyển dụng','Câu lạc bộ / sự kiện','Khác'].map(x=>`<option ${x===(r.manualTopic||r.topic)?'selected':''}>${x}</option>`).join('')}</select></label></div>
 <label class="review-note">Ghi chú rà soát<textarea id="review-note" rows="2" placeholder="Lý do chọn nhãn hoặc điều cần lưu ý…"></textarea></label><div class="detail-actions"><span class="muted">Thao tác minh họa</span><div class="actions"><button data-save="stay">Lưu nhãn</button><button class="primary" data-save="next">Lưu & câu tiếp ${icon('arrow')}</button></div></div></div>
 <div class="tab-content" ${detailTab!=='explore'?'hidden':''}><h3>Thử bỏ một cụm từ</h3><p class="explore-copy">Quan sát dự đoán thay đổi khi bỏ một đoạn. Văn bản gốc được giữ nguyên.</p>${r.id==='D06'?`<label for="phrase">Cụm từ cần bỏ</label><div class="explore-control"><input id="phrase" value="báo lỗi liên tục" readonly><button class="primary" data-experiment>${icon('zap')}Xem ví dụ</button></div><div class="comparison" id="comparison" hidden><small>Câu sau khi bỏ cụm từ</small><p>Cổng đăng ký học phần , mình chưa đăng ký được môn bắt buộc.</p><div class="compare-values"><div><small>Cảm xúc câu gốc</small><strong class="negative-text">Tiêu cực · 59,5%</strong></div>${icon('arrow')}<div><small>Cảm xúc biến thể</small><strong>Trung tính · 98,8%</strong></div></div><table><thead><tr><th>Nhãn</th><th>Gốc</th><th>Biến thể</th></tr></thead><tbody><tr><td>Tiêu cực</td><td>59,5%</td><td>1,1%</td></tr><tr><td>Trung tính</td><td>40,1%</td><td>98,8%</td></tr></tbody></table></div><p class="note">Ví dụ minh họa từ kịch bản demo D06. Thay đổi điểm cho thấy độ nhạy với đầu vào, không chứng minh quan hệ nhân quả.</p>`:'<div class="note">Mockup minh họa thao tác này ở câu D06.</div><button data-item="D06" style="margin-top:14px">Mở câu D06 để xem ví dụ</button>'}</div></div>`;
 document.getElementById('review-note').value=draftNotes.get(r.id)||'';
}

const examples=[
 {name:'Dịch vụ sinh viên',text:feedback[0].text,label:'Tiêu cực',topic:'Dịch vụ',score:'59,5%',topicScore:'69,8%',scores:[40.1,.3,59.5,.1]},
 {name:'Trải nghiệm học tập',text:feedback[5].text,label:'Tích cực',topic:'Học tập',score:'92,4%',topicScore:'88,6%',scores:[5.2,92.4,2.3,.1]},
 {name:'Một thông báo',text:'Thư viện mở cửa đến chín giờ tối.',label:'Trung tính',topic:'Tin tức',score:'96,1%',topicScore:'81,0%',scores:[96.1,2.3,1.5,.1]},
];
let exampleIndex=0;
let waitingTimer;
function quick() {
 return `<header class="page-head"><div><h1>Thử một câu</h1><p>Đọc dự đoán cảm xúc và chủ đề trước khi phân tích cả bộ dữ liệu.</p></div>${tag('Màn tương tác minh họa','outline')}</header>
 <div class="quick-grid"><div><section class="panel quick-input-panel"><header class="panel-head"><div><h2>Bạn muốn phân tích câu nào?</h2><p>Nhập nội dung tiếng Việt, giữ nguyên cách diễn đạt.</p></div>${icon('chat')}</header><div class="panel-content"><div class="profile-choice" role="group" aria-label="Loại nội dung"><button class="chosen" aria-pressed="true">${icon('check')}Thảo luận sinh viên · NEU</button><button disabled>UIT <small>Chưa có model</small></button></div><label class="sr-only" for="quick-text">Văn bản cần phân tích</label><div class="editor-wrap"><textarea id="quick-text" spellcheck="false">${examples[0].text}</textarea></div><div class="editor-meta"><span>Văn bản gốc của bạn được giữ nguyên</span><span id="char-count"></span></div><p class="field-hint">Hoặc chọn một câu mẫu để xem cách trình bày</p><div class="examples">${examples.map((e,i)=>`<button data-example="${i}" class="${i===0?'selected':''}">${e.name}</button>`).join('')}</div><div class="quick-submit"><span>Kết quả bên phải là dữ liệu minh họa.</span><button class="primary" id="preview-analyze">${icon('zap')}Phân tích câu ${icon('arrow')}</button></div></div></section><div class="quick-support">${icon('shield')}<div><strong>Bạn luôn là người quyết định nhãn cuối cùng</strong><p>AI hỗ trợ đọc phản hồi. Kết quả và các điểm số cần được đối chiếu với nội dung thực tế.</p></div></div></div>
 <div><section class="panel result-panel" aria-label="Kết quả phân tích mẫu"><header class="panel-head"><div><h2 id="result-heading">Kết quả minh họa</h2><p>Hai tác vụ, hiển thị riêng biệt</p></div>${tag('Dữ liệu mẫu','green')}</header><div class="panel-content" id="quick-result"></div></section><div class="state-switch"><button id="show-waiting">${icon('clock')}Xem thiết kế lúc đang chờ</button></div></div></div>`;
}

function renderResult() {
 const e=examples[exampleIndex];
 document.getElementById('result-heading').textContent='Kết quả minh họa';
 document.getElementById('quick-result').innerHTML=`<div class="predictions"><div class="prediction-box ${e.label==='Tiêu cực'?'negative':''}"><label>Cảm xúc</label><div class="value"><strong>${e.label}</strong><span>${e.score}</span></div></div><div class="prediction-box"><label>Chủ đề</label><div class="value"><strong>${e.topic}</strong><span>${e.topicScore}</span></div></div></div><div class="score-title"><h3>Điểm từng nhãn cảm xúc</h3><span>Điểm softmax · chưa hiệu chuẩn</span></div>${['Trung tính','Tích cực','Tiêu cực','Toxic'].map((label,i)=>`<div class="score-row"><span>${label}</span><div class="score-track"><div class="score-fill ${e.scores[i]===Math.max(...e.scores)?'leading':''}" style="width:${Math.max(e.scores[i],.5)}%"></div></div><strong>${e.scores[i].toFixed(1).replace('.',',')}%</strong></div>`).join('')}<div class="note">${exampleIndex===0?'Điểm nhãn cảm xúc dẫn đầu dưới ngưỡng 0,60. Câu này cần người rà soát lại.':'Không có tín hiệu phân vân trong ví dụ này. Bạn vẫn nên đối chiếu dự đoán với nội dung câu.'}</div><div class="result-footer"><a class="text-link" href="review.html">Xem màn rà soát ${icon('arrow')}</a><button data-toast="Trong app thật, nút này sẽ lưu văn bản vào bộ phản hồi bạn chọn.">${icon('plus')}Lưu câu vào bộ</button></div><p class="model-disclaimer">Số liệu ở đây chỉ dùng để duyệt giao diện, không được suy luận từ ô nhập.</p>`;
 document.getElementById('show-waiting').textContent='Xem thiết kế lúc đang chờ';
}

function showWaiting(autoFinish=false) {
 clearTimeout(waitingTimer);
 document.getElementById('result-heading').textContent='Đang chuẩn bị kết quả';
 document.getElementById('quick-result').innerHTML=`<div class="waiting"><div class="waiting-title"><span class="waiting-icon">${icon('clock')}</span><div><h3>Đang nạp model và phân tích</h3><p>Câu của bạn đã được tiếp nhận.</p></div></div><div class="waiting-steps"><div class="waiting-step done"><span class="step-icon">${icon('check')}</span>Tiếp nhận văn bản<small>Đã xong</small></div><div class="waiting-step active"><span class="step-icon">${icon('zap')}</span>Chuẩn bị model & tính dự đoán</div><div class="waiting-step"><span class="step-icon">${icon('chart')}</span>Hiển thị hai kết quả</div></div><div class="waiting-hint"><strong>Lần đầu có thể cần chờ lâu hơn</strong>Model cần được nạp vào bộ nhớ. Bạn có thể hủy hoặc tiếp tục chờ; không cần bấm Phân tích nhiều lần.</div><div class="waiting-bottom"><span>Đã chờ 8 giây <small>(minh họa)</small></span><button id="cancel-preview">Hủy phân tích</button></div></div>`;
 document.getElementById('show-waiting').textContent='Quay lại kết quả mẫu';
 if(autoFinish)waitingTimer=setTimeout(renderResult,2600);
}

document.getElementById('app').innerHTML=shell(page==='review'?review():page==='quick'?quick():overview());
let toastTimer;
function toast(message){const el=document.querySelector('.toast');el.textContent=message;el.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.hidden=true,4500);}
function rememberDraft(){const note=document.getElementById('review-note');if(note)draftNotes.set(selectedId,note.value);}
if(page==='review'){renderList();renderDetail();}
if(page==='quick'){renderResult();document.getElementById('char-count').textContent=examples[0].text.length+' / 5.000 ký tự';}

document.addEventListener('click',event=>{
 const target=event.target.closest('button,[data-toast]');if(!target)return;
 if(target.dataset.toast)toast(target.dataset.toast);
 if(target.dataset.filter){listMode=target.dataset.filter;renderList();}
 if(target.dataset.item){rememberDraft();selectedId=target.dataset.item;renderList();renderDetail();}
 if(target.dataset.step){rememberDraft();const i=feedback.findIndex(r=>r.id===selectedId);selectedId=feedback[(i+Number(target.dataset.step)+feedback.length)%feedback.length].id;renderList();renderDetail();}
 if(target.dataset.detailTab){rememberDraft();detailTab=target.dataset.detailTab;renderDetail();}
 if(target.hasAttribute('data-experiment')){document.getElementById('comparison').hidden=false;target.innerHTML=icon('check')+'Đang xem ví dụ';}
 if(target.dataset.save){const r=feedback.find(r=>r.id===selectedId);rememberDraft();r.reviewed=true;r.manualLabel=document.getElementById('review-sentiment').value;r.manualTopic=document.getElementById('review-topic').value;if(target.dataset.save==='next'){const i=feedback.indexOf(r);selectedId=feedback[(i+1)%feedback.length].id;}renderList();renderDetail();toast('Đã lưu trong bản xem trước. Dữ liệu của app thật không thay đổi.');}
 if(target.dataset.example!==undefined){clearTimeout(waitingTimer);exampleIndex=Number(target.dataset.example);document.getElementById('quick-text').value=examples[exampleIndex].text;document.getElementById('char-count').textContent=examples[exampleIndex].text.length+' / 5.000 ký tự';document.querySelectorAll('[data-example]').forEach(b=>b.classList.toggle('selected',Number(b.dataset.example)===exampleIndex));renderResult();}
 if(target.id==='preview-analyze'){const text=document.getElementById('quick-text').value.trim();const match=examples.findIndex(e=>e.text===text);if(match<0){toast('Đây là mockup, chưa kết nối model. Hãy chọn một câu mẫu để xem cách hiển thị.');return;}exampleIndex=match;showWaiting(true);toast('Đang mô phỏng chuyển trạng thái UI, không chạy inference.');}
 if(target.id==='show-waiting'){if(document.querySelector('.waiting')){clearTimeout(waitingTimer);renderResult();}else showWaiting();}
 if(target.id==='cancel-preview'){clearTimeout(waitingTimer);document.getElementById('result-heading').textContent='Đã hủy mô phỏng';document.getElementById('quick-result').innerHTML='<div class="waiting-hint">Bạn có thể sửa câu và bấm Phân tích để xem lại luồng minh họa.</div>';document.getElementById('show-waiting').textContent='Xem thiết kế lúc đang chờ';toast('Đã hủy mô phỏng.');}
});
document.addEventListener('input',event=>{if(event.target.id==='review-search'){reviewSearch=event.target.value;renderList();}if(event.target.id==='quick-text'){clearTimeout(waitingTimer);document.getElementById('char-count').textContent=event.target.value.length+' / 5.000 ký tự';document.getElementById('result-heading').textContent='Sẵn sàng phân tích';document.getElementById('quick-result').innerHTML='<div class="waiting-hint"><strong>Nội dung đã thay đổi</strong>Mockup chưa chạy model. Chọn một câu mẫu để xem thiết kế kết quả.</div>';document.querySelectorAll('[data-example]').forEach(b=>b.classList.remove('selected'));}});
document.getElementById('label-source')?.addEventListener('change',()=>toast('Trong app thật, bảng sẽ tính lại theo nguồn nhãn. Số liệu mockup được giữ để duyệt bố cục.'));
