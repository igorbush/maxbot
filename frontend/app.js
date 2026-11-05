let currentUserId = 1001;
let currentUserData = null;

document.addEventListener("DOMContentLoaded", () => {
  initUserFromMAX();
  loadProfile();
});

function initUserFromMAX() {
  const urlParams = new URLSearchParams(window.location.search);
  const urlUserId = urlParams.get("user_id");

  if (window.WebApp && window.WebApp.initDataUnsafe && window.WebApp.initDataUnsafe.user) {
    currentUserId = window.WebApp.initDataUnsafe.user.id;
    const demoBar = document.getElementById("demo-bar");
    if (demoBar) demoBar.style.display = "none";
  } else if (urlUserId) {
    currentUserId = parseInt(urlUserId);
    const demoSelect = document.getElementById("demo-user-select");
    if (demoSelect) demoSelect.value = currentUserId;
  }
}

function switchDemoUser(newUserId) {
  currentUserId = parseInt(newUserId);
  showToast("Переключен пользователь: ID " + currentUserId);
  loadProfile();
}

async function loadProfile() {
  try {
    const res = await fetch(`/api/profile?user_id=${currentUserId}`);
    if (!res.ok) throw new Error("Ошибка загрузки профиля");
    const data = await res.json();
    currentUserData = data;

    document.getElementById("header-name").textContent = data.name;
    document.getElementById("header-role").textContent = data.role === "teacher" ? "Учитель 🎓" : "Школьник";
    document.getElementById("header-coins").textContent = data.coins;
    document.getElementById("header-avatar").textContent = data.role === "teacher" ? "👩‍🏫" : "🎒";

    document.getElementById("profile-level-title").textContent = data.level.title;
    document.getElementById("profile-level-num").textContent = `${data.level.level} ур.`;
    document.getElementById("profile-xp-text").textContent = `${data.level.current_xp} / ${data.level.next_xp} XP`;
    document.getElementById("profile-xp-fill").style.width = `${data.level.progress_percent}%`;

    document.getElementById("profile-helped").textContent = data.helped_count;
    document.getElementById("profile-questions").textContent = data.questions_count;
    document.getElementById("profile-rank").textContent = `#${data.rank}`;

    const shopCoins = document.getElementById("shop-coins");
    if (shopCoins) shopCoins.textContent = data.coins;

    const teacherNavBtn = document.getElementById("nav-teacher-btn");
    if (teacherNavBtn) {
      teacherNavBtn.style.display = data.role === "teacher" ? "flex" : "none";
    }

  } catch (err) {
    console.error(err);
    showToast("Не удалось загрузить данные профиля");
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

async function loadLeaderboard() {
  const container = document.getElementById("leaderboard-container");
  container.innerHTML = '<div class="loading-spinner">Загрузка рейтинга...</div>';

  try {
    const res = await fetch("/api/leaderboard");
    const leaders = await res.json();

    if (!leaders.length) {
      container.innerHTML = '<p class="empty-hint">Пока нет участников в рейтинге.</p>';
      return;
    }

    container.innerHTML = leaders.map((item, idx) => {
      let rankIcon = `#${item.rank}`;
      let rankClass = "";
      if (item.rank === 1) { rankIcon = "🥇"; rankClass = "rank-1"; }
      if (item.rank === 2) { rankIcon = "🥈"; rankClass = "rank-2"; }
      if (item.rank === 3) { rankIcon = "🥉"; rankClass = "rank-3"; }

      const isCurrent = item.max_user_id === currentUserId;

      return `
        <div class="leader-item ${isCurrent ? 'current-user' : ''}">
          <div class="leader-rank ${rankClass}">${rankIcon}</div>
          <div class="leader-info">
            <div class="leader-name">${item.name} ${isCurrent ? '(Вы)' : ''}</div>
            <div class="leader-sub">${item.level_title} • ${item.helped_count} раз(а) помог</div>
          </div>
          <div class="leader-xp">${item.xp} XP</div>
        </div>
      `;
    }).join("");

  } catch (err) {
    container.innerHTML = '<p class="empty-hint">Ошибка загрузки рейтинга.</p>';
  }
}

async function loadAchievements() {
  const container = document.getElementById("achievements-container");
  container.innerHTML = '<div class="loading-spinner">Загрузка достижений...</div>';

  try {
    const res = await fetch(`/api/achievements?user_id=${currentUserId}`);
    const achievements = await res.json();

    container.innerHTML = achievements.map(ach => {
      const isUnlocked = ach.is_unlocked;
      return `
        <div class="ach-card ${isUnlocked ? 'unlocked' : 'locked'}">
          <span class="ach-icon">${ach.icon}</span>
          <div class="ach-title">${ach.title}</div>
          <div class="ach-desc">${ach.description}</div>
          <div class="ach-reward-tag">+${ach.xp_reward} XP • +${ach.coins_reward} 🪙</div>
          ${isUnlocked ? `<div class="ach-date">Открыто ${ach.unlocked_at}</div>` : '<div class="ach-date" style="color:#718096;">🔒 Заблокировано</div>'}
        </div>
      `;
    }).join("");

  } catch (err) {
    container.innerHTML = '<p class="empty-hint">Ошибка загрузки достижений.</p>';
  }
}

async function loadRewards() {
  const grid = document.getElementById("rewards-container");
  const requestsList = document.getElementById("my-requests-list");
  grid.innerHTML = '<div class="loading-spinner">Загрузка лавки...</div>';

  try {
    const res = await fetch(`/api/rewards?user_id=${currentUserId}`);
    const data = await res.json();

    document.getElementById("shop-coins").textContent = data.user_coins;

    if (!data.rewards.length) {
      grid.innerHTML = '<p class="empty-hint">Учитель пока не добавил награды.</p>';
    } else {
      grid.innerHTML = data.rewards.map(rew => {
        const canAfford = data.user_coins >= rew.price_coins;
        return `
          <div class="reward-card">
            <div class="reward-icon-box">${rew.icon}</div>
            <div class="reward-details">
              <div class="reward-title">${rew.title}</div>
              <div class="reward-desc">${rew.description}</div>
            </div>
            <button
              class="btn-buy"
              ${canAfford ? '' : 'disabled'}
              onclick="handleBuyReward(${rew.id})"
            >
              ${rew.price_coins} 🪙
            </button>
          </div>
        `;
      }).join("");
    }

    if (!data.my_requests.length) {
      requestsList.innerHTML = '<p class="empty-hint">У вас пока нет активных запросов.</p>';
    } else {
      requestsList.innerHTML = data.my_requests.map(req => {
        let statusText = "⏳ На рассмотрении";
        let statusClass = "status-pending";
        if (req.status === "approved") { statusText = "✅ Одобрено"; statusClass = "status-approved"; }
        if (req.status === "rejected") { statusText = "❌ Отклонено"; statusClass = "status-rejected"; }

        return `
          <div class="req-item">
            <div>
              <strong>${req.reward_icon} ${req.reward_title}</strong>
              <div style="font-size: 11px; color: var(--text-muted);">${req.created_at}</div>
            </div>
            <span class="status-badge ${statusClass}">${statusText}</span>
          </div>
        `;
      }).join("");
    }

  } catch (err) {
    grid.innerHTML = '<p class="empty-hint">Ошибка загрузки наград.</p>';
  }
}

async function handleBuyReward(rewardId) {
  try {
    const res = await fetch("/api/rewards/buy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: currentUserId,
        reward_id: rewardId
      })
    });
    const result = await res.json();
    if (result.success) {
      showToast(result.message);
      loadProfile();
      loadRewards();
    } else {
      showToast(result.error || "Не удалось купить награду");
    }
  } catch (err) {
    showToast("Ошибка при отправке запроса");
  }
}

