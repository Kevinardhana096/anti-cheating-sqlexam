(function () {
"use strict";

/**
 * Offline SQL Exam System - Student Workspace Controller
 * Features:
 * - Scope Encapsulation (IIFE) against DevTools console tampering
 * - CodeMirror 5 Integration (PostgreSQL Mode & Autocompletion)
 * - Fullscreen Enforcement Guard & Exit Logging
 * - Anti-F12 / DevTools Shortcut Blocking & Context Menu Disabling
 * - Anti-Copy-Paste Security Filter
 * - Tab Switch / Focus Loss Detection Logging
 * - IP-Binding Heartbeat & Kick Detection
 * - Live Query Execution & Dynamic Data Grid
 * - Answer Submission & Status Tracking
 * - CodeMirror Dynamic SQL Autocomplete Hints
 */

let editor = null;
let currentQuestionIndex = 0;
let questionsData = [];
let submissionsMap = {};
let studentNim = "";
let studentSessionToken = "";
let studentCategory = "";
let pendingCategorySelection = null;
let heartbeatInterval = null;
let isLoggingOut = false;

function studentFetch(url, options = {}) {
    if (document.body.dataset.adminPractice === "true") {
        url = url.replace("/api/student/", "/api/admin/practice/");
        const headers = new Headers(options.headers || {});
        headers.set("X-CSRF-Token", document.querySelector('meta[name="admin-csrf-token"]').content);
        options = { ...options, headers };
    }
    return fetch(url, options);
}

function isUserLoggingOut() {
    return isLoggingOut || Boolean(window.isLoggingOut) || Boolean(window._examAccessClosed);
}

// ==============================================================================
// Toast Notification System for Student IDE (Hoisted Top-Level Declaration)
// ==============================================================================
function showToast(message, type = "info") {
    try {
        let container = document.getElementById("toast-container");
        if (!container) {
            container = document.createElement("div");
            container.id = "toast-container";
            container.className = "toast-container";
            document.body.appendChild(container);
        }

        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.transition = "opacity 0.25s ease, transform 0.25s ease";
            toast.style.opacity = "0";
            toast.style.transform = "translateX(50px)";
            setTimeout(() => toast.remove(), 250);
        }, 3500);
    } catch (e) {
        console.warn("[Toast]", type, message);
    }
}
window.showToast = showToast;

// Initialize when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
    studentNim = document.body.dataset.nim || "";
    studentSessionToken = document.body.dataset.token || "";
    studentCategory = document.body.dataset.category || "";

    if (studentCategory) {
        updateHeaderPackageBadge(studentCategory);
    }

    initCodeMirror();
    initThemeSelector();
    setupAntiCheat();
    setupExitModal();
    loadQuestions();
    if (studentCategory) initDatabaseSelector();
    initImageLightbox();
    initNetworkMonitor();
    startHeartbeat();

    // Bind Package Selection Modal Buttons
    document.getElementById("btn-cancel-select-pkg")?.addEventListener("click", cancelPackageSelection);
    document.getElementById("btn-proceed-lock-pkg")?.addEventListener("click", confirmPackageSelection);

    // Bind Action Buttons
    document.getElementById("btn-run-query").addEventListener("click", runQuery);
    document.getElementById("btn-submit-answer").addEventListener("click", submitAnswer);
    document.getElementById("btn-format-sql")?.addEventListener("click", formatQuery);
    document.getElementById("btn-practice-reset-package")?.addEventListener("click", async () => {
        try {
            const response = await studentFetch("/api/student/reset-package", { method: "POST" });
            if (!response.ok) throw new Error("Pilihan paket belum dapat direset. Muat ulang halaman.");
            window.location.reload();
        } catch (error) { showToast(error.message, "warning"); }
    });
});

// ==============================================================================

// ==============================================================================
// 1.0 Local Draft Autosave Manager (Fase 1 - Anti Data Loss)
// ==============================================================================
const AUTOSAVE_DEBOUNCE_MS = 600;
let autosaveTimer = null;

function getDraftStorageKey(nim, questionId) {
    return `sqlexam_draft_${nim || "guest"}_${questionId}`;
}

function saveLocalDraft(nim, questionId, queryText) {
    if (!nim || !questionId) return;
    try {
        const payload = {
            nim: String(nim),
            questionId: Number(questionId),
            query: queryText,
            timestamp: Date.now()
        };
        localStorage.setItem(getDraftStorageKey(nim, questionId), JSON.stringify(payload));
        updateAutosaveUI("saved");
    } catch (e) {
        console.warn("Autosave to localStorage failed:", e);
        updateAutosaveUI("error");
    }
}

function getLocalDraft(nim, questionId) {
    if (!nim || !questionId) return null;
    try {
        const raw = localStorage.getItem(getDraftStorageKey(nim, questionId));
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        // Expire drafts older than 24 hours
        if (Date.now() - (parsed.timestamp || 0) > 24 * 60 * 60 * 1000) {
            localStorage.removeItem(getDraftStorageKey(nim, questionId));
            return null;
        }
        return parsed;
    } catch (e) {
        return null;
    }
}

function triggerDebouncedAutosave() {
    if (!editor || !questionsData || !questionsData[currentQuestionIndex]) return;
    const q = questionsData[currentQuestionIndex];
    const currentVal = editor.getValue();

    // Cache in RAM
    q.draftQuery = currentVal;

    updateAutosaveUI("saving");

    if (autosaveTimer) {
        clearTimeout(autosaveTimer);
    }

    autosaveTimer = setTimeout(() => {
        saveLocalDraft(studentNim, q.id, currentVal);
    }, AUTOSAVE_DEBOUNCE_MS);
}

function updateAutosaveUI(state) {
    // Label autosave/draft dihapus dari UI sesuai Subtask 4.3 untuk mengurangi distraksi.
    // Autosave ke localStorage tetap berjalan di background tanpa visual UI noise.
    return;
}

window.saveLocalDraft = saveLocalDraft;
window.getLocalDraft = getLocalDraft;
window.triggerDebouncedAutosave = triggerDebouncedAutosave;
window.getCurrentQuestionId = () => (questionsData[currentQuestionIndex] ? questionsData[currentQuestionIndex].id : null);


// ==============================================================================
// 1.2 Network Monitor & Offline Guard (Fase 2)
// ==============================================================================
let isNetworkOnline = true;
let consecutiveHeartbeatFailures = 0;
const MAX_HEARTBEAT_FAILS_BEFORE_OFFLINE = 2;

function initNetworkMonitor() {
    window.addEventListener("online", () => {
        console.log("[NetworkMonitor] Browser fired 'online' event");
        checkNetworkNow();
    });

    window.addEventListener("offline", () => {
        console.warn("[NetworkMonitor] Browser fired 'offline' event");
        setNetworkState(false, "Kabel LAN atau Wi-Fi Anda terputus!");
    });

    if (!navigator.onLine) {
        setNetworkState(false, "Perangkat Anda sedang offline.");
    }
}

function setNetworkState(isOnline, reason = "") {
    if (isNetworkOnline === isOnline) return;
    isNetworkOnline = isOnline;

    const badge = document.getElementById("network-status-badge");
    const textEl = document.getElementById("network-status-text");
    const banner = document.getElementById("offline-warning-banner");
    const submitBtn = document.getElementById("btn-submit-answer");

    if (isOnline) {
        consecutiveHeartbeatFailures = 0;
        if (badge) {
            badge.className = "status-badge badge-online";
            badge.title = "Koneksi jaringan dan server aktif stabil";
        }
        if (textEl) {
            textEl.textContent = "Terkoneksi";
        }
        if (banner) {
            banner.style.display = "none";
        }
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.title = "Simpan query ini sebagai jawaban resmi";
        }
        showToast("Koneksi jaringan telah pulih kembali. Anda dapat melanjutkan ujian.", "success");
    } else {
        if (badge) {
            badge.className = "status-badge badge-danger network-offline-badge";
            badge.title = "Koneksi jaringan atau server terputus! Kueri Anda tetap aman di draf lokal.";
        }
        if (textEl) {
            textEl.textContent = "Jaringan Terputus";
        }
        if (banner) {
            banner.style.display = "block";
        }
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.title = "Koneksi terputus. Harap tunggu hingga jaringan tersambung kembali.";
        }
        showToast(reason || "Peringatan: Koneksi jaringan terputus. Jangan me-refresh browser!", "danger");
    }
}

