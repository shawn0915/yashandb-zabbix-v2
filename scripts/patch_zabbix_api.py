#!/usr/bin/env python3
"""精确补丁 zabbix_api.py for Zabbix 7.x Bearer token auth."""
import re

LIB = "/home/shawnyan/.local/lib/python3.9/site-packages/zabbix_api.py"
BACKUP = LIB + ".bak9"

with open(LIB, "r", encoding="utf-8") as f:
    src = f.read()
with open(BACKUP, "w") as f:
    f.write(src)
print(f"Backup: {BACKUP}")

# ── 1. version_compare: handle None ─────────────────────────────────────────
old_vc = '''def version_compare(v1, v2):
    """
    The result is 0 if v1 == v2, -1 if v1 < v2, and +1 if v1 > v2
    """
    for v1_part, v2_part in zip(v1.split("."), v2.split(".")):
        if v1_part.isdecimal() and v2_part.isdecimal():
            if int(v1_part) > int(v2_part):
                return 1
            elif int(v1_part) < int(v2_part):
                return -1
        else:
            if v1 > v2:
                return 1
            elif v1 < v2:
                return -1
    return 0'''
new_vc = '''def version_compare(v1, v2):
    """
    The result is 0 if v1 == v2, -1 if v1 < v2, and +1 if v1 > v2
    """
    if v1 is None:
        return 1  # assume modern (>= 7.x)
    for v1_part, v2_part in zip(v1.split("."), v2.split(".")):
        if v1_part.isdecimal() and v2_part.isdecimal():
            if int(v1_part) > int(v2_part):
                return 1
            elif int(v1_part) < int(v2_part):
                return -1
        else:
            if v1 > v2:
                return 1
            elif v1 < v2:
                return -1
    return 0'''
if old_vc in src:
    src = src.replace(old_vc, new_vc)
    print("[OK] version_compare patched")
else:
    print("[FAIL] version_compare pattern not found")

# ── 2. api_version: replace entirely ─────────────────────────────────────────
old_av = '''    def api_version(self, **options):
        obj = self.do_request(self.json_obj('apiinfo.version', options, auth=False))
        return obj['result']'''
new_av = '''    def api_version(self, **options):
        # Zabbix 7.x: try with Bearer token first (will be empty before login)
        for use_bearer in [False, True]:
            headers = {'Content-Type': 'application/json-rpc'}
            if use_bearer and self.auth:
                headers['Authorization'] = 'Bearer ' + str(self.auth)
            body = json.dumps({'jsonrpc': '2.0', 'method': 'apiinfo.version',
                                'params': options, 'id': self.id}).encode()
            try:
                req = urllib2.Request(url=self.url, data=body, headers=headers)
                opener = urllib2.build_opener(urllib2.HTTPHandler())
                urllib2.install_opener(opener)
                resp = opener.open(req, timeout=self.timeout)
                result = json.loads(resp.read().decode())
                if result.get('result'):
                    return result['result']
            except Exception:
                pass
        return None'''
if old_av in src:
    src = src.replace(old_av, new_av)
    print("[OK] api_version patched")
else:
    print("[FAIL] api_version pattern not found")

# ── 3. login: safe version check ─────────────────────────────────────────────
old_login = """        if version_compare(self.api_version(), '5.4') >= 0:
            login_arg = {'username': l_user, 'password': l_password}
        else:
            login_arg = {'user': l_user, 'password': l_password}"""
new_login = """        # Zabbix 7.x style; api_version may fail with Bearer requirement
        try:
            ver = self.api_version()
        except Exception:
            ver = None
        if ver and version_compare(ver, '5.4') < 0:
            login_arg = {'user': l_user, 'password': l_password}
        else:
            login_arg = {'username': l_user, 'password': l_password}"""
if old_login in src:
    src = src.replace(old_login, new_login)
    print("[OK] login patched")
else:
    print("[FAIL] login pattern not found")

# ── 4. do_request: Bearer header + remove auth from body ─────────────────────
old_dr = '''    def do_request(self, json_obj):
        headers = {'Content-Type': 'application/json-rpc',
                   'User-Agent': 'python/zabbix_api'}

        if self.httpuser:
            self.debug(logging.INFO, "HTTP Auth enabled")
            credentials = (self.httpuser + ':' + self.httppasswd).encode('ascii')
            auth = 'Basic ' + base64.b64encode(credentials).decode("ascii")
            headers['Authorization'] = auth
        self.r_query.append(str(json_obj))
        self.debug(logging.INFO, "Sending: " + str(json_obj))
        self.debug(logging.DEBUG, "Sending headers: " + str(headers))'''
new_dr = '''    def do_request(self, json_obj):
        headers = {'Content-Type': 'application/json-rpc',
                   'User-Agent': 'python/zabbix_api'}

        if self.httpuser:
            self.debug(logging.INFO, "HTTP Auth enabled")
            credentials = (self.httpuser + ':' + self.httppasswd).encode('ascii')
            auth = 'Basic ' + base64.b64encode(credentials).decode("ascii")
            headers['Authorization'] = auth
        elif self.auth:
            # Zabbix 7.x: Bearer token in header (NOT in JSON body)
            headers['Authorization'] = 'Bearer ' + str(self.auth)

        # Zabbix 7.x: remove 'auth' from JSON body (not supported)
        if isinstance(json_obj, str):
            try:
                obj = json.loads(json_obj)
                if 'auth' in obj:
                    del obj['auth']
                    json_obj = json.dumps(obj)
            except Exception:
                pass

        self.r_query.append(str(json_obj))
        self.debug(logging.INFO, "Sending: " + str(json_obj))
        self.debug(logging.DEBUG, "Sending headers: " + str(headers))'''
if old_dr in src:
    src = src.replace(old_dr, new_dr)
    print("[OK] do_request patched")
else:
    print("[FAIL] do_request pattern not found")

with open(LIB, "w", encoding="utf-8") as f:
    f.write(src)
print("Saved:", LIB)

# Verify syntax
import subprocess, sys
r = subprocess.run(["python3", "-m", "py_compile", LIB], capture_output=True)
if r.returncode == 0:
    print("[OK] Syntax check passed")
else:
    print("[FAIL] Syntax error:", r.stderr.decode())
    sys.exit(1)
