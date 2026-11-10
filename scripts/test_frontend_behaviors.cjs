const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const formatter = require(path.join(root, 'static/vendor/sql-formatter/sql-formatter.min.js'));

test('admin practice uses the same controller with authenticated practice API transport', async () => {
    const f = context('static/js/student.js');
    await f.run('studentFetch("/api/student/questions")');
    assert.equal(f.state.requests.at(-1)[0], '/api/student/questions');
    f.ctx.document.body.dataset.adminPractice = 'true';
    await f.run('studentFetch("/api/student/submit", {method:"POST",body:"{}"})');
    const [url, options] = f.state.requests.at(-1);
    assert.equal(url, '/api/admin/practice/submit');
    assert.equal(options.headers.get('X-CSRF-Token'), 'csrf');
    assert.equal(options.body, '{}');
});

function element(value = '') {
    const classes = new Set();
    return { value, dataset: {}, style: {}, textContent: '', innerHTML: '', disabled: false,
        addEventListener(name, fn) { this[name] = fn; },
        classList: { add: c => classes.add(c), remove: c => classes.delete(c), toggle(c, yes) { yes ? classes.add(c) : classes.delete(c); } } };
}
function context(file, nodes = {}) {
    const state = { toasts: [], logs: [], autosaved: 0, requests: [], intervals: [], callbacks: {} };
    const storage = new Map();
    const ctx = { console: { log() {}, warn() {}, error() {} }, URL, Headers, AbortController,
        navigator: { onLine: true }, sqlFormatter: formatter,
        document: { body: { dataset: { nim: 'TEST', token: 'token', category: 'A' } }, hidden: false, hasFocus: () => true,
            getElementById: id => nodes[id] || null, querySelector: () => ({ content: 'csrf' }), querySelectorAll: () => [],
            addEventListener: (name, cb) => { state.callbacks[name] = cb; } },
        localStorage: { getItem: k => storage.get(k) || null, setItem: (k, v) => storage.set(k, v), removeItem: k => storage.delete(k) },
        setTimeout: () => 1, clearTimeout() {}, clearInterval() {}, setInterval: fn => { state.intervals.push(fn); return 1; },
        addEventListener() {}, location: { href: 'http://localhost/exam', origin: 'http://localhost', replace() {} },
        fetch: async (...args) => { state.requests.push(args); if (state.failure) throw state.failure; return state.response; }, state };
    ctx.window = ctx;
    vm.createContext(ctx);
    let source = fs.readFileSync(path.join(root, file), 'utf8');
    if (file.endsWith('student.js')) source = source.replace(/\}\)\(\);\s*$/, 'window.__testExecute = code => eval(code);\n})();');
    vm.runInContext(source, ctx);
    const run = code => ctx.__testExecute ? ctx.__testExecute(code) : vm.runInContext(code, ctx);
    run('showToast=(...a)=>state.toasts.push(a);');
    return { ctx, state, nodes, run };
}
function editor(text, from = 0, to = from) {
    const cm = { value: text, old: [], readonly: false, getOption() { return this.readonly; },
        getValue() { return this.value; }, somethingSelected() { return from !== to; }, getSelection() { return this.value.slice(from, to); },
        listSelections() { return [{}]; }, getCursor(which) { return { index: which === 'from' ? from : to }; }, indexFromPos(p) { return p.index; },
        lastLine() { return this.value.split('\n').length - 1; }, getLine(n) { return this.value.split('\n')[n]; }, focus() {},
        operation(fn) { fn(); }, replaceSelection(value) { this.old.push(this.value); this.value = this.value.slice(0, from) + value + this.value.slice(to); },
        replaceRange(value) { this.old.push(this.value); this.value = value; }, undo() { this.value = this.old.pop(); } };
    return cm;
}
function student(text = 'select 1', from = 0, to = from) {
    const nodes = Object.fromEntries(['submission-status-tag', 'autograder-banner', 'btn-submit-answer', 'output-content', 'output-meta-text'].map(k => [k, element()]));
    const fixture = context('static/js/student.js', nodes);
    fixture.ctx.cm = editor(text, from, to);
    fixture.run('editor=cm; questionsData=[{id:1,score_weight:10}]; studentNim="TEST"; studentSessionToken="token"; triggerDebouncedAutosave=()=>state.autosaved++;');
    return fixture;
}

