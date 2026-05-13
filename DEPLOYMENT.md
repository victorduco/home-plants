# Deployment

## Local → HA server structure

```
ha/custom_components/plants/   →   /config/custom_components/plants/
ha/dashboards/plants.yaml      →   /config/dashboards/plants.yaml
```

HA server is the source of truth.

## Deploy

```sh
./deploy.sh                # everything
./deploy.sh integration    # custom component + auto-restart HA
./deploy.sh dashboard      # dashboard only (refresh browser, no restart)
```

Requires: SSH key at `~/.ssh/id_ed25519`, `.env` with `HA_URL` and `HA_TOKEN`.

## Pull from HA (remote → local)

```sh
rsync -av --exclude='__pycache__' -e "ssh -i ~/.ssh/id_ed25519 -p 22" \
  --rsync-path="sudo rsync" \
  hassio@192.168.1.151:/config/custom_components/plants/ ./ha/custom_components/plants/

rsync -av -e "ssh -i ~/.ssh/id_ed25519 -p 22" \
  hassio@192.168.1.151:/config/dashboards/plants.yaml ./ha/dashboards/plants.yaml
```
