/**

 * Offline SQL Exam System - Admin Dashboard Controller

 * Features:

 * - Real-Time Student Activity Monitoring & Tab Switch Alerting

 * - Question Management (CRUD Modal)

 * - Database Sandbox Reset & Custom SQL Import

 * - Submissions Export (CSV & ZIP of .sql files)

 * - Live Event Logs Tracking

 */



let activeTab = "monitoring";

let questionsList = [];

let packagesList = [];

let availableCategories = [];

let monitorInterval = null;



// ==============================================================================

// Global Theme System

// ==============================================================================

const THEME_STORAGE_KEY = "exam_global_theme";



function initGlobalTheme() {

    const select = document.getElementById("global-theme-select");

    const savedTheme = localStorage.getItem(THEME_STORAGE_KEY) || "dracula";

    applyGlobalTheme(savedTheme);



    if (select) {

        select.addEventListener("change", () => {

            applyGlobalTheme(select.value);

            localStorage.setItem(THEME_STORAGE_KEY, select.value);

        });

    }

}



function applyGlobalTheme(theme) {

    document.documentElement.setAttribute("data-theme", theme);

    const select = document.getElementById("global-theme-select");

    if (select) select.value = theme;

}





document.addEventListener("DOMContentLoaded", () => {

    initGlobalTheme();

    initAdminTabs();

    loadDashboardData();

    loadQuestionsData();

    loadSchemaPreview();

    loadLogsData();



    // Start auto refresh for student monitoring every 10 seconds

    monitorInterval = setInterval(() => {

        if (activeTab === "monitoring") {

            loadDashboardData();

        }

    }, 10000);



    // Initial load and WebSocket for Real-Time Waiting Room & Chat

    initAdminChat();

    initAdminWebSocket();

    loadWaitingRoomPanel();

    loadWaitingRoomChat();

    // Gentle fallback polling every 20 seconds

    setInterval(loadWaitingRoomPanel, 20000);



    // Event Bindings

    document.getElementById("btn-refresh-monitor")?.addEventListener("click", loadDashboardData);

    document.getElementById("btn-exam-start")?.addEventListener("click", startExam);

    document.getElementById("btn-exam-stop")?.addEventListener("click", stopExam);

    document.getElementById("btn-stop-all-sessions")?.addEventListener("click", confirmStopAllSessions);

    document.getElementById("btn-clear-sessions")?.addEventListener("click", openClearSessionsModal);

    document.getElementById("btn-confirm-clear-sessions")?.addEventListener("click", executeClearSessions);

    document.getElementById("btn-add-question")?.addEventListener("click", openAddQuestionModal);

    document.getElementById("btn-add-package")?.addEventListener("click", openAddPackageModal);

    document.getElementById("filter-question-category")?.addEventListener("change", () => {

        renderQuestionsTable();

        renderPackageCards();

    });

    document.getElementById("modal-q-category")?.addEventListener("change", updateNextQuestionNumber);

    document.getElementById("btn-delete-all-questions")?.addEventListener("click", openDeleteAllQuestionsModal);

    document.getElementById("btn-confirm-delete-all-questions")?.addEventListener("click", deleteAllQuestions);

    document.getElementById("delete-all-confirm-input")?.addEventListener("input", (e) => {

        const confirmBtn = document.getElementById("btn-confirm-delete-all-questions");

        if (confirmBtn) confirmBtn.disabled = e.target.value.trim() !== "HAPUS SEMUA";

    });

    document.getElementById("btn-reset-db")?.addEventListener("click", confirmResetDatabase);

    document.getElementById("admin-db-selector")?.addEventListener("change", (e) => {

        loadSchemaPreview(e.target.value);

    });

    document.getElementById("btn-refresh-logs")?.addEventListener("click", loadLogsData);

    document.getElementById("btn-clear-logs")?.addEventListener("click", confirmClearLogs);

    document.getElementById("btn-export-csv")?.addEventListener("click", () => {

        window.location.href = "/api/admin/export/csv";

    });

    document.getElementById("btn-export-zip")?.addEventListener("click", () => {

        window.location.href = "/api/admin/export/zip";

    });



    // Export Rekap Log Aktivitas

    const downloadLogs = () => {

        window.location.href = "/api/admin/export/logs-csv";

    };

    document.getElementById("btn-download-logs-tab4")?.addEventListener("click", downloadLogs);

    document.getElementById("btn-export-logs-csv")?.addEventListener("click", downloadLogs);



    // Export Rekap Perpindahan Tab

    const downloadTabSwitches = () => {

        window.location.href = "/api/admin/export/tab-switches-csv";

    };

    document.getElementById("btn-download-tab-switches-tab4")?.addEventListener("click", downloadTabSwitches);

    document.getElementById("btn-export-tab-switches-csv")?.addEventListener("click", downloadTabSwitches);



    // Custom SQL Upload Form

    document.getElementById("sql-upload-form")?.addEventListener("submit", handleSqlUpload);



    // Change Master Password Modal & Form

    document.getElementById("btn-open-change-pw-modal")?.addEventListener("click", openChangePasswordModal);

    document.getElementById("form-change-password")?.addEventListener("submit", handleChangePassword);

});



// ==============================================================================

// Exam Control & Waiting Room Panel (WebSocket & Real-Time)

// ==============================================================================



let adminWs = null;

let adminWsReconnectTimer = null;



function initAdminWebSocket() {

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";

    const wsUrl = `${proto}//${window.location.host}/ws/admin`;



    try {

        adminWs = new WebSocket(wsUrl);

    } catch (_) {

        return;

    }



    adminWs.onopen = function () {

        clearTimeout(adminWsReconnectTimer);

    };



    adminWs.onmessage = function (event) {

        try {

            const data = JSON.parse(event.data);

            if (data.event === "INIT_STATE") {

                updateExamStateBadge(data.exam_state || "waiting");

                updateWaitingParticipantsList(data.participants || []);

                if (data.messages && data.messages.length > 0) {

                    appendAdminChatMessages(data.messages);

                }

            } else if (data.event === "NEW_MESSAGE") {

                if (data.message) {

                    appendAdminChatMessages([data.message]);

                }

            } else if (data.event === "PARTICIPANTS_UPDATE") {

                updateWaitingParticipantsList(data.participants || []);

            } else if (data.event === "EXAM_STARTED") {

                updateExamStateBadge("active");

            } else if (data.event === "EXAM_STOPPED") {

                updateExamStateBadge("waiting");

            } else if (data.event === "CLEAR_MESSAGES") {

                const chatContainer = document.getElementById("admin-chat-messages");

                if (chatContainer) {

                    chatContainer.innerHTML = '<div class="admin-chat-empty" id="admin-chat-empty">Belum ada obrolan di waiting room...</div>';

                }

                const countBadge = document.getElementById("admin-chat-count-badge");

                if (countBadge) countBadge.textContent = "0 pesan";

            }

        } catch (_) {}

    };



    adminWs.onclose = function () {

        adminWsReconnectTimer = setTimeout(initAdminWebSocket, 3000);

    };



    adminWs.onerror = function () {

        try { adminWs.close(); } catch (_) {}

    };

}



function updateWaitingParticipantsList(participants) {

    const countEl = document.getElementById("admin-waiting-count");

    const namesEl = document.getElementById("admin-waiting-names");



    if (countEl) countEl.textContent = participants.length;



    if (namesEl) {

        namesEl.innerHTML = "";

        participants.slice(0, 20).forEach(p => {

            const pill = document.createElement("span");

            pill.style.cssText = "background:var(--bg-surface-elevated);border:1px solid var(--border-subtle);border-radius:999px;padding:0.15rem 0.55rem;font-size:0.72rem;color:var(--text-main);";

            pill.textContent = p.name;

            namesEl.appendChild(pill);

        });

        if (participants.length > 20) {

            const more = document.createElement("span");

            more.style.cssText = "font-size:0.72rem;color:var(--text-muted);";

            more.textContent = `+${participants.length - 20} lainnya`;

            namesEl.appendChild(more);

        }

    }

}



