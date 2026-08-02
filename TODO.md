# TODO

- Починить надоедливые нотификации
- Проверить почему агент включает свет ночью
- Посмотреть другие логи и ошибки в LangSmith
- Посмотреть что есть в Heroku, почему много бабла выходит, удалить ненужные проекты

## Баги из диагностики (2026-08-01)

- `select.py`/`text.py` в интеграции `plants`: `AttributeError: 'NoneType'/'ThermostatsData' object has no attribute 'plants'` при старте HA — похоже на race condition между загрузкой разных config entries (plants/thermostats/etc)
- `Failed to load services.yaml for integration: plants` — интеграция регистрирует сервис `plants.update_agent_log` в коде, но у неё нет `services.yaml`
- [ПОЧИНЕНО 2026-08-02] Tablet-дашборд и hourly_plant_log показывали "no data" для 6 из 9 растений — `PlantMoistureSensor` генерирует `entity_id` с суффиксом `_moisture`, но 3 старых растения сохранили entity_id с суффиксом `_soil_moisture_state` (registry не переименовывается при смене кода). Шаблоны, хардкодившие один суффикс, ловили только часть растений — заменили на явный маппинг (`tablet.yaml`) и матчинг по `friendly_name` вместо `entity_id` (`hourly_plant_log.yaml`), как уже было сделано в `plants.yaml`. Стоит рассмотреть унификацию entity_id для всех растений, чтобы не поддерживать два соглашения об именовании
