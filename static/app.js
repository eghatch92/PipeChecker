
const analyzeBtn = document.getElementById('analyzeBtn');
const clearBtn = document.getElementById('clearBtn');
const rawText = document.getElementById('rawText');
const results = document.getElementById('results');
const emptyState = document.getElementById('emptyState');
const errorBox = document.getElementById('errorBox');
const dealCount = document.getElementById('dealCount');
const charCount = document.getElementById('charCount');

let latestAnalysis = null;
let unlocked = false;

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

function copyText(text, successText = 'Copied.') {
  navigator.clipboard.writeText(text).then(() => alert(successText)).catch(() => {});
}

function buildShareText(data) {
  return `Just ran a deal through Pipe Checker.\n\nScore: ${data.overall_score}/100\nStage: ${data.stage}\n${data.benchmark_text}\n\nTry it: ${window.location.origin}`;
}

function renderUnlockedSection(data) {
  const emailBody = `Subject: ${data.email.subject}\n\n${data.email.body}`;
  const callBody = data.call_script.join('\n');
  return `
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
}

function renderLockedSection() {
  return `
    <div class="card locked-panel" id="lockedPanel">
      <div class="locked-title">🔒 Unlock the follow-up email and deal strategy</div>
      <div class="helper">Pipe Checker Pro reveals the action plan, recommended email, and call script for this deal. Drop your email to unlock it now and join the waitlist for pipeline-wide analysis.</div>
      <form id="waitlistForm" class="waitlist-inline">
        <input type="email" id="waitlistEmail" placeholder="Enter your work email" required>
        <button type="submit">Unlock insight</button>
      </form>
      <div class="unlock-note">No spam. Early access only.</div>
      <div id="waitlistMessage" class="helper" style="margin-top:12px;"></div>
    </div>
  `;
}

function bindResultActions(data) {
  const shareBtn = document.getElementById('shareScoreBtn');
  if (shareBtn) {
    shareBtn.addEventListener('click', () => copyText(buildShareText(data), 'Share text copied. Paste it into LinkedIn or X.'));
  }

  const copyEmailBtn = document.getElementById('copyEmailBtn');
  if (copyEmailBtn) {
    const emailBody = `Subject: ${data.email.subject}\n\n${data.email.body}`;
    copyEmailBtn.addEventListener('click', () => copyText(emailBody, 'Email copied.'));
  }

  const copyCallBtn = document.getElementById('copyCallBtn');
  if (copyCallBtn) {
    copyCallBtn.addEventListener('click', () => copyText(data.call_script.join('\n'), 'Call script copied.'));
  }

  const waitlistForm = document.getElementById('waitlistForm');
  if (waitlistForm) {
    waitlistForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const emailInput = document.getElementById('waitlistEmail');
      const msg = document.getElementById('waitlistMessage');
      const email = (emailInput.value || '').trim();
      msg.textContent = 'Unlocking...';
      try {
        const res = await fetch('/waitlist', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: 'email=' + encodeURIComponent(email)
        });
        const payload = await res.json().catch(() => ({}));
        if (res.ok) {
          unlocked = true;
          msg.textContent = "You're on the list. Strategy unlocked.";
          msg.classList.add('success-text');
          renderResults(latestAnalysis);
        } else {
          msg.textContent = payload.error || 'That email did not look valid. Please try again.';
        }
      } catch (err) {
        msg.textContent = 'Something went wrong. Please try again.';
      }
    });
  }
}

function renderResults(data) {
  latestAnalysis = data;
  emptyState.classList.add('hidden');
  emptyState.style.display = 'none';
  results.classList.remove('hidden');
  dealCount.textContent = data.deal_count;

  const averageText = data.average_score ? `${data.average_score}% avg across all analyzed deals` : 'First deal on the board';
  const unlockedHtml = unlocked ? renderUnlockedSection(data) : renderLockedSection();

  results.innerHTML = `
    <div class="metric-grid">
      <div class="metric hero-score">
        <div class="gif-wrap">
          <img src="${escapeHtml(data.gif.file)}" alt="${escapeHtml(data.gif.label)}">
          <div class="gif-caption"><strong>${escapeHtml(data.gif.label)}</strong><br>${escapeHtml(data.gif.caption)}</div>
        </div>
        <div>
          <div class="metric-label">Pipe Checker Score</div>
          <div class="score-big">${data.overall_score}<span style="font-size:26px;">/100</span></div>
          <div class="score-sub">${escapeHtml(data.benchmark_text)}</div>
          <div class="score-sub">${escapeHtml(averageText)}</div>
          <div class="score-actions">
            <button class="mini-btn" id="shareScoreBtn">Copy share text</button>
          </div>
        </div>
      </div>
      <div class="metric"><div class="metric-label">Stage</div><div class="metric-value">${escapeHtml(data.stage)}</div></div>
      <div class="metric"><div class="metric-label">Confidence</div><div class="metric-value">${escapeHtml(data.confidence)}</div></div>
      <div class="metric"><div class="metric-label">Deals analyzed</div><div class="metric-value">${escapeHtml(String(data.deal_count))}</div></div>
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

    ${unlockedHtml}

    <div class="card" style="margin-top:20px;text-align:center;">
      <strong>Want Pipe Checker to audit your entire pipeline automatically?</strong>
      <div class="helper" style="margin-top:8px;">We're building a version that scans every deal in your CRM and flags weak opportunities before they slip.</div>
      <div class="helper" style="margin-top:6px;">${unlocked ? 'You already unlocked this deal. Future-you is so brave.' : 'Unlocking the strategy also puts you on the early access list.'}</div>
    </div>
  `;

  bindResultActions(data);
}

analyzeBtn.addEventListener('click', async () => {
  errorBox.classList.add('hidden');
  analyzeBtn.disabled = true;
  analyzeBtn.textContent = 'Analyzing...';
  try {
    unlocked = false;
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
  unlocked = false;
  latestAnalysis = null;
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
