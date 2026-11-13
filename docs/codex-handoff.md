# Контекст для VS Code / Codex,13 ноября2026

Repo lonelyoutsider/openjiuwen_hackaton_2026, ветка experiment/coding-edit-ab,
PR7. Прочитать AGENTS.md, requirements.md, final-day.md и progress.md.
main покаf6715b5; новые defaults нужно после проверки перенести в main до дедлайна.

Дедлайн13 ноября23:59 МСК. Ссылку на repo обязательно отправить
openjiuwen_org@nsu.ru: новое уточнение заменяет старое «email не нужен».
promsoft и MikhailOnyanov имеют write, madrugado pending по сообщению пользователя.
Письмо ассистентом не отправлялось. Не считать приглашение принятым.

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
strict3/9. Tags тогда не решён, нельзя объявлять все регрессии пройденными.

## Релизный кандидат

Default edit/recovery ON,6 вызовов/задачу, output cap1024. Если остаток мал,
cap снижается с сохранением прежнего input-резерва (минимум64 при cap>=64).
JSON auto только HTTPS api.neuraldeep.ru:443; неизвестный адрес прокси получает
обычный chat-запрос и recovery. URL организаторов никогда не заменять.
Boolean override-флаги доступны; A/B оценщик явно задаёт оба режима, чтобы
новые defaults не испортили контрольный вариант.

Следующий один запуск на Windows в корне текущей ветки:

git pull --ff-only
docker build --progress=plain -t its-ia:release .
py scripts/run_release_check.py --live

Потолок10000 на21 случай: public8 + coding3 + свежие10;19 решаемых/51 reward.
Скрипт замораживает commit, проверяет image fingerprint без сети до ввода ключа,
запускает агент из /app с --tasks-dir и BUDGET env, не из mounted /repo.
Read-only root, /tmp2GB, CPU8/RAM16GB. ITS_IA_DIAGNOSTICS включает лишь лог.
Передать artifacts/release-*/release.json. Не повторять probe или E02.
Это dev-тест с NeuralDeep, не финальный proxy или скрытые отборочные2 задачи.

После отчёта — исправить конкретные сбои, проверить, merge PR7, freeze main SHA.
Не добавлять сегодня другие модели/swarm/обучение/переписывание очереди.
Не запускать параллельные серии с командным ключом. Не подгонять код под IDs,
expected, будущие шаги. Не менять official examples. Новые случаи после запуска
тоже считаются development, а не новым независимым holdout.

## Совместная работа

Ассистент пишет код, тесты, фиксирует в ветке/PR; пользователь с Мишей обсуждают
результаты и запускают Docker/API локально. В этом чате нет доступа к Windows.
Автосинхронизации истории с IDE нет: состояние в git и этих документах.
Не перезаписывать чужие изменения. Реальный Qwen отделять от SDK/fake тестов.
Квалификацию/heartbeat больше не выполнять. Секреты/сырые traces не коммитить.