async function loadWaitingRoomPanel() {

    try {

        const res = await fetch("/api/admin/waiting/participants");

        if (!res.ok) return;

        const data = await res.json();

        const participants = data.participants || [];

        const examState = data.exam_state || "waiting";



        updateWaitingParticipantsList(participants);

        updateExamStateBadge(examState);

    } catch (_) {}

}



function updateExamStateBadge(state) {

    const badge = document.getElementById("admin-exam-state-badge");

    const startBtn = document.getElementById("btn-exam-start");

    const stopBtn = document.getElementById("btn-exam-stop");



    if (state === "active") {

        if (badge) {

            badge.textContent = "Aktif";

            badge.className = "status-badge badge-online";

        }

        if (startBtn) startBtn.disabled = true;

        if (stopBtn) stopBtn.disabled = false;

    } else {

        if (badge) {

            badge.textContent = "Menunggu";

            badge.className = "status-badge badge-warning";

        }

        if (startBtn) startBtn.disabled = false;

        if (stopBtn) stopBtn.disabled = true;

    }

}



async function startExam() {

    const startBtn = document.getElementById("btn-exam-start");

    if (startBtn) startBtn.disabled = true;

    try {

        const res = await fetch("/api/admin/exam/start", { method: "POST" });

        const data = await res.json();

        showToast(data.message || "Ujian dimulai.", "success");

        updateExamStateBadge("active");

        loadWaitingRoomPanel();

        adminLastMsgId = 0;

        const chatContainer = document.getElementById("admin-chat-messages");

        if (chatContainer) {

            chatContainer.innerHTML = '<div class="admin-chat-empty" id="admin-chat-empty">Belum ada obrolan di waiting room...</div>';

        }

        const countBadge = document.getElementById("admin-chat-count-badge");

        if (countBadge) countBadge.textContent = "0 pesan";

    } catch (_) {

        showToast("Gagal memulai ujian.", "danger");

        if (startBtn) startBtn.disabled = false;

    }

}



async function stopExam() {

    if (!confirm("Hentikan ujian? Peserta yang sedang mengerjakan akan dikembalikan ke waiting room.")) return;

    const stopBtn = document.getElementById("btn-exam-stop");

    if (stopBtn) stopBtn.disabled = true;

    try {

        const res = await fetch("/api/admin/exam/stop", { method: "POST" });

        const data = await res.json();

        showToast(data.message || "Ujian dihentikan.", "success");

        updateExamStateBadge("waiting");

        loadWaitingRoomPanel();

    } catch (_) {

        showToast("Gagal menghentikan ujian.", "danger");

        if (stopBtn) stopBtn.disabled = false;

    }

}



// ==============================================================================

// Live Chat Waiting Room (YouTube Live Stream style)

// ==============================================================================

let adminLastMsgId = 0;

const MAX_ADMIN_CHAT_MESSAGES = 50;



async function loadWaitingRoomChat() {

    try {

        const res = await fetch(`/api/admin/waiting/messages?since_id=${adminLastMsgId}`);

        if (!res.ok) return;

        const data = await res.json();

        const messages = data.messages || [];

        if (messages.length > 0) {

            appendAdminChatMessages(messages);

            adminLastMsgId = messages[messages.length - 1].id;

        }

    } catch (_) {}

}



function appendAdminChatMessages(messages) {

    const chatContainer = document.getElementById("admin-chat-messages");

    const countBadge = document.getElementById("admin-chat-count-badge");

    const scrollBottomBtn = document.getElementById("admin-chat-scroll-bottom");

    if (!chatContainer) return;



    const emptyPlaceholder = document.getElementById("admin-chat-empty");

    if (emptyPlaceholder) {

        emptyPlaceholder.remove();

    }



    const wasAtBottom = chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight <= 45;



    messages.forEach(msg => {

        if (chatContainer.querySelector(`[data-id="${msg.id}"]`)) return;



        const item = document.createElement("div");

        const isAdmin = msg.nim === "ADMIN";

        item.className = "admin-chat-msg" + (isAdmin ? " is-admin" : "");

        item.dataset.id = msg.id;



        const timeStr = formatChatTime(msg.sent_at);

        const escapedName = escapeHtml(msg.name || "Peserta");

        const escapedMsg = escapeHtml(msg.message || "");

        const badgeHtml = isAdmin 

            ? `<span class="admin-chat-badge-proctor">Pengawas</span>`

            : `<span class="admin-chat-badge-nim">(${escapeHtml(msg.nim || "")})</span>`;



        item.innerHTML = `

            <div class="admin-chat-msg-header">

                <span class="admin-chat-msg-time">${timeStr}</span>

                <span class="admin-chat-msg-sender">${escapedName}</span>

                ${badgeHtml}

            </div>

            <div class="admin-chat-msg-text">${escapedMsg}</div>

        `;



        chatContainer.appendChild(item);

    });



    // Enforce max messages limit (like YouTube Live Chat buffer)

    while (chatContainer.children.length > MAX_ADMIN_CHAT_MESSAGES) {

        chatContainer.firstElementChild.remove();

    }



    // Update count badge

    if (countBadge) {

        countBadge.textContent = `${chatContainer.children.length} pesan`;

    }



    // Auto-scroll or show "new messages" button

    if (wasAtBottom) {

        chatContainer.scrollTop = chatContainer.scrollHeight;

        if (scrollBottomBtn) scrollBottomBtn.style.display = "none";

    } else {

        if (scrollBottomBtn) scrollBottomBtn.style.display = "block";

    }

}



function formatChatTime(iso) {

    if (!iso) return "";

    try {

        const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");

        return d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });

    } catch (_) {

        return "";

    }

}



function initAdminChat() {

    const chatContainer = document.getElementById("admin-chat-messages");

    const scrollBottomBtn = document.getElementById("admin-chat-scroll-bottom");

    const form = document.getElementById("admin-chat-form");

    const input = document.getElementById("admin-chat-input");

    const sendBtn = document.getElementById("btn-admin-chat-send");

    const clearBtn = document.getElementById("btn-admin-clear-chat");



    if (chatContainer && scrollBottomBtn) {

        chatContainer.addEventListener("scroll", () => {

            const isAtBottom = chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight <= 35;

            if (isAtBottom) {

                scrollBottomBtn.style.display = "none";

            }

        });



        scrollBottomBtn.addEventListener("click", () => {

            chatContainer.scrollTop = chatContainer.scrollHeight;

            scrollBottomBtn.style.display = "none";

        });

    }



    if (form && input && sendBtn) {

        form.addEventListener("submit", async (e) => {

            e.preventDefault();

            const text = input.value.trim();

            if (!text || input.disabled) return;



            input.disabled = true;

            sendBtn.disabled = true;

            try {

                let sentViaWs = false;

                if (adminWs && adminWs.readyState === WebSocket.OPEN) {

                    try {

                        adminWs.send(JSON.stringify({ type: "CHAT", message: text }));

                        sentViaWs = true;

                    } catch (_) {}

                }



                if (!sentViaWs) {

                    const res = await fetch("/api/admin/waiting/messages", {

                        method: "POST",

                        headers: { "Content-Type": "application/json" },

                        body: JSON.stringify({ message: text })

                    });

                    if (!res.ok) {

                        showToast("Gagal mengirim pesan chat.", "danger");

                    }

                }

                input.value = "";

            } catch (_) {

                showToast("Gagal mengirim pesan chat.", "danger");

            } finally {

                input.disabled = false;

                sendBtn.disabled = false;

                input.focus();

            }

        });

    }



    if (clearBtn) {

        clearBtn.addEventListener("click", async () => {

            if (!confirm("Bersihkan seluruh pesan chat di waiting room?")) return;

            try {

                const res = await fetch("/api/admin/waiting/clear-messages", { method: "POST" });

                if (res.ok) {

                    showToast("Chat waiting room telah dibersihkan.", "success");

                    adminLastMsgId = 0;

                    if (chatContainer) {

                        chatContainer.innerHTML = '<div class="admin-chat-empty" id="admin-chat-empty">Belum ada obrolan di waiting room...</div>';

                    }

                    const countBadge = document.getElementById("admin-chat-count-badge");

                    if (countBadge) countBadge.textContent = "0 pesan";

                    if (scrollBottomBtn) scrollBottomBtn.style.display = "none";

                } else {

                    showToast("Gagal membersihkan chat.", "danger");

                }

            } catch (_) {

                showToast("Gagal membersihkan chat.", "danger");

            }

        });

    }

}