let heartbeatProbe = null;
let lastBusyNotice = 0;

function checkNetworkNow() {
    if (heartbeatProbe) return heartbeatProbe;
    heartbeatProbe = probeStudentHeartbeat().finally(() => { heartbeatProbe = null; });
    return heartbeatProbe;
}

async function probeStudentHeartbeat() {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 6000);
    try {
        const response = await studentFetch("/api/student/heartbeat", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ nim: studentNim, session_token: studentSessionToken }),
            signal: controller.signal
        });
        const data = await response.json();
        if (response.status === 401 || (response.ok && data.valid === false)) {
            clearInterval(heartbeatInterval);
            showKickModal(data.reason || data.detail || "Sesi sudah tidak aktif. Silakan login kembali.");
            return false;
        }
        if (leaveInactiveExam(data.exam_state)) return false;
        if (response.status === 429) {
            consecutiveHeartbeatFailures = 0;
            setNetworkState(true);
            if (Date.now() - lastBusyNotice > 30000) {
                lastBusyNotice = Date.now();
                showToast("Server sibuk. Pemeriksaan sesi akan dicoba lagi.", "warning");
            }
            return false;
        }
        if (!response.ok || data.valid !== true) throw new Error(`Heartbeat HTTP ${response.status}`);
        consecutiveHeartbeatFailures = 0;
        setNetworkState(true);
        if (studentCategory && !data.selected_category) {
            studentCategory = "";
            updateHeaderPackageBadge(null);
            showToast("Pilihan paket di-reset pengawas. Silakan pilih paket baru.", "info");
            loadQuestions();
        }
        void refreshPendingGrades();
        return true;
    } catch (error) {
        consecutiveHeartbeatFailures++;
        console.warn(`[Heartbeat] Probe failed (${consecutiveHeartbeatFailures}):`, error.name);
        if (consecutiveHeartbeatFailures >= MAX_HEARTBEAT_FAILS_BEFORE_OFFLINE || !navigator.onLine) {
            setNetworkState(false, "Koneksi ke server belum tersedia. Draf tetap tersimpan di perangkat ini.");
        }
        return false;
    } finally {
        clearTimeout(timeout);
    }
}

window.checkNetworkNow = checkNetworkNow;
window.setNetworkState = setNetworkState;
window.getIsNetworkOnline = () => isNetworkOnline;

function formatQuery() {
    if (!editor || editor.getOption("readOnly")) return;
    const selected = editor.somethingSelected();
    const original = selected ? editor.getSelection() : editor.getValue();
    if (!original.trim()) return;
    if (!window.sqlFormatter?.format) {
        showToast("Formatter belum tersedia. Muat ulang halaman; draf tetap tersimpan.", "warning");
        return;
    }
    try {
        const options = { language: "postgresql", keywordCase: "upper", tabWidth: 4, linesBetweenQueries: 1 };
        const fullText = editor.getValue();
        if (fullText.length > 50000 || editor.listSelections().length !== 1) {
            showToast("Pilih satu bagian SQL dengan panjang maksimal 50.000 karakter.", "warning");
            return;
        }
        const formatted = window.sqlFormatter.format(original, options);
        if (selected) {
            const from = editor.indexFromPos(editor.getCursor("from"));
            const to = editor.indexFromPos(editor.getCursor("to"));
            const candidate = fullText.slice(0, from) + formatted + fullText.slice(to);
            if (window.sqlFormatter.format(fullText, options) !== window.sqlFormatter.format(candidate, options)) {
                showToast("Pilih bagian SQL lengkap di luar literal atau komentar. Teks asli tetap dipertahankan.", "warning");
                return;
            }
        }
        editor.operation(() => {
            if (selected) editor.replaceSelection(formatted, "around", "+format");
            else editor.replaceRange(formatted, { line: 0, ch: 0 }, { line: editor.lastLine(), ch: editor.getLine(editor.lastLine()).length }, "+format");
        });
        editor.focus();
        triggerDebouncedAutosave();
        showToast(selected ? "Bagian SQL yang dipilih sudah dirapikan." : "SQL sudah dirapikan.", "info");
    } catch (error) {
        showToast("Bagian SQL ini belum dapat diformat. Teks asli tetap dipertahankan.", "warning");
    }
}

// 1. CodeMirror SQL Editor Initialization
// ==============================================================================
function insertJoinClause(cm) {
    if (cm.getOption("readOnly") || cm.somethingSelected() || cm.listSelections().length !== 1) return;

    const cursor = cm.getCursor();
    const tokenType = cm.getTokenAt(cursor, true).type || "";
    if (/\b(?:comment|string(?:-\d+)?)\b/.test(tokenType)) return;

    const line = cm.getLine(cursor.line);
    const before = line.slice(0, cursor.ch);
    const after = line.slice(cursor.ch);
    if (/^ ON /i.test(after)) {
        const joinOrOn = cm.getLineTokens(cursor.line, true).filter(token =>
            token.end <= cursor.ch && token.type === "keyword" && /^(JOIN|ON)$/i.test(token.string)
        ).pop();
        if (joinOrOn && /^JOIN$/i.test(joinOrOn.string)) {
            if (before.slice(joinOrOn.end).trim()) {
                cm.setCursor(CodeMirror.Pos(cursor.line, cursor.ch + 4));
            }
            return;
        }
    }

    const prefix = before && !/\s$/.test(before) ? " " : "";
    cm.operation(() => {
        cm.replaceRange(`${prefix}JOIN  ON `, cursor, cursor, "+join");
        cm.setCursor(CodeMirror.Pos(cursor.line, cursor.ch + prefix.length + 5));
    });
}

