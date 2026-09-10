# Расписание МГУ — запуск на сервере

Минимальный production-комплект Telegram-бота. Требуется Python 3.12 или новее.

## Загрузка из GitHub

```bash
git clone АДРЕС_РЕПОЗИТОРИЯ
cd ИМЯ_РЕПОЗИТОРИЯ
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
nano .env
```

В `.env` укажите токен:

```dotenv
BOT_TOKEN=токен_от_BotFather
CACHE_ENABLED=true
```

Файл `.env` исключён из Git. Не публикуйте его и не добавляйте токен в исходный код.

Проверка живого сайта МГУ без запуска Telegram:

```bash
.venv/bin/python -m app.smoke
```

Разовый запуск бота:

```bash
.venv/bin/python main.py
```

## Постоянный запуск на Ubuntu/Debian

Откройте `deploy/raspisanie-bot.service.example`, замените `YOUR_USER` и `/opt/raspisanie` на пользователя и абсолютный путь проекта. Затем:

```bash
sudo cp deploy/raspisanie-bot.service.example /etc/systemd/system/raspisanie-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now raspisanie-bot
sudo systemctl status raspisanie-bot
```

Просмотр логов:

```bash
journalctl -u raspisanie-bot -f
```

После обновления из GitHub:

```bash
git pull
.venv/bin/python -m pip install -r requirements.txt
sudo systemctl restart raspisanie-bot
```

Запускайте только один экземпляр бота на один Telegram-токен.
