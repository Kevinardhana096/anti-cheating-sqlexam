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
 * - Interactive Schema Browser
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

function isUserLoggingOut() {
    return isLoggingOut || Boolean(window.isLoggingOut);
}

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
    initDatabaseSelector();
    initImageLightbox();
    loadErdSchema();
    initSidebarTabs();
    initNetworkMonitor();
    startHeartbeat();

    // Bind Package Selection Modal Buttons
    document.getElementById("btn-cancel-select-pkg")?.addEventListener("click", cancelPackageSelection);
    document.getElementById("btn-proceed-lock-pkg")?.addEventListener("click", confirmPackageSelection);

    // Bind Action Buttons
    document.getElementById("btn-run-query").addEventListener("click", runQuery);
    document.getElementById("btn-submit-answer").addEventListener("click", submitAnswer);
    document.getElementById("btn-format-sql")?.addEventListener("click", formatQuery);
    document.getElementById("btn-open-erd-diagram")?.addEventListener("click", openErdDiagram);
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
    const indicator = document.getElementById("autosave-indicator");
    const textEl = document.getElementById("autosave-text");
    if (!indicator || !textEl) return;

    if (state === "saving") {
        indicator.className = "autosave-indicator is-saving";
        textEl.textContent = "Menyimpan draf...";
        indicator.title = "Sedang menyimpan draf ke penyimpanan lokal browser...";
    } else if (state === "saved") {
        indicator.className = "autosave-indicator is-saved";
        const d = new Date();
        const timeStr = d.toTimeString().split(" ")[0];
        textEl.textContent = `Draf tersimpan (${timeStr})`;
        indicator.title = `Draf kueri otomatis tersimpan di browser ini pada ${timeStr}`;
    } else if (state === "restored") {
        indicator.className = "autosave-indicator is-restored";
        textEl.textContent = "Draf dipulihkan";
        indicator.title = "Kueri berhasil dipulihkan dari draf lokal browser";
    } else if (state === "error") {
        indicator.className = "autosave-indicator is-error";
        textEl.textContent = "Gagal simpan lokal";
        indicator.title = "Penyimpanan lokal browser penuh atau diblokir";
    } else {
        indicator.className = "autosave-indicator";
        textEl.textContent = "Draf tersimpan";
    }
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

async function checkNetworkNow() {
    const badge = document.getElementById("network-status-badge");
    const textEl = document.getElementById("network-status-text");
    if (!isNetworkOnline && textEl) {
        textEl.textContent = "Menghubungkan...";
        if (badge) badge.className = "status-badge badge-warning";
    }

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 4000);
        const res = await fetch("/api/student/heartbeat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                nim: studentNim,
                session_token: studentSessionToken
            }),
            signal: controller.signal
        });
        clearTimeout(timeoutId);

        if (res.ok) {
            const data = await res.json();
            if (data.valid) {
                setNetworkState(true);
                return true;
            }
        }
        setNetworkState(false, "Server ujian tidak merespon.");
        return false;
    } catch (e) {
        setNetworkState(false, "Gagal menghubungi server ujian.");
        return false;
    }
}

window.checkNetworkNow = checkNetworkNow;
window.setNetworkState = setNetworkState;
window.getIsNetworkOnline = () => isNetworkOnline;

