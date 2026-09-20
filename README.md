# SOMT

> SOMT 是一个 **SystemOne** 模型的工具包，包含一个 Python 类和 Playground 网页。
>
> 默认为 TypeSafe 的 Jev 模型。

## Python 类

Python 类代码：`sopy/systemone.py`

使用示例：`example.py`

## Playground 网页

### 1. 准备

- 在 [TypeSafe 官网](https://typesafe.ai/) 注册账号；

- 在 [TypeSafe API Keys](https://console.typesafe.ai/keys) 创建 API Key，保存至根目录文件 `systemone.apikey` 或输入至 Playground 界面。

### 2. 使用

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

### 3. 其他

- **调整各项上限**：修改 `config.js`，保存后刷新页面即可；

- 运行记录保存在同目录的 `run-log.jsonl`，可以自行备份或删除。
