const analyzeBtn = document.getElementById('analyzeBtn');
const clearBtn = document.getElementById('clearBtn');
const rawText = document.getElementById('rawText');
const results = document.getElementById('results');
const emptyState = document.getElementById('emptyState');
const errorBox = document.getElementById('errorBox');
const dealCount = document.getElementById('dealCount');
const charCount = document.getElementById('charCount');
const methodologySelect = document.getElementById('methodology');
const loadingStatus = document.getElementById('loadingStatus');

const loadingMessages = [
  'Getting the plunger...',
  'Flushing the forecast...',
  'Checking for emotional support toilet paper...',
  'Sending a camera down the poop tunnel...',
  'Pressure-testing the porcelain...',
  'Wrestling the sewer goblin...',
  'Scooping mystery sludge out of stage three...',
  'Running a brown-water diagnostics sweep...',
  'Looking for who clogged budget approval...',
  'Spraying the pipe with aggressive honesty...',
  'Snaking the deal for hidden champion problems...',
  'Shaking loose whatever is stuck in authority...',
  'Listening for timeline gurgles...',
  'Checking if this pipeline is all fart, no flush...',
  'Digging corn kernels out of the decision process...',
  'Bleaching the call notes...',
  'Inspecting the bowl for MEDDPICC residue...',
  'Trying not to make eye contact with procurement...',
  'Unclogging the economic buyer trap...',
  'Seeing whether this thing is constipated or just dead...',
  'Running the courtesy flush on weak deal hygiene...',
  'Comparing your notes against OSHA sewer standards...',
  'Wiping down the mutual action plan...',
  'Poking the status quo with a toilet brush...',
  'Asking the pipe spirit for guidance...'
];

let loadingInterval = null;
let loadingMessageIndex = 0;
let latestAnalysis = null;
let unlocked = false;

function startLoadingStatus() {
  if (!loadingStatus) return;
  loadingMessageIndex = Math.floor(Math.random() * loadingMessages.length);
  loadingStatus.textContent = loadingMessages[loadingMessageIndex];
  loadingStatus.classList.remove('hidden');
  if (loadingInterval) clearInterval(loadingInterval);
  loadingInterval = setInterval(() => {
    loadingMessageIndex = (loadingMessageIndex + 1) % loadingMessages.length;
    loadingStatus.textContent = loadingMessages[loadingMessageIndex];
  }, 1500);
}