// 1. CodeMirror SQL Editor Initialization
// ==============================================================================
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
            "Ctrl-Enter": () => runQuery(),
            "Cmd-Enter": () => runQuery(),
            "Shift-Ctrl-Enter": () => runQuery(true),
            "Shift-Cmd-Enter": () => runQuery(true)
        }
    });
    window.editor = editor;

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

    // Auto-trigger completion on typing words
    editor.on("inputRead", (cm, change) => {
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

    // 3. Track internal copy/cut across the IDE (editor, question descriptions, ERD, result table)
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

    // 4. Detect tab/window switches
    document.addEventListener("visibilitychange", () => {
        if (isUserLoggingOut()) return;
        if (document.hidden) {
            showToast("Peringatan: Berpindah tab atau aplikasi dicatat oleh sistem!", "danger");
            logCheatingAction("blur_tab", "Mahasiswa memindahkan fokus tab atau keluar jendela ujian");
        } else {
            logCheatingAction("focus_tab", "Mahasiswa kembali ke jendela ujian");
        }
    });

    window.addEventListener("blur", () => {
        if (isUserLoggingOut()) return;
        logCheatingAction("blur_tab", "Window blur terdeteksi");
    });

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
        await fetch("/api/student/log-event", {
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
function startHeartbeat() {
    heartbeatInterval = setInterval(async () => {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 6000);
            const res = await fetch("/api/student/heartbeat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    nim: studentNim,
                    session_token: studentSessionToken
                }),
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            const data = await res.json();
            consecutiveHeartbeatFailures = 0;
            if (!isNetworkOnline) {
                setNetworkState(true);
            }

            if (!data.valid) {
                clearInterval(heartbeatInterval);
                showKickModal(data.reason || "NIM Anda sedang diakses dari perangkat lain!");
            } else {
                // Deteksi jika paket soal di-reset oleh pengawas
                if (studentCategory && !data.selected_category) {
                    studentCategory = "";
                    updateHeaderPackageBadge(null);
                    showToast("Pilihan paket soal Anda telah di-reset oleh pengawas. Silakan pilih paket baru.", "warning");
                    loadQuestions();
                }
            }
        } catch (err) {
            consecutiveHeartbeatFailures++;
            console.warn(`[Heartbeat] Probe failed (${consecutiveHeartbeatFailures}/${MAX_HEARTBEAT_FAILS_BEFORE_OFFLINE}):`, err);
            if (consecutiveHeartbeatFailures >= MAX_HEARTBEAT_FAILS_BEFORE_OFFLINE || !navigator.onLine) {
                setNetworkState(false, "Koneksi ke server ujian terputus!");
            }
        }
    }, 12000); // Check every 12 seconds
}

function showKickModal(message) {
    if (editor) {
        editor.setOption("readOnly", "nocursor");
    }
    const modalHtml = `
        <div class="modal-backdrop is-active" id="kick-modal" role="dialog" aria-modal="true" style="display: flex;">
            <div class="modal-dialog">
                <div class="modal-header">
                    <h3 style="color: #ef4444;">Sesi Ditangguhkan (Kicked)</h3>
                </div>
                <div class="modal-body">
                    <div class="alert-box alert-danger">
                        ${escapeHtml(message)}
                    </div>
                    <p style="margin-top: 0.5rem; color: #cbd5e1;">
                        Sistem mendeteksi aktivitas login baru dengan NIM Anda di perangkat lain atau IP yang berbeda. 
                        Untuk menjaga integritas ujian, sesi pada perangkat ini telah dinonaktifkan.
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
async function loadQuestions() {
    try {
        const res = await fetch(`/api/student/questions?token=${encodeURIComponent(studentSessionToken)}`);
        const data = await res.json();

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
        badge.textContent = `Paket ${category}`;
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
        const cat = c.category;
        const name = c.name || `Paket ${cat}`;
        const desc = c.description || "";
        const count = c.total_questions || 0;
        const weight = c.total_weight || 0;

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
        const res = await fetch("/api/student/select-category", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                nim: studentNim,
                session_token: studentSessionToken,
                category: cat
            })
        });
        const data = await res.json();
        if (res.ok && data.status === "success") {
            studentCategory = cat;
            hideCategorySelectionModal();
            updateHeaderPackageBadge(cat);
            questionsData = data.questions || [];
            submissionsMap = {};
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
        btn.title = `Soal No. ${q.question_number}: ${q.title}`;
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
    document.getElementById("q-title").textContent = q.title;
    const weightEl = document.getElementById("q-weight");
    if (weightEl) weightEl.style.display = "none";
    
    // Convert basic markdown/newlines to safe HTML
    document.getElementById("q-description").innerHTML = formatMarkdown(q.description);

    // Update Expected Output Table Screenshot Container (Fase 4)
    const outputBox = document.getElementById("q-expected-output-box");
    const outputImg = document.getElementById("q-expected-output-img");
    if (outputBox && outputImg) {
        const imgUrl = (q.expected_output_image || "").trim();
        if (imgUrl) {
            outputImg.src = imgUrl;
            outputBox.style.display = "block";
        } else {
            outputImg.src = "";
            outputBox.style.display = "none";
        }
    }

    // Populate editor with submitted query, local draft, or clean placeholder (Fase 1)
    const existingSubmission = submissionsMap[q.id];
    const localDraft = getLocalDraft(studentNim, q.id);
    let queryToLoad = "";
    let isFromDraft = false;

    if (existingSubmission && existingSubmission.submitted_query) {
        // If there is an active local draft that differs from submitted query, prefer local draft
        if (localDraft && localDraft.query && localDraft.query.trim() !== existingSubmission.submitted_query.trim()) {
            queryToLoad = localDraft.query;
            isFromDraft = true;
        } else {
            queryToLoad = existingSubmission.submitted_query;
        }
    } else if (localDraft && localDraft.query !== undefined) {
        queryToLoad = localDraft.query;
        isFromDraft = true;
    } else if (q.draftQuery !== undefined) {
        queryToLoad = q.draftQuery;
        isFromDraft = true;
    } else {
        queryToLoad = `-- Jawaban Soal No. ${q.question_number}: ${q.title}\nSELECT \n`;
    }

    editor.setValue(queryToLoad);
    editor.focus();
    editor.setCursor(editor.lineCount(), 0);

    if (isFromDraft && localDraft) {
        updateAutosaveUI("restored");
    } else {
        updateAutosaveUI("saved");
    }

    // Update submission indicator tag & autograder banner
    const subTag = document.getElementById("submission-status-tag");
    const autoBanner = document.getElementById("autograder-banner");
    if (existingSubmission) {
        const isCorrect = existingSubmission.is_correct === 1;
        const score = existingSubmission.score || 0;
        const maxScore = q.score_weight || 20;

        if (isCorrect) {
            if (subTag) {
                subTag.className = "status-badge badge-online";
                subTag.textContent = "🟢 Terjawab";
            }
        } else {
            if (subTag) {
                subTag.className = "status-badge badge-danger";
                subTag.textContent = "🔴 Perlu Perbaikan";
            }
        }

        if (existingSubmission.feedback) {
            renderAutograderBanner(isCorrect, score, maxScore, existingSubmission.feedback);
        } else if (autoBanner) {
            autoBanner.style.display = "none";
        }
    } else {
        if (subTag) {
            subTag.className = "status-badge badge-warning";
            subTag.textContent = "Belum Disubmit";
        }
        if (autoBanner) {
            autoBanner.style.display = "none";
            autoBanner.className = "autograder-banner";
        }
    }
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
        const res = await fetch("/api/student/run-query", {
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
        
        if (data.success) {
            renderResultTable(data.columns, data.rows, data.row_count, data.is_truncated);
            metaContainer.textContent = `${data.row_count} baris dikembalikan (${data.execution_time_ms} ms)${isPartial ? " • Run Partial" : ""}`;
            if (isPartial) {
                showToast(`Partial run berhasil (${data.row_count} baris).`, "info");
            }
            if (data.virtual_db !== undefined) {
                updateSandboxOptionLabel(data.virtual_db);
            }
            // If running DDL/DML or virtual DB on student sandbox, refresh ERD view
            if (currentActiveDb === "sandbox_pribadi") {
                const uq = query.toUpperCase();
                if (uq.includes("CREATE TABLE") || uq.includes("DROP TABLE") || uq.includes("ALTER TABLE") || uq.includes("CREATE DATABASE") || uq.includes("USE ") || uq.includes("DROP DATABASE")) {
                    loadErdSchema("sandbox_pribadi");
                }
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

function renderAutograderBanner(isCorrect, score, maxScore, feedback) {
    const banner = document.getElementById("autograder-banner");
    if (!banner) return;

    banner.className = `autograder-banner ${isCorrect ? "banner-correct" : "banner-wrong"}`;
    banner.style.display = "flex";

    const titleText = isCorrect ? "JAWABAN BENAR!" : "OUTPUT BELUM SESUAI";
    const titleClass = isCorrect ? "correct" : "wrong";
    const scoreBadgeText = isCorrect ? "Tercatat di Sistem" : "Perlu Perbaikan";
    const badgeClass = isCorrect ? "correct" : "wrong";
    const iconSvg = isCorrect
        ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`
        : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`;

    const retryNotice = isCorrect 
        ? `<div class="grader-retry-hint" style="color: #10b981;">Nilai soal ini telah tercatat dalam sistem penilaian ujian.</div>`
        : `<div class="grader-retry-hint">Perbaiki query Anda di editor lalu klik <strong>Submit Answer</strong> kembali untuk mencoba lagi.</div>`;

    banner.innerHTML = `
        <div class="grader-top-row">
            <div class="grader-verdict ${titleClass}">
                ${iconSvg}
                <span>${titleText}</span>
            </div>
            <div class="grader-score-badge ${badgeClass}">
                ${scoreBadgeText}
            </div>
        </div>
        <div class="grader-feedback-msg">
            ${escapeHtml(feedback || (isCorrect ? "Kueri menghasilkan output yang sesuai." : "Hasil output kueri belum cocok."))}
        </div>
        ${retryNotice}
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
    if (!isNetworkOnline) {
        showToast("Koneksi jaringan sedang terputus! Kueri Anda tetap aman di draf lokal. Menghubungkan ulang...", "danger");
        return;
    }
    const q = questionsData[currentQuestionIndex];
    if (!q) return;

    const query = editor.getValue().trim();
    if (!query) {
        showToast("Query jawaban tidak boleh kosong!", "warning");
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
        const res = await fetch("/api/student/submit", {
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
        if (data.status === "success") {
            const isCorrect = data.is_correct === true;
            const score = data.score || 0;
            const maxScore = data.max_score || q.score_weight;

            // Cache submission in map & sync local draft (Fase 1)
            submissionsMap[q.id] = {
                submitted_query: query,
                is_correct: isCorrect ? 1 : 0,
                score: score,
                eval_status: data.eval_status,
                feedback: data.feedback
            };
            saveLocalDraft(studentNim, q.id, query);
            updateAutosaveUI("saved");

            // Update button visual in navigation grid
            const buttons = document.querySelectorAll(".q-btn");
            if (buttons[currentQuestionIndex]) {
                const b = buttons[currentQuestionIndex];
                b.classList.add("submitted");
                if (isCorrect) {
                    b.classList.add("submitted-correct");
                    b.classList.remove("submitted-wrong");
                } else {
                    b.classList.add("submitted-wrong");
                    b.classList.remove("submitted-correct");
                }
            }

            // Update status tag in sidebar
            const subTag = document.getElementById("submission-status-tag");
            if (subTag) {
                if (isCorrect) {
                    subTag.className = "status-badge badge-online";
                    subTag.textContent = `🟢 Benar (+${score} Poin)`;
                } else {
                    subTag.className = "status-badge badge-danger";
                    subTag.textContent = "🔴 Belum Sesuai (0 Poin)";
                }
            }

            if (currentActiveDb === "sandbox_pribadi") {
                loadErdSchema("sandbox_pribadi");
            }
            // Render auto-grader banner
            renderAutograderBanner(isCorrect, score, maxScore, data.feedback);

            // Render table output if columns exist, or error box
            const outputContainer = document.getElementById("output-content");
            if (data.eval_status === "syntax_error" && data.error) {
                outputContainer.innerHTML = `
                    <div class="state-box-error" style="border-left: 4px solid #ef4444; margin: 0.85rem;">
                        <strong style="color: #ef4444;">Error Sintaks SQL:</strong><br>
                        ${escapeHtml(data.error)}
                    </div>
                `;
                metaContainer.textContent = `Query Error Sintaks • Evaluasi Gagal`;
            } else if (data.columns && data.columns.length > 0) {
                renderResultTable(data.columns, data.rows, data.row_count, false, isCorrect ? "correct" : "wrong");
                metaContainer.textContent = `${data.row_count} baris • ${data.execution_time_ms} ms • Status: ${isCorrect ? "BENAR" : "BELUM SESUAI"}`;
            } else {
                outputContainer.innerHTML = `
                    <div class="state-box state-box-empty" style="margin: 0.85rem;">
                        <p>Kueri berhasil dieksekusi tetapi menghasilkan 0 baris kolom data.</p>
                    </div>
                `;
                metaContainer.textContent = `0 baris • Status: ${isCorrect ? "BENAR" : "BELUM SESUAI"}`;
            }

            // Toast feedback
            if (isCorrect) {
                showToast(`🎉 Jawaban Soal No. ${q.question_number} BENAR! (+${score} Poin)`, "success");
            } else {
                showToast(`Jawaban Soal No. ${q.question_number} belum sesuai. Periksa feedback di bawah.`, "danger");
            }
        } else {
            showToast(data.message || "Gagal menyimpan jawaban.", "danger");
            if (data.message && (data.message.includes("belum memilih paket") || data.message.includes("tidak sesuai dengan paket"))) {
                loadQuestions();
            }
        }
    } catch (err) {
        showToast("Gagal mengirim jawaban ke server.", "danger");
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
    }
}

// ==============================================================================
// 7. Schema Browser
// ==============================================================================
// ==============================================================================
// 7b. Sidebar Tab Switcher
// ==============================================================================
function initSidebarTabs() {
    const tabBtns = document.querySelectorAll(".sidebar-tab-btn");
    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            tabBtns.forEach(b => { b.classList.remove("active"); b.setAttribute("aria-selected", "false"); });
            btn.classList.add("active");
            btn.setAttribute("aria-selected", "true");
            const target = btn.dataset.tab;
            document.querySelectorAll(".sidebar-tab-pane").forEach(pane => {
                pane.style.display = (pane.id === `tab-pane-${target}`) ? "flex" : "none";
            });
        });
    });
}

