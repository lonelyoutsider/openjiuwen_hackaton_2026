# Контекст для VS Code / Codex,13 ноября2026

Repo lonelyoutsider/openjiuwen_hackaton_2026,experiment/challenge-benchmark.
E04 на26f3d05 завершён:baseline130/195,24/48,11691.7 токена;compact165/195,
33/48,11651.2. Оба exit0/usage complete/unattributed0. Все24 baseline-успеха
сохранены,+9 новых. Это одна calibration-пара, не hidden score.
Разбор:experiments/e04-context-result.md. Основные docs:AGENTS.md,
requirements.md,plan.md,progress.md,research-2026-11-13.md.

SDK60s timeout исправлен через явную Session,finally ledger и SyntaxError
feedback проверены SDK и реальным Docker-прогоном. Эти общие исправления
интегрируются main через PR8.72a942c — исторический резерв с известным багом.
Compact остаётся opt-in до выбора обычных defaults; не выдавать победу opt-in
за включение его в запуск жюри.

Следующий один запуск (runtime не меняется,image уже есть):

git pull --ff-only
py scripts/run_candidate_validation.py --live

Одна серия:confirmation40/plain/compact BUDGET12000,затем regression21 BUDGET5000,
независимые бюджеты этапов,максимум17000 суммарно.6 calls/cap1024,Qwen3.8-noreason,
без retries. При error/unknown usage второй этап не запускается. Источник и
image заморожены,ключ только в env. Fingerprint прежний
57afd096596df211adba8f9510b3bc2f8e2320eb80c27b1b6a0699267e7a9686.
Передать artifacts/candidate-*/validation.json,confirmation.json,regression.json.

После отчёта:отдельно оценить32 отложенных решаемых и19 старых регрессий.
При принятии включить compact в стандартный CLI,сохранить явное отключение
для контрольных запусков и перепроверить путь без feature flag. Не менять
сейчас очередь/модель/форматные циклы до confirmation. Не требуется rebuild
для нового runner:ни один файл runtime/Dockerfile/lock после26f3d05 не меняется.

Нерешённые calibration:b075 ложный отказ после5 одинаковых malformed JSON,
b040 неверный ответ после5 пустых content,b064 вычислен18.0,но финальный
answer не помещается в резерв. Прочие12 решаемых compact вообще не запускал.
Эти факты — кандидаты следующего исследования,не новые исправления.

Дедлайн13 ноября23:59 МСК. Доступ madrugado по последней проверке всё ещё none;
pending не равен доступу. Отправленное пользователем письмо зафиксировано,
получение URL оргкомитетом независимо не подтверждено.

## Постановка и состояние

100 задач, известный reward, максимум reward при общем output+input/10;
при равных баллах меньше токенов лучше. Не отдельная MAE-регрессия.
BUDGET из env может быть меньше или больше100k, остаток считаем сами.
Настоящий openJiuwen0.1.19, Python3.12 Docker; Python3.14 только scripts без SDK.
Runtime-сеть только предоставленный прокси, без GPU/скачиваний. Ключи только env.

Детерминированная фаза затем последовательный LLM JSON/tool агент через SDK.
Приватный workspace, защищённые тесты, unittest перед публикацией coding.
Общий ledger сохраняет резерв при неизвестном usage; retry нет. Reasoning уже
в completion, второй раз не добавлять; кеш без скидки. Expected не доступен агенту.

Последнее измерение E02 на5e495b5: validation-v1, оба режима21/21 reward,
8/8 решаемых и2 корректных отказа. Text1660.1 токена/18 вызовов; JSON1580.1/15.
Это одна пара, не hidden score. Подробности experiments/e02-result.md.
Ранее публичные8: deterministic16/20, live20/20 за850.6 токена.
E01 coding3: оба4/9, edit не исполнился из-за формата. E01b recovery5/9 против
strict3/9. Tags тогда не решён; в новом release-check он прошёл за3 вызова.

## Релизный кандидат

Default edit/recovery ON,6 вызовов/задачу, output cap1024. Если остаток мал,
cap снижается с сохранением прежнего input-резерва (минимум64 при cap>=64).
JSON auto только HTTPS api.neuraldeep.ru:443; неизвестный адрес прокси получает
обычный chat-запрос и recovery. URL организаторов никогда не заменять.
Boolean override-флаги доступны; A/B оценщик явно задаёт оба режима, чтобы
новые defaults не испортили контрольный вариант.

Release-check уже выполнен:19/19,51/51,3360.8 токена,24 вызова,image1.36GB.
Повторять его до нового обоснованного кандидата не требуется. Теперь baseline
проверяем на новом calibration60/plain. Архивные probe/E02 не повторять.

## Совместная работа

Ассистент пишет код, тесты, фиксирует в ветке/PR; пользователь с Мишей обсуждают
результаты и запускают Docker/API локально. В этом чате нет доступа к Windows.
Автосинхронизации истории с IDE нет: состояние в git и этих документах.
Не перезаписывать чужие изменения. Реальный Qwen отделять от SDK/fake тестов.
Квалификацию/heartbeat больше не выполнять. Секреты/сырые traces не коммитить.
