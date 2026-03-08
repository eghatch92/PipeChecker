from flask import Flask, render_template, request, jsonify, Response
import csv
import io
import json
import os
import re
import sqlite3
import time
from collections import defaultdict, deque
from threading import Lock
from urllib import request as urlrequest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, 'pipe_checker.db')
DB_PATH = os.environ.get('DB_PATH', DEFAULT_DB_PATH)
ADMIN_EXPORT_KEY = os.environ.get('ADMIN_EXPORT_KEY', 'change-this-now')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '').strip()
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-5-mini')
OPENAI_TIMEOUT_SECONDS = int(os.environ.get('OPENAI_TIMEOUT_SECONDS', '25'))
AI_MAX_PER_HOUR = int(os.environ.get('AI_MAX_PER_HOUR', '50'))
AI_LIMIT_MESSAGE = os.environ.get('AI_LIMIT_MESSAGE', 'AI coaching temporarily exhausted for this hour. Try again soon.')
MAX_INPUT_CHARS = int(os.environ.get('MAX_INPUT_CHARS', '50000'))
ANALYZE_RATE_LIMIT = int(os.environ.get('ANALYZE_RATE_LIMIT', '12'))
RATE_WINDOW_SECONDS = int(os.environ.get('RATE_WINDOW_SECONDS', '600'))

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 512 * 1024

RATE_STATE = defaultdict(deque)
RATE_LOCK = Lock()
AI_CALLS = deque()
AI_LOCK = Lock()

STAGE_PATTERNS = [
    (r'closed\s*won|contract\s*signed|signature|signed order form', 'Closed Won', 6),
    (r'negotiat|legal review|procurement|redlines|msa|security review', 'Negotiation', 5),
    (r'proposal|quote|pricing|business case|roi|commercials|send contract', 'Proposal', 4),
    (r'pilot|poc|trial|evaluation|demo completed|technical validation', 'Evaluation', 3),
    (r'demo|discovery|qualification|intro call|first meeting|met with', 'Discovery', 2),
]
LATE_STAGE_THRESHOLD = 4
NEGATION_WORDS = ['unknown', 'not sure', 'tbd', 'unclear', 'none', 'not mentioned', 'not confirmed', 'unsure', 'guess']
NUMBER_PATTERN = r'\b\d+(?:[\.,]\d+)?\b'
DATE_PATTERN = r'\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|q[1-4]|20\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b'

GIF_CONFIG = [
    {'max': 19, 'file': '/static/gifs/pipe_catastrophe.gif', 'label': 'Nuclear poop plume', 'caption': 'This deal detonated the toilet and now the hallway smells like regret.'},
    {'max': 39, 'file': '/static/gifs/pipe_mega_clog.gif', 'label': 'King Kong turd jam', 'caption': 'A champion-sized log is lodged in the bend and nobody brought a plunger.'},
    {'max': 59, 'file': '/static/gifs/pipe_wobbly_flow.gif', 'label': 'Murky swirl of doom', 'caption': 'It is technically moving, but only in the way a haunted septic tank moves.'},
    {'max': 79, 'file': '/static/gifs/pipe_cleanish.gif', 'label': 'Mostly de-pooped', 'caption': 'Still a faint whiff of danger, but the poop demons are losing leverage.'},
    {'max': 100, 'file': '/static/gifs/pipe_cleanish.gif', 'label': 'Toilet bowl valedictorian', 'caption': 'A suspiciously healthy pipe. Someone actually qualified this thing.'},
]

