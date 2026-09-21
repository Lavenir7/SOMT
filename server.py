#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jev Playground 本地服务。

作用：
  1. 托管 index.html（同目录静态文件）。
  2. 提供 /api/systemone 代理，把浏览器请求转发到 TypeSafe API。
     —— 因为 https://api.typesafe.ai 不允许浏览器跨域直连，必须经由本地代理。
  3. 自动读取同目录下的 systemone.apikey 作为 API Key（也可在页面顶部临时填写覆盖）。
  4. 把每次运行的请求与返回追加记录到本地文件 run-log.jsonl。

API Key 优先级：请求头 > systemone.apikey > 环境变量 TYPESAFE_API_KEY。

只依赖 Python 标准库，直接运行：

    python server.py                              # 默认 http://127.0.0.1:8000
    python server.py --port 9000                  # 换端口
    python server.py --host 0.0.0.0 --port 9000   # 换地址与端口

也可用环境变量（命令行参数优先）：
    HOST=127.0.0.1                 监听地址
    PORT=8000                      监听端口
    TYPESAFE_API_KEY=<key>          备用 API Key（优先级低于 systemone.apikey）
    JEV_ALLOW_ANY_HOST=1           允许代理到任意 URL（默认只允许 *.typesafe.ai）
    JEV_ALLOW_REMOTE_KEY_WRITE=1   允许非本机请求写入 API Key（默认仅本机）
    JEV_LOG_FILE=<path>            运行记录文件（默认同目录 run-log.jsonl）
    JEV_LOG_DISABLE=1              关闭运行记录
    JEV_TIMEOUT=180                转发请求超时秒数

