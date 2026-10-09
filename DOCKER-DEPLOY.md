# Docker image deployment

This repository publishes the application image to GHCR on every push to `main`.
Tags use China Standard Time (UTC+8): `YYYYMMDD-HHMMSS`, plus `latest`.

## Run the application container

The image built from `app/Dockerfile` is the Flask/Gunicorn application service on port 5000. Keep uploaded files persistent by mounting `/data/files` from the host.

First create a host directory and choose your own strong password and secret key:

```bash
sudo mkdir -p /data/files
docker pull ghcr.io/cby-chen/file-server-docker:latest

docker run -d \
  --name file-server \
  --restart unless-stopped \
  -p 5000:5000 \
  -v /data/files:/data/files \
  -e FILE_USER='admin' \
  -e FILE_PASSWORD='替换为你自己的强密码' \
  -e SECRET_KEY='替换为一段足够长的随机字符串' \
  -e MAX_UPLOAD_SIZE='50GB' \
  -e UPLOAD_CHUNK_SIZE='16MB' \
  -e UPLOAD_CONCURRENCY='4' \
  -e SESSION_TIMEOUT_HOURS='12' \
  ghcr.io/cby-chen/file-server-docker:latest
```

Check container health:

```bash
curl -fsS http://127.0.0.1:5000/health
docker logs --tail=100 file-server
```

The health endpoint should return `ok`. Do not expose port 5000 directly to the public Internet without a TLS reverse proxy and appropriate firewall rules.

## Important: complete web UI

The image above contains the application service only. The repository's full browser-based interface and HTTPS setup also use the existing `nginx`, `html`, and `certs` assets described in `docker-compose.yml`. To run the complete existing stack, use Docker Compose and keep the Nginx service; running this app image alone does not replace Nginx/static-file serving.

## Optional: publish to Alibaba Cloud ACR

In GitHub repository **Settings → Secrets and variables → Actions**, add these repository variables:

- `ACR_REGISTRY`: the exact registry domain shown in your ACR console, e.g. an instance domain such as `<instance-name>-registry.cn-hangzhou.cr.aliyuncs.com`
- `ACR_IMAGE`: full image name including namespace/repository, without a tag, and starting with `ACR_REGISTRY/`

Add these repository secrets:

- `ACR_USERNAME`: the ACR registry login username
- `ACR_PASSWORD`: the dedicated ACR registry password (not necessarily your Alibaba Cloud console password)

Once all four values are set, subsequent workflow runs also publish timestamp and `latest` tags to ACR. ACR is skipped when none of these settings is present. Use the exact registry domain and repository namespace from your ACR console; do not copy the example domain literally.