BANT_MODEL = {
    'Budget': {
        'weight': 25,
        'description': 'Budget process awareness, budget ownership, prior buying pattern, and access to the person controlling spend.',
        'signals': [
            {
                'name': 'Budget process understood',
                'weight': 8,
                'patterns': [r'budget process', r'approval process', r'how budget gets approved', r'funding process', r'approval path', r'approval workflow'],
                'partial_patterns': [r'budget', r'funding', r'approved funds', r'opex', r'capex'],
                'missing_hint': 'Do they understand how spend like this gets approved?'
            },
            {
                'name': 'Budget owner identified',
                'weight': 8,
                'patterns': [r'who controls budget', r'budget owner', r'finance leader', r'vp finance', r'cfo', r'controller', r'head of finance'],
                'partial_patterns': [r'finance', r'budget holder', r'owns spend', r'controls spend'],
                'missing_hint': 'Who actually controls budget for this initiative?'
            },
            {
                'name': 'Prior similar purchase discussed',
                'weight': 4,
                'patterns': [r'purchased something like this before', r'bought something similar', r'previous vendor', r'last time they bought', r'prior purchase'],
                'partial_patterns': [r'used a tool before', r'legacy system', r'current vendor', r'incumbent'],
                'missing_hint': 'Have they purchased something like this before and how did that work?'
            },
            {
                'name': 'Path to budget owner exists',
                'weight': 5,
                'patterns': [r'introduce.*budget', r'introduce.*finance', r'loop in finance', r'bring.*budget owner', r'meet.*budget owner', r'intro to.*cfo'],
                'partial_patterns': [r'open to intro', r'can bring in', r'will involve finance', r'finance will join'],
                'missing_hint': 'Will they introduce the person who controls the money?'
            },
        ],
        'next_step': 'Understand Budget',
    },
    'Authority': {
        'weight': 25,
        'description': 'Buying committee visibility, role clarity, and path to the people who can move the deal.',
        'signals': [
            {
                'name': 'Buying committee members named',
                'weight': 9,
                'patterns': [r'buying committee', r'stakeholders include', r'decision team', r'committee includes', r'leadership team includes'],
                'partial_patterns': [r'stakeholder', r'approver', r'decision maker', r'committee'],
                'missing_hint': 'Who is on the buying committee by name?'
            },
            {
                'name': 'Roles in decision are clear',
                'weight': 8,
                'patterns': [r'final approver', r'technical approver', r'legal approver', r'procurement approver', r'role in approval', r'signs off on'],
                'partial_patterns': [r'approver', r'legal', r'procurement', r'it', r'security'],
                'missing_hint': 'What role does each person play in approval?'
            },
            {
                'name': 'Access path to authority exists',
                'weight': 8,
                'patterns': [r'introduce.*decision', r'bring.*vp', r'bring.*committee', r'intro to.*leader', r'can get.*meeting', r'will involve.*leader'],
                'partial_patterns': [r'open to meeting', r'will pull in', r'can loop in'],
                'missing_hint': 'Can the current contact get you to the right decision participants?'
            },
        ],
        'next_step': 'Map Buying Committee',
    },
    'Need': {
        'weight': 25,
        'description': 'Specific quantified problem, target outcome, business upside, and what must change to achieve it.',
        'signals': [
            {
                'name': 'Problem is quantified',
                'weight': 10,
                'patterns': [NUMBER_PATTERN + r'.*(?:problem|issue|loss|drop|miss|decline|shortfall|waste)', r'(?:problem|issue|loss|drop|miss|decline|shortfall|waste).+' + NUMBER_PATTERN],
                'partial_patterns': [r'problem', r'issue', r'pain', r'challenge', r'not working'],
                'missing_hint': 'What is the problem in hard numbers?'
            },
            {
                'name': 'Target outcome defined',
                'weight': 8,
                'patterns': [NUMBER_PATTERN + r'.*(?:increase|reduce|improve|grow|save|target|goal)', r'(?:increase|reduce|improve|grow|save|target|goal).+' + NUMBER_PATTERN],
                'partial_patterns': [r'goal', r'objective', r'want to', r'need to', r'looking to'],
                'missing_hint': 'What exact business outcome do they want instead?'
            },
            {
                'name': 'Business impact and dependencies clear',
                'weight': 7,
                'patterns': [r'if this changes', r'good outcomes', r'result would be', r'need to make that happen', r'because of that', r'cost of doing nothing'],
                'partial_patterns': [r'impact', r'outcome', r'result', r'benefit'],
                'missing_hint': 'Why does this matter, and what must happen to get the result?'
            },
        ],
        'next_step': 'Quantify Need',
    },
    'Timeline': {
        'weight': 25,
        'description': 'Closed-won date, reason the date matters, and milestones required to get there.',
        'signals': [
            {
                'name': 'Target close date exists',
                'weight': 10,
                'patterns': [r'target close', r'close by', r'closed won by', r'sign by', r'contract by', DATE_PATTERN],
                'partial_patterns': [r'this quarter', r'next quarter', r'next month', r'timeline', r'go live'],
                'missing_hint': 'What is the actual target close-won date?'
            },
            {
                'name': 'Compelling event or reason is stated',
                'weight': 8,
                'patterns': [r'compelling event', r'before .* launch', r'before .* renewal', r'leadership meeting', r'board meeting', r'vacation', r'fiscal year', r'deadline'],
                'partial_patterns': [r'need this by', r'driving timing', r'urgent'],
                'missing_hint': 'Why does that date matter?'
            },
            {
                'name': 'Milestones to closed won are mapped',
                'weight': 7,
                'patterns': [r'next step', r'milestone', r'legal then', r'procurement then', r'steps required', r'between now and signature'],
                'partial_patterns': [r'next meeting', r'follow up', r'process'],
                'missing_hint': 'What steps need to happen before signature?'
            },
        ],
        'next_step': 'Lock Timeline',
    },
}

