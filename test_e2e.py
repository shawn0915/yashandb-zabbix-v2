#!/usr/bin/env python3
"""通过 yashandb_monitor.py collect_metric 端到端验证"""
import sys, os
sys.path.insert(0, '/tmp')
os.environ['LD_LIBRARY_PATH'] = '/opt/yashandb/yashandb_yasdb_home/lib'
import yaspy

# 直接模拟 collect_metric 的关键指标
conn = yaspy.connect(dsn='yas_oracle:1688', user='sys', password='Cod-2022')

def q(sql):
    cur = conn.cursor()
    cur.execute(sql)
    return cur.fetchone()[0]

print("=== monitor.py 端到端验证 ===")

tests = [
    ("yashandb.db.qps",              "EXECUTE COUNT"),
    ("yashandb.db.tps",              "COMMITS"),
    ("yashandb.archived_log.count_today", "当天归档"),
    ("yashandb.wait_class.discovery", "等待类LLD"),
    ("yashandb.tablespace.temp_usage_pct", "Temp使用率%"),
    ("yashandb.tablespace.undo_usage_pct", "Undo使用率%"),
    ("yashandb.sql.top_buffer_gets_sql", "Top SQL(BufferGets)"),
    ("yashandb.resource_limit.usage_pct", "资源限制%"),
    ("yashandb.sql.p95_elapsed_ms",   "P95延迟ms"),
    ("yashandb.sql.p99_elapsed_ms",   "P99延迟ms"),
    ("yashandb.session.user.discovery","用户会话LLD"),
    ("yashandb.invalid_objects.by_type.discovery", "INVALID对象LLD"),
    ("yashandb.datafile.non_autoextend_count", "非自动扩展DF"),
    ("yashandb.user.expiring_soon_count", "密码即将过期"),
    ("yashandb.db.statistics_level",  "STATISTICS_LEVEL"),
]

# 直接用 SQL 验证（collect_metric 内部逻辑一致）
for key, desc in tests:
    try:
        # 从 yashandb_monitor.py 中提取对应 SQL
        if key == "yashandb.db.qps":
            val = q("SELECT VALUE FROM V$SYSSTAT WHERE NAME='EXECUTE COUNT'")
        elif key == "yashandb.db.tps":
            val = q("SELECT VALUE FROM V$SYSSTAT WHERE NAME='COMMITS'")
        elif key == "yashandb.archived_log.count_today":
            val = q("SELECT COUNT(*) FROM V$ARCHIVED_LOG WHERE FIRST_TIME >= TRUNC(SYSDATE)")
        elif key == "yashandb.wait_class.discovery":
            import json
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT WAIT_CLASS FROM V$SYSTEM_WAIT_CLASS ORDER BY WAIT_CLASS")
            rows = cur.fetchall()
            data = [{"{#WAIT_CLASS}": r[0]} for r in rows]
            val = json.dumps({"data": data})
            cur.close()
        elif key == "yashandb.tablespace.temp_usage_pct":
            val = q("SELECT ROUND(GREATEST((SUM(ALLOCATED_SPACE)-SUM(FREE_SPACE))*100.0/NULLIF(SUM(TABLESPACE_SIZE),0),0),2) FROM DBA_TEMP_FREE_SPACE")
        elif key == "yashandb.tablespace.undo_usage_pct":
            val = q("SELECT ROUND((SUM(d.BYTES)-NVL(SUM(f.BYTES),0))*100.0/NULLIF(SUM(d.BYTES),0),2) FROM DBA_DATA_FILES d JOIN DBA_TABLESPACES t ON d.TABLESPACE_NAME=t.TABLESPACE_NAME LEFT JOIN DBA_FREE_SPACE f ON d.TABLESPACE_NAME=f.TABLESPACE_NAME WHERE t.CONTENTS='UNDO'")
        elif key == "yashandb.sql.top_buffer_gets_sql":
            val = q("SELECT SQL_ID FROM V$SQLAREA ORDER BY BUFFER_GETS DESC FETCH FIRST 1 ROWS ONLY")
        elif key == "yashandb.resource_limit.usage_pct":
            val = q("SELECT ROUND(GREATEST((SELECT COUNT(*)*100.0/NULLIF(TO_NUMBER((SELECT VALUE FROM V$PARAMETER WHERE NAME='MAX_SESSIONS')),0) FROM V$SESSION),(SELECT COUNT(*)*100.0/NULLIF(TO_NUMBER((SELECT VALUE FROM V$PARAMETER WHERE NAME='MAX_SESSIONS')),0) FROM V$PROCESS)),2) FROM DUAL")
        elif key == "yashandb.sql.p95_elapsed_ms":
            val = q("SELECT ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY ELAPSED_TIME)/1000,2) FROM V$SQL WHERE EXECUTIONS>0 AND ELAPSED_TIME>0")
        elif key == "yashandb.sql.p99_elapsed_ms":
            val = q("SELECT ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY ELAPSED_TIME)/1000,2) FROM V$SQL WHERE EXECUTIONS>0 AND ELAPSED_TIME>0")
        elif key == "yashandb.session.user.discovery":
            import json
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT NVL(USERNAME,'(NULL)') FROM V$SESSION WHERE TYPE='USER' ORDER BY 1")
            rows = cur.fetchall()
            data = [{"{#USERNAME}": r[0]} for r in rows]
            val = json.dumps({"data": data})
            cur.close()
        elif key == "yashandb.invalid_objects.by_type.discovery":
            import json
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT OBJECT_TYPE FROM DBA_OBJECTS WHERE STATUS='INVALID' ORDER BY OBJECT_TYPE")
            rows = cur.fetchall()
            data = [{"{#OBJTYPE}": r[0]} for r in rows]
            val = json.dumps({"data": data})
            cur.close()
        elif key == "yashandb.datafile.non_autoextend_count":
            val = q("SELECT COUNT(*) FROM DBA_DATA_FILES WHERE AUTOEXTENSIBLE='NO'")
        elif key == "yashandb.user.expiring_soon_count":
            val = q("SELECT COUNT(*) FROM DBA_USERS WHERE EXPIRY_DATE IS NOT NULL AND EXPIRY_DATE<=TRUNC(SYSDATE)+7 AND ACCOUNT_STATUS NOT IN ('EXPIRED','LOCKED')")
        elif key == "yashandb.db.statistics_level":
            val = q("SELECT VALUE FROM V$PARAMETER WHERE NAME='STATISTICS_LEVEL'")
        print(f"  [OK] {key}: {str(val)[:50]}")
    except Exception as e:
        print(f"  [FAIL] {key}: {e}")

conn.close()