function initCodeMirror() {
    const textarea = document.getElementById("sql-editor");
    if (!textarea) return;

    editor = CodeMirror.fromTextArea(textarea, {
        mode: "text/x-pgsql",
        theme: THEME_CM_MAP[localStorage.getItem(THEME_STORAGE_KEY) || "dracula"] || "dracula",
        lineNumbers: true,
        indentWithTabs: false,
        smartIndent: true,
        indentUnit: 4,
        matchBrackets: true,
        autoCloseBrackets: true,
        lineWrapping: true,
        extraKeys: {
            "Ctrl-Space": "autocomplete",
            "Alt-J": insertJoinClause,
            "Ctrl-Enter": () => runQuery(),
            "Cmd-Enter": () => runQuery(),
            "Shift-Ctrl-Enter": () => runQuery(true),
            "Shift-Cmd-Enter": () => runQuery(true)
        }
    });
    window.editor = editor;

    // Refresh CodeMirror when window resizes to ensure proper line rendering
    window.addEventListener("resize", () => {
        if (editor) {
            editor.refresh();
        }
    });

    // Update Run button label dynamically when selection changes (Run Partial)
    // Debounced autosave to localStorage on typing (Fase 1)
    editor.on("change", (cm, changeObj) => {
        if (changeObj && changeObj.origin === "setValue") {
            return; // Ignore programmatic setValue
        }
        triggerDebouncedAutosave();
    });

    editor.on("cursorActivity", () => {
        const sel = editor.getSelection().trim();
        const runText = document.getElementById("btn-run-text");
        const selBadge = document.getElementById("selection-indicator");
        if (runText) {
            runText.textContent = sel ? "Run Selection" : "Run Query";
        }
        if (selBadge) {
            selBadge.style.display = sel ? "inline-flex" : "none";
        }
    });

    // Smart Internal Copy-Paste Handler: Allows internal copy-paste, blocks external clipboard
    editor.on("paste", (cm, e) => {
        let pastedText = "";
        let isInternalHeader = false;

        if (e.clipboardData) {
            pastedText = e.clipboardData.getData("text/plain") || "";
            isInternalHeader = (e.clipboardData.getData("application/x-ide-internal") === "true");
        } else if (window.clipboardData) {
            pastedText = window.clipboardData.getData("Text") || "";
        }

        const normInternal = _normalizeClipboard(_internalClipboardText);
        const normPasted = _normalizeClipboard(pastedText);
        const isInternal = isInternalHeader || (normInternal && normPasted && normInternal === normPasted);

        if (isInternal) {
            // Internal copy-paste is ALLOWED
            e.preventDefault();
            cm.replaceSelection(pastedText);
            showToast("Menempelkan teks internal IDE.", "info");
        } else {
            // External paste from outside the browser / exam window is BLOCKED
            e.preventDefault();
            showToast("Paste dari luar jendela ujian dilarang! Silakan ketik query secara mandiri.", "danger");
            logCheatingAction("paste_attempt", "Mencoba melakukan paste teks dari luar aplikasi ujian");
        }
    });

    const suggestionsToggle = document.getElementById("sql-auto-suggestions");
    const suggestionsKey = "exam_sql_auto_suggestions";
    if (suggestionsToggle) {
        suggestionsToggle.checked = localStorage.getItem(suggestionsKey) !== "off";
        suggestionsToggle.addEventListener("change", () => {
            if (!suggestionsToggle.checked) editor.closeHint();
            localStorage.setItem(suggestionsKey, suggestionsToggle.checked ? "on" : "off");
        });
    }

    editor.on("inputRead", (cm, change) => {
        if (suggestionsToggle && !suggestionsToggle.checked) return;
        if (change.origin !== "+input") return;
        const text = change.text[0];
        if (/[a-zA-Z_]/.test(text) && !cm.state.completionActive) {
            CodeMirror.commands.autocomplete(cm, null, { completeSingle: false });
        }
    });
}

// ==============================================================================
// 1b. Global Theme System
// ==============================================================================
const THEME_STORAGE_KEY = "exam_global_theme";

// Maps website theme key -> CodeMirror theme name
const THEME_CM_MAP = {
    "dracula":    "dracula",
    "monokai":    "monokai",
    "nord":       "nord",
    "material":   "material-darker",
    "gruvbox":    "gruvbox-dark",
    "solarized":  "solarized dark",
    "ayu":        "ayu-dark",
    "light":      "default",        // CodeMirror's built-in light theme
};

function initThemeSelector() {
    const select = document.getElementById("global-theme-select");
    if (!select) return;

    const savedTheme = localStorage.getItem(THEME_STORAGE_KEY) || "dracula";
    applyGlobalTheme(savedTheme);

    select.addEventListener("change", () => {
        applyGlobalTheme(select.value);
        localStorage.setItem(THEME_STORAGE_KEY, select.value);
    });
}

function applyGlobalTheme(theme) {
    // Apply CSS variable theme to entire page
    document.documentElement.setAttribute("data-theme", theme);

    // Sync the dropdown
    const select = document.getElementById("global-theme-select");
    if (select) select.value = theme;

    // Sync CodeMirror editor theme
    if (editor) {
        const cmTheme = THEME_CM_MAP[theme] || "dracula";
        editor.setOption("theme", cmTheme);
    }
}


// ==============================================================================
// 2. Anti-Cheating & Security Controls (Smart Internal Clipboard)
// ==============================================================================
let _internalClipboardText = "";
let _internalClipboardTimestamp = 0;

function _normalizeClipboard(str) {
    return (str || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
}

function _registerInternalCopy(text) {
    if (typeof text === "string" && text.length > 0) {
        _internalClipboardText = text;
        _internalClipboardTimestamp = Date.now();
    }
}

let examFocusAway = false;
function recordExamFocus(away) {
    if (isUserLoggingOut() || examFocusAway === away) return;
    examFocusAway = away;
    if (away) showToast("Perpindahan fokus dicatat oleh sistem.", "warning");
    logCheatingAction(away ? "blur_tab" : "focus_tab", away ? "Fokus keluar dari halaman ujian" : "Fokus kembali ke halaman ujian");
}

function setupAntiCheat() {
    // 1. Prevent DevTools shortcuts & Inspect Element
    document.addEventListener("keydown", (e) => {
        const isCtrlOrCmd = e.ctrlKey || e.metaKey;
        const key = e.key ? e.key.toUpperCase() : "";

        // F12 or Ctrl+Shift+I/J/C or Ctrl+U (source) or Ctrl+S (save)
        if (
            key === "F12" ||
            (isCtrlOrCmd && e.shiftKey && (key === "I" || key === "J" || key === "C")) ||
            (isCtrlOrCmd && (key === "U" || key === "S"))
        ) {
            e.preventDefault();
            e.stopPropagation();
            showToast("Akses pintasan Developer Tools dinonaktifkan!", "danger");
            logCheatingAction("devtools_attempt", `Pintasan keyboard dicegah: ${e.code || e.key}`);
            return false;
        }
    }, true);

    // 2. Disable Right-Click Context Menu across exam interface
    document.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        showToast("Menu klik kanan dinonaktifkan selama ujian!", "warning");
    }, true);

    // 3. Track internal copy/cut across the IDE (editor, question descriptions, result table)
    document.addEventListener("copy", (e) => {
        let sel = "";
        if (editor && editor.hasFocus() && editor.somethingSelected()) {
            sel = editor.getSelection();
        } else {
            const s = window.getSelection();
            sel = s ? s.toString() : "";
        }
        if (sel) {
            _registerInternalCopy(sel);
            if (e.clipboardData) {
                try {
                    e.clipboardData.setData("text/plain", sel);
                    e.clipboardData.setData("application/x-ide-internal", "true");
                    e.preventDefault();
                } catch (err) {}
            }
        }
    });

    document.addEventListener("cut", (e) => {
        let sel = "";
        if (editor && editor.hasFocus() && editor.somethingSelected()) {
            sel = editor.getSelection();
        } else {
            const s = window.getSelection();
            sel = s ? s.toString() : "";
        }
        if (sel) {
            _registerInternalCopy(sel);
            if (e.clipboardData) {
                try {
                    e.clipboardData.setData("text/plain", sel);
                    e.clipboardData.setData("application/x-ide-internal", "true");
                    e.preventDefault();
                } catch (err) {}
            }
        }
    });

    // Intercept general clipboard paste on page (outside CodeMirror)
    document.addEventListener("paste", (e) => {
        if (e.target && (e.target.closest(".CodeMirror") || e.target.id === "sql-editor")) {
            return; // Handled directly by CodeMirror paste handler
        }

        let pastedText = "";
        let isInternalHeader = false;
        if (e.clipboardData) {
            pastedText = e.clipboardData.getData("text/plain") || "";
            isInternalHeader = (e.clipboardData.getData("application/x-ide-internal") === "true");
        }

        const normInternal = _normalizeClipboard(_internalClipboardText);
        const normPasted = _normalizeClipboard(pastedText);
        const isInternal = isInternalHeader || (normInternal && normPasted && normInternal === normPasted);

        if (!isInternal) {
            e.preventDefault();
            showToast("Paste dari luar dilarang pada sistem ujian!", "danger");
            logCheatingAction("paste_attempt", "Mencoba paste di luar editor");
        }
    });

    document.addEventListener("visibilitychange", () => recordExamFocus(document.hidden || !document.hasFocus()));
    window.addEventListener("blur", () => recordExamFocus(true));
    window.addEventListener("focus", () => recordExamFocus(document.hidden));

    // 5. Fullscreen Guard & Enforcement
    setupFullscreenGuard();
}