MEDDPICC_MODEL = {
    'Metrics': {
        'weight': 12,
        'description': 'Hard, specific numbers tied to a measurable outcome.',
        'signals': [
            {'name': 'Hard number present', 'weight': 4, 'patterns': [NUMBER_PATTERN], 'partial_patterns': [r'sell more', r'increase', r'improve', r'reduce'], 'missing_hint': 'What exact number are they trying to move?'},
            {'name': 'Metric is specific, not generic', 'weight': 4, 'patterns': [NUMBER_PATTERN + r'.*(?:new|used|preowned|ford|gm|service|revenue|gross|appointments|leads|hours|days|stores|locations)', r'(?:new|used|preowned|ford|gm|service|revenue|gross|appointments|leads|hours|days|stores|locations).+' + NUMBER_PATTERN], 'partial_patterns': [r'more cars', r'more revenue', r'better conversion'], 'missing_hint': 'Is the metric specific enough to act on?'},
            {'name': 'Current-to-target comparison exists', 'weight': 4, 'patterns': [r'from .* to .*', r'vs last', r'compared to', r'from \d+ to \d+', r'last month.*this month', r'currently .* target'], 'partial_patterns': [r'goal', r'target'], 'missing_hint': 'What is the current state and what is the target state?'}
        ],
        'next_step': 'Tighten Metrics',
    },
    'Economic Buyer': {
        'weight': 13,
        'description': 'Head of the buying committee who can move money between competing initiatives.',
        'signals': [
            {'name': 'Economic buyer is named', 'weight': 5, 'patterns': [r'economic buyer', r'head of the buying committee', r'can move money', r'controls priorities', r'controls initiatives'], 'partial_patterns': [r'vp', r'cfo', r'gm', r'head of'], 'missing_hint': 'Who is the real economic buyer? Do not confuse this with a signer.'},
            {'name': 'Champion has access to economic buyer', 'weight': 4, 'patterns': [r'access to .*economic buyer', r'works closely with .*economic buyer', r'reports to .*economic buyer', r'meets with .*economic buyer'], 'partial_patterns': [r'can get to', r'knows them'], 'missing_hint': 'Does the champion have access to the economic buyer?'},
            {'name': 'Champion knows what buyer cares about', 'weight': 4, 'patterns': [r'cares about', r'priorities are', r'initiative is tied to', r'what matters to .*buyer'], 'partial_patterns': [r'likely cares', r'probably cares'], 'missing_hint': 'What does the economic buyer care about right now?'}
        ],
        'next_step': 'Map Economic Buyer',
    },
    'Decision Criteria': {
        'weight': 12,
        'description': 'The technical boxes and evaluation requirements that must be satisfied.',
        'signals': [
            {'name': 'Technical requirements listed', 'weight': 4, 'patterns': [r'rfp', r'requirements', r'must have', r'technical criteria', r'security requirements', r'integration requirements'], 'partial_patterns': [r'check boxes', r'criteria', r'requirements'], 'missing_hint': 'What exact technical boxes must be checked?'},
            {'name': 'Success criteria are explicit', 'weight': 4, 'patterns': [r'pass .*review', r'needs to support', r'must integrate', r'must comply', r'acceptance criteria'], 'partial_patterns': [r'support', r'needs'], 'missing_hint': 'How will they judge whether you passed the test?'},
            {'name': 'Gaps against criteria are known', 'weight': 4, 'patterns': [r'gap', r'blocker', r'risk against criteria', r'not supported', r'need workaround'], 'partial_patterns': [r'concern', r'question'], 'missing_hint': 'Where could you fail their checklist?'}
        ],
        'next_step': 'Clarify Decision Criteria',
    },
    'Decision Process': {
        'weight': 13,
        'description': 'Who is involved, timeline to decide, compelling event, and precedent from past decisions.',
        'signals': [
            {'name': 'People in process identified', 'weight': 4, 'patterns': [r'involved in the decision', r'decision process includes', r'committee includes', r'who is involved'], 'partial_patterns': [r'legal', r'procurement', r'it', r'security'], 'missing_hint': 'Who is involved in making the decision?'},
            {'name': 'Decision timeline exists', 'weight': 4, 'patterns': [DATE_PATTERN, r'decision by', r'select vendor by', r'choose by'], 'partial_patterns': [r'next month', r'this quarter', r'timeline'], 'missing_hint': 'When will the decision actually be made?'},
            {'name': 'Compelling event / precedent known', 'weight': 5, 'patterns': [r'compelling event', r'vacation', r'how long did it take last time', r'last time took', r'before .* renewal', r'before .* event'], 'partial_patterns': [r'urgent', r'deadline'], 'missing_hint': 'Are there vacations, precedent timing, or an event driving the decision?'}
        ],
        'next_step': 'Map Decision Process',
    },
    'Paper Process': {
        'weight': 12,
        'description': 'Paperwork steps and how long each step takes.',
        'signals': [
            {'name': 'Paper steps are named', 'weight': 5, 'patterns': [r'paper process', r'legal review', r'procurement', r'msa', r'security review', r'dpa', r'redlines'], 'partial_patterns': [r'contract', r'legal', r'paperwork'], 'missing_hint': 'What paperwork steps happen after selection?'},
            {'name': 'Durations are known', 'weight': 4, 'patterns': [NUMBER_PATTERN + r'.*(?:days|weeks)', r'takes .*days', r'takes .*weeks'], 'partial_patterns': [r'usually takes a while', r'can be slow'], 'missing_hint': 'How long does each paper step take?'},
            {'name': 'Owners are known', 'weight': 3, 'patterns': [r'legal owns', r'procurement owns', r'security owns', r'owned by'], 'partial_patterns': [r'legal team', r'procurement team'], 'missing_hint': 'Who owns each paper step?'}
        ],
        'next_step': 'Map Paper Process',
    },
    'Identify Pain': {
        'weight': 13,
        'description': 'Current state, why it fails, desired future state, outcomes, and required enablers.',
        'signals': [
            {'name': 'Current state is explicit', 'weight': 3, 'patterns': [r'right now they', r'currently', r'today they', r'what they are doing now'], 'partial_patterns': [r'currently use', r'as-is'], 'missing_hint': 'What are they doing now?'},
            {'name': 'Why current state fails is explicit', 'weight': 3, 'patterns': [r'isn\'t working', r'not working because', r'fails because', r'breaks down when'], 'partial_patterns': [r'problem', r'issue'], 'missing_hint': 'Why is the current approach failing?'},
            {'name': 'Future state is explicit', 'weight': 2, 'patterns': [r'want to have happen', r'would rather', r'future state', r'instead they want'], 'partial_patterns': [r'want to', r'need to'], 'missing_hint': 'What do they want to happen instead?'},
            {'name': 'Good outcomes are explicit', 'weight': 3, 'patterns': [r'good outcome', r'if that happens', r'result would be', r'benefit would be'], 'partial_patterns': [r'better outcome', r'benefit'], 'missing_hint': 'What good outcomes follow if this changes?'},
            {'name': 'Required enablers are clear', 'weight': 2, 'patterns': [r'need to make that happen', r'requires', r'for that to work'], 'partial_patterns': [r'need', r'requires'], 'missing_hint': 'What do they need in order to get the outcome?'}
        ],
        'next_step': 'Deepen Pain',
    },
    'Champion': {
        'weight': 13,
        'description': 'A tested champion who has influence, sells when you are not in the room, and opens doors.',
        'signals': [
            {'name': 'Champion identified', 'weight': 3, 'patterns': [r'champion', r'our internal lead', r'point person', r'internal advocate'], 'partial_patterns': [r'friendly contact', r'supporter'], 'missing_hint': 'Who is the champion?'},
            {'name': 'Champion has influence', 'weight': 4, 'patterns': [r'influence', r'trusted by leadership', r'respected internally', r'has pull'], 'partial_patterns': [r'well connected', r'close to leadership'], 'missing_hint': 'Do they actually have influence?'},
            {'name': 'Champion sells when you are absent', 'weight': 3, 'patterns': [r'sells for us', r'advocates internally', r'pushes this when we are not there', r'circulates our case'], 'partial_patterns': [r'positive about us', r'likes the solution'], 'missing_hint': 'Do they sell when you are not in the room?'},
            {'name': 'Champion introduces committee access', 'weight': 3, 'patterns': [r'introduced us', r'opened doors', r'brought in', r'introduced .*committee'], 'partial_patterns': [r'willing to intro', r'can bring in'], 'missing_hint': 'Have they introduced you to others on the buying committee?'}
        ],
        'next_step': 'Test Champion',
    },
    'Competition': {
        'weight': 12,
        'description': 'Named competitors, status quo, and other projects that can steal budget or attention.',
        'signals': [
            {'name': 'External competitors identified', 'weight': 4, 'patterns': [r'competitor', r'vendor shortlist', r'against .*vendor', r'evaluating .*vendor'], 'partial_patterns': [r'alternatives', r'other vendors'], 'missing_hint': 'Who else are they evaluating?'},
            {'name': 'Status quo risk understood', 'weight': 4, 'patterns': [r'do nothing', r'status quo', r'stay with current', r'keep current process'], 'partial_patterns': [r'maybe no change', r'might keep current'], 'missing_hint': 'How strong is the status quo?'},
            {'name': 'Other initiatives competing for budget', 'weight': 4, 'patterns': [r'other project', r'competing initiative', r'budget could move', r'priority conflict', r'another initiative'], 'partial_patterns': [r'other priorities', r'budget pressure'], 'missing_hint': 'What else could steal budget from this project?'}
        ],
        'next_step': 'Pressure-Test Competition',
    },
}


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




