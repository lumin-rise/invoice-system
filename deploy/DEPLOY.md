# 发票系统 · 子域名部署指南

目标：`invoice.你的域名.com` 访问发票系统，主域名留给另一个项目。
前端与 API 同源（FastAPI 托管 `frontend/dist`），**代码不需要任何修改**。

> 下文所有 `invoice.example.com` 替换成你的真实子域名，`服务器IP` 替换成服务器公网 IP。

## 0. 前提

- 一台有公网 IP 的服务器（Linux，推荐 Ubuntu/Debian；国内服务器需主域名已备案）
- 域名解析控制台的登录权限（阿里云 / 腾讯云 / Cloudflare 等）

## 1. 加 DNS 解析（免费，约 1 分钟）

在域名解析控制台点「添加记录」：

| 主机记录 | 记录类型 | 记录值 | TTL |
|---------|---------|--------|-----|
| invoice | A | 服务器IP | 默认 |

保存后验证（本机执行，返回你服务器 IP 即生效）：

```bat
nslookup invoice.example.com
```

## 2. 服务器上部署代码

```bash
# 上传代码（本机 Git Bash 执行，或用你习惯的方式）
rsync -av --exclude node_modules --exclude .venv /f/code/invoice-system/ user@服务器IP:/opt/invoice-system/

# 服务器上装依赖（建议 venv）
cd /opt/invoice-system
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

前端 `frontend/dist` 已在代码里，无需在服务器上重新构建。想改前端时在本机
`npm run build` 后同步 dist 即可。

先手动验证能跑：

```bash
cd /opt/invoice-system/backend
../venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000        # 返回页面 HTML 即 OK，Ctrl+C 退出
```

## 3. 常驻运行（systemd）

```bash
sudo cp /opt/invoice-system/deploy/invoice-system.service /etc/systemd/system/
# 若部署路径或用户不同，先改 service 文件里的 WorkingDirectory / User / ExecStart
sudo systemctl daemon-reload
sudo systemctl enable --now invoice-system
sudo systemctl status invoice-system      # 确认 active (running)
```

## 4. Nginx 反向代理

```bash
sudo apt install nginx
sudo cp /opt/invoice-system/deploy/nginx-invoice.conf /etc/nginx/conf.d/invoice.conf
sudo nano /etc/nginx/conf.d/invoice.conf   # 改 server_name 为真实子域名
sudo nginx -t && sudo nginx -s reload
```

此时浏览器打开 `http://invoice.example.com` 应该已经能看到系统。

## 5. HTTPS（Let's Encrypt，免费）

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d invoice.example.com
```

certbot 会自动改写 nginx 配置并配置 80→443 跳转、自动续期。

## 6. 安全加固（强烈建议，公网必做）

发票是财务数据，本系统**没有登录功能**，裸奔上线任何人都可访问。
两种方案（nginx-invoice.conf 里已写好模板，取消注释即可）：

- **基础认证**（推荐，最快）：`sudo htpasswd -c /etc/nginx/.htpasswd 用户名`，
  然后启用配置里的 `auth_basic` 两行。访问时输一次账号密码。
- **IP 白名单**：只允许你办公/家里的 IP 访问，启用 `allow/deny` 两行。

改完 `sudo nginx -t && sudo nginx -s reload`。

## 7. 国内服务器备注

- 主域名已 ICP 备案的，**子域名不需要单独备案**，直接解析即可使用。
- 若还没备案，国内服务器 80/443 会被阻断；可临时用非标端口
  （如 `invoice.example.com:8443`）或选香港/海外服务器。

## 日常运维

```bash
sudo systemctl restart invoice-system   # 改代码后重启
journalctl -u invoice-system -f         # 看运行日志
sudo systemctl status invoice-system    # 看运行状态
```

会话与上传数据在 `backend/data/`，记得纳入备份。
