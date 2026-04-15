#!/usr/bin/env python3
"""生成 yas_zabbix v2.4/2.5 新增指标的 XML 条目"""
import uuid

def uuid_gen(prefix):
    """生成以 prefix 开头的 UUID"""
    base = "d2010100000000000000000000000"
    suffix = f"{prefix:03d}"
    return base[:20] + suffix

def item_xml(uuid_val, name, key, delay="60s", value_type="UNSIGNED", units="", description="", trigger_expr="", trigger_name="", trigger_priority="WARNING", trigger_desc=""):
    """生成 Zabbix item XML"""
    xml = f"""                <item>
                    <uuid>{uuid_val}</uuid>
                    <name>{name}</name>
                    <key>{key}</key>
                    <delay>{delay}</delay>
                    <history>7d</history>
                    <trends>90d</trends>
                    <value_type>{value_type}</value_type>"""
    if units:
        xml += f"\n                    <units>{units}</units>"
    xml += f"\n                    <description>{description}</description>"
    if trigger_expr:
        xml += f"""
                    <triggers>
                        <trigger>
                            <uuid>{uuid_val[:18]}ff</uuid>
                            <expression>{trigger_expr}</expression>
                            <name>{trigger_name}</name>
                            <priority>{trigger_priority}</priority>
                            <description>{trigger_desc}</description>
                            <manual_close>YES</manual_close>
                        </trigger>
                    </triggers>"""
    xml += "\n                </item>\n"
    return xml

# 生成所有新指标 XML
new_items = []

# ===== Phase 1 =====
# 1. QPS
new_items.append(item_xml(
    "d201010000000000000000000000051", "YashanDB: 每秒查询数（QPS）",
    "yashandb.db.qps", "60s", "UNSIGNED", "qps",
    "每秒查询数（累计值）。来源: V$SYSSTAT EXECUTE COUNT。注意：此为累计值，Zabbix 需使用 change/sec 或 delta 计算每秒速率。对标 Flashcat Cprobe oracle_qps。"
))

# 2. TPS
new_items.append(item_xml(
    "d201010000000000000000000000052", "YashanDB: 每秒事务数（TPS）",
    "yashandb.db.tps", "60s", "UNSIGNED", "tps",
    "每秒事务数（累计值）。来源: V$SYSSTAT COMMITS。注意：此为累计值，Zabbix 需使用 change/sec 或 delta 计算每秒速率。对标 Flashcat Cprobe oracle_tps。"
))

# 3. 当天归档数
new_items.append(item_xml(
    "d201010000000000000000000000053", "YashanDB: 当天归档日志数量",
    "yashandb.archived_log.count_today", "300s", "UNSIGNED",
    description="当天（TRUNC(SYSDATE)）以来生成的归档日志文件数量。对标 Flashcat Cprobe archivelog.count（当天）。"
))

# 4. 等待类 LLD
# (单独添加 discovery_rule)

# 5. 等待类 - Application count
new_items.append(item_xml(
    "d201010000000000000000000000054", "YashanDB: 等待类 [Application] 总等待次数",
    "yashandb.db.wait_class.count[Application]", "60s", "UNSIGNED",
    description="V$SYSTEM_WAIT_CLASS 中 Application 等待类的 TOTAL_WAITS。"
))

# 6. 等待类 - Application time
new_items.append(item_xml(
    "d201010000000000000000000000055", "YashanDB: 等待类 [Application] 总等待时间",
    "yashandb.db.wait_class.time[Application]", "60s", "UNSIGNED", "s",
    description="V$SYSTEM_WAIT_CLASS 中 Application 等待类的 TIME_WAITED（厘秒→秒）。"
))

# 7. 按类型表空间 - PERMANENT
new_items.append(item_xml(
    "d201010000000000000000000000056", "YashanDB: PERMANENT 类型表空间总大小",
    "yashandb.tablespace.by_type[PERMANENT]", "3600s", "UNSIGNED", "B",
    description="CONTENTS='PERMANENT' 的所有表空间数据文件总大小（字节）。对标 zCloud 巡检表空间按类型分类。"
))