def ai_limit_check():
    now = time.time()
    if AI_MAX_PER_HOUR <= 0:
        return False
    with AI_LOCK:
        while AI_CALLS and now - AI_CALLS[0] > 3600:
            AI_CALLS.popleft()
        if len(AI_CALLS) >= AI_MAX_PER_HOUR:
            return False
        AI_CALLS.append(now)
        return True


def split_sentences(text):
    cleaned = re.sub(r'\s+', ' ', text).strip()
    if not cleaned:
        return []
    parts = re.split(r'(?<=[.!?])\s+', cleaned)
    return [p.strip() for p in parts if p.strip()]


def dedupe_list(items):
    out = []
    seen = set()
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            out.append(item.strip())
            seen.add(key)
    return out


def sentence_hits(text, patterns, max_items=4):
    sentences = split_sentences(text)
    found = []
    for sent in sentences:
        lower = sent.lower()
        if any(re.search(p, lower, re.I) for p in patterns):
            found.append(sent.strip())
        if len(found) >= max_items:
            break
    return dedupe_list(found)


def has_hard_number(text):
    return re.search(NUMBER_PATTERN, text) is not None


def has_specific_metric_context(text):
    return re.search(r'(?:new|used|preowned|ford|gm|service|revenue|gross|appointments|leads|hours|days|stores|locations)', text, re.I) is not None


