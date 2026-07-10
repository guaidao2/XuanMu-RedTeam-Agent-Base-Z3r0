---
title: 首次使用
editLink: true
---

# 首次使用

本文档将首先介绍 Z3r0 的整体功能，然后通过一次从 0 到 1 自动化完成 CTF 解题任务的逐步讲解，介绍系统的各个模块和使用方式。

## 系统概览

根据配置的监听地址和端口，访问跳转至落地页：

![landing-1](/images/landing-1.png)

点击 `Open workbench` 按钮跳转至登录页：

![login-1](/images/login-1.png)

输入配置的管理员账号、密码，登录成功后即进入管理后台页。

系统包含以下核心模块：

1. Playground：核心工作区域模块，和智能体团队直接交互、协作的区域。
2. Work Projects：工作项目管理模块，用于创建、编辑、审查工作项目。
3. Host Management：主机节点管理模块，统一管理远程主机，编排沙盒容器的实际运行环境。
4. Egress Proxies：统一出口管理模块，配置 HTTP/HTTPS/SOCKS5 代理，用于沙盒容器的网络出口。
5. Sandbox Images：沙盒镜像管理模块，统一管理针对不同需求定制的沙盒镜像。
6. Sandbox Containers：沙盒容器管理模块，编排配置实际运行的沙盒容器。
7. System Users：系统用户管理模块，可配置用户信息、角色等。
8. System Config：系统运行配置模块，支持热更新。

## 开始工作

以下内容将从系统初始状态开始，逐步配置运行环境，最终完成一道 CTF 赛题。

### 连接主机

系统在启动时，默认添加本机到主机管理列表中，不需配置远程主机也可正常运行。但大多数场景下，出于安全防护、防止溯源的考虑，强烈建议配置远程主机，将沙盒容器运行在远端。

按照以下说明，配置并连接远程主机。

**1. 安装 Docker 并配置 Remote API 和双向证书认证**

```bash
curl -fsSL https://get.docker.com | bash -s docker
wget https://raw.githubusercontent.com/yv1ing/Z3r0/refs/heads/main/sandbox/init_host.sh && chmod +x init_host.sh
```

使用 `bash ./init_host.sh` 执行脚本，输入主机 IP 地址，等待证书生成和自动配置，Docker 客户端证书将会被输出到当前目录下：

![init-host-1](/images/init-host-1.png)

部分发行版下，可能需要手动修改 Docker service，避免 daemon 配置冲突：

```bash
systemctl edit docker.service
```

空白处写入以下内容：

```text
[Service]
ExecStart=
ExecStart=/usr/bin/dockerd
```

![init-host-2](/images/init-host-2.png)

重启 Docker service：

```bash
systemctl restart docker
```

**2. 创建主机记录并填写连接信息**

在系统的 `Host Management` 模块，点击 `Create Host` 打开编辑表单，将远程主机的 IP 地址、端口、账号、密码以及 Docker 的证书信息填入，完成后保存即可。

> 注意：公网环境注意选择 TLS 模式，局域网可选择 Plain 模式，无需证书认证。

![create-host-1](/images/create-host-1.png)

**3. 连接主机并构建沙盒镜像**

系统提供了在线终端，可以直接通过 SSH 连接到远程主机。按照 [快速开始](./quick-start#构建沙盒) 中的说明，构建沙盒镜像。

![create-host-2](/images/create-host-2.png)

### 创建镜像

在 `Sandbox Images` 模块中，新建一条镜像记录，要求名称与实际构建的镜像名称保持一致：

![create-image-1](/images/create-image-1.png)

### 创建容器

在 `Sandbox Containers` 模块中，新建一个容器，选择对应的远程主机和沙盒镜像。创建容器时，可以指定容器的出口网络连接方式，支持直连、HTTP、HTTPS、SOCKS5 和 Tor 几种模式，其中 HTTP、HTTPS 和 SOCKS5 需要预先在 Egress Proxies 模块中配置添加。

![create-container-1](/images/create-container-1.png)

### 测试容器

沙盒容器创建完成后，可以通过列表项右侧的操作按钮进行对应的操作。启动容器后，通过网页终端、文件管理器和 noVNC 画面接入到沙盒容器。

![create-container-2](/images/create-container-2.png)

### 创建项目

以一道 CTF 赛题为目标，在 `Work Projects` 模块中新建一个工作项目，填写项目名称、项目类型、项目描述、负责人员等基础信息，设置绑定的沙盒容器和已知的资产信息：

![create-project-1](/images/create-project-1.png)

### 任务实施

工作项目创建完成后，`Playground` 列表中就会出现对应的选项，点击进入创建一个新会话，即可正式进入与智能体团队的协作流程。通过自然语言与智能体团队交互，要求攻破 CTF 题目获取 flag，最终交付 write-up：

![project-example-1](/images/project-example-1.png)

任务执行过程中，可以通过 `Project records` 窗口查看实时进度和相关信息，这里通过资产、发现、关系和图谱共同将任务执行过程沉淀为长期的证据留存：

![project-example-2](/images/project-example-2.png)

![project-example-3](/images/project-example-3.png)
