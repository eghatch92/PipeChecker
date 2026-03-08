
from flask import Flask, render_template, request, jsonify, Response
import csv
import io
import os
import re
import sqlite3
import time
from collections import defaultdict, deque
from threading import Lock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, 'pipe_checker.db')
DB_PATH = os.environ.get('DB_PATH', DEFAULT_DB_PATH)
ADMIN_EXPORT_KEY = os.environ.get('ADMIN_EXPORT_KEY', 'change-this-now')
MAX_INPUT_CHARS = int(os.environ.get('MAX_INPUT_CHARS', '50000'))
ANALYZE_RATE_LIMIT = int(os.environ.get('ANALYZE_RATE_LIMIT', '12'))
RATE_WINDOW_SECONDS = int(os.environ.get('RATE_WINDOW_SECONDS', '600'))

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 512 * 1024

RATE_STATE = defaultdict(deque)
RATE_LOCK = Lock()

STAGE_PATTERNS = [
    (r'closed\s*won|contract\s*signed|signature|signed order form', 'Closed Won', 6),
    (r'negotiat|legal review|procurement|redlines|msa|security review', 'Negotiation', 5),
    (r'proposal|quote|pricing|business case|roi|commercials|send contract', 'Proposal', 4),
    (r'pilot|poc|trial|evaluation|demo completed|technical validation', 'Evaluation', 3),
    (r'demo|discovery|qualification|intro call|first meeting|met with', 'Discovery', 2),
]

LATE_STAGE_THRESHOLD = 4

BUDGET_HINTS = [
    r'budget', r'approved funds', r'funding', r'who controls budget', r'budget owner',
    r'procurement', r'capex', r'opex', r'purchased something like this before', r'budget process',
    r'introduce.*finance', r'introduce.*budget', r'finance team', r'approved spend'
]
AUTHORITY_HINTS = [
    r'buying committee', r'economic buyer', r'decision maker', r'vp', r'cfo', r'ceo',
    r'procurement', r'legal', r'it', r'security', r'champion', r'stakeholder', r'approver',
    r'committee', r'leadership team', r'gm', r'director'
]
NEED_HINTS = [
    r'problem', r'pain', r'missed', r'lost', r'need to', r'goal', r'objective', r'quantif',
    r'reduce', r'increase', r'save', r'grow', r'current process', r'challenge', r'issue',
    r'bring that to', r'traffic', r'efficiency', r'conversion', r'revenue'
]
TIMELINE_HINTS = [
    r'by q[1-4]', r'next month', r'this month', r'this quarter', r'next quarter', r'by end of',
    r'go live', r'close by', r'target close', r'contract by', r'implementation by', r'next week',
    r'leadership meeting', r'committee review',
    r'\bjan\b|\bfeb\b|\bmar\b|\bapr\b|\bmay\b|\bjun\b|\bjul\b|\baug\b|\bsep\b|\boct\b|\bnov\b|\bdec\b',
    r'\b20\d{2}\b', r'\b\d{1,2}/\d{1,2}/\d{2,4}\b'
]

NEGATION_WORDS = ['unknown', 'not sure', 'tbd', 'unclear', 'none', 'no budget', 'no timeline', 'not mentioned']

GIF_CONFIG = [
    {'max': 24, 'file': '/static/gifs/pipe_catastrophe.gif', 'label': 'Catastrophic blowout', 'caption': 'This pipe is spraying everywhere. Absolute poop emergency.'},
    {'max': 49, 'file': '/static/gifs/pipe_mega_clog.gif', 'label': 'Mega clog', 'caption': 'The turds are stacked to the ceiling. Somebody call maintenance.'},
    {'max': 74, 'file': '/static/gifs/pipe_wobbly_flow.gif', 'label': 'Wobbly flow', 'caption': 'Still poopy, but at least the toilet is making an effort.'},
    {'max': 100, 'file': '/static/gifs/pipe_cleanish.gif', 'label': 'Mostly unpooped', 'caption': 'Not pristine, but the poop goblin is losing ground.'},
]


