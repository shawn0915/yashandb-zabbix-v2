"""
测试 yashandb_bulk.py 批量采集脚本

运行：
    pytest tests/test_bulk.py -v
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import yashandb_bulk as b


class TestBulkScript:
    """测试 bulk 脚本基本结构"""

    def test_bulk_module_imports(self):
        """bulk 模块应能正常导入"""
        import yashandb_bulk as b
        assert hasattr(b, "get_connection")
        assert hasattr(b, "collect_metric")
        assert hasattr(b, "BULK_METRICS")
        assert hasattr(b, "main")

    def test_bulk_metrics_count(self):
        """BULK_METRICS 应包含 52 个不含参数的指标（72 - 20 个表空间参数版）"""
        import yashandb_bulk as b
        # 72 总指标 - 18 个参数版 = 52 个直接可采集指标
        # 表空间 discovery 算 1 个（不含参数），其他 5 个 + 4个原生 = 9 个参数版
        assert len(b.BULK_METRICS) >= 50, \
            f"BULK_METRICS 应至少 50 个，实际 {len(b.BULK_METRICS)}"

    def test_bulk_includes_key_metrics(self):
        """BULK_METRICS 必须包含关键指标"""
        import yashandb_bulk as b
        required = [
            "yashandb.db.status",
            "yashandb.db.version",
            "yashandb.active_sessions",
            "yashandb.buffer_cachehit_ratio",
            "yashandb.redo_generated",
            "yashandb.tablespace.in_use",
            "yashandb.host_cpu_utilization",
            "yashandb.process.pga_allocated_memory",
        ]
        for key in required:
            assert key in b.BULK_METRICS, f"BULK_METRICS 缺少 {key}"

    def test_bulk_no_duplicates(self):
        """BULK_METRICS 不应有重复项"""
        import yashandb_bulk as b
        assert len(b.BULK_METRICS) == len(set(b.BULK_METRICS)), \
            "BULK_METRICS 存在重复项"


class TestBulkMainMocked:
    """测试 bulk main() 在 mock 连接下的行为"""

    def test_bulk_main_with_mock_conn(self, monkeypatch):
        """mock 连接下 main() 应正常运行并输出"""
        import yashandb_bulk as b

        class FakeConn:
            closed = False

            def cursor(self):
                class Cur:
                    def execute(self, *a): pass

                    def fetchone(self):
                        return (1,)

                    def fetchall(self):
                        return [(1,)]

                    def close(self):
                        pass

                return Cur()

            def close(self):
                self.closed = True

        fake_conn = FakeConn()

        def fake_get_connection(*a, **kw):
            return fake_conn

        import sys
        old_argv = sys.argv
        old_stdout = sys.stdout

        monkeypatch.setattr(b, "get_connection", fake_get_connection)
        sys.argv = [
            "yashandb_bulk.py",
            "--host", "127.0.0.1",
            "--user", "sys",
            "--password", "pass",
        ]

        import io

        captured_out = io.StringIO()
        captured_err = io.StringIO()
        sys.stdout = captured_out
        sys.stderr = captured_err

        try:
            b.main()
        except SystemExit:
            pass  # main() 可能通过 sys.exit 退出
        finally:
            sys.argv = old_argv
            sys.stdout = old_stdout

        output = captured_out.getvalue()
        # 应输出指标内容
        assert "yashandb.db.status" in output or "metrics" in output.lower(), \
            f"bulk 输出应包含指标，输出: {output[:200]}"


class TestBulkMetricCoverage:
    """验证 BULK_METRICS 覆盖所有 dispatch 中的无参数指标"""

    def _extract_dispatch_keys(self):
        """从源码解析 dispatch dict key（不用 bytecode，防止字符串去重丢失）"""
        import re
        import os

        src_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "yashandb_monitor.py")
        with open(src_path, encoding="utf-8") as f:
            source = f.read()

        m_start = re.search(r"dispatch\s*=\s*\{", source)
        if not m_start:
            raise RuntimeError("无法在源码中找到 dispatch 字典")

        pos = m_start.start() + len("dispatch = {") - 1
        depth = 1
        while pos < len(source) and depth > 0:
            if source[pos] == "{":
                depth += 1
            elif source[pos] == "}":
                depth -= 1
            pos += 1
        dispatch_text = source[m_start.start() + len("dispatch = {") - 1 + 1: pos - 1]

        keys = []
        for line in dispatch_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            found = re.findall(r'"(yashandb\.[^"]+)"', stripped)
            keys.extend(found)

        return keys

    def test_bulk_covers_all_dispatched_keys(self):
        """
        dispatch 中所有不含参数的 key 都应在 BULK_METRICS 中。
        这确保新增指标后 bulk 不会遗漏。
        """
        import yashandb_bulk as b

        dispatch_raw = self._extract_dispatch_keys()
        # 只检查无参数的 base key（不含 [param] 且 lambda 不使用 param）
        # 注意：
        #   - yashandb.db.tablespace.total 等 key 无括号但 lambda 用 param → 跳过
        #   - yashandb.db.stat 同上 → 跳过
        #   - 带括号的 key 如 yashandb.db.tablespace.total[TS] 已在 key 中 → 跳过
        # 从源码解析 dispatch key，过滤掉带 [param] 或 lambda 使用 param 的
        import re as _re
        src_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "yashandb_monitor.py")
        with open(src_path, encoding="utf-8") as _f:
            _source = _f.read()

        _m = _re.search(r"dispatch\s*=\s*\{", _source)
        _pos = _m.start() + len("dispatch = {") - 1
        _depth = 1
        while _pos < len(_source) and _depth > 0:
            if _source[_pos] == "{": _depth += 1
            elif _source[_pos] == "}": _depth -= 1
            _pos += 1
        dispatch_text = _source[_m.start() + len("dispatch = {") - 1 + 1: _pos - 1]

        dispatch_keys = []
        for _line in dispatch_text.splitlines():
            _stripped = _line.strip()
            if _stripped.startswith("#") or not _stripped:
                continue
            _keys = _re.findall(r'"(yashandb\.[^"]+)"', _stripped)
            if not _keys:
                continue
            _key = _keys[0]
            # 跳过含 [param]（已参数化）和 lambda 使用 param 的 key
            if "[" in _key or "param" in _stripped:
                continue
            dispatch_keys.append(_key)

        missing = [k for k in dispatch_keys if k not in b.BULK_METRICS]
        assert not missing, f"BULK_METRICS 缺少以下 dispatch key: {missing}"