// ==============================================================================
// 7c. ERD Schema & pgAdmin-Style Database Connection Management
// ==============================================================================
let _erdSchemaCache = null;
let _erdRelCache = [];
let _erdShowRel = false;
let _activeDbCache = "pagila";

function initDatabaseSelector() {
    const dbSelect = document.getElementById("db-connection-select");
    if (!dbSelect) return;

    // Fetch available databases dynamically from backend
    const nimParam = studentNim ? `?nim=${encodeURIComponent(studentNim)}` : "";
    fetch(`/api/student/databases${nimParam}`)
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

    dbSelect.addEventListener("change", (e) => {
        const chosenDb = e.target.value;
        setActiveDatabase(chosenDb, false /* manual switch */);
    });
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

    try {
        await loadErdSchema(dbName);
        updateDbConnectionStatus("connected", dbName);
        if (isAutoSwitch) {
            showToast(`Koneksi database otomatis disesuaikan ke '${dbName}'.`, "info");
        } else if (previousDb !== dbName) {
            showToast(`Koneksi database aktif dialihkan ke '${dbName}'.`, "info");
        }
    } catch (_) {
        updateDbConnectionStatus("error", dbName);
        showToast(`Gagal terhubung ke database '${dbName}'.`, "danger");
    }
}

async function loadErdSchema(dbName) {
    const container = document.getElementById("erd-cards-container");
    if (!container) return;

    const targetDb = dbName || getActiveDatabase();
    _activeDbCache = targetDb;

    // Update ERD Header info
    const dbNameLabel = document.getElementById("erd-active-db-name");
    const countBadge = document.getElementById("erd-table-count-badge");
    if (dbNameLabel) dbNameLabel.textContent = targetDb;
    if (countBadge) countBadge.textContent = "Memuat...";

    container.innerHTML = `
        <div style="padding: 1.5rem; text-align: center; color: var(--text-muted); font-size: 0.85rem;">
            <div class="spinner" style="margin: 0 auto 0.5rem auto; width: 22px; height: 22px; border-width: 2px;"></div>
            Memuat skema '${escapeHtml(targetDb)}'...
        </div>
    `;

    try {
        const res = await fetch(`/api/student/schema-full?db=${encodeURIComponent(targetDb)}`, { credentials: "same-origin" });
        if (!res.ok) { renderErdError(container, targetDb); return; }
        const data = await res.json();
        _erdSchemaCache = data.schema || {};
        _erdRelCache = data.relations || [];

        renderErdCards(container, _erdSchemaCache, _erdRelCache, targetDb);
        bindErdSearch();
        bindErdRelToggle();

        const tableCount = Object.keys(_erdSchemaCache).length;
        if (countBadge) countBadge.textContent = `${tableCount} Tabel`;
        if (dbNameLabel) {
            dbNameLabel.textContent = data.virtual_db ? `${targetDb} (${data.virtual_db})` : targetDb;
        }
        if (targetDb === "sandbox_pribadi") {
            updateSandboxOptionLabel(data.virtual_db);
        }

        // Synchronize CodeMirror autocomplete with this database's tables & columns
        updateCodeMirrorHints(_erdSchemaCache);
    } catch (_) {
        renderErdError(container, targetDb);
    }
}

function renderErdError(container, dbName) {
    container.innerHTML = `<div style="padding:1rem;color:var(--danger,#ef4444);font-size:.82rem;">Gagal memuat schema untuk database '${escapeHtml(dbName || '')}'. Pastikan service PostgreSQL aktif.</div>`;
}

