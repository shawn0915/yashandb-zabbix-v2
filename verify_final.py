#!/usr/bin/env python3
"""最终验证 - 全部新指标"""
import yaspy, os
os.environ['LD_LIBRARY_PATH']='/opt/yashandb/yashandb_yasdb_home/lib'
conn = yaspy.connect(dsn='yas_oracle:1688', user='sys', password='Cod-2022')

def q(sql, label):
    cur = conn.cursor()
    try:
        cur.execute(sql)
        row = cur.fetchone()
        val = row[0] if row else None
        ok = val is not None
        print(f"  {'[OK]' if ok else '[FAIL]'} {label}: {val}")
        return ok
    except Exception as e:
        print(f"  [ERROR] {label}: {str(e)[:60]}")
        return False
    finally:
        cur.close()

results = []

print("=== Phase 1 ===")
results.append(q("SELECT VALUE FROM V$SYSSTAT WHERE NAME='EXECUTE COUNT'", "db.qps"))
results.append(q("SELECT VALUE FROM V$SYSSTAT WHERE NAME='COMMITS'", "db.tps"))
results.append(q("SELECT COUNT(*) FROM V$ARCHIVED_LOG WHERE FIRST_TIME >= TRUNC(SYSDATE)", "archived_log.count_today"))
results.append(q("SELECT COUNT(*) FROM V$SYSTEM_WAIT_CLASS", "wait_class.discovery"))
results.append(q("SELECT TOTAL_WAITS FROM V$SYSTEM_WAIT_CLASS WHERE WAIT_CLASS='Application'", "wait_class.count[Application]"))
results.append(q("SELECT TIME_WAITED FROM V$SYSTEM_WAIT_CLASS WHERE WAIT_CLASS='Application'", "wait_class.time[Application]"))
results.append(q("SELECT NVL(SUM(d.BYTES),0) FROM DBA_DATA_FILES d JOIN DBA_TABLESPACES t ON d.TABLESPACE_NAME=t.TABLESPACE_NAME WHERE t.CONTENTS='PERMANENT'", "tablespace.by_type[PERMANENT]"))
results.append(q("SELECT NVL(SUM(d.BYTES),0) FROM DBA_DATA_FILES d JOIN DBA_TABLESPACES t ON d.TABLESPACE_NAME=t.TABLESPACE_NAME WHERE t.CONTENTS='UNDO'", "tablespace.by_type[UNDO]"))
results.append(q("SELECT NVL(SUM(d.BYTES),0) FROM DBA_DATA_FILES d JOIN DBA_TABLESPACES t ON d.TABLESPACE_NAME=t.TABLESPACE_NAME WHERE t.CONTENTS='TEMPORARY'", "tablespace.by_type[TEMPORARY]"))
results.append(q("SELECT ROUND(GREATEST((SUM(ALLOCATED_SPACE)-SUM(FREE_SPACE))*100.0/NULLIF(SUM(TABLESPACE_SIZE),0),0),2) FROM DBA_TEMP_FREE_SPACE", "tablespace.temp_usage_pct"))
results.append(q("SELECT ROUND((SUM(d.BYTES)-NVL(SUM(f.BYTES),0))*100.0/NULLIF(SUM(d.BYTES),0),2) FROM DBA_DATA_FILES d JOIN DBA_TABLESPACES t ON d.TABLESPACE_NAME=t.TABLESPACE_NAME LEFT JOIN DBA_FREE_SPACE f ON d.TABLESPACE_NAME=f.TABLESPACE_NAME WHERE t.CONTENTS='UNDO'", "tablespace.undo_usage_pct"))
results.append(q("SELECT SQL_ID FROM V$SQLAREA ORDER BY BUFFER_GETS DESC FETCH FIRST 1 ROWS ONLY", "sql.top_buffer_gets_sql"))
results.append(q("SELECT SQL_ID FROM V$SQLAREA ORDER BY DISK_READS DESC FETCH FIRST 1 ROWS ONLY", "sql.top_disk_reads_sql"))
results.append(q("SELECT SQL_ID FROM V$SQLAREA ORDER BY EXECUTIONS DESC FETCH FIRST 1 ROWS ONLY", "sql.top_executions_sql"))
results.append(q("SELECT ROUND(GREATEST((SELECT COUNT(*)*100.0/NULLIF(TO_NUMBER((SELECT VALUE FROM V$PARAMETER WHERE NAME='MAX_SESSIONS')),0) FROM V$SESSION),(SELECT COUNT(*)*100.0/NULLIF(TO_NUMBER((SELECT VALUE FROM V$PARAMETER WHERE NAME='MAX_SESSIONS')),0) FROM V$PROCESS)),2) FROM DUAL", "resource_limit.usage_pct"))

print("\n=== Phase 2 ===")
results.append(q("SELECT ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY ELAPSED_TIME)/1000,2) FROM V$SQL WHERE EXECUTIONS>0 AND ELAPSED_TIME>0", "sql.p95_elapsed_ms"))
results.append(q("SELECT ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY ELAPSED_TIME)/1000,2) FROM V$SQL WHERE EXECUTIONS>0 AND ELAPSED_TIME>0", "sql.p99_elapsed_ms"))
results.append(q("SELECT COUNT(DISTINCT NVL(USERNAME,'(NULL)')) FROM V$SESSION WHERE TYPE='USER'", "session.user.discovery"))
results.append(q("SELECT COUNT(*) FROM V$SESSION WHERE TYPE='USER' AND USERNAME='SYS'", "session.by_user[SYS]"))
results.append(q("SELECT COUNT(DISTINCT NVL(PROGRAM,'(NULL)')) FROM V$SESSION WHERE TYPE='USER'", "session.program.discovery"))
results.append(q("SELECT COUNT(*) FROM DBA_OBJECTS WHERE STATUS='INVALID' AND OBJECT_TYPE='PROCEDURE'", "invalid_objects.by_type[PROCEDURE]"))
results.append(q("SELECT COUNT(*) FROM DBA_DATA_FILES WHERE AUTOEXTENSIBLE='NO'", "datafile.non_autoextend_count"))
results.append(q("SELECT COUNT(*) FROM DBA_USERS WHERE EXPIRY_DATE IS NOT NULL AND EXPIRY_DATE<=TRUNC(SYSDATE)+7 AND ACCOUNT_STATUS NOT IN ('EXPIRED','LOCKED')", "user.expiring_soon_count"))
results.append(q("SELECT VALUE FROM V$PARAMETER WHERE NAME='STATISTICS_LEVEL'", "db.statistics_level"))

conn.close()
ok = sum(results)
total = len(results)
print(f"\n{'='*50}")
print(f"结果: {ok}/{total} 通过, {total-ok} 失败")
print(f"{'='*50}")
