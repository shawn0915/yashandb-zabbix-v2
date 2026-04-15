#!/usr/bin/env python3
"""Zabbix 模板导入 + 主机创建脚本（直连 MySQL，Zabbix 7.x 兼容）

用法：
    python zabbix_import.py --host yas-zabbix-agent [--dry-run]
"""

import argparse
import xml.etree.ElementTree as ET
import pymysql
import sys
import re
import uuid as _u
from datetime import datetime


def make_uuid():
    """生成 32 字符的 Zabbix 风格 UUID"""
    return _u.uuid4().hex  # 32 字符十六进制


# ===================== 配置 =====================
MYSQL_HOST = '172.30.112.1'
MYSQL_PORT = 3308
MYSQL_USER = 'zabbix'
MYSQL_PASSWORD = 'Zabbix2026'
MYSQL_DATABASE = 'zabbix'
XML_TEMPLATE_PATH = r'C:\Users\DELL\WorkBuddy\Claw\yas_zabbix\template\yashandb_zabbix_template_7.0.xml'


# ===================== XML 解析 =====================
def xml_text(el, default=''):
    return (el.text or '').strip() if el is not None else default


def parse_template_xml(path):
    """解析 Zabbix XML。关键：XML 中所有字段均为子元素（<delay>60s</delay>），
    type/value_type 为文本名（如 'UNSIGNED'），需映射为数字。"""
    tree = ET.parse(path)
    root = tree.getroot()

    VALUE_TYPE_MAP = {
        'UNSIGNED': 3, 'FLOAT': 0, 'STR': 1, 'LOG': 2,
        'DB': 4, 'TEXT': 5, 'BLOB': 6,
    }
    PRIORITY_MAP = {
        'NOT CLASSIFIED': 0, 'INFO': 1, 'WARNING': 2,
        'AVERAGE': 3, 'HIGH': 4, 'DISASTER': 5,
    }
    MANUAL_CLOSE_MAP = {'YES': 1, 'NO': 0}

    templates = []
    for tmpl_el in root.findall('.//template'):
        name = xml_text(tmpl_el.find('name'))
        tmpl_name = xml_text(tmpl_el.find('template'))
        uuid = xml_text(tmpl_el.find('uuid'))
        desc = xml_text(tmpl_el.find('description'))
        groups = [xml_text(g.find('name')) for g in tmpl_el.findall('.//groups/group')]

        def parse_item(e):
            delay_el = e.find('delay'); history_el = e.find('history')
            trends_el = e.find('trends'); vt_el = e.find('value_type')
            vt_str = xml_text(vt_el)
            return {
                'name': xml_text(e.find('name')),
                'type': '0',  # Zabbix Agent (active), default
                'key': xml_text(e.find('key')),  # key 是直接文本，不是嵌套
                'delay': xml_text(delay_el) if delay_el is not None else '30s',
                'history': xml_text(history_el) if history_el is not None else '7d',
                'trends': xml_text(trends_el) if trends_el is not None else '365d',
                'status': '0',  # enabled
                # XML 可能没有 <value_type> 标签，缺失时默认 UNSIGNED(3)
                'value_type': VALUE_TYPE_MAP.get(vt_str, 3) if vt_str else 3,
                'description': xml_text(e.find('description')),
                'flags': '0',
            }

        def parse_trigger(e):
            pri_el = e.find('priority'); mc_el = e.find('manual_close')
            return {
                'expression': xml_text(e.find('expression')),
                'name': xml_text(e.find('name')),
                'description': xml_text(e.find('description')),
                'url': xml_text(e.find('url')),
                'status': '0',
                'priority': str(PRIORITY_MAP.get(xml_text(pri_el), 2)),
                'type': '0',
                'recovery_mode': '0',
                'recovery_expression': xml_text(e.find('recovery_expression')),
                'manual_close': str(MANUAL_CLOSE_MAP.get(xml_text(mc_el), 0)),
                'event_name': xml_text(e.find('name')),
            }

        def parse_discovery_rule(e):
            return {
                'name': xml_text(e.find('name')),
                'key': xml_text(e.find('key')),
                'delay': xml_text(e.find('delay')) or '1h',
                'status': '0',
                'description': xml_text(e.find('description')),
                'items': [parse_item(i) for i in e.findall('.//item')],
            }

        items = [parse_item(i) for i in tmpl_el.findall('.//items/item')]
        discovery_rules = [parse_discovery_rule(r) for r in tmpl_el.findall('.//discovery_rules/discovery_rule')]
        # triggers 在 items 内嵌
        triggers = []
        for item_el in tmpl_el.findall('.//items/item'):
            for trig_el in item_el.findall('.//triggers/trigger'):
                triggers.append(parse_trigger(trig_el))
        # 也可能在顶层 triggers
        for trig_el in tmpl_el.findall('.//triggers/trigger'):
            triggers.append(parse_trigger(trig_el))

        graphs = []
        for g in tmpl_el.findall('.//graphs/graph'):
            gi_list = []
            for gi in g.findall('.//graph_item'):
                k = gi.find('.//key')
                ki = gi.find('.//key/value')
                key_text = xml_text(ki) if ki is not None else (xml_text(k) if k is not None else '')
                gi_list.append({'item_key': key_text, 'color': gi.get('color', '00DD00')})
            graphs.append({'name': xml_text(g.find('name')), 'items': gi_list,
                           'width': int(g.get('width', 900)), 'height': int(g.get('height', 200))})

        templates.append({
            'name': name, 'template': tmpl_name, 'uuid': uuid,
            'description': desc, 'groups': groups,
            'items': items, 'triggers': triggers, 'graphs': graphs,
            'discovery_rules': discovery_rules,
        })
    return templates