function renderErdCards(container, schema, relations, currentDb = "pagila") {
    container.innerHTML = "";

    // Build quick lookup: table -> [incoming FKs], table -> [outgoing FKs]
    const incoming = {}; // to_table -> [{from_table, from_col, to_col}]
    const outgoing = {}; // from_table -> [{to_table, from_col, to_col}]
    const fkCols   = {}; // "table.col" -> true  (marks FK columns)

    relations.forEach(r => {
        if (!incoming[r.to_table])   incoming[r.to_table] = [];
        if (!outgoing[r.from_table]) outgoing[r.from_table] = [];
        incoming[r.to_table].push(r);
        outgoing[r.from_table].push(r);
        fkCols[`${r.from_table}.${r.from_col}`] = true;
    });

    const tableNames = Object.keys(schema).sort();

    if (tableNames.length === 0) {
        if (currentDb === "sandbox_pribadi") {
            container.innerHTML = `
                <div style="padding: 1.5rem 1rem; text-align: center; color: var(--text-muted); font-size: 0.82rem; line-height: 1.5;">
                    <p style="font-weight: 600; color: var(--text-main); margin-bottom: 0.35rem;">📦 Kamar Sandbox Pribadi</p>
                    <p>Belum ada tabel di skema pribadi Anda. Jalankan perintah <code>CREATE DATABASE</code> atau <code>CREATE TABLE</code> pada Soal Easy untuk membuat database dan tabel baru.</p>
                </div>
            `;
        } else {
            container.innerHTML = `
                <div style="padding: 1.5rem 1rem; text-align: center; color: var(--text-muted); font-size: 0.82rem;">
                    Belum ada tabel pada database '${escapeHtml(currentDb)}'.
                </div>
            `;
        }
        return;
    }

    tableNames.forEach(tbl => {
        const cols = schema[tbl];
        const hasRel = !!(incoming[tbl] || outgoing[tbl]);
        const card = document.createElement("div");
        card.className = "erd-table-card" + (hasRel ? " has-rel" : "") + " open";
        card.dataset.table = tbl;

        // ---- Header ----
        const header = document.createElement("div");
        header.className = "erd-table-header";
        header.innerHTML = `
            <span class="erd-table-name" title="${tbl}">${tbl}</span>
            <span class="erd-table-count">${cols.length} col</span>
            <svg class="erd-table-toggle" width="14" height="14"><use href="#si-chevron-down"/></svg>
        `;
        header.addEventListener("click", () => card.classList.toggle("open"));
        card.appendChild(header);

        // ---- Relation tags (outgoing FKs from this table) ----
        if (outgoing[tbl] && outgoing[tbl].length > 0) {
            const relWrap = document.createElement("div");
            relWrap.className = "erd-rel-tags erd-rel-section";
            relWrap.style.display = _erdShowRel ? "flex" : "none";
            outgoing[tbl].forEach(r => {
                const tag = document.createElement("span");
                tag.className = "erd-rel-tag";
                tag.title = `FK: ${r.from_table}.${r.from_col} → ${r.to_table}.${r.to_col}`;
                tag.textContent = `${r.from_col} → ${r.to_table}.${r.to_col}`;
                relWrap.appendChild(tag);
            });
            card.appendChild(relWrap);
        }

        // ---- Incoming relation tags ----
        if (incoming[tbl] && incoming[tbl].length > 0) {
            const relWrap = document.createElement("div");
            relWrap.className = "erd-rel-tags erd-rel-section";
            relWrap.style.cssText = `display:${_erdShowRel ? "flex" : "none"};background:color-mix(in srgb,var(--success,#10b981) 5%,transparent);`;
            incoming[tbl].forEach(r => {
                const tag = document.createElement("span");
                tag.className = "erd-rel-tag";
                tag.style.cssText = "color:var(--success,#10b981);background:color-mix(in srgb,var(--success,#10b981) 12%,transparent);";
                tag.title = `Referenced by: ${r.from_table}.${r.from_col}`;
                tag.textContent = `← ${r.from_table}.${r.from_col}`;
                relWrap.appendChild(tag);
            });
            card.appendChild(relWrap);
        }

        // ---- Column list ----
        const colList = document.createElement("div");
        colList.className = "erd-col-list";

        cols.forEach(col => {
            const isFk = !!fkCols[`${tbl}.${col.name}`];
            const colRow = document.createElement("div");
            colRow.className = "erd-col-row";
            colRow.dataset.colname = col.name.toLowerCase();
            colRow.title = `Klik untuk sisipkan "${col.name}" ke editor`;

            let badges = "";
            if (col.pk)             badges += `<span class="erd-badge erd-badge-pk">PK</span>`;
            if (isFk)               badges += `<span class="erd-badge erd-badge-fk">FK</span>`;
            if (!col.nullable && !col.pk) badges += `<span class="erd-badge erd-badge-nn">NN</span>`;

            colRow.innerHTML = `${badges}<span class="erd-col-name">${escapeHtml(col.name)}</span><span class="erd-col-type">${shortType(col.type)}</span>`;

            colRow.addEventListener("click", () => {
                if (editor) {
                    editor.replaceSelection(col.name);
                    editor.focus();
                }
                // Flash highlight
                colRow.classList.add("erd-highlight");
                setTimeout(() => colRow.classList.remove("erd-highlight"), 700);
            });

            colList.appendChild(colRow);
        });

        card.appendChild(colList);
        container.appendChild(card);
    });

    if (tableNames.length === 0) {
        container.innerHTML = '<div style="padding:1rem;text-align:center;color:var(--text-muted);font-size:.82rem;">Database belum diinisialisasi. Minta admin untuk memuat data classicmodels.</div>';
    }
}

function shortType(pgType) {
    const map = {
        "character varying": "varchar",
        "double precision": "double",
        "integer": "int",
        "smallint": "int2",
        "bigint": "int8",
        "boolean": "bool",
        "timestamp without time zone": "timestamp",
        "timestamp with time zone": "timestamptz",
        "character": "char",
        "numeric": "numeric",
        "text": "text",
    };
    return map[pgType] || pgType;
}

function bindErdSearch() {
    const input = document.getElementById("erd-search");
    if (!input) return;
    input.addEventListener("input", () => {
        const q = input.value.trim().toLowerCase();
        const cards = document.querySelectorAll(".erd-table-card");
        cards.forEach(card => {
            const tbl = (card.dataset.table || "").toLowerCase();
            const colRows = card.querySelectorAll(".erd-col-row");

            if (!q) {
                card.classList.remove("erd-hidden");
                colRows.forEach(r => r.classList.remove("erd-highlight"));
                return;
            }

            // Check table name match
            const tblMatch = tbl.includes(q);
            // Check column name match
            let colMatch = false;
            colRows.forEach(r => {
                const cn = (r.dataset.colname || "");
                if (cn.includes(q)) {
                    r.classList.add("erd-highlight");
                    colMatch = true;
                } else {
                    r.classList.remove("erd-highlight");
                }
            });

            if (tblMatch || colMatch) {
                card.classList.remove("erd-hidden");
                // Auto-open if column matched
                if (colMatch && !tblMatch) card.classList.add("open");
            } else {
                card.classList.add("erd-hidden");
            }
        });
    });
}

function bindErdRelToggle() {
    const btn = document.getElementById("erd-toggle-rel");
    const legend = document.getElementById("erd-rel-legend");
    if (!btn) return;
    btn.addEventListener("click", () => {
        _erdShowRel = !_erdShowRel;
        btn.style.color = _erdShowRel ? "var(--accent)" : "";
        btn.style.borderColor = _erdShowRel ? "var(--accent)" : "";
        if (legend) legend.style.display = _erdShowRel ? "flex" : "none";
        document.querySelectorAll(".erd-rel-section").forEach(el => {
            el.style.display = _erdShowRel ? "flex" : "none";
        });
    });
}

// ==============================================================================
// 8. Utilities
// ==============================================================================
function formatQuery() {
    if (!editor) return;
    const keywords = [
        "select", "from", "where", "group by", "order by", "having", 
        "inner join", "left join", "right join", "join", "on", 
        "as", "count", "sum", "avg", "min", "max", "round", "concat",
        "distinct", "limit", "offset", "and", "or", "in", "like", "between",
        "is null", "is not null", "asc", "desc"
    ];

    function applyFormat(t) {
        keywords.forEach(kw => {
            const reg = new RegExp(`\\b${kw}\\b`, "gi");
            t = t.replace(reg, kw.toUpperCase());
        });
        return t;
    }

    if (editor.somethingSelected()) {
        const sel = editor.getSelection();
        editor.replaceSelection(applyFormat(sel));
        showToast("Format SQL diterapkan pada bagian yang diseleksi.", "info");
    } else {
        editor.setValue(applyFormat(editor.getValue()));
        showToast("Format SQL diterapkan pada seluruh editor.", "info");
    }
}

