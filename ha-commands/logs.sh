#!/usr/bin/env bash
# Tail Home Assistant logs
ssh -i ~/.ssh/id_ed25519 -p 22 hassio@192.168.1.151 "tail -f /config/home-assistant.log"
