# yas-zabbix-agent Docker 镜像构建与配置指南

> 适用场景：Zabbix Server (Docker) + YashanDB 监控插件，监控端以 Docker 容器方式运行
> 版本：yas-zabbix-agent:centos | Zabbix Agent 6.0.45 | Python 3.9 | yaspy 1.2.0

---

## 目录

1. [架构说明](#1-架构说明)
2. [前提条件](#2-前提条件)
3. [构建镜像](#3-构建镜像)
4. [启动容器](#4-启动容器)
5. [配置修改](#5-配置修改)
6. [增加监控指标](#6-增加监控指标)
7. [验证连通性](#7-验证连通性)
8. [Zabbix Web UI 接入](#8-zabbix-web-ui-接入)
9. [故障排查](#9-故障排查)

---

## 1. 架构说明

```
┌─────────────────────────────────────────────────────────┐
│  Windows 宿主机                                          │
│    ├── WSL MySQL 8.4 (172.30.112.1:3308)                │
│    └── Docker Desktop                                   │
│           ┌─────────────────────────────────────────┐  │
│           │  docker network: zabbix-net              │  │
│           │                                          │  │
│           │  zabbix-server (Alpine)  ←── 10051/tcp  │  │
│           │  zabbix-web (Alpine)       8080/tcp     │  │
│           │  yas_oracle (YashanDB 23.4) 1688/tcp     │  │
│           │                                          │  │
│           │  yas-zabbix-agent (CentOS) ← 本镜像     │  │
│           │    ├── /opt/yashandb/    ← Docker 卷    │  │
│           │    │     yas_agent_libs  (libyascli.so)  │  │
│           │    └── yashandb_monitor.py → Zabbix     │  │
│           └─────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**为什么用 CentOS 而不是 Alpine？**

YashanDB 官方提供的 C 驱动 `libyascli.so` 是 **glibc 编译版**，Alpine Linux 使用 musl libc，二进制不兼容。因此 Agent 容器必须使用基于 glibc 的 CentOS Stream 9。

---

## 2. 前提条件

### 2.1 Docker 网络

```powershell
# 确保 zabbix-net 网络存在
docker network create zabbix-net 2>$null; echo done
```

### 2.2 YashanDB 驱动卷（必须）

`libyascli.so` 等 glibc 库必须从 `yas_oracle` 容器提取到 Docker 卷：

```powershell
# 提取 YashanDB 库文件到 Docker 卷
docker stop yas_oracle

# 创建卷（如尚不存在）
docker volume create yas_agent_libs

# 从 yas_oracle 容器复制库文件
docker run --rm -v yas_agent_libs:/data alpine sh -c "
    mkdir -p /data/lib &&
    docker cp yas_oracle:/opt/yashandb/yashandb_yasdb_home/lib/. /data/lib/ &&
    ls /data/lib/ | grep -i yas
"

# 重启 yas_oracle（如果之前停掉了）
docker start yas_oracle
```

**验证卷内容**：
```powershell
docker run --rm -v yas_agent_libs:/data alpine ls /data/lib/ | findstr yascli
# 应输出: libyascli.so
```

### 2.3 确认 YashanDB 密码

```powershell
docker inspect yas_oracle --format "{{range .Config.Env}}{{println .}}{{end}}" | Select-String "SYS_PASSWD"
# 输出示例: SYS_PASSWD=Cod-2022
```

### 2.4 源码文件准备

在 `analyze/` 目录下确认以下文件存在：

```
analyze/
├── Dockerfile.yas-zabbix-agent-centos   ← 镜像定义
├── agent-entrypoint-centos.sh           ← 启动脚本
├── wrapper.sh                           ← LD_LIBRARY_PATH 注入脚本
├── config/
│   └── yashandb_userparameter_docker.conf  ← UserParameter 配置
└── scripts/
    └── yashandb_monitor.py               ← 监控采集脚本
```

---

## 3. 构建镜像

### 3.1 完整构建命令

```powershell
cd C:\Users\DELL\WorkBuddy\Claw\analyze

docker build `
    --no-cache `
    -f Dockerfile.yas-zabbix-agent-centos `
    -t yas-zabbix-agent:centos .
```

**预期输出**（关键节点）：

```
Step 13/19: RUN python3 -c "import yaspy; print('yaspy import OK')"
    yaspy import OK
Step 18/19: RUN chmod +x ...
Successfully tagged yas-zabbix-agent:centos
```

> **注意**：首次构建需要从 Docker Hub 拉取基础镜像（`docker.1ms.run/zabbix/zabbix-agent:centos-6.0-latest`），约 200MB。后续构建除脚本层外全部命中缓存。

### 3.2 增量构建（修改脚本后）

如果只改了 `yashandb_monitor.py`、`wrapper.sh` 或 `userparameter` 配置，不需要 `--no-cache`，只有改动层会重建：

```powershell
cd C:\Users\DELL\WorkBuddy\Claw\analyze
docker build -f Dockerfile.yas-zabbix-agent-centos -t yas-zabbix-agent:centos .
```

### 3.3 构建产物

| 产物 | 值 |
|------|-----|
| 镜像名 | `yas-zabbix-agent:centos` |
| 基础镜像 | `docker.1ms.run/zabbix/zabbix-agent:centos-6.0-latest` |
| Zabbix Agent | 6.0.45 |
| Python | 3.9.25 |
| yaspy | 1.2.0 |
| 容器内脚本 | `/etc/zabbix/scripts/yashandb/yashandb_monitor.py` |
| 容器内配置 | `/etc/zabbix/scripts/yashandb/yashandb.ini` |
| 容器内 UserParameter | `/etc/zabbix/zabbix_agentd.d/yashandb.conf` |

---

## 4. 启动容器

### 4.1 一键启动

```powershell
docker run -d `
    --name yas-zabbix-agent `
    --network zabbix-net `
    -v yas_agent_libs:/opt/yashandb/yashandb_yasdb_home:ro `
    -e YASDB_HOST=yas_oracle `
    -e YASDB_PORT=1688 `
    -e YASDB_USER=sys `
    -e YASDB_PASSWORD=Cod-2022 `
    -e ZBX_SERVER_HOST=zabbix-server `
    -e ZBX_HOSTNAME=yas-zabbix-agent `
    yas-zabbix-agent:centos
```

### 4.2 参数说明

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `YASDB_HOST` | `yas_oracle` | YashanDB 监听地址（Docker 内部 DNS 名称） |
| `YASDB_PORT` | `1688` | YashanDB 端口 |
| `YASDB_USER` | `sys` | 连接用户名 |
| `YASDB_PASSWORD` | `CHANGE_ME` | **必须覆盖**，当前 YashanDB 密码为 `Cod-2022` |
| `ZBX_SERVER_HOST` | `zabbix-server` | Zabbix Server 地址（容器名） |
| `ZBX_HOSTNAME` | `yas-zabbix-agent` | Agent 注册名，**必须与 Zabbix Web 中主机名一致** |
| `YASDB_LIB_PATH` | `/opt/yashandb/yashandb_yasdb_home/lib` | YashanDB C 库路径（由卷挂载） |

### 4.3 启动日志检查

```powershell
docker logs yas-zabbix-agent
```

**正常日志**（关键行）：

```
[yas-zabbix] Starting...
[yas-zabbix] Config written to /etc/zabbix/scripts/yashandb/yashandb.ini
[yas-zabbix] Agent config: Server=zabbix-server, Hostname=yas-zabbix-agent, Include/UnsafeUserParameters enabled
[yas-zabbix] LD_LIBRARY_PATH=/opt/yashandb/yashandb_yasdb_home/lib:...
[yas-zabbix] libyascli.so found - C driver OK
[yas-zabbix] Testing Python...
Python 3.9.25
yaspy import OK
[yas-zabbix] yaspy driver ready
[yas-zabbix] Starting zabbix_agentd...
[yas-zabbix] Agent PID=13
```

---

## 5. 配置修改

### 5.1 修改 YashanDB 连接参数

**方式 A：重启容器（覆盖环境变量）**

```powershell
docker stop yas-zabbix-agent
docker rm yas-zabbix-agent

# 重新启动，换新密码/地址
docker run -d `
    --name yas-zabbix-agent `
    --network zabbix-net `
    -v yas_agent_libs:/opt/yashandb/yashandb_yasdb_home:ro `
    -e YASDB_HOST=yas_oracle `
    -e YASDB_PORT=1688 `
    -e YASDB_USER=sys `
    -e YASDB_PASSWORD=你的新密码 `
    -e ZBX_SERVER_HOST=zabbix-server `
    -e ZBX_HOSTNAME=yas-zabbix-agent `
    yas-zabbix-agent:centos
```

**方式 B：直接修改容器内配置文件（无需重启）**

```powershell
# 查看当前配置
docker exec yas-zabbix-agent cat /etc/zabbix/scripts/yashandb/yashandb.ini

# 修改密码（假设改为 NewPass123）
docker exec yas-zabbix-agent sed -i 's/^password = .*/password = NewPass123/' /etc/zabbix/scripts/yashandb/yashandb.ini

# 立即生效：Zabbix Agent 下次轮询时自动使用新配置（配置每次调用时读取）
# 如果需要立即生效，重启 agentd：
docker exec yas-zabbix-agent pkill -HUP zabbix_agentd
```

### 5.2 修改 Zabbix Server 地址

```powershell
# 方式 A：重启容器 + 新环境变量
# 方式 B：直接修改 agent 配置（无需重启）
docker exec yas-zabbix-agent sed -i "s/^Server=.*/Server=新的Zabbix服务器地址/" /etc/zabbix/zabbix_agentd.conf
docker exec yas-zabbix-agent pkill -HUP zabbix_agentd
```

### 5.3 修改 Zabbix Hostname（影响 Web UI 中的主机标识）

```powershell
docker exec yas-zabbix-agent sed -i "s/^Hostname=.*/Hostname=新的主机名/" /etc/zabbix/zabbix_agentd.conf
docker exec yas-zabbix-agent pkill -HUP zabbix_agentd
```

---

## 6. 增加监控指标

### 6.1 指标体系概览

脚本当前支持 **125 个监控指标**，分为以下类别：

| 类别 | 数量 | 示例 |
|------|------|------|
| 实例状态 | 4 | `db.status`、`db.version`、`db.uptime` |
| 会话 | 10 | `sessions.active`、`sessions.total`、`sessions.waiting` |
| SQL 解析 | 6 | `sql.executions_per_sec`、`sql.avg_elapsed_ms`、`sql.slow_count` |
| 内存/SGA/PGA | 15 | `memory.buffer_pool_hit`、`pga.total_alloc` |
| 物理 I/O | 4 | `disk.reads`、`disk.writes` |
| 逻辑读 | 3 | `logical.gets`、`logical.buffer_hit_ratio` |
| 排序 | 2 | `sort.memory`、`sort.disk` |
| Redo 日志 | 9 | `redo.flush_speed`、`redo.checkpoint_lag` |
| 等待事件 | 7 | `wait.top_event`、`wait.total_waits` |
| 锁 | 4 | `lock.count`、`lock.blocking_sessions` |
| 索引 | 2 | `index.invalid_objects`、`index.invalid_indexes` |
| 表空间（LLD） | 13 | `tablespace.discovery`（发现）+ `tablespace.pct_used[TS名]` |
| RAC | 2 | `rac.nodes`、`rac.interconnect_traffic` |
| HA/长事务 | 2 | `ha.long_transaction_count`、`ha.archive_gap` |
| 归档日志 | 2 | `archived_log.count`、`archived_log.first_time` |
| 其他 | 40+ | Datadog/Nagios/New Relic 兼容指标 |

### 6.2 新增指标步骤

假设要新增一个指标：`yashandb.db.archive_status`（检查归档状态，返回 0=未开启，1=已开启）

**Step 1：在 `yashandb_monitor.py` 中添加采集函数**

找到函数定义区域（约 line 500-1200），添加：

```python
def metric_archive_status(conn):
    """归档状态：0=未开启，1=已开启"""
    cur = conn.cursor()
    cur.execute("""
        SELECT CASE
            WHEN LOG_MODE = 'NO ARCHIVELOG' THEN 0
            ELSE 1
        END
        FROM V$DATABASE
    """)
    row = cur.fetchone()
    cur.close()
    return row[0] if row else -1
```

**Step 2：在 dispatch 表中注册**

在 `collect_metric()` 函数的 `dispatch` 字典中（约 line 1822）添加一行：

```python
    dispatch = {
        # ... 现有条目 ...
        "yashandb.db.archive_status":  lambda: metric_archive_status(conn),  # ← 新增
    }
```

**Step 3：在 `yashandb_userparameter_docker.conf` 中添加 UserParameter**

在配置文件末尾添加：

```ini
# ---- 归档 ----
UserParameter=yashandb.db.archive_status,/bin/bash /etc/zabbix/scripts/yashandb/wrapper.sh --metric db.archive_status
```

**Step 4：重新构建镜像并重启**

```powershell
# 重新构建
cd C:\Users\DELL\WorkBuddy\Claw\analyze
docker build -f Dockerfile.yas-zabbix-agent-centos -t yas-zabbix-agent:centos .

# 重启容器
docker stop yas-zabbix-agent && docker rm yas-zabbix-agent
docker run -d `
    --name yas-zabbix-agent `
    --network zabbix-net `
    -v yas_agent_libs:/opt/yashandb/yashandb_yasdb_home:ro `
    -e YASDB_HOST=yas_oracle `
    -e YASDB_PORT=1688 `
    -e YASDB_USER=sys `
    -e YASDB_PASSWORD=Cod-2022 `
    -e ZBX_SERVER_HOST=zabbix-server `
    -e ZBX_HOSTNAME=yas-zabbix-agent `
    yas-zabbix-agent:centos
```

**Step 5：验证新指标**

```powershell
# 容器内直接测试
docker exec yas-zabbix-agent /bin/bash /etc/zabbix/scripts/yashandb/wrapper.sh --metric db.archive_status

# 从 Zabbix Server 拉取（网络层验证）
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "yashandb.db.archive_status"
```

### 6.3 新增带参数的指标（如表空间 LLD）

如果新指标需要 `{TABLENAME}` 参数，格式为 `tablespace.used[SYSAUX]`：

**Step 1：采集函数接受 `param` 参数**

```python
def metric_custom_tablespace_used(conn, param=None):
    """自定义表空间使用量（MB）"""
    if not param:
        raise ValueError("缺少表空间名参数")
    cur = conn.cursor()
    cur.execute("""
        SELECT NVL(USED_SPACE * 8 / 1024, 0)
        FROM DBA_TABLESPACE_USAGE_METRICS
        WHERE TABLESPACE_NAME = :ts
    """, (param,))
    row = cur.fetchone()
    cur.close()
    return float(row[0]) if row and row[0] else 0.0
```

**Step 2：dispatch 中注册（注意函数要接收 param）**

```python
"yashandb.custom.ts.used": lambda ctx: metric_custom_tablespace_used(ctx, ctx.get("param")),
```

> `collect_metric` 会自动把 `db.custom.ts.used[$1]` 中的 `$1` 提取为 `param` 传给函数。

**Step 3：UserParameter 中使用参数占位符**

```ini
UserParameter=yashandb.custom.ts.used[*],/bin/bash /etc/zabbix/scripts/yashandb/wrapper.sh --metric "db.custom.ts.used[$1]"
```

### 6.4 同步到 yas_zabbix 项目

构建镜像用的脚本在 `analyze/scripts/yashandb_monitor.py`，正式项目脚本在 `yas_zabbix/scripts/yashandb_monitor.py`。

修改完成后，将脚本同步到正式项目：

```powershell
copy C:\Users\DELL\WorkBuddy\Claw\analyze\scripts\yashandb_monitor.py `
      C:\Users\DELL\WorkBuddy\Claw\yas_zabbix\scripts\yashandb_monitor.py
```

---

## 7. 验证连通性

```powershell
# 1. Agent 自身
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "agent.ping"
# 期望: 1

# 2. 数据库状态
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "yashandb.db.status"
# 期望: 1

# 3. 数据库版本
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "yashandb.db.version"
# 期望: Enterprise Edition Release 23.4.7.100 x86_64

# 4. 活跃会话数
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "yashandb.sessions.active"
# 期望: 数字（如 26）

# 5. 表空间 LLD 发现
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "yashandb.tablespace.discovery"
# 期望: JSON {"data":[{"{#TS}":"SWAP"},{"{#TS}":"SYSAUX"},...]}

# 6. 表空间使用率（参数指标）
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "yashandb.tablespace.pct_used[SYSTEM]"
# 期望: 数字（如 68.5）
```

---

## 8. Zabbix Web UI 接入

### 8.1 导入模板

1. 打开 http://localhost:8080，登录（Admin / zabbix）
2. **配置 → 模板 → 导入**
3. 选择文件：`C:\Users\DELL\WorkBuddy\Claw\yas_zabbix\template\yashandb_zabbix_template_7.0.xml`
4. 勾选 **所有选项**，点击 **导入**

### 8.2 创建主机

1. **配置 → 主机 → 创建主机**
2. **主机名**：`yas-zabbix-agent`（必须与容器的 `ZBX_HOSTNAME` 环境变量完全一致）
3. **群组**：选择 `Linux servers` 或新建 `YashanDB`
4. **Interfaces**：
   - 类型：**Agent**
   - IP：`yas-zabbix-agent`（Docker 内部 DNS，直接写容器名）
   - 端口：`10050`
5. **Templates**：
   - 链接模板：搜索并选择 **YashanDB Monitor**
6. 点击 **添加**

### 8.3 查看监控数据

等待 1-2 分钟后：
- **监控 → 最新数据**：筛选 host = `yas-zabbix-agent`，查看所有指标
- **监控 → 图形**：为目标创建自定义图形
- **配置 → 主机**：在触发器 tab 中配置告警阈值

---

## 9. 故障排查

### 9.1 `libyascli.so: No such file or directory`

**原因**：`yas_agent_libs` 卷未挂载或内容为空。

**排查**：
```powershell
docker exec yas-zabbix-agent ls /opt/yashandb/yashandb_yasdb_home/lib/ | findstr yascli
# 如无输出，执行 Step 2.2 重新提取卷内容
```

### 9.2 `Unsupported item key`

**原因**：UserParameter 配置未被加载。

**排查**：
```powershell
# 检查 Include 是否启用
docker exec yas-zabbix-agent grep "^Include" /etc/zabbix/zabbix_agentd.conf
# 期望: Include=/etc/zabbix/zabbix_agentd.d/*.conf

# 检查 UserParameter 文件是否存在
docker exec yas-zabbix-agent ls /etc/zabbix/zabbix_agentd.d/
# 期望: yashandb.conf
```

### 9.3 `invalid username/password`

**原因**：YashanDB 密码不正确。

**排查**：
```powershell
docker exec yas-zabbix-agent cat /etc/zabbix/scripts/yashandb/yashandb.ini
# 对照 yas_oracle 容器的 SYS_PASSWD 环境变量
```

### 9.4 `Not Found: host [yas-zabbix-agent]`

**原因**：Zabbix Web 中创建主机时填的主机名与容器 `ZBX_HOSTNAME` 不一致。

**修复**：在 Zabbix Web 中将主机名改为与容器环境变量一致，或修改容器内 `Hostname=` 值后重启。

### 9.5 `access permissions`

**原因**：`/etc/zabbix/zabbix_agentd.conf` 中 `Server=` 只允许特定 IP 的请求。

**修复**：
```powershell
docker exec yas-zabbix-agent sed -i "s/^Server=.*/Server=zabbix-server/" /etc/zabbix/zabbix_agentd.conf
docker exec yas-zabbix-agent pkill -HUP zabbix_agentd
```

### 9.6 日志位置

| 日志 | 路径 |
|------|------|
| Agent 启动日志 | `docker logs yas-zabbix-agent` |
| Zabbix Agent 运行日志 | `docker exec yas-zabbix-agent cat /var/log/zabbix/zabbix_agentd.log` |
| Zabbix Server 日志 | `docker logs zabbix-server` |

---

## 附录：完整一键脚本

```powershell
# === rebuild-yas-agent.ps1 ===
docker stop yas-zabbix-agent 2>$null
docker rm   yas-zabbix-agent 2>$null

cd C:\Users\DELL\WorkBuddy\Claw\analyze

# 构建镜像（无 --no-cache 时仅增量更新）
docker build -f Dockerfile.yas-zabbix-agent-centos -t yas-zabbix-agent:centos .

# 启动容器
docker run -d `
    --name yas-zabbix-agent `
    --network zabbix-net `
    -v yas_agent_libs:/opt/yashandb/yashandb_yasdb_home:ro `
    -e YASDB_HOST=yas_oracle `
    -e YASDB_PORT=1688 `
    -e YASDB_USER=sys `
    -e YASDB_PASSWORD=Cod-2022 `
    -e ZBX_SERVER_HOST=zabbix-server `
    -e ZBX_HOSTNAME=yas-zabbix-agent `
    yas-zabbix-agent:centos

Write-Host "等待启动..."
Start-Sleep -Seconds 5

Write-Host "=== 启动日志 ==="
docker logs yas-zabbix-agent

Write-Host ""
Write-Host "=== 连通性验证 ==="
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "agent.ping"
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "yashandb.db.status"
```
