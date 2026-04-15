#!/bin/bash
export LD_LIBRARY_PATH=/opt/yashandb/yashandb_yasdb_home/lib
PYTHON="python3 /tmp/yashandb_monitor.py --host yas_oracle --port 1688 --user sys --password Cod-2022"

tests=(
  "yashandb.db.qps"
  "yashandb.db.tps"
  "yashandb.archived_log.count_today"
  "yashandb.wait_class.discovery"
  "yashandb.tablespace.temp_usage_pct"
  "yashandb.tablespace.undo_usage_pct"
  "yashandb.sql.top_buffer_gets_sql"
  "yashandb.resource_limit.usage_pct"
  "yashandb.sql.p95_elapsed_ms"
  "yashandb.sql.p99_elapsed_ms"
  "yashandb.session.user.discovery"
  "yashandb.invalid_objects.by_type.discovery"
  "yashandb.datafile.non_autoextend_count"
  "yashandb.user.expiring_soon_count"
  "yashandb.db.statistics_level"
  "yashandb.db.wait_class.count[Application]"
  "yashandb.db.wait_class.time[Application]"
  "yashandb.tablespace.by_type[PERMANENT]"
  "yashandb.tablespace.by_type[UNDO]"
  "yashandb.tablespace.by_type[TEMPORARY]"
  "yashandb.session.by_user[SYS]"
)

passed=0
failed=0
for m in "${tests[@]}"; do
  result=$($PYTHON --metric "$m" 2>&1)
  if echo "$result" | grep -q "ZBX_NOTSUPPORTED\|Error\|ERROR"; then
    echo "[FAIL] $m => $result"
    failed=$((failed+1))
  else
    echo "[OK]   $m => $(echo $result | head -c 60)"
    passed=$((passed+1))
  fi
done
echo ""
echo "=========================================="
echo "结果: $passed/$((passed+failed)) 通过, $failed 失败"
echo "=========================================="
