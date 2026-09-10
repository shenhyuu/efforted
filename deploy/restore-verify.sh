#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 /path/to/zhihen-backup.db" >&2
  exit 2
fi

backup_path=$1
if [[ ! -f "$backup_path" ]]; then
  echo "backup not found: $backup_path" >&2
  exit 2
fi

work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT
restored_path="$work_dir/zhihen-restored.db"
sqlite3 "$backup_path" ".backup '$restored_path'"

integrity=$(sqlite3 "$restored_path" "PRAGMA integrity_check;")
if [[ "$integrity" != "ok" ]]; then
  echo "restore verification failed: $integrity" >&2
  exit 1
fi

sqlite3 -header -column "$restored_path" \
  "SELECT 'users' AS table_name, count(*) AS rows FROM users
   UNION ALL SELECT 'records', count(*) FROM records
   UNION ALL SELECT 'lamps', count(*) FROM lamps
   UNION ALL SELECT 'timers', count(*) FROM timers;"
echo "restore verification passed"
