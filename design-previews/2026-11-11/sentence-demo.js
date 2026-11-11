const samples = [
  {text:'Cổng đăng ký học phần báo lỗi liên tục, mình chưa đăng ký được môn bắt buộc.',sentiment:'Tiêu cực',topic:'Dịch vụ',score:59.5,topicScore:69.8,topics:[69.8,25.2,5],values:[40.1,.3,59.5,.1]},
  {text:'Giảng viên giải thích bài tập rõ ràng, mình hiểu bài dễ hơn.',sentiment:'Tích cực',topic:'Học tập',score:92.4,topicScore:88.6,topics:[8.1,88.6,3.3],values:[5.2,92.4,2.3,.1]},
  {text:'Thư viện mở cửa đến chín giờ tối.',sentiment:'Trung tính',topic:'Tin tức',score:96.1,topicScore:81,topics:[12,7,81],values:[96.1,2.3,1.5,.1]},
];
const byId = id => document.getElementById(id);
const explanations = [
  {reading:'Câu mô tả sự cố đăng ký học phần và việc chưa đăng ký được môn bắt buộc. Nội dung này phù hợp với cách đọc mang sắc thái tiêu cực và liên quan đến dịch vụ sinh viên.',caution:'Điểm Tiêu cực là 59,5%, còn Trung tính là 40,1%. Phân bố vẫn dành điểm đáng kể cho Trung tính; nên đối chiếu nội dung thay vì xem nhãn dẫn đầu là kết luận chắc chắn.'},
  {reading:'Người viết đánh giá tốt cách giảng viên giải thích và cho biết mình hiểu bài dễ hơn. Cách đọc này phù hợp với nhãn Tích cực và chủ đề Học tập trong kết quả mẫu.',caution:'Điểm Tích cực cao hơn rõ rệt các nhãn còn lại, nhưng không đồng nghĩa với xác suất đúng 92,4%. Phần diễn giải chỉ đối chiếu nội dung với kết quả đã có.'},
  {reading:'Câu cung cấp giờ mở cửa thư viện, không trực tiếp thể hiện khen hay chê. Nhãn Trung tính phù hợp với cách đọc đó; nội dung cũng mang hình thức một thông báo.',caution:'Tin tức là nhãn dẫn đầu trong ví dụ. Thư viện cũng liên quan đến dịch vụ sinh viên, nên cần xét quy ước gán nhãn và ngữ cảnh khi đánh giá chủ đề.'},
];
const format = n => n.toFixed(1).replace('.',',');
let selected = 0;
let timer;
let toastTimer;
let running = false;
let hasResult = true;