def has_date_like(text):
    return re.search(DATE_PATTERN, text, re.I) is not None


def db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_stat(conn, key, value=0):
    cur = conn.execute('SELECT value FROM stats WHERE key=?', (key,))
    if cur.fetchone() is None:
        conn.execute('INSERT INTO stats (key, value) VALUES (?, ?)', (key, value))


def init_db():
    conn = db()
    conn.execute('CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, value INTEGER NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS waitlist (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    for key in ['deal_count', 'total_score', 'deal_count_bant', 'total_score_bant', 'deal_count_meddpicc', 'total_score_meddpicc']:
        ensure_stat(conn, key, 0)
    conn.commit()
    conn.close()


def stat_value(key, default=0):
    conn = db()
    row = conn.execute('SELECT value FROM stats WHERE key=?', (key,)).fetchone()
    conn.close()
    return int(row['value']) if row else default


def get_count():
    return stat_value('deal_count', 0)


def get_average_score(methodology=None):
    suffix = '' if not methodology else f'_{methodology}'
    count = stat_value(f'deal_count{suffix}', 0)
    total = stat_value(f'total_score{suffix}', 0)
    return round(total / count) if count else 0


def increment_stats(score, methodology):
    conn = db()
    conn.execute("UPDATE stats SET value = value + 1 WHERE key='deal_count'")
    conn.execute("UPDATE stats SET value = value + ? WHERE key='total_score'", (int(score),))
    conn.execute("UPDATE stats SET value = value + 1 WHERE key=?", (f'deal_count_{methodology}',))
    conn.execute("UPDATE stats SET value = value + ? WHERE key=?", (int(score), f'total_score_{methodology}'))
    conn.commit()
    deal_count = conn.execute("SELECT value FROM stats WHERE key='deal_count'").fetchone()['value']
    method_count = conn.execute("SELECT value FROM stats WHERE key=?", (f'deal_count_{methodology}',)).fetchone()['value']
    method_total = conn.execute("SELECT value FROM stats WHERE key=?", (f'total_score_{methodology}',)).fetchone()['value']
    conn.close()
    average = round(method_total / method_count) if method_count else 0
    return int(deal_count), int(average)


def infer_stage(text):
    lower = text.lower()
    for pat, stage, score in STAGE_PATTERNS:
        if re.search(pat, lower, re.I):
            return {'stage': stage, 'maturity_score': score}
    return {'stage': 'Unclear', 'maturity_score': 2}


def signal_strength(text, signal):
    complete_hits = sentence_hits(text, signal.get('patterns', []), max_items=2)
    partial_hits = sentence_hits(text, signal.get('partial_patterns', []), max_items=2)
    status = 'Missing'
    evidence = []
    points = 0
    if complete_hits:
        status = 'Complete'
        evidence = complete_hits
        points = signal['weight']
    elif partial_hits:
        status = 'Partial'
        evidence = partial_hits
        points = max(1, round(signal['weight'] * 0.45))

    # MEDDPICC metric hard-number guardrails
    if signal['name'] == 'Hard number present' and not has_hard_number(text):
        status, points, evidence = 'Missing', 0, []
    if signal['name'] == 'Metric is specific, not generic':
        if has_hard_number(text) and has_specific_metric_context(text):
            status = 'Complete'
            points = signal['weight']
            evidence = dedupe_list((complete_hits or partial_hits) + sentence_hits(text, [NUMBER_PATTERN + r'.*(?:new|used|preowned|ford|gm|service|revenue|gross|appointments|leads|hours|days|stores|locations)'], 2))
        elif has_hard_number(text):
            status = 'Partial'
            points = max(1, round(signal['weight'] * 0.45))
            evidence = dedupe_list((complete_hits or partial_hits) + sentence_hits(text, [NUMBER_PATTERN], 2))
    if signal['name'] == 'Current-to-target comparison exists' and status != 'Complete' and re.search(r'from\s+' + NUMBER_PATTERN + r'.*to\s+' + NUMBER_PATTERN, text, re.I):
        status = 'Complete'
        points = signal['weight']
        evidence = sentence_hits(text, [r'from .* to .*', r'vs last', r'compared to'], 2)
    if signal['name'] == 'Decision timeline exists' and status != 'Complete' and has_date_like(text):
        status = 'Complete'
        points = signal['weight']
        evidence = dedupe_list((evidence or []) + sentence_hits(text, [DATE_PATTERN], 2))
    if signal['name'] == 'Target close date exists' and status != 'Complete' and has_date_like(text):
        status = 'Complete'
        points = signal['weight']
        evidence = dedupe_list((evidence or []) + sentence_hits(text, [DATE_PATTERN], 2))

    lower = text.lower()
    for neg in NEGATION_WORDS:
        if neg in lower and status == 'Complete':
            status = 'Partial'
            points = max(1, round(signal['weight'] * 0.45))
            break
    return {
        'name': signal['name'],
        'status': status,
        'points': points,
        'max_points': signal['weight'],
        'evidence': evidence[:2],
        'missing_hint': signal['missing_hint'],
    }


def category_status(points, max_points):
    pct = points / max_points if max_points else 0
    if pct >= 0.85:
        return 'Complete'
    if pct >= 0.35:
        return 'Partial'
    return 'Missing'


def analyze_model(text, model):
    parts = {}
    all_signal_statuses = []
    for category, cfg in model.items():
        signal_results = [signal_strength(text, signal) for signal in cfg['signals']]
        points = sum(item['points'] for item in signal_results)
        status = category_status(points, cfg['weight'])
        evidence = dedupe_list([ev for item in signal_results for ev in item['evidence']])[:4]
        missing = [item['missing_hint'] for item in signal_results if item['status'] != 'Complete']
        notes = []
        if status == 'Partial' and points < cfg['weight']:
            notes.append('Some evidence exists, but it is incomplete or implied. Tighten this before calling the deal qualified.')
        parts[category] = {
            'status': status,
            'points': points,
            'max_points': cfg['weight'],
            'evidence': evidence,
            'missing': missing,
            'correction': correction_text(category, model),
            'notes': notes,
            'signals': signal_results,
            'description': cfg['description'],
        }
        all_signal_statuses.extend(signal_results)
    total_score = sum(v['points'] for v in parts.values())
    total_max = sum(v['max_points'] for v in parts.values())
    score = round((total_score / total_max) * 100) if total_max else 0
    return parts, score, all_signal_statuses


def correction_text(category, model):
    if model is BANT_MODEL:
        corrections = {
            'Budget': 'Confirm how budget gets approved, who controls the spend, whether they bought something similar before, and whether your contact will bring that person into the deal.',
            'Authority': 'Name the buying committee, map each role, and confirm who can block or accelerate the deal before it reaches late stage.',
            'Need': 'Get to the hard-number problem, the target outcome, the upside of fixing it, and what has to change for success to happen.',
            'Timeline': 'Confirm the real close-won date, the reason timing matters, and the milestones required to hit that date.'
        }
        return corrections[category]
    corrections = {
        'Metrics': 'Push for specific current-state and target-state numbers. Generic goals get minimal credit.',
        'Economic Buyer': 'Name the real economic buyer, make sure the champion has access to them, and understand what priorities they can move money between.',
        'Decision Criteria': 'Get the exact technical boxes that need to be checked and identify where you could fail them.',
        'Decision Process': 'Map who is involved, the decision date, the compelling event, and how long this took in the past.',
        'Paper Process': 'List the paper steps, who owns each one, and how long they usually take.',
        'Identify Pain': 'Describe what they do now, why it fails, what they want instead, the business outcome of changing it, and what is required to get there.',
        'Champion': 'Pressure-test the champion. Influence, internal selling, and introductions matter more than friendliness.',
        'Competition': 'Pressure-test named competitors, the status quo, and any other initiative that could steal money or attention.'
    }
    return corrections[category]


def choose_next_step(parts, stage_info, methodology):
    order = []
    for key, val in parts.items():
        if val['status'] != 'Complete':
            order.append((val['points'] / max(1, val['max_points']), key))
    if not order:
        return 'Advance to Mutual Action Plan'
    if stage_info['maturity_score'] >= LATE_STAGE_THRESHOLD:
        late_priority = ['Authority', 'Budget'] if methodology == 'bant' else ['Economic Buyer', 'Decision Process', 'Paper Process']
        for item in late_priority:
            if item in parts and parts[item]['status'] != 'Complete':
                return model_for(methodology)[item]['next_step']
    weakest = sorted(order, key=lambda x: x[0])[0][1]
    return model_for(methodology)[weakest]['next_step']


def red_flags(parts, stage_info, methodology):
    flags = []
    late = stage_info['maturity_score'] >= LATE_STAGE_THRESHOLD
    if methodology == 'bant':
        if late:
            for key in ['Budget', 'Authority', 'Timeline']:
                if parts[key]['status'] != 'Complete':
                    flags.append(f'Late-stage warning: {key} is {parts[key]["status"].lower()} while the deal appears to be in {stage_info["stage"]}.')
        if parts['Need']['status'] == 'Missing':
            flags.append('No quantified problem found. This looks like deal motion without a measurable reason to buy.')
    else:
        if late:
            for key in ['Economic Buyer', 'Decision Process', 'Paper Process']:
                if parts[key]['status'] != 'Complete':
                    flags.append(f'Late-stage warning: {key} is {parts[key]["status"].lower()} even though the deal appears to be in {stage_info["stage"]}.')
        if parts['Metrics']['status'] != 'Complete':
            flags.append('Metrics are weak. The deal may feel urgent without a precise numeric reason to change.')
        if parts['Champion']['status'] == 'Missing':
            flags.append('No tested champion found. That makes internal momentum fragile.')
    for key, val in parts.items():
        flags.extend([f'{key}: {n}' for n in val['notes']])
    return flags


def confidence_label(stage_info, parts):
    evidence_points = sum(len(v['evidence']) for v in parts.values())
    if stage_info['stage'] != 'Unclear' and evidence_points >= 8:
        return 'High'
    if evidence_points >= 4:
        return 'Medium'
    return 'Low'


def score_benchmark_text(score, average):
    if average == 0:
        return 'First deal on the board. You are the founding poop scientist.'
    delta = score - average
    if delta >= 15:
        return f'This deal is {delta} points above average. Somebody actually plunged before forecast call.'
    if delta >= 1:
        return f'This deal is {delta} points above average. Mild toilet pride is allowed.'
    if delta == 0:
        return 'This deal is exactly average. Neutral poop turbulence.'
    if delta <= -15:
        return f'This deal is {abs(delta)} points below average. The sewer goblin is eating your forecast.'
    return f'This deal is {abs(delta)} points below average. The pipe still smells suspicious.'


def pick_gif(score):
    for item in GIF_CONFIG:
        if score <= item['max']:
            return item
    return GIF_CONFIG[-1]


def model_for(methodology):
    return MEDDPICC_MODEL if methodology == 'meddpicc' else BANT_MODEL


def methodology_title(methodology):
    return 'MEDDPICC' if methodology == 'meddpicc' else 'BANT'


def unlocked_summary(parts, methodology):
    weak = [name for name, val in parts.items() if val['status'] != 'Complete']
    if not weak:
        return f'{methodology_title(methodology)} looks clean. Move to a mutual action plan and protect momentum.'
    return f'Tighten {", ".join(weak[:3])} before you call this fully qualified.'


def fallback_email_and_script(raw_text, parts, stage_info, methodology, next_step):
    weak = [name for name, val in parts.items() if val['status'] != 'Complete']
    primary = weak[0] if weak else ('Budget' if methodology == 'bant' else 'Metrics')
    missing = parts[primary]['missing'][:3]
    subject = {
        'bant': {
            'Understand Budget': 'Quick alignment on budget process',
            'Map Buying Committee': 'Quick alignment on who should be involved',
            'Quantify Need': 'Confirming the business impact and target outcome',
            'Lock Timeline': 'Working backward from your target close date',
            'Advance to Mutual Action Plan': 'Proposed next steps to keep momentum',
        },
        'meddpicc': {
            'Tighten Metrics': 'Confirming the exact numbers behind this initiative',
            'Map Economic Buyer': 'Clarifying economic buyer and priorities',
            'Clarify Decision Criteria': 'Confirming the technical boxes that matter most',
            'Map Decision Process': 'Aligning on decision path and timing',
            'Map Paper Process': 'Clarifying contract and approval steps',
            'Deepen Pain': 'Confirming the current state and desired outcome',
            'Test Champion': 'Making sure we have the right internal support',
            'Pressure-Test Competition': 'Pressure-testing alternatives and competing priorities',
            'Advance to Mutual Action Plan': 'Proposed next steps to keep momentum',
        }
    }
    subj = subject[methodology].get(next_step, 'Aligning on next steps')
    ask_lines = '\n'.join([f'- {item}' for item in missing]) if missing else '- Confirm the remaining decision gaps'
    email = (
        'Hi team,\n\n'
        f'To keep this moving, I want to make sure we close the remaining {methodology_title(methodology)} gaps before the next forecast conversation. '
        f'Right now the biggest area to tighten is {primary}.\n\n'
        'The fastest way to do that would be to confirm:\n'
        f'{ask_lines}\n\n'
        f'If helpful, I can keep the next conversation tight and focused so we can get this into a cleaner stage than {stage_info["stage"]}.\n\n'
        'Best,'
    )
    script = [
        f'Before we move this past {stage_info["stage"]}, I want to pressure-test {primary}.',
    ] + missing[:3]
    if not missing:
        script += [
            'What could still get in the way between now and signature?',
            'Who else should we involve now so the process stays smooth?'
        ]
    return {'subject': subj, 'body': email}, script


def ai_email_and_script(raw_text, parts, stage_info, methodology, next_step):
    if not OPENAI_API_KEY:
        return fallback_email_and_script(raw_text, parts, stage_info, methodology, next_step)
    if not ai_limit_check():
        fallback_email, fallback_script = fallback_email_and_script(raw_text, parts, stage_info, methodology, next_step)
        fallback_email['subject'] = 'AI hourly limit reached'
        fallback_email['body'] = AI_LIMIT_MESSAGE + '\n\n' + fallback_email['body']
        return fallback_email, fallback_script

    gaps = []
    for category, val in parts.items():
        if val['status'] != 'Complete':
            gaps.append({'category': category, 'missing': val['missing'][:4], 'evidence': val['evidence'][:2], 'status': val['status']})

    system_prompt = (
        'You are a pragmatic B2B sales coach. '
        'Write crisp, useful output for a seller. '
        'The email must be written as the seller sending a next-step email directly to the customer. '
        'Do not write an internal email, manager update, recap note, or message to colleagues. '
        'Address the customer directly and focus on moving the deal forward. '
        'The call_script must be customer-facing talk track or questions for the seller to use live with the customer. '
        'Never use em dashes. '
        'Avoid generic filler. '
        'Keep it grounded in the supplied deal context and methodology. '
        'Return strict JSON with keys subject, body, and call_script. '
        'call_script must be an array of 4 concise lines.'
    )
    user_prompt = {
        'methodology': methodology_title(methodology),
        'stage': stage_info['stage'],
        'next_step': next_step,
        'summary': unlocked_summary(parts, methodology),
        'gaps': gaps,
        'email_audience': 'customer',
        'seller_goal': 'send the next external email to the customer that helps collect missing deal information and move the opportunity forward',
        'deal_text': raw_text[:8000],
    }
    payload = {
        'model': OPENAI_MODEL,
        'input': [
            {'role': 'system', 'content': [{'type': 'input_text', 'text': system_prompt}]},
            {'role': 'user', 'content': [{'type': 'input_text', 'text': json.dumps(user_prompt)}]},
        ],
        'text': {'format': {'type': 'json_object'}},
    }
    req = urlrequest.Request(
        'https://api.openai.com/v1/responses',
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {OPENAI_API_KEY}',
        },
        method='POST'
    )
    try:
        with urlrequest.urlopen(req, timeout=OPENAI_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        text = None
        if isinstance(data.get('output_text'), str):
            text = data['output_text']
        else:
            for item in data.get('output', []):
                for content in item.get('content', []):
                    if content.get('type') == 'output_text':
                        text = content.get('text')
                        break
                if text:
                    break
        parsed = json.loads(text) if text else {}
        subject = parsed.get('subject') or 'Aligning on next steps'
        body = parsed.get('body') or fallback_email_and_script(raw_text, parts, stage_info, methodology, next_step)[0]['body']
        call_script = parsed.get('call_script') or fallback_email_and_script(raw_text, parts, stage_info, methodology, next_step)[1]
        if not isinstance(call_script, list):
            call_script = [str(call_script)]
        return {'subject': str(subject), 'body': str(body)}, [str(x) for x in call_script[:6]]
    except Exception:
        app.logger.exception('AI generation failed, using fallback content')
        return fallback_email_and_script(raw_text, parts, stage_info, methodology, next_step)


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
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=pipe_checker_waitlist.csv'})


@app.route('/waitlist-view', methods=['GET'])
def waitlist_view():
    key = request.args.get('key')
    if key != ADMIN_EXPORT_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = db()
    rows = conn.execute('SELECT email, created_at FROM waitlist ORDER BY created_at DESC').fetchall()
    conn.close()
    html = """
    <html><head><title>Pipe Checker Waitlist</title><style>
    body { font-family: Arial, sans-serif; padding: 24px; }
    table { border-collapse: collapse; width: 100%; max-width: 900px; }
    th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
    th { background: #f5f5f5; }
    </style></head><body><h1>Pipe Checker Waitlist</h1><table><thead><tr><th>Email</th><th>Created At</th></tr></thead><tbody>
    """
    for row in rows:
        html += f"<tr><td>{row['email']}</td><td>{row['created_at']}</td></tr>"
    html += "</tbody></table></body></html>"
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
    methodology = ((payload.get('methodology') or 'bant').strip().lower())
    if methodology not in {'bant', 'meddpicc'}:
        methodology = 'bant'
    if not raw_text:
        return jsonify({'error': 'Paste opportunity context before running analysis.'}), 400
    if len(raw_text) < 40:
        return jsonify({'error': 'Add more detail. The pasted context is too short for a useful analysis.'}), 400
    if len(raw_text) > MAX_INPUT_CHARS:
        return jsonify({'error': f'Input is too large. Keep it under about {MAX_INPUT_CHARS:,} characters.'}), 400

    model = model_for(methodology)
    stage_info = infer_stage(raw_text)
    parts, score, _signal_results = analyze_model(raw_text, model)
    step = choose_next_step(parts, stage_info, methodology)
    deal_count, average_score = increment_stats(score, methodology)
    gif = pick_gif(score)
    email, call_script = ai_email_and_script(raw_text, parts, stage_info, methodology, step)

    result = {
        'methodology': methodology,
        'methodology_label': methodology_title(methodology),
        'overall_score': score,
        'average_score': average_score,
        'benchmark_text': score_benchmark_text(score, average_score),
        'stage': stage_info['stage'],
        'confidence': confidence_label(stage_info, parts),
        'analysis': parts,
        'red_flags': red_flags(parts, stage_info, methodology),
        'next_step': step,
        'email': email,
        'call_script': call_script,
        'deal_count': deal_count,
        'gif': gif,
        'ai_enabled': bool(OPENAI_API_KEY),
        'summary_text': unlocked_summary(parts, methodology),
    }
    return jsonify(result)


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', '8000'))
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    init_db()
