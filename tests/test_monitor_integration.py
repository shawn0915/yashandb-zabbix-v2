"""
集成测试：在真实 YashanDB Docker 上运行所有指标

前置条件：
    1. YashanDB Docker 容器正在运行
    2. yaspy 已安装：pip install yashandb-python-driver
    3. 设置环境变量：
       set YAS_ZABBIX_TEST_LIVE=1
       set YAS_PASSWORD=yourpassword

运行：
    pytest tests/test_monitor_integration.py -v  # 自动 skip（需启用）
    pytest tests/ -v -m integration               # 仅集成测试（需启用）
    pytest tests/ -v -m "not integration"          # 仅单元测试（默认）
"""
import json
import pytest
import sys
import os

# 标记本模块所有测试为 integration（可通过 -m integration 过滤）
pytestmark = pytest.mark.integration

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import yashandb_monitor as m

ALL_METRIC_KEYS = [
    # 原生
    "yashandb.db.status",
    "yashandb.db.version",
    "yashandb.db.uptime",
    "yashandb.db.mode",
    "yashandb.db.sessions.active",
    "yashandb.db.sessions.total",
    "yashandb.db.sessions.waiting",
    "yashandb.db.sessions.max",
    "yashandb.db.memory.buffer_pool_size",
    "yashandb.db.memory.buffer_pool_used",
    "yashandb.db.memory.buffer_pool_hit",
    "yashandb.db.memory.vm_pool_size",
    "yashandb.db.memory.vm_pool_used",
    "yashandb.db.redo.flush_speed",
    "yashandb.db.redo.free_space",
    "yashandb.db.redo.checkpoint_lag",
    "yashandb.db.sql.executions_per_sec",
    "yashandb.db.sql.avg_elapsed_ms",
    "yashandb.db.sql.slow_count",
    "yashandb.db.sql.parse_count",
    "yashandb.db.wait.top_event",
    "yashandb.db.wait.total_waits",
    "yashandb.db.wait.time_waited_ms",
    "yashandb.db.lock.count",
    "yashandb.db.lock.blocking_sessions",
    # Datadog 兼容
    "yashandb.active_background",
    "yashandb.active_sessions",
    "yashandb.process_limit",
    "yashandb.session_count",
    "yashandb.session_limit_usage",
    "yashandb.user_sessions",
    "yashandb.hard_parses",
    "yashandb.memory_sorts_ratio",
    "yashandb.buffer_cachehit_ratio",
    "yashandb.cache_blocks_lost",
    "yashandb.physical_memory_gb",
    "yashandb.shared_memory_size",
    "yashandb.shared_pool_free",
    "yashandb.process.pga_allocated_memory",
    "yashandb.process.pga_freeable_memory",
    "yashandb.process.pga_max_memory",
    "yashandb.process.pga_used_memory",
    "yashandb.physical_reads",
    "yashandb.physical_writes",
    "yashandb.consistent_read_changes",
    "yashandb.db_block_changes",
    "yashandb.logical_reads",
    "yashandb.disk_sorts",
    "yashandb.sorts_per_user_call",
    "yashandb.redo_allocation_hit_ratio",
    "yashandb.redo_generated",
    "yashandb.redo_writes",
    "yashandb.dbwr_checkpoints",
    "yashandb.user_commits",
    "yashandb.user_rollbacks",
    "yashandb.host_cpu_utilization",
    "yashandb.num_cpus",
    "yashandb.os_load",
    "yashandb.avg_synchronous_single_block_read_latency",
    "yashandb.network_traffic_volume",
    "yashandb.branch_node_splits",
    "yashandb.leaf_node_splits",
    "yashandb.tablespace.in_use",
    "yashandb.tablespace.maxsize",
    "yashandb.tablespace.offline",
    "yashandb.tablespace.size",
    "yashandb.tablespace.used",
    "yashandb.gc_average_cr_get_time",
    "yashandb.gc_average_current_get_time",
]