function showToast(message, type = "success") {
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
        toast.style.opacity = "0";
        setTimeout(() => toast.remove(), 200);
    }, 4000);
}

function escapeHtml(str) {
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function formatMarkdown(text) {
    if (!text) return "";
    let safe = escapeHtml(text);
    safe = safe.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    safe = safe.replace(/`(.*?)`/g, "<code>$1</code>");
    return safe.split("\n\n").map(p => `<p>${p.replace(/\n/g, "<br>")}</p>`).join("");
}

// ==========================================================================// ==============================================================================
// ERD Diagram — Structured Matrix Layout & Visual Relations
// ==============================================================================

const ERD_TBL_W      = 230;
const ERD_COL_H      = 22;
const ERD_HDR_H      = 34;
const ERD_PAD        = 10;
const ERD_PALETTE    = [
    '#6366f1','#059669','#0284c7','#d97706','#8b5cf6',
    '#0d9488','#ec4899','#f97316','#3b82f6','#10b981'
];

let _dc = null;   // canvas
let _dx = null;   // ctx
let _dn = [];     // nodes
let _de = [];     // edges
let _dt = {s:1, px:0, py:0}; // transform
let _dDrag = false;
let _dLast = {x:0, y:0};
let _dSelected = null; // highlighted table name
let _draggedNode = null;
let _dragOffset = {x:0, y:0};
let _downPos = {x:0, y:0};

function _getTableColor(table, index) {
    const domainColors = {
        offices:      '#6366f1', // Indigo - Organization Root
        employees:    '#4f46e5', // Deep Indigo - Staff
        customers:    '#059669', // Emerald - Clients
        payments:     '#0d9488', // Teal - Payments & Billing
        orders:       '#d97706', // Amber - Sales Orders
        orderdetails: '#ea580c', // Orange - Order Line Items
        products:     '#0284c7', // Sky Blue - Product Catalog
        productlines: '#0891b2'  // Cyan - Product Categories
    };
    return domainColors[table] || ERD_PALETTE[index % ERD_PALETTE.length];
}

function openErdDiagram() {
    const modal = document.getElementById('erd-diagram-modal');
    if (!modal) return;
    modal.style.display = 'flex';
    _initDiagram();
}

function closeErdDiagram() {
    const modal = document.getElementById('erd-diagram-modal');
    if (modal) modal.style.display = 'none';
    _dSelected = null;
    _draggedNode = null;
    _dDrag = false;
}

function _initDiagram() {
    const canvas = document.getElementById('erd-diagram-canvas');
    if (!canvas) return;
    const wrap = document.getElementById('erd-canvas-wrapper');
    if (wrap) {
        canvas.width  = wrap.clientWidth  || window.innerWidth  - 40;
        canvas.height = wrap.clientHeight || window.innerHeight - 130;
    }
    _dc = canvas;
    _dx = canvas.getContext('2d');
    _dn = [];
    _dSelected = null;

    const schema = _erdSchemaCache || {};
    const rels   = _erdRelCache   || [];
    _de = rels;

    if (Object.keys(schema).length === 0) {
        loadErdSchema().then(() => _initDiagram());
        return;
    }

    // Build FK lookup dictionary
    const fkCols = {};
    rels.forEach(r => {
        const fromColNorm = (r.from_col || '').toLowerCase().replace(/_/g, '');
        fkCols[`${r.from_table}.${fromColNorm}`] = true;
    });

    const tables = Object.keys(schema).sort();

    tables.forEach((tbl, i) => {
        const cols = schema[tbl] || [];
        const h = ERD_HDR_H + cols.length * ERD_COL_H + ERD_PAD;
        _dn.push({
            table: tbl,
            cols,
            fkCols,
            w: ERD_TBL_W,
            h,
            x: 0,
            y: 0,
            color: _getTableColor(tbl, i)
        });
    });

    _applyStructuredLayout();
    _centerDiagram();
    _drawDiagram();
    _bindDiagramEvents();
}

function _applyStructuredLayout() {
    const schema = _erdSchemaCache || {};
    const rels   = _erdRelCache   || [];
    const tables = Object.keys(schema);
    if (!tables.length) return;

    // Canonical 4x2 matrix layout for classicmodels:
    // Row 0: offices (0,0)  <- employees (1,0)  <- customers (2,0)    <- payments (3,0)
    // Row 1: productlines(0,1) <- products(1,1) <- orderdetails(2,1) -> orders(3,1)
    // Note: orderdetails links products (left) and orders (right). orders links customers (up-left).
    const cmKeys = ['offices', 'employees', 'customers', 'orders', 'orderdetails', 'products', 'productlines', 'payments'];
    const matchCount = cmKeys.filter(t => schema[t]).length;
    const isClassicModels = matchCount >= 4;

    if (isClassicModels) {
        const matrix = {
            offices:      { col: 0, row: 0 },
            employees:    { col: 1, row: 0 },
            customers:    { col: 2, row: 0 },
            payments:     { col: 3, row: 0 },
            productlines: { col: 0, row: 1 },
            products:     { col: 1, row: 1 },
            orderdetails: { col: 2, row: 1 },
            orders:       { col: 3, row: 1 }
        };

        const colWidth = ERD_TBL_W;
        const colGap   = 100;
        const startX   = 50;
        const startY   = 50;

        let maxRow0H = 0;
        _dn.forEach(n => {
            const pos = matrix[n.table];
            if (pos && pos.row === 0) {
                if (n.h > maxRow0H) maxRow0H = n.h;
            }
        });
        const rowGap = 95;
        const row1Y = startY + maxRow0H + rowGap;

        let extraIdx = 0;
        _dn.forEach(n => {
            const pos = matrix[n.table];
            if (pos) {
                n.x = startX + pos.col * (colWidth + colGap);
                n.y = pos.row === 0 ? startY : row1Y;
                n.w = colWidth;
            } else {
                n.x = startX + (extraIdx % 4) * (colWidth + colGap);
                n.y = row1Y + 300 + Math.floor(extraIdx / 4) * 260;
                n.w = colWidth;
                extraIdx++;
            }
        });
    } else {
        _applyHierarchicalLayout(tables, schema, rels);
    }
}

function _applyHierarchicalLayout(tables, schema, rels) {
    const colWidth = ERD_TBL_W;
    const colGap   = 90;
    const rowGap   = 40;
    const startX   = 50;
    const startY   = 50;

    const outEdges = {};
    const inEdges = {};
    tables.forEach(t => { outEdges[t] = []; inEdges[t] = []; });
    rels.forEach(r => {
        if (r.from_table !== r.to_table && outEdges[r.from_table] && inEdges[r.to_table]) {
            outEdges[r.from_table].push(r.to_table);
            inEdges[r.to_table].push(r.from_table);
        }
    });

    const layer = {};
    tables.forEach(t => {
        if (outEdges[t].length === 0) layer[t] = 0;
    });

    if (Object.keys(layer).length === 0) {
        let minOut = Infinity, minT = tables[0];
        tables.forEach(t => {
            if (outEdges[t].length < minOut) { minOut = outEdges[t].length; minT = t; }
        });
        layer[minT] = 0;
    }

    let changed = true;
    let maxIter = 10;
    while (changed && maxIter-- > 0) {
        changed = false;
        tables.forEach(t => {
            const parents = outEdges[t];
            if (parents.length > 0) {
                const pLayers = parents.map(p => layer[p]).filter(l => l !== undefined);
                if (pLayers.length > 0) {
                    const newL = Math.max(...pLayers) + 1;
                    if (layer[t] !== newL) {
                        layer[t] = newL;
                        changed = true;
                    }
                }
            }
        });
    }

    tables.forEach(t => { if (layer[t] === undefined) layer[t] = 0; });

    const columns = {};
    tables.forEach(t => {
        const l = layer[t];
        if (!columns[l]) columns[l] = [];
        columns[l].push(t);
    });

    const nodeMap = {};
    _dn.forEach(n => { nodeMap[n.table] = n; n.w = colWidth; });

    Object.keys(columns).sort((a,b)=>a-b).forEach(l => {
        const colTables = columns[l];
        let currY = startY;
        const colX = startX + parseInt(l) * (colWidth + colGap);
        colTables.forEach(t => {
            const n = nodeMap[t];
            if (n) {
                n.x = colX;
                n.y = currY;
                currY += n.h + rowGap;
            }
        });
    });
}

function _centerDiagram() {
    if (!_dc || _dn.length === 0) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    _dn.forEach(n => {
        minX = Math.min(minX, n.x);
        minY = Math.min(minY, n.y);
        maxX = Math.max(maxX, n.x + n.w);
        maxY = Math.max(maxY, n.y + n.h);
    });
    const gW = maxX - minX || 100;
    const gH = maxY - minY || 100;
    const pad = 65;
    const sx = (_dc.width  - pad * 2) / gW;
    const sy = (_dc.height - pad * 2) / gH;
    _dt.s  = Math.max(0.35, Math.min(sx, sy, 1.05));
    _dt.px = (_dc.width  - gW * _dt.s) / 2 - minX * _dt.s;
    _dt.py = (_dc.height - gH * _dt.s) / 2 - minY * _dt.s;
}

function _drawDiagram() {
    const ctx = _dx, cv = _dc;
    if (!ctx || !cv) return;
    ctx.clearRect(0, 0, cv.width, cv.height);

    // Canvas background
    ctx.fillStyle = _cssVar('--bg-app', '#0f172a');
    ctx.fillRect(0, 0, cv.width, cv.height);

    // Faint grid dots
    ctx.fillStyle = 'rgba(255,255,255,0.05)';
    const gridS = 32;
    for (let gx = gridS/2; gx < cv.width; gx += gridS) {
        for (let gy = gridS/2; gy < cv.height; gy += gridS) {
            ctx.beginPath();
            ctx.arc(gx, gy, 1, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    ctx.save();
    ctx.translate(_dt.px, _dt.py);
    ctx.scale(_dt.s, _dt.s);

    _drawEdges(ctx);
    _dn.forEach(n => _drawNode(ctx, n));

    ctx.restore();
}

function _drawNode(ctx, n) {
    const {x, y, w, h, table, cols, fkCols, color} = n;
    const R = 8;
    const isSelected = (_dSelected === table);

    // Card shadow
    ctx.shadowColor = isSelected ? color : 'rgba(0,0,0,0.55)';
    ctx.shadowBlur  = isSelected ? 22 : 12;
    ctx.shadowOffsetY = 4;

    // Body
    _rRect(ctx, x, y, w, h, R);
    ctx.fillStyle = _cssVar('--bg-surface', '#1e293b');
    ctx.fill();

    // Outline
    ctx.strokeStyle = isSelected ? color : 'rgba(255,255,255,0.08)';
    ctx.lineWidth   = isSelected ? 2.5 : 1;
    _rRect(ctx, x, y, w, h, R);
    ctx.stroke();

    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;
    ctx.shadowOffsetY = 0;

    // Header gradient
    const g = ctx.createLinearGradient(x, y, x + w, y + ERD_HDR_H);
    g.addColorStop(0, color);
    g.addColorStop(1, _lightenHex(color, 24));
    _rRectTop(ctx, x, y, w, ERD_HDR_H, R);
    ctx.fillStyle = g;
    ctx.fill();

    // Header separator line
    ctx.strokeStyle = 'rgba(0,0,0,0.2)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, y + ERD_HDR_H);
    ctx.lineTo(x + w, y + ERD_HDR_H);
    ctx.stroke();

    // Table icon (grid symbol)
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    const iconX = x + 12, iconY = y + ERD_HDR_H/2;
    ctx.fillRect(iconX, iconY - 5, 4, 4);
    ctx.fillRect(iconX + 6, iconY - 5, 4, 4);
    ctx.fillRect(iconX, iconY + 1, 4, 4);
    ctx.fillRect(iconX + 6, iconY + 1, 4, 4);

    // Table name
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 13px "Segoe UI",system-ui,sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(table, x + 26, y + ERD_HDR_H/2);

    // Column count badge on header right
    const countText = `${cols.length} col`;
    ctx.font = '9px "Segoe UI",sans-serif';
    const ctw = ctx.measureText(countText).width;
    const cbx = x + w - ctw - 18;
    ctx.fillStyle = 'rgba(0,0,0,0.28)';
    _rRect(ctx, cbx, y + ERD_HDR_H/2 - 7, ctw + 10, 14, 3);
    ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.textAlign = 'center';
    ctx.fillText(countText, cbx + (ctw + 10)/2, y + ERD_HDR_H/2);

    // Columns
    const mainColor  = '#f1f5f9';
    const mutedColor = '#94a3b8';
    const elevColor  = 'rgba(255,255,255,0.025)';
    const sepColor   = 'rgba(255,255,255,0.05)';

    cols.forEach((col, i) => {
        const rowY  = y + ERD_HDR_H + i * ERD_COL_H;
        const midY  = rowY + ERD_COL_H / 2 + 0.5;
        const isPk  = !!col.pk;
        const normColName = (col.name || '').toLowerCase().replace(/_/g, '');
        const isFk  = !!(fkCols && fkCols[`${table}.${normColName}`]);

        // Zebra tint
        if (i % 2 === 0) {
            ctx.fillStyle = elevColor;
            ctx.fillRect(x + 1, rowY, w - 2, ERD_COL_H);
        }

        // Row border
        if (i < cols.length - 1) {
            ctx.strokeStyle = sepColor;
            ctx.lineWidth = 0.5;
            ctx.beginPath();
            ctx.moveTo(x + 2, rowY + ERD_COL_H);
            ctx.lineTo(x + w - 2, rowY + ERD_COL_H);
            ctx.stroke();
        }

        // Badges
        let bx = x + 7;
        if (isPk) { bx = _drawBadge(ctx, bx, midY, 'PK', '#f59e0b'); }
        if (isFk) { bx = _drawBadge(ctx, bx, midY, 'FK', '#6366f1'); }

        // Column Name
        ctx.fillStyle = isPk ? '#fbbf24' : (isFk ? '#c7d2fe' : mainColor);
        ctx.font = isPk ? 'bold 11px "Segoe UI",system-ui' : '11px "Segoe UI",system-ui';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText(col.name, bx + 2, midY);

        // Column Type
        const typeStr = _shortT(col.type);
        ctx.fillStyle = mutedColor;
        ctx.font = '9.5px "Courier New",monospace';
        ctx.textAlign = 'right';
        ctx.fillText(typeStr, x + w - 8, midY);
    });
}

function _drawBadge(ctx, x, cy, label, color) {
    const pad = 3, fs = 8.5;
    ctx.font = `bold ${fs}px "Segoe UI",system-ui`;
    const tw = ctx.measureText(label).width;
    const bw = tw + pad * 2;
    const bh = 12;
    ctx.fillStyle = color + '28';
    ctx.strokeStyle = color;
    ctx.lineWidth = 0.8;
    _rRectFull(ctx, x, cy - bh/2, bw, bh, 2.5);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = color;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, x + bw/2, cy);
    return x + bw + 4;
}

function _drawEdges(ctx) {
    const nMap = {};
    _dn.forEach(n => nMap[n.table] = n);

    const grp = {};
    _de.forEach(e => {
        const key = `${e.from_table}||${e.to_table}`;
        if (!grp[key]) grp[key] = [];
        grp[key].push(e);
    });

    const allPairs = [];
    Object.values(grp).forEach(edges => {
        edges.forEach((e, idx) => {
            const a = nMap[e.from_table];
            const b = nMap[e.to_table];
            if (!a || !b) return;
            const off = (idx - (edges.length - 1) / 2) * 8;
            const isSelected = _dSelected && (_dSelected === e.from_table || _dSelected === e.to_table);
            allPairs.push({ a, b, edge: e, off, isSelected });
        });
    });

    allPairs.sort((p1, p2) => (p1.isSelected ? 1 : 0) - (p2.isSelected ? 1 : 0));

    allPairs.forEach(p => {
        _drawEdge(ctx, p.a, p.b, p.edge, p.off, p.isSelected);
    });
}

function _drawEdge(ctx, a, b, edge, off, isHighlighted) {
    const isSelf = (a === b);
    const hasSelection = (_dSelected !== null);
    const isDimmed = hasSelection && !isHighlighted;

    const baseColor  = isHighlighted ? '#a5b4fc' : (isDimmed ? 'rgba(148, 163, 184, 0.16)' : 'rgba(99, 102, 241, 0.52)');
    const arrowColor = isHighlighted ? '#818cf8' : (isDimmed ? 'rgba(148, 163, 184, 0.25)' : 'rgba(99, 102, 241, 0.85)');
    const lineWidth  = isHighlighted ? 2.4 : (isDimmed ? 1 : 1.5);

    const fromColNorm = (edge.from_col || '').toLowerCase().replace(/_/g, '');
    const toColNorm   = (edge.to_col   || '').toLowerCase().replace(/_/g, '');

    const fromIdx = a.cols.findIndex(c => (c.name || '').toLowerCase().replace(/_/g, '') === fromColNorm);
    const toIdx   = b.cols.findIndex(c => (c.name || '').toLowerCase().replace(/_/g, '') === toColNorm);

    // 1. Self-referential FK (e.g. employees.reports_to -> employees.employee_number)
    if (isSelf) {
        const sy = a.y + ERD_HDR_H + (fromIdx >= 0 ? fromIdx * ERD_COL_H + ERD_COL_H/2 : a.h * 0.75);
        const ty = a.y + ERD_HDR_H + (toIdx   >= 0 ? toIdx   * ERD_COL_H + ERD_COL_H/2 : a.h * 0.25);
        const sx = a.x;
        const tx = a.x;
        const loopOut = 42;

        ctx.strokeStyle = baseColor;
        ctx.lineWidth   = lineWidth;
        ctx.beginPath();
        ctx.moveTo(sx, sy);
        ctx.bezierCurveTo(sx - loopOut, sy + 8, tx - loopOut, ty - 8, tx, ty);
        ctx.stroke();

        ctx.fillStyle = arrowColor;
        ctx.beginPath();
        ctx.moveTo(tx, ty);
        ctx.lineTo(tx - 7, ty - 4);
        ctx.lineTo(tx - 7, ty + 4);
        ctx.closePath();
        ctx.fill();

        ctx.beginPath();
        ctx.arc(sx, sy, isHighlighted ? 4 : 3, 0, Math.PI * 2);
        ctx.fill();

        if (isHighlighted) {
            _drawBadgeOnLine(ctx, sx - loopOut + 4, (sy + ty)/2, `${edge.from_col} → ${edge.to_col}`);
        }
        return;
    }

    // 2. Inter-table FK
    const ay = a.y + ERD_HDR_H + (fromIdx >= 0 ? fromIdx * ERD_COL_H + ERD_COL_H/2 : a.h / 2) + off;
    const by = b.y + ERD_HDR_H + (toIdx   >= 0 ? toIdx   * ERD_COL_H + ERD_COL_H/2 : b.h / 2) + off;

    let ax, bx, cpx1, cpx2, cpy1, cpy2;
    let targetDir = 1;

    if (a.x >= b.x + b.w - 10) {
        // Source A is to the right of Target B (leaves A left, enters B right)
        ax = a.x;
        bx = b.x + b.w;
        const dx = ax - bx;
        const cp = Math.max(35, Math.min(dx * 0.5, 90));
        cpx1 = ax - cp;
        cpx2 = bx + cp;
        cpy1 = ay;
        cpy2 = by;
        targetDir = -1;
    } else if (a.x + a.w <= b.x + 10) {
        // Source A is to the left of Target B (leaves A right, enters B left)
        ax = a.x + a.w;
        bx = b.x;
        const dx = bx - ax;
        const cp = Math.max(35, Math.min(dx * 0.5, 90));
        cpx1 = ax + cp;
        cpx2 = bx - cp;
        cpy1 = ay;
        cpy2 = by;
        targetDir = 1;
    } else {
        // Vertically overlapping X coordinates
        ax = a.x + a.w;
        bx = b.x + b.w;
        cpx1 = ax + 45;
        cpx2 = bx + 45;
        cpy1 = ay;
        cpy2 = by;
        targetDir = -1;
    }

    ctx.strokeStyle = baseColor;
    ctx.lineWidth   = lineWidth;
    ctx.beginPath();
    ctx.moveTo(ax, ay);
    ctx.bezierCurveTo(cpx1, cpy1, cpx2, cpy2, bx, by);
    ctx.stroke();

    // Arrowhead at target PK
    const AS = 7;
    ctx.fillStyle = arrowColor;
    ctx.beginPath();
    ctx.moveTo(bx, by);
    ctx.lineTo(bx - targetDir * AS, by - 4);
    ctx.lineTo(bx - targetDir * AS, by + 4);
    ctx.closePath();
    ctx.fill();

    // Source dot at FK
    ctx.beginPath();
    ctx.arc(ax, ay, isHighlighted ? 4 : 3, 0, Math.PI * 2);
    ctx.fill();

    if (isHighlighted) {
        const mx = 0.125 * ax + 0.375 * cpx1 + 0.375 * cpx2 + 0.125 * bx;
        const my = 0.125 * ay + 0.375 * cpy1 + 0.375 * cpy2 + 0.125 * by;
        _drawBadgeOnLine(ctx, mx, my, `${edge.from_col} → ${edge.to_col}`);
    }
}

function _drawBadgeOnLine(ctx, cx, cy, text) {
    ctx.save();
    ctx.font = 'bold 9.5px "Segoe UI",system-ui,sans-serif';
    const tw = ctx.measureText(text).width;
    const bw = tw + 14;
    const bh = 17;
    ctx.fillStyle = 'rgba(15, 23, 42, 0.92)';
    ctx.strokeStyle = '#818cf8';
    ctx.lineWidth = 1;
    _rRect(ctx, cx - bw/2, cy - bh/2, bw, bh, 4);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = '#e0e7ff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, cx, cy);
    ctx.restore();
}

function _bindDiagramEvents() {
    const cv = _dc;
    if (!cv || cv._erdBound) return;
    cv._erdBound = true;

    function getCanvasCoords(e) {
        const rect = cv.getBoundingClientRect();
        return {
            cx: e.clientX - rect.left,
            cy: e.clientY - rect.top,
            wx: (e.clientX - rect.left - _dt.px) / _dt.s,
            wy: (e.clientY - rect.top  - _dt.py) / _dt.s
        };
    }

    cv.addEventListener('mousedown', e => {
        const { cx, cy, wx, wy } = getCanvasCoords(e);
        _downPos = { x: cx, y: cy };

        let hit = null;
        for (let i = _dn.length - 1; i >= 0; i--) {
            const n = _dn[i];
            if (wx >= n.x && wx <= n.x + n.w && wy >= n.y && wy <= n.y + n.h) {
                hit = n;
                break;
            }
        }

        if (hit) {
            _draggedNode = hit;
            _dragOffset = { x: wx - hit.x, y: wy - hit.y };
            cv.style.cursor = 'grabbing';
        } else {
            _dDrag = true;
            _dLast = { x: e.clientX, y: e.clientY };
            cv.style.cursor = 'grabbing';
        }
    });

    window.addEventListener('mousemove', e => {
        if (_draggedNode) {
            const { wx, wy } = getCanvasCoords(e);
            _draggedNode.x = Math.round(wx - _dragOffset.x);
            _draggedNode.y = Math.round(wy - _dragOffset.y);
            _drawDiagram();
            return;
        }

        if (_dDrag) {
            _dt.px += e.clientX - _dLast.x;
            _dt.py += e.clientY - _dLast.y;
            _dLast = { x: e.clientX, y: e.clientY };
            _drawDiagram();
            return;
        }

        const { wx, wy } = getCanvasCoords(e);
        let hoverNode = null;
        for (let i = _dn.length - 1; i >= 0; i--) {
            const n = _dn[i];
            if (wx >= n.x && wx <= n.x + n.w && wy >= n.y && wy <= n.y + n.h) {
                hoverNode = n;
                break;
            }
        }
        cv.style.cursor = hoverNode ? 'grab' : 'default';
    });

    window.addEventListener('mouseup', () => {
        if (_draggedNode) {
            _draggedNode = null;
            if (cv) cv.style.cursor = 'grab';
        }
        if (_dDrag) {
            _dDrag = false;
            if (cv) cv.style.cursor = 'default';
        }
    });

    cv.addEventListener('click', e => {
        const { cx, cy, wx, wy } = getCanvasCoords(e);
        const dist = Math.hypot(cx - _downPos.x, cy - _downPos.y);
        if (dist > 4) return; // Ignore drag release

        let hit = null;
        for (let i = _dn.length - 1; i >= 0; i--) {
            const n = _dn[i];
            if (wx >= n.x && wx <= n.x + n.w && wy >= n.y && wy <= n.y + n.h) {
                hit = n.table;
                break;
            }
        }
        _dSelected = (_dSelected === hit) ? null : hit;
        _drawDiagram();
    });

    cv.addEventListener('wheel', e => {
        e.preventDefault();
        const factor = e.deltaY > 0 ? 0.9 : 1.1;
        const rect = cv.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        _dt.px = mx - factor * (mx - _dt.px);
        _dt.py = my - factor * (my - _dt.py);
        _dt.s *= factor;
        _dt.s = Math.max(0.3, Math.min(_dt.s, 2.5));
        _drawDiagram();
    }, { passive: false });
}

function erdZoomIn()      { _dt.s = Math.min(_dt.s * 1.2, 2.5); _drawDiagram(); }
function erdZoomOut()     { _dt.s = Math.max(_dt.s / 1.2, 0.3); _drawDiagram(); }
function erdResetView()   { _centerDiagram(); _drawDiagram(); }
function erdResetLayout() { _applyStructuredLayout(); _centerDiagram(); _dSelected = null; _drawDiagram(); }

// ---- Canvas helpers ----
function _rRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x+r, y);
    ctx.lineTo(x+w-r, y);
    ctx.quadraticCurveTo(x+w, y, x+w, y+r);
    ctx.lineTo(x+w, y+h-r);
    ctx.quadraticCurveTo(x+w, y+h, x+w-r, y+h);
    ctx.lineTo(x+r, y+h);
    ctx.quadraticCurveTo(x, y+h, x, y+h-r);
    ctx.lineTo(x, y+r);
    ctx.quadraticCurveTo(x, y, x+r, y);
    ctx.closePath();
}

function _rRectTop(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x+r, y);
    ctx.lineTo(x+w-r, y);
    ctx.quadraticCurveTo(x+w, y, x+w, y+r);
    ctx.lineTo(x+w, y+h);
    ctx.lineTo(x, y+h);
    ctx.lineTo(x, y+r);
    ctx.quadraticCurveTo(x, y, x+r, y);
    ctx.closePath();
}