// ==============================================================================

// 1. Navigation Tabs

// ==============================================================================

function initAdminTabs() {

    const tabButtons = document.querySelectorAll(".admin-tab-btn");

    tabButtons.forEach(btn => {

        btn.addEventListener("click", () => {

            tabButtons.forEach(b => b.classList.remove("active"));

            btn.classList.add("active");

            activeTab = btn.dataset.tab;



            document.querySelectorAll(".tab-pane").forEach(pane => {

                pane.style.display = pane.id === `tab-${activeTab}` ? "block" : "none";

            });



            if (activeTab === "monitoring") loadDashboardData();

            if (activeTab === "questions") loadQuestionsData();

            if (activeTab === "database") loadSchemaPreview();

            if (activeTab === "logs") loadLogsData();

        });

    });

}



// ==============================================================================

// 2. Live Student Monitoring

// ==============================================================================

async function loadDashboardData() {

    try {

        const res = await fetch("/api/admin/students");

        const data = await res.json();

        const students = data.students || [];



        // Update Stat Cards

        const total = students.length;

        const online = students.filter(s => s.is_active).length;

        const totalSubmissions = students.reduce((acc, s) => acc + (s.total_submitted || 0), 0);

        const suspiciousCount = students.filter(s => s.tab_switches > 0).length;



        document.getElementById("stat-total-students").textContent = total;

        document.getElementById("stat-online-students").textContent = online;

        document.getElementById("stat-total-submissions").textContent = totalSubmissions;

        document.getElementById("stat-suspicious-count").textContent = suspiciousCount;



        // Render Table Rows

        const tbody = document.getElementById("student-table-body");

        if (!tbody) return;



        if (students.length === 0) {

            tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 2rem;">Belum ada mahasiswa yang login.</td></tr>`;

            return;

        }



        let html = "";

        students.forEach(s => {

            const statusBadge = s.is_active

                ? `<span class="status-badge badge-online">Aktif</span>`

                : `<span class="status-badge badge-offline">Offline</span>`;



            let cheatBadge = `<span style="color: #64748b;">0</span>`;

            if (s.tab_switches > 0) {

                cheatBadge = `<span class="status-badge badge-warning" title="${s.tab_switches} kali berpindah tab/jendela">${s.tab_switches}x Pindah Tab</span>`;

            }



            const pkgBadge = s.selected_category

                ? `<span style="background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.3); font-weight: 700; padding: 3px 8px; border-radius: 4px; font-size: 0.78rem; white-space: nowrap; display: inline-block;">Paket ${escapeHtml(s.selected_category)}</span>`

                : `<span style="background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); font-weight: 600; padding: 3px 8px; border-radius: 4px; font-size: 0.78rem; white-space: nowrap; display: inline-block;">Belum Pilih</span>`;



            const scoreVal = s.total_score || 0;

            const maxScore = s.max_score || 125;

            const scoreColor = scoreVal >= 85 ? "#10b981" : (scoreVal > 0 ? "#f59e0b" : "#94a3b8");

            const scoreBadge = `<div style="display: inline-flex; align-items: baseline; gap: 4px; font-weight: 700; white-space: nowrap;">

                <span style="color: ${scoreColor}; font-size: 0.95rem;">${scoreVal}</span>

                <span style="font-size: 0.72rem; color: var(--text-muted); font-weight: 500;">/ ${maxScore}</span>

                <span style="font-size: 0.72rem; color: #10b981; font-weight: 600; margin-left: 2px;">(${s.correct_count || 0} Benar)</span>

            </div>`;



            html += `

                <tr>

                    <td><strong>${escapeHtml(s.nim)}</strong></td>

                    <td>${escapeHtml(s.name)}</td>

                    <td><code>${escapeHtml(s.ip_address || "-")}</code></td>

                    <td>${pkgBadge}</td>

                    <td>${statusBadge}</td>

                    <td><strong style="color: #60a5fa;">${s.total_submitted}</strong> Soal</td>

                    <td>${scoreBadge}</td>

                    <td>${cheatBadge}</td>

                    <td style="text-align: right; white-space: nowrap;">

                        <button type="button" class="btn btn-secondary btn-sm" onclick="kickStudent('${escapeHtml(s.nim)}')" title="Tendang sesi untuk memaksa login ulang">

                            Reset Sesi

                        </button>

                        <button type="button" class="btn btn-warning btn-sm" style="margin-left: 0.35rem;" onclick="resetStudentCategory('${escapeHtml(s.nim)}', '${escapeHtml(s.name)}')" title="Reset pilihan paket soal mahasiswa agar dapat memilih ulang">

                            Reset Paket

                        </button>

                    </td>

                </tr>

            `;

        });

        tbody.innerHTML = html;

    } catch (err) {

        console.error("Failed loading students:", err);

    }

}



async function resetStudentCategory(nim, name) {

    if (!confirm(`Apakah Anda yakin ingin me-reset paket soal untuk mahasiswa ${name} (${nim})?\nMahasiswa akan diminta memilih paket soal kembali saat membuka ujian.`)) return;

    try {

        const res = await fetch(`/api/admin/student/${encodeURIComponent(nim)}/reset-category`, {

            method: "POST",

            headers: { "Content-Type": "application/json" }

        });

        const data = await res.json();

        if (data.status === "success") {

            showToast(data.message || `Paket soal mahasiswa ${nim} berhasil direset.`);

            loadDashboardData();

        } else {

            showToast(data.message || "Gagal mereset paket soal.", "danger");

        }

    } catch (err) {

        console.error("Reset category error:", err);

        showToast("Gagal menghubungi server untuk reset paket soal.", "danger");

    }

}



async function kickStudent(nim) {

    if (!confirm(`Apakah Anda yakin ingin me-reset sesi mahasiswa dengan NIM: ${nim}?`)) return;

    try {

        const res = await fetch("/api/admin/kick-student", {

            method: "POST",

            headers: { "Content-Type": "application/json" },

            body: JSON.stringify({ nim: nim })

        });

        const data = await res.json();

        showToast(data.message || "Sesi berhasil direset.");

        loadDashboardData();

    } catch (err) {

        showToast("Gagal mereset sesi mahasiswa.", "danger");

    }

}



async function confirmStopAllSessions() {

    if (!confirm("Hentikan SEMUA sesi mahasiswa yang aktif sekarang? Semua mahasiswa akan dipaksa logout dan perlu login ulang.")) return;

    const btn = document.getElementById("btn-stop-all-sessions");

    btn.disabled = true;

    btn.textContent = "Menghentikan...";

    try {

        const res = await fetch("/api/admin/stop-all-sessions", { method: "POST" });

        const data = await res.json();

        showToast(data.message || "Semua sesi telah dihentikan.");

        loadDashboardData();

    } catch (err) {

        showToast("Gagal menghentikan semua sesi.", "danger");

    } finally {

        btn.disabled = false;

        btn.textContent = "Hentikan Semua Sesi";

    }

}



function openClearSessionsModal() {

    document.getElementById("chk-clear-logs-also").checked = false;

    document.getElementById("clear-sessions-modal").style.display = "flex";

}



async function executeClearSessions() {

    const clearLogsAlso = document.getElementById("chk-clear-logs-also").checked;

    const btn = document.getElementById("btn-confirm-clear-sessions");

    btn.disabled = true;

    btn.textContent = "Membersihkan...";

    try {

        const res = await fetch("/api/admin/clear-sessions", {

            method: "POST",

            headers: { "Content-Type": "application/json" },

            body: JSON.stringify({ clear_logs: clearLogsAlso })

        });

        const data = await res.json();

        document.getElementById("clear-sessions-modal").style.display = "none";

        showToast(data.message || "Sesi sebelumnya berhasil dibersihkan.");

        loadDashboardData();

        if (clearLogsAlso) loadLogsData();

    } catch (err) {

        showToast("Gagal membersihkan sesi.", "danger");

    } finally {

        btn.disabled = false;

        btn.textContent = "Ya, Bersihkan Sekarang";

    }

}