PARAM_METRIC_KEYS = [
    "yashandb.db.tablespace.discovery",
    "yashandb.tablespace.discovery",
    "yashandb.db.tablespace.total[MAIN]",
    "yashandb.db.tablespace.used[MAIN]",
    "yashandb.db.tablespace.free[MAIN]",
    "yashandb.db.tablespace.pct_used[MAIN]",
    "yashandb.tablespace.total[MAIN]",
    "yashandb.tablespace.used[MAIN]",
    "yashandb.tablespace.free[MAIN]",
    "yashandb.tablespace.pct_used[MAIN]",
    "yashandb.db.stat[physical reads]",
]


class TestLiveDBBasic:
    """基础连接测试"""

    def test_db_status_ok(self, live_conn):
        """数据库状态应为 1"""
        val = m.collect_metric(live_conn, "yashandb.db.status")
        assert val == 1, f"数据库状态应为 1，实际 {val}"

    def test_db_version_is_string(self, live_conn):
        """数据库版本应为非空字符串"""
        val = m.collect_metric(live_conn, "yashandb.db.version")
        assert isinstance(val, str) and len(val) > 0, \
            f"version 应为非空字符串，实际 {val}"

    def test_db_uptime_is_positive(self, live_conn):
        """数据库启动时长应为正整数（秒）"""
        val = m.collect_metric(live_conn, "yashandb.db.uptime")
        assert isinstance(val, int) and val > 0, \
            f"uptime 应为正整数，实际 {val}"


class TestLiveDBMetrics:
    """
    所有指标在真实数据库上执行并验证返回值。
    """

    @pytest.mark.parametrize("metric_key", ALL_METRIC_KEYS)
    def test_metric_executes_without_error(self, live_conn, metric_key):
        """每个指标在真实数据库上执行不抛异常"""
        result = m.collect_metric(live_conn, metric_key)
        assert result != "ZBX_NOTSUPPORTED", \
            f"{metric_key} 在真实 DB 上返回 ZBX_NOTSUPPORTED"

    @pytest.mark.parametrize("metric_key", PARAM_METRIC_KEYS)
    def test_param_metric_executes_without_error(self, live_conn, metric_key):
        """带参数的指标同样在真实 DB 上验证"""
        result = m.collect_metric(live_conn, metric_key)
        assert result != "ZBX_NOTSUPPORTED"


class TestLiveDBReturnTypes:
    """验证关键指标的返回值类型符合 Zabbix 期望"""

    def test_session_counts_are_int(self, live_conn):
        for key in ["yashandb.db.sessions.active",
                    "yashandb.db.sessions.total",
                    "yashandb.active_sessions"]:
            val = m.collect_metric(live_conn, key)
            assert isinstance(val, int), f"{key} 应返回 int，实际 {type(val)}"
            assert val >= 0, f"{key} 应 >= 0"

    def test_memory_metrics_are_numeric_positive(self, live_conn):
        for key in ["yashandb.physical_memory_gb",
                    "yashandb.shared_memory_size"]:
            val = m.collect_metric(live_conn, key)
            assert isinstance(val, (int, float)), f"{key} 应返回 numeric"
            assert val > 0, f"{key} 应 > 0"

    def test_pct_metrics_in_valid_range(self, live_conn):
        pct_keys = [
            "yashandb.host_cpu_utilization",
            "yashandb.tablespace.in_use",
            "yashandb.db.memory.buffer_pool_hit",
        ]
        for key in pct_keys:
            val = m.collect_metric(live_conn, key)
            if val is not None:
                assert 0 <= val <= 100, f"{key} 应在 0~100，实际 {val}"


class TestLiveDBTablespaceDiscovery:
    """表空间 LLD 发现测试"""

    def test_discovery_returns_valid_json(self, live_conn):
        """LLD 发现返回有效的 Zabbix LLD JSON 格式"""
        val = m.collect_metric(live_conn, "yashandb.tablespace.discovery")
        data = json.loads(val)
        assert "data" in data
        assert isinstance(data["data"], list)
        for item in data["data"]:
            assert "{#TS}" in item, "LLD 条目应包含 {#TS}"
