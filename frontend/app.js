let currentUserId = "";
let currentUserDisplayName = "";
let currentUserData = null;
let availableChats = [];
let selectedChatId = "all";
let selectedChatTitle = "Учебный чат";
let currentLeaderboardPeriod = "all_time";
let currentLeaderboardScope = "class";
let lastThemeToggle = 0;

function toggleCardCollapse(cardId) {
  const card = document.getElementById(cardId);
  if (!card) return;
  card.classList.toggle("collapsed");
  const icon = card.querySelector(".collapse-icon");
  if (icon) {
    icon.textContent = card.classList.contains("collapsed") ? "▸" : "▾";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initUserFromMAX();
  loadProfile();

  const themeBtn = document.getElementById("theme-toggle-btn");
  if (themeBtn) {
    themeBtn.addEventListener("click", toggleTheme);
  }
});

function initTheme() {
  try {
    for (let i = 1; i <= 7; i++) {
      localStorage.removeItem("sferum_theme_v" + i);
    }
    localStorage.removeItem("sferum_theme");
  } catch (e) {}

  let savedTheme = "light";
  try {
    savedTheme = localStorage.getItem("sferum_theme_v8") || "light";
  } catch (e) {}

  applyTheme(savedTheme === "dark" ? "dark" : "light");
}

function toggleTheme(event) {
  if (event) {
    if (typeof event.preventDefault === "function") event.preventDefault();
    if (typeof event.stopPropagation === "function") event.stopPropagation();
  }
  const now = Date.now();
  if (now - lastThemeToggle < 350) {
    return;
  }
  lastThemeToggle = now;

  const current = document.documentElement.getAttribute("data-theme") || "light";
  const next = current === "light" ? "dark" : "light";
  applyTheme(next);
  try {
    localStorage.setItem("sferum_theme_v8", next);
  } catch (e) {}
  if (typeof showToast === "function") {
    showToast(next === "dark" ? "Тёмная тема" : "Светлая тема");
  }
}

function applyTheme(theme) {
  const safeTheme = theme === "dark" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", safeTheme);
  document.documentElement.style.colorScheme = safeTheme === "light" ? "only light" : "dark";
  document.documentElement.style.backgroundColor = safeTheme === "dark" ? "#141415" : "#edeef0";
  document.documentElement.style.color = safeTheme === "dark" ? "#e1e3e6" : "#000000";

  if (document.body) {
    document.body.setAttribute("data-theme", safeTheme);
    document.body.style.colorScheme = safeTheme === "light" ? "only light" : "dark";
    document.body.style.backgroundColor = safeTheme === "dark" ? "#141415" : "#edeef0";
    document.body.style.color = safeTheme === "dark" ? "#e1e3e6" : "#000000";
  }

  const metaTheme = document.getElementById("meta-theme-color");
  if (metaTheme) {
    metaTheme.setAttribute("content", safeTheme === "dark" ? "#141415" : "#edeef0");
  }

  const metaScheme = document.getElementById("meta-color-scheme");
  if (metaScheme) {
    metaScheme.setAttribute("content", safeTheme === "light" ? "only light" : "dark");
  }

  const sunIcon = document.getElementById("theme-icon-sun");
  const moonIcon = document.getElementById("theme-icon-moon");
  if (sunIcon && moonIcon) {
    if (safeTheme === "dark") {
      sunIcon.classList.remove("hidden");
      moonIcon.classList.add("hidden");
    } else {
      sunIcon.classList.add("hidden");
      moonIcon.classList.remove("hidden");
    }
  }
}