test('student DOM initialization registers a defined Format SQL handler', () => {
    const f = student();
    f.nodes['btn-format-sql'] = element(); f.nodes['btn-run-query'] = element();
    f.run('initCodeMirror=initThemeSelector=setupAntiCheat=setupExitModal=loadQuestions=initDatabaseSelector=initImageLightbox=initNetworkMonitor=startHeartbeat=()=>{};');
    assert.doesNotThrow(() => f.state.callbacks.DOMContentLoaded());
    assert.equal(typeof f.nodes['btn-format-sql'].click, 'function');
});
test('formatter preserves PostgreSQL literals, quoted identifiers, comments and undo', () => {
    const source = '-- select literal\nselect \'from select\', $tag$from SELECT$tag$, "CaseSensitive", 1.2300 from t where id=1;';
    const f = student(source); f.run('formatQuery()');
    for (const literal of ['-- select literal', "'from select'", '$tag$from SELECT$tag$', '"CaseSensitive"', '1.2300']) assert.ok(f.ctx.cm.value.includes(literal));
    assert.match(f.ctx.cm.value, /SELECT/); assert.ok(f.ctx.cm.value.split('\n').length > 3);
    f.ctx.cm.undo(); assert.equal(f.ctx.cm.value, source);
});
test('format selection preserves all text outside selected SQL', () => {
    const prefix = 'select 1;\n'; const query = 'select a,b from t where id=2;';
    const f = student(prefix + query, prefix.length, prefix.length + query.length); f.run('formatQuery()');
    assert.ok(f.ctx.cm.value.startsWith(prefix)); assert.match(f.ctx.cm.value.slice(prefix.length), /SELECT/);
});
test('selection inside literal never rewrites the literal', () => {
    const source = "SELECT 'select from' AS x;"; const f = student(source, 8, 14); f.run('formatQuery()');
    assert.equal(f.ctx.cm.value, source); assert.equal(f.state.toasts.at(-1)[1], 'warning');
});
test('unsupported SQL and missing formatter leave original text intact', () => {
    const f = student("select 'unfinished"); f.run('formatQuery()'); assert.equal(f.ctx.cm.value, "select 'unfinished");
    f.ctx.sqlFormatter = null; f.run('formatQuery()'); assert.equal(f.ctx.cm.old.length, 0);
});
test('editing package suggests target number and restores original on return', () => {
    const nodes = { 'modal-q-id': element('42'), 'modal-q-category': element('B'), 'modal-q-num': element('9') };
    nodes['modal-q-id'].dataset = { originalCategory: 'A', originalNumber: '9' };
    const f = context('static/js/admin.js', nodes);
    f.run('questionsList=[{id:42,category:"A",question_number:9},{id:43,category:"B",question_number:3}]; updateNextQuestionNumber();');
    assert.equal(nodes['modal-q-num'].value, 4);
    nodes['modal-q-category'].value = 'A'; f.run('updateNextQuestionNumber()'); assert.equal(nodes['modal-q-num'].value, '9');
    nodes['modal-q-id'].value = ''; f.run('updateNextQuestionNumber()'); assert.equal(nodes['modal-q-num'].value, 10);
});
test('latest wrong verdict stays separate from retained best score', () => {
    const f = student();
    f.run('renderSubmissionState({score_weight:10},{score:10,is_correct:1,latest_attempt:{graded:1,is_correct:0,score:0,feedback:"secret diagnostic"}})');
    assert.match(f.nodes['submission-status-tag'].textContent, /Salah/);
    assert.match(f.nodes['autograder-banner'].innerHTML, /10 \/ 10/);
    assert.doesNotMatch(f.nodes['autograder-banner'].innerHTML, /secret diagnostic/);
});
test('pending answer is stored without a false zero or wrong verdict', () => {
    const f = student(); f.run('renderSubmissionState({score_weight:10},{score:null,latest_attempt:{graded:0,is_correct:null,score:null}})');
    assert.match(f.nodes['submission-status-tag'].textContent, /Tersimpan/);
    assert.doesNotMatch(f.nodes['autograder-banner'].textContent, /salah|0 poin/i);
});
test('submit wrong confirms persistence; no red error toast', async () => {
    const f = student('SELECT 2'); f.state.response = { ok: true, status: 200, json: async () => ({ status: 'success', graded: true,
        is_correct: true, score: 10, score_retained: true, best_submission: { submitted_query: 'SELECT 1', score: 10, is_correct: 1 },
        latest_attempt: { submitted_query: 'SELECT 2', graded: 1, score: 0, is_correct: 0 }, columns: [], rows: [] }) };
    await f.run('submitAnswer()');
    assert.deepEqual(Array.from(f.state.toasts.at(-1)), ['Jawaban tersimpan. Hasil: salah.', 'info']);
    assert.match(f.nodes['autograder-banner'].innerHTML, /10 \/ 10/);
});
test('lost submit response reports unknown persistence, preserving draft', async () => {
    const f = student('SELECT 2'); f.state.failure = new Error('Disconnected'); await f.run('submitAnswer()');
    assert.match(f.state.toasts.at(-1)[0], /belum dapat dipastikan/);
    assert.ok(f.ctx.localStorage.getItem('sqlexam_draft_TEST_1'));
});
test('visibility and window blur produce one log per focus loss', () => {
    const f = student(); f.run('logCheatingAction=(...a)=>state.logs.push(a); recordExamFocus(true); recordExamFocus(true); recordExamFocus(false); recordExamFocus(false);');
    assert.equal(f.state.logs.length, 2); assert.equal(f.state.logs[0][0], 'blur_tab');
    assert.equal(f.state.toasts.length, 1); assert.equal(f.state.toasts[0][1], 'warning');
});
test('heartbeat 503 is not misclassified as a kicked session', async () => {
    const f = student(); f.run('showKickModal=()=>state.kicked=true;');
    f.state.response = { ok: false, status: 503, json: async () => ({ detail: 'Temporary failure' }) };
    await f.run('checkNetworkNow()'); assert.equal(f.state.kicked, undefined); assert.equal(f.run('isNetworkOnline'), true);
    await f.run('checkNetworkNow()'); assert.equal(f.run('isNetworkOnline'), false);
});
test('invalid session and throttling never masquerade as lost Wi-Fi', async () => {
    const f = student(); f.run('showKickModal=()=>state.kicked=true;');
    f.state.response = { ok: true, status: 200, json: async () => ({ valid: false, reason: 'Expired' }) };
    await f.run('checkNetworkNow()'); assert.equal(f.state.kicked, true); assert.equal(f.run('isNetworkOnline'), true);
    f.state.kicked = false; f.state.response = { ok: false, status: 429, json: async () => ({ detail: 'Busy' }) };
    await f.run('checkNetworkNow()'); assert.equal(f.state.kicked, false); assert.equal(f.run('isNetworkOnline'), true);
});
test('concurrent heartbeat checks share a single request', async () => {
    const f = student(); let done;
    f.state.response = { ok: true, status: 200, json: () => new Promise(resolve => { done = resolve; }) };
    const a = f.run('checkNetworkNow()'); const b = f.run('checkNetworkNow()');
    await new Promise(resolve => setImmediate(resolve)); done({ valid: true, exam_state: 'active' }); await Promise.all([a, b]);
    assert.equal(f.state.requests.length, 1);
});

