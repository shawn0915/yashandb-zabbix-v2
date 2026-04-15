# 测试套件

## 目录结构

```
tests/
├── __init__.py
├── conftest.py              # pytest fixtures（mock + live conn）
├── test_monitor_metrics.py  # 所有指标函数的单元测试
├── test_monitor_cli.py      # CLI 参数解析 + dispatch 完整性测试
├── test_monitor_integration.py  # 真实数据库集成测试
└── test_bulk.py             # bulk 批量采集脚本测试
```

## 快速开始

### 安装依赖

```bash
# 核心依赖
pip install pytest

# 集成测试（需真实数据库）
pip install yashandb-python-driver
```

### 运行测试

```bash
# 仅单元测试（默认，无需数据库）
pytest tests/ -v

# 包含集成测试（需 Docker + 环境变量）
set YAS_ZABBIX_TEST_LIVE=1
set YAS_PASSWORD=yourpassword
pytest tests/ -v

# 仅运行集成测试
pytest tests/ -v -m integration

# 仅运行单元测试
pytest tests/ -v -m "not integration"
```

### 调试

```bash
# 只运行某个文件
pytest tests/test_monitor_metrics.py -v

# 只运行某个测试类
pytest tests/test_monitor_metrics.py::TestCollectMetricDispatch -v

# 只运行某个测试
pytest tests/test_monitor_metrics.py::TestCollectMetricDispatch::test_collect_metric_unknown_key_raises -v
```

## 测试覆盖

| 测试文件 | 内容 | 需要 DB |
|---------|------|---------|
| `test_monitor_metrics.py` | 所有 72 个指标函数的路由、类型、异常处理 | 否 |
| `test_monitor_cli.py` | 参数解析、配置加载、METRIC_HELP 完整性 | 否 |
| `test_monitor_integration.py` | 所有指标在真实 YashanDB 上执行 | 是 |
| `test_bulk.py` | BULK_METRICS 列表完整性 + bulk 脚本行为 | 否 |

## 添加新指标测试

新增指标函数后，在 `test_monitor_metrics.py` 的 `TestCollectMetricDispatch` 类中添加参数化测试：

```python
@pytest.mark.parametrize("metric_key", [
    "yashandb.new_metric",  # 新增这行
])
def test_collect_metric_dispatches_without_error(self, mock_conn, metric_key):
    ...
```

同时确保 `BULK_METRICS` 列表中包含该指标。
