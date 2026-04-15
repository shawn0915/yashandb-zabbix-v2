# Zabbix 7.0 → 7.4.9 升级评估报告

> 评估日期：2026-04-11
> 当前环境：Zabbix 7.0 LTS

---

## 一、当前环境清单

| 组件 | 当前版本 | 当前镜像 |
|------|----------|----------|
| Zabbix Server | 7.0 LTS | `zabbix/zabbix-server-mysql:alpine-7.0-latest` |
| Zabbix Web | 7.0 LTS | `zabbix/zabbix-web-nginx-mysql:alpine-7.0-latest` |
| Zabbix Agent | **6.0.45** ⚠️ | `yas-zabbix-agent:centos`（基于 `docker.1ms.run/zabbix/zabbix-agent:centos-6.0-latest`） |
| YashanDB 模板 | 7.4 XML | `yashandb_zabbix_template.xml`（已有） |
| Dashboard | — | ID 422/423/424（3个，Zabbix DB 存储） |
| MySQL 后端 | 8.4 | WSL 内，172.30.112.1:3308 |

### ⚠️ 已有版本错配问题

Agent（6.0.45）和 Server（7.0）版本不匹配，升级到 7.4 反而是**修复机会**（先升级到 7.0 再升 7.4，不如一步到位）。

---

## 二、升级影响矩阵

| 升级项 | 是否需要修改 | 风险等级 | 说明 |
|--------|------------|----------|------|
| **Zabbix Server 镜像** | ✅ 需改镜像 TAG | 🟡 中 | 7.0 → 7.4，数据库 schema 兼容（向后） |
| **Zabbix Web 镜像** | ✅ 需改镜像 TAG | 🟡 中 | 随 Server 同升，不影响数据 |
| **Zabbix Agent 镜像** | ✅ 需重构建 | 🔴 高 | 基础镜像从 6.0 升至 7.4，需重编译 yaspy |
| **yaspy Python 驱动** | ✅ 需重新安装 | 🟡 中 | yaspy 含 gcc 编译的 C 扩展，镜像重建自动重装 |
| **自定义 Dockerfile** | ✅ 改 FROM 行 | 🟢 低 | `docker.1ms.run/zabbix/zabbix-agent:centos-6.0-latest` → `zabbix/zabbix-agent:centos-7.4-latest` |
| **Docker Entrypoint** | ❌ 不需要 | — | bash 逻辑无需修改 |
| **采集脚本** | ❌ 不需要 | — | yashandb_monitor.py 与 Zabbix 版本无关 |
| **UserParameter 配置** | ❌ 不需要 | — | 语法 6.0/7.x 兼容 |
| **YashanDB 模板 XML** | ❌ 不需要 | — | 当前 `yashandb_zabbix_template.xml` 已是 Zabbix 7.4 格式（`<version>7.4</version>`） |
| **Dashboard（3个）** | ❌ 不需要 | 🟢 低 | 存储在 Zabbix MySQL DB 中，schema 兼容 |
| **zabbix_import.py 导入脚本** | ❌ 不需要 | — | 与 Server 版本无关，调用 Zabbix API |
| **监控数据（history/trends）** | ❌ 不丢失 | 🟢 无 | 存在 MySQL，7.4 向后兼容 |
| **主机/主机组配置** | ❌ 不丢失 | 🟢 无 | API 导出/导入，Zabbix DB schema 兼容 |

---

## 三、逐项详解

### 3.1 Zabbix Server + Web（影响最小）

官方 Docker 镜像升级仅需改 TAG，数据库 schema Zabbix 自动迁移：

```
# 当前
zabbix/zabbix-server-mysql:alpine-7.0-latest
zabbix/zabbix-web-nginx-mysql:alpine-7.0-latest

# 升级后
zabbix/zabbix-server-mysql:alpine-7.4-latest
zabbix/zabbix-web-nginx-mysql:alpine-7.4-latest
```

**操作**：停止旧容器 → `docker run` 新镜像（卷/网络/环境变量不变）

### 3.2 Zabbix Agent（影响最大）

基础镜像从 Zabbix Agent **6.0** 升至 **7.4**，主要变化：

- Agent 配置文件格式完全兼容（`zabbix_agentd.conf`）
- UserParameter 语法完全兼容
- 但需重新编译 yaspy（Python C 扩展）

**Dockerfile 改动（仅改 1 行）**：

```diff
- FROM docker.1ms.run/zabbix/zabbix-agent:centos-6.0-latest
+ FROM zabbix/zabbix-agent:centos-7.4-latest
```

> **注意**：`docker.1ms.run/zabbix/zabbix-agent:centos-6.0-latest` 是第三方镜像，`zabbix/zabbix-agent:centos-7.4-latest` 是官方镜像。两者包管理器都是 `microdnf`，改动极小。

### 3.3 yaspy 重编译

