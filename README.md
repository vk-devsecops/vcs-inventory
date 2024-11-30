# vcs-inventory

В проекте реализована инвентаризация систем контроля версий для целей DevSecOps.

Распространяется на правах дополнительных материалов доклада "[Инвентаризируй это: строим автоматический DevSecOps для 40 тысяч репозиториев](https://highload.ru/moscow/2024/abstracts/13494)" на конференции HighLoad++ 2024.

## Модуль инвентаризации
В файле `inventory.py` содержится исходный код модуля инвентаризации, осуществляющий заполнение БД информацией о репозиториях, группах, пользователях и их коммитах.

Поддерживается два варианта запуска: [локальный запуск](#локальный-запуск) и [запуск при помощи Docker-compose](#docker-compose).

## Локальный запуск
Для локального запуска процесса потребуется Python версии 3.11+, а также [virtualenv](https://virtualenv.pypa.io/en/latest/installation.html).

Для начала инвентаризации необходимо выполнить следующие команды:

```bash
$ virtualenv -p python3.11 venv
$ source venv/bin/activate
$ pip install -r requirements.txt
$ DEBUG_ENABLED=True DRY_RUN=True python3 inventory.py
```

После запуска, начнётся процесс инвентаризации всех перечисленных в файле `vcs-instances.yaml` инстансов VCS, с сохранением данных в локальную базу `sqlite3.db`, поскольку указан флаг `DRY_RUN`.
Будьте внимательны: поскольку переменная `DRY_RUN` установлена в `True`, инвентаризация окончится после прохождения 100 групп/репозиториев.

## Docker-compose
Для запуска инвентаризации в контейнеризованной среде, необходимо заполнить файл `.env` по образцу `.env.example`:
```bash
$ cp .env.example .env
$ vi .env
```
Используемые переменные среды описаны в разделе ["Переменные среды"](#переменные-среды).

После заполнения, необходимо выполнить команду:
```bash
$ docker-compose build && docker-compose up -d
```

В результате выполнения данной команды будет запущено три контейнера: контейнер vcs-inventory, который начнём инвентаризацию всех VCS, описанных в файле `vcs-instances.yaml`, контейнер с БД PostgreSQL, и контейнер с веб-интерфейсом [pgAdmin](https://www.pgadmin.org/), доступный по адресу `localhost:5050` (учётные данные необходимо указать в переменных `PGADMIN_DEFAULT_EMAIL` и `PGADMIN_PASSWORD` файла `.env`), в котором будет заранее добавлена БД inventory, в которой начнут появлятся данные, полученные в результате инвентаризации.

Будьте внимательны: по умолчанию, в файле `.env.example` переменная `DRY_RUN` установлена в `True`, поэтому инвентаризация окончится после прохождения 100 групп/репозиториев, и контейнер завершится с кодом возврата 0.


## Конфигурация

Для конфигурации перечня инвентаризируемых VCS, необходимо заполнить yaml-файл `vcs-instances.yaml`, перечислив в нём все инстансы, их тип (`TYPE`), адрес (`URL`), имя (`USERNAME`) и аутентификационный токен (`PAT`) учётной записи, от имени которой проводится инвентаризация. Инструкции по получению аутентификационного токена: [Bitbucket](https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html), [Gitlab](https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html).

Пример конфигурационного файла находится в `settings.yaml.example`.

### Переменные среды
Конфигурация переменных среды возможна как вручную, так и при заполнении файла `.env`. Пример файла с переменными среды находится в `.env.example`.

При помощи переменных среды можно конфигурировать следующие параметры инвентаризации:
- `START_TIME` – время начала ежедневной инвентаризации в формате `HH:MM`, например, `22:00`;
- `LOG_LEVEL` (`DEBUG`/`INFO`/`ERROR`/`CRITICAL`) – минимальный уровень, при котором сообщение будет выведено в лог-файл. По умолчанию, имеет значение `INFO`;
- `DEBUG_ENABLED` (`True`/`False`) – режим отладки, при котором в качестве БД будет использована локальная БД sqlite3 (файл `sqlite3.db`, создаваемый в корневой директории проекта в момент запуска);
- `DRY_RUN` (`True`/`False`) – режим тестирования, при котором инвентаризация запустится в момент запуска модуля, а не по расписанию, указанному в `START_TIME`, и
будет остановлена после прохода 100 репозиториев. Полезно для проверки корректности конфигурации модуля и первичного наполнения БД;
- `DEBUG_LAST_ID` – максимальный ID репозитория в инстансе на текущий момент. Используется для переопределения механизма get_last_project_id() в процессе отладки механизма "быстрой" инвентаризации;
- `ENVIRONMENT` (`DEV`/`STAGE`/`PROD`) – среда, в которой запущен процесс инвентаризации. По умолчанию имеет значение `DEV`. Влияет на формат логирования – в средах `STAGE` и `PROD` логирование осуществляется в JSON-формате, совместимом с ELK;
- `FAST_INVENTORY_INTERVAL` – промежуток между запуском "быстрой" инвентаризации в минутах, например, `15`;
- `FULL_UPDATE_DAY` – числовое обозначение дня, в который будет произведена полная инвентаризации (обновление всей существующей в БД информации), например, для субботы это `6`;
- `INSERT_CHUNK_SIZE` – ограничение на максимальное количество вставляемых / обновляемых в БД объектов. Необходимо для предотвращения повышенной нагрузки и отказа БД. По умолчанию, установлено в `50000`;
- `PROCESS_PROJECTS` (`True`/`False`) – используется для включения / отключения функционала инвентаризации проектов (репозиториев);
- `PROCESS_GROUPS` (`True`/`False`) – используется для включения / отключения функционала инвентаризации групп;
- `PROCESS_REGISTRIES` (`True`/`False`) – используется для включения / отключения функционала инвентаризации Docker-registry / Docker-images (только Gitlab);
- `PROJECT_WORKERS_COUNT` (`20`) – количество потоков (обработчиков) для репозиториев. Увеличение данного количества может существенно повысить скорость инвентаризации, однако негативно влияет на достижение rate-лимитов;
- `GROUP_WORKERS_COUNT` (`10`) – количество потоков (обработчиков) для групп.

Помимо этого, для подключения к БД PostgreSQL используются переменные среды `POSTGRES_*`, позволяющие задать параметры подключения к базе данных (IP-адрес, порт, имя и схему используемой базы данных, пользователя и пароль, соответственно).

## Процесс инвентаризации
Скорость инвентаризации зависит от состава (репозитории, группы, коммиты, права доступа) и количества инвентаризируемых объектов, а также от лимитов на взаимодействие с API. При отсутствии лимитов – скорость инвентаризации напрямую зависит от количества потоков (переменные среды `PROJECT_WORKERS_COUNT` и `GROUP_WORKERS_COUNT`).

К примеру, в Gitlab по умолчанию установлен [лимит на 400 запросов](https://docs.gitlab.com/ee/administration/settings/rate_limit_on_projects_api.html) информации о проектах (`/projects`) в минуту.

Таким образом, ориентировочное время инвентаризации одного инстанса, содержащего ~28 тысяч репозиториев, без снятия лимитов на запросы к API, может достигать 3-4 часов.

## Аналитика
В файле `ANALYTICS.md` приведены примеры аналитических запросов, демонстрирующих, как можно использовать полученную информацию для проведения аналитики по VCS.

## Поиск по VSC
В файле `gitlab-search-keyword.py` приведён пример сценария, позволяющего провести массовый поиск ключевого слова (аргумент `--keyword` в двойных кавычках, формата [Gitlab Advanced Search](https://docs.gitlab.com/ee/user/search/advanced_search.html#syntax) по всем файлам (blobs) в используемых инстансах Gitlab.

Опционально, возможно также передать фильтр (`--filter`) в формате SQL AND, к примеру, `"(CURRENT_TIMESTAMP - last_activity_repo) < '1 year'::interval"` – отфильтрует репозитории, в которых была активность за последние сутки.

Для запуска, необходимо выполнить следующие команды:
```bash
$ virtualenv -p python3.11 venv
$ source venv/bin/activate
$ pip install -r requirements.txt
$ nohup python3 -u gitlab-search-keyword.py --keyword "test" --filter "(CURRENT_TIMESTAMP - last_activity_repo) < '1 year'::interval" > search.log 2> search.log &
```

Наблюдать за процессом поиска в реальном времени можно при помощи команды `tail -f search.log`, либо:
```bash
watch -n1 "ps aux | grep gitlab-search-keyword | head -1 & tail -28 search.log & echo \"Bad response: $(grep 'bad response' search.log | wc -l) | Found: $(grep 'Found!' search.log| wc -l)\""
```

Результат поиска (найденные фрагменты и ссылки на них) будут сохраняться в директорию `search/`: путь файла соответствовует пути к репозиторию в VCS, с заменой символов `/` на `_`.

## Модуль сканирования
В файле `scanner.py` приведён пример реализации модуля, выполняющего операции над собранной базой, конкретно в данном примере – для однократного сканирования собранной базы средствами анализатора [Gitleaks](https://github.com/gitleaks/gitleaks).


Данный модуль выполняет выгрузку всех соответствующих фильтру репозиториев, (флаг `--filter`, перечень возможных фильтров описан в файле `filters.py`), и запускает для них инструмент, указанный в `--tool`. Дополнительно, можно указать путь до SSH-ключа `--key`, который будет использован для выгрузки репозиториев, использующих по умолчанию протокол `ssh://` – в случае, если ключ не указан, такие репозитории будут пропущены.

Для запуска необходимо предварительно провести инвентаризацию. После этого, необходимо [установить Gitleaks](https://github.com/gitleaks/gitleaks?tab=readme-ov-file#installing) и выполнить следующие команды, указав в качестве аргумента флага `--config` путь до конфигурации `gitleaks.toml` (содержится в директории `config` репозитория `gitleaks`):

```bash
$ virtualenv -p python3.11 venv
$ source venv/bin/activate
$ pip install -r requirements.txt
$ python3 scanner.py --filter default --tool gitleaks --config gitleaks.toml --key ~/.ssh/id_rsa
```

## Зависимости
В проекте использованы следующие зависимости:
- [python-gitlab](https://github.com/python-gitlab/python-gitlab) – взаимодействие с API Gitlab;
- [atlassian-python-api](https://github.com/atlassian-api/atlassian-python-api) – взаимодействие с API Bitbucket;
- [peewee](https://github.com/coleifer/peewee) – взаимодействие с БД sqlite3 / PostgreSQL (ORM).
