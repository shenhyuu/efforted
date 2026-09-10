#!/usr/bin/env bash
set -euo pipefail

database_path=/var/lib/zhihen/zhihen.db
backup_dir=/var/backups/zhihen
timestamp=$(date -u +%Y%m%dT%H%M%SZ)

install -d -m 0700 "$backup_dir"
sqlite3 "$database_path" ".backup '$backup_dir/zhihen-$timestamp.db'"
find "$backup_dir" -type f -name 'zhihen-*.db' -mtime +30 -delete