async function initUserFromMAX() {
  const urlParams = new URLSearchParams(window.location.search);
  const urlUserId = urlParams.get("user_id");

  if (window.WebApp && window.WebApp.initDataUnsafe && window.WebApp.initDataUnsafe.user) {
    const maxUser = window.WebApp.initDataUnsafe.user;
    currentUserId = String(maxUser.id);

    const fName = maxUser.first_name || "";
    const lName = maxUser.last_name || "";
    const builtName = `${fName} ${lName}`.trim() || maxUser.username || "";
    if (builtName) {
      currentUserDisplayName = builtName;
      syncUserWithBackend(maxUser.id, fName, lName, maxUser.username);
    }

    const demoBar = document.getElementById("demo-bar");
    if (demoBar) demoBar.style.display = "none";
  } else if (urlUserId) {
    currentUserId = String(urlUserId);
    const demoSelect = document.getElementById("demo-user-select");
    if (demoSelect) demoSelect.value = currentUserId;
  }
}

async function syncUserWithBackend(userId, firstName, lastName, username) {
  try {
    await fetch("/api/sync-user", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: String(userId),
        first_name: firstName,
        last_name: lastName,
        username: username,
      }),
    });
  } catch (err) {}
}

function switchDemoUser(newUserId) {
  currentUserId = String(newUserId);
  currentUserDisplayName = "";
  showToast("Выбран профиль: " + currentUserId);
  loadProfile();
  refreshActiveTab();
}

function refreshActiveTab() {
  const activeTab = document.querySelector(".tab-pane.active");
  if (!activeTab) return;
  const tabId = activeTab.id.replace("tab-", "");
  if (tabId === "leaderboard") loadLeaderboard();
  if (tabId === "achievements") loadAchievements();
  if (tabId === "rewards") loadRewards();
  if (tabId === "teacher") loadTeacherData();
}

