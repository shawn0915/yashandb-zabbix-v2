#!/bin/bash
# YashanDB Monitor Wrapper
# 确保 LD_LIBRARY_PATH 正确设置后再调用监控脚本
# 此脚本由 zabbix_agentd 通过 UserParameter 调用

# YashanDB C 驱动库路径（与 Docker run -e YASDB_LIB_PATH 对应）
YASDB_LIB_PATH="${YASDB_LIB_PATH:-/opt/yashandb/yashandb_yasdb_home/lib}"
export LD_LIBRARY_PATH="${YASDB_LIB_PATH}:${LD_LIBRARY_PATH}"

# 转发所有参数给监控脚本
exec python3 /etc/zabbix/scripts/yashandb/yashandb_monitor.py "$@"