`pip3 install` 时需要 gcc + python3-devel + openssl-devel，当前 Dockerfile 中已安装，镜像重建时会自动重装。

唯一风险：如果 `yashandb-python` GitHub 仓库有新 breaking change，需要留意。不过 yaspy 驱动本身与 Zabbix 版本无关。

### 3.4 Dashboard 和历史数据

3 个 Dashboard（ID 422/423/424）存储在 Zabbix MySQL DB 中，7.4 schema 完全向后兼容，**无需任何操作**。

---

## 四、升级步骤（推荐）

### Phase 1：备份（必须）

```bash
# 1. 导出当前模板
python scripts/zabbix_import.py --action=export --hostid=10684

# 2. 备份 Zabbix MySQL（WSL 内）
wsl -d Ubuntu-24.04 -- mysqldump -u root -p'checkindb1qazxsw2' zabbix > zabbix_backup_$(date +%Y%m%d).sql
```

### Phase 2：升级 Server + Web

```bash
# 停止
docker stop zabbix-web zabbix-server

# 拉起 7.4
docker run -d --name zabbix-server \
  --network zabbix-net \
  -e DB_SERVER_HOST=172.30.112.1 \
  -e MYSQL_PORT=3308 \
  -e MYSQL_DATABASE=zabbix \
  -e MYSQL_USER=zabbix \
  -e MYSQL_PASSWORD=zabbix \
  -p 10051:10051 \
  zabbix/zabbix-server-mysql:alpine-7.4-latest

docker run -d --name zabbix-web \
  --network zabbix-net \
  -e ZBX_SERVER_HOST=zabbix-server \
  -e DB_SERVER_HOST=172.30.112.1 \
  -e MYSQL_PORT=3308 \
  -e MYSQL_DATABASE=zabbix \
  -e MYSQL_USER=zabbix \
  -e MYSQL_PASSWORD=zabbix \
  -p 8080:8080 \
  zabbix/zabbix-web-nginx-mysql:alpine-7.4-latest
```

### Phase 3：升级 Agent

```bash
# 修改 Dockerfile 第 18 行
# FROM docker.1ms.run/zabbix/zabbix-agent:centos-6.0-latest
# → FROM zabbix/zabbix-agent:centos-7.4-latest

# 重新构建
cd analyze/
docker build --no-cache -f Dockerfile.yas-zabbix-agent-centos \
  -t yas-zabbix-agent:centos-7.4 .

# 停止旧容器（保留 yas_agent_libs 卷）
docker stop yas-zabbix-agent
docker rm yas-zabbix-agent

# 启动新容器（参数不变）
docker run -d --name yas-zabbix-agent --network zabbix-net \
  -v yas_agent_libs:/opt/yashandb/yashandb_yasdb_home:ro \
  -e YASDB_HOST=yas_oracle \
  -e YASDB_PORT=1688 \
  -e YASDB_USER=sys \
  -e YASDB_PASSWORD=Cod-2022 \
  -e ZBX_SERVER_HOST=zabbix-server \
  -e ZBX_HOSTNAME=yas-zabbix-agent \
  yas-zabbix-agent:centos-7.4
```

### Phase 4：验证

```bash
# Agent 确认 7.4
docker exec yas-zabbix-agent zabbix_agentd -V

# 全链路验证
docker exec yas-zabbix-agent zabbix_agentd -p | grep yashandb | head -5
zabbix_get -s yas-zabbix-agent -k yashandb.db.status
zabbix_get -s yas-zabbix-agent -k yashandb.db.version
zabbix_get -s yas-zabbix-agent -k yashandb.library_cache_hit_ratio

# Web UI
# http://localhost:8080/zabbix.php?action=dashboard.view&dashboardid=422
```

---

## 五、关键风险

| 风险 | 缓解方案 |
|------|----------|
| 第三方镜像 `docker.1ms.run/zabbix/zabbix-agent:centos-6.0-latest` 没有 7.4 版本 | 改用官方 `zabbix/zabbix-agent:centos-7.4-latest`，两个镜像均基于 CentOS，包管理器相同 |
| 升级后 Zabbix Web 界面 UI 变化大 | 先用浏览器打开确认，不需要改任何配置 |
| MySQL DB schema 迁移失败 | 升级前先备份 `mysqldump zabbix` |
| Agent 7.4 与 Server 7.4 加密通信 | Server 默认兼容旧版本，无需改配置 |

---

## 六、结论

**升级到 7.4.9 是低风险操作**，主要工作量在于重建 Agent 镜像。Dashboard、模板、历史数据均可复用，Server/Web 仅需换镜像 TAG。

**预计改动量**：
- Dockerfile：改 1 行（FROM）
- 镜像版本 TAG：3 处（server/web/agent）
- 零代码修改

**建议**：先用 `docker.1ms.run/zabbix/zabbix-agent:centos-6.0-latest` 验证官方 7.4 Agent 镜像是否可用，再正式重建。
