let currentUserId = "1001";
let currentUserData = null;
let currentLeaderboardPeriod = "all_time";

document.addEventListener("DOMContentLoaded", () => {
  initUserFromMAX();
  loadProfile();
});

function initUserFromMAX() {
  const urlParams = new URLSearchParams(window.location.search);
  const urlUserId = urlParams.get("user_id");

  if (window.WebApp && window.WebApp.initDataUnsafe && window.WebApp.initDataUnsafe.user) {
    currentUserId = String(window.WebApp.initDataUnsafe.user.id);
    const demoBar = document.getElementById("demo-bar");
    if (demoBar) demoBar.style.display = "none";
  } else if (urlUserId) {
    currentUserId = String(urlUserId);
    const demoSelect = document.getElementById("demo-user-select");
    if (demoSelect) demoSelect.value = currentUserId;
  }
}

function switchDemoUser(newUserId) {
  currentUserId = String(newUserId);
  showToast("Выбран профиль: " + currentUserId);
  loadProfile();
  const activeTab = document.querySelector(".tab-pane.active");
  if (activeTab) {
    const tabId = activeTab.id.replace("tab-", "");
    if (tabId === "leaderboard") loadLeaderboard();
    if (tabId === "achievements") loadAchievements();
    if (tabId === "rewards") loadRewards();
    if (tabId === "teacher") loadTeacherData();
  }
}

async function loadProfile() {
  try {
    const res = await fetch(`/api/profile?user_id=${currentUserId}`);
    if (!res.ok) throw new Error("Profile error");
    const data = await res.json();
    currentUserData = data;

    document.getElementById("header-name").textContent = data.display_name;
    document.getElementById("header-role").textContent = data.role === "teacher" ? "Учитель 🎓" : "Школьник";
    document.getElementById("header-coins").textContent = data.balance_spasibki;
    document.getElementById("header-avatar").textContent = data.role === "teacher" ? "👩‍🏫" : "🎒";

    document.getElementById("profile-level-title").textContent = data.rank;
    document.getElementById("profile-level-num").textContent = `${data.level} ур.`;
    
    const xpInLevel = data.xp % 100;
    document.getElementById("profile-xp-text").textContent = `${xpInLevel} / 100 XP (${data.xp} всего)`;
    document.getElementById("profile-xp-fill").style.width = `${Math.min(100, xpInLevel)}%`;

    document.getElementById("profile-helped").textContent = data.helped_count || 0;
    document.getElementById("profile-questions").textContent = data.questions_count || 0;
    document.getElementById("profile-rank").textContent = `#${data.rank_position || 1}`;

    const shopCoins = document.getElementById("shop-coins");
    if (shopCoins) shopCoins.textContent = data.balance_spasibki;

    const teacherNavBtn = document.getElementById("nav-teacher-btn");
    if (teacherNavBtn) {
      teacherNavBtn.style.display = (data.role === "teacher" || data.role === "admin" || currentUserId === "9999" || currentUserId === "teacher_1") ? "flex" : "none";
    }

  } catch (err) {
    showToast("Ошибка загрузки профиля");
  }
}

function switchTab(tabName, btnElement) {
  document.querySelectorAll(".tab-pane").forEach(pane => pane.classList.remove("active"));
  const target = document.getElementById(`tab-${tabName}`);
  if (target) target.classList.add("active");

  document.querySelectorAll(".nav-item").forEach(item => item.classList.remove("active"));
  if (btnElement) btnElement.classList.add("active");

  if (tabName === "profile") loadProfile();
  if (tabName === "leaderboard") loadLeaderboard();
  if (tabName === "achievements") loadAchievements();
  if (tabName === "rewards") loadRewards();
  if (tabName === "teacher") loadTeacherData();
}

function changeLeaderboardPeriod(period) {
  currentLeaderboardPeriod = period;
  document.getElementById("btn-period-all").classList.toggle("active", period === "all_time");
  document.getElementById("btn-period-week").classList.toggle("active", period === "weekly");
  loadLeaderboard();
}

