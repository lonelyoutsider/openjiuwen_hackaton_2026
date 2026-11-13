# Контекст для VS Code / Codex,13 ноября2026

Repo lonelyoutsider/openjiuwen_hackaton_2026. Main72a942c сохраняется как
проверенная резервная версия. Пользователь попросил продолжить оптимизацию;
прежнее «финальная/freeze» не означает остановку исследования. Новая ветка
experiment/challenge-benchmark, без изменений runtime/Dockerfile/lock.

Прочитать AGENTS.md, requirements.md, research-2026-11-13.md,
benchmarks/challenge-v1.md и progress.md. Release51/51 описан в
release-2026-11-13.md; это development-результат, не100-task hidden score.

E03 на7b6bfd9 завершился аварийно:SDK workflow timeout60с после b091,
109/195 reward,19/48 решаемых. Все19 фактически начатых выполнимых правильны;
29 не исследованы, все12 coding не запускались. Расход по records10587.8,
49 вызовов,5 явных правильных отказов; не объявлять12 пропусков верными отказами.
Разбор: docs/experiments/e03-partial-result.md.

SDK0.1.19 проверен по installed source: Runner envs игнорируется, нужна явная
create_workflow_session с WORKFLOW_EXECUTE_TIMEOUT. Исправление использует
остаток глобального deadline+30с cleanup. Сам deadline/HTTP/tools/BUDGET сохранены.
run_usage печатается в finally; evaluator читает общий ledger даже после crash.
SyntaxError от write теперь tool feedback, не crash (найдено аудитом, не в E03).

Следующий один запуск в ветке experiment/challenge-benchmark:

git pull --ff-only
docker build --progress=plain -t its-ia:context-experiment .
py scripts/run_context_experiment.py --live

Одна пара baseline/compact, calibration60/plain, по12000/максимум24000.
Обе arms используют общие reliability fixes; отличаются только превью данных:
8000 прежнее против1024+явный marker. Маленькие файлы и .py не меняются.
Compact opt-in, --compact-data-context; не включать default до результата.
При неизвестном usage/ошибке control treatment не запускается; нет retries.
Нужен именно rebuild нового tag: старый release image содержит timeout bug.
Передать artifacts/context-*/comparison.json,baseline.json,compact.json.

Confirmation40 отложен. Не менять одновременно очередь/модель/лимиты вызовов.
Выбранный вариант далее проверить на confirmation/старых регрессиях и внедрить
до13 ноября23:59 МСК. Даже если compact проиграет, SDK fix надо включить в сдачу
после Docker-проверки.72a942c — резерв с известным60s дефектом, не финальный оптимум.
Доступ жюри остаётся отдельным организационным вопросом, pending не равен доступу.

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
