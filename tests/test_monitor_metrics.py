"""
测试 yashandb_monitor.py 的指标采集函数

运行：
    pytest tests/test_monitor_metrics.py -v
    pytest tests/test_monitor_metrics.py -v -k "session"  # 只测会话相关
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import yashandb_monitor as m


# ---------------------------------------------------------------------------
# 1. 基础：连接函数
# ---------------------------------------------------------------------------

class TestConnection:
    """基础连接函数测试"""

    def test_get_connection_no_yaspy(self, monkeypatch):
        """无 yaspy 时应抛出 RuntimeError"""
        monkeypatch.setattr(m, "yaspy", None)
        with pytest.raises(RuntimeError, match="yaspy"):
            m.get_connection("127.0.0.1", "1688", "sys", "pass")

    def test_collect_metric_dispatch_no_error(self, mock_conn):
        """collect_metric 对任意已知 key 不抛异常（路由正确）"""
        for key in [
            "yashandb.db.status",
            "yashandb.db.version",
            "yashandb.active_sessions",
        ]:
            # 只要不抛异常就说明 dispatch 路由正确
            try:
                m.collect_metric(mock_conn, key)
            except Exception as e:
                pytest.fail(f"{key} 路由失败: {e}")


# ---------------------------------------------------------------------------
# 2. collect_metric 路由测试（参数化覆盖所有指标）
# ---------------------------------------------------------------------------

class TestCollectMetricDispatch:
    """验证 collect_metric 能正确分发到每个指标函数"""

    @pytest.mark.parametrize("metric_key", [
        # ---- 原生指标 ----
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
        # ---- Datadog 兼容指标 ----
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
    ])
    def test_collect_metric_dispatches_without_error(self, mock_conn, metric_key):
        """
        每个指标都能被 dispatch 识别并执行（不验证返回值类型，只验证不抛异常）。
        这是最基本的回归测试：指标函数存在且可调用。
        """
        # 不带参数的 key
        result = m.collect_metric(mock_conn, metric_key)
        # 不应返回 ZBX_NOTSUPPORTED 或抛出异常
        assert result != "ZBX_NOTSUPPORTED"

    def test_collect_metric_unknown_key_raises(self, mock_conn):
        """未知指标应抛出 ValueError"""
        with pytest.raises(ValueError, match="未知的监控指标"):
            m.collect_metric(mock_conn, "yashandb.nonexistent")

    def test_collect_metric_param_format(self, mock_conn):
        """带参数指标：格式 key[param]"""
        result = m.collect_metric(mock_conn, "yashandb.db.tablespace.total[MAIN]")
        assert result != "ZBX_NOTSUPPORTED"


# ---------------------------------------------------------------------------
# 3. 各指标函数返回值类型测试
# ---------------------------------------------------------------------------

class TestMetricReturnTypes:
    """
    验证指标返回值类型符合预期。
    mock 数据只保证基本返回，类型检查依赖指标函数本身逻辑。
    """

    def test_db_status_returns_int(self, mock_conn):
        """db.status 应返回 0 或 1"""
        val = m.collect_metric(mock_conn, "yashandb.db.status")
        assert isinstance(val, int)
        assert val in (0, 1)

    def test_db_uptime_returns_int(self, mock_conn):
        """db.uptime 应返回整数（秒）"""
        val = m.collect_metric(mock_conn, "yashandb.db.uptime")
        assert isinstance(val, int)
        assert val >= 0

    def test_session_counts_return_int(self, mock_conn):
        for key in [
            "yashandb.db.sessions.active",
            "yashandb.db.sessions.total",
            "yashandb.db.sessions.waiting",
            "yashandb.db.sessions.max",
            "yashandb.active_background",
            "yashandb.active_sessions",
            "yashandb.session_count",
            "yashandb.user_sessions",
        ]:
            val = m.collect_metric(mock_conn, key)
            assert isinstance(val, int), f"{key} 应返回 int，实际 {type(val)}"
            assert val >= 0, f"{key} 应 >= 0"

    def test_percentage_metrics_return_numeric(self, mock_conn):
        """百分比指标应返回数值（int 或 float）"""
        for key in [
            "yashandb.db.memory.buffer_pool_hit",
            "yashandb.memory_sorts_ratio",
            "yashandb.buffer_cachehit_ratio",
            "yashandb.process_limit",
            "yashandb.session_limit_usage",
            "yashandb.shared_pool_free",
            "yashandb.redo_allocation_hit_ratio",
            "yashandb.host_cpu_utilization",
            "yashandb.tablespace.in_use",
            "yashandb.db.tablespace.pct_used[MAIN]",
        ]:
            val = m.collect_metric(mock_conn, key)
            assert isinstance(val, (int, float)), \
                f"{key} 应返回 numeric，实际 {type(val)}"

    def test_memory_metrics_return_numeric(self, mock_conn):
        """内存指标应返回正数"""
        for key in [
            "yashandb.db.memory.buffer_pool_size",
            "yashandb.db.memory.buffer_pool_used",
            "yashandb.db.memory.vm_pool_size",
            "yashandb.db.memory.vm_pool_used",
            "yashandb.physical_memory_gb",
            "yashandb.shared_memory_size",
            "yashandb.process.pga_allocated_memory",
            "yashandb.process.pga_used_memory",
        ]:
            val = m.collect_metric(mock_conn, key)
            assert isinstance(val, (int, float)), f"{key} 应返回 numeric"
            assert val >= 0, f"{key} 应 >= 0"

    def test_tablespace_metrics_return_numeric(self, mock_conn):
        """表空间指标应返回正数或 JSON"""
        for key in [
            "yashandb.tablespace.size",
            "yashandb.tablespace.used",
            "yashandb.tablespace.maxsize",
        ]:
            val = m.collect_metric(mock_conn, key)
            assert isinstance(val, (int, float)), f"{key} 应返回 numeric"

    def test_tablespace_discovery_returns_json(self, mock_conn):
        """表空间发现应返回 JSON 字符串"""
        import json
        val = m.collect_metric(mock_conn, "yashandb.tablespace.discovery")
        data = json.loads(val)
        assert "data" in data

    def test_lock_metrics_return_int(self, mock_conn):
        for key in [
            "yashandb.db.lock.count",
            "yashandb.db.lock.blocking_sessions",
        ]:
            val = m.collect_metric(mock_conn, key)
            assert isinstance(val, int), f"{key} 应返回 int"
            assert val >= 0

    def test_gc_metrics_return_int(self, mock_conn):
        """单机 RAC 指标应返回 0"""
        for key in [
            "yashandb.gc_average_cr_get_time",
            "yashandb.gc_average_current_get_time",
        ]:
            val = m.collect_metric(mock_conn, key)
            assert isinstance(val, (int, float))


# ---------------------------------------------------------------------------
# 4. main() 函数异常处理测试
# ---------------------------------------------------------------------------

class TestMainFunction:
    """测试 main() 的错误处理路径"""

    def test_status_metric_when_conn_fails(self, monkeypatch):
        """
        连接失败时，yashandb.db.status 应返回 0（ZBabbix 健康检查期望行为）
        """
        import yashandb_monitor as mm

        # 模拟连接失败
        def fake_get_connection(*a, **kw):
            raise RuntimeError("connection refused")

        monkeypatch.setattr(mm, "get_connection", fake_get_connection)
        monkeypatch.setattr(sys, "argv", [
            "yashandb_monitor.py",
            "--host", "127.0.0.1",
            "--port", "1688",
            "--user", "sys",
            "--password", "wrong",
            "--metric", "yashandb.db.status",
        ])

        # capture stdout
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            mm.main()
            output = sys.stdout.getvalue().strip()
        finally:
            sys.stdout = old_stdout

        assert output == "0", "连接失败时 db.status 应输出 0"

    def test_unknown_metric_exits_with_error(self, monkeypatch):
        """未知指标应输出 ZBX_NOTSUPPORTED 并以错误码退出"""
        import yashandb_monitor as mm

        # 不需要真实连接就能测
        captured = {}

        def fake_get_connection(*a, **kw):
            class FakeConn:
                def cursor(self):
                    class FakeCur:
                        def execute(self, *a): pass
                        def fetchone(self): return None
                        def close(self): pass
                    return FakeCur()
                def close(self): pass
            captured["conn"] = FakeConn()
            return captured["conn"]

        monkeypatch.setattr(mm, "get_connection", fake_get_connection)
        monkeypatch.setattr(sys, "argv", [
            "yashandb_monitor.py",
            "--host", "127.0.0.1",
            "--port", "1688",
            "--user", "sys",
            "--password", "pass",
            "--metric", "yashandb.db.nonexistent",
        ])

        import io
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        captured_out = ""
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        try:
            with pytest.raises(SystemExit) as exc_info:
                mm.main()
            # 错误码 1
            assert exc_info.value.code == 1
            # 捕获 stdout 值（在恢复之前）
            captured_out = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        assert "ZBX_NOTSUPPORTED" in captured_out, \
            f"期望 stdout 含 ZBX_NOTSUPPORTED，实际: {captured_out!r}"


# ---------------------------------------------------------------------------
# 5. 空值（None）处理
# ---------------------------------------------------------------------------

class TestNullHandling:
    """测试 query 返回 None 时的处理"""

    def test_collect_metric_with_null_result(self, mock_conn):
        """
        如果 SQL 查询返回 NULL（None），collect_metric 应能继续执行，
        main() 应输出 0（Zabbix 不理解 None）
        """
        import yashandb_monitor as mm

        # 手动用 None cursor 测试
        cursor = mock_conn.cursor()
        cursor._rows = []  # 空结果 → fetchone → None
        cursor._side_effect = lambda sql, p: []  # 强制空

        # 模拟 main 行为
        val = mm.collect_metric(mock_conn, "yashandb.db.version")
        # query_one 对空结果返回 None，collect_metric 透传 None
        # main() 会把 None 打印为 0
        # 这个测试只验证不抛异常
        assert val is None or isinstance(val, str)
