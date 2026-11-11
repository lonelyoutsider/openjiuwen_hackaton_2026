# Контекст для VS Code / Codex

Команда Its IA, Иван и Миша. Repo lonelyoutsider/openjiuwen_hackaton_2026.
Прочитать AGENTS.md, docs/requirements.md, docs/progress.md и docs/plan.md.

Цель — reward на 100 задачах под общим бюджетом output + input/10, не MAE
отдельного предиктора. openJiuwen обязателен. В main первый узкий baseline:
6/8 официальных примеров, 16/20, 0 API calls, реальный Workflow/Runner.

Начать с python -m unittest discover -s tests -v и
python scripts/evaluate_examples.py в окружении requirements.lock.
Dockerfile подготовлен, но build/run и размер образа ещё не проверены.
Не редактировать официальные примеры для улучшения результата.
Не давать expected в решатель; evaluator удаляет его из входной копии.
Не путать unsupported с доказанной невыполнимостью.

Следующая реализация: OpenAI-compatible API-клиент по env, usage/бюджет,
лимиты времени и повторов, coding-агент через openJiuwen, локальные инструменты,
проверка тестов без правки tests, answer.txt рядом с task.json.
Утвердить небольшой экспериментальный бюджет до массовых запросов.

API base при разработке по памятке https://api.neuraldeep.ru/v1;
на оценке использовать только LLM_BASE_URL и LLM_API_KEY проверяющих.
Invite-код и ключ команды в repo не хранить. Во время разработки не выходить
за два одновременных внешних IP командного аккаунта.

Нет автоматической синхронизации контекста между чатом и IDE:
фиксация состояния — коммиты и docs/progress.md. Для изменений отдельная ветка/PR.
MCP-квалификация уже закрыта. Не выполнять регистрацию или heartbeat.


Уточнения 11 ноября: 8 логических CPU; локальные модели организатор ограничил
через запрет GPU, в отличие от старой формулировки регламента. См. requirements.
Формулировки в финале будут другими: нужен общий LLM fallback, не расширение
только парсеров для коробок. Пользователь активировал API, но реальный smoke
ещё не выполнен. scripts/smoke_api.py работает без установки SDK; основную
разработку вести в Docker/Python 3.12, не в системном Python 3.14 пользователя.


12 ноября добавлен LLM fallback: harness/llm.py, agent.py, tools.py.
run_agent сначала решает все бесплатные задачи, затем использует agent из
настоящего WorkflowComponent. Автовключение по LLM_API_KEY, --no-llm для baseline.
Оценщик требует явный --llm. Первый live запуск: py scripts/run_live_examples.py
после docker build -t its-ia:agent .; бюджет 3000, max calls/task 4.
Реальной оценки новой версии пока нет; fake HTTP тесты не считаются LLM-результатом.
Baseline Docker подтверждён пользователем: 6/8, 16/20, образ1.36GB.
Дальше приоритет: живой coding smoke, исправления ошибок протокола, вариации
формулировок, затем улучшение reward/cost-планирования на реальных траекториях.


Последний факт 12 ноября: пользователь подтвердил live Qwen на публичных
примерах — 8/8, 20/20, 850.6 учётных токена, 4 вызова. Это не hidden score.
Добавлены scripts/validation_set.py и --suite validation: 10 новых задач,
8 решаемых и 2 недоопределённых. Следующий ограниченный прогон — 6000 токенов.
Результат и coding-исходники в artifacts/validation_report.json (gitignored).
Подробности конфигурации и фактические измерения — docs/progress.md.


Последний live validation-v1: 7/8 решаемых, 18/21, 2169.9 токена/24 вызова.
Проблемы data_tie и data_missing_costs достигли 4-call лимита. Для второго
отсутствие ответа ещё не означает распознавание невыполнимости. Одна поисковая
недоопределённая задача корректно получила insufficient_data.
Следующий прогон только этих двух задач: --only data_tie,data_missing_costs
--budget 3000 --diagnostics. Отчёт validation_subset_report.json содержит шаги.
Не повышать лимиты и не добавлять task-ID решения без выяснения причины.