test('lobby deduplicates NIM cards while retaining distinct students on a shared IP', () => {
    const html = fs.readFileSync(path.join(root, 'templates/waiting_room.html'), 'utf8');
    const source = html.slice(html.indexOf('    function renderParticipants('), html.indexOf('    function buildCard('));
    const cards = [];
    function card(nim) { return { dataset: { nim }, remove() { cards.splice(cards.indexOf(this), 1); } }; }
    const counter = {};
    const grid = { querySelectorAll: () => cards.slice(), querySelector: () => null, appendChild: node => cards.push(node) };
    const ctx = { document: { getElementById: id => id === 'wr-participant-count' ? counter : grid }, buildCard: p => card(p.nim) };
    vm.createContext(ctx); vm.runInContext(source, ctx);
    cards.push(card('NIM1'), card('nim1'));
    ctx.list = [{ nim: 'NIM1', ip_address: '10.0.0.1' }, { nim: 'nim1', ip_address: '10.0.0.1' }, { nim: 'NIM2', ip_address: '10.0.0.1' }];
    vm.runInContext('renderParticipants(list)', ctx);
    assert.equal(counter.textContent, 2); assert.equal(cards.length, 2);
    vm.runInContext('renderParticipants(list)', ctx); assert.equal(cards.length, 2);
});

test('pending grades refresh without replacing editor and stop after completion', async () => {
    const f = student('SELECT unsaved_draft');
    f.run('submissionsMap={1:{latest_attempt:{id:3,graded:0,grading_job:{status:"queued"}}}}; renderQuestionNav=()=>{}; renderSubmissionState=()=>{};');
    f.state.response={ok:true,status:200,json:async()=>({submissions:{1:{score:10,is_correct:1,latest_attempt:{id:3,graded:1}}}})};
    await f.run('refreshPendingGrades()');
    assert.equal(f.run('submissionsMap[1].score'),10);
    assert.equal(f.ctx.cm.value,'SELECT unsaved_draft');
    await f.run('refreshPendingGrades()');
    assert.equal(f.state.requests.length,1);
});

test('grade refresh does not overwrite a newer submit response', async () => {
    const f = student();
    f.run('submissionsMap={1:{latest_attempt:{id:3,graded:0,grading_job:{status:"queued"}}}};');
    f.state.response={ok:true,status:200,json:async()=>{
        f.run('submissionsMap[1]={score:20,latest_attempt:{id:4,graded:1}}');
        return {submissions:{1:{score:10,latest_attempt:{id:3,graded:1}}}};
    }};
    await f.run('refreshPendingGrades()');
    assert.equal(f.run('submissionsMap[1].score'),20);
});