function getInitials(name) {
  if (!name) return "УЧ";
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

async function loadProfile() {
  try {
    let url = `/api/profile?user_id=${encodeURIComponent(currentUserId)}`;
    if (selectedChatId && selectedChatId !== "all") {
      url += `&chat_id=${encodeURIComponent(selectedChatId)}`;
    }
    if (currentUserDisplayName) {
      url += `&display_name=${encodeURIComponent(currentUserDisplayName)}`;
    }

    const res = await fetch(url);
    if (!res.ok) throw new Error("Profile error");
    const data = await res.json();
    currentUserData = data;
    if (data.max_user_id) {
      currentUserId = String(data.max_user_id);
    }

    document.getElementById("header-name").textContent = data.display_name;
    const roleElem = document.getElementById("header-role");
    if (data.role === "teacher") {
      roleElem.textContent = "Учитель";
      roleElem.classList.add("teacher");
    } else {
      roleElem.textContent = "Ученик";
      roleElem.classList.remove("teacher");
    }

    document.getElementById("header-coins").textContent = data.balance_spasibki;
    document.getElementById("header-avatar").textContent = getInitials(data.display_name);

    document.getElementById("profile-level-title").textContent = data.role === "teacher" ? "Преподаватель" : data.rank;
    document.getElementById("profile-level-num").textContent = data.role === "teacher" ? "Наставник" : `${data.level} уровень`;

    const xpInLevel = data.xp % 100;
    document.getElementById("profile-xp-text").textContent = data.role === "teacher" ? "Вне игрового рейтинга" : `${xpInLevel} / 100 XP (${data.xp} всего)`;
    document.getElementById("profile-xp-fill").style.width = data.role === "teacher" ? "100%" : `${Math.min(100, xpInLevel)}%`;

    document.getElementById("profile-helped").textContent = data.helped_count || 0;
    document.getElementById("profile-questions").textContent = data.questions_count || 0;
    document.getElementById("profile-rank").textContent = data.role === "teacher" ? "—" : `#${data.rank_position || 1}`;

    const shopCoins = document.getElementById("shop-coins");
    if (shopCoins) shopCoins.textContent = data.balance_spasibki;

    if (data.chats && data.chats.length > 0) {
      availableChats = data.chats.filter(c => c.title && c.title.toLowerCase() !== "диалог");
      if (selectedChatId === "all" || !availableChats.some(c => c.id === selectedChatId)) {
        selectedChatId = availableChats[0].id;
        selectedChatTitle = availableChats[0].title;
      }
    } else {
      availableChats = [{ id: "my_class", title: "Мой учебный чат", role: data.role }];
      selectedChatId = "my_class";
      selectedChatTitle = "Мой учебный чат";
    }

    const isTeacherInChat = (data.role === "teacher");
    const teacherNavBtn = document.getElementById("nav-teacher-btn");
    if (teacherNavBtn) {
      teacherNavBtn.style.display = isTeacherInChat ? "flex" : "none";
    }
    const teacherTab = document.getElementById("tab-teacher");
    if (!isTeacherInChat && teacherTab && teacherTab.classList.contains("active")) {
      switchTab("profile", document.querySelector(".bottom-tabbar .tab-item"));
    }

    updateClassSelectorUI();
  } catch (err) {
    showToast("Не удалось обновить профиль");
  }
}

function updateClassSelectorUI() {
  const label = document.getElementById("current-class-label");
  if (label) {
    label.textContent = selectedChatTitle;
  }
}

function openClassModal() {
  const modal = document.getElementById("class-modal");
  const list = document.getElementById("sheet-classes-list");
  if (!modal || !list) return;

  const validChats = availableChats.filter(c => c.title && c.title.toLowerCase() !== "диалог");

  list.innerHTML = validChats.map(c => `
    <div class="class-option-card ${c.id === selectedChatId ? 'selected' : ''}" onclick="selectClass('${c.id}', '${escapeHtml(c.title)}')">
      <div>
        <div class="class-option-name">${escapeHtml(c.title)}</div>
        <div class="class-option-role">${c.role === 'teacher' ? 'Преподаватель' : 'Ученик'}</div>
      </div>
      <div>${c.id === selectedChatId ? '✓' : ''}</div>
    </div>
  `).join("");

  modal.classList.remove("hidden");
}

function closeClassModal(e) {
  if (e && e.target && e.target.closest && e.target.closest(".modal-sheet") && !e.target.classList.contains("sheet-close")) {
    return;
  }
  const modal = document.getElementById("class-modal");
  if (modal) modal.classList.add("hidden");
}

function selectClass(chatId, chatTitle) {
  selectedChatId = chatId;
  selectedChatTitle = chatTitle;

  const chatObj = availableChats.find(c => c.id === chatId);
  const isTeacher = chatObj ? (chatObj.role === "teacher") : false;
  const roleElem = document.getElementById("header-role");
  if (roleElem) {
    if (isTeacher) {
      roleElem.textContent = "Учитель";
      roleElem.classList.add("teacher");
    } else {
      roleElem.textContent = "Ученик";
      roleElem.classList.remove("teacher");
    }
  }

  const teacherNavBtn = document.getElementById("nav-teacher-btn");
  if (teacherNavBtn) {
    teacherNavBtn.style.display = isTeacher ? "flex" : "none";
  }
  const teacherTab = document.getElementById("tab-teacher");
  if (!isTeacher && teacherTab && teacherTab.classList.contains("active")) {
    switchTab("profile", document.querySelector(".bottom-tabbar .tab-item"));
  }

  updateClassSelectorUI();
  closeClassModal();
  showToast("Выбран чат: " + chatTitle);
  loadProfile();
  refreshActiveTab();
}

function switchTab(tabName, btnElement) {
  document.querySelectorAll(".tab-pane").forEach(pane => pane.classList.remove("active"));
  const target = document.getElementById(`tab-${tabName}`);
  if (target) target.classList.add("active");

  document.querySelectorAll(".tab-item").forEach(item => item.classList.remove("active"));
  if (btnElement) btnElement.classList.add("active");

  if (tabName === "profile") loadProfile();
  if (tabName === "leaderboard") loadLeaderboard();
  if (tabName === "achievements") loadAchievements();
  if (tabName === "rewards") loadRewards();
  if (tabName === "teacher") loadTeacherData();
}

function setLeaderboardScope(scope) {
  currentLeaderboardScope = scope;
  const isChat = (scope === "chat" || scope === "class");
  const classBtn = document.getElementById("scope-class-btn");
  const allBtn = document.getElementById("scope-school-btn");
  if (classBtn) classBtn.classList.toggle("active", isChat);
  if (allBtn) allBtn.classList.toggle("active", !isChat);
  loadLeaderboard();
}

function changeLeaderboardPeriod(period) {
  currentLeaderboardPeriod = period;
  document.getElementById("btn-period-all").classList.toggle("active", period === "all_time");
  document.getElementById("btn-period-week").classList.toggle("active", period === "weekly");
  loadLeaderboard();
}

async function loadLeaderboard() {
  const container = document.getElementById("leaderboard-container");
  container.innerHTML = '<div class="state-loading">Загрузка рейтинга...</div>';

  try {
    let url = `/api/leaderboard?period=${currentLeaderboardPeriod}`;
    const isChat = (currentLeaderboardScope === "chat" || currentLeaderboardScope === "class");
    if (isChat && selectedChatId && selectedChatId !== "all") {
      url += `&chat_id=${encodeURIComponent(selectedChatId)}`;
    } else {
      url += `&chat_id=all`;
    }

    const res = await fetch(url);
    const data = await res.json();
    const leaders = data.items || [];

    if (!leaders.length) {
      container.innerHTML = '<p class="empty-state-text">В этом рейтинге пока нет участников.</p>';
      return;
    }

    container.innerHTML = leaders.map(item => {
      let rankText = `#${item.rank_position}`;
      let topClass = "";
      if (item.rank_position === 1) topClass = "top-1";
      if (item.rank_position === 2) topClass = "top-2";
      if (item.rank_position === 3) topClass = "top-3";

      const isCurrent = String(item.max_user_id) === String(currentUserId);
      const initials = getInitials(item.display_name);

      return `
        <div class="leader-card ${isCurrent ? 'current-user' : ''}">
          <div class="leader-rank-col ${topClass}">${rankText}</div>
          <div class="leader-avatar">${initials}</div>
          <div class="leader-details">
            <div class="leader-name">${escapeHtml(item.display_name)}</div>
            <div class="leader-meta">${escapeHtml(item.rank)}</div>
          </div>
          <div class="leader-score">
            <div class="leader-xp-val">${item.xp} XP</div>
            <div class="leader-coins-val">${item.balance_spasibki} спасибок</div>
          </div>
        </div>
      `;
    }).join("");

  } catch (err) {
    container.innerHTML = '<p class="empty-state-text">Не удалось загрузить рейтинг</p>';
  }
}

const ACHIEVEMENT_THEMES = {
  first_step: { icon: "🎯", bg: "linear-gradient(135deg, #ff416c 0%, #ff4b2b 100%)", glow: "rgba(255, 65, 108, 0.4)" },
  fast_aid: { icon: "⚡️", bg: "linear-gradient(135deg, #f7971e 0%, #ffd200 100%)", glow: "rgba(247, 151, 30, 0.45)" },
  rescuer: { icon: "🛟", bg: "linear-gradient(135deg, #00b4db 0%, #0083b0 100%)", glow: "rgba(0, 180, 219, 0.4)" },
  marathoner: { icon: "🏃‍♂️", bg: "linear-gradient(135deg, #11998e 0%, #38ef7d 100%)", glow: "rgba(56, 239, 125, 0.4)" },
  week_streak: { icon: "🔥", bg: "linear-gradient(135deg, #f12711 0%, #f5af19 100%)", glow: "rgba(241, 39, 17, 0.45)" },
  mentor: { icon: "🧠", bg: "linear-gradient(135deg, #8a2387 0%, #e94057 50%, #f27121 100%)", glow: "rgba(233, 64, 87, 0.45)" },
  subject_expert: { icon: "📐", bg: "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)", glow: "rgba(79, 172, 254, 0.4)" },
  universal: { icon: "🌐", bg: "linear-gradient(135deg, #654ea3 0%, #eaafc8 100%)", glow: "rgba(101, 78, 163, 0.4)" },
  class_legend: { icon: "👑", bg: "linear-gradient(135deg, #f39c12 0%, #f1c40f 100%)", glow: "rgba(243, 156, 18, 0.5)" },
  brave_question: { icon: "🙋‍♂️", bg: "linear-gradient(135deg, #36d1dc 0%, #5b86e5 100%)", glow: "rgba(91, 134, 229, 0.4)" },
  curious: { icon: "🔍", bg: "linear-gradient(135deg, #0ba360 0%, #3cba92 100%)", glow: "rgba(60, 186, 146, 0.4)" },
  grateful: { icon: "🤝", bg: "linear-gradient(135deg, #e17055 0%, #fab1a0 100%)", glow: "rgba(225, 112, 85, 0.4)" },
  week_leader: { icon: "🏆", bg: "linear-gradient(135deg, #f6d365 0%, #fda085 100%)", glow: "rgba(246, 211, 101, 0.5)" },
  teacher_choice: { icon: "⭐️", bg: "linear-gradient(135deg, #a18cd1 0%, #fbc2eb 100%)", glow: "rgba(161, 140, 209, 0.45)" },
};

async function loadAchievements() {
  const container = document.getElementById("achievements-container");
  container.innerHTML = '<div class="state-loading">Загрузка достижений...</div>';

  try {
    const res = await fetch(`/api/achievements?user_id=${currentUserId}`);
    const achievements = await res.json();

    if (!achievements.length) {
      container.innerHTML = '<p class="empty-state-text">Достижения не найдены.</p>';
      return;
    }

    container.innerHTML = achievements.map(ach => {
      const isUnlocked = ach.unlocked;
      let statusTag = "";
      if (isUnlocked && ach.awarded_at) {
        const d = new Date(ach.awarded_at);
        statusTag = `<span class="ach-tag tag-unlocked">Получено ${d.toLocaleDateString('ru-RU')}</span>`;
      } else if (isUnlocked) {
        statusTag = `<span class="ach-tag tag-unlocked">Получено</span>`;
      } else {
        statusTag = `<span class="ach-tag tag-locked">Не открыто</span>`;
      }

      const theme = ACHIEVEMENT_THEMES[ach.code] || {
        icon: ach.icon_url || "🏅",
        bg: "linear-gradient(135deg, #2d78f0 0%, #70a7ff 100%)",
        glow: "rgba(45, 120, 240, 0.35)",
      };

      const iconContent = (ach.icon_url && (ach.icon_url.startsWith("http") || ach.icon_url.startsWith("/")))
        ? `<img src="${escapeHtml(ach.icon_url)}" class="ach-custom-img" alt="">`
        : `<span class="ach-emoji">${theme.icon}</span>`;

      return `
        <div class="ach-item-card ${isUnlocked ? 'unlocked' : 'locked'}">
          <div class="ach-icon-circle" style="background: ${theme.bg}; box-shadow: 0 4px 12px ${isUnlocked ? theme.glow : 'transparent'};">
            ${iconContent}
          </div>
          <div class="ach-title">${escapeHtml(ach.name_ru)}</div>
          <div class="ach-desc">${escapeHtml(ach.description_ru)}</div>
          ${statusTag}
        </div>
      `;
    }).join("");

  } catch (err) {
    container.innerHTML = '<p class="empty-state-text">Не удалось загрузить список наград</p>';
  }
}

async function loadRewards() {
  const container = document.getElementById("rewards-container");
  container.innerHTML = '<div class="state-loading">Загрузка лавки...</div>';

  try {
    let url = `/api/rewards?user_id=${encodeURIComponent(currentUserId)}`;
    if (selectedChatId && selectedChatId !== "all") {
      url += `&chat_id=${encodeURIComponent(selectedChatId)}`;
    }

    const res = await fetch(url);
    const rewards = await res.json();

    if (!rewards.length) {
      container.innerHTML = '<p class="empty-state-text">В лавке пока нет доступных наград.</p>';
    } else {
      const chatObj = availableChats.find(c => c.id === selectedChatId);
      const isTeacherInChat = Boolean(
        (currentUserData && currentUserData.role === "teacher") ||
        (chatObj && chatObj.role === "teacher")
      );

      container.innerHTML = rewards.map(r => {
        const isOwnReward = Boolean(r.created_by_teacher_id && String(r.created_by_teacher_id) === String(currentUserId));
        let actionBtnHtml = "";
        if (isOwnReward) {
          actionBtnHtml = `<span class="reward-tag-self">Создано вами</span> <button class="sferum-btn btn-danger-sm" onclick="handleDeleteReward(${r.id})">Удалить</button>`;
        } else if (isTeacherInChat) {
          actionBtnHtml = `<span class="reward-tag-teacher">Для учеников</span> <button class="sferum-btn btn-danger-sm" onclick="handleDeleteReward(${r.id})">Удалить</button>`;
        } else {
          actionBtnHtml = `<button class="sferum-btn btn-primary" onclick="handleClaimReward(${r.id}, ${r.cost_spasibki})">Обменять</button>`;
        }

        return `
          <div class="reward-card-item">
            <div class="reward-main-col">
              <div class="reward-item-title">${escapeHtml(r.title)}</div>
              <div class="reward-item-desc">${escapeHtml(r.description)}</div>
              <div class="reward-cost-tag">${r.cost_spasibki} спасибок</div>
            </div>
            <div>
              ${actionBtnHtml}
            </div>
          </div>
        `;
      }).join("");
    }

    loadMyClaims();

  } catch (err) {
    container.innerHTML = '<p class="empty-state-text">Не удалось загрузить лавку</p>';
  }
}

async function loadMyClaims() {
  const container = document.getElementById("my-requests-list");
  try {
    const res = await fetch(`/api/my-claims?user_id=${currentUserId}`);
    const claims = await res.json();

    if (!claims.length) {
      container.innerHTML = '<p class="empty-state-text">У вас пока нет активных запросов.</p>';
      return;
    }

    container.innerHTML = claims.map(c => {
      let statusText = "Ожидает учителя";
      let statusClass = "status-requested";
      if (c.status === "approved") {
        statusText = "Одобрено учителем";
        statusClass = "status-approved";
      } else if (c.status === "rejected") {
        statusText = "Отклонено";
        statusClass = "status-rejected";
      }

      return `
        <div class="claim-history-row">
          <div>
            <strong>${escapeHtml(c.title)}</strong>
            <div class="stat-caption">${c.cost_spasibki} спасибок</div>
          </div>
          <span class="claim-status-pill ${statusClass}">${statusText}</span>
        </div>
      `;
    }).join("");

  } catch (err) {
    container.innerHTML = '<p class="empty-state-text">Не удалось загрузить историю наград</p>';
  }
}

async function handleClaimReward(rewardId, cost) {
  if (currentUserData && currentUserData.balance_spasibki < cost) {
    showToast(`Нужно ${cost} спасибок. У вас ${currentUserData.balance_spasibki}`);
    return;
  }

  try {
    const res = await fetch("/api/rewards/claim", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": currentUserId,
      },
      body: JSON.stringify({
        reward_id: rewardId,
        user_id: currentUserId,
        chat_id: selectedChatId !== "all" ? selectedChatId : null,
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Ошибка запроса");
    }

    showToast("Заявка успешно отправлена учителю!");
    loadProfile();
    loadRewards();

  } catch (err) {
    showToast(err.message || "Ошибка обмена");
  }
}

async function loadTeacherData() {
  const listContainer = document.getElementById("teacher-requests-list");
  const badgeCount = document.getElementById("pending-claims-count");
  listContainer.innerHTML = '<div class="state-loading">Загрузка заявок...</div>';

  try {
    let url = `/api/teacher/overview?user_id=${encodeURIComponent(currentUserId)}`;
    if (selectedChatId && selectedChatId !== "all") {
      url += `&chat_id=${encodeURIComponent(selectedChatId)}`;
    }

    const res = await fetch(url);
    if (!res.ok) throw new Error("Только для учителей");
    const overview = await res.json();

    const claims = overview.pending_claims || [];
    if (badgeCount) badgeCount.textContent = claims.length;

    const pendingCard = document.getElementById("card-pending-claims");
    if (pendingCard) {
      if (claims.length === 0) {
        pendingCard.classList.add("collapsed");
        const icon = pendingCard.querySelector(".collapse-icon");
        if (icon) icon.textContent = "▸";
      } else {
        pendingCard.classList.remove("collapsed");
        const icon = pendingCard.querySelector(".collapse-icon");
        if (icon) icon.textContent = "▾";
      }
    }

    if (!claims.length) {
      listContainer.innerHTML = '<p class="empty-state-text">Новых заявок от учеников нет.</p>';
    } else {
      listContainer.innerHTML = claims.map(c => `
        <div class="teacher-claim-card">
          <div class="claim-user-row">
            <span class="claim-student-name">${escapeHtml(c.student_name)}</span>
            <span class="claim-price-pill">${c.cost_spasibki} спасибок</span>
          </div>
          <div class="claim-reward-text">Запрос: <b>${escapeHtml(c.reward_title)}</b></div>
          <div class="claim-btn-row">
            <button class="sferum-btn btn-primary flex-1" onclick="handleReviewClaim(${c.claim_id}, 'approved')">Одобрить</button>
            <button class="sferum-btn btn-outline flex-1" onclick="handleReviewClaim(${c.claim_id}, 'rejected')">Отклонить</button>
          </div>
        </div>
      `).join("");
    }

    const issuedContainer = document.getElementById("teacher-issued-list");
    const issuedBadge = document.getElementById("teacher-issued-count");
    const issued = overview.issued_rewards || [];
    if (issuedBadge) issuedBadge.textContent = issued.length;

    if (issuedContainer) {
      if (!issued.length) {
        issuedContainer.innerHTML = '<p class="empty-state-text">Вы пока не выдавали наград в этом чате.</p>';
      } else {
        issuedContainer.innerHTML = issued.map(item => `
          <div class="teacher-issued-row">
            <div class="issued-info-col">
              <div class="issued-student-name">${escapeHtml(item.student_name)}</div>
              <div class="issued-reward-title">${escapeHtml(item.reward_title)}</div>
            </div>
            <div class="issued-meta-col">
              <span class="issued-price-tag">${item.cost_spasibki > 0 ? item.cost_spasibki + ' спасибок' : 'Бонус'}</span>
              <span class="issued-date">${escapeHtml(item.date || '')}</span>
            </div>
          </div>
        `).join("");
      }
    }

    loadStudentsDropdown();
    loadTeacherRewards();

  } catch (err) {
    listContainer.innerHTML = '<p class="empty-state-text">Кабинет доступен учителям.</p>';
  }
}

async function loadStudentsDropdown() {
  const selectElem = document.getElementById("teacher-award-student");
  try {
    let url = "/api/students";
    if (selectedChatId && selectedChatId !== "all") {
      url += `?chat_id=${encodeURIComponent(selectedChatId)}`;
    }
    const res = await fetch(url);
    const students = await res.json();
    selectElem.innerHTML = '<option value="">Выберите ученика...</option>' +
      students.map(s => `<option value="${s.max_user_id}">${escapeHtml(s.display_name)} (${s.xp} XP, ${s.balance_spasibki} спасибок)</option>`).join("");
  } catch (err) {
    selectElem.innerHTML = '<option value="">Ошибка загрузки учеников</option>';
  }
}

async function handleReviewClaim(claimId, decision) {
  try {
    const res = await fetch("/api/teacher/review-claim", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": currentUserId,
      },
      body: JSON.stringify({ claim_id: claimId, decision: decision })
    });

    if (!res.ok) throw new Error("Ошибка обновления");
    showToast(decision === "approved" ? "Заявка одобрена!" : "Заявка отклонена");
    loadTeacherData();

  } catch (err) {
    showToast("Не удалось обработать заявку");
  }
}

