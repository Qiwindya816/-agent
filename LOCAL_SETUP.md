# 本机运行说明

- 项目目录：`D:\AI agent`
- 分支：`dev`（浅克隆）
- Python：3.12.4
- 独立环境：`.venv`
- VS Code 已设置为使用 `.venv\Scripts\python.exe`。

## 启动

先在 `.env` 中填写 `DEEPSEEK_API_KEY`，然后在项目目录运行：

```powershell
.\.venv\Scripts\python.exe main.py
```

无需激活环境，也无需修改 PowerShell 执行策略。模型名称和接口地址沿用项目的 `.env.example`；真实模型调用需要有效密钥和接口访问权限。

## 检查与重建

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
```

重新创建环境时：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest
```

`requirements.local.lock.txt` 保存本次安装的实际版本，可用于同类 Windows / Python 3.12 环境复现：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.local.lock.txt
```

`.env`、`.venv` 及运行时数据已被 Git 忽略。