function stopLoadingStatus() {
  if (loadingInterval) {
    clearInterval(loadingInterval);
    loadingInterval = null;
  }
  if (loadingStatus) {
    loadingStatus.classList.add('hidden');
    loadingStatus.textContent = '';
  }
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function renderList(items, cls = '') {
  if (!items || !items.length) return `<div class="helper ${cls}">None detected.</div>`;
  return `<ul class="${cls}">${items.map(i => `<li>${escapeHtml(i)}</li>`).join('')}</ul>`;
}

function copyText(text, successText = 'Copied.') {
  navigator.clipboard.writeText(text).then(() => alert(successText)).catch(() => {});
}

function buildShareText(data) {
  return `Just ran a deal through Pipe Checker.\n\nMethodology: ${data.methodology_label}\nScore: ${data.overall_score}/100\nStage: ${data.stage}\n${data.benchmark_text}\n\nTry it: ${window.location.origin}`;
}

function scoreTone(score) {
  if (score >= 81) return 'Strong opportunity';
  if (score >= 61) return 'Qualified but still risky';
  if (score >= 41) return 'Risky deal';
  return 'Pipe fully clogged';
}

function renderUsageBars(usage, methodology) {
  const active = methodology === 'meddpicc' ? 'meddpicc' : 'bant';
  return `
    <div class="usage-stack">
      <div class="usage-row ${active === 'bant' ? 'active' : ''}">
        <div class="usage-top"><span>BANT</span><span>${usage.bant_pct || 0}% · ${usage.bant_count || 0} runs</span></div>
        <div class="usage-track"><span style="width:${usage.bant_pct || 0}%"></span></div>
      </div>
      <div class="usage-row ${active === 'meddpicc' ? 'active' : ''}">
        <div class="usage-top"><span>MEDDPICC</span><span>${usage.meddpicc_pct || 0}% · ${usage.meddpicc_count || 0} runs</span></div>
        <div class="usage-track"><span style="width:${usage.meddpicc_pct || 0}%"></span></div>
      </div>
    </div>
  `;
}

function renderSignalRows(signals) {
  if (!signals || !signals.length) return '';
  return `<div class="signal-grid">${signals.map(sig => `
    <div class="signal-row">
      <div class="signal-top"><span>${escapeHtml(sig.name)}</span><span class="tiny-badge ${sig.status}">${escapeHtml(sig.status)}</span></div>
      <div class="signal-points">${sig.points} / ${sig.max_points} pts</div>
      <div class="signal-hint">${escapeHtml(sig.missing_hint)}</div>
    </div>
  `).join('')}</div>`;
}

function renderCategoryAccordion(name, obj, isOpen = false) {
  return `
    <details class="category-accordion" ${isOpen ? 'open' : ''}>
      <summary>
        <div>
          <div class="category-title-row">
            <span class="category-name">${escapeHtml(name)}</span>
            <span class="badge ${obj.status}">${obj.status}</span>
          </div>
          <div class="category-subcopy">${escapeHtml(obj.description)}</div>
        </div>
        <div class="category-score">${obj.points} / ${obj.max_points}</div>
      </summary>
      <div class="category-body">
        <div class="category-columns">
          <div class="detail-block">
            <h4>Evidence found</h4>
            ${renderList(obj.evidence, 'tight-list')}
          </div>
          <div class="detail-block">
            <h4>Missing / expected</h4>
            ${renderList(obj.missing, 'tight-list')}
          </div>
        </div>
        <div class="detail-block detail-block-full">
          <h4>How to correct</h4>
          <p class="helper strong-helper">${escapeHtml(obj.correction)}</p>
        </div>
        ${renderSignalRows(obj.signals)}
      </div>
    </details>
  `;
}

function renderUnlockedSection(data) {
  return `
    <div class="stack-section">
      <div class="section-kicker">Action plan</div>
      <div class="card primary-card">
        <div class="card-heading-row">
          <div>
            <h3 class="card-title">Recommended next step</h3>
            <div class="helper">${escapeHtml(data.summary_text)}</div>
          </div>
          <span class="pill">${escapeHtml(data.next_step)}</span>
        </div>
      </div>

      <div class="card split-card">
        <div>
          <div class="copy-row"><strong>Recommended email</strong><button class="mini-btn" id="copyEmailBtn">Copy</button></div>
          <div class="subject-line"><span>Subject</span>${escapeHtml(data.email.subject)}</div>
          <pre>${escapeHtml(data.email.body)}</pre>
          <div class="helper">${data.ai_enabled ? 'AI-assisted rewrite is enabled for this server.' : 'AI fallback is off, so this is using the built-in coaching template.'}</div>
        </div>
      </div>

      <div class="card">
        <div class="copy-row"><strong>Recommended call script</strong><button class="mini-btn" id="copyCallBtn">Copy</button></div>
        ${renderList(data.call_script, 'tight-list')}
      </div>
    </div>
  `;
}

function renderLockedSection(data) {
  return `
    <div class="card locked-panel" id="lockedPanel">
      <div class="locked-title">🔒 Unlock the follow-up email and deal strategy</div>
      <div class="helper">Pipe Checker Pro reveals the customer-facing next-step email, call script, and action plan for this ${escapeHtml(data.methodology_label)} readout. Drop your email to unlock it now and join the waitlist for pipeline-wide analysis.</div>
      <form id="waitlistForm" class="waitlist-inline">
        <input type="email" id="waitlistEmail" placeholder="Enter your work email" required>
        <button type="submit">Unlock insight</button>
      </form>
      <div class="unlock-note">No spam. Early access only.</div>
      <div id="waitlistMessage" class="helper" style="margin-top:12px;"></div>
    </div>
  `;
}

function renderLeaderboard(items) {
  if (!items || !items.length) return '<div class="helper">No leaderboard data yet. Be the first glorious toilet legend today.</div>';
  return `<div class="leaderboard-list">${items.map(item => `
    <div class="leaderboard-row">
      <div class="leaderboard-rank">#${item.rank}</div>
      <div>
        <div class="leaderboard-title">${escapeHtml(item.label)}</div>
        <div class="helper">Top score logged today</div>
      </div>
      <div class="leaderboard-score">${item.score}</div>
    </div>
  `).join('')}</div>`;
}

function bindResultActions(data) {
  const shareBtn = document.getElementById('shareScoreBtn');
  if (shareBtn) shareBtn.addEventListener('click', () => copyText(buildShareText(data), 'Share text copied. Paste it into LinkedIn or X.'));

  const copyEmailBtn = document.getElementById('copyEmailBtn');
  if (copyEmailBtn) {
    const emailBody = `Subject: ${data.email.subject}\n\n${data.email.body}`;
    copyEmailBtn.addEventListener('click', () => copyText(emailBody, 'Email copied.'));
  }

  const copyCallBtn = document.getElementById('copyCallBtn');
  if (copyCallBtn) copyCallBtn.addEventListener('click', () => copyText(data.call_script.join('\n'), 'Call script copied.'));

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

  const averageText = data.average_score ? `${data.average_score}% avg for ${data.methodology_label} deals` : `First ${data.methodology_label} deal on the board`;
  const topThresholdText = data.top20_threshold ? `${data.top20_threshold}+ gets you into the top 20% of ${data.methodology_label} runs` : 'Top-20% benchmark will appear after more runs';
  const unlockedHtml = unlocked ? renderUnlockedSection(data) : renderLockedSection(data);
  const categoriesHtml = Object.entries(data.analysis).map(([name, obj], idx) => renderCategoryAccordion(name, obj, idx === 0)).join('');

  results.innerHTML = `
    <div class="results-shell">
      <section class="hero-grid">
        <div class="hero-card card">
          <div class="gif-wrap">
            <img src="${escapeHtml(data.gif.file)}" alt="${escapeHtml(data.gif.label)}">
            <div class="gif-caption"><strong>${escapeHtml(data.gif.label)}</strong><br>${escapeHtml(data.gif.caption)}</div>
          </div>
          <div class="hero-copy">
            <div class="section-kicker">${escapeHtml(data.methodology_label)} score</div>
            <div class="score-big">${data.overall_score}<span>/100</span></div>
            <div class="hero-tone">${escapeHtml(scoreTone(data.overall_score))}</div>
            <div class="score-sub">${escapeHtml(data.benchmark_text)}</div>
            <div class="score-actions">
              <button class="mini-btn" id="shareScoreBtn">Copy share text</button>
            </div>
          </div>
        </div>

        <div class="snapshot-grid">
          <div class="metric compact"><div class="metric-label">Stage</div><div class="metric-value">${escapeHtml(data.stage)}</div></div>
          <div class="metric compact"><div class="metric-label">Confidence</div><div class="metric-value">${escapeHtml(data.confidence)}</div></div>
          <div class="metric compact"><div class="metric-label">Deals analyzed</div><div class="metric-value">${escapeHtml(String(data.deal_count))}</div></div>
          <div class="metric compact"><div class="metric-label">Average score</div><div class="metric-value">${escapeHtml(String(data.average_score || 0))}</div><div class="metric-note">${escapeHtml(averageText)}</div></div>
        </div>
      </section>

      <section class="insights-grid">
        <div class="card insight-card">
          <div class="section-kicker">What to do now</div>
          <h3 class="card-title">${escapeHtml(data.next_step)}</h3>
          <p class="helper strong-helper">${escapeHtml(data.summary_text)}</p>
          <div class="helper">${escapeHtml(topThresholdText)}</div>
        </div>

        <div class="card insight-card">
          <div class="section-kicker">Methodology usage</div>
          <h3 class="card-title">What people are using</h3>
          ${renderUsageBars(data.methodology_usage || {}, data.methodology)}
        </div>

        <div class="card insight-card">
          <div class="section-kicker">Leaderboard</div>
          <h3 class="card-title">Top pipe scores today</h3>
          ${renderLeaderboard(data.leaderboard_today || [])}
        </div>
      </section>

      <section class="stack-section">
        <div class="section-kicker">Red flags</div>
        <div class="card">
          ${renderList(data.red_flags, 'tight-list')}
        </div>
      </section>

      ${unlockedHtml}

      <section class="stack-section">
        <div class="section-kicker">Detailed analysis</div>
        <div class="accordion-stack">${categoriesHtml}</div>
      </section>

      <div class="card footer-card">
        <strong>Want Pipe Checker to audit your entire pipeline automatically?</strong>
        <div class="helper" style="margin-top:8px;">We're building a version that scans every deal in your CRM and flags weak opportunities before they slip.</div>
        <div class="helper" style="margin-top:6px;">${unlocked ? 'You already unlocked this deal. Future-you is so brave.' : 'Unlocking the strategy also puts you on the early access list.'}</div>
      </div>
      <div class="micro-footer">Built by a sales nerd. More tools coming.</div>
    </div>
  `;

  bindResultActions(data);
}

analyzeBtn.addEventListener('click', async () => {
  errorBox.classList.add('hidden');
  analyzeBtn.disabled = true;
  analyzeBtn.textContent = 'Analyzing...';
  startLoadingStatus();
  try {
    unlocked = false;
    const res = await fetch('/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_text: rawText.value, methodology: methodologySelect.value })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Analysis failed.');
    renderResults(data);
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.classList.remove('hidden');
  } finally {
    stopLoadingStatus();
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
  stopLoadingStatus();
  rawText.focus();
});

rawText.addEventListener('input', () => {
  charCount.textContent = String(rawText.value.length);
});