function setupFullscreenGuard() {
    const overlay = document.getElementById("fullscreen-overlay");
    const enterBtn = document.getElementById("btn-enter-fullscreen");

    function isExamFullscreen() {
        return Boolean(
            document.fullscreenElement ||
            document.webkitFullscreenElement ||
            document.mozFullScreenElement ||
            document.msFullscreenElement
        );
    }

    function requestExamFullscreen() {
        const elem = document.documentElement;
        const requestMethod = elem.requestFullscreen ||
                              elem.webkitRequestFullscreen ||
                              elem.mozRequestFullScreen ||
                              elem.msRequestFullscreen;
        if (requestMethod) {
            try {
                const p = requestMethod.call(elem);
                if (p && typeof p.then === "function") {
                    p.then(() => {
                        hideOverlay();
                        if (editor) editor.refresh();
                    }).catch((err) => {
                        console.warn("Fullscreen request error:", err);
                    });
                }
            } catch (err) {
                console.warn("Fullscreen call error:", err);
            }
        }
    }

    function showOverlay() {
        if (isUserLoggingOut()) return;
        if (overlay) {
            overlay.style.display = "flex";
        }
    }

    function hideOverlay() {
        if (overlay) {
            overlay.style.display = "none";
        }
    }

    if (enterBtn) {
        enterBtn.addEventListener("click", () => {
            requestExamFullscreen();
        });
    }

    let hasEnteredFullscreenOnce = false;
    let lastFullscreenExitLogTime = 0;

    function handleFullscreenChange() {
        if (isUserLoggingOut()) return;

        if (isExamFullscreen()) {
            hideOverlay();
            hasEnteredFullscreenOnce = true;
            if (editor) editor.refresh();
        } else {
            showOverlay();
            const now = Date.now();
            if (hasEnteredFullscreenOnce && now - lastFullscreenExitLogTime > 2500) {
                lastFullscreenExitLogTime = now;
                showToast("Peringatan: Keluar dari mode layar penuh dicatat sebagai pelanggaran!", "danger");
                logCheatingAction("exit_fullscreen", "Mahasiswa keluar dari mode layar penuh (fullscreen)");
            }
        }
    }

    document.addEventListener("fullscreenchange", handleFullscreenChange);
    document.addEventListener("webkitfullscreenchange", handleFullscreenChange);
    document.addEventListener("mozfullscreenchange", handleFullscreenChange);
    document.addEventListener("MSFullscreenChange", handleFullscreenChange);

    // Initial check on load
    if (!isExamFullscreen()) {
        showOverlay();
    }

    window.addEventListener("resize", () => {
        if (isUserLoggingOut()) return;
        if (!isExamFullscreen()) {
            showOverlay();
        }
    });
}

function setupExitModal() {
    const triggerBtn = document.getElementById("btn-logout-trigger");
    const modal = document.getElementById("exit-confirm-modal");
    const cancelBtn = document.getElementById("btn-exit-cancel");
    const cancelXBtn = document.getElementById("btn-exit-cancel-x");
    const proceedBtn = document.getElementById("btn-exit-proceed");

    if (!triggerBtn || !modal) return;

    function openModal() {
        modal.style.display = "flex";
    }

    function closeModal() {
        modal.style.display = "none";
    }

    triggerBtn.addEventListener("click", (e) => {
        e.preventDefault();
        openModal();
    });

    if (cancelBtn) {
        cancelBtn.addEventListener("click", closeModal);
    }
    if (cancelXBtn) {
        cancelXBtn.addEventListener("click", closeModal);
    }

    // Close when clicking directly on the backdrop
    modal.addEventListener("click", (e) => {
        if (e.target === modal) {
            closeModal();
        }
    });

    // Close on ESC key
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && modal.style.display === "flex") {
            closeModal();
        }
    });

    // Set flag when student confirms exit so navigation does not fire false blur warning
    if (proceedBtn) {
        proceedBtn.addEventListener("click", () => {
            isLoggingOut = true;
            window.isLoggingOut = true;
        });
    }
}

async function logCheatingAction(actionType, details) {
    try {
        await studentFetch("/api/student/log-event", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                nim: studentNim,
                session_token: studentSessionToken,
                action_type: actionType,
                details: details
            })
        });
    } catch (err) {
        console.error("Log error:", err);
    }
}

// ==============================================================================
// 3. Heartbeat & Anti-Joki Session Monitoring
// ==============================================================================
function leaveInactiveExam(state) {
    if (!state || state === "active") return false;
    const question = questionsData[currentQuestionIndex];
    if (editor && question) saveLocalDraft(studentNim, question.id, editor.getValue());
    isLoggingOut = true;
    window.isLoggingOut = true;
    clearInterval(heartbeatInterval);
    if (editor) editor.setOption("readOnly", "nocursor");
    window.location.replace("/waiting");
    return true;
}

function handleExamAccessResponse(response, data) {
    if (response.status === 401) {
        showKickModal(data.detail || "Sesi berakhir. Silakan login kembali.");
        return false;
    }
    if (leaveInactiveExam(data.exam_state)) return false;
    if (!response.ok) {
        showToast(data.detail || "Permintaan ditolak oleh server.", "warning");
        return false;
    }
    return true;
}

function startHeartbeat() {
    clearInterval(heartbeatInterval);
    heartbeatInterval = setInterval(() => { checkNetworkNow(); }, 12000);
}

