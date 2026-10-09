# 文件服务器 Docker 部署指南（中文版）

本文介绍如何使用 Docker Compose 部署完整的文件上传/下载服务。完整部署包含 **两个镜像**：

1. **应用镜像（app）**：运行 Python / Gunicorn 后端，处理登录、上传、分片上传及文件下载等 API。
2. **网页入口镜像（nginx）**：提供网页静态文件、HTTPS 入口，并将 API 请求转发给应用容器。

CI 会将这两个镜像分别发布到阿里云 ACR 和 GitHub Container Registry（GHCR）。每个镜像包含三个标签：latest、Git 提交短 SHA、北京时间构建时间戳（YYYYMMDD-HHMMSS）。这些是同一镜像的不同标签，不是额外的独立镜像。

## 一、镜像地址

### 阿里云 ACR（默认）

| 用途 | 镜像地址 |
| --- | --- |
| 应用后端 | registry.cn-hangzhou.aliyuncs.com/chenby/file-server-docker:latest |
| Nginx 网页入口 | registry.cn-hangzhou.aliyuncs.com/chenby/file-server-docker-nginx:latest |

### GitHub Container Registry（可选）

| 用途 | 镜像地址 |
| --- | --- |
| 应用后端 | ghcr.io/cby-chen/file-server-docker:latest |
| Nginx 网页入口 | ghcr.io/cby-chen/file-server-docker-nginx:latest |

如果 GHCR 镜像是私有的，请先执行 docker login ghcr.io，并使用有权限读取该 Package 的 GitHub 令牌登录。

## 二、服务器准备

服务器需要安装 Docker Engine 和 Docker Compose v2（可使用 docker compose 命令）。以下命令以 Linux 服务器为例。

克隆仓库并进入目录：

~~~bash
git clone https://github.com/cby-chen/file-server-docker.git
cd file-server-docker
~~~

创建文件持久化目录：

~~~bash
sudo mkdir -p /data/files
sudo chown -R "$USER":"$USER" /data/files
~~~

上传文件会保存在宿主机的 /data/files 中。容器重建或升级时，只要不删除这个目录，文件就会保留。

## 三、配置环境变量

复制示例配置：

~~~bash
cp .env.example .env
~~~

编辑 .env，至少修改登录密码和密钥：

~~~dotenv
FILE_USER=admin
FILE_PASSWORD=请替换为高强度且独立的密码
SECRET_KEY=请替换为足够长的随机字符串
MAX_UPLOAD_SIZE=50GB
UPLOAD_CHUNK_SIZE=16MB
UPLOAD_CONCURRENCY=4
SESSION_TIMEOUT_HOURS=12

# 默认使用阿里云 ACR；如需使用 GHCR，请改为下面两行
APP_IMAGE=registry.cn-hangzhou.aliyuncs.com/chenby/file-server-docker:latest
NGINX_IMAGE=registry.cn-hangzhou.aliyuncs.com/chenby/file-server-docker-nginx:latest
~~~

生成强随机密钥的示例：

~~~bash
openssl rand -hex 32
~~~

把生成的字符串填入 SECRET_KEY。请妥善保存 .env，不要提交到 Git 仓库，也不要把密码或密钥发给他人。

如需改用 GHCR，将 .env 中的镜像地址改为：

~~~dotenv
APP_IMAGE=ghcr.io/cby-chen/file-server-docker:latest
NGINX_IMAGE=ghcr.io/cby-chen/file-server-docker-nginx:latest
~~~

Docker Compose 会从项目目录中的 .env 文件读取用于镜像地址和环境变量替换的配置。更多说明可参考 [Docker 官方环境变量文档](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)。

## 四、配置 HTTPS 证书

Nginx 配置要求以下两个文件存在于服务器的 certs/ 目录：

- certs/server.crt
- certs/server.key

仓库提供了生成自签名证书的脚本。在仓库根目录运行：

~~~bash
cd certs
sh generate-cert.sh
cd ..
~~~

此脚本生成的自签名证书仅适合测试或内网临时使用，浏览器会显示证书安全警告。正式对公网提供服务时，请将其替换为域名对应的可信 TLS 证书，并确保文件名仍为 server.crt 和 server.key。

## 五、启动完整服务

在仓库根目录执行：

~~~bash
docker compose pull
docker compose up -d
~~~

查看容器状态：

~~~bash
docker compose ps
docker compose logs --tail=100 app
docker compose logs --tail=100 nginx
~~~

检查后端健康状态：

