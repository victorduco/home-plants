# TODO

- Починить надоедливые нотификации
- Проверить почему агент включает свет ночью
- Посмотреть другие логи и ошибки в LangSmith
- Посмотреть что есть в Heroku, почему много бабла выходит, удалить ненужные проекты

## Баги из диагностики (2026-08-01)

- [ПОЧИНЕНО 2026-08-02] Автоматизация `hourly_plant_log` падала: `ValueError: float got invalid input 'No soil moisture meter near the plant.'` — заменили `rejectattr` на `selectattr('state', 'is_number')`
- [ПОЧИНЕНО 2026-08-02] Дашборд `plants.yaml` (карточка "Plant Status") падал: `ValueError: int got invalid input 'unknown'` — добавили дефолт `| int(0)` для всех порогов
- [ПОЧИНЕНО 2026-08-02] `PlantAirTemperatureSensor`/остальные mirror-сенсоры кидали `ValueError` при записи состояния — `native_unit_of_measurement` теперь возвращает `None`, если `native_value` не числовое (было: unit оставался, даже когда значение — строка типа "No meter..."/"Stale")
- GW1200B (Ecowitt) шлюз физически не шлёт данные в HA ни по одному каналу (не только почва — indoor температура/влажность/давление тоже `unavailable`, `restored: true`, `integration_entities("ecowitt")` = 0) — нужно проверить сам гейтвей физически: питание, Wi-Fi, адрес сервера в приложении WSView Plus/Ecowitt
- `select.py`/`text.py` в интеграции `plants`: `AttributeError: 'NoneType'/'ThermostatsData' object has no attribute 'plants'` при старте HA — похоже на race condition между загрузкой разных config entries (plants/thermostats/etc)
- `Failed to load services.yaml for integration: plants` — интеграция регистрирует сервис `plants.update_agent_log` в коде, но у неё нет `services.yaml`
