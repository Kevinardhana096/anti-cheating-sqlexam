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

function isUserLoggingOut() {
    return isLoggingOut || Boolean(window.isLoggingOut);
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
    initDatabaseSelector();
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

function renderAutograderBanner(isCorrect, score, maxScore, feedback, scoreRetained = false, retainedScore = 0) {
    const banner = document.getElementById("autograder-banner");
    if (!banner) return;

    if (scoreRetained) {
        banner.className = "autograder-banner banner-correct";
        banner.style.display = "flex";

        banner.innerHTML = `
            <div class="grader-top-row">
                <div class="grader-verdict correct">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                    <span>OUTPUT BELUM SESUAI (SKOR TERBAIK DIPERTAHANKAN)</span>
                </div>
                <div class="grader-score-badge correct">
                    Skor +${retainedScore} Poin Tersimpan
                </div>
            </div>
            <div class="grader-feedback-msg" style="color: #cbd5e1;">
                ${escapeHtml(feedback || "Kueri terbaru Anda belum menghasilkan output yang sesuai acuan.")}
            </div>
            <div class="grader-retry-hint" style="color: #10b981;">
                ℹ️ <strong>Proteksi Nilai Aktif:</strong> Kueri terbaru Anda belum tepat, namun karena Anda sudah pernah menyelesaikan soal ini dengan benar sebelumnya, skor tertinggi Anda (<strong>+${retainedScore} Poin</strong>) tetap aman tercatat dalam sistem ujian.
            </div>
        `;
        return;
    }

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
            const scoreRetained = data.score_retained === true;

            // Cache submission in map & sync local draft (Fase 1)
            submissionsMap[q.id] = {
                submitted_query: query,
                is_correct: isCorrect ? 1 : 0,
                score: score,
                eval_status: data.eval_status,
                feedback: data.feedback,
                score_retained: scoreRetained
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

            // Render auto-grader banner
            renderAutograderBanner(isCorrect, score, maxScore, data.feedback, scoreRetained, score);

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
            if (scoreRetained) {
                showToast(`⚠️ Kueri terbaru belum tepat. Skor terbaik Anda (+${score} Poin) tetap aman!`, "warning");
            } else if (isCorrect) {
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
// 7c. pgAdmin-Style Database Connection Management
// ==============================================================================
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

function updateLightboxDisplay() {
    const img = document.getElementById("image-lightbox-img");
    const counter = document.getElementById("lightbox-counter");
    const prevBtn = document.getElementById("lightbox-prev-btn");
    const nextBtn = document.getElementById("lightbox-next-btn");

    if (!currentLightboxList || currentLightboxList.length === 0) return;

    const url = currentLightboxList[currentLightboxIndex];
    if (img) img.src = url;

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
