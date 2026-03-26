#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YashanDB Zabbix Monitor Plugin
Version: 1.0.0
Compatible: YashanDB 23.4 LTS + Zabbix 7.4.x

用法:
    python yashandb_monitor.py --host <host> --port <port> \
        --user <user> --password <password> --metric <metric_key>

示例:
    python yashandb_monitor.py --host 127.0.0.1 --port 1688 \
        --user sys --password yasdb_123 --metric db.status
"""

import argparse
import json
import sys
import os
import traceback

# -------------------------------------------------------
# 尝试导入 yaspy（YashanDB 官方 Python 驱动）
# -------------------------------------------------------
try:
    import yaspy
    DRIVER = "yaspy"
except ImportError:
    yaspy = None
    DRIVER = None

# -------------------------------------------------------
# 支持的监控指标定义
# -------------------------------------------------------
METRIC_HELP = """
支持的 metric_key 列表：

【实例状态】
  db.status              数据库实例状态（1=正常, 0=异常）
  db.version             数据库版本号
  db.uptime              数据库启动时长（秒）
  db.mode                数据库运行模式（PRIMARY/STANDBY）

【连接会话】
  db.sessions.active     当前活跃会话数
  db.sessions.total      当前总会话数
  db.sessions.waiting    当前等待中的会话数
  db.sessions.max        最大会话数限制

【内存】
  db.memory.buffer_pool_size    Buffer Pool 总大小（字节）
  db.memory.buffer_pool_used    Buffer Pool 已使用大小（字节）
  db.memory.buffer_pool_hit     Buffer Pool 命中率（%）
  db.memory.vm_pool_size        VM Pool 总大小（字节）
  db.memory.vm_pool_used        VM Pool 已使用大小（字节）