function showKickModal(message) {
    if (document.getElementById("kick-modal")) return;
    window._examAccessClosed = true;
    if (editor) {
        editor.setOption("readOnly", "nocursor");
    }
    const modalHtml = `
        <div class="modal-backdrop is-active" id="kick-modal" role="dialog" aria-modal="true" style="display: flex;">
            <div class="modal-dialog">
                <div class="modal-header">
                    <h3 style="color: #ef4444;">Sesi Tidak Aktif</h3>
                </div>
                <div class="modal-body">
                    <div class="alert-box alert-danger">
                        ${escapeHtml(message)}
                    </div>
                    <p style="margin-top: 0.5rem; color: #cbd5e1;">
                        Sesi pada perangkat ini sudah tidak berlaku. Silakan login kembali atau hubungi pengawas.
                    </p>
                </div>
                <div class="modal-footer">
                    <a href="/login" class="btn btn-primary">Kembali ke Halaman Login</a>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML("beforeend", modalHtml);
}

// ==============================================================================
// 4. Questions & Navigation (Multi-Category / Package Support)
// ==============================================================================
let nextGradeRefresh = 0;
let gradeRefreshDelay = 12000;
let gradeRefreshRunning = false;

async function refreshPendingGrades() {
    const pending = Object.values(submissionsMap).some(sub => {
        const attempt = sub.latest_attempt;
        return attempt && !attempt.graded && ['queued', 'running'].includes(attempt.grading_job?.status);
    });
    if (!pending) { gradeRefreshDelay = 12000; nextGradeRefresh = 0; return; }
    if (gradeRefreshRunning || Date.now() < nextGradeRefresh) return;
    gradeRefreshRunning = true;
    const previous = submissionsMap;
    const snapshot = JSON.stringify(previous);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 6000);
    try {
        const response = await studentFetch('/api/student/questions', {signal: controller.signal});
        const data = await response.json();
        if (!handleExamAccessResponse(response, data) || !response.ok || !data.submissions) return;
        if (submissionsMap !== previous || JSON.stringify(previous) !== snapshot) return;
        submissionsMap = data.submissions;
        renderQuestionNav();
        const question = questionsData[currentQuestionIndex];
        if (question && submissionsMap[question.id]) renderSubmissionState(question, submissionsMap[question.id]);
    } catch (error) {
        console.warn('Status penilaian belum dapat diperbarui:', error);
    } finally {
        clearTimeout(timeout);
        nextGradeRefresh = Date.now() + gradeRefreshDelay;
        gradeRefreshDelay = Math.min(gradeRefreshDelay * 2, 60000);
        gradeRefreshRunning = false;
    }
}

async function loadQuestions() {
    try {
        const res = await studentFetch("/api/student/questions");
        const data = await res.json();
        if (!handleExamAccessResponse(res, data)) return;

        // Mahasiswa belum mengunci paket soal
        if (data.needs_category_selection) {
            studentCategory = "";
            updateHeaderPackageBadge(null);
            showCategorySelectionModal(data.categories || []);
            return;
        }

        // Mahasiswa sudah memiliki paket soal terkunci
        hideCategorySelectionModal();
        studentCategory = data.category || "";
        updateHeaderPackageBadge(studentCategory);

        if (data.questions) {
            questionsData = data.questions;
            submissionsMap = data.submissions || {};
            renderQuestionNav();
            selectQuestion(0);
        }
    } catch (err) {
        showToast("Gagal memuat daftar soal ujian.", "danger");
    }
}

function updateHeaderPackageBadge(category) {
    const container = document.getElementById("student-package-badge-container");
    const badge = document.getElementById("student-package-badge");
    if (!container || !badge) return;

    if (category) {
        const cleanCat = String(category).replace(/^Paket\s+/i, "");
        badge.textContent = `Paket ${cleanCat}`;
        container.style.display = "inline-flex";
    } else {
        container.style.display = "none";
    }
}

function showCategorySelectionModal(categories) {
    const modal = document.getElementById("category-select-modal");
    const grid = document.getElementById("category-cards-grid");
    if (!modal || !grid) return;

    if (!categories || categories.length === 0) {
        grid.innerHTML = `
            <div style="text-align: center; color: var(--text-muted); padding: 2rem; grid-column: 1 / -1;">
                <p style="font-size: 1rem; color: #f87171; margin-bottom: 0.5rem; font-weight: 600;">⚠️ Belum Ada Paket Soal Aktif</p>
                <p style="font-size: 0.85rem;">Bank soal ujian belum memiliki paket soal aktif. Harap tunggu arahan pengawas ujian.</p>
            </div>
        `;
        modal.style.display = "flex";
        return;
    }

    grid.innerHTML = "";
    categories.forEach(c => {
        const cat = c.category || c.code;
        const name = c.name || `Paket ${cat}`;
        const desc = c.description || "";
        const count = c.total_questions ?? c.question_count ?? c.count ?? 0;
        const weight = c.total_weight ?? c.total_score ?? 0;

        const card = document.createElement("div");
        card.className = "pkg-card";
        card.innerHTML = `
            <div class="pkg-card-title">
                <span style="font-weight: 800;">${escapeHtml(name)}</span>
                <span style="font-size: 1.15rem; color: #818cf8;">&rarr;</span>
            </div>
            ${desc ? `<div style="font-size: 0.78rem; color: var(--text-muted); margin: 0.35rem 0 0.5rem 0; line-height: 1.35; max-height: 2.8em; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;" title="${escapeHtml(desc)}">${escapeHtml(desc)}</div>` : ''}
            <div class="pkg-card-meta">
                <span class="pkg-pill">${count} Soal</span>
                <span class="pkg-pill" style="background: rgba(16, 185, 129, 0.15); color: #34d399;">${weight} Poin</span>
            </div>
            <button type="button" class="btn btn-primary btn-sm" style="margin-top: 0.5rem; width: 100%; pointer-events: none;">
                Pilih Paket Ini
            </button>
        `;
        card.addEventListener("click", () => onSelectPackageClicked(cat, name));
        grid.appendChild(card);
    });

    modal.style.display = "flex";
}

function hideCategorySelectionModal() {
    const modal = document.getElementById("category-select-modal");
    if (modal) modal.style.display = "none";
    const confirmModal = document.getElementById("category-confirm-modal");
    if (confirmModal) confirmModal.style.display = "none";
    pendingCategorySelection = null;
}

function onSelectPackageClicked(category, displayName) {
    pendingCategorySelection = category;
    const nameEl = document.getElementById("confirm-package-name");
    if (nameEl) nameEl.textContent = displayName || `Paket ${category}`;
    const confirmModal = document.getElementById("category-confirm-modal");
    if (confirmModal) confirmModal.style.display = "flex";
}

function cancelPackageSelection() {
    const confirmModal = document.getElementById("category-confirm-modal");
    if (confirmModal) confirmModal.style.display = "none";
    pendingCategorySelection = null;
}

let isLockingPackage = false;

async function confirmPackageSelection() {
    if (isLockingPackage || !pendingCategorySelection) return;
    isLockingPackage = true;
    const cat = pendingCategorySelection;
    const btn = document.getElementById("btn-proceed-lock-pkg");
    if (btn) {
        btn.disabled = true;
        btn.textContent = "Mengunci...";
    }

    try {
        const res = await studentFetch("/api/student/select-category", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                nim: studentNim,
                session_token: studentSessionToken,
                category: cat
            })
        });
        const data = await res.json();
        if (!handleExamAccessResponse(res, data)) return;
        if (res.ok && data.status === "success") {
            studentCategory = cat;
            initDatabaseSelector();
            hideCategorySelectionModal();
            updateHeaderPackageBadge(cat);
            questionsData = data.questions || [];
            submissionsMap = data.submissions || {};
            renderQuestionNav();
            selectQuestion(0);
            showToast(`Paket ${cat} berhasil dikunci! Selamat mengerjakan ujian.`, "success");
        } else {
            showToast(data.detail || data.message || "Gagal mengunci paket soal.", "danger");
        }
    } catch (err) {
        console.error("Gagal mengunci paket:", err);
        showToast("Terjadi gangguan koneksi saat memilih paket soal.", "danger");
    } finally {
        isLockingPackage = false;
        if (btn) {
            btn.disabled = false;
            btn.textContent = "Ya, Kunci Pilihan Saya";
        }
    }
}

// Expose modal handlers to window for template safety & testing
window.onSelectPackageClicked = onSelectPackageClicked;
window.cancelPackageSelection = cancelPackageSelection;
window.confirmPackageSelection = confirmPackageSelection;
window.loadQuestions = loadQuestions;

function renderQuestionNav() {
    const container = document.getElementById("question-nav");
    if (!container) return;
    container.innerHTML = "";

    const totalBadge = document.getElementById("q-total-count-badge");
    if (totalBadge) totalBadge.textContent = `${questionsData.length} Soal`;

    questionsData.forEach((q, idx) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `q-btn ${idx === currentQuestionIndex ? "active" : ""}`;
        const sub = submissionsMap[q.id];
        if (sub) {
            btn.classList.add("submitted");
            if (sub.is_correct === 1) {
                btn.classList.add("submitted-correct");
            } else {
                btn.classList.add("submitted-wrong");
            }
        }
        btn.textContent = q.question_number;
        btn.title = `Soal No. ${q.question_number}`;
        btn.addEventListener("click", () => selectQuestion(idx));
        container.appendChild(btn);
    });
}

function selectQuestion(idx) {
    if (idx < 0 || idx >= questionsData.length) return;

    // Save current editor draft to memory and localStorage before switching (Fase 1)
    if (currentQuestionIndex !== idx && questionsData[currentQuestionIndex] && editor) {
        const curQ = questionsData[currentQuestionIndex];
        const curVal = editor.getValue();
        if (curVal && curVal.trim()) {
            curQ.draftQuery = curVal;
            saveLocalDraft(studentNim, curQ.id, curVal);
        }
    }

    currentQuestionIndex = idx;
    const q = questionsData[idx];

    // Smart Auto-Switch Database Connection to match Question Target
    const targetDb = q.target_database || "pagila";
    const currentDb = getActiveDatabase();
    if (targetDb && targetDb !== currentDb) {
        setActiveDatabase(targetDb, true /* isAutoSwitch */);
    }

    // Update active button
    const buttons = document.querySelectorAll(".q-btn");
    buttons.forEach((b, i) => {
        b.classList.toggle("active", i === idx);
    });

    // Update question details in UI
    document.getElementById("q-number").textContent = `Soal No. ${q.question_number}`;
    const titleEl = document.getElementById("q-title");
    const rawTitle = (q.title || "").trim();
    if (!rawTitle || rawTitle === String(q.question_number)) {
        titleEl.textContent = `Instruksi Soal #${q.question_number}`;
    } else {
        titleEl.textContent = rawTitle;
    }
    const weightEl = document.getElementById("q-weight");
    if (weightEl) weightEl.style.display = "none";

    // Convert basic markdown/newlines to safe HTML
    document.getElementById("q-description").innerHTML = formatMarkdown(q.description);

    // Update Question Diagrams Gallery (Multi-Image Support)
    let qDiagrams = [];
    if (Array.isArray(q.question_images_list)) {
        qDiagrams = q.question_images_list;
    } else if (typeof q.question_images === "string" && q.question_images.trim()) {
        try {
            const parsed = JSON.parse(q.question_images);
            qDiagrams = Array.isArray(parsed) ? parsed : [q.question_images.trim()];
        } catch {
            qDiagrams = [q.question_images.trim()];
        }
    }

    const diagBox = document.getElementById("q-diagrams-box");
    const diagGallery = document.getElementById("q-diagrams-gallery");
    const diagCountBadge = document.getElementById("q-diagrams-count-badge");

    if (diagBox && diagGallery) {
        if (qDiagrams && qDiagrams.length > 0) {
            diagBox.style.display = "block";
            if (diagCountBadge) {
                diagCountBadge.textContent = `${qDiagrams.length} Gambar`;
            }
            diagGallery.innerHTML = qDiagrams.map((url, i) => `
                <div class="student-media-thumb-card" onclick="openImageLightboxWithList(window._currentQuestionDiagrams, ${i}, 'Diagram Soal #${q.question_number}')" title="Klik untuk memperbesar gambar">
                    <span class="student-media-badge">#${i + 1}</span>
                    <img src="${escapeHtml(url)}" alt="Diagram Soal ${i + 1}" class="student-media-thumb">
                </div>
            `).join("");
            window._currentQuestionDiagrams = qDiagrams;
        } else {
            diagBox.style.display = "none";
            diagGallery.innerHTML = "";
            window._currentQuestionDiagrams = [];
        }
    }

    // Update Expected Output Table Screenshot Container (Multi-Image Support)
    let expImages = [];
    if (Array.isArray(q.expected_output_images)) {
        expImages = q.expected_output_images;
    } else if (typeof q.expected_output_image === "string" && q.expected_output_image.trim()) {
        try {
            const parsed = JSON.parse(q.expected_output_image);
            expImages = Array.isArray(parsed) ? parsed : [q.expected_output_image.trim()];
        } catch {
            expImages = [q.expected_output_image.trim()];
        }
    }

    const outputBox = document.getElementById("q-expected-output-box");
    const outputGallery = document.getElementById("q-expected-output-gallery");
    const outputCountBadge = document.getElementById("q-output-count-badge");

    if (outputBox && outputGallery) {
        if (expImages && expImages.length > 0) {
            outputBox.style.display = "block";
            if (outputCountBadge) {
                outputCountBadge.textContent = `${expImages.length} Screenshot`;
            }
            outputGallery.innerHTML = expImages.map((url, i) => `
                <div class="student-media-thumb-card" onclick="openImageLightboxWithList(window._currentExpectedOutputImages, ${i}, 'Ekspektasi Output #${q.question_number}')" title="Klik untuk memperbesar screenshot tabel">
                    <span class="student-media-badge">#${i + 1}</span>
                    <img src="${escapeHtml(url)}" alt="Output Tabel ${i + 1}" class="student-media-thumb">
                </div>
            `).join("");
            window._currentExpectedOutputImages = expImages;
        } else {
            outputBox.style.display = "none";
            outputGallery.innerHTML = "";
            window._currentExpectedOutputImages = [];
        }
    }

    // Populate editor with submitted query, local draft, or clean placeholder (Fase 1)
    const existingSubmission = submissionsMap[q.id];
    const localDraft = getLocalDraft(studentNim, q.id);
    let queryToLoad = "";
    let isFromDraft = false;

    const latestQuery = existingSubmission?.latest_attempt?.submitted_query || existingSubmission?.submitted_query;
    if (latestQuery) {
        // If there is an active local draft that differs from submitted query, prefer local draft
        if (localDraft && localDraft.query && localDraft.query.trim() !== latestQuery.trim()) {
            queryToLoad = localDraft.query;
            isFromDraft = true;
        } else {
            queryToLoad = latestQuery;
        }
    } else if (localDraft && localDraft.query !== undefined) {
        queryToLoad = localDraft.query;
        isFromDraft = true;
    } else if (q.draftQuery !== undefined) {
        queryToLoad = q.draftQuery;
        isFromDraft = true;
    } else {
        const titleSuffix = (!rawTitle || rawTitle === String(q.question_number)) ? "" : `: ${rawTitle}`;
        queryToLoad = `-- Jawaban Soal No. ${q.question_number}${titleSuffix}\nSELECT \n`;
    }

    editor.setValue(queryToLoad);
    editor.focus();
    editor.setCursor(editor.lineCount(), 0);

    if (isFromDraft && localDraft) {
        updateAutosaveUI("restored");
    } else {
        updateAutosaveUI("saved");
    }

    renderSubmissionState(q, existingSubmission);
}