~~~bash
docker compose exec app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:5000/health').read().decode())"
~~~

正常情况下，健康检查返回 ok。

## 六、访问网站和防火墙

当前 docker-compose.yml 默认映射端口：

- HTTP：宿主机 17001，访问后会重定向到 HTTPS 的 17002 端口。
- HTTPS：宿主机 17002。

因此访问地址为：

- http://服务器IP:17001
- https://服务器IP:17002

请在服务器防火墙和云厂商安全组中按需放行 TCP 17001、17002。生产环境建议使用域名和可信证书；如果希望使用标准的 80/443 端口，需要相应调整 Compose 端口映射及 Nginx 的重定向配置。

不要将应用容器的 5000 端口直接暴露到公网。当前 Compose 仅在内部网络中向 Nginx 暴露该端口。

## 七、升级镜像

发布新版本后，在服务器仓库目录执行：

~~~bash
docker compose pull
docker compose up -d
docker image prune -f
~~~

docker compose pull 会拉取 .env 指定的两个镜像，docker compose up -d 会按新镜像重建容器。升级前建议备份 /data/files 和 .env。

如果希望固定到某次构建，而不是始终使用 latest，可以把 .env 中的两个镜像标签改成同一次构建对应的短 SHA 标签或北京时间标签，然后执行上述升级命令。

## 八、GitHub Actions 自动构建与发布

每次向 main 分支推送代码，或手动触发工作流，GitHub Actions 会执行代码检查、构建两个镜像、运行应用健康检查、检查 Nginx 配置，然后发布到配置的镜像仓库。

工作流文件：.github/workflows/docker-ci.yml

### ACR 配置

在 GitHub 仓库的 **Settings → Secrets and variables → Actions** 中配置以下 Repository variables：

- ACR_REGISTRY：例如 registry.cn-hangzhou.aliyuncs.com，必须与 ACR 控制台显示的实际仓库域名一致。
- ACR_IMAGE：应用镜像的完整仓库路径，不包含标签，例如 registry.cn-hangzhou.aliyuncs.com/chenby/cby。

配置以下 Repository secrets：

- ACR_USERNAME：ACR 镜像仓库登录用户名。
- ACR_PASSWORD：ACR 镜像仓库访问密码或专用凭证，不一定等于阿里云控制台登录密码。

工作流会将应用镜像推送到 ACR_IMAGE，将 Nginx 镜像推送到 ACR_IMAGE 后追加 -nginx 的仓库名。例如应用仓库为 registry.cn-hangzhou.aliyuncs.com/chenby/cby 时，Nginx 仓库为 registry.cn-hangzhou.aliyuncs.com/chenby/cby-nginx。

GHCR 使用工作流的 GITHUB_TOKEN 推送，无需额外配置个人令牌；工作流已声明 packages: write 权限。

查看构建状态：[GitHub Actions](https://github.com/cby-chen/file-server-docker/actions)

## 九、常见问题

### 1. 提示缺少 FILE_PASSWORD 或 SECRET_KEY

检查仓库根目录下是否存在 .env，并确认这两个变量已设置为非空值。修改后重新执行：

~~~bash
docker compose up -d
~~~

### 2. 拉取镜像时提示 denied 或 unauthorized

检查镜像仓库地址、标签和访问权限。私有 GHCR Package 需要先登录；ACR 私有仓库也需要使用有拉取权限的凭据登录。

### 3. 网站无法访问或 HTTPS 报错

检查容器状态和日志，确认 certs/server.crt、certs/server.key 存在，并检查服务器防火墙和云安全组是否放行 17001/17002 端口。自签名证书出现浏览器警告属于预期现象。

### 4. 网页能打开，但上传或 API 报错

检查两个容器是否都在运行，并查看 docker compose logs --tail=100 app nginx。不要把应用容器的 5000 端口暴露到公网。

### 5. 上传文件在重建容器后不见了

确认宿主机的 /data/files 挂载正确，并且没有删除宿主机文件目录。重要数据应另行备份。

## 十、常用维护命令

~~~bash
# 查看容器
docker compose ps

# 查看实时日志
docker compose logs -f

# 重启服务
docker compose restart

# 停止并移除容器（不会删除绑定挂载中的 /data/files）
docker compose down

# 查看 Compose 最终解析出的配置（注意输出可能包含敏感环境变量）
docker compose config
~~~

注意：docker compose down 不会删除宿主机的 /data/files；请勿手动删除该目录，除非确定不再需要其中的数据。