async function loadTeacherData() {
  const reqList = document.getElementById("teacher-requests-list");
  reqList.innerHTML = '<div class="loading-spinner">Загрузка заявок...</div>';

  try {
    const res = await fetch(`/api/teacher/requests?teacher_id=${currentUserId}`);
    const requests = await res.json();

    if (!requests.length) {
      reqList.innerHTML = '<p class="empty-hint">Нет ожидающих заявок от учеников.</p>';
    } else {
      reqList.innerHTML = requests.map(req => `
        <div class="teacher-req-item">
          <div class="teacher-req-header">
            <strong>${req.student_name}</strong>
            <span style="color: var(--gold);">${req.price_coins} 🪙</span>
          </div>
          <div style="font-size: 13px;">Запрос: ${req.reward_icon} ${req.reward_title}</div>
          <div style="font-size: 11px; color: var(--text-muted);">${req.created_at}</div>
          <div class="teacher-req-actions">
            <button class="btn btn-green flex-1" onclick="handleReviewRequest(${req.id}, 'approve')">Одобрить ✅</button>
            <button class="btn btn-red flex-1" onclick="handleReviewRequest(${req.id}, 'reject')">Отклонить ❌</button>
          </div>
        </div>
      `).join("");
    }

    const usersRes = await fetch("/api/demo/users");
    const allUsers = await usersRes.json();
    const studentSelect = document.getElementById("teacher-award-student");
    const students = allUsers.filter(u => u.role === "student");

    studentSelect.innerHTML = '<option value="">Выберите ученика...</option>' +
      students.map(s => `<option value="${s.max_user_id}">${s.name} (${s.xp} XP)</option>`).join("");

  } catch (err) {
    reqList.innerHTML = '<p class="empty-hint">Ошибка доступа к учительской панели.</p>';
  }
}

async function handleReviewRequest(requestId, action) {
  try {
    const res = await fetch("/api/teacher/request/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        teacher_id: currentUserId,
        request_id: requestId,
        action: action
      })
    });
    const result = await res.json();
    showToast(result.message);
    loadTeacherData();
    loadProfile();
  } catch (err) {
    showToast("Ошибка при рассмотрении заявки");
  }
}

async function handleCreateReward(event) {
  event.preventDefault();
  const title = document.getElementById("rew-title").value.trim();
  const desc = document.getElementById("rew-desc").value.trim();
  const price = parseInt(document.getElementById("rew-price").value);
  const icon = document.getElementById("rew-icon").value;

  try {
    const res = await fetch("/api/teacher/reward/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        teacher_id: currentUserId,
        title: title,
        description: desc,
        price_coins: price,
        icon: icon
      })
    });
    const result = await res.json();
    showToast(result.message);
    document.getElementById("create-reward-form").reset();
  } catch (err) {
    showToast("Ошибка при создании награды");
  }
}

async function handleAwardTeacherBadge() {
  const select = document.getElementById("teacher-award-student");
  const studentId = select.value;
  if (!studentId) {
    showToast("Пожалуйста, выберите ученика!");
    return;
  }

  try {
    const res = await fetch("/api/teacher/award_badge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        teacher_id: currentUserId,
        student_id: parseInt(studentId)
      })
    });
    const result = await res.json();
    showToast(result.message);
    loadTeacherData();
  } catch (err) {
    showToast("Ошибка при вручении награды");
  }
}

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  setTimeout(() => {
    toast.classList.add("hidden");
  }, 3200);
}
