# Эксперимент 1: Cursor Agent + GPT-5.3 Codex Spark — Electronics Domain

## Описание эксперимента

**Дата:** 2026-03-31
**Инструмент:** Cursor Agent CLI (`cursor-agent v2026.03.30`)
**Модель:** `gpt-5.3-codex-spark-preview-high` (GPT-5.3 Codex Spark High)
**Домен:** Electronics (Google Product Taxonomy)
**Метод:** Ralph loop — итеративный автономный агентный цикл

### Конфигурация запуска

| Параметр | Значение |
|----------|----------|
| Стартовая таксономия | 20 узлов (root + 19 L1-L2 категорий) |
| Gold standard | 418 узлов, глубина 6 |
| Число stories в prd.json | 8 |
| Max iterations | 10 |
| Флаги cursor-agent | `--print --yolo --trust --workspace .` |
| Instruction file | `AGENTS.md` (не CLAUDE.md) |
| Python env | `taxonomy-as-code` (conda, Python 3.11) |

### Установка и подготовка

1. Conda env `taxonomy-as-code` создан с `networkx`, `mcp`
2. `cursor-agent` установлен через `curl https://cursor.com/install -fsSL | bash`
3. `prepare_data.py` сгенерировал 4 домена из Google Product Taxonomy (5595 строк)
4. `ralph.sh` адаптирован: Cursor = третий агент, читает `AGENTS.md`, парсинг `--tool`/`--model` флагов

---

## Результаты

### Итерация 1 — Story 1: Verify L1 categories

**Статус:** PASSED

**Что сделал агент:**
- Прочитал `AGENTS.md`, `progress.txt`, `prd.json`, `taxonomy.json`
- Определил, что L1-структура (19 подкатегорий) уже соответствует acceptance criteria
- Запустил `validate.py` — PASSED (0 ошибок, 1 warning: fanout 19 > 15)
- Запустил `metrics.py` — Edge F1 = 0.0872
- Обновил `prd.json` (passes: true)
- Записал learnings в `progress.txt`
- Создал git commit

**Метрики после итерации 1:**

| Метрика | Значение |
|---------|----------|
| Edge F1 | 0.0872 |
| Node Coverage | — |
| Ancestor F1 | — |
| Число узлов | 20 |
| Глубина | 2 |

**Наблюдения:**
- Агент корректно идентифицировал, что задача уже выполнена (start taxonomy содержит L1+L2)
- Самостоятельно обнаружил проблему с Python-версией (system Python 3.8 vs conda 3.11) и использовал правильный путь
- Записал полезное наблюдение в `progress.txt` для следующих итераций
- Время выполнения: ~2-3 минуты

---

## Последующие итерации

_Будут добавлены после полного прогона._

| Итерация | Story | Passed | Edge F1 | Узлы | Время (сек) |
|----------|-------|--------|---------|------|-------------|
| 1 | Verify L1 | true | 0.0872 | 20 | ~120 |
| 2 | ... | | | | |
| 3 | ... | | | | |

---

## Выводы (предварительные)

1. **Ralph loop с Cursor Agent CLI работает** — агент успешно выполняет цикл: читает инструкции, выполняет задачу, валидирует, коммитит
2. **AGENTS.md как instruction file** — cursor-agent корректно читает его как основной файл инструкций
3. **GPT-5.3 Codex Spark High** справляется с taxonomy engineering задачами
4. **Non-interactive mode** (`--print --yolo --trust`) позволяет полностью автономную работу

### Проблемы обнаруженные

1. `python` в PATH = 3.8 (anaconda base), а taxonomy_core.py использует `str | Path` (Python 3.10+) — исправлено: ralph.sh теперь использует `$PYTHON` из conda env
2. ralph.sh ранее не логировал метрики в CSV — добавлено per-iteration CSV logging

---

## Для диплома

### Формулировка

> Мы адаптировали Ralph loop для работы с Cursor Agent CLI, добавив поддержку моделей GPT-5.3 Codex Spark. В отличие от Claude Code, Cursor Agent использует файл `AGENTS.md` как нативный источник инструкций, что соответствует конвенциям IDE Cursor. Агент запускается в неинтерактивном режиме (`--print --yolo --trust`) с указанием модели и рабочей директории.

### Ключевые отличия от Claude Code

| Аспект | Claude Code | Cursor Agent |
|--------|-------------|--------------|
| CLI команда | `claude --dangerously-skip-permissions` | `cursor-agent --print --yolo --trust` |
| Instruction file | `CLAUDE.md` | `AGENTS.md` |
| Модель | Claude Sonnet/Opus | GPT-5.3 Codex Spark High/Extra High |
| Prompt подача | stdin pipe | positional argument |
