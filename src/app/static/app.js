const form = document.querySelector('#chat-form');
const question = document.querySelector('#question');
const submit = document.querySelector('#submit');
const messages = document.querySelector('#messages');
const formStatus = document.querySelector('#form-status');

function addMessage(role, text, evidence = []) {
  const article = document.createElement('article');
  article.className = `message ${role}`;

  const avatar = document.createElement('span');
  avatar.className = 'avatar';
  avatar.setAttribute('aria-hidden', 'true');
  avatar.textContent = role === 'assistant' ? 'AI' : 'Bạn';

  const body = document.createElement('div');
  const author = document.createElement('strong');
  author.textContent = role === 'assistant' ? 'Trợ lý' : 'Bạn';
  const content = document.createElement('p');
  content.textContent = text;
  body.append(author, content);

  if (evidence.length) {
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = `Nguồn dữ liệu (${evidence.length})`;
    const list = document.createElement('ul');
    evidence.forEach((item) => {
      const row = document.createElement('li');
      const period = item.metadata?.period ? ` — ${item.metadata.period}` : '';
      row.textContent = `${item.citation_id || 'Nguồn'}: ${item.source}${period}`;
      list.append(row);
    });
    details.append(summary, list);
    body.append(details);
  }

  article.append(avatar, body);
  messages.append(article);
  article.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function setLoading(loading) {
  submit.disabled = loading;
  question.disabled = loading;
  form.setAttribute('aria-busy', String(loading));
  submit.textContent = loading ? 'Đang phân tích…' : 'Gửi câu hỏi';
  formStatus.textContent = loading ? 'Đang truy vấn dữ liệu chỉ đọc…' : 'Nhấn Ctrl + Enter để gửi.';
}

async function sendQuestion(text) {
  addMessage('user', text);
  setLoading(true);
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: text }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || 'Không thể xử lý yêu cầu.');
    }
    addMessage('assistant', payload.answer, payload.evidence || []);
  } catch (error) {
    addMessage('error', error.message || 'Không thể kết nối đến hệ thống.');
  } finally {
    setLoading(false);
    question.focus();
  }
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  const text = question.value.trim();
  if (!text) return;
  question.value = '';
  sendQuestion(text);
});

question.addEventListener('keydown', (event) => {
  if (event.ctrlKey && event.key === 'Enter') {
    event.preventDefault();
    form.requestSubmit();
  }
});

document.querySelectorAll('[data-question]').forEach((button) => {
  button.addEventListener('click', () => {
    question.value = button.dataset.question;
    question.focus();
  });
});