async function confirmClearLogs() {

    if (!confirm("Hapus SELURUH riwayat log aktivitas ujian? Tindakan ini tidak dapat dibatalkan.")) return;

    const btn = document.getElementById("btn-clear-logs");

    btn.disabled = true;

    btn.textContent = "Membersihkan...";

    try {

        const res = await fetch("/api/admin/clear-logs", { method: "POST" });

        const data = await res.json();

        showToast(data.message || "Log berhasil dibersihkan.");

        loadLogsData();

    } catch (err) {

        showToast("Gagal membersihkan log.", "danger");

    } finally {

        btn.disabled = false;

        btn.textContent = "Bersihkan Semua Log";

    }

}



// ==============================================================================

// 3. Question & Package Management (CRUD)

// ==============================================================================



async function loadQuestionsData() {

    try {

        const res = await fetch("/api/admin/questions");

        const data = await res.json();

        questionsList = data.questions || [];

        availableCategories = data.categories || [];

        packagesList = data.packages || [];



        // If packages not provided in questions endpoint response, fetch from /api/admin/packages

        if (!packagesList || packagesList.length === 0) {

            try {

                const pkgRes = await fetch("/api/admin/packages");

                const pkgData = await pkgRes.json();

                packagesList = pkgData.packages || [];

            } catch (pkgErr) {

                console.error("Failed fetching packages:", pkgErr);

            }

        }



        // Update category filter dropdown

        const filterSelect = document.getElementById("filter-question-category");

        if (filterSelect) {

            const currentFilter = filterSelect.value;

            let optionsHtml = '<option value="">Semua Paket</option>';



            if (packagesList && packagesList.length > 0) {

                packagesList.forEach(p => {

                    optionsHtml += `<option value="${escapeHtml(p.code)}">Paket ${escapeHtml(p.code)} - ${escapeHtml(p.name)} (${p.total_questions ?? p.question_count ?? 0} Soal)</option>`;

                });

            } else {

                const knownCats = new Set(["A", "B", "C", "D"]);

                if (availableCategories.length > 0) {

                    availableCategories.forEach(c => knownCats.add(c.category));

                }

                questionsList.forEach(q => {

                    if (q.category) knownCats.add(q.category);

                });

                Array.from(knownCats).sort().forEach(cat => {

                    const count = questionsList.filter(q => (q.category || "A") === cat).length;

                    optionsHtml += `<option value="${escapeHtml(cat)}">Paket ${escapeHtml(cat)} (${count} Soal)</option>`;

                });

            }



            filterSelect.innerHTML = optionsHtml;

            if (currentFilter && (packagesList.some(p => p.code === currentFilter) || currentFilter === "")) {

                filterSelect.value = currentFilter;

            }

        }



        // Update modal question category dropdown

        const modalCatSelect = document.getElementById("modal-q-category");

        if (modalCatSelect && packagesList && packagesList.length > 0) {

            const currentVal = modalCatSelect.value;

            modalCatSelect.innerHTML = packagesList.map(p => `

                <option value="${escapeHtml(p.code)}">Paket ${escapeHtml(p.code)} - ${escapeHtml(p.name)}</option>

            `).join("");

            if (currentVal && packagesList.some(p => p.code === currentVal)) {

                modalCatSelect.value = currentVal;

            }

        }



        renderPackageCards();

        renderQuestionsTable();

    } catch (err) {

        console.error("Failed loading questions:", err);

    }

}



function renderPackageCards() {

    const grid = document.getElementById("package-summary-grid");

    if (!grid) return;



    if (!packagesList || packagesList.length === 0) {

        grid.innerHTML = `

            <div style="grid-column: 1 / -1; padding: 1.25rem; text-align: center; color: var(--text-muted); background: var(--bg-surface); border: 1px dashed var(--border-subtle); border-radius: var(--radius-md);">

                Belum ada paket soal yang terdaftar. Klik <strong>+ Tambah Paket Baru</strong> untuk membuatnya.

            </div>

        `;

        return;

    }



    const activeFilter = document.getElementById("filter-question-category")?.value || "";



    let html = "";

    packagesList.forEach(p => {

        const isFiltered = activeFilter === p.code;

        const cardBorder = isFiltered ? "border-color: #6366f1; box-shadow: 0 0 0 1px #6366f1;" : "";

        const statusBadge = p.is_active

            ? `<span class="status-badge badge-online" style="font-size: 0.68rem; padding: 1px 6px;">Aktif</span>`

            : `<span class="status-badge badge-offline" style="font-size: 0.68rem; padding: 1px 6px;">Nonaktif</span>`;



        html += `

            <div class="stat-card" style="padding: 0.95rem 1rem; position: relative; ${cardBorder} transition: all 0.15s ease;">

                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.45rem;">

                    <div style="display: flex; align-items: center; gap: 0.4rem;">

                        <span style="background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.3); font-weight: 800; padding: 2px 8px; border-radius: 4px; font-size: 0.78rem;">

                            Paket ${escapeHtml(p.code)}

                        </span>

                        ${statusBadge}

                    </div>

                    <div style="display: flex; gap: 0.3rem;">

                        <button type="button" class="btn btn-secondary btn-sm" onclick="openEditPackageModal('${escapeHtml(p.code)}')" title="Edit detail paket" style="padding: 2px 7px; font-size: 0.72rem; line-height: 1;">

                            Edit

                        </button>

                        <button type="button" class="btn btn-danger btn-sm" onclick="confirmDeletePackage('${escapeHtml(p.code)}', ${p.total_questions ?? p.question_count ?? 0}, ${p.total_students ?? p.student_count ?? 0})" title="Hapus paket soal ini" style="padding: 2px 7px; font-size: 0.72rem; line-height: 1;">

                            Hapus

                        </button>

                    </div>

                </div>

                <div style="font-weight: 700; font-size: 0.92rem; color: var(--text-main); margin-bottom: 0.35rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(p.name)}">

                    ${escapeHtml(p.name)}

                </div>

                ${p.description ? `<div style="font-size: 0.76rem; color: var(--text-muted); margin-bottom: 0.6rem; max-height: 2.4em; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;" title="${escapeHtml(p.description)}">${escapeHtml(p.description)}</div>` : `<div style="font-size: 0.76rem; color: var(--text-subtle); margin-bottom: 0.6rem; font-style: italic;">Tidak ada deskripsi tambahan.</div>`}

                

                <div style="display: flex; justify-content: space-between; align-items: center; padding-top: 0.5rem; border-top: 1px solid var(--border-subtle); font-size: 0.76rem;">

                    <div style="display: flex; gap: 0.55rem; color: var(--text-muted);">

                        <span><strong style="color: #60a5fa;">${p.total_questions ?? p.question_count ?? 0}</strong> Soal</span>

                        <span>&bull;</span>

                        <span><strong style="color: #34d399;">${p.total_weight ?? p.total_score ?? 0}</strong> Poin</span>

                        <span>&bull;</span>

                        <span><strong style="color: #fbbf24;">${p.total_students ?? p.student_count ?? 0}</strong> Mhs</span>

                    </div>

                    <button type="button" class="btn btn-secondary btn-sm" onclick="filterByPackage('${escapeHtml(p.code)}')" style="padding: 2px 8px; font-size: 0.72rem; ${isFiltered ? 'background: #6366f1; color: #fff; border-color: #6366f1;' : ''}">

                        ${isFiltered ? 'Menampilkan' : 'Filter'}

                    </button>

                </div>

            </div>

        `;

    });

    grid.innerHTML = html;

}



function filterByPackage(code) {

    const filterSelect = document.getElementById("filter-question-category");

    if (!filterSelect) return;

    if (filterSelect.value === code) {

        filterSelect.value = "";

    } else {

        filterSelect.value = code;

    }

    renderQuestionsTable();

    renderPackageCards();

}