function notify(text) {
  byId('toast').textContent = text;
  byId('toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => byId('toast').hidden = true, 5000);
}

function setState(state) {
  byId('ai-content').hidden = true;
  byId('explain-ai').setAttribute('aria-expanded','false');
  byId('explain-ai').textContent = 'Xem diễn giải mẫu →';
  byId('interpret-content').hidden = state !== 'result';
  byId('interpret-empty').hidden = state === 'result';
  byId('result-content').hidden = state !== 'result';
  byId('empty-state').hidden = state !== 'empty';
  byId('waiting-state').hidden = state !== 'waiting';
  document.querySelector('.result-panel').setAttribute('aria-busy',String(state === 'waiting'));
  running = state === 'waiting';
  byId('analyze').disabled = running || !byId('sentence').value.trim();
  byId('sentence').disabled = running;
  byId('clear').disabled = running;
  document.querySelectorAll('[data-example]').forEach(button => button.disabled = running);
  byId('preview-wait').textContent = running ? 'Quay lại màn trước →' : 'Xem thiết kế trạng thái chờ →';
}

function renderResult() {
  const sample = samples[selected];
  byId('sentiment').textContent = sample.sentiment;
  byId('sentiment').style.color = sample.sentiment === 'Tiêu cực' ? 'var(--red)' : 'var(--teal)';
  byId('topic').textContent = sample.topic;
  byId('sentiment-score').innerHTML = format(sample.score)+'<span>%</span>';
  byId('topic-score').innerHTML = format(sample.topicScore)+'<span>%</span>';
  byId('signal').classList.toggle('clear', sample.score >= 60);
  byId('signal').innerHTML = sample.score < 60
    ? '<span aria-hidden="true">!</span><p><strong>Cảm xúc cần được đối chiếu thêm</strong>Điểm nhãn dẫn đầu dưới ngưỡng 0,60. Hãy đọc cả câu trước khi kết luận.</p>'
    : '<span aria-hidden="true">✓</span><p><strong>Không có cờ phân vân trong ví dụ này</strong>Điểm cao không bảo đảm dự đoán đúng. Hãy đối chiếu với nội dung thực tế.</p>';
  byId('scores').innerHTML = ['Trung tính','Tích cực','Tiêu cực','Toxic'].map((label,i)=>`<div class="score-row"><span>${label}</span><div class="score-track"><span class="${sample.values[i]===sample.score?'leading':''}" style="width:${sample.values[i]}%"></span></div><strong>${format(sample.values[i])}%</strong></div>`).join('');
  byId('topic-scores').innerHTML = ['Dịch vụ','Học tập','Tin tức'].map((label,i)=>`<div class="score-row"><span>${label}</span><div class="score-track"><span class="${sample.topics[i]===sample.topicScore?'leading':''}" style="width:${sample.topics[i]}%"></span></div><strong>${format(sample.topics[i])}%</strong></div>`).join('');
  byId('sentence-reading').textContent = sample.text;
  byId('sentence-labels').textContent = `${sample.sentiment} · ${format(sample.score)}% / ${sample.topic} · ${format(sample.topicScore)}%`;
  hasResult = true;
  setState('result');
}

function updateInput() {
  byId('characters').textContent = byId('sentence').value.length+' / 5.000';
  document.querySelectorAll('[data-example]').forEach(button=>{
    const active = byId('sentence').value.trim() === samples[Number(button.dataset.example)].text;
    button.classList.toggle('active',active);
    button.setAttribute('aria-pressed',String(active));
  });
}

document.querySelectorAll('[data-example]').forEach(button=>button.addEventListener('click',()=>{
  clearTimeout(timer);
  selected = Number(button.dataset.example);
  byId('sentence').value = samples[selected].text;
  updateInput();
  byId('comparison').hidden = true;
  renderResult();
}));
byId('sentence').addEventListener('input',()=>{
  hasResult = false;
  updateInput();
  setState('empty');
  byId('comparison').hidden = true;
});
byId('clear').addEventListener('click',()=>{
  clearTimeout(timer);
  byId('sentence').value = '';
  hasResult = false;
  updateInput();
  setState('empty');
  byId('comparison').hidden = true;
  byId('sentence').focus();
});
byId('analyze').addEventListener('click',()=>{
  const match = samples.findIndex(s=>s.text===byId('sentence').value.trim());
  if(match<0){notify('Mockup chưa kết nối model. Chọn một trong ba câu mẫu để xem kết quả minh họa.');return;}
  selected=match;
  setState('waiting');
  notify('Đang mô phỏng luồng giao diện. Thời gian này không phải tốc độ chạy model.');
  timer=setTimeout(renderResult,2200);
});
byId('cancel').addEventListener('click',()=>{
  clearTimeout(timer);
  hasResult=false;
  setState('empty');
  notify('Đã hủy mô phỏng. Bạn có thể sửa câu hoặc phân tích lại.');
});
byId('preview-wait').addEventListener('click',()=>{
  clearTimeout(timer);
  if(running)setState(hasResult?'result':'empty');else setState('waiting');
});
byId('toggle-explore').addEventListener('click',()=>{
  const open=byId('explore-body').hidden;
  byId('explore-body').hidden=!open;
  byId('toggle-explore').setAttribute('aria-expanded',String(open));
});
byId('compare').addEventListener('click',()=>{
  byId('comparison').hidden=false;
  if(byId('sentence').value.trim()!==samples[0].text)notify('Phần so sánh minh họa riêng câu mẫu Dịch vụ sinh viên, không phải câu đang nhập.');
});
byId('explain-ai').addEventListener('click',()=>{
  const open = byId('ai-content').hidden;
  const sample = samples[selected];
  byId('ai-reading').textContent = explanations[selected].reading;
  byId('ai-caution').textContent = explanations[selected].caution;
  byId('ai-evidence').textContent = `Dữ kiện sử dụng: câu mẫu hiện tại · ${sample.sentiment} ${format(sample.score)}% · ${sample.topic} ${format(sample.topicScore)}% · phân bố điểm. Chưa sử dụng thử nghiệm bỏ cụm từ.`;
  byId('ai-content').hidden = !open;
  byId('explain-ai').setAttribute('aria-expanded',String(open));
  byId('explain-ai').textContent = open ? 'Thu gọn diễn giải ↑' : 'Xem diễn giải mẫu →';
});
document.querySelectorAll('[data-info]').forEach(button=>button.addEventListener('click',()=>notify(button.dataset.info)));
updateInput();
renderResult();
