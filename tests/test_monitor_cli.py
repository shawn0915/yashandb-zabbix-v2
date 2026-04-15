"""
测试 yashandb_monitor.py 命令行参数解析与配置加载

运行：
    pytest tests/test_monitor_cli.py -v
"""
import argparse
import configparser
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import yashandb_monitor as m


class TestArgParsing:
    """测试命令行参数解析"""

    def test_required_args_present(self):
        """必须参数不全时应报错"""
        sys.argv = ["yashandb_monitor.py"]  # 只有脚本名，无任何参数
        with pytest.raises(SystemExit):
            m.parse_args()

    def test_minimal_valid_args(self):
        """最小有效参数集"""
        sys.argv = [
            "yashandb_monitor.py",
            "--host", "127.0.0.1",
            "--user", "sys",
            "--password", "pass",
            "--metric", "yashandb.db.status",
        ]
        args = m.parse_args()
        assert args.host == "127.0.0.1"
        assert args.user == "sys"
        assert args.password == "pass"
        assert args.metric == "yashandb.db.status"
        assert args.port == "1688"       # 默认值
        assert args.timeout == "10"      # 默认值

    def test_all_args(self):
        """所有参数都能正确解析"""
        sys.argv = [
            "yashandb_monitor.py",
            "--host", "192.168.1.100",
            "--port", "1689",
            "--user", "monitor",
            "--password", "secret",
            "--metric", "yashandb.active_sessions",
            "--timeout", "30",
        ]
        args = m.parse_args()
        assert args.host == "192.168.1.100"
        assert args.port == "1689"
        assert args.user == "monitor"
        assert args.password == "secret"
        assert args.metric == "yashandb.active_sessions"
        assert args.timeout == "30"


class TestLoadConfig:
    """测试配置文件加载"""

    def test_load_config_file_not_found(self, tmp_path):
        """文件不存在返回空字典"""
        result = m.load_config(str(tmp_path / "nonexistent.ini"))
        assert result == {}

    def test_load_config_valid(self, tmp_path):
        """正确解析 INI 配置文件"""
        ini_file = tmp_path / "yashandb.ini"
        ini_file.write_text(
            "[yashandb]\n"
            "host = 192.168.1.50\n"
            "port = 1688\n"
            "user = monitor\n"
            "password = mypass\n",
            encoding="utf-8",
        )
        cfg = m.load_config(str(ini_file))
        assert cfg["host"] == "192.168.1.50"
        assert cfg["port"] == "1688"
        assert cfg["user"] == "monitor"
        assert cfg["password"] == "mypass"

    def test_load_config_no_yashandb_section(self, tmp_path):
        """INI 有其他 section 但无 yashandb 时返回空字典"""
        ini_file = tmp_path / "other.ini"
        ini_file.write_text("[mysql]\nhost=localhost\n", encoding="utf-8")
        result = m.load_config(str(ini_file))
        assert result == {}


class TestMetricHelp:
    """测试 METRIC_HELP 文档包含关键指标"""

    def test_help_contains_native_metrics(self):
        """METRIC_HELP 应包含所有原生指标"""
        native_keys = [
            "yashandb.db.status",
            "yashandb.db.sessions.active",
            "yashandb.db.memory.buffer_pool_hit",
            "yashandb.db.tablespace.discovery",
        ]
        for key in native_keys:
            assert key in m.METRIC_HELP, f"METRIC_HELP 应包含 {key}"

    def test_help_contains_datadog_metrics(self):
        """METRIC_HELP 应包含 Datadog 兼容指标"""
        dd_keys = [
            "yashandb.active_sessions",
            "yashandb.buffer_cachehit_ratio",
            "yashandb.process.pga_allocated_memory",
            "yashandb.redo_generated",
            "yashandb.tablespace.in_use",
        ]
        for key in dd_keys:
            assert key in m.METRIC_HELP, f"METRIC_HELP 应包含 {key}"

    def test_help_contains_na_section(self):
        """METRIC_HELP 应包含 N/A 指标说明"""
        assert "N/A" in m.METRIC_HELP
        assert "ASM" in m.METRIC_HELP or "不支持" in m.METRIC_HELP


class TestDispatchCompleteness:
    """验证 dispatch 表覆盖所有指标"""

    def _extract_dispatch_keys(self):
        """
        从 collect_metric 源码中解析 dispatch dict 的 key。

        注意：不能依赖 bytecode co_consts——Python peephole 优化器会
        对字典字面量中的重复字符串字面量去重，导致部分 key 丢失。
        直接解析源码更可靠。
        """
        import re
        import os

        src_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "yashandb_monitor.py")
        with open(src_path, encoding="utf-8") as f:
            source = f.read()

        # 找 collect_metric 函数的 dispatch dict
        # dispatch = { ... } 后紧跟 if base_key not in dispatch:
        m_start = re.search(r"dispatch\s*=\s*\{", source)
        if not m_start:
            raise RuntimeError("无法在源码中找到 dispatch 字典")

        # 数括号找到 dict 结束位置
        pos = m_start.start() + len("dispatch = {") - 1
        depth = 1
        while pos < len(source) and depth > 0:
            if source[pos] == "{":
                depth += 1
            elif source[pos] == "}":
                depth -= 1
            pos += 1
        dispatch_text = source[m_start.start() + len("dispatch = {") - 1 + 1: pos - 1]

        # 提取所有 yashandb.* key（跳过注释行）
        keys = []
        for line in dispatch_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            found = re.findall(r'"(yashandb\.[^"]+)"', stripped)
            keys.extend(found)

        return keys

    def test_all_documented_metrics_in_dispatch(self):
        """
        METRIC_HELP 中列出的每个指标都必须在 dispatch 中存在。
        这防止了"文档写了但函数没实现"的遗漏。

        注意：N/A 部分（标注"不支持"的指标）不参与此检查。
        """
        import re

        # 从 METRIC_HELP 提取支持的指标（跳过 N/A 行）
        documented_keys = set()
        for line in m.METRIC_HELP.splitlines():
            # 跳过 N/A 标注行（这些是明确不支持的指标）
            if "N/A" in line:
                continue
            m2 = re.match(r"^\s+(yashandb\.[a-z0-9_.*[\]]+)", line)
            if m2:
                key = m2.group(1)
                base = key.split("[")[0].rstrip(".")
                documented_keys.add(base)

        # 从 dispatch 提取 base key
        dispatch_raw = self._extract_dispatch_keys()
        dispatch_keys = {k.split("[")[0] for k in dispatch_raw}

        missing = documented_keys - dispatch_keys
        assert not missing, \
            f"METRIC_HELP 中有 {len(missing)} 个指标未在 dispatch 中实现: {sorted(missing)}"
