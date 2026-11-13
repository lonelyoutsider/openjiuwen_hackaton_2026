# Контекст для VS Code / Codex,13 ноября2026

Repo lonelyoutsider/openjiuwen_hackaton_2026. Main72a942c сохраняется как
проверенная резервная версия. Пользователь попросил продолжить оптимизацию;
прежнее «финальная/freeze» не означает остановку исследования. Новая ветка
experiment/challenge-benchmark, без изменений runtime/Dockerfile/lock.

Прочитать AGENTS.md, requirements.md, research-2026-11-13.md,
benchmarks/challenge-v1.md и progress.md. Release51/51 описан в
release-2026-11-13.md; это development-результат, не100-task hidden score.

Следующий один live-запуск на Windows в текущем repo:

git fetch origin
git switch experiment/challenge-benchmark
py scripts/run_challenge_benchmark.py --partition calibration --format plain --budget 15000 --live

Docker Desktop нужен. Image its-ia:release уже подходит: runtime fingerprint
тот же ead9793f405a0565a7c1d01d89a4d8101c47998ba48ac752382e730beadb242e.
Rebuild не требуется. Скрипт сначала проверит source match без API/сети.

Набор100:80 решаемых/20 missing;40 решаемых семейств по2 варианта,20 missing
сценариев. Calibration60 (48 решаемых,195 reward), confirmation40 (32,118),
непересекающиеся семейства. First run только calibration/plain и BUDGET15000.
Plain явно задаёт --no-json-mode к реальному /app агенту, имитируя payload,
который он выберет на незнакомом proxy. Не имитирует сам proxy/usage/HTTP.
Передать artifacts/challenge-*/benchmark.json. Отложенные40 пока не запускать.

После отчёта выбрать один механизм, проверить SDK/юниты, затем ограниченную
A/B пару при одинаковом бюджете. Для расписания нужен действительно тесный
бюджет. Не менять одновременно модель/инструменты/расписание и не приписывать
результат одному фактору. Ни одна новая runtime-гипотеза ещё не измерена.

Дедлайн13 ноября23:59 МСК; сохранить72a942c, если кандидат не доказал выигрыш.
Пользователь написал оргкомитету о pending-приглашении. Последняя проверка
promsoft=write, madrugado=none. Доступ/получение URL письмом не считать завершёнными.

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
