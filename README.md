# Docker 私人文件服务器 v4 完整版

## 功能
- 自定义登录页面、登录/登出、Session 超时
- HTTP 17001 自动跳转 HTTPS 17002
- Nginx 直接高速下载，下载和文件 API 都需要登录
- 文件列表、文件夹、新建文件夹、搜索、删除
- 点击选文件、拖拽、多文件上传、进度/速度/剩余时间
- 并发分片上传、分片大小与并发数可配置
- 断点续传状态查询，已上传分片跳过
- 临时分片位于 `/data/files/.uploads`，避免跨文件系统 `os.replace` 错误

## 部署
```bash
mkdir -p /opt/file-server /data/files
cd /opt/file-server
cp .env.example .env
# 编辑 .env，设置强密码和随机 SECRET_KEY
cd certs
sh generate-cert.sh
cd ..
docker compose up -d --build
docker compose ps
```

浏览器访问 `http://服务器IP:17001`，会跳转到 `https://服务器IP:17002`。自签名证书会有浏览器警告。

## 配置
在 `.env` 中设置：
```dotenv
FILE_USER=admin
FILE_PASSWORD=请替换为强密码
SECRET_KEY=请替换为足够长的随机字符串
MAX_UPLOAD_SIZE=50GB
UPLOAD_CHUNK_SIZE=16MB
UPLOAD_CONCURRENCY=4
SESSION_TIMEOUT_HOURS=12
```

分片支持 B/KB/MB/GB/TB 单位；并发限制在 1-32。修改后执行 `docker compose up -d --build`。

## 说明
- 上传临时分片存储于 `/data/files/.uploads`，与最终文件处于同一挂载点。
- 当前断点续传会根据服务器已有分片跳过已上传分片；浏览器刷新/关闭后的任务 ID 自动恢复尚未持久化。
- 请勿将真实密码、生产环境私钥或证书提交到 Git。