# 8. 按类型表空间 - UNDO
new_items.append(item_xml(
    "d201010000000000000000000000057", "YashanDB: UNDO 类型表空间总大小",
    "yashandb.tablespace.by_type[UNDO]", "3600s", "UNSIGNED", "B",
    description="CONTENTS='UNDO' 的所有表空间数据文件总大小（字节）。对标 zCloud 巡检表空间按类型分类。"
))

# 9. 按类型表空间 - TEMPORARY
new_items.append(item_xml(
    "d201010000000000000000000000058", "YashanDB: TEMPORARY 类型表空间总大小",
    "yashandb.tablespace.by_type[TEMPORARY]", "3600s", "UNSIGNED", "B",
    description="CONTENTS='TEMPORARY' 的所有表空间数据文件总大小（字节）。对标 zCloud 巡检表空间按类型分类。"
))

# 10. Temp 表空间使用率
new_items.append(item_xml(
    "d201010000000000000000000000059", "YashanDB: 临时表空间使用率",
    "yashandb.tablespace.temp_usage_pct", "300s", "FLOAT", "%",
    description="临时表空间使用率（%）。来源: DBA_TEMP_FREE_SPACE。对标 CSDN Oracle 监控临时表空间使用情况。",
    trigger_expr="last(/YashanDB by Zabbix Agent/yashandb.tablespace.temp_usage_pct) > 80",
    trigger_name="YashanDB: 临时表空间使用率过高 ({HOST.NAME})",
    trigger_priority="WARNING",
    trigger_desc="临时表空间使用率超过 80%，可能影响排序操作。"
))

# 11. Undo 表空间使用率
new_items.append(item_xml(
    "d201010000000000000000000000060", "YashanDB: Undo 表空间使用率",
    "yashandb.tablespace.undo_usage_pct", "300s", "FLOAT", "%",
    description="Undo 表空间使用率（%）。来源: DBA_DATA_FILES+DBA_TABLESPACES。对标 CSDN Oracle 监控 Undo 表空间使用情况。",
    trigger_expr="last(/YashanDB by Zabbix Agent/yashandb.tablespace.undo_usage_pct) > 80",
    trigger_name="YashanDB: Undo 表空间使用率过高 ({HOST.NAME})",
    trigger_priority="WARNING",
    trigger_desc="Undo 表空间使用率超过 80%，可能导致快照过旧问题。"
))

# 12. Top SQL - buffer gets SQL_ID
new_items.append(item_xml(
    "d201010000000000000000000000061", "YashanDB: Top SQL（按 Buffer Gets）SQL_ID",
    "yashandb.sql.top_buffer_gets_sql", "120s", "TEXT",
    description="V$SQLAREA 中按 BUFFER_GETS 排序最高的 SQL 的 SQL_ID。对标 Flashcat/Oracle AWR Top SQL。"
))

# 13. Top SQL - disk reads SQL_ID
new_items.append(item_xml(
    "d201010000000000000000000000062", "YashanDB: Top SQL（按 Disk Reads）SQL_ID",
    "yashandb.sql.top_disk_reads_sql", "120s", "TEXT",
    description="V$SQLAREA 中按 DISK_READS 排序最高的 SQL 的 SQL_ID。对标 Flashcat/Oracle AWR Top SQL。"
))

# 14. Top SQL - executions SQL_ID
new_items.append(item_xml(
    "d201010000000000000000000000063", "YashanDB: Top SQL（按执行次数）SQL_ID",
    "yashandb.sql.top_executions_sql", "120s", "TEXT",
    description="V$SQLAREA 中按 EXECUTIONS 排序最高的 SQL 的 SQL_ID。对标 Flashcat/Oracle AWR Top SQL。"
))

