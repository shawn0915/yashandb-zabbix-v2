"""
pytest 配置与共享 fixtures

用法:
    # 单元测试（mock 连接）
    pytest tests/test_monitor_metrics.py -v

    # 集成测试（真实数据库）
    pytest tests/test_monitor_integration.py -v --live-db

    # 跳过集成测试运行全部
    pytest tests/ -v -m "not integration"
"""
import os
import sys

import pytest

# 确保 monitor 模块可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


# ---------------------------------------------------------------------------
# Mock cursor / connection（用于单元测试）
# ---------------------------------------------------------------------------


class MockCursor:
    """模拟 DB-API 2.0 cursor"""

    def __init__(self, rows=None, side_effect=None):
        # rows: list of tuple — fetchone/fetchall 返回值
        # side_effect: callable(sql, params) -> rows
        self._rows = rows or []
        self._side_effect = side_effect
        self.executed_sqls = []

    def execute(self, sql, params=None):
        self.executed_sqls.append((sql, params))
        if self._side_effect:
            self._rows = self._side_effect(sql, params) or []

    def fetchone(self):
        if self._rows:
            return self._rows[0]
        return None

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class MockConnection:
    """模拟数据库连接"""

    def __init__(self, cursor=None, side_effect=None):
        self._cursor = cursor or MockCursor(side_effect=side_effect)
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def side_effect(sql, params):
    """根据 SQL 猜测对应的 mock 数据"""
    sql_upper = sql.upper()
    # 简化匹配：按关键字猜测
    if "V$SYSSTAT" in sql_upper:
        return [(1000,)]

    if "V$BUFFER_POOL_STATISTICS" in sql_upper:
        return [(100, 900, 1000)]
    if "V$SESSION" in sql_upper:
        return [(1,)]
    if "V$PROCESS" in sql_upper:
        return [(1,)]
    if "DBA_TABLESPACES" in sql_upper:
        return [("MAIN",)]
    if "DBA_DATA_FILES" in sql_upper:
        return [(1048576000,)]
    if "DBA_FREE_SPACE" in sql_upper:
        return [(524288000,)]
    if "V$INSTANCE" in sql_upper:
        if "SYSDATE" in sql_upper or "STARTUP_TIME" in sql_upper:
            return [(3600,)]          # uptime: 1小时（秒）
        return [("23.4.7.100",)]      # VERSION 列
    if "V$DATABASE" in sql_upper:
        return [("PRIMARY",)]
    if "V$OSSTAT" in sql_upper:
        return [(15,)]
    if "V$SGA" in sql_upper:
        return [(1073741824,)]
    if "V$SGASTAT" in sql_upper:
        return [(107374182, 314572800)]
    if "V$REDOSTAT" in sql_upper:
        return [(102400, 104857600, 0)]
    if "V$SQL" in sql_upper:
        return [(1, 5200)]
    if "V$SYSTEM_EVENT" in sql_upper:
        return [("db file sequential read", 10000, 85000)]
    if "V$LOCK" in sql_upper:
        return [(5,)]
    if "V$PARAMETER" in sql_upper:
        return [(200,)]
    if "V$VMSTAT" in sql_upper:
        return [(268435456, 134217728)]
    return [(1,)]


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_conn():
    """返回 MockConnection（用于单元测试）"""
    return MockConnection(side_effect=side_effect)


@pytest.fixture
def live_conn(request):
    """
    返回真实数据库连接（需 YashanDB Docker 在运行）。
    仅在传入 --live-db 参数时激活：
        pytest tests/ --live-db
    """
    # 检查是否标记为 integration 且启用了 --live-db
    marker = request.node.get_closest_marker("integration")
    if marker is None:
        pytest.skip("not an integration test")

    if not os.environ.get("YAS_ZABBIX_TEST_LIVE"):
        pytest.skip("set YAS_ZABBIX_TEST_LIVE=1 to run integration tests")

    try:
        import yaspy
    except ImportError:
        pytest.skip("yaspy not installed")

    password = os.environ.get("YAS_PASSWORD", "")
    if not password:
        pytest.skip("YAS_PASSWORD env not set")

    conn = yaspy.connect(
        dsn="127.0.0.1:1688",
        user="sys",
        password=password,
    )
    yield conn
    try:
        conn.close()
    except Exception:
        pass

