# Home Assistant Setup

All commands → see `Makefile`.

## Prerequisites

1. SSH access to the HA server:
```sh
ssh-copy-id -i ~/.ssh/id_ed25519 -p 22 hassio@192.168.1.151
```

2. Create `.env` in the repo root:
```sh
HA_URL=http://192.168.1.151:8123
HA_TOKEN=<long-lived token from HA profile page>
```