# ===================== 数据库工具 =====================
# 模板 items 专用 dummy interface（interfaceid=0 FK 不存在，需用虚拟 interfaceid）
DUMMY_INTERFACEID = 99999


def get_db_max(table, col):
    cur.execute(f"SELECT MAX({col}) FROM {table}")
    return cur.fetchone()[0] or 0


def next_id(table, col=None):
    """分配下一个自增ID。col 为 None 时自动推断（通常用主键列）。"""
    # 自动推断主键列名
    if col is None:
        col_map = {
            'hosts_groups': 'hostgroupid',
            'item_discovery': 'itemdiscoveryid',
            'graphs_items': 'gitemid',
            'graphs': 'graphid',
            'hosts': 'hostid',
            'items': 'itemid',
            'triggers': 'triggerid',
            'functions': 'functionid',
            'interface': 'interfaceid',
            'hstgrp': 'groupid',
        }
        col = col_map.get(table, 'id')
    n = get_db_max(table, col) + 1
    return n


def upsert(sql, params, table=None, where_col=None, where_val=None):
    """INSERT IGNORE + 打印摘要"""
    try:
        cur.execute(sql, params)
        if cur.rowcount > 0:
            print(f"    + {table}: inserted 1 row")
        return True
    except Exception as e:
        # 尝试 UPDATE 路径（如果已存在）
        if where_col and where_val:
            update_sql = sql.replace('INSERT', 'UPDATE').split('SET ')[0]
            try:
                cur.execute(f"SELECT 1 FROM {table} WHERE {where_col}=%s", (where_val,))
                if cur.fetchone():
                    cur.execute(f"UPDATE {table} SET " + sql.split('SET ')[1], params)
                    print(f"    ~ {table}: updated 1 row")
                    return True
            except:
                pass
        print(f"    ! {table}: {e}")
        return False


def get_group_id(name, gtype=0):
    """获取或创建组，返回 groupid"""
    cur.execute("SELECT groupid FROM hstgrp WHERE name=%s", (name,))
    r = cur.fetchone()
    if r:
        return r[0]
    gid = next_id('hstgrp', 'groupid')
    cur.execute("INSERT INTO hstgrp (groupid, name, flags, type) VALUES (%s,%s,0,%s)", (gid, name, gtype))
    print(f"    + 组 {name} (type={gtype}, gid={gid})")
    return gid