async function loadLeaderboard() {
  const container = document.getElementById("leaderboard-container");
  container.innerHTML = '<div class="loading-spinner">Загрузка рейтинга...</div>';

  try {
    const res = await fetch(`/api/leaderboard?period=${currentLeaderboardPeriod}`);
    const data = await res.json();
    const leaders = data.items || [];

    if (!leaders.length) {
      container.innerHTML = '<p class="empty-hint">Пока нет участников в рейтинге.</p>';
      return;
    }

    container.innerHTML = leaders.map(item => {
      let rankIcon = `#${item.rank_position}`;
      let rankClass = "";
      if (item.rank_position === 1) { rankIcon = "🥇"; rankClass = "rank-1"; }
      if (item.rank_position === 2) { rankIcon = "🥈"; rankClass = "rank-2"; }
      if (item.rank_position === 3) { rankIcon = "🥉"; rankClass = "rank-3"; }

      const isCurrent = String(item.max_user_id) === String(currentUserId);

      return `
        <div class="leader-item ${isCurrent ? 'current-user' : ''}">
          <div class="leader-rank ${rankClass}">${rankIcon}</div>
          <div class="leader-avatar">🎒</div>
          <div class="leader-info">
            <div class="leader-name">${escapeHtml(item.display_name)}</div>
            <div class="leader-sub">${escapeHtml(item.rank)}</div>
          </div>
          <div class="leader-score">
            <div class="leader-xp">${item.xp} XP</div>
            <div class="leader-coins">🪙 ${item.balance_spasibki}</div>
          </div>
        </div>
      `;
    }).join("");

  } catch (err) {
    container.innerHTML = '<p class="empty-hint">Не удалось загрузить рейтинг</p>';
  }
}

async function loadAchievements() {
  const container = document.getElementById("achievements-container");
  container.innerHTML = '<div class="loading-spinner">Загрузка достижений...</div>';

  try {
    const res = await fetch(`/api/achievements?user_id=${currentUserId}`);
    const achievements = await res.json();

    if (!achievements.length) {
      container.innerHTML = '<p class="empty-hint">Достижения не найдены.</p>';
      return;
    }

    container.innerHTML = achievements.map(ach => {
      const isUnlocked = ach.unlocked;
      const icon = ach.icon_url || "🎖";
      let dateStr = "";
      if (isUnlocked && ach.awarded_at) {
        const d = new Date(ach.awarded_at);
        dateStr = `<span class="ach-badge">Получено ${d.toLocaleDateString('ru-RU')}</span>`;
      } else if (isUnlocked) {
        dateStr = `<span class="ach-badge">Получено</span>`;
      }

      return `
        <div class="ach-card ${isUnlocked ? 'unlocked' : 'locked'}">
          <div class="ach-icon">${icon}</div>
          <div class="ach-name">${escapeHtml(ach.name_ru)}</div>
          <div class="ach-desc">${escapeHtml(ach.description_ru)}</div>
          ${dateStr}
        </div>
      `;
    }).join("");

  } catch (err) {
    container.innerHTML = '<p class="empty-hint">Не удалось загрузить достижения</p>';
  }
}

async function loadRewards() {
  const container = document.getElementById("rewards-container");
  container.innerHTML = '<div class="loading-spinner">Загрузка витрины...</div>';

  try {
    const res = await fetch("/api/rewards");
    const rewards = await res.json();

    if (!rewards.length) {
      container.innerHTML = '<p class="empty-hint">В лавке пока нет наград.</p>';
    } else {
      container.innerHTML = rewards.map(r => `
        <div class="reward-card">
          <div class="reward-icon">🎁</div>
          <div class="reward-info">
            <div class="reward-title">${escapeHtml(r.title)}</div>
            <div class="reward-desc">${escapeHtml(r.description)}</div>
            <div class="reward-price">🪙 ${r.cost_spasibki} спасибок</div>
          </div>
          <div class="reward-action">
            <button class="btn btn-primary btn-sm" onclick="handleClaimReward(${r.id}, ${r.cost_spasibki})">Обменять</button>
          </div>
        </div>
      `).join("");
    }

    loadMyClaims();

  } catch (err) {
    container.innerHTML = '<p class="empty-hint">Не удалось загрузить витрину наград</p>';
  }
}

