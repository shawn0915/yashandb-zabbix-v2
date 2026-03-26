#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YashanDB Zabbix 批量采集脚本
一次性采集所有常用指标并输出为 JSON，用于 Zabbix Trapper 或调试诊断

用法:
    python yashandb_bulk.py --host 127.0.0.1 --port 1688 \
        --user sys --password yasdb_123
"""

import argparse
import json
import sys
import os

# 将 scripts 目录加入模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yashandb_monitor import get_connection, collect_metric


BULK_METRICS = [
    "db.status",
    "db.version",
    "db.uptime",
    "db.mode",
    "db.sessions.active",
    "db.sessions.total",
    "db.sessions.waiting",
    "db.sessions.max",
    "db.memory.buffer_pool_size",
    "db.memory.buffer_pool_used",
    "db.memory.buffer_pool_hit",
    "db.memory.vm_pool_size",
    "db.memory.vm_pool_used",
    "db.redo.flush_speed",
    "db.redo.free_space",
    "db.redo.checkpoint_lag",
    "db.sql.executions_per_sec",
    "db.sql.avg_elapsed_ms",
    "db.sql.slow_count",
    "db.sql.parse_count",
    "db.wait.total_waits",
    "db.wait.time_waited_ms",
    "db.wait.top_event",
    "db.lock.count",
    "db.lock.blocking_sessions",
]


def main():
    parser = argparse.ArgumentParser(description="YashanDB Zabbix 批量采集")
    parser.add_argument("--host",     required=True)
    parser.add_argument("--port",     default="1688")
    parser.add_argument("--user",     required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--json",     action="store_true",
                        help="以 JSON 格式输出（默认 key=value）")
    args = parser.parse_args()

    results = {}
    errors = {}

    try:
        conn = get_connection(args.host, args.port, args.user, args.password)
    except Exception as e:
        print(json.dumps({"error": str(e), "db.status": 0}))
        sys.exit(1)

    for metric in BULK_METRICS:
        try:
            val = collect_metric(conn, metric)
            results[metric] = val if val is not None else 0
        except Exception as e:
            errors[metric] = str(e)
            results[metric] = "ERROR"

    try:
        conn.close()
    except Exception:
        pass

    if args.json:
        output = {"metrics": results}
        if errors:
            output["errors"] = errors
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        for k, v in results.items():
            print(f"{k} = {v}")
        if errors:
            print("\n--- ERRORS ---", file=sys.stderr)
            for k, v in errors.items():
                print(f"{k}: {v}", file=sys.stderr)


if __name__ == "__main__":
    main()
