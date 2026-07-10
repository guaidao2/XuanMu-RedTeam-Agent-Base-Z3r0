---
title: Quick Start
editLink: true
---

# Quick Start

Z3r0's core philosophy is to pursue extreme simplicity as much as possible, so Z3r0's deployment also keeps the steps as simple as possible.

> :warning: Iteration Notice
>
> Z3r0 is currently in a phase of rapid iteration and may undergo major structural or contract changes. To ensure code quality, forward compatibility is not considered for now. When using it in production, proper version control is recommended, and historical data may require additional migration measures.

## Before You Start

### Basic Configuration

Z3r0 requires only the following core content and infrastructure to run:

| Item | Description |
| --- | --- |
| `.xuanmu/config.json` | System runtime configuration |
| `.xuanmu/agents/*` | Agent configuration information |
| `Sandbox` | Customized sandbox environment |
| `Docker` | Sandbox environment runtime |
| `PostgreSQL` | Persistent data storage |

Get the latest code from GitHub:

```bash
git clone https://github.com/yv1ing/Z3r0.git && cd Z3r0
```

### Build the Sandbox

Z3r0's capabilities are deeply tied to the sandbox environment, so you need to build the corresponding sandbox image:

> :warning: Architecture Limitation
>
> The sandbox image build currently supports only the x64/amd64 architecture. arm64/Apple Silicon, including Apple Silicon Macs, is not supported. Run this step on an x64 host or in an x64 build environment.

```bash
cd sandbox && bash build.sh
```

After a short wait, you will get `sandbox-runtime:latest`. On first use, you also need to add the corresponding image record to the system.

## Production Environment

When deploying to production, follow these steps one by one.

### Prepare Configuration

```bash
cp .xuanmu/config.json.example .xuanmu/config.json
```

Edit the system runtime configuration in `.xuanmu/config.json`, mainly updating the following items:

| Item | Description |
| --- | --- |
| `system.encrypt_key` | System data encryption key. This must be changed. A random string of at least 32 bytes is recommended. |
| `system.bootstrap_admin` | Default system administrator information. This must be changed. A strong password is recommended. |
| `database` | System database connection information. When deploying with Docker Compose, set `host` to the corresponding service name. |
| `agents.*` | LLM API configuration for each agent. Different providers and models can be configured separately as needed. |

### Start Containers

Once everything is ready, start Z3r0 with one command:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### Reverse Proxy (Optional)

By default, the service listens on `0.0.0.0:8000`. You can configure it to listen on `127.0.0.1:8000` as needed and set up a reverse proxy.

An example Nginx configuration is shown below:

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

## Development Environment

When deploying in a development environment, follow these steps one by one.

### Configure the Environment

- Python version: 3.13.5
- Node.js version: 24.16.0

Create a virtual environment with the following commands:

```bash
python -m venv .venv

# Windows:
.venv\Scripts\Activate.ps1

# Linux:
source .venv/bin/activate
```

Install system dependencies:

```bash
pip install -r requirements.txt
```

```bash
cd web && npm install
```

Build the frontend project:

```bash
cd web && npm run build
```

Create the database:

Use `docker-compose.dev.yml` to start the database environment with one command:

```bash
docker compose -f docker-compose.dev.yml up -d
```

Visit `127.0.0.1:5433`, log in with the configured pgAdmin username and password, enter the PostgreSQL connection information, and connect to the service.

Create the `z3r0` database. The database name must match the value configured in `config.json`.

### Start the Project

Create `.xuanmu/config.json` and fill in the relevant information based on the example in `.xuanmu/config.json.example`.

Start the project with the following command:

```bash
python main.py
```

By default, the service listens on `0.0.0.0:8000`. Visit `http://127.0.0.1:8000/` to access it.

## Next Step

Follow the instructions in [First Use](./first-use) to officially start working with Z3r0.