async function handleCreateReward(e) {
  e.preventDefault();
  const title = document.getElementById("rew-title").value.trim();
  const desc = document.getElementById("rew-desc").value.trim();
  const price = parseInt(document.getElementById("rew-price").value);

  if (!title || !desc || !price) return;

  try {
    const res = await fetch("/api/teacher/rewards", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": currentUserId,
      },
      body: JSON.stringify({
        title: title,
        description: desc,
        cost_spasibki: price,
        chat_id: selectedChatId !== "all" ? selectedChatId : null,
      })
    });

    if (!res.ok) throw new Error("Ошибка публикации");
    showToast("Награда добавлена в лавку!");
    document.getElementById("create-reward-form").reset();
    document.getElementById("rew-price").value = 5;
    loadRewards();
    loadTeacherRewards();

  } catch (err) {
    showToast("Не удалось добавить награду");
  }
}

async function loadTeacherRewards() {
  const container = document.getElementById("teacher-rewards-list");
  const countBadge = document.getElementById("teacher-rewards-count");
  if (!container) return;

  try {
    let url = `/api/rewards?user_id=${encodeURIComponent(currentUserId)}`;
    if (selectedChatId && selectedChatId !== "all") {
      url += `&chat_id=${encodeURIComponent(selectedChatId)}`;
    }
    const res = await fetch(url);
    const rewards = await res.json();
    if (countBadge) countBadge.textContent = rewards.length;

    if (!rewards.length) {
      container.innerHTML = '<p class="empty-state-text">Активных наград пока нет.</p>';
      return;
    }

    container.innerHTML = rewards.map(r => `
      <div class="teacher-reward-row">
        <div class="reward-main-col">
          <div class="reward-item-title">${escapeHtml(r.title)}</div>
          <div class="reward-item-desc">${escapeHtml(r.description)}</div>
          <div class="reward-cost-tag">${r.cost_spasibki} спасибок</div>
        </div>
        <div>
          <button class="sferum-btn btn-danger-sm" onclick="handleDeleteReward(${r.id})">Удалить</button>
        </div>
      </div>
    `).join("");
  } catch (err) {
    container.innerHTML = '<p class="empty-state-text">Не удалось загрузить награды</p>';
  }
}

