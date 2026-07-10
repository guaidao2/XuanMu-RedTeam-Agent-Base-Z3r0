---
title: First Use
editLink: true
---

# First Use

This guide first introduces the overall capabilities of Z3r0, then walks through a complete CTF task from initial setup to automated solving. The walkthrough explains the main system modules and their intended usage.

## System Overview

Access the configured listening address and port to enter the landing page:

![landing-1](/images/landing-1.png)

Click `Open workbench` to open the login page:

![login-1](/images/login-1.png)

Enter the configured administrator account and password. After successful authentication, the management console is displayed.

The system contains the following core modules:

1. Playground: the primary workspace for direct interaction and collaboration with the agent team.
2. Work Projects: manages work projects, including creation, editing, and review.
3. Host Management: manages host nodes and orchestrates the runtime environment for sandbox containers.
4. Egress Proxies: manages unified network egress through HTTP, HTTPS, and SOCKS5 proxies.
5. Sandbox Images: manages customized sandbox images for different task requirements.
6. Sandbox Containers: orchestrates and configures runnable sandbox containers.
7. System Users: manages system users, roles, and related identity information.
8. System Config: manages runtime configuration and supports hot updates.

## Start Working

The following sections start from a clean system state, configure the runtime environment step by step, and complete a CTF challenge.

### Connect a Host

When the system starts, it adds the local machine to the host management list by default, so Z3r0 can run without a remote host. In most scenarios, however, it is strongly recommended to configure a remote host and run sandbox containers remotely for security isolation and source-tracing resistance.

Follow the steps below to configure and connect a remote host.

**1. Install Docker and configure the Remote API with mutual TLS authentication**

```bash
curl -fsSL https://get.docker.com | bash -s docker
wget https://raw.githubusercontent.com/yv1ing/Z3r0/refs/heads/main/sandbox/init_host.sh && chmod +x init_host.sh
```

Run `bash ./init_host.sh`, enter the host IP address, and wait for certificate generation and automatic configuration to complete. The Docker client certificates are written to the current directory:

![init-host-1](/images/init-host-1.png)

On some distributions, you may need to manually edit the Docker service to avoid daemon configuration conflicts:

```bash
systemctl edit docker.service
```

Add the following content to the blank editor area:

```text
[Service]
ExecStart=
ExecStart=/usr/bin/dockerd
```

![init-host-2](/images/init-host-2.png)

Restart the Docker service:

```bash
systemctl restart docker
```

**2. Create a host record and fill in the connection information**

In the `Host Management` module, click `Create Host` to open the edit form. Fill in the remote host IP address, port, account, password, and Docker certificate information, then save the record.

> Note: In public network environments, use TLS mode. In LAN environments, Plain mode can be used without certificate authentication.

![create-host-1](/images/create-host-1.png)

**3. Connect to the host and build the sandbox image**

Z3r0 provides a web terminal that can connect directly to the remote host over SSH. Follow the instructions in [Quick Start](./quick-start#build-the-sandbox) to build the sandbox image.

![create-host-2](/images/create-host-2.png)

### Create an Image

In the `Sandbox Images` module, create an image record. The image name must match the name of the image that was actually built:

![create-image-1](/images/create-image-1.png)

### Create a Container

In the `Sandbox Containers` module, create a container and select the corresponding remote host and sandbox image. During container creation, you can specify the container egress mode. Z3r0 supports direct connection, HTTP, HTTPS, SOCKS5, and Tor. HTTP, HTTPS, and SOCKS5 require proxy entries to be configured in advance in the `Egress Proxies` module.

![create-container-1](/images/create-container-1.png)

### Test the Container

After the sandbox container is created, use the action buttons on the right side of the list item to operate it. Start the container, then access the sandbox through the web terminal, file manager, and noVNC display.

![create-container-2](/images/create-container-2.png)

### Create a Project

Using a CTF challenge as the target, create a work project in the `Work Projects` module. Fill in the project name, project type, description, responsible users, and other basic information. Then bind the sandbox container and enter the known asset information:

![create-project-1](/images/create-project-1.png)

### Execute the Task

After the work project is created, the corresponding option appears in the `Playground` list. Open it, create a new session, and start collaborating with the agent team. Use natural language to instruct the agent team to solve the CTF challenge, obtain the flag, and finally deliver the write-up:

![project-example-1](/images/project-example-1.png)

During execution, open the `Project records` window to inspect real-time progress and related information. Assets, findings, relationships, and graphs together preserve the task execution process as long-term evidence:

![project-example-2](/images/project-example-2.png)

![project-example-3](/images/project-example-3.png)