async function loadMyClaims() {
  const container = document.getElementById("my-requests-list");
  try {
    const res = await fetch(`/api/my-claims?user_id=${currentUserId}`);
    const claims = await res.json();

    if (!claims.length) {
      container.innerHTML = '<p class="empty-hint">У вас пока нет активных запросов.</p>';
      return;
    }

    container.innerHTML = claims.map(c => {
      let statusText = "На рассмотрении";
      let statusClass = "status-requested";
      if (c.status === "approved") {
        statusText = "Одобрено учительницей ✅";
        statusClass = "status-approved";
      } else if (c.status === "rejected") {
        statusText = "Отклонено";
        statusClass = "status-rejected";
      }

      return `
        <div class="request-item">
          <div>
            <strong>${escapeHtml(c.title)}</strong>
            <div class="leader-sub">🪙 ${c.cost_spasibki} спасибок</div>
          </div>
          <span class="req-status ${statusClass}">${statusText}</span>
        </div>
      `;
    }).join("");

  } catch (err) {
    container.innerHTML = '<p class="empty-hint">Не удалось загрузить историю запросов</p>';
  }
}

async function handleClaimReward(rewardId, cost) {
  if (currentUserData && currentUserData.balance_spasibki < cost) {
    showToast(`Недостаточно спасибок! Нужно ${cost}, у вас ${currentUserData.balance_spasibki}`);
    return;
  }

  try {
    const res = await fetch("/api/rewards/claim", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": currentUserId,
      },
      body: JSON.stringify({ reward_id: rewardId, user_id: currentUserId })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Ошибка обмена");
    }

    showToast("Запрос отправлен учителю!");
    loadProfile();
    loadRewards();

  } catch (err) {
    showToast(err.message || "Ошибка при обмене награды");
  }
}

async function loadTeacherData() {
  const listContainer = document.getElementById("teacher-requests-list");
  listContainer.innerHTML = '<div class="loading-spinner">Загрузка заявок...</div>';

  try {
    const res = await fetch(`/api/teacher/overview?user_id=${currentUserId}`);
    if (!res.ok) throw new Error("Доступ только для учителей");
    const overview = await res.json();

    const claims = overview.pending_claims || [];
    if (!claims.length) {
      listContainer.innerHTML = '<p class="empty-hint">Нет новых заявок на рассмотрение.</p>';
    } else {
      listContainer.innerHTML = claims.map(c => `
        <div class="teacher-claim-item">
          <div class="teacher-claim-header">
            <strong>${escapeHtml(c.student_name)} (${c.student_max_id})</strong>
            <span>🪙 ${c.cost_spasibki}</span>
          </div>
          <div class="reward-desc">Запрос награды: «${escapeHtml(c.reward_title)}»</div>
          <div class="teacher-claim-actions">
            <button class="btn btn-primary btn-sm flex-1" onclick="handleReviewClaim(${c.claim_id}, 'approved')">Одобрить</button>
            <button class="btn btn-outline btn-sm flex-1" onclick="handleReviewClaim(${c.claim_id}, 'rejected')">Отклонить</button>
          </div>
        </div>
      `).join("");
    }

    loadStudentsDropdown();

  } catch (err) {
    listContainer.innerHTML = '<p class="empty-hint">Панель доступна только с аккаунта учителя.</p>';
  }
}

async function loadStudentsDropdown() {
  const selectElem = document.getElementById("teacher-award-student");
  try {
    const res = await fetch("/api/students");
    const students = await res.json();
    selectElem.innerHTML = '<option value="">Выберите ученика...</option>' +
      students.map(s => `<option value="${s.max_user_id}">${escapeHtml(s.display_name)} (${s.xp} XP, 🪙 ${s.balance_spasibki})</option>`).join("");
  } catch (err) {
    selectElem.innerHTML = '<option value="">Ошибка загрузки списка</option>';
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

    if (!res.ok) throw new Error("Ошибка обновления статуса");
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
      body: JSON.stringify({ title: title, description: desc, cost_spasibki: price })
    });

    if (!res.ok) throw new Error("Ошибка создания");
    showToast("Награда добавлена в лавку!");
    document.getElementById("create-reward-form").reset();
    document.getElementById("rew-price").value = 30;

  } catch (err) {
    showToast("Не удалось создать награду");
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
      body: JSON.stringify({ student_id: studentId, badge_code: "teacher_choice" })
    });

    if (!res.ok) throw new Error("Ошибка");
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
