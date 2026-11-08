# Инструкция по развертыванию проекта «Лига Помощников»

Данное руководство содержит подробные шаги для полного развертывания чат-бота и веб-приложения (WebApp) «Лига Помощников» с нуля на чистом сервере (Ubuntu / Debian / любая Linux-система), а также инструкции по обновлению и мониторингу.

---

## 📋 Системные требования

* **ОС:** Ubuntu 22.04 LTS / 24.04 LTS или Debian 11/12 (рекомендуется)
* **Процессор:** от 1 vCPU
* **Оперативная память:** от 1 ГБ RAM
* **Дисковое пространство:** от 10 ГБ SSD
* **Программное обеспечение:** Docker (с поддержкой Docker Compose v2) или Python 3.11+
* **Сеть:** Публичный IP-адрес, открытые порты 80 (HTTP) и 443 (HTTPS)
* **Доменное имя:** Желательно наличие домена (например, `myschool-bot.ru`) для выпуска SSL-сертификата Let's Encrypt (для работы WebApp внутри MAX требуется HTTPS)
* **Токен бота MAX:** Токен, полученный от платформы мессенджера MAX

---

## 🚀 Вариант 1: Развертывание в Docker (Рекомендуемый)

### 1. Подключение к серверу и установка Docker

Подключитесь к вашему VPS по SSH:
```bash
ssh root@IP_ВАШЕГО_СЕРВЕРА
```

Обновите пакеты системы и установите Docker и Docker Compose:
```bash
apt update && apt upgrade -y
apt install -y curl git ufw nginx certbot python3-certbot-nginx

# Установка Docker через официальный скрипт
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
systemctl enable --now docker
```

---

### 2. Клонирование репозитория

```bash
cd ~
git clone https://github.com/igorbush/maxbot.git
cd maxbot
mkdir -p data
```

---

### 3. Настройка переменных окружения (`.env`)

Скопируйте пример файла конфигурации или создайте `.env`:
```bash
cp .env.example .env
nano .env
```

Заполните переменные конфигурации:
```env
# Токен бота, полученный на платформе MAX
MAX_BOT_TOKEN=ВАШ_ТОКЕН_БОТА_MAX

# Базовый URL API платформы MAX
MAX_API_BASE_URL=https://platform-api2.max.ru

# Проверка SSL для API MAX (при наличии корпоративных прокси можно установить false)
MAX_SSL_VERIFY=false

# Публичный HTTPS-адрес вашего веб-приложения (без слеша на конце)
WEBAPP_BASE_URL=https://ВАШ_ДОМЕН

# Подключение к базе данных (SQLite с асинхронным драйвером)
DATABASE_URL=sqlite+aiosqlite:///data/liga.db

# Настройки внутреннего веб-сервера
HOST=0.0.0.0
PORT=8000
```

> **Сохранение в nano:** нажмите `Ctrl + O`, затем `Enter`, затем `Ctrl + X` для выхода.

---

### 4. Настройка Nginx и выпуск бесплатного SSL-сертификата

Для открытия WebApp внутри мессенджера MAX обязателен протокол HTTPS.

#### А. Создание конфигурации Nginx
```bash
nano /etc/nginx/sites-available/default
```

Вставьте конфигурацию, заменив `ВАШ_ДОМЕН` на ваше доменное имя:
```nginx
server {
    listen 80;
    server_name ВАШ_ДОМЕН www.ВАШ_ДОМЕН;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Проверьте синтаксис и перезапустите Nginx:
```bash
nginx -t
systemctl reload nginx
```

#### Б. Выпуск SSL-сертификата Let's Encrypt
```bash
certbot --nginx -d ВАШ_ДОМЕН -d www.ВАШ_ДОМЕН --non-interactive --agree-tos -m admin@ВАШ_ДОМЕН --redirect
```

Certbot автоматически настроит защищённый редирект с HTTP на HTTPS и пропишет сертификаты в конфиг Nginx.

---

### 5. Сборка и запуск контейнера

```bash
cd ~/maxbot
docker compose up -d --build
```

Просмотр логов запущенного бота:
```bash
docker compose logs -f
```

При успешном запуске в логах появится:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
[БОТ] Бот успешно запущен и слушает события (Long Polling)...
```

---

## 🛠 Вариант 2: Локальное или прямое развертывание (без Docker)

Если вы запускаете проект без Docker:

1. Убедитесь, что установлен Python 3.11+:
```bash
python3 --version
apt install -y python3-pip python3-venv
```

2. Создайте и активируйте виртуальное окружение:
```bash
cd ~/maxbot
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

3. Подготовьте `.env` (как описано выше).

4. Запустите приложение:
```bash
python3 main.py
```

### Настройка автозапуска через systemd (для Варианта 2)
Создайте юнит:
```bash
nano /etc/systemd/system/maxbot.service
```

```ini
[Unit]
Description=Liga Pomoshnikov MAX Bot Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/maxbot
ExecStart=/root/maxbot/venv/bin/python main.py
Restart=always
RestartSec=5
EnvironmentFile=/root/maxbot/.env

[Install]
WantedBy=multi-user.target
```

Включите и запустите сервис:
```bash
systemctl daemon-reload
systemctl enable --now maxbot
systemctl status maxbot
```

---

## 🔄 Обновление проекта на сервере

В проекте настроен удобный скрипт автоматического обновления `update.sh`.

Для применения свежих изменений из репозитория выполните одну команду:
```bash
cd ~/maxbot && bash update.sh
```

Скрипт автоматически:
1. Загружает последние коммиты без конфликтов (`git fetch` + `git reset --hard origin/main`).
2. Сохраняет файл `.env` и данные базы в `data/`.
3. Пересобирает контейнер с флагом `--no-cache`.
4. Перезапускает сервис и выводит свежие логи.

---

## 🩺 Проверка работоспособности (Health Check)

1. **Проверка бэкенда:**
   Откройте в браузере или через curl:
   ```bash
   curl -I https://ВАШ_ДОМЕН/health
   # Должен вернуть HTTP/1.1 200 OK
   ```

2. **Проверка WebApp:**
   Перейдите по адресу `https://ВАШ_ДОМЕН/` — откроется интерфейс «Лиги Помощников» в светлой дизайн-системе Сферум.

3. **Проверка бота в MAX:**
   * Откройте бота в мессенджере MAX.
   * Нажмите «Запустить» или отправьте `/start`.
   * Бот мгновенно пришлет приветственное сообщение с инлайн-клавиатурой `[ ❓ Как спросить? ]`, `[ 👤 Мой профиль ]` и `[ 🪙 Баланс спасибок ]`.
