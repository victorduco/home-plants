# TODO

- [ПОЧИНЕНО] Починить надоедливые нотификации — см. RESEARCH_RESULTS.md
- [ПОЧИНЕНО] Проверить почему агент включает свет ночью — см. RESEARCH_RESULTS.md
- [СДЕЛАНО] Посмотреть другие логи и ошибки в LangSmith — см. RESEARCH_RESULTS.md
- **Осталось вручную:** в Heroku Scheduler у `home-plants-agent` заменить часовой запуск `runner.py` на раз в 4 часа (`make agent-scheduler`)
- Посмотреть что есть в Heroku, почему много бабла выходит, удалить ненужные проекты

## Баги из диагностики (2026-08-01)

- `select.py`/`text.py` в интеграции `plants`: `AttributeError: 'NoneType'/'ThermostatsData' object has no attribute 'plants'` при старте HA — похоже на race condition между загрузкой разных config entries (plants/thermostats/etc)
- [ПОЧИНЕНО] `Failed to load services.yaml for integration: plants` — добавлен `ha/custom_components/plants/services.yaml` с описанием `update_agent_log` (включая новое поле `plant_check_notified`)
- [ПОЧИНЕНО 2026-08-02] Tablet-дашборд и hourly_plant_log показывали "no data" для 6 из 9 растений — `PlantMoistureSensor` генерирует `entity_id` с суффиксом `_moisture`, но 3 старых растения сохранили entity_id с суффиксом `_soil_moisture_state` (registry не переименовывается при смене кода). Шаблоны, хардкодившие один суффикс, ловили только часть растений — заменили на явный маппинг (`tablet.yaml`) и матчинг по `friendly_name` вместо `entity_id` (`hourly_plant_log.yaml`), как уже было сделано в `plants.yaml`. Стоит рассмотреть унификацию entity_id для всех растений, чтобы не поддерживать два соглашения об именовании