// ==============================================================================
// 5. Query Execution & Results Rendering
// ==============================================================================
async function runQuery(forcePartial = false) {
    if (!editor) return;
    const selection = editor.getSelection().trim();
    const fullQuery = editor.getValue().trim();
    const isPartial = (forcePartial && selection) || (selection.length > 0);
    const query = isPartial ? selection : fullQuery;

    if (!query) {
        showToast(isPartial ? "Bagian teks query yang diseleksi kosong." : "Editor query masih kosong.", "warning");
        return;
    }

    const runBtn = document.getElementById("btn-run-query");
    const outputContainer = document.getElementById("output-content");
    const metaContainer = document.getElementById("output-meta-text");

    // Hide autograder banner during scratchpad Run Query
    const autoBanner = document.getElementById("autograder-banner");
    if (autoBanner) {
        autoBanner.style.display = "none";
    }

    runBtn.disabled = true;
    outputContainer.innerHTML = `
        <div class="state-box">
            <div class="spinner"></div>
            <p>Mengeksekusi ${isPartial ? "bagian query terpilih (Partial)" : "query"} pada sandbox PostgreSQL...</p>
        </div>
    `;
    metaContainer.textContent = isPartial ? "Menjalankan (Partial)..." : "Menjalankan...";

    try {
        const currentActiveDb = getActiveDatabase();
        const res = await studentFetch("/api/student/run-query", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                nim: studentNim,
                session_token: studentSessionToken,
                query: query,
                active_database: currentActiveDb
            })
        });
        const data = await res.json();
        if (!handleExamAccessResponse(res, data)) return;

        if (data.success) {
            renderResultTable(data.columns, data.rows, data.row_count, data.is_truncated);
            metaContainer.textContent = `${data.row_count} baris dikembalikan (${data.execution_time_ms} ms)${isPartial ? " • Run Partial" : ""}`;
            if (isPartial) {
                showToast(`Partial run berhasil (${data.row_count} baris).`, "info");
            }
            if (data.virtual_db !== undefined) {
                updateSandboxOptionLabel(data.virtual_db);
            }
        } else {
            outputContainer.innerHTML = `
                <div class="state-box-error">
                    <strong>Error Eksekusi SQL${isPartial ? " (Partial Run)" : ""}:</strong><br>
                    ${escapeHtml(data.error || "Query gagal dieksekusi.")}
                </div>
            `;
            metaContainer.textContent = isPartial ? "Query Partial Gagal" : "Query Gagal";
        }
    } catch (err) {
        outputContainer.innerHTML = `
            <div class="state-box-error">
                <strong>Gagal Menghubungi Server:</strong><br>
                ${escapeHtml(err.message)}
            </div>
        `;
        metaContainer.textContent = "Koneksi Error";
    } finally {
        runBtn.disabled = false;
    }
}

