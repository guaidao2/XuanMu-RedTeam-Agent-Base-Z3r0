---
title: 快速开始
editLink: true
---

# 快速开始

Z3r0 的核心理念是：尽力做到极致的简洁，因此 Z3r0 的部署也将尽力简化步骤。

> :warning: 迭代说明
> 
> 目前，Z3r0 正处于快速迭代阶段，可能出现大幅度的结构、契约变动。为了保证代码质量，暂不考虑向前兼容。在生产环境使用时，建议做好合理的版本控制，历史数据可能需要额外的迁移措施。

## 开始之前

### 基础配置

Z3r0 的运行只需要以下核心内容和基础设施：

| 项目 | 说明 |
| --- | --- |
| `.xuanmu/config.json` | 系统的运行时配置 |
| `.xuanmu/agents/*` | 智能体的配置信息 |
| `Sandbox` | 定制的沙盒环境 |
| `Docker` | 沙盒环境运行时 |
| `PostgreSQL` | 数据持久化存储 |

通过 GitHub 获取最新代码：

```bash
git clone https://github.com/yv1ing/Z3r0.git && cd Z3r0
```

### 构建沙盒

Z3r0 的能力与沙盒环境深度绑定，因此需要构建对应的沙盒镜像：

> :warning: 架构限制
>
> Sandbox 镜像构建目前仅支持 x64/amd64 架构，不支持 arm64/Apple Silicon（包括 Apple Silicon Mac）。请在 x64 主机或 x64 构建环境中执行该步骤。

```bash
cd sandbox && bash build.sh
```

稍等片刻即可得到 `sandbox-runtime:latest`，在首次使用时，还需要在系统中添加对应的镜像记录。

## 生产环境

生产环境部署时，请按照以下步骤逐项进行。

### 准备配置

```bash
cp .xuanmu/config.json.example .xuanmu/config.json
```

编辑 `.xuanmu/config.json` 中的系统运行时配置，主要修改以下内容：

| 项目 | 说明 |
| --- | --- |
| `system.encrypt_key` | 系统数据加密密钥，必须修改，建议使用至少 32 字节的随机字符串。 |
| `system.bootstrap_admin` | 系统默认管理员信息，必须修改，建议使用强密码。 |
| `database` | 系统数据库连接信息，使用 Docker Compose 部署时，`host` 填写对应的服务名称。 |
| `agents.*` | 各智能体的 LLM API 配置，可根据需要分别配置不同的供应商和模型。 |

### 启动容器

一切准备就绪后，使用以下命令一键启动 Z3r0：

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### 反向代理（可选）

服务默认监听在 `0.0.0.0:8000` 上，可根据需要设置监听在 `127.0.0.1:8000`，并配置反向代理。

可参考的 Nginx 配置如下：

```text
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 10000 ssl default_server;

    ssl_certificate     /etc/nginx/ssl/vps.crt;
    ssl_certificate_key /etc/nginx/ssl/vps.key;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    auth_basic "Origin Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8000;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;

        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_buffering off;
    }
}
```

## 开发环境

开发环境部署时，请按照以下步骤逐项进行。

### 配置环境

- Python 版本：3.13.5
- Node.js 版本：24.16.0

使用以下命令创建虚拟环境：

```bash
python -m venv .venv

# Windows:
.venv\Scripts\Activate.ps1

# Linux:
source .venv/bin/activate
```

安装系统依赖：

```bash
pip install -r requirements.txt
```

```bash
cd web && npm install
```

构建前端项目：

```bash
cd web && npm run build
```

创建数据库：

使用 `docker-compose.dev.yml` 一键启动数据库环境：

```bash
docker compose -f docker-compose.dev.yml up -d
```

访问 `127.0.0.1:5433`，使用设置的 pgAdmin 账号密码登录，填写 PostgreSQL 连接信息并连接到服务。

创建 `z3r0` 数据库，数据库名称要与 `config.json` 中填写的保持一致。

### 启动项目

创建 `.xuanmu/config.json`，根据 `.xuanmu/config.json.example` 中的示例填写相关信息。

使用以下命令启动项目：

```bash
python main.py
```

服务默认监听在 `0.0.0.0:8000` 上，使用 `http://127.0.0.1:8000/` 即可访问。

## 下一步

根据 [首次使用](./first-use) 中的说明，正式开启 Z3r0 的工作！
