"""通过 Zabbix API 重建 yas-zabbix-agent 主机和监控项（确保正确注册到 Server 缓存）"""
import urllib.request, json, time

API_URL = 'http://localhost:8080/api_jsonrpc.php'

def api_call(method, params, auth=None):
    req = urllib.request.Request(API_URL,
        data=json.dumps({'jsonrpc': '2.0', 'method': method,
                         'params': params, 'auth': auth, 'id': 1}).encode(),
        headers={'Content-Type': 'application/json'})
    resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
    if 'error' in resp:
        print(f'API ERROR: {resp["error"]}')
        return None
    return resp.get('result')

# Login
auth = api_call('user.login', {'username': 'Admin', 'password': 'zabbix'})
if not auth:
    print('Login failed')
    exit(1)
print('Logged in')

# Step 1: Get or create host group
groups = api_call('hostgroup.get', {'output': ['groupid', 'name']}, auth)
linux_group = next((g for g in groups if g['name'] == 'Linux servers'), None)
if linux_group:
    groupid = linux_group['groupid']
    print(f'Using existing group "Linux servers": {groupid}')
else:
    result = api_call('hostgroup.create', {'name': 'Linux servers'}, auth)
    groupid = result['groupids'][0]
    print(f'Created group "Linux servers": {groupid}')

# Step 2: Delete existing broken host
existing = api_call('host.get', {'filter': {'host': 'yas-zabbix-agent'}}, auth)
if existing:
    hid = existing[0]['hostid']
    api_call('host.delete', [hid], auth)
    print(f'Deleted existing host {hid}')

# Step 3: Create host with interface via API
host_result = api_call('host.create', {
    'host': 'yas-zabbix-agent',
    'name': 'YashanDB Agent (API)',
    'interfaces': [{
        'type': 1,           # Zabbix Agent
        'main': 1,
        'useip': 1,
        'ip': '172.18.0.3',
        'dns': '',
        'port': '10050'
    }],
    'groups': [{'groupid': groupid}],
    'status': 0
}, auth)
hostid = host_result['hostids'][0]
print(f'Created host: {hostid} (yas-zabbix-agent)')

# Step 4: Read template XML and create items
import xml.etree.ElementTree as ET
tree = ET.parse(r'C:\Users\DELL\WorkBuddy\Claw\yas_zabbix\template\yashandb_zabbix_template_7.0.xml')
root = tree.getroot()

VALUE_TYPE_MAP = {'UNSIGNED': 3, 'FLOAT': 0, 'STR': 1, 'LOG': 2, 'DB': 4, 'TEXT': 5}
tmpl = root.find('.//template')
items_xml = tmpl.findall('.//items/item') + tmpl.findall('.//discovery_rules/item')

created = 0
errors = 0
for el in items_xml:
    name = (el.findtext('name') or '').strip()
    key = (el.findtext('key') or '').strip()
    if not name or not key:
        continue

    delay_el = el.find('delay')
    delay = delay_el.text.strip() if delay_el is not None and delay_el.text else '60s'

    vt_el = el.find('value_type')
    vt = VALUE_TYPE_MAP.get(vt_el.text.strip() if vt_el is not None and vt_el.text else '', 3) if vt_el is not None else 3

    desc_el = el.find('description')
    desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ''

    result = api_call('item.create', {
        'hostid': hostid,
        'name': name,
        'key_': key,
        'type': 5,           # Zabbix Agent (passive)
        'value_type': vt,
        'delay': delay,
        'history': '7d',
        'trends': '365d',
        'status': 0,
        'description': desc,
    }, auth)

    if result:
        created += 1
        if created % 20 == 0:
            print(f'  Created {created} items...')
    else:
        errors += 1
        print(f'  FAILED: {key}')

print(f'\nDone! Created {created} items, {errors} errors')

# Step 5: Verify
time.sleep(2)
items = api_call('item.get', {'hostids': [hostid], 'output': ['itemid', 'key_', 'type', 'delay', 'status']}, auth)
print(f'Host has {len(items)} items')
for item in items[:3]:
    print(f'  {item["key_"]}: type={item["type"]}, delay={item["delay"]}')

print(f'\nHost URL: http://localhost:8080/zabbix.php?action=host.view&hostid={hostid}')