# 15. 资源限制使用率
new_items.append(item_xml(
    "d201010000000000000000000000064", "YashanDB: 资源限制使用率",
    "yashandb.resource_limit.usage_pct", "60s", "FLOAT", "%",
    description="sessions/processes 资源限制使用率的最大值（%）。V$RESOURCE_LIMIT 在 YashanDB 中不存在，改用 V$PARAMETER+V$SESSION/V$PROCESS。对标 Cprobe oracle_resource_limit。",
    trigger_expr="last(/YashanDB by Zabbix Agent/yashandb.resource_limit.usage_pct) > 80",
    trigger_name="YashanDB: 资源限制使用率过高 ({HOST.NAME})",
    trigger_priority="WARNING",
    trigger_desc="资源限制使用率超过 80%，接近系统上限。"
))

# ===== Phase 2 =====
# 16. P95 延迟
new_items.append(item_xml(
    "d201010000000000000000000000065", "YashanDB: 慢查询 P95 延迟",
    "yashandb.sql.p95_elapsed_ms", "120s", "FLOAT", "ms",
    description="慢查询 P95 延迟（毫秒）。来源: V$SQL PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY ELAPSED_TIME)。对标 Cprobe slow_queries 分位数版。"
))

# 17. P99 延迟
new_items.append(item_xml(
    "d201010000000000000000000000066", "YashanDB: 慢查询 P99 延迟",
    "yashandb.sql.p99_elapsed_ms", "120s", "FLOAT", "ms",
    description="慢查询 P99 延迟（毫秒）。来源: V$SQL PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY ELAPSED_TIME)。对标 Cprobe slow_queries 分位数版。"
))

# 18. 会话分布 LLD（用户）
# (单独添加 discovery_rule)

# 19. 按用户会话数（示例：SYS）
new_items.append(item_xml(
    "d201010000000000000000000000067", "YashanDB: 用户 [SYS] 会话数",
    "yashandb.session.by_user[SYS]", "60s", "UNSIGNED",
    description="V$SESSION 中指定用户（SYS）的会话数量。用于连接池效率分析。对标 HertzBeat 按用户分组会话。"
))

# 20. 会话分布 LLD（程序）
# (单独添加 discovery_rule)

# 21. INVALID 对象类型 LLD
# (单独添加 discovery_rule)

# 22. 非自动扩展数据文件数
new_items.append(item_xml(
    "d201010000000000000000000000068", "YashanDB: 禁用了自动扩展的数据文件数量",
    "yashandb.datafile.non_autoextend_count", "3600s", "UNSIGNED",
    description="DBA_DATA_FILES 中 AUTOEXTENSIBLE='NO' 的数据文件数量。对标 zCloud 监控数据文件自动扩展状态。",
    trigger_expr="last(/YashanDB by Zabbix Agent/yashandb.datafile.non_autoextend_count) > 0",
    trigger_name="YashanDB: 存在禁用了自动扩展的数据文件 ({HOST.NAME})",
    trigger_priority="INFO",
    trigger_desc="存在禁用了自动扩展的数据文件，可能导致表空间满时无法自动扩展。"
))

# 23. 密码即将过期账户数
new_items.append(item_xml(
    "d201010000000000000000000000069", "YashanDB: 密码即将过期账户数（7天内）",
    "yashandb.user.expiring_soon_count", "86400s", "UNSIGNED",
    description="7天内密码即将过期的账户数量（DBA_USERS）。对标 zCloud 安全监控密码即将过期账户。",
    trigger_expr="last(/YashanDB by Zabbix Agent/yashandb.user.expiring_soon_count) > 0",
    trigger_name="YashanDB: 有账户密码即将过期 ({HOST.NAME})",
    trigger_priority="WARNING",
    trigger_desc="存在密码即将过期的账户，请及时更新密码。"
))

# 24. STATISTICS_LEVEL
new_items.append(item_xml(
    "d201010000000000000000000000070", "YashanDB: STATISTICS_LEVEL 参数值",
    "yashandb.db.statistics_level", "86400s", "CHAR",
    description="STATISTICS_LEVEL 参数当前值（应为 TYPICAL）。对标 zCloud 巡检 STATISTICS_LEVEL 非 TYPICAL 告警。YashanDB 默认 TYPICAL。",
    trigger_expr="last(/YashanDB by Zabbix Agent/yashandb.db.statistics_level)<> 'TYPICAL'",
    trigger_name="YashanDB: STATISTICS_LEVEL 非 TYPICAL ({HOST.NAME})",
    trigger_priority="HIGH",
    trigger_desc="STATISTICS_LEVEL 不是 TYPICAL，可能影响 SQL 优化器性能和统计信息收集。"
))