function openAddPackageModal() {

    const modal = document.getElementById("package-modal");

    if (!modal) return;

    document.getElementById("package-modal-title").textContent = "Tambah Paket Soal Baru";

    const codeInput = document.getElementById("modal-pkg-code");

    codeInput.value = "";

    codeInput.readOnly = false;

    codeInput.style.opacity = "1";

    document.getElementById("modal-pkg-name").value = "";

    document.getElementById("modal-pkg-desc").value = "";

    document.getElementById("modal-pkg-active").checked = true;

    modal.dataset.mode = "create";

    modal.style.display = "flex";

    setTimeout(() => codeInput.focus(), 50);

}



function openEditPackageModal(code) {

    const pkg = packagesList.find(p => p.code === code);

    if (!pkg) return;

    const modal = document.getElementById("package-modal");

    if (!modal) return;

    document.getElementById("package-modal-title").textContent = `Edit Paket Soal ${pkg.code}`;

    const codeInput = document.getElementById("modal-pkg-code");

    codeInput.value = pkg.code;

    codeInput.readOnly = true;

    codeInput.style.opacity = "0.7";

    document.getElementById("modal-pkg-name").value = pkg.name;

    document.getElementById("modal-pkg-desc").value = pkg.description || "";

    document.getElementById("modal-pkg-active").checked = Boolean(pkg.is_active);

    modal.dataset.mode = "edit";

    modal.style.display = "flex";

    setTimeout(() => document.getElementById("modal-pkg-name").focus(), 50);

}



function closePackageModal() {

    const modal = document.getElementById("package-modal");

    if (modal) modal.style.display = "none";

}



async function savePackageForm(e) {

    e.preventDefault();

    const modal = document.getElementById("package-modal");

    const mode = modal ? modal.dataset.mode : "create";

    const code = document.getElementById("modal-pkg-code").value.trim().toUpperCase();

    const name = document.getElementById("modal-pkg-name").value.trim();

    const description = document.getElementById("modal-pkg-desc").value.trim();

    const is_active = document.getElementById("modal-pkg-active").checked;



    if (!code || !name) {

        showToast("Kode dan Nama Paket wajib diisi!", "danger");

        return;

    }



    const saveBtn = document.getElementById("btn-save-package");

    if (saveBtn) {

        saveBtn.disabled = true;

        saveBtn.textContent = "Menyimpan...";

    }



    try {

        let res;

        if (mode === "edit") {

            res = await fetch(`/api/admin/packages/${encodeURIComponent(code)}`, {

                method: "PUT",

                headers: { "Content-Type": "application/json" },

                body: JSON.stringify({ name, description, is_active })

            });

        } else {

            res = await fetch("/api/admin/packages", {

                method: "POST",

                headers: { "Content-Type": "application/json" },

                body: JSON.stringify({ code, name, description, is_active })

            });

        }



        const data = await res.json();

        if (res.ok && data.status === "success") {

            showToast(data.message || "Paket soal berhasil disimpan.");

            closePackageModal();

            await loadQuestionsData();

        } else {

            const errorMsg = data.detail || data.message || "Gagal menyimpan paket soal.";

            showToast(errorMsg, "danger");

        }

    } catch (err) {

        console.error("Save package error:", err);

        showToast("Terjadi kesalahan jaringan saat menyimpan paket soal.", "danger");

    } finally {

        if (saveBtn) {

            saveBtn.disabled = false;

            saveBtn.textContent = "Simpan Paket";

        }

    }

}



async function confirmDeletePackage(code, totalQuestions, totalStudents) {

    if (totalStudents > 0) {

        alert(`Tidak dapat menghapus Paket ${code}:\nMasih ada ${totalStudents} mahasiswa yang terkunci pada paket ini.\nSilakan lakukan 'Reset Paket' pada mahasiswa terkait di tab Monitoring terlebih dahulu.`);

        return;

    }



    let deleteQuestions = false;

    if (totalQuestions > 0) {

        const confirmCascade = confirm(`PERINGATAN:\nPaket '${code}' saat ini memiliki ${totalQuestions} butir soal.\n\nApakah Anda yakin ingin menghapus Paket '${code}' sekaligus MENGHAPUS SEMUA ${totalQuestions} SOAL & SUBMISI di dalamnya?\n\nKlik OK untuk menghapus paket dan seluruh soalnya, atau Cancel untuk membatalkan.`);

        if (!confirmCascade) return;

        deleteQuestions = true;

    } else {

        if (!confirm(`Hapus Paket '${code}' dari daftar paket soal ujian?`)) return;

    }



    try {

        const url = `/api/admin/packages/${encodeURIComponent(code)}${deleteQuestions ? "?delete_questions=true" : ""}`;

        const res = await fetch(url, { method: "DELETE" });

        const data = await res.json();

        if (res.ok && data.status === "success") {

            showToast(data.message || `Paket ${code} berhasil dihapus.`);

            // If current filter was this package, reset filter

            const filterSelect = document.getElementById("filter-question-category");

            if (filterSelect && filterSelect.value === code) {

                filterSelect.value = "";

            }

            await loadQuestionsData();

        } else {

            showToast(data.detail || data.message || "Gagal menghapus paket soal.", "danger");

        }

    } catch (err) {

        console.error("Delete package error:", err);

        showToast("Gagal menghubungi server untuk menghapus paket soal.", "danger");

    }

}



function renderQuestionsTable() {

    const tbody = document.getElementById("questions-table-body");

    if (!tbody) return;



    const filterSelect = document.getElementById("filter-question-category");

    const activeFilter = filterSelect ? filterSelect.value : "";



    const displayed = activeFilter

        ? questionsList.filter(q => (q.category || "A") === activeFilter)

        : questionsList;



    if (displayed.length === 0) {

        const msg = activeFilter

            ? `Belum ada soal ujian untuk Paket ${escapeHtml(activeFilter)}.`

            : "Belum ada soal ujian yang dibuat.";

        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 2rem;">${msg}</td></tr>`;

        return;

    }



    let html = "";

    displayed.forEach(q => {

        const cat = q.category || "A";

        html += `

            <tr>

                <td style="width: 100px; white-space: nowrap;">

                    <span style="background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.3); font-weight: 700; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; white-space: nowrap; display: inline-block;">

                        Paket ${escapeHtml(cat)}

                    </span>

                </td>

                <td style="width: 70px; white-space: nowrap;"><strong>#${q.question_number}</strong></td>

                <td style="min-width: 220px; max-width: 320px; white-space: normal; line-height: 1.4; word-break: break-word;">

                    <strong>${escapeHtml(q.title)}</strong>

                </td>

                <td style="width: 100px; white-space: nowrap;">

                    <span class="weight-pill" style="display: inline-block !important; white-space: nowrap;">${q.score_weight} Poin</span>

                </td>

                <td>

                    <code style="display: block; max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #38bdf8;" title="${escapeHtml(q.expected_query || '-')}">

                        ${escapeHtml(q.expected_query || "-")}

                    </code>

                </td>

                <td style="width: 140px; text-align: right; white-space: nowrap;">

                    <button type="button" class="btn btn-secondary btn-sm" onclick="openEditQuestionModal(${q.id})">Edit</button>

                    <button type="button" class="btn btn-danger btn-sm" onclick="deleteQuestion(${q.id})">Hapus</button>

                </td>

            </tr>

        `;

    });

    tbody.innerHTML = html;

}



function updateNextQuestionNumber() {

    const qId = document.getElementById("modal-q-id")?.value;

    const catSelect = document.getElementById("modal-q-category");

    const numInput = document.getElementById("modal-q-num");

    if (!qId && catSelect && numInput) {

        const cat = catSelect.value || "A";

        const catQuestions = questionsList.filter(q => (q.category || "A") === cat);

        const maxNum = catQuestions.reduce((max, q) => Math.max(max, q.question_number || 0), 0);

        numInput.value = maxNum + 1;

    }

}