function renderSubmissionState(question, submission) {
    const tag = document.getElementById("submission-status-tag");
    const banner = document.getElementById("autograder-banner");
    if (!submission) {
        if (tag) { tag.className = "status-badge badge-warning"; tag.textContent = "Belum Disubmit"; }
        if (banner) banner.style.display = "none";
        return;
    }
    const latest = submission.latest_attempt || submission;
    const pending = latest.graded === 0 || latest.graded === false || latest.is_correct === null;
    if (pending) {
        if (tag) { tag.className = "status-badge"; tag.textContent = "Tersimpan • Menunggu penilaian"; }
        if (banner) {
            banner.className = "autograder-banner";
            banner.style.display = "flex";
            banner.textContent = "Jawaban tersimpan. Menunggu penilaian.";
            if (submission.score != null) banner.textContent += ` Skor terbaik: ${Number(submission.score)} poin.`;
        }
        return;
    }
    const correct = latest.is_correct === 1 || latest.is_correct === true;
    const bestScore = Number(submission.score ?? 0);
    const latestScore = Number(latest.score ?? bestScore);
    const retained = submission.score_retained || latestScore < bestScore || (!correct && Boolean(submission.is_correct));
    if (tag) {
        tag.className = `status-badge ${correct ? "badge-online" : "badge-warning"}`;
        tag.textContent = `Tersimpan • ${correct ? "Benar" : "Salah"}`;
    }
    renderAutograderBanner(correct, latestScore, Number(question.score_weight ?? 0), "", retained, bestScore);
}

function renderAutograderBanner(isCorrect, score, maxScore, feedback, scoreRetained = false, retainedScore = 0) {
    const banner = document.getElementById("autograder-banner");
    if (!banner) return;
    banner.className = `autograder-banner ${isCorrect ? "banner-correct" : "banner-wrong"}`;
    banner.style.display = "flex";
    banner.innerHTML = `
        <div class="grader-top-row">
            <div class="grader-verdict ${isCorrect ? "correct" : "wrong"}">
                <span>Jawaban tersimpan. Hasil: ${isCorrect ? "benar" : "salah"}.</span>
            </div>
            <div class="grader-score-badge">Skor terbaik: ${Math.max(Number(score), Number(retainedScore))} / ${Number(maxScore)}</div>
        </div>
        ${scoreRetained ? '<div class="grader-feedback-msg">Skor terbaik sebelumnya tetap dipertahankan.</div>' : ''}
    `;
}

function renderResultTable(columns, rows, count, isTruncated, evalMode = null) {
    const container = document.getElementById("output-content");
    if (!columns || columns.length === 0) {
        container.innerHTML = `
            <div class="state-box state-box-empty">
                <p>Query berhasil dieksekusi (Tidak ada baris data kolom yang dikembalikan).</p>
            </div>
        `;
        return;
    }

    const evalClass = evalMode === "correct" ? "eval-correct" : (evalMode === "wrong" ? "eval-wrong" : "");
    let html = `<div class="result-table-container ${evalClass}"><table class="result-table"><thead><tr>`;
    columns.forEach(col => {
        html += `<th>${escapeHtml(col)}</th>`;
    });
    html += `</tr></thead><tbody>`;

    if (rows.length === 0) {
        html += `<tr><td colspan="${columns.length}" style="text-align: center; color: var(--text-subtle); padding: 2rem;">0 baris data ditemukan.</td></tr>`;
    } else {
        rows.forEach(row => {
            html += `<tr>`;
            row.forEach(val => {
                if (val === null) {
                    html += `<td><span class="val-null">NULL</span></td>`;
                } else {
                    html += `<td>${escapeHtml(String(val))}</td>`;
                }
            });
            html += `</tr>`;
        });
    }

    html += `</tbody></table>`;
    if (isTruncated) {
        html += `<div style="padding: 0.5rem 1rem; font-size: 0.75rem; color: #f59e0b; background: rgba(245, 158, 11, 0.1);">Tampilan dibatasi maksimal 500 baris untuk menjaga performa browser.</div>`;
    }
    html += `</div>`;
    container.innerHTML = html;
}

// ==============================================================================
// 6. Answer Submission
// ==============================================================================
async function submitAnswer() {
    const q = questionsData[currentQuestionIndex];
    if (!q || !editor) return;
    const query = editor.getValue().trim();
    if (!query) {
        showToast("Query jawaban tidak boleh kosong.", "warning");
        return;
    }
    saveLocalDraft(studentNim, q.id, query);
    if (!isNetworkOnline) {
        showToast("Belum dapat mengirim ke server. Draf disimpan di perangkat; coba lagi setelah koneksi pulih.", "warning");
        return;
    }

    const submitBtn = document.getElementById("btn-submit-answer");
    const originalText = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = `
        <span class="spinner" style="width: 14px; height: 14px; border-width: 2px; display: inline-block; vertical-align: middle; margin-right: 5px;"></span>
        Mengevaluasi...
    `;

    const metaContainer = document.getElementById("output-meta-text");
    metaContainer.textContent = "Sedang mengevaluasi jawaban...";

    try {
        const currentActiveDb = getActiveDatabase();
        const res = await studentFetch("/api/student/submit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                nim: studentNim,
                session_token: studentSessionToken,
                question_id: q.id,
                query: query,
                active_database: currentActiveDb
            })
        });
        const data = await res.json();
        if (!handleExamAccessResponse(res, data)) return;
        if (data.status === "success") {
            const latest = data.latest_attempt || {
                submitted_query: query, graded: data.graded !== false,
                is_correct: data.is_correct ? 1 : 0, score: data.new_score, feedback: data.feedback
            };
            const submission = {
                ...(data.best_submission || submissionsMap[q.id] || {}),
                latest_attempt: latest, score_retained: data.score_retained === true
            };
            submissionsMap[q.id] = submission;
            saveLocalDraft(studentNim, q.id, query);
            updateAutosaveUI("saved");
            const button = document.querySelectorAll(".q-btn")[currentQuestionIndex];
            if (button) {
                button.classList.add("submitted");
                button.classList.toggle("submitted-correct", Boolean(submission.is_correct));
                button.classList.toggle("submitted-wrong", submission.is_correct === 0);
            }
            renderSubmissionState(q, submission);
            const pending = data.graded === false;
            const correct = latest.is_correct === 1 || latest.is_correct === true;
            if (data.columns?.length) {
                renderResultTable(data.columns, data.rows, data.row_count, data.is_truncated, correct ? "correct" : "wrong");
            } else {
                document.getElementById("output-content").textContent = pending
                    ? "Jawaban tersimpan. Menunggu penilaian." : "Jawaban tersimpan.";
            }
            metaContainer.textContent = pending ? "Tersimpan • Menunggu penilaian"
                : `Tersimpan • ${correct ? "Benar" : "Salah"}${data.is_truncated ? ` • ${data.rows.length} dari ${data.row_count} baris ditampilkan` : ""}`;
            showToast(pending ? "Jawaban tersimpan. Menunggu penilaian."
                : `Jawaban tersimpan. Hasil: ${correct ? "benar" : "salah"}.`, correct && !pending ? "success" : "info");
        } else {
            showToast(data.detail || data.message || "Penyimpanan jawaban belum dikonfirmasi server.", "warning");
        }
    } catch (error) {
        metaContainer.textContent = "Status penyimpanan belum terkonfirmasi";
        showToast("Status penyimpanan belum dapat dipastikan. Periksa riwayat setelah koneksi pulih; draf tetap tersimpan.", "warning");
    } finally {
        submitBtn.disabled = !isNetworkOnline || isUserLoggingOut();
        submitBtn.innerHTML = originalText;
    }
}



// ==============================================================================
// 7c. pgAdmin-Style Database Connection Management
// ==============================================================================
let _activeDbCache = "pagila";