# ===================== 主逻辑 =====================
def do_import(tmpl, dry_run=False):
    """导入模板"""
    print(f"\n{'='*60}")
    print(f"模板: {tmpl['name']} | uuid={tmpl['uuid']}")

    # 检查是否已存在
    cur.execute("SELECT hostid FROM hosts WHERE uuid=%s AND flags=3", (tmpl['uuid'],))
    r = cur.fetchone()
    if r:
        print(f"  [已存在] template_hostid={r[0]}")
        return r[0]

    tid = next_id('hosts', 'hostid')
    print(f"  + 分配 template_hostid={tid}")

    # 1. 插入 hosts（模板，flags=3）
    cur.execute("""
        INSERT INTO hosts SET
            hostid=%s, host=%s, name=%s, flags=3, status=0,
            description=%s, uuid=%s, tls_connect=1, tls_accept=1,
            maintenance_status=0, maintenance_type=0, custom_interfaces=0,
            discover=0, monitored_by=0,
            ipmi_authtype=-1, ipmi_privilege=2,
            proxyid=NULL, templateid=NULL
    """, (tid, tmpl['template'], tmpl['name'], tmpl['description'][:65535] if tmpl['description'] else '', tmpl['uuid']))

    # 1b. 插入 dummy interface（模板 items 的 interfaceid FK 占位）
    cur.execute("""
        INSERT INTO interface SET
            interfaceid=%s, hostid=%s, type=1, main=1,
            useip=1, ip='127.0.0.1', dns='', port='10050', available=0,
            error='', errors_from=0, disable_until=0
    """, (DUMMY_INTERFACEID, tid))

    # 2. 主机组/模板组
    default_group = 'Templates/Databases'
    for gname in (tmpl['groups'] or [default_group]):
        gid = get_group_id(gname, gtype=1)
        cur.execute("INSERT IGNORE INTO hosts_groups (hostgroupid, hostid, groupid) VALUES (%s,%s,%s)",
                    (next_id('hosts_groups', 'hostgroupid'), tid, gid))

    # 3. 插入 items（模板）
    item_map = {}  # key -> itemid
    for item in tmpl['items']:
        key = item['key']
        if not key:
            continue
        iid = next_id('items', 'itemid')
        delay_str = item['delay'] or '30s'
        history_str = item['history'] or '7d'
        trends_str = item['trends'] or '365d'
        item_uuid = make_uuid()
        desc_str = item['description'][:65535] if item['description'] else ''
        item_type = int(item['type']) if item['type'] else 0

        cur.execute("""
            INSERT INTO items SET
                itemid=%s, hostid=%s, name=%s, type=%s, key_=%s,
                delay=%s, history=%s, trends=%s, status=%s,
                value_type=%s, description=%s, flags=0,
                interfaceid=%s, uuid=%s,
                timeout='30s', lifetime='30d',
                enabled_lifetime_type=2, enabled_lifetime='0',
                discover=0,
                params='', posts='', query_fields='', headers=''
        """, (iid, tid, item['name'], item_type, key,
              delay_str, history_str, trends_str, item['status'],
              item['value_type'], desc_str, DUMMY_INTERFACEID, item_uuid))
        item_map[key] = iid
    print(f"  + items: {len(item_map)} 条")

    # 4. 插入 triggers
    trig_map = {}  # expression -> triggerid
    for trig in tmpl['triggers']:
        expr = trig['expression']
        if not expr:
            continue
        trigid = next_id('triggers', 'triggerid')
        trig_uuid = make_uuid()
        trig_comments = trig['description'][:65535] if trig['description'] else ''

        cur.execute("""
            INSERT INTO triggers SET
                triggerid=%s, expression=%s, description=%s,
                url=%s, status=%s, value=0, priority=%s,
                comments=%s, error='', templateid=NULL, type=%s,
                state=0, flags=0,
                recovery_mode=%s, recovery_expression=%s,
                correlation_mode=0, correlation_tag='',
                manual_close=%s, opdata='',
                discover=0, event_name=%s, uuid=%s,
                url_name=''
        """, (trigid, expr, trig['name'], trig['url'] or '',
              trig['status'], trig['priority'], trig_comments,
              trig['type'], trig['recovery_mode'], trig['recovery_expression'] or '',
              trig['manual_close'], trig['event_name'], trig_uuid))
        trig_map[expr] = trigid

    print(f"  + triggers: {len(trig_map)} 条")

    # 5. 插入 functions（关联 trigger -> item）
    # 表达式格式: last(/{tmpl_name}/{item_key}) 或 change(/{tmpl_name}/{item_key}) 等
    func_count = 0
    for trig in tmpl['triggers']:
        expr = trig['expression']
        if not expr or expr not in trig_map:
            continue
        trigid = trig_map[expr]
        # 提取 /{host}/{item_key} 部分
        m = re.search(r'/[^/]+/([^)]+)\)', expr)
        if m:
            item_key_raw = m.group(1).strip()
            for k, iid in item_map.items():
                if item_key_raw == k or item_key_raw in k:
                    cur.execute("""
                        INSERT IGNORE INTO functions SET
                            functionid=%s, itemid=%s, triggerid=%s,
                            name='last', parameter='/'
                    """, (next_id('functions'), iid, trigid))
                    func_count += 1
                    break
    print(f"  + functions: {func_count} 条")

    # 6. 插入 graphs
    for g in tmpl['graphs']:
        if not g['name']:
            continue
        gid = next_id('graphs', 'graphid')
        graph_uuid = make_uuid()
        cur.execute("""
            INSERT INTO graphs SET
                graphid=%s, name=%s, width=%s, height=%s,
                templateid=NULL, show_work_period=1, show_triggers=1,
                graphtype=0, show_legend=1, show_3d=0,
                yaxismin=0.0, yaxismax=100.0,
                ymin_type=0, ymax_type=0,
                flags=0, discover=0, uuid=%s
        """, (gid, g['name'], g['width'], g['height'], graph_uuid))
        for gi in g['items']:
            gk = gi['item_key']
            for k, iid in item_map.items():
                if gk == k or gk in k:
                    cur.execute("""
                        INSERT IGNORE INTO graphs_items SET
                            gitemid=%s, graphid=%s, itemid=%s,
                            drawtype=0, sortorder=0, color=%s,
                            yaxisside=0, calc_fnc=2, type=0
                    """, (next_id('graphs_items'), gid, iid, gi['color']))
                    break
    print(f"  + graphs: {len(tmpl['graphs'])} 条")

    # 7. 插入 discovery_rules（LLOW）
    for dr in tmpl['discovery_rules']:
        key = dr['key']
        if not key:
            continue
        dr_uuid = make_uuid()
        parent_iid = next_id('items', 'itemid')
        delay_str = dr['delay'] or '1h'

        # 创建 LLD item (type=0=agent, flags=1=discover)
        cur.execute("""
            INSERT INTO items SET
                itemid=%s, hostid=%s, name=%s, type=0, key_=%s,
                delay=%s, history='7d', trends='365d', status=%s,
                value_type=4, description=%s, flags=1,
                interfaceid=%s, uuid=%s,
                timeout='30s', lifetime='30d',
                enabled_lifetime_type=2, enabled_lifetime='0',
                discover=0,
                params='', posts='', query_fields='', headers=''
        """, (parent_iid, tid, dr['name'], key, delay_str,
              dr['status'], dr['description'][:65535] if dr['description'] else '',
              DUMMY_INTERFACEID, dr_uuid))

        # 创建 item_discovery
        cur.execute("""
            INSERT IGNORE INTO item_discovery SET
                itemdiscoveryid=%s, itemid=%s, parent_itemid=%s,
                key_='', lastcheck=0, ts_delete=0, status=0,
                disable_source=0, ts_disable=0
        """, (next_id('item_discovery'), parent_iid, parent_iid))

        # LLD items
        for item in dr['items']:
            lld_key = item['key']
            if not lld_key:
                continue
            liid = next_id('items', 'itemid')
            lld_uuid = make_uuid()
            item_type = int(item['type']) if item['type'] else 0
            cur.execute("""
                INSERT INTO items SET
                    itemid=%s, hostid=%s, name=%s, type=%s, key_=%s,
                    delay=%s, history=%s, trends=%s, status=%s,
                    value_type=%s, description=%s, flags=1,
                    interfaceid=%s, uuid=%s,
                    timeout='30s', lifetime='30d',
                    enabled_lifetime_type=2, enabled_lifetime='0',
                    discover=0, master_itemid=%s,
                    params='', posts='', query_fields='', headers=''
            """, (liid, tid, item['name'], item_type, lld_key,
                  item['delay'] or '30s', item['history'] or '7d',
                  item['trends'] or '365d', item['status'],
                  item['value_type'], item['description'][:65535] if item['description'] else '',
                  DUMMY_INTERFACEID, lld_uuid, parent_iid))

        print(f"  + LLD: {dr['name']} (key={key})")

    print(f"  [OK] 模板导入完成，template_hostid={tid}")
    return tid