function openAddQuestionModal() {

    document.getElementById("q-modal-title").textContent = "Tambah Soal Ujian Baru";

    document.getElementById("modal-q-id").value = "";

    const catSelect = document.getElementById("modal-q-category");
    if (catSelect && packagesList && packagesList.length > 0) {
        catSelect.innerHTML = packagesList.map(p => `
            <option value="${escapeHtml(p.code)}">Paket ${escapeHtml(p.code)} - ${escapeHtml(p.name)}</option>
        `).join("");
    }

    // Default to current category filter if set, else first package or "A"

    const filterVal = document.getElementById("filter-question-category")?.value || (packagesList && packagesList[0] ? packagesList[0].code : "A");

    if (catSelect && filterVal) {

        catSelect.value = filterVal;

    }



    updateNextQuestionNumber();



    document.getElementById("modal-q-title").value = "";

    document.getElementById("modal-q-desc").value = "";

    document.getElementById("modal-q-weight").value = "15";

    document.getElementById("modal-q-expected").value = "";

    const targetDbEl = document.getElementById("modal-q-target-db");

    if (targetDbEl) targetDbEl.value = "pagila";

    const imgUrlEl = document.getElementById("modal-q-image-url");

    if (imgUrlEl) imgUrlEl.value = "";

    const prevWrap = document.getElementById("modal-q-image-preview-wrap");

    if (prevWrap) prevWrap.style.display = "none";

    const clearBtn = document.getElementById("btn-clear-image");

    if (clearBtn) clearBtn.style.display = "none";

    document.getElementById("question-modal").style.display = "flex";

}



function openEditQuestionModal(qId) {

    const q = questionsList.find(item => item.id === qId);

    if (!q) return;

    document.getElementById("q-modal-title").textContent = `Edit Soal #${q.question_number} (Paket ${q.category || "A"})`;

    document.getElementById("modal-q-id").value = q.id;

    const catSelect = document.getElementById("modal-q-category");
    if (catSelect && packagesList && packagesList.length > 0) {
        catSelect.innerHTML = packagesList.map(p => `
            <option value="${escapeHtml(p.code)}">Paket ${escapeHtml(p.code)} - ${escapeHtml(p.name)}</option>
        `).join("");
    }

    if (catSelect) {

        catSelect.value = q.category || "A";

    }

    document.getElementById("modal-q-num").value = q.question_number;

    document.getElementById("modal-q-title").value = q.title;

    document.getElementById("modal-q-desc").value = q.description;

    document.getElementById("modal-q-weight").value = q.score_weight;

    document.getElementById("modal-q-expected").value = q.expected_query || "";

    const targetDbEl = document.getElementById("modal-q-target-db");

    if (targetDbEl) targetDbEl.value = q.target_database || "pagila";

    const imgUrl = (q.expected_output_image || "").trim();

    const imgUrlEl = document.getElementById("modal-q-image-url");

    const prevWrap = document.getElementById("modal-q-image-preview-wrap");

    const prevImg = document.getElementById("modal-q-image-preview");

    const clearBtn = document.getElementById("btn-clear-image");

    if (imgUrlEl) imgUrlEl.value = imgUrl;

    if (imgUrl && prevWrap && prevImg) {

        prevImg.src = imgUrl;

        prevWrap.style.display = "block";

        if (clearBtn) clearBtn.style.display = "inline-block";

    } else {

        if (prevWrap) prevWrap.style.display = "none";

        if (clearBtn) clearBtn.style.display = "none";

    }

    document.getElementById("question-modal").style.display = "flex";

}



function closeQuestionModal() {

    document.getElementById("question-modal").style.display = "none";

}



async function saveQuestionForm(e) {

    e.preventDefault();

    const qId = document.getElementById("modal-q-id").value;

    const payload = {

        question_id: qId ? parseInt(qId) : null,

        category: (document.getElementById("modal-q-category")?.value || "A").trim().toUpperCase(),

        question_number: parseInt(document.getElementById("modal-q-num").value),

        title: document.getElementById("modal-q-title").value.trim(),

        description: document.getElementById("modal-q-desc").value.trim(),

        score_weight: parseInt(document.getElementById("modal-q-weight").value),

        expected_query: document.getElementById("modal-q-expected").value.trim(),

        target_database: document.getElementById("modal-q-target-db")?.value || "pagila",

        expected_output_image: document.getElementById("modal-q-image-url")?.value.trim() || ""

    };



    if (!payload.title || !payload.description) {

        alert("Judul dan Deskripsi Soal wajib diisi!");

        return;

    }



    try {

        const res = await fetch("/api/admin/questions", {

            method: "POST",

            headers: { "Content-Type": "application/json" },

            body: JSON.stringify(payload)

        });

        const data = await res.json();

        if (data.status === "success") {

            showToast("Soal berhasil disimpan.");

            closeQuestionModal();

            loadQuestionsData();

        } else {

            showToast(data.message || "Gagal menyimpan soal.", "danger");

        }

    } catch (err) {

        showToast("Error koneksi server saat menyimpan soal.", "danger");

    }

}



async function deleteQuestion(qId) {

    if (!confirm("Hapus soal ini? Mahasiswa yang telah menjawab soal ini akan kehilangan submisi untuk nomor ini.")) return;

    try {

        const res = await fetch(`/api/admin/questions/${qId}`, { method: "DELETE" });

        const data = await res.json();

        showToast(data.message || "Soal berhasil dihapus.");

        loadQuestionsData();

    } catch (err) {

        showToast("Gagal menghapus soal.", "danger");

    }

}



function openDeleteAllQuestionsModal() {

    const input = document.getElementById("delete-all-confirm-input");

    const confirmBtn = document.getElementById("btn-confirm-delete-all-questions");

    if (input) input.value = "";

    if (confirmBtn) confirmBtn.disabled = true;

    document.getElementById("delete-all-questions-modal").style.display = "flex";

}



async function deleteAllQuestions() {

    try {

        const res = await fetch("/api/admin/questions", { method: "DELETE" });

        const data = await res.json();

        document.getElementById("delete-all-questions-modal").style.display = "none";

        showToast(data.message || "Seluruh soal berhasil dihapus.", "success");

        loadQuestionsData();

    } catch (err) {

        showToast("Gagal menghapus semua soal.", "danger");

    }

}



// Window exposures for inline event bindings

window.openAddPackageModal = openAddPackageModal;

window.openEditPackageModal = openEditPackageModal;

window.closePackageModal = closePackageModal;

window.savePackageForm = savePackageForm;

window.confirmDeletePackage = confirmDeletePackage;

window.filterByPackage = filterByPackage;

window.openAddQuestionModal = openAddQuestionModal;

window.openEditQuestionModal = openEditQuestionModal;

window.closeQuestionModal = closeQuestionModal;

window.saveQuestionForm = saveQuestionForm;

window.deleteQuestion = deleteQuestion;

window.openDeleteAllQuestionsModal = openDeleteAllQuestionsModal;

window.deleteAllQuestions = deleteAllQuestions;

window.resetStudentCategory = resetStudentCategory;

window.kickStudent = kickStudent;



// ==============================================================================

// 4. Database Sandbox Management

// ==============================================================================