function initDatabaseSelector() {
    const dbSelect = document.getElementById("db-connection-select");
    if (!dbSelect) return;

    // Fetch available databases dynamically from backend
    const nimParam = studentNim ? `?nim=${encodeURIComponent(studentNim)}` : "";
    studentFetch(`/api/student/databases${nimParam}`)
        .then(res => res.json())
        .then(data => {
            if (data && data.status === "success" && data.databases) {
                const currentVal = dbSelect.value || data.default || "pagila";
                dbSelect.innerHTML = "";
                data.databases.forEach(db => {
                    const opt = document.createElement("option");
                    opt.value = db.name;
                    if (db.name === 'sandbox_pribadi' && db.virtual_db) {
                        opt.textContent = `sandbox_pribadi (${db.virtual_db})`;
                    } else {
                        opt.textContent = `${db.name} (${db.type === 'sandbox_student' ? 'Easy DDL/DML' : 'Master'})`;
                    }
                    opt.title = db.description || "";
                    if (db.name === currentVal) opt.selected = true;
                    dbSelect.appendChild(opt);
                });
                _activeDbCache = dbSelect.value;
            }
        })
        .catch(err => {
            console.warn("Menggunakan opsi database lokal:", err);
        });

    dbSelect.onchange = (e) => {
        const chosenDb = e.target.value;
        setActiveDatabase(chosenDb, false /* manual switch */);
    };
}

function updateSandboxOptionLabel(virtualDb) {
    const dbSelect = document.getElementById("db-connection-select");
    if (!dbSelect) return;
    const opt = dbSelect.querySelector('option[value="sandbox_pribadi"]');
    if (opt) {
        opt.textContent = virtualDb ? `sandbox_pribadi (${virtualDb})` : `sandbox_pribadi (Easy DDL/DML)`;
    }
}

function getActiveDatabase() {
    const dbSelect = document.getElementById("db-connection-select");
    return (dbSelect ? dbSelect.value : _activeDbCache) || "pagila";
}

function updateDbConnectionStatus(status, dbName) {
    const pill = document.getElementById("db-status-pill");
    const text = document.getElementById("db-status-text");
    if (!pill || !text) return;

    pill.classList.remove("connecting", "error");
    if (status === "connecting") {
        pill.classList.add("connecting");
        text.textContent = "Connecting...";
    } else if (status === "error") {
        pill.classList.add("error");
        text.textContent = "Disconnected";
    } else {
        text.textContent = "Connected";
    }
}

function updateCodeMirrorHints(schema) {
    if (!editor || !schema) return;
    const cmTables = {};
    Object.keys(schema).forEach(tbl => {
        cmTables[tbl] = (schema[tbl] || []).map(col => col.name);
    });
    editor.setOption("hintOptions", { tables: cmTables });
}

async function setActiveDatabase(dbName, isAutoSwitch = false) {
    const dbSelect = document.getElementById("db-connection-select");
    const previousDb = _activeDbCache;
    _activeDbCache = dbName;

    if (dbSelect && dbSelect.value !== dbName) {
        let exists = Array.from(dbSelect.options).some(o => o.value === dbName);
        if (!exists) {
            const opt = document.createElement("option");
            opt.value = dbName;
            opt.textContent = `${dbName} (${dbName === 'sandbox_pribadi' ? 'Easy DDL/DML' : 'Master'})`;
            dbSelect.appendChild(opt);
        }
        dbSelect.value = dbName;
    }

    updateDbConnectionStatus("connecting", dbName);

    updateDbConnectionStatus("connected", dbName);
    if (isAutoSwitch) {
        showToast(`Koneksi database otomatis disesuaikan ke '${dbName}'.`, "info");
    } else if (previousDb !== dbName) {
        showToast(`Koneksi database aktif dialihkan ke '${dbName}'.`, "info");
    }
}

// ==============================================================================
// 7d. Image Lightbox Modal for Question Images & Expected Output (Multi-Image Support)
// ==============================================================================
let currentLightboxList = [];
let currentLightboxIndex = 0;

function openImageLightboxWithList(list, index = 0, title = "Gambar Acuan") {
    if (!list || list.length === 0) return;
    currentLightboxList = list;
    currentLightboxIndex = Math.max(0, Math.min(index, list.length - 1));

    const modal = document.getElementById("image-lightbox-modal");
    const titleEl = document.getElementById("lightbox-title-text");
    if (titleEl) titleEl.textContent = title;

    updateLightboxDisplay();
    if (modal) modal.style.display = "flex";
}

function setLightboxOriginalSize(original) {
    const viewport = document.querySelector(".image-lightbox-body");
    const button = document.getElementById("btn-original-image-size");
    if (viewport) {
        viewport.classList.toggle("is-original", original);
        viewport.scrollTop = 0;
        viewport.scrollLeft = 0;
    }
    if (button) {
        button.textContent = original ? "Sesuaikan layar" : "Ukuran asli";
        button.setAttribute("aria-pressed", String(original));
    }
}

function updateLightboxDisplay() {
    const img = document.getElementById("image-lightbox-img");
    const counter = document.getElementById("lightbox-counter");
    const prevBtn = document.getElementById("lightbox-prev-btn");
    const nextBtn = document.getElementById("lightbox-next-btn");

    if (!currentLightboxList || currentLightboxList.length === 0) return;

    const url = currentLightboxList[currentLightboxIndex];
    if (img) img.src = url;
    setLightboxOriginalSize(false);

    if (counter) {
        counter.textContent = currentLightboxList.length > 1
            ? `${currentLightboxIndex + 1} / ${currentLightboxList.length}`
            : "";
    }

    if (prevBtn) {
        prevBtn.style.display = currentLightboxList.length > 1 ? "flex" : "none";
    }
    if (nextBtn) {
        nextBtn.style.display = currentLightboxList.length > 1 ? "flex" : "none";
    }
}

function lightboxPrev() {
    if (currentLightboxList.length <= 1) return;
    currentLightboxIndex = (currentLightboxIndex - 1 + currentLightboxList.length) % currentLightboxList.length;
    updateLightboxDisplay();
}

function lightboxNext() {
    if (currentLightboxList.length <= 1) return;
    currentLightboxIndex = (currentLightboxIndex + 1) % currentLightboxList.length;
    updateLightboxDisplay();
}

function closeImageLightbox() {
    const modal = document.getElementById("image-lightbox-modal");
    if (modal) modal.style.display = "none";
}

function initImageLightbox() {
    document.getElementById("btn-original-image-size")?.addEventListener("click", () => {
        const viewport = document.querySelector(".image-lightbox-body");
        setLightboxOriginalSize(!viewport?.classList.contains("is-original"));
    });
    const lightboxModal = document.getElementById("image-lightbox-modal");
    const closeBtn = document.getElementById("btn-close-lightbox");
    const overlay = document.getElementById("image-lightbox-overlay");

    if (!lightboxModal) return;

    closeBtn?.addEventListener("click", closeImageLightbox);
    overlay?.addEventListener("click", closeImageLightbox);

    document.addEventListener("keydown", (e) => {
        if (lightboxModal.style.display !== "none") {
            if (e.key === "Escape") {
                closeImageLightbox();
            } else if (e.key === "ArrowLeft") {
                lightboxPrev();
            } else if (e.key === "ArrowRight") {
                lightboxNext();
            }
        }
    });
}

window.openImageLightboxWithList = openImageLightboxWithList;
window.closeImageLightbox = closeImageLightbox;
window.lightboxPrev = lightboxPrev;
window.lightboxNext = lightboxNext;
window.selectQuestion = selectQuestion;
window.getActiveDatabase = getActiveDatabase;

// ==============================================================================
// 10. String & Formatting Utilities
// ==============================================================================
function escapeHtml(str) {
    if (!str && str !== 0) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function formatMarkdown(text) {
    if (!text) return "";
    let safe = escapeHtml(text);
    // Bold: **text**
    safe = safe.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    // Code: `code`
    safe = safe.replace(/`(.*?)`/g, "<code>$1</code>");
    // Line breaks to paragraphs
    return safe.split("\n\n").map(p => `<p>${p.replace(/\n/g, "<br>")}</p>`).join("");
}

window.escapeHtml = escapeHtml;
window.formatMarkdown = formatMarkdown;

})();