def client_ip():
    forwarded = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
    return forwarded or request.remote_addr or 'unknown'


def rate_limit_check(bucket_key: str, limit: int, window_seconds: int):
    now = time.time()
    ip = client_ip()
    key = f'{bucket_key}:{ip}'
    with RATE_LOCK:
        bucket = RATE_STATE[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = max(1, int(window_seconds - (now - bucket[0])))
            return False, retry_after
        bucket.append(now)
    return True, None


def split_sentences(text):
    cleaned = re.sub(r'\s+', ' ', text).strip()
    if not cleaned:
        return []
    parts = re.split(r'(?<=[.!?])\s+', cleaned)
    return [p.strip() for p in parts if p.strip()]


def sentence_evidence(text, patterns, max_items=3):
    sentences = split_sentences(text)
    found = []
    for sent in sentences:
        lower_sent = sent.lower()
        if any(re.search(pat, lower_sent, re.I) for pat in patterns):
            normalized = sent.strip()
            if normalized and normalized not in found:
                found.append(normalized)
        if len(found) >= max_items:
            break
    return found


def db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute('CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, value INTEGER NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS waitlist (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    defaults = {
        'deal_count': 0,
        'total_score': 0,
    }
    for key, value in defaults.items():
        cur = conn.execute('SELECT value FROM stats WHERE key=?', (key,))
        if cur.fetchone() is None:
            conn.execute('INSERT INTO stats (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()


def stat_value(key, default=0):
    conn = db()
    row = conn.execute('SELECT value FROM stats WHERE key=?', (key,)).fetchone()
    conn.close()
    return int(row['value']) if row else default


def get_count():
    return stat_value('deal_count', 0)


def get_average_score():
    count = stat_value('deal_count', 0)
    total = stat_value('total_score', 0)
    return round(total / count) if count else 0


def increment_stats(score):
    conn = db()
    conn.execute("UPDATE stats SET value = value + 1 WHERE key='deal_count'")
    conn.execute("UPDATE stats SET value = value + ? WHERE key='total_score'", (int(score),))
    conn.commit()
    count = conn.execute("SELECT value FROM stats WHERE key='deal_count'").fetchone()['value']
    total = conn.execute("SELECT value FROM stats WHERE key='total_score'").fetchone()['value']
    conn.close()
    average = round(total / count) if count else 0
    return int(count), int(average)


def extract_matches(text, patterns, label):
    found = sentence_evidence(text, patterns, max_items=3)
    lower = text.lower()
    status = 'Missing'
    notes = []
    if found:
        status = 'Partial' if len(found) < 2 else 'Complete'
    for neg in NEGATION_WORDS:
        if neg in lower:
            notes.append(f"Potential weak or implied evidence detected ({neg}). Confirm explicitly.")
            status = 'Partial' if status in ['Missing', 'Complete'] else status
            break
    missing = []
    correction = ''
    if label == 'Budget':
        missing = [
            'Whether the current contact understands the budget process',
            'Who controls budget',
            'Whether they have purchased something like this before',
            'Whether they will introduce the budget owner'
        ]
        correction = 'Ask how budget gets approved, who owns it, what similar purchases looked like, and ask for an introduction to the budget owner.'
    elif label == 'Authority':
        missing = [
            'Named members of the buying committee',
            "Each member's role in approval",
            'Who can block or accelerate the deal'
        ]
        correction = 'Map the buying committee by name and role, then confirm who must be involved before the deal can progress.'
    elif label == 'Need':
        missing = [
            'Quantified problem',
            'Business outcome they want to correct',
            'Why solving it matters now'
        ]
        correction = 'Push for hard numbers, a target outcome, and the cost of doing nothing.'
    elif label == 'Timeline':
        missing = [
            'Target close date',
            'Why that date matters',
            'Steps required to hit closed won'
        ]
        correction = 'Confirm the target close date, the business event driving it, and the milestones that must happen before signature.'

    return {
        'status': status,
        'evidence': found[:3],
        'missing': missing,
        'correction': correction,
        'notes': notes,
    }


def infer_stage(text):
    lower = text.lower()
    for pat, stage, score in STAGE_PATTERNS:
        if re.search(pat, lower, re.I):
            return {'stage': stage, 'maturity_score': score}
    return {'stage': 'Unclear', 'maturity_score': 2}


def overall_score(parts):
    mapping = {'Missing': 0, 'Partial': 1, 'Complete': 2}
    total = sum(mapping[p['status']] for p in parts.values())
    return round((total / 8) * 100)


def choose_next_step(parts, stage_info):
    priority = []
    if parts['Authority']['status'] != 'Complete':
        priority.append('Map Buying Committee')
    if parts['Budget']['status'] != 'Complete':
        priority.append('Understand Budget')
    if parts['Need']['status'] != 'Complete':
        priority.append('Quantify Need')
    if parts['Timeline']['status'] != 'Complete':
        priority.append('Lock Timeline')
    if stage_info['maturity_score'] >= LATE_STAGE_THRESHOLD:
        if parts['Authority']['status'] != 'Complete':
            return 'Map Buying Committee'
        if parts['Budget']['status'] != 'Complete':
            return 'Understand Budget'
    return priority[0] if priority else 'Advance to Mutual Action Plan'


def red_flags(parts, stage_info):
    flags = []
    late = stage_info['maturity_score'] >= LATE_STAGE_THRESHOLD
    if late:
        for key in ['Budget', 'Authority', 'Timeline']:
            if parts[key]['status'] != 'Complete':
                flags.append(f"Late-stage warning: {key} is {parts[key]['status'].lower()} while the deal appears to be in {stage_info['stage']}.")
    if parts['Need']['status'] == 'Missing':
        flags.append('No clear quantified problem found. The deal may be progressing without a measurable reason to buy.')
    for key, val in parts.items():
        flags.extend([f"{key}: {n}" for n in val['notes']])
    return flags


def build_email(step):
    subj = {
        'Understand Budget': 'Aligning on budget process and decision path',
        'Map Buying Committee': 'Quick alignment on who should be involved',
        'Quantify Need': 'Confirming the business impact we discussed',
        'Lock Timeline': 'Working backward from your target close date',
        'Advance to Mutual Action Plan': 'Proposed next steps to keep momentum'
    }[step]
    body = {
        'Understand Budget': (
            "Hi team,\n\n"
            "To keep this moving, I want to make sure I understand how budget gets approved on your side. "
            "Could you help me confirm the budget process, who ultimately controls the spend, and whether there is someone I should meet as part of that conversation? "
            "If you have purchased something similar before, it would also help to understand how that decision was handled.\n\n"
            "If easier, I can send over a short list of questions ahead of time.\n\nBest,"
        ),
        'Map Buying Committee': (
            "Hi team,\n\n"
            "As we move this forward, I want to make sure the right people are included early. "
            "Could you help me understand who is part of the buying committee, what role each person plays in the decision, and whether there is anyone we should involve now to avoid surprises later?\n\n"
            "Happy to keep this lightweight and work around your team’s process.\n\nBest,"
        ),
        'Quantify Need': (
            "Hi team,\n\n"
            "I want to make sure we are tying this project to the business outcome that matters most to you. "
            "Could we spend a few minutes confirming the current problem in measurable terms, what success would look like, and what happens if this stays as-is for another quarter?\n\n"
            "That will help me make sure any recommendation is grounded in the right business case.\n\nBest,"
        ),
        'Lock Timeline': (
            "Hi team,\n\n"
            "To keep momentum, I’d like to confirm the target closed-won date you are working toward and what milestones need to happen before then. "
            "If there is a business event or deadline driving timing, that context will help us build a realistic path forward.\n\n"
            "Happy to propose a simple plan once I have that input.\n\nBest,"
        ),
        'Advance to Mutual Action Plan': (
            "Hi team,\n\n"
            "It seems like we have the core inputs we need. My suggestion is that we align on a simple next-step plan with owners, dates, and dependencies so we can keep the process moving cleanly.\n\n"
            "I’m happy to draft that and send it over for review.\n\nBest,"
        ),
    }[step]
    return {'subject': subj, 'body': body}


def build_call_script(step):
    scripts = {
        'Understand Budget': [
            'Walk me through how spend like this gets approved on your side.',
            'Who controls or strongly influences budget for this initiative?',
            'Have you purchased something similar before, and how did that process work?',
            'Would you be open to bringing the budget owner into the next conversation?'
        ],
        'Map Buying Committee': [
            'Who is on the buying committee for this decision?',
            'What role will each person play in approval?',
            'Who could block this if they are not involved early?',
            'Who should be in the next meeting to keep momentum and avoid surprises?'
        ],
        'Quantify Need': [
            'What is the current problem in measurable terms?',
            'What outcome are you trying to improve, and by how much?',
            'What happens if this stays the same for another quarter?',
            'Why is this important to solve now instead of later?'
        ],
        'Lock Timeline': [
            'What date are you targeting for a closed-won decision?',
            'What business event or deadline is driving that timing?',
            'What needs to happen between now and signature?',
            'Who owns each step to keep the process on schedule?'
        ],
        'Advance to Mutual Action Plan': [
            'It sounds like we have the key inputs. Can we align on owners, dates, and next steps?',
            'What are the remaining dependencies between now and signature?',
            'What would make the next step easiest for your team?',
            'Can I send a simple action plan for us to confirm together?'
        ]
    }
    return scripts[step]


def confidence_label(stage_info, parts):
    evidence_points = sum(len(v['evidence']) for v in parts.values())
    if stage_info['stage'] != 'Unclear' and evidence_points >= 5:
        return 'High'
    if evidence_points >= 3:
        return 'Medium'
    return 'Low'


def score_benchmark_text(score, average):
    if average == 0:
        return 'This is the first deal analyzed. You are the official poop pioneer.'
    delta = score - average
    if delta >= 15:
        return f'This deal is smoking the average by {delta} points. The poop is mostly under control.'
    if delta >= 1:
        return f'This deal is {delta} points above the current average. Light pooping only.'
    if delta == 0:
        return 'This deal is exactly average. Perfectly mid poop situation.'
    if delta <= -15:
        return f'This deal is {abs(delta)} points below average. The pipe goblin is winning.'
    return f'This deal is {abs(delta)} points below average. There is still poop in the elbow joint.'


def pick_gif(score):
    for item in GIF_CONFIG:
        if score <= item['max']:
            return item
    return GIF_CONFIG[-1]


@app.after_request
def add_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    return response


@app.errorhandler(413)
def too_large(_error):
    return jsonify({'error': f'Input is too large. Keep it under about {MAX_INPUT_CHARS:,} characters.'}), 413


@app.errorhandler(429)
def too_many(_error):
    return jsonify({'error': 'Too many requests. Wait a few minutes and try again.'}), 429


@app.errorhandler(404)
def not_found(_error):
    return jsonify({'error': 'Not found.'}), 404


@app.route('/favicon.ico')
def favicon():
    return '', 204


@app.errorhandler(Exception)
def handle_generic_error(_error):
    app.logger.exception('Unhandled server error')
    return jsonify({'error': 'Something went wrong while processing the deal. Please try again.'}), 500


@app.route('/')
def index():
    return render_template('index.html', deal_count=get_count(), max_input_chars=MAX_INPUT_CHARS)


@app.route('/healthz')
def healthz():
    return {'status': 'ok'}, 200


@app.route('/waitlist', methods=['POST'])
def waitlist():
    email = ((request.form.get('email') if request.form else None) or '').strip().lower()
    if not email or '@' not in email or '.' not in email:
        return jsonify({'status': 'invalid', 'error': 'That email did not look valid. Please try again.'}), 400

    conn = db()
    try:
        conn.execute('INSERT INTO waitlist (email) VALUES (?)', (email,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()

    return jsonify({'status': 'ok'})


@app.route('/waitlist-export', methods=['GET'])
def waitlist_export():
    key = request.args.get('key')
    if key != ADMIN_EXPORT_KEY:
        return jsonify({'error': 'Unauthorized'}), 401

    conn = db()
    rows = conn.execute('SELECT email, created_at FROM waitlist ORDER BY created_at DESC').fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['email', 'created_at'])
    writer.writerows([[row['email'], row['created_at']] for row in rows])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=pipe_checker_waitlist.csv'}
    )


@app.route('/waitlist-view', methods=['GET'])
def waitlist_view():
    key = request.args.get('key')
    if key != ADMIN_EXPORT_KEY:
        return jsonify({'error': 'Unauthorized'}), 401

    conn = db()
    rows = conn.execute('SELECT email, created_at FROM waitlist ORDER BY created_at DESC').fetchall()
    conn.close()

    html = """
    <html>
    <head>
        <title>Pipe Checker Waitlist</title>
        <style>
            body { font-family: Arial, sans-serif; padding: 24px; }
            table { border-collapse: collapse; width: 100%; max-width: 900px; }
            th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
            th { background: #f5f5f5; }
        </style>
    </head>
    <body>
        <h1>Pipe Checker Waitlist</h1>
        <table>
            <thead>
                <tr>
                    <th>Email</th>
                    <th>Created At</th>
                </tr>
            </thead>
            <tbody>
    """

    for row in rows:
        html += f"<tr><td>{row['email']}</td><td>{row['created_at']}</td></tr>"

    html += """
            </tbody>
        </table>
    </body>
    </html>
    """
    return html


@app.route('/analyze', methods=['POST'])
def analyze():
    ok, retry_after = rate_limit_check('analyze', ANALYZE_RATE_LIMIT, RATE_WINDOW_SECONDS)
    if not ok:
        response = jsonify({'error': 'Too many deal analyses from this connection. Please wait a few minutes and try again.'})
        response.status_code = 429
        response.headers['Retry-After'] = str(retry_after)
        return response

    payload = request.get_json(silent=True) or {}
    raw_text = (payload.get('raw_text') or '').strip()
    if not raw_text:
        return jsonify({'error': 'Paste opportunity context before running analysis.'}), 400
    if len(raw_text) < 40:
        return jsonify({'error': 'Add more detail. The pasted context is too short for a useful analysis.'}), 400
    if len(raw_text) > MAX_INPUT_CHARS:
        return jsonify({'error': f'Input is too large. Keep it under about {MAX_INPUT_CHARS:,} characters.'}), 400

    stage_info = infer_stage(raw_text)
    parts = {
        'Budget': extract_matches(raw_text, BUDGET_HINTS, 'Budget'),
        'Authority': extract_matches(raw_text, AUTHORITY_HINTS, 'Authority'),
        'Need': extract_matches(raw_text, NEED_HINTS, 'Need'),
        'Timeline': extract_matches(raw_text, TIMELINE_HINTS, 'Timeline'),
    }
    step = choose_next_step(parts, stage_info)
    score = overall_score(parts)
    deal_count, average_score = increment_stats(score)
    gif = pick_gif(score)

    result = {
        'overall_score': score,
        'average_score': average_score,
        'benchmark_text': score_benchmark_text(score, average_score),
        'stage': stage_info['stage'],
        'confidence': confidence_label(stage_info, parts),
        'bant': parts,
        'red_flags': red_flags(parts, stage_info),
        'next_step': step,
        'email': build_email(step),
        'call_script': build_call_script(step),
        'deal_count': deal_count,
        'gif': gif,
    }
    return jsonify(result)


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', '8000'))
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    init_db()