async function loadSchemaPreview(targetDb) {

    const container = document.getElementById("db-schema-preview");

    if (!container) return;



    const dbSelector = document.getElementById("admin-db-selector");

    const currentDb = (targetDb || (dbSelector ? dbSelector.value : "pagila") || "pagila").toLowerCase();

    if (dbSelector && dbSelector.value !== currentDb) {

        dbSelector.value = currentDb;

    }



    const titleEl = document.getElementById("admin-schema-preview-title");

    if (titleEl) {

        titleEl.textContent = `Preview Skema Tabel '${currentDb}':`;

    }



    container.innerHTML = `<p style="color: var(--text-muted);"><span class="spinner" style="width:14px;height:14px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:6px;"></span>Memuat struktur database '${escapeHtml(currentDb)}'...</p>`;



    try {

        const res = await fetch(`/api/admin/schema?db=${encodeURIComponent(currentDb)}`);

        const data = await res.json();

        const schema = data.schema || {};

        _erdSchemaCache = schema;

        _erdRelCache = data.relations || [];



        if (titleEl) {

            titleEl.textContent = `Preview Skema Tabel '${currentDb}' (${Object.keys(schema).length} Tabel):`;

        }



        if (Object.keys(schema).length === 0) {

            container.innerHTML = `<p style="color: var(--text-muted); padding: 1rem;">Belum ada tabel di database '${escapeHtml(currentDb)}'.</p>`;

            return;

        }



        let html = "";

        Object.keys(schema).forEach(table => {

            const cols = schema[table];

            html += `

                <div style="background: #0f172a; border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.75rem; margin-bottom: 0.75rem;">

                    <div style="font-weight: 600; color: #93c5fd; margin-bottom: 0.4rem; display: flex; justify-content: space-between;">

                        <span>Tabel: ${table}</span>

                        <span style="font-size: 0.75rem; color: var(--text-muted);">${cols.length} Kolom</span>

                    </div>

                    <div style="display: flex; flex-wrap: wrap; gap: 0.35rem;">

                        ${cols.map(c => `

                            <span style="font-size: 0.75rem; background: #1e293b; padding: 0.15rem 0.45rem; border-radius: 3px; font-family: var(--font-mono); color: ${c.pk ? '#f59e0b' : '#cbd5e1'};">

                                ${c.pk ? '[PK] ' : ''}${c.name} (${c.type})

                            </span>

                        `).join("")}

                    </div>

                </div>

            `;

        });

        container.innerHTML = html;

    } catch (err) {

        container.innerHTML = `<p style="color: #ef4444;">Gagal memuat preview skema database '${escapeHtml(currentDb)}'.</p>`;

    }

}



async function confirmResetDatabase() {

    const dbSelector = document.getElementById("admin-db-selector");

    const currentDb = (dbSelector ? dbSelector.value : "classicmodels") || "classicmodels";

    if (!confirm(`Peringatan: Tindakan ini akan mengosongkan dan mengembalikan database '${currentDb}' ke kondisi awal dataset master. Lanjutkan?`)) {

        return;

    }



    const btn = document.getElementById("btn-reset-db");

    btn.disabled = true;

    btn.textContent = `Mereset Database ${currentDb}...`;



    try {

        const res = await fetch("/api/admin/reset-database", { 

            method: "POST",

            headers: { "Content-Type": "application/json" },

            body: JSON.stringify({ target_db: currentDb })

        });

        const data = await res.json();

        if (data.status === "success") {

            showToast(`Database '${currentDb}' berhasil di-reset!`);

            loadSchemaPreview(currentDb);

        } else {

            showToast(data.message || "Gagal mereset database.", "danger");

        }

    } catch (err) {

        showToast("Error saat menghubungi server untuk reset database.", "danger");

    } finally {

        btn.disabled = false;

        btn.textContent = "Reset Database Terpilih";

    }

}



async function handleSqlUpload(e) {

    e.preventDefault();

    const fileInput = document.getElementById("sql-file-input");

    if (!fileInput.files || fileInput.files.length === 0) {

        alert("Pilih file .sql terlebih dahulu!");

        return;

    }



    const targetDbSelect = document.getElementById("sql-upload-target-db");

    const targetDb = (targetDbSelect ? targetDbSelect.value : "classicmodels") || "classicmodels";



    const formData = new FormData();

    formData.append("file", fileInput.files[0]);

    formData.append("target_db", targetDb);



    const uploadBtn = document.getElementById("btn-upload-sql");

    uploadBtn.disabled = true;

    uploadBtn.textContent = `Mengeksekusi SQL ke ${targetDb}...`;



    try {

        const res = await fetch("/api/admin/upload-sql", {

            method: "POST",

            body: formData

        });

        const data = await res.json();

        if (data.status === "success") {

            showToast(`File SQL berhasil dieksekusi ke database '${targetDb}'!`);

            fileInput.value = "";

            const dbSelector = document.getElementById("admin-db-selector");

            if (dbSelector) dbSelector.value = targetDb;

            loadSchemaPreview(targetDb);

        } else {

            showToast(data.message || "Eksekusi SQL gagal.", "danger");

        }

    } catch (err) {

        showToast("Error saat mengunggah file SQL.", "danger");

    } finally {

        uploadBtn.disabled = false;

        uploadBtn.textContent = "Upload & Eksekusi";

    }

}



// ==============================================================================

// 5. Exam Event Logs

// ==============================================================================

async function loadLogsData() {

    const tbody = document.getElementById("logs-table-body");

    if (!tbody) return;



    try {

        const res = await fetch("/api/admin/logs");

        const data = await res.json();

        const logs = data.logs || [];



        if (logs.length === 0) {

            tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2rem;">Belum ada log aktivitas.</td></tr>`;

            return;

        }



        let html = "";

        logs.forEach(l => {

            let badgeClass = "badge-offline";

            if (l.action_type === "login") badgeClass = "badge-online";

            if (l.action_type === "submit") badgeClass = "badge-online";

            if (l.action_type === "blur_tab" || l.action_type === "paste_attempt") badgeClass = "badge-danger";

            if (l.action_type === "ip_switch_kick") badgeClass = "badge-warning";



            html += `

                <tr>

                    <td style="white-space: nowrap; font-size: 0.8rem; color: var(--text-muted);">${escapeHtml(l.timestamp || "-")}</td>

                    <td><strong>${escapeHtml(l.nim || "Sistem")}</strong></td>

                    <td>${escapeHtml(l.name || "-")}</td>

                    <td><span class="status-badge ${badgeClass}">${escapeHtml(l.action_type)}</span></td>

                    <td style="font-size: 0.85rem; color: #cbd5e1;">${escapeHtml(l.details || "-")}</td>

                </tr>

            `;

        });

        tbody.innerHTML = html;

    } catch (err) {

        console.error("Failed loading logs:", err);

    }

}



// ==============================================================================

// 6. Toast Notification Helper

