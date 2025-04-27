#!/bin/bash
echo "Restoring backed up components..."
NPM_BACKUP=$(find /usr/local/bin /opt/homebrew/bin -name "npm_backup" 2>/dev/null | head -n 1)
if [ ! -z "$NPM_BACKUP" ]; then sudo mv "$NPM_BACKUP" "${NPM_BACKUP%_backup}"; echo "npm restored"; else echo "npm backup not found"; fi
JQ_BACKUP=$(find /usr/local/bin /opt/homebrew/bin -name "jq_backup" 2>/dev/null | head -n 1)
if [ ! -z "$JQ_BACKUP" ]; then sudo mv "$JQ_BACKUP" "${JQ_BACKUP%_backup}"; echo "jq restored"; else echo "jq backup not found"; fi
echo "Restore complete!"
