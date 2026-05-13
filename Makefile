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