// ==============================================================================

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

    if (!str) return "";

    return String(str)

        .replace(/&/g, "&amp;")

        .replace(/</g, "&lt;")

        .replace(/>/g, "&gt;")

        .replace(/"/g, "&quot;")

        .replace(/'/g, "&#039;");

}



// ==============================================================================

// 7. Ubah Password Master Admin

// ==============================================================================

function openChangePasswordModal() {

    const alertBox = document.getElementById("change-pw-alert");

    if (alertBox) {

        alertBox.style.display = "none";

        alertBox.textContent = "";

    }

    const currentInput = document.getElementById("current-master-pw");

    const newInput = document.getElementById("new-master-pw");

    const confirmInput = document.getElementById("confirm-master-pw");

    if (currentInput) currentInput.value = "";

    if (newInput) newInput.value = "";

    if (confirmInput) confirmInput.value = "";



    const modal = document.getElementById("change-pw-modal");

    if (modal) {

        modal.style.display = "flex";

        currentInput?.focus();

    }

}



async function handleChangePassword(e) {

    e.preventDefault();

    const currentPw = document.getElementById("current-master-pw").value;

    const newPw = document.getElementById("new-master-pw").value;

    const confirmPw = document.getElementById("confirm-master-pw").value;

    const alertBox = document.getElementById("change-pw-alert");



    const showAlert = (msg, isSuccess = false) => {

        if (!alertBox) return;

        alertBox.style.display = "block";

        if (isSuccess) {

            alertBox.style.backgroundColor = "rgba(16, 185, 129, 0.15)";

            alertBox.style.color = "#34d399";

            alertBox.style.border = "1px solid rgba(16, 185, 129, 0.3)";

        } else {

            alertBox.style.backgroundColor = "rgba(239, 68, 68, 0.15)";

            alertBox.style.color = "#f87171";

            alertBox.style.border = "1px solid rgba(239, 68, 68, 0.3)";

        }

        alertBox.textContent = msg;

    };



    if (newPw !== confirmPw) {

        showAlert("Konfirmasi password baru tidak cocok!");

        return;

    }



    if (newPw.length < 4) {

        showAlert("Password baru minimal 4 karakter!");

        return;

    }



    const btn = document.getElementById("btn-save-master-pw");

    btn.disabled = true;

    btn.textContent = "Menyimpan...";



    try {

        const res = await fetch("/api/admin/change-password", {

            method: "POST",

            headers: { "Content-Type": "application/json" },

            body: JSON.stringify({ current_password: currentPw, new_password: newPw })

        });

        const data = await res.json();

        if (data.success) {

            showAlert("Password master admin berhasil diperbarui!", true);

            showToast("Password master admin berhasil diperbarui!", "success");

            setTimeout(() => {

                document.getElementById("change-pw-modal").style.display = "none";

            }, 1200);

        } else {

            showAlert(data.message || "Gagal mengubah password!");

        }

    } catch (err) {

        showAlert("Terjadi kesalahan jaringan.");

    } finally {

        btn.disabled = false;

        btn.textContent = "Simpan Password";

    }

}



// ==============================================================================

// ERD Diagram — Structured Matrix Layout & Visual Relations (Admin)

// ==============================================================================



let _erdSchemaCache = null;

let _erdRelCache = [];



const ERD_TBL_W      = 230;

const ERD_COL_H      = 22;

const ERD_HDR_H      = 34;

const ERD_PAD        = 10;

const ERD_PALETTE    = [

    '#6366f1','#059669','#0284c7','#d97706','#8b5cf6',

    '#0d9488','#ec4899','#f97316','#3b82f6','#10b981'

];



let _dc = null;

let _dx = null;

let _dn = [];

let _de = [];

let _dt = {s:1, px:0, py:0};

let _dDrag = false;

let _dLast = {x:0, y:0};

let _dSelected = null;

let _draggedNode = null;

let _dragOffset = {x:0, y:0};

let _downPos = {x:0, y:0};



function _getTableColor(table, index) {

    const domainColors = {

        offices:      '#6366f1',

        employees:    '#4f46e5',

        customers:    '#059669',

        payments:     '#0d9488',

        orders:       '#d97706',

        orderdetails: '#ea580c',

        products:     '#0284c7',

        productlines: '#0891b2'

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

        loadSchemaPreview().then(() => _initDiagram());

        return;

    }



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



    ctx.fillStyle = _cssVar('--bg-app', '#0f172a');

    ctx.fillRect(0, 0, cv.width, cv.height);



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



    ctx.shadowColor = isSelected ? color : 'rgba(0,0,0,0.55)';

    ctx.shadowBlur  = isSelected ? 22 : 12;

    ctx.shadowOffsetY = 4;



    _rRect(ctx, x, y, w, h, R);

    ctx.fillStyle = _cssVar('--bg-surface', '#1e293b');

    ctx.fill();



    ctx.strokeStyle = isSelected ? color : 'rgba(255,255,255,0.08)';

    ctx.lineWidth   = isSelected ? 2.5 : 1;

    _rRect(ctx, x, y, w, h, R);

    ctx.stroke();



    ctx.shadowColor = 'transparent';

    ctx.shadowBlur = 0;

    ctx.shadowOffsetY = 0;



    const g = ctx.createLinearGradient(x, y, x + w, y + ERD_HDR_H);

    g.addColorStop(0, color);

    g.addColorStop(1, _lightenHex(color, 24));

    _rRectTop(ctx, x, y, w, ERD_HDR_H, R);

    ctx.fillStyle = g;

    ctx.fill();



    ctx.strokeStyle = 'rgba(0,0,0,0.2)';

    ctx.lineWidth = 1;

    ctx.beginPath();

    ctx.moveTo(x, y + ERD_HDR_H);

    ctx.lineTo(x + w, y + ERD_HDR_H);

    ctx.stroke();



    ctx.fillStyle = 'rgba(255,255,255,0.85)';

    const iconX = x + 12, iconY = y + ERD_HDR_H/2;

    ctx.fillRect(iconX, iconY - 5, 4, 4);

    ctx.fillRect(iconX + 6, iconY - 5, 4, 4);

    ctx.fillRect(iconX, iconY + 1, 4, 4);

    ctx.fillRect(iconX + 6, iconY + 1, 4, 4);



    ctx.fillStyle = '#ffffff';

    ctx.font = 'bold 13px "Segoe UI",system-ui,sans-serif';

    ctx.textAlign = 'left';

    ctx.textBaseline = 'middle';

    ctx.fillText(table, x + 26, y + ERD_HDR_H/2);



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



        if (i % 2 === 0) {

            ctx.fillStyle = elevColor;

            ctx.fillRect(x + 1, rowY, w - 2, ERD_COL_H);

        }



        if (i < cols.length - 1) {

            ctx.strokeStyle = sepColor;

            ctx.lineWidth = 0.5;

            ctx.beginPath();

            ctx.moveTo(x + 2, rowY + ERD_COL_H);

            ctx.lineTo(x + w - 2, rowY + ERD_COL_H);

            ctx.stroke();

        }



        let bx = x + 7;

        if (isPk) { bx = _drawBadge(ctx, bx, midY, 'PK', '#f59e0b'); }

        if (isFk) { bx = _drawBadge(ctx, bx, midY, 'FK', '#6366f1'); }



        ctx.fillStyle = isPk ? '#fbbf24' : (isFk ? '#c7d2fe' : mainColor);

        ctx.font = isPk ? 'bold 11px "Segoe UI",system-ui' : '11px "Segoe UI",system-ui';

        ctx.textAlign = 'left';

        ctx.textBaseline = 'middle';

        ctx.fillText(col.name, bx + 2, midY);



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



    const ay = a.y + ERD_HDR_H + (fromIdx >= 0 ? fromIdx * ERD_COL_H + ERD_COL_H/2 : a.h / 2) + off;

    const by = b.y + ERD_HDR_H + (toIdx   >= 0 ? toIdx   * ERD_COL_H + ERD_COL_H/2 : b.h / 2) + off;



    let ax, bx, cpx1, cpx2, cpy1, cpy2;

    let targetDir = 1;



    if (a.x >= b.x + b.w - 10) {

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



    const AS = 7;

    ctx.fillStyle = arrowColor;

    ctx.beginPath();

    ctx.moveTo(bx, by);

    ctx.lineTo(bx - targetDir * AS, by - 4);

    ctx.lineTo(bx - targetDir * AS, by + 4);

    ctx.closePath();

    ctx.fill();



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

        if (dist > 4) return;



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



// ==============================================================================

// Admin Question Screenshot Upload Handler (Fase 4)

// ==============================================================================

async function handleQuestionImageUpload(e) {

    const file = e.target.files[0];

    if (!file) return;



    const formData = new FormData();

    formData.append("image", file);



    try {

        showToast("Mengunggah screenshot tabel...");

        const res = await fetch("/api/admin/questions/upload-image", {

            method: "POST",

            body: formData

        });

        const data = await res.json();

        if (data.status === "success" && data.image_url) {

            document.getElementById("modal-q-image-url").value = data.image_url;

            const prevImg = document.getElementById("modal-q-image-preview");

            const prevWrap = document.getElementById("modal-q-image-preview-wrap");

            const clearBtn = document.getElementById("btn-clear-image");

            if (prevImg) prevImg.src = data.image_url;

            if (prevWrap) prevWrap.style.display = "block";

            if (clearBtn) clearBtn.style.display = "inline-block";

            showToast("Screenshot berhasil diunggah!", "success");

        } else {

            showToast(data.detail || "Gagal mengunggah gambar.", "danger");

        }

    } catch (err) {

        showToast("Error saat mengunggah file gambar.", "danger");

    } finally {

        e.target.value = "";

    }

}



function clearQuestionImage() {

    document.getElementById("modal-q-image-url").value = "";

    const prevWrap = document.getElementById("modal-q-image-preview-wrap");

    const prevImg = document.getElementById("modal-q-image-preview");

    const clearBtn = document.getElementById("btn-clear-image");

    if (prevImg) prevImg.src = "";

    if (prevWrap) prevWrap.style.display = "none";

    if (clearBtn) clearBtn.style.display = "none";

}



window.handleQuestionImageUpload = handleQuestionImageUpload;

window.clearQuestionImage = clearQuestionImage;

