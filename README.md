# SOMT

> SOMT 是一个 **SystemOne** 模型的工具包，包含一个 Python 类和 Playground 网页。

## SystemOne 提供商

| SystemOne Provider               | SystemOne Models       | others                                       |
| :-:                              | :-:                    | :-:                                          |
| [TypeSafe](https://typesafe.ai/) | `Jev`                  | [API Keys](https://console.typesafe.ai/keys) |
| [Ollama](https://ollama.com)     | `nimble` `tev1` `clef` | /                                            |

## Python 类

Python 类代码：[systemone.py](sopy/systemone.py)

使用示例：[example.py](sopy/example.py)

## Playground 网页

### 使用

#### 启动服务

```bash
python server.py
```

启动服务，打开 `http://localhost:8000` （`Ctrl+C` 停止服务）

#### 修改地址和端口

- 使用命令行参数（推荐）：

```bash
python server.py --port 9000
python server.py --host 0.0.0.0 --port 9000
```

- 使用环境变量：

```bash
HOST=0.0.0.0 PORT=9000 python server.py
```

---

### 其他

- `config.js`：**调整各项上限**，保存后刷新页面即可；

- `models.json`：**Provider / Model** 配置；

- **环境变量**：

```bash
TYPESAFE_API_KEY=<key>          # 备用 API Key
SO_ALLOW_REMOTE_KEY_WRITE=1     # 允许非本机读写 apikey.json（默认仅本机）
SO_ALLOW_REMOTE_MODEL_WRITE=1   # 允许非本机增删自定义 Provider（默认仅本机）
SO_TIMEOUT=180                  # 转发请求超时秒数
SO_LOG_FILE=<path>              # 运行记录文件（默认 run-log.jsonl）
SO_LOG_DISABLE=1                # 关闭运行记录
```

- 运行记录保存在同目录的 `run-log.jsonl`，可以自行备份或删除。