【存储 / 表空间】
  db.tablespace.discovery       表空间自动发现（JSON，用于 LLD）
  db.tablespace.total[{#TS}]    指定表空间总大小（字节）
  db.tablespace.used[{#TS}]     指定表空间已使用（字节）
  db.tablespace.free[{#TS}]     指定表空间剩余（字节）
  db.tablespace.pct_used[{#TS}] 指定表空间使用率（%）

【Redo / 日志】
  db.redo.flush_speed           Redo 刷盘速度（字节/秒）
  db.redo.free_space            Redo 空闲空间（字节）
  db.redo.checkpoint_lag        检查点落后量

【SQL 性能】
  db.sql.executions_per_sec     每秒 SQL 执行次数
  db.sql.avg_elapsed_ms         SQL 平均执行时长（ms）
  db.sql.slow_count             慢 SQL 数量（>1s）
  db.sql.parse_count            SQL 解析次数

【等待事件】
  db.wait.top_event             当前 TOP 等待事件名称
  db.wait.total_waits           总等待次数
  db.wait.time_waited_ms        总等待时间（ms）

【锁】
  db.lock.count                 当前锁数量
  db.lock.blocking_sessions     阻塞中的会话数

【系统统计】
  db.stat[<stat_name>]          从 V$SYSSTAT 查询指定统计项的值
                                 示例: db.stat[physical reads]
"""


def get_connection(host, port, user, password):
    """建立 YashanDB 数据库连接"""
    if yaspy is None:
        raise RuntimeError(
            "YashanDB Python 驱动 (yaspy) 未安装。\n"
            "请参考官方文档安装: pip install yashandb-python-driver"
        )
    dsn = f"{host}:{port}"
    conn = yaspy.connect(dsn=dsn, user=user, password=password)
    return conn


def query_one(conn, sql, params=None):
    """执行查询，返回第一行第一列"""
    cursor = conn.cursor()
    try:
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        cursor.close()


def query_all(conn, sql, params=None):
    """执行查询，返回所有行"""
    cursor = conn.cursor()
    try:
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return cursor.fetchall()
    finally:
        cursor.close()


# -------------------------------------------------------
# 各指标采集函数
# -------------------------------------------------------

def metric_db_status(conn):
    """数据库状态：1=正常，0=异常"""
    try:
        val = query_one(conn, "SELECT 1 FROM DUAL")
        return 1 if val == 1 else 0
    except Exception:
        return 0


def metric_db_version(conn):
    """数据库版本"""
    return query_one(conn, "SELECT VERSION FROM V$INSTANCE")


def metric_db_uptime(conn):
    """数据库启动时长（秒）"""
    # STARTUP_TIME 为启动时间戳，计算与当前时间差
    sql = """
        SELECT ROUND((SYSDATE - STARTUP_TIME) * 86400)
        FROM V$INSTANCE
    """
    return query_one(conn, sql)


def metric_db_mode(conn):
    """数据库模式"""
    return query_one(conn, "SELECT DATABASE_ROLE FROM V$DATABASE")


def metric_sessions_active(conn):
    """活跃会话数"""
    return query_one(conn,
        "SELECT COUNT(*) FROM V$SESSION WHERE STATUS = 'ACTIVE'")


def metric_sessions_total(conn):
    """总会话数"""
    return query_one(conn, "SELECT COUNT(*) FROM V$SESSION")


def metric_sessions_waiting(conn):
    """等待中的会话数"""
    return query_one(conn,
        "SELECT COUNT(*) FROM V$SESSION WHERE WAIT_CLASS != 'Idle'")


def metric_sessions_max(conn):
    """最大会话限制"""
    return query_one(conn,
        "SELECT VALUE FROM V$PARAMETER WHERE NAME = 'sessions'")


def metric_memory_buffer_pool_size(conn):
    """Buffer Pool 总大小（字节）"""
    row = query_one(conn,
        "SELECT BLOCK_SIZE * (FREE_BUFFERS + USED_BUFFERS) "
        "FROM V$BUFFER_POOL_STATISTICS")
    return row


def metric_memory_buffer_pool_used(conn):
    """Buffer Pool 已使用大小（字节）"""
    return query_one(conn,
        "SELECT BLOCK_SIZE * USED_BUFFERS FROM V$BUFFER_POOL_STATISTICS")


def metric_memory_buffer_pool_hit(conn):
    """Buffer Pool 命中率（%）"""
    sql = """
        SELECT ROUND(
            (1 - PHYSICAL_READS / GREATEST(DB_BLOCK_GETS + CONSISTENT_GETS, 1))
            * 100, 2
        ) FROM V$BUFFER_POOL_STATISTICS
    """
    return query_one(conn, sql)


def metric_memory_vm_pool_size(conn):
    """VM Pool 总大小（字节）"""
    return query_one(conn,
        "SELECT TOTAL_SIZE FROM V$VMSTAT")


def metric_memory_vm_pool_used(conn):
    """VM Pool 已使用（字节）"""
    return query_one(conn,
        "SELECT USED_SIZE FROM V$VMSTAT")


def metric_tablespace_discovery(conn):
    """表空间 LLD 自动发现，返回 JSON"""
    rows = query_all(conn,
        "SELECT TABLESPACE_NAME FROM DBA_TABLESPACES ORDER BY TABLESPACE_NAME")
    data = [{"{#TS}": row[0]} for row in rows]
    return json.dumps({"data": data})


def metric_tablespace_total(conn, ts_name):
    """指定表空间总大小（字节）"""
    return query_one(conn,
        "SELECT SUM(BYTES) FROM DBA_DATA_FILES WHERE TABLESPACE_NAME = ?",
        (ts_name.upper(),))


def metric_tablespace_used(conn, ts_name):
    """指定表空间已使用（字节）"""
    sql = """
        SELECT SUM(d.BYTES) - NVL(SUM(f.BYTES), 0)
        FROM DBA_DATA_FILES d
        LEFT JOIN DBA_FREE_SPACE f ON d.TABLESPACE_NAME = f.TABLESPACE_NAME
        WHERE d.TABLESPACE_NAME = ?
    """
    return query_one(conn, sql, (ts_name.upper(),))


def metric_tablespace_free(conn, ts_name):
    """指定表空间剩余（字节）"""
    return query_one(conn,
        "SELECT SUM(BYTES) FROM DBA_FREE_SPACE WHERE TABLESPACE_NAME = ?",
        (ts_name.upper(),))


def metric_tablespace_pct_used(conn, ts_name):
    """指定表空间使用率（%）"""
    total = metric_tablespace_total(conn, ts_name)
    free = metric_tablespace_free(conn, ts_name)
    if total and total > 0:
        used = total - (free or 0)
        return round(used / total * 100, 2)
    return 0


def metric_redo_flush_speed(conn):
    """Redo 刷盘速度（字节/秒）"""
    return query_one(conn, "SELECT FLUSH_SPEED FROM V$REDOSTAT")


def metric_redo_free_space(conn):
    """Redo 空闲空间（字节）"""
    return query_one(conn, "SELECT FREE_SPACE FROM V$REDOSTAT")


def metric_redo_checkpoint_lag(conn):
    """检查点落后量"""
    return query_one(conn, "SELECT CHECKPOINT_LAG FROM V$REDOSTAT")


def metric_sql_executions_per_sec(conn):
    """每秒 SQL 执行次数"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME = 'execute count'")


def metric_sql_avg_elapsed_ms(conn):
    """SQL 平均执行时长（ms）"""
    sql = """
        SELECT ROUND(AVG(ELAPSED_TIME) / 1000, 2)
        FROM V$SQL
        WHERE EXECUTIONS > 0
    """
    return query_one(conn, sql)


def metric_sql_slow_count(conn):
    """慢 SQL 数量（执行时间 > 1s）"""
    return query_one(conn,
        "SELECT COUNT(*) FROM V$SQL "
        "WHERE ELAPSED_TIME > 1000000 AND EXECUTIONS > 0")


def metric_sql_parse_count(conn):
    """SQL 解析次数"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME = 'parse count (total)'")


def metric_wait_top_event(conn):
    """当前 TOP 等待事件"""
    return query_one(conn,
        "SELECT EVENT FROM V$SYSTEM_EVENT "
        "ORDER BY TOTAL_WAITS DESC FETCH FIRST 1 ROWS ONLY")


def metric_wait_total_waits(conn):
    """总等待次数"""
    return query_one(conn,
        "SELECT SUM(TOTAL_WAITS) FROM V$SYSTEM_EVENT "
        "WHERE WAIT_CLASS != 'Idle'")


def metric_wait_time_waited_ms(conn):
    """总等待时间（ms）"""
    return query_one(conn,
        "SELECT ROUND(SUM(TIME_WAITED) / 100, 2) FROM V$SYSTEM_EVENT "
        "WHERE WAIT_CLASS != 'Idle'")


def metric_lock_count(conn):
    """当前锁数量"""
    return query_one(conn, "SELECT COUNT(*) FROM V$LOCK")


def metric_lock_blocking_sessions(conn):
    """阻塞中的会话数"""
    return query_one(conn,
        "SELECT COUNT(DISTINCT BLOCKING_SESSION) FROM V$SESSION "
        "WHERE BLOCKING_SESSION IS NOT NULL")


def metric_sysstat(conn, stat_name):
    """从 V$SYSSTAT 查询指定统计项"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE LOWER(NAME) = LOWER(?)",
        (stat_name,))


# -------------------------------------------------------
# 指标路由分发
# -------------------------------------------------------

def collect_metric(conn, metric_key):
    """根据 metric_key 调用对应采集函数"""

    # 带参数的指标（格式：metric_key[param]）
    if "[" in metric_key and metric_key.endswith("]"):
        base_key, param = metric_key[:-1].split("[", 1)
    else:
        base_key = metric_key
        param = None

    dispatch = {
        "db.status":                    lambda: metric_db_status(conn),
        "db.version":                   lambda: metric_db_version(conn),
        "db.uptime":                    lambda: metric_db_uptime(conn),
        "db.mode":                      lambda: metric_db_mode(conn),
        "db.sessions.active":           lambda: metric_sessions_active(conn),
        "db.sessions.total":            lambda: metric_sessions_total(conn),
        "db.sessions.waiting":          lambda: metric_sessions_waiting(conn),
        "db.sessions.max":              lambda: metric_sessions_max(conn),
        "db.memory.buffer_pool_size":   lambda: metric_memory_buffer_pool_size(conn),
        "db.memory.buffer_pool_used":   lambda: metric_memory_buffer_pool_used(conn),
        "db.memory.buffer_pool_hit":    lambda: metric_memory_buffer_pool_hit(conn),
        "db.memory.vm_pool_size":       lambda: metric_memory_vm_pool_size(conn),
        "db.memory.vm_pool_used":       lambda: metric_memory_vm_pool_used(conn),
        "db.tablespace.discovery":      lambda: metric_tablespace_discovery(conn),
        "db.tablespace.total":          lambda: metric_tablespace_total(conn, param),
        "db.tablespace.used":           lambda: metric_tablespace_used(conn, param),
        "db.tablespace.free":           lambda: metric_tablespace_free(conn, param),
        "db.tablespace.pct_used":       lambda: metric_tablespace_pct_used(conn, param),
        "db.redo.flush_speed":          lambda: metric_redo_flush_speed(conn),
        "db.redo.free_space":           lambda: metric_redo_free_space(conn),
        "db.redo.checkpoint_lag":       lambda: metric_redo_checkpoint_lag(conn),
        "db.sql.executions_per_sec":    lambda: metric_sql_executions_per_sec(conn),
        "db.sql.avg_elapsed_ms":        lambda: metric_sql_avg_elapsed_ms(conn),
        "db.sql.slow_count":            lambda: metric_sql_slow_count(conn),
        "db.sql.parse_count":           lambda: metric_sql_parse_count(conn),
        "db.wait.top_event":            lambda: metric_wait_top_event(conn),
        "db.wait.total_waits":          lambda: metric_wait_total_waits(conn),
        "db.wait.time_waited_ms":       lambda: metric_wait_time_waited_ms(conn),
        "db.lock.count":                lambda: metric_lock_count(conn),
        "db.lock.blocking_sessions":    lambda: metric_lock_blocking_sessions(conn),
        "db.stat":                      lambda: metric_sysstat(conn, param),
    }

    if base_key not in dispatch:
        raise ValueError(f"未知的监控指标: {metric_key}\n\n{METRIC_HELP}")

    return dispatch[base_key]()


# -------------------------------------------------------
# 主入口
# -------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="YashanDB Zabbix Monitor Plugin v1.0.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=METRIC_HELP
    )
    parser.add_argument("--host",     required=True,  help="YashanDB 主机地址")
    parser.add_argument("--port",     required=False, default="1688",
                        help="YashanDB 端口（默认 1688）")
    parser.add_argument("--user",     required=True,  help="数据库用户名")
    parser.add_argument("--password", required=True,  help="数据库密码")
    parser.add_argument("--metric",   required=True,  help="监控指标 key")
    parser.add_argument("--timeout",  required=False, default="10",
                        help="连接超时秒数（默认 10）")
    # 支持从配置文件读取连接信息
    parser.add_argument("--config",   required=False, default=None,
                        help="连接配置文件路径（INI格式），优先级低于命令行参数")
    return parser.parse_args()


def load_config(config_path):
    """从 INI 配置文件加载连接参数"""
    import configparser
    cfg = configparser.ConfigParser()
    cfg.read(config_path, encoding="utf-8")
    section = "yashandb"
    if section not in cfg:
        return {}
    return dict(cfg[section])


def main():
    args = parse_args()

    # 配置文件兜底
    config = {}
    if args.config and os.path.isfile(args.config):
        config = load_config(args.config)

    host     = args.host     or config.get("host", "127.0.0.1")
    port     = args.port     or config.get("port", "1688")
    user     = args.user     or config.get("user", "sys")
    password = args.password or config.get("password", "")
    metric   = args.metric

    conn = None
    try:
        # db.status 在连接失败时直接返回 0
        try:
            conn = get_connection(host, port, user, password)
        except Exception as e:
            if metric == "db.status":
                print(0)
                return
            raise

        result = collect_metric(conn, metric)

        if result is None:
            # Zabbix 对空值不友好，返回 0 或空字符串
            print(0)
        else:
            print(result)

    except Exception as e:
        # Zabbix agent 要求脚本失败时输出到 stderr，stdout 返回 ZBX_NOTSUPPORTED
        sys.stderr.write(f"ERROR: {e}\n")
        # 对于状态类指标，连接失败返回 0
        if metric == "db.status":
            print(0)
        else:
            print("ZBX_NOTSUPPORTED")
        sys.exit(1)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