def do_create_host(host_name, template_tid, dry_run=False):
    """创建主机并关联模板"""
    print(f"\n{'='*60}")
    print(f"主机: {host_name}")

    # 检查是否已存在
    cur.execute("SELECT hostid FROM hosts WHERE host=%s AND flags=0", (host_name,))
    r = cur.fetchone()
    if r:
        print(f"  [已存在] hostid={r[0]}")
        return r[0]

    hid = next_id('hosts', 'hostid')
    print(f"  + 分配 hostid={hid}")

    # 1. 插入 hosts
    cur.execute("""
        INSERT INTO hosts SET
            hostid=%s, host=%s, name=%s, flags=0, status=0,
            description='', tls_connect=1, tls_accept=1,
            maintenance_status=0, maintenance_type=0, custom_interfaces=0,
            discover=0, monitored_by=0,
            ipmi_authtype=-1, ipmi_privilege=2,
            proxyid=NULL, templateid=NULL
    """, (hid, host_name, host_name))

    # 2. 加入主机组
    gid = get_group_id('Linux servers', gtype=0)
    cur.execute("INSERT IGNORE INTO hosts_groups (hostgroupid, hostid, groupid) VALUES (%s,%s,%s)",
                (next_id('hosts_groups', 'hostgroupid'), hid, gid))

    # 3. 创建 Agent 接口
    ifid = next_id('interface', 'interfaceid')
    cur.execute("""
        INSERT INTO interface SET
            interfaceid=%s, hostid=%s, type=1, main=1,
            useip=0, ip=%s, dns=%s, port=%s, available=0,
            error='', errors_from=0, disable_until=0
    """, (ifid, hid, host_name, '', '10050'))
    print(f"    + Agent 接口: {host_name}:10050 (interfaceid={ifid})")

    # ⚠️ 关键修复：将 items 的 interfaceid 从 DUMMY_INTERFACEID(99999) 更新为真实 interfaceid
    cur.execute("""
        UPDATE items
        SET interfaceid=%s
        WHERE hostid=%s AND interfaceid IS NULL
    """, (ifid, hid))
    updated_items = cur.rowcount
    if updated_items > 0:
        print(f"    + Items interfaceid 修复: {updated_items} 条")

    # 4. 关联模板
    cur.execute("INSERT IGNORE INTO hosts_templates (hostid, templateid) VALUES (%s,%s)",
                (hid, template_tid))
    print(f"    + 关联模板 hostid={template_tid}")

    print(f"  [OK] 主机创建完成，hostid={hid}")
    return hid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='yas-zabbix-agent')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--xml', default=XML_TEMPLATE_PATH)
    args = ap.parse_args()

    global cur

    print(f"[1] 解析 XML: {args.xml}")
    templates = parse_template_xml(args.xml)
    if not templates:
        print("[ERROR] 未找到模板")
        sys.exit(1)
    tmpl = templates[0]
    print(f"  模板: {tmpl['name']}")
    print(f"  Items: {len(tmpl['items'])}, Triggers: {len(tmpl['triggers'])}, "
          f"Graphs: {len(tmpl['graphs'])}, LLD: {len(tmpl['discovery_rules'])}")

    if args.dry_run:
        print("\n[DRY RUN] 退出")
        return

    print(f"\n[2] 连接 MySQL: {MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}")
    conn = pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE, charset='utf8mb4'
    )
    cur = conn.cursor()

    try:
        template_tid = do_import(tmpl)
        host_id = do_create_host(args.host, template_tid)
        conn.commit()
        print(f"\n[OK] 完成！")
        print(f"  模板 hostid : {template_tid}")
        print(f"  主机 hostid  : {host_id}")
        print(f"  主机名       : {args.host}")
        print(f"  模板         : {tmpl['name']}")
        print(f"  Zabbix Web  : http://localhost:8080")
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