print("=== 新增 Items XML ===")
for item in new_items:
    print(item)

print("\n=== Discovery Rules XML ===")
wait_class_discovery = """
            <discovery_rule>
                <uuid>e201010000000000000000000000001</uuid>
                <name>YashanDB: 等待类自动发现</name>
                <key>yashandb.wait_class.discovery</key>
                <delay>3600s</delay>
                <description>自动发现所有等待类，为每个等待类创建监控项原型</description>
                <item_prototypes>
                    <item_prototype>
                        <uuid>e201010000000000000000000000002</uuid>
                        <name>YashanDB: 等待类 [{#WAIT_CLASS}] 总等待次数</name>
                        <key>yashandb.db.wait_class.count[{#WAIT_CLASS}]</key>
                        <delay>60s</delay>
                        <history>7d</history>
                        <trends>90d</trends>
                        <value_type>UNSIGNED</value_type>
                        <description>V$SYSTEM_WAIT_CLASS 中 {#WAIT_CLASS} 等待类的 TOTAL_WAITS。</description>
                    </item_prototype>
                    <item_prototype>
                        <uuid>e201010000000000000000000000003</uuid>
                        <name>YashanDB: 等待类 [{#WAIT_CLASS}] 总等待时间</name>
                        <key>yashandb.db.wait_class.time[{#WAIT_CLASS}]</key>
                        <delay>60s</delay>
                        <history>7d</history>
                        <trends>90d</trends>
                        <value_type>UNSIGNED</value_type>
                        <units>s</units>
                        <description>V$SYSTEM_WAIT_CLASS 中 {#WAIT_CLASS} 等待类的 TIME_WAITED（厘秒→秒）。</description>
                    </item_prototype>
                </item_prototypes>
            </discovery_rule>"""

session_user_discovery = """
            <discovery_rule>
                <uuid>e201010000000000000000000000004</uuid>
                <name>YashanDB: 用户会话分布自动发现</name>
                <key>yashandb.session.user.discovery</key>
                <delay>300s</delay>
                <description>自动发现所有用户会话，为每个用户创建监控项原型</description>
                <item_prototypes>
                    <item_prototype>
                        <uuid>e201010000000000000000000000005</uuid>
                        <name>YashanDB: 用户 [{#USERNAME}] 会话数</name>
                        <key>yashandb.session.by_user[{#USERNAME}]</key>
                        <delay>60s</delay>
                        <history>7d</history>
                        <trends>90d</trends>
                        <value_type>UNSIGNED</value_type>
                        <description>V$SESSION 中指定用户的会话数量。用于连接池效率分析。</description>
                    </item_prototype>
                </item_prototypes>
            </discovery_rule>"""

invalid_obj_discovery = """
            <discovery_rule>
                <uuid>e201010000000000000000000000006</uuid>
                <name>YashanDB: INVALID 对象类型自动发现</name>
                <key>yashandb.invalid_objects.by_type.discovery</key>
                <delay>3600s</delay>
                <description>自动发现所有 INVALID 对象类型，为每个类型创建监控项原型</description>
                <item_prototypes>
                    <item_prototype>
                        <uuid>e201010000000000000000000000007</uuid>
                        <name>YashanDB: INVALID 对象数量（{#OBJTYPE}）</name>
                        <key>yashandb.invalid_objects.by_type[{#OBJTYPE}]</key>
                        <delay>3600s</delay>
                        <history>7d</history>
                        <trends>90d</trends>
                        <value_type>UNSIGNED</value_type>
                        <description>DBA_OBJECTS 中 STATUS='INVALID' 且 OBJECT_TYPE='{#OBJTYPE}' 的对象数量。</description>
                    </item_prototype>
                </item_prototypes>
            </discovery_rule>"""

print(wait_class_discovery)
print(session_user_discovery)
print(invalid_obj_discovery)