async function handleDeleteReward(rewardId) {
  try {
    const res = await fetch(`/api/teacher/rewards/${rewardId}/delete`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": currentUserId,
      },
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Не удалось удалить награду");
    }
    showToast("Награда удалена");
    loadRewards();
    loadTeacherData();
  } catch (err) {
    showToast(err.message || "Ошибка удаления");
  }
}

async function handleAwardTeacherBadge() {
  const studentId = document.getElementById("teacher-award-student").value;
  if (!studentId) {
    showToast("Выберите ученика из списка");
    return;
  }

  try {
    const res = await fetch("/api/teacher/award-badge", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": currentUserId,
      },
      body: JSON.stringify({
        student_id: studentId,
        badge_code: "teacher_choice",
        chat_id: selectedChatId !== "all" ? selectedChatId : null,
      })
    });

    if (!res.ok) throw new Error("Ошибка награждения");
    showToast("Бейдж «Выбор учителя» успешно вручён!");
    loadTeacherData();

  } catch (err) {
    showToast("Не удалось вручить награду");
  }
}

function showToast(text) {
  const toast = document.getElementById("toast");
  toast.textContent = text;
  toast.classList.remove("hidden");
  clearTimeout(window.__toastTimeout);
  window.__toastTimeout = setTimeout(() => {
    toast.classList.add("hidden");
  }, 2600);
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