function _rRectFull(ctx, x, y, w, h, r) { _rRect(ctx, x, y, w, h, r); }

function _cssVar(name, fallback) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function _lightenHex(hex, amt) {
    const n = parseInt(hex.slice(1), 16);
    const r = Math.min(255, (n >> 16) + amt);
    const g = Math.min(255, ((n >> 8) & 0xff) + amt);
    const b = Math.min(255, (n & 0xff) + amt);
    return '#' + (((r << 16) | (g << 8) | b).toString(16).padStart(6, '0'));
}

function _shortT(t) {
    const m = {
        'character varying':'varchar',
        'double precision':'double',
        'integer':'int',
        'smallint':'int2',
        'bigint':'int8',
        'boolean':'bool',
        'timestamp without time zone':'timestamp',
        'timestamp with time zone':'timestamptz',
        'character':'char',
        'numeric':'numeric'
    };
    return m[t] || (t && t.length > 9 ? t.slice(0, 9) + '..' : t);
}

    // Expose only non-sensitive visualizer utilities to global window for inline modal/diagram buttons
    window.openErdDiagram = openErdDiagram;
    window.closeErdDiagram = closeErdDiagram;
    window.erdZoomIn = erdZoomIn;
    window.erdZoomOut = erdZoomOut;
    window.erdResetView = erdResetView;
    window.erdResetLayout = erdResetLayout;
})();