本地记录：每次 /api/systemone 调用（请求的 model/state/questions + 返回的
model/answers/usage + 状态码/耗时）都会追加写入 run-log.jsonl（每行一个 JSON）。
可通过 GET /api/logs?limit=20 查看最近记录。
"""

import argparse
import json
import os
import posixpath
import sys
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
TIMEOUT = int(os.environ.get("JEV_TIMEOUT", "180"))
ALLOW_ANY = os.environ.get("JEV_ALLOW_ANY_HOST", "") not in ("", "0", "false", "False")
ALLOW_REMOTE_KEY_WRITE = os.environ.get("JEV_ALLOW_REMOTE_KEY_WRITE", "") not in ("", "0", "false", "False")
ALLOW_REMOTE_LOG_WRITE = os.environ.get("JEV_ALLOW_REMOTE_LOG_WRITE", "") not in ("", "0", "false", "False")
DEFAULT_TARGET = "https://api.typesafe.ai/v1/systemone"

KEY_FILE = os.path.join(HERE, "systemone.apikey")
KEY_FILE_NAME = "systemone.apikey"
ENV_KEY_NAME = "TYPESAFE_API_KEY"

# 每次运行（请求 + 返回）追加写入的本地记录文件（JSONL，每行一个 JSON）
DEFAULT_LOG_NAME = "run-log.jsonl"
LOG_FILE = os.environ.get("JEV_LOG_FILE") or os.path.join(HERE, DEFAULT_LOG_NAME)
if not os.path.isabs(LOG_FILE):
    LOG_FILE = os.path.join(HERE, LOG_FILE)
LOG_FILE_NAME = os.path.basename(LOG_FILE)
LOG_DISABLED = os.environ.get("JEV_LOG_DISABLE", "") not in ("", "0", "false", "False")

ALLOWED_EXT = {".html", ".htm", ".js", ".css", ".json", ".svg", ".ico",
                ".png", ".jpg", ".jpeg", ".webp", ".gif", ".woff", ".woff2", ".map", ".txt"}

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


def is_allowed_target(url: str) -> bool:
    if ALLOW_ANY:
        return True
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    return host == "typesafe.ai" or host.endswith(".typesafe.ai")


def extract_bearer(auth: str) -> str:
    if not auth:
        return ""
    parts = auth.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return auth.strip()


def read_key_file():
    """读取 systemone.apikey，忽略空行与 # 开头的注释行。返回 (key, error)。"""
    try:
        with open(KEY_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line, None
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        return None, str(exc)
    return None, None


def resolve_api_key(header_auth: str):
    """优先级：请求头 > systemone.apikey > 环境变量。返回 (key, source)。"""
    token = extract_bearer(header_auth)
    if token:
        return token, "request"
    key, _ = read_key_file()
    if key:
        return key, "file"
    env = (os.environ.get(ENV_KEY_NAME) or "").strip()
    if env:
        return env, "env"
    return None, None


def mask_key(key):
    if not key:
        return None
    if len(key) <= 10:
        return "…"
    return key[:6] + "..." + key[-4:]


def is_loopback(addr: str) -> bool:
    host = (addr or "").split("%")[0]
    return host in ("127.0.0.1", "::1", "localhost")


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def append_log(entry):
    """把一条运行记录追加到本地 JSONL 文件；失败不影响主流程。"""
    if LOG_DISABLED:
        return
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        sys.stderr.write("[jev] 写入运行记录失败: %s\n" % exc)


def read_log_tail(limit=20):
    """读取本地记录文件最后 limit 条。"""
    if not os.path.isfile(LOG_FILE):
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return []
    out = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            out.append({"raw": line})
    return out


def gen_id():
    return "run_" + uuid.uuid4().hex[:16]


def ensure_log_ids():
    """为旧记录补上 id（就地重写一次），使每条记录都能单独删除。"""
    if LOG_DISABLED or not os.path.isfile(LOG_FILE):
        return
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return
    changed = False
    out = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            out.append(s + "\n")
            continue
        if isinstance(obj, dict) and not obj.get("id"):
            obj["id"] = gen_id()
            changed = True
        out.append(json.dumps(obj, ensure_ascii=False) + "\n")
    if changed:
        try:
            tmp = LOG_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.writelines(out)
            os.replace(tmp, LOG_FILE)
            sys.stderr.write("[jev] 已为运行记录补全 id\n")
        except OSError as exc:
            sys.stderr.write("[jev] 补全运行记录 id 失败: %s\n" % exc)


def delete_log_ids(ids):
    """按 id 删除记录；id 为空集合且 all_ids=True 时清空。返回删除条数。"""
    if not os.path.isfile(LOG_FILE):
        return 0
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return 0
    keep = []
    removed = 0
    for line in lines:
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            keep.append(s + "\n")
            continue
        if isinstance(obj, dict) and obj.get("id") in ids:
            removed += 1
            continue
        keep.append(json.dumps(obj, ensure_ascii=False) + "\n")
    if removed:
        try:
            tmp = LOG_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.writelines(keep)
            os.replace(tmp, LOG_FILE)
        except OSError as exc:
            sys.stderr.write("[jev] 删除运行记录失败: %s\n" % exc)
            return 0
    return removed


class Handler(BaseHTTPRequestHandler):
    server_version = "JevPlayground/1.0"

    # -- quieter, clearer logging -------------------------------------------
    def log_message(self, fmt, *args):
        sys.stderr.write("[jev] %s - %s\n" % (self.address_string(), fmt % args))

    # -- helpers -------------------------------------------------------------
    def _send(self, status, body: bytes, content_type="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Jev-Url")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Expose-Headers", "X-Jev-Log-Id")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, status, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    # -- GET -----------------------------------------------------------------
    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path in ("/api/health", "/api/health/"):
            self._send_json(200, {"ok": True, "service": "jev-playground"})
            return
        if path in ("/api/systemone", "/api/systemone/"):
            self._send_json(405, {"error": {"message": "请使用 POST"}})
            return
        if path in ("/api/config", "/api/config/"):
            key, source = resolve_api_key("")
            self._send_json(200, {
                "ok": True,
                "hasKey": bool(key),
                "source": source,
                "keyHint": mask_key(key),
                "keyFile": KEY_FILE_NAME,
                "logFile": LOG_FILE_NAME,
                "logEnabled": not LOG_DISABLED,
            })
            return
        if path in ("/api/logs", "/api/logs/"):
            query = urlparse(self.path).query
            params = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
            try:
                limit = int(params.get("limit", "20"))
            except ValueError:
                limit = 20
            limit = max(1, min(limit, 500))
            entries = read_log_tail(limit)
            self._send_json(200, {
                "ok": True,
                "file": LOG_FILE_NAME,
                "enabled": not LOG_DISABLED,
                "count": len(entries),
                "entries": entries,
            })
            return
        self._serve_static(path)

    def do_HEAD(self):
        self.do_GET()

    # -- POST ----------------------------------------------------------------
    def do_POST(self):
        path = unquote(urlparse(self.path).path)
        if path in ("/api/systemone", "/api/systemone/"):
            self._proxy()
            return
        if path in ("/api/apikey", "/api/apikey/"):
            self._save_api_key()
            return
        if path in ("/api/logs/delete", "/api/logs/delete/"):
            self._delete_logs()
            return
        self._send_json(404, {"error": {"message": "未知接口: %s" % path}})

    def do_OPTIONS(self):
        self._send(204, b"")

    # -- static files --------------------------------------------------------
    def _serve_static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        # normalize and block traversal
        safe = posixpath.normpath(path).lstrip("/")
        if safe.startswith("..") or os.path.isabs(safe):
            self._send(403, "Forbidden", "text/plain; charset=utf-8")
            return
        ext = os.path.splitext(safe)[1].lower()
        if ext not in ALLOWED_EXT:
            self._send(404, "Not Found", "text/plain; charset=utf-8")
            return
        full = os.path.join(HERE, *safe.split("/"))
        if not os.path.abspath(full).startswith(HERE) or not os.path.isfile(full):
            self._send(404, "Not Found", "text/plain; charset=utf-8")
            return
        ctype = MIME.get(ext, "application/octet-stream")
        try:
            with open(full, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            self._send(500, "Read error: %s" % exc, "text/plain; charset=utf-8")
            return
        self._send(200, data, ctype)

    # -- API key storage -----------------------------------------------------
    def _save_api_key(self):
        if not is_loopback(self.client_address[0]) and not ALLOW_REMOTE_KEY_WRITE:
            self._send_json(403, {"error": {"message": "仅允许本机写入 API Key"}})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            self._send_json(400, {"error": {"message": "请求体必须是 JSON"}})
            return

        key = (data.get("apiKey") or "").strip()
        if not key:
            # 空值 = 清除本地文件
            try:
                if os.path.exists(KEY_FILE):
                    os.remove(KEY_FILE)
            except OSError as exc:
                self._send_json(500, {"error": {"message": "删除失败: %s" % exc}})
                return
            self._send_json(200, {"ok": True, "hasKey": False, "source": None, "keyHint": None})
            return
        if any(ch in key for ch in "\r\n\t ") or len(key) > 512:
            self._send_json(400, {"error": {"message": "API Key 格式不合法（不能包含空白字符或过长）"}})
            return
        try:
            with open(KEY_FILE, "w", encoding="utf-8") as fh:
                fh.write(key + "\n")
            try:
                os.chmod(KEY_FILE, 0o600)
            except OSError:
                pass
        except OSError as exc:
            self._send_json(500, {"error": {"message": "写入失败: %s" % exc}})
            return
        self._send_json(200, {"ok": True, "hasKey": True, "source": "file", "keyHint": mask_key(key)})

    # -- run log -------------------------------------------------------------
    def _write_run_log(self, body, target, payload, status, started):
        entry = {
            "id": gen_id(),
            "time": now_iso(),
            "target": target,
            "status": status,
            "ok": 200 <= status < 300,
            "duration_ms": int((time.time() - started) * 1000),
        }
        try:
            req_json = json.loads(body.decode("utf-8")) if body else None
        except Exception:
            req_json = None
        if isinstance(req_json, dict):
            entry["model_requested"] = req_json.get("model")
            entry["state"] = req_json.get("state")
            entry["questions"] = req_json.get("questions")
        elif body:
            entry["request_raw"] = body.decode("utf-8", "replace")[:4000]
        try:
            resp_json = json.loads(payload.decode("utf-8"))
        except Exception:
            resp_json = None
        if isinstance(resp_json, dict):
            entry["model"] = resp_json.get("model")
            entry["answers"] = resp_json.get("answers")
            entry["usage"] = resp_json.get("usage")
            if not entry["ok"]:
                entry["error"] = resp_json
        elif payload:
            entry["response_raw"] = payload.decode("utf-8", "replace")[:4000]
        append_log(entry)
        return entry.get("id")

    # -- run log delete ------------------------------------------------------
    def _delete_logs(self):
        if not is_loopback(self.client_address[0]) and not ALLOW_REMOTE_LOG_WRITE:
            self._send_json(403, {"error": {"message": "仅允许本机删除运行记录"}})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            self._send_json(400, {"error": {"message": "请求体必须是 JSON"}})
            return
        if data.get("all"):
            # 清空：直接截断文件
            try:
                if os.path.exists(LOG_FILE):
                    with open(LOG_FILE, "w", encoding="utf-8"):
                        pass
            except OSError as exc:
                self._send_json(500, {"error": {"message": "清空失败: %s" % exc}})
                return
            self._send_json(200, {"ok": True, "deleted": "all"})
            return
        ids = data.get("ids") or []
        if not isinstance(ids, list) or not ids:
            self._send_json(400, {"error": {"message": "缺少 ids"}})
            return
        removed = delete_log_ids(set(str(i) for i in ids))
        self._send_json(200, {"ok": True, "deleted": removed})

    # -- API proxy -----------------------------------------------------------
    def _proxy(self):
        started = time.time()
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length else b""

        target = (self.headers.get("X-Jev-Url") or DEFAULT_TARGET).strip()
        if not is_allowed_target(target):
            self._send_json(400, {"error": {"message":
                "拒绝代理到该地址（仅允许 *.typesafe.ai）。可用 JEV_ALLOW_ANY_HOST=1 放开。"}})
            return

        auth = self.headers.get("Authorization", "")
        key, source = resolve_api_key(auth)
        if not key:
            self._send_json(401, {"error": {"message":
                "未找到 API Key。请把 Key 写入同目录的 " + KEY_FILE_NAME + "，或在页面顶部填写。"}})
            return

        req = urlrequest.Request(
            target,
            data=body,
            method="POST",
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": self.headers.get("Content-Type", "application/json"),
                "Accept": "application/json",
                "User-Agent": "jev-playground/1.0",
            },
        )

        try:
            with urlrequest.urlopen(req, timeout=TIMEOUT) as resp:
                payload = resp.read()
                status = resp.status
                ctype = resp.headers.get("Content-Type", "application/json; charset=utf-8")
        except urlerror.HTTPError as exc:
            payload = exc.read()
            status = exc.code
            ctype = exc.headers.get("Content-Type", "application/json; charset=utf-8") if exc.headers else "application/json; charset=utf-8"
        except urlerror.URLError as exc:
            self._send_json(502, {"error": {"message": "连接 TypeSafe 失败: %s" % exc.reason}})
            return
        except Exception as exc:  # noqa: BLE001
            self._send_json(502, {"error": {"message": "代理异常: %s" % exc}})
            return

        log_id = self._write_run_log(body, target, payload, status, started)
        self._send(status, payload, ctype, extra=(({"X-Jev-Log-Id": log_id} if log_id else None)))


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        prog="server.py",
        description="Jev Playground 本地服务（静态托管 + TypeSafe API 代理）。",
    )
    ap.add_argument("-H", "--host", default=None,
                    help="监听地址，默认 127.0.0.1（也可用环境变量 HOST）")
    ap.add_argument("-p", "--port", type=int, default=None,
                    help="监听端口，默认 8000（也可用环境变量 PORT）")
    return ap.parse_args(argv)


def main():
    global HOST, PORT
    args = parse_args()
    if args.host:
        HOST = args.host
    if args.port:
        PORT = args.port
    ensure_log_ids()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = "http://%s:%d" % (HOST if HOST != "0.0.0.0" else "localhost", PORT)
    print("Jev Playground 已启动 →  %s" % url)
    print("代理接口: POST /api/systemone   (转发到 %s)" % DEFAULT_TARGET)
    key, source = resolve_api_key("")
    if key:
        where = {"file": KEY_FILE_NAME, "env": ENV_KEY_NAME}.get(source, source or "?")
        print("API Key: 已从 %s 读取 (%s)" % (where, mask_key(key)))
    else:
        print("API Key: 未配置。请把 Key 写入 %s，或在页面顶部填写后点「保存」。" % KEY_FILE_NAME)
    if LOG_DISABLED:
        print("运行记录: 已关闭 (JEV_LOG_DISABLE)")
    else:
        print("运行记录: 每次运行写入 %s" % LOG_FILE)
    if ALLOW_ANY:
        print("注意: JEV_ALLOW_ANY_HOST 已开启，可代理到任意地址。")
    print("按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
