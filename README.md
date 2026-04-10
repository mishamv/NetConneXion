# NetConneXion

Современное приложение для Windows для управления сетевыми профилями и Wi-Fi подключениями, построенное на PySide6 / Qt6.

![Platform](https://img.shields.io/badge/платформа-Windows-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![UI](https://img.shields.io/badge/UI-PySide6%20%2F%20Qt6-green)

[English](README.en.md)

---

## Возможности

### Сетевые профили
- Создание, редактирование и удаление профилей IP-конфигурации (IP-адрес, маска подсети, шлюз, DNS)
- Применение любого профиля одним кликом через `netsh`
- Импорт и экспорт профилей в формате JSON

### Wi-Fi менеджер
- Сканирование и отображение доступных сетей (SSID, сигнал, защита, канал, диапазон, скорость)
- Подключение к сохранённым и новым сетям; пароли хранятся зашифрованными через Windows DPAPI
- Просмотр и управление сохранёнными Wi-Fi профилями

### Сетевые инструменты
| Инструмент | Описание |
|------------|----------|
| Ping | ICMP-пинг со статистикой |
| DNS Lookup | Прямое / обратное разрешение DNS |
| Сканер портов | Одиночные порты, список через запятую или диапазон (например `22,80,443,8000-8100`) |
| Traceroute | Трассировка маршрута |
| Netstat | Таблица активных соединений (Протокол / Локальный / Удалённый / Состояние / PID) |
| ARP таблица | Кэш ARP с маппингом IP → MAC |
| HTTP Check | Время ответа и статус HTTP/HTTPS |
| SSL сертификат | Детали TLS-сертификата (субъект, издатель, срок действия, SAN, шифр) |
| Таблица маршрутов | Таблица маршрутизации Windows через PowerShell `Get-NetRoute` |
| Wi-Fi Signal Monitor | График уровня сигнала в реальном времени (dBm / качество), лог событий роуминга |

### История
- Полный журнал применения профилей с временными метками и состоянием до/после
- Откат к любой предыдущей конфигурации одним кликом

### Настройки
- Светлая / тёмная тема
- Выбор языка (Русский / English)
- Сворачивание в трей, запуск свёрнутым
- Настройка автоматического сканирования Wi-Fi

---

## Требования

- Windows 10 / 11
- Python 3.10+
- Права администратора (требуются для команд `netsh`)

```
PySide6 >= 6.5
pywin32 >= 306   # Шифрование паролей через Windows DPAPI (рекомендуется)
```

---

## Установка

```bash
git clone https://github.com/mishamv/NetConneXion.git
cd NetConneXion
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Опционально: шифрование паролей через DPAPI
python -m pip install pywin32
python .venv\Scripts\pywin32_postinstall.py -install
```

---

## Запуск

```bash
# Запуск от имени администратора для полного доступа к netsh
python -m quickip
```

Или через проводник: правая кнопка мыши → «Запуск от имени администратора».

---

## Структура проекта

```
quickip/
  app/              # Bootstrap, DI-контейнер, точка входа
  domain/           # Доменные модели и сервисы
  events/           # Шина событий
  features/         # Модули функций (profiles, wifi, tools, history, settings)
  ui_qt/            # Слой UI на PySide6
    pages/          # Страницы (profiles, wifi, tools, settings)
    qss/            # Стили Qt (dark / light)
    assets/         # Иконки и SVG
  core/             # Общая инфраструктура (process runner, security vault, paths)
data/               # Пользовательские данные (в .gitignore): профили, настройки, история, логи
```

---

## Безопасность

- Пароли Wi-Fi хранятся зашифрованными с помощью **Windows DPAPI** (привязка к машине и пользователю) через `pywin32`
- Пароли расшифровываются только в оперативной памяти в момент подключения и никогда не записываются на диск в открытом виде
- Если `pywin32` недоступен, приложение использует существующие профили WLAN из Windows

---

## Сборка

```bash
pip install pyinstaller
pyinstaller --noconfirm --windowed --onefile ^
  --name NetConneXion ^
  --add-data "quickip;quickip" ^
  --add-data "data/locales;data/locales" ^
  -m quickip
```

После сборки можно запустить Inno Setup на сгенерированном spec-файле для создания установщика Windows.
