# Deployment notes

This repo deploys the Home Assistant custom component under `ha_integration/`.

## SSH access

- Host: `192.168.1.151`
- Port: `22`
- User: `hassio`
- SSH key: `~/.ssh/id_ed25519`

Quick check:

```sh
ssh -i ~/.ssh/id_ed25519 -p 22 hassio@192.168.1.151 "ls -la /config/custom_components"
```

## Target path on server

Home Assistant config path is `/config` (symlink to `/homeassistant`).

Custom component destination:

```
/config/custom_components/plants/
```

## Deploy command (rsync)

Use sudo on the remote side to handle permissions and cleanup:

```sh
rsync -av --delete \
  -e "ssh -i ~/.ssh/id_ed25519 -p 22" \
  --rsync-path="sudo rsync" \
  ./ha_integration/ \
  hassio@192.168.1.151:/config/custom_components/plants/
```

## Home Assistant API

API details live in `.env` at the repo root:

- `HA_URL`
- `HA_TOKEN`

Example restart call:

```sh
source ./.env
curl -X POST "$HA_URL/api/services/homeassistant/restart" \
  -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Tip: if `homeassistant.local` is not resolvable from this machine, replace
`HA_URL` in `.env` with the IP of the HA host, e.g. `http://192.168.1.151:8123`.
