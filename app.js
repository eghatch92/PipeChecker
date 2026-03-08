const analyzeBtn = document.getElementById('analyzeBtn');
const clearBtn = document.getElementById('clearBtn');
const rawText = document.getElementById('rawText');
const results = document.getElementById('results');
const emptyState = document.getElementById('emptyState');
const errorBox = document.getElementById('errorBox');
const dealCount = document.getElementById('dealCount');
const charCount = document.getElementById('charCount');

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function renderList(items) {
  if (!items || !items.length) return '<div class="helper">None detected.</div>';
  return `<ul>${items.map(i => `<li>${escapeHtml(i)}</li>`).join('')}</ul>`;
}

function renderBantCard(name, obj) {
  return `
    <div class="card">
      <h3>${name} <span class="badge ${obj.status}">${obj.status}</span></h3>
      <div><strong>Evidence found</strong>${renderList(obj.evidence)}</div>
      <div><strong>Missing / expected</strong>${renderList(obj.missing)}</div>
      <div><strong>How to correct</strong><div class="helper" style="margin-top:6px">${escapeHtml(obj.correction)}</div></div>
    </div>
  `;
}

function copyText(text) {
  navigator.clipboard.writeText(text).catch(() => {});
}

function renderResults(data) {
  emptyState.classList.add('hidden');
  emptyState.style.display = 'none';
  results.classList.remove('hidden');
  dealCount.textContent = data.deal_count;

  const emailBody = `Subject: ${data.email.subject}\n\n${data.email.body}`;
  const callBody = data.call_script.join('\n');

  results.innerHTML = `
    <div class="metric-grid">
      <div class="metric"><div class="metric-label">Overall BANT Score</div><div class="metric-value">${data.overall_score}%</div></div>
      <div class="metric"><div class="metric-label">Stage</div><div class="metric-value">${escapeHtml(data.stage)}</div></div>
      <div class="metric"><div class="metric-label">Confidence</div><div class="metric-value">${escapeHtml(data.confidence)}</div></div>
    </div>

    <h2 class="section-title">BANT analysis</h2>
    <div class="cards">
      ${renderBantCard('Budget', data.bant.Budget)}
      ${renderBantCard('Authority', data.bant.Authority)}
      ${renderBantCard('Need', data.bant.Need)}
      ${renderBantCard('Timeline', data.bant.Timeline)}
    </div>

    <h2 class="section-title">Red flags</h2>
    <div class="card">${renderList(data.red_flags)}</div>

    <h2 class="section-title">Recommended next step</h2>
    <div class="card"><strong>${escapeHtml(data.next_step)}</strong></div>

    <h2 class="section-title">Recommended email</h2>
    <div class="card">
      <div class="copy-row"><strong>Subject:</strong> ${escapeHtml(data.email.subject)} <button class="mini-btn" id="copyEmailBtn">Copy</button></div>
      <pre>${escapeHtml(data.email.body)}</pre>
    </div>

    <h2 class="section-title">Recommended call script</h2>
    <div class="card">
      <div class="copy-row"><strong>Questions to ask</strong><button class="mini-btn" id="copyCallBtn">Copy</button></div>
      ${renderList(data.call_script)}
    </div>
  `;

  document.getElementById('copyEmailBtn').addEventListener('click', () => copyText(emailBody));
  document.getElementById('copyCallBtn').addEventListener('click', () => copyText(callBody));
}

analyzeBtn.addEventListener('click', async () => {
  errorBox.classList.add('hidden');
  analyzeBtn.disabled = true;
  analyzeBtn.textContent = 'Analyzing...';
  try {
    const res = await fetch('/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_text: rawText.value })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Analysis failed.');
    renderResults(data);
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.classList.remove('hidden');
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = 'Analyze deal';
  }
});

clearBtn.addEventListener('click', () => {
  rawText.value = '';
  charCount.textContent = '0';
  results.classList.add('hidden');
  emptyState.classList.remove('hidden');
  emptyState.style.display = 'flex';
  errorBox.classList.add('hidden');
});

rawText.addEventListener('input', () => {
  charCount.textContent = String(rawText.value.length);
});
