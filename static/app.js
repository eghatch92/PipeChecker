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
let detailFilter = 'all';
let latestUnlockContextId = '';

function startLoadingStatus() {
  loadingMessageIndex = Math.floor(Math.random() * loadingMessages.length);
  loadingStatus.textContent = loadingMessages[loadingMessageIndex];
  loadingStatus.classList.remove('hidden');
  clearInterval(loadingInterval);
  loadingInterval = setInterval(() => {
    loadingMessageIndex = (loadingMessageIndex + 1) % loadingMessages.length;
    loadingStatus.textContent = loadingMessages[loadingMessageIndex];
  }, 1500);
}

function stopLoadingStatus() {
  clearInterval(loadingInterval);
  loadingInterval = null;
  loadingStatus.classList.add('hidden');
  loadingStatus.textContent = '';
}

function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function renderList(items, cls = '') {
  if (!items || !items.length) return `<div class="helper ${cls}">None detected.</div>`;
  return `<ul class="tight-list ${cls}">${items.map(i => `<li>${escapeHtml(i)}</li>`).join('')}</ul>`;
}

function copyText(text, successText = 'Copied.') {
  navigator.clipboard.writeText(text).then(() => alert(successText)).catch(() => {});
}

function buildShareText(data) {
  return `Just ran a deal through PipeChecker by Little Post Manager.\n\nMethodology: ${data.methodology_label}\nScore: ${data.overall_score}/100\nStage: ${data.stage}\n${data.benchmark_text}\n\nTry it: ${window.location.origin}`;
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
    </div>`;
}

function renderSignalRows(signals) {
  if (!signals || !signals.length) return '<div class="helper">No signal detail available yet.</div>';
  return `<div class="signal-grid">${signals.map(sig => `
    <div class="signal-row">
      <div class="signal-top"><span>${escapeHtml(sig.name)}</span><span class="tiny-badge ${sig.status}">${escapeHtml(sig.status)}</span></div>
      <div class="signal-points">${sig.points} / ${sig.max_points} pts</div>
      <div class="signal-hint">${escapeHtml(sig.missing_hint)}</div>
    </div>`).join('')}</div>`;
}

function renderCategoryCard(name, obj, isOpen = false) {
  const statusClass = obj.status || 'Missing';
  return `
    <article class="category-card ${statusClass.toLowerCase()} ${isOpen ? 'open' : ''}" data-status="${statusClass.toLowerCase()}">
      <div class="category-summary" data-accordion-toggle>
        <div class="category-main">
          <div class="category-title-row">
            <span class="category-name">${escapeHtml(name)}</span>
            <span class="badge ${statusClass}">${escapeHtml(statusClass)}</span>
          </div>
          <div class="category-subcopy">${escapeHtml(obj.description)}</div>
        </div>
        <div class="category-score">${obj.points} / ${obj.max_points}</div>
        <div class="category-chevron">+</div>
      </div>
      <div class="category-body">
        <div class="detail-grid">
          <div class="subpanel">
            <h4>Evidence found</h4>
            ${renderList(obj.evidence)}
          </div>
          <div class="subpanel">
            <h4>Missing / expected</h4>
            ${renderList(obj.missing)}
          </div>
        </div>
        <div class="subpanel">
          <h4>How to correct</h4>
          <p class="helper">${escapeHtml(obj.correction)}</p>
        </div>
        <div class="subpanel">
          <h4>Signal breakdown</h4>
          ${renderSignalRows(obj.signals)}
        </div>
      </div>
    </article>`;
}

function renderLockedSection(data) {
  return `
    <section class="locked-panel panel" id="lockedPanel">
      <div class="section-kicker">Unlock strategy</div>
      <h3>Unlock the customer email and call plan</h3>
      <p class="helper">Drop your email to unlock the customer-facing email, call script, and action plan for this ${escapeHtml(data.methodology_label)} readout.</p>
      <form id="waitlistForm" class="waitlist-inline">
        <input type="email" id="waitlistEmail" placeholder="Enter your work email" required>
        <button type="submit">Unlock insight</button>
      </form>
      <div class="unlock-note">No spam. Early access only.</div>
      <div id="waitlistMessage" class="helper"></div>
    </section>`;
}

function renderUnlockedSection(data) {
  return `
    <section class="unlocked-card panel">
      <div class="section-kicker">Unlocked strategy</div>
      <div class="action-strip">
        <div class="action-card">
          <h3>Recommended next step</h3>
          <div class="key-line">${escapeHtml(data.next_step)}</div>
          <p class="helper" style="margin-top:10px;">${escapeHtml(data.summary_text)}</p>
          <div class="quick-actions">
            <button class="mini-btn" id="copyEmailBtn">Copy email</button>
            <button class="mini-btn secondary" id="copyCallBtn">Copy call script</button>
          </div>
        </div>
        <div class="stats-card">
          <div class="section-kicker">Customer email</div>
          <div class="subpanel" style="margin-top:10px;">
            <h4>Subject</h4>
            <div>${escapeHtml(data.email.subject)}</div>
          </div>
        </div>
      </div>
      <div class="detail-grid" style="margin-top:18px;">
        <div class="subpanel">
          <h4>Email draft</h4>
          <pre>${escapeHtml(data.email.body)}</pre>
        </div>
        <div class="subpanel">
          <h4>Call script</h4>
          ${renderList(data.call_script)}
        </div>
      </div>
    </section>`;
}

function renderStatsRail(data, averageText) {
  const usage = data.methodology_usage || {};
  const leaderboard = (data.leaderboard_today || [])[0];
  return `
    <div class="stats-grid">
      <div class="stat-card">
        <div class="micro-label">Average score</div>
        <div class="stat-value">${escapeHtml(String(data.average_score || 0))}</div>
        <div class="stat-note">${escapeHtml(averageText)}</div>
      </div>
      <div class="stat-card">
        <div class="micro-label">Methodology usage</div>
        ${renderUsageBars(usage, data.methodology)}
      </div>
      <div class="stat-card">
        <div class="micro-label">Top score today</div>
        ${leaderboard ? `
          <div class="leader-inline">
            <div class="leaderboard-row">
              <div class="leaderboard-rank">#${leaderboard.rank}</div>
              <div>
                <div class="leaderboard-title">${escapeHtml(leaderboard.label)}</div>
                <div class="helper">Highest score logged today</div>
              </div>
              <div class="leaderboard-score">${leaderboard.score}</div>
            </div>
          </div>` : '<div class="stat-note">No leaderboard data yet.</div>'}
      </div>
    </div>`;
}

function bindResultActions(data) {
  document.getElementById('shareScoreBtn')?.addEventListener('click', () => {
    copyText(buildShareText(data), 'Share text copied.');
  });

  document.getElementById('runAnotherBtn')?.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    rawText.focus();
  });

  document.getElementById('copyEmailBtn')?.addEventListener('click', () => {
    const body = `Subject: ${data.email.subject}\n\n${data.email.body}`;
    copyText(body, 'Email copied.');
  });

  document.getElementById('copyCallBtn')?.addEventListener('click', () => {
    copyText(data.call_script.join('\n'), 'Call script copied.');
  });

  document.querySelectorAll('[data-accordion-toggle]').forEach(el => {
    el.addEventListener('click', () => {
      const card = el.closest('.category-card');
      if (card) card.classList.toggle('open');
    });
  });

  document.querySelectorAll('[data-filter]').forEach(btn => {
    btn.addEventListener('click', () => {
      detailFilter = btn.dataset.filter;
      document.querySelectorAll('[data-filter]').forEach(b => b.classList.toggle('active', b.dataset.filter === detailFilter));
      document.querySelectorAll('.category-card').forEach(card => {
        const match = detailFilter === 'all' || card.dataset.status === detailFilter;
        card.style.display = match ? '' : 'none';
      });
    });
  });

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
          body: [
            'email=' + encodeURIComponent(email),
            'unlock_context_id=' + encodeURIComponent(latestUnlockContextId)
          ].join('&')
        });
        const payload = await res.json().catch(() => ({}));
        if (res.ok) {
          if (payload.email && payload.call_script) {
            latestAnalysis = {
              ...latestAnalysis,
              email: payload.email,
              call_script: payload.call_script
            };
          }
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
  results.classList.remove('hidden');
  dealCount.textContent = data.deal_count;

  const averageText = data.average_score
    ? `${data.average_score}% avg for ${data.methodology_label} deals`
    : `First ${data.methodology_label} deal on the board`;

  const topThresholdText = data.top20_threshold
    ? `${data.top20_threshold}+ gets into the top 20% of ${data.methodology_label} runs`
    : 'Top-20% benchmark appears after more runs';

  const categoriesHtml = Object.entries(data.analysis)
    .map(([name, obj], idx) => renderCategoryCard(name, obj, idx === 0))
    .join('');

  results.innerHTML = `
    <div class="results-shell">
      <section class="hero-grid">
        <article class="hero-card">
          <div class="gif-wrap">
            <img src="${escapeHtml(data.gif.file)}" alt="${escapeHtml(data.gif.label)}">
            <div class="gif-caption"><strong>${escapeHtml(data.gif.label)}</strong><br>${escapeHtml(data.gif.caption)}</div>
          </div>
          <div class="hero-copy">
            <div class="section-kicker">${escapeHtml(data.methodology_label)} score</div>
            <div class="score-row">
              <div class="score-big">${data.overall_score}<span>/100</span></div>
              <div class="hero-tone">${escapeHtml(scoreTone(data.overall_score))}</div>
            </div>
            <div class="hero-summary">${escapeHtml(data.benchmark_text)}</div>
            <div class="hero-actions">
              <button class="mini-btn" id="shareScoreBtn">Copy share text</button>
              <button class="mini-btn secondary" id="runAnotherBtn">Analyze another deal</button>
            </div>
          </div>
        </article>

        <aside class="snapshot-card">
          <div class="snapshot-top">
            <div class="snapshot-metric">
              <div class="metric-label">Stage</div>
              <div class="snapshot-value">${escapeHtml(data.stage)}</div>
            </div>
            <div class="snapshot-metric">
              <div class="metric-label">Confidence</div>
              <div class="snapshot-value">${escapeHtml(data.confidence)}</div>
            </div>
            <div class="snapshot-metric">
              <div class="metric-label">Deals analyzed</div>
              <div class="snapshot-value">${escapeHtml(String(data.deal_count))}</div>
            </div>
          </div>
          <div class="snapshot-secondary">
            <div class="snapshot-highlight">
              <div class="metric-label">Next step</div>
              <div class="highlight-title">${escapeHtml(data.next_step)}</div>
              <div class="helper">${escapeHtml(data.summary_text)}</div>
            </div>
            <div class="snapshot-highlight">
              <div class="metric-label">Benchmark</div>
              <div class="highlight-title">${escapeHtml(String(data.average_score || 0))} avg</div>
              <div class="helper">${escapeHtml(topThresholdText)}</div>
            </div>
          </div>
        </aside>
      </section>

      <section class="red-flags-card card">
        <div class="red-flags-head">
          <div>
            <div class="section-kicker">Deal risks</div>
            <h3>What could kill this deal</h3>
          </div>
        </div>
        ${renderList(data.red_flags)}
      </section>

      ${unlocked ? renderUnlockedSection(data) : renderLockedSection(data)}

      <section class="detail-card card">
        <div class="detail-head">
          <div>
            <div class="section-kicker">Detailed analysis</div>
            <h3>Open only the categories you need</h3>
          </div>
          <div class="detail-toggle-bar">
            <button class="mini-btn filter-chip active" data-filter="all">All</button>
            <button class="mini-btn filter-chip" data-filter="missing">Missing</button>
            <button class="mini-btn filter-chip" data-filter="partial">Partial</button>
            <button class="mini-btn filter-chip" data-filter="complete">Complete</button>
          </div>
        </div>
        <div class="accordion-stack">${categoriesHtml}</div>
      </section>

      <section class="stats-card card">
        <div class="section-kicker">Community stats</div>
        <h3>How this run stacks up</h3>
        ${renderStatsRail(data, averageText)}
      </section>

      <div class="footer-card card">
        <strong>Want Pipe Checker to audit your entire pipeline automatically?</strong>
        <div class="helper" style="margin-top:8px;">We're building a version that scans every deal in your CRM and flags weak opportunities before they slip.</div>
        <div class="helper" style="margin-top:6px;">${unlocked ? 'You already unlocked this deal. Future-you is so brave.' : 'Unlocking the strategy also puts you on the early access list.'}</div>
        <div class="footer-actions"><a class="contact-btn" href="mailto:info@littlepostmanager.com?subject=PipeChecker%20question">Need help? Contact us</a></div>
      </div>
      <div class="micro-footer">Built by a sales nerd. More tools coming.</div>
    </div>`;

  bindResultActions(data);
}

analyzeBtn.addEventListener('click', async () => {
  errorBox.classList.add('hidden');
  analyzeBtn.disabled = true;
  analyzeBtn.textContent = 'Analyzing...';
  startLoadingStatus();
  try {
    unlocked = false;
    detailFilter = 'all';
    const res = await fetch('/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_text: rawText.value, methodology: methodologySelect.value })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Analysis failed.');
    latestUnlockContextId = data.unlock_context_id || '';
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
  latestUnlockContextId = '';
  detailFilter = 'all';
  rawText.value = '';
  charCount.textContent = '0';
  results.classList.add('hidden');
  emptyState.classList.remove('hidden');
  errorBox.classList.add('hidden');
  stopLoadingStatus();
  rawText.focus();
});

rawText.addEventListener('input', () => {
  charCount.textContent = String(rawText.value.length);
});
