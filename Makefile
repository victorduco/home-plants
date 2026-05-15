.DEFAULT_GOAL := deploy

deploy:
	./ha-commands/deploy.sh all

deploy-integration:
	./ha-commands/deploy.sh integration

deploy-dashboard:
	./ha-commands/deploy.sh dashboard

restart:
	./ha-commands/restart.sh

clear-notifications:
	./ha-commands/clear-notifications.sh

reload-dashboards:
	./ha-commands/reload-dashboards.sh

logs:
	./ha-commands/logs.sh

ssh:
	ssh -i ~/.ssh/id_ed25519 -p 22 hassio@192.168.1.151

pull:
	./ha-commands/pull.sh

agent-dev:
	cd langgraph-app && langgraph dev

agent-install:
	cd langgraph-app && pip install -e .

agent-deploy:
	HEROKU_APP_NAME=home-plants-agent ./ha-commands/deploy-langgraph.sh

agent-run:
	cd langgraph-app && LANGGRAPH_API_URL=https://home-plants-agent-5910b5a018d0.herokuapp.com python runner.py

agent-logs:
	HEROKU_API_KEY=$$(grep HEROKU_API_KEY .env | cut -d= -f2) \
	  heroku logs --tail -a home-plants-agent

agent-scheduler:
	HEROKU_API_KEY=$$(grep HEROKU_API_KEY .env | cut -d= -f2) \
	  heroku addons:open scheduler -a home-plants-agent

backup:
	@BACKUP_DIR="backups/$$(date +%Y-%m-%d_%H-%M-%S)"; \
	mkdir -p "$$BACKUP_DIR"; \
	echo "→ Backing up plants storage files..."; \
	ssh -i ~/.ssh/id_ed25519 -p 22 hassio@192.168.1.151 \
		"sudo tar -czf - /config/.storage/plants* 2>/dev/null" \
		> "$$BACKUP_DIR/plants_storage.tar.gz"; \
	echo "→ Backing up entity & device registry..."; \
	ssh -i ~/.ssh/id_ed25519 -p 22 hassio@192.168.1.151 \
		"sudo tar -czf - /config/.storage/core.entity_registry /config/.storage/core.device_registry 2>/dev/null" \
		> "$$BACKUP_DIR/registry.tar.gz"; \
	echo "→ Backing up logbook & history (plants domain)..."; \
	ssh -i ~/.ssh/id_ed25519 -p 22 hassio@192.168.1.151 \
		"sudo python3 -c \"\
import sqlite3, json; \
conn = sqlite3.connect('/config/home-assistant_v2.db'); \
cur = conn.cursor(); \
cur.execute('SELECT et.event_type, ed.shared_data, e.time_fired_ts FROM events e JOIN event_types et ON e.event_type_id = et.event_type_id JOIN event_data ed ON e.data_id = ed.data_id WHERE ed.shared_data LIKE \\\"%plants%\\\"'); \
rows = [{'event_type': r[0], 'data': json.loads(r[1]), 'time': r[2]} for r in cur.fetchall()]; \
print(json.dumps(rows, ensure_ascii=False, indent=2)); \
conn.close() \
\"" > "$$BACKUP_DIR/plants_logbook.json"; \
	echo "✓ Backup saved to $$BACKUP_DIR"