// ==============================================================================
// 7d. Image Lightbox Modal for Expected Output Table (Fase 4)
// ==============================================================================
function initImageLightbox() {
    const previewWrap = document.getElementById("q-expected-output-preview-wrap");
    const hintBtn = document.getElementById("btn-zoom-hint");
    const lightboxModal = document.getElementById("image-lightbox-modal");
    const lightboxImg = document.getElementById("image-lightbox-img");
    const closeBtn = document.getElementById("btn-close-lightbox");
    const overlay = document.getElementById("image-lightbox-overlay");

    if (!lightboxModal || !lightboxImg) return;

    function openLightbox() {
        const src = document.getElementById("q-expected-output-img")?.src;
        if (src && !src.endsWith("/") && src !== window.location.href) {
            lightboxImg.src = src;
            lightboxModal.style.display = "flex";
        }
    }

    function closeLightbox() {
        lightboxModal.style.display = "none";
    }

    previewWrap?.addEventListener("click", openLightbox);
    hintBtn?.addEventListener("click", openLightbox);
    closeBtn?.addEventListener("click", closeLightbox);
    overlay?.addEventListener("click", closeLightbox);

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && lightboxModal.style.display !== "none") {
            closeLightbox();
        }
    });
}

window.checkNetworkNow = checkNetworkNow;
window.setNetworkState = setNetworkState;
window.getIsNetworkOnline = () => isNetworkOnline;

window.selectQuestion = selectQuestion;
window.getActiveDatabase = getActiveDatabase;
