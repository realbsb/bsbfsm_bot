# Развёртывание

## Предварительные требования

- 6-ядерный процессор, 6ГБ RAM, 150ГБ ОЗУ
- База данных установлена нативно
- Docker и docker-compose установлены
- Пользователь с sudo

## Шаг 1. Подготовка системы

sudo apt update
sudo apt install -y python3-pip python3-venv git poppler-utils tzdata
sudo timedatectl set-timezone Asia/Yekaterinburg

## Шаг 2. Установка БД
docker compose build
docker compose up -d mariadb redis
Дождаться, пока NCP поднимется, создать MariaDB и пользователя.

## Шаг 3. Создание схемы workflow
sudo mysql -u root
CREATE DATABASE workflow CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'workflow'@'%' IDENTIFIED BY 'сильный_пароль';
GRANT ALL PRIVILEGES ON workflow.* TO 'workflow'@'%';
FLUSH PRIVILEGES;
EXIT;

## Шаг 4. Клонирование и настройка
sudo mkdir -p /opt/workflow /var/lib/workflow
sudo chown -R $USER:$USER /opt/workflow /var/lib/workflow
cd /opt/workflow
git clone https://github.com/realbsb/workflowbot
cp .env.example .env
nano .env
Заполнить обязательные переменные: BOT_TOKEN, DB_PASSWORD, WEBAPP_SECRET, BOT_ADMIN_IDS.

## Шаг 5. Сборка и миграции
docker compose run --rm workflow-bot alembic upgrade head
docker compose run --rm workflow-bot python -m workflow.services.seed_cli

## Шаг 6. Запуск
docker compose up -d
docker compose logs -f --tail=100 workflow-bot

## Шаг 7. Обратный прокси
server {
    listen 443 ssl http2;
    server_name workflow.local;

    ssl_certificate /etc/letsencrypt/live/workflow.local/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/workflow.local/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
или Apache:
<VirtualHost *:443>
    ServerName workflow.example.com

    # TLS
    SSLEngine on
    SSLCertificateFile      /etc/letsencrypt/live/workflow.example.com/fullchain.pem
    SSLCertificateKeyFile   /etc/letsencrypt/live/workflow.example.com/privkey.pem

    # Прокси на workflow-webapp
    ProxyPreserveHost On
    ProxyRequests Off
    RequestHeader set X-Forwarded-Proto "https"

    <Location />
        ProxyPass http://127.0.0.1:8080/
        ProxyPassReverse http://127.0.0.1:8080/
    </Location>

    <Location /health>
        ProxyPass http://127.0.0.1:8080/health
        ProxyPassReverse http://127.0.0.1:8080/health
    </Location>

    ErrorLog  ${APACHE_LOG_DIR}/workflow-error.log
    CustomLog ${APACHE_LOG_DIR}/workflow-access.log combined
</VirtualHost>

<VirtualHost *:80>
    ServerName workflow.example.com
    Redirect permanent / https://workflow.example.com/
</VirtualHost>

## Шаг 8. Whisper
Убедиться, что ваш Whisper-контейнер работает и доступен по имени, указанному в WHISPER_CONTAINER.
docker ps | grep whisper

## Шаг 9. Radicale
[server]
hosts = 0.0.0.0:5232

[auth]
type = htpasswd
htpasswd_filename = /data/users
htpasswd_encryption = bcrypt

[storage]
filesystem_folder = /data/collections

mkdir -p /opt/workflow/radicale/data /opt/workflow/radicale/config
nano /opt/workflow/radicale/config/config
[server]
hosts = 0.0.0.0:5232

[auth]
type = htpasswd
htpasswd_filename = /data/users
htpasswd_encryption = bcrypt

[storage]
filesystem_folder = /data/collections

docker compose up -d workflow-radicale

Создать пользователей:
docker exec -it workflow-radicale htpasswd -B -c /data/users ivan
docker exec -it workflow-radicale htpasswd -B /data/users petr
docker restart workflow-radicale

## Шаг 10. Бэкап
sudo crontab -e
0 3 * * * /opt/workflow/scripts/backup.sh >> /var/log/workflow-backup.log 2>&1

## Шаг 11. Мониторинг
docker compose ps
docker compose logs --tail=50 workflow-worker

Health-check WebApp:
curl http://localhost:8080/health

## Бэкап
Обновление:
cd /opt/workflow
git pull
docker compose build
docker compose run --rm workflow-bot alembic upgrade head
docker compose up -d
docker compose logs -f --tail=100

Восстановление из бэкапа:
LATEST=$(ls -1dt /var/lib/workflow/backup/* | head -1)
gunzip < $LATEST/db.sql.gz | mysql -u workflow -p workflow
tar -xzf $LATEST/archive.tar.gz -C /var/lib/workflow/

## Если внешний Redis
sudo grep -E '^(port|bind|unixsocket|protected-mode|requirepass|maxmemory|maxmemory-policy)' /etc/redis/redis.conf
port 6379
bind 127.0.0.1 -::1
maxmemory 512mb
maxmemory-policy noeviction
appendonly yes
appendfsync everysec

sudo systemctl restart redis-server
redis-cli -h 127.0.0.1 -p 6379 ping