# 部署

## 方式一：Docker（推荐，服务器上三条命令）

```bash
git clone git@github.com:lumin-rise/invoice-system.git && cd invoice-system
docker compose up -d --build
```

打开 `http://服务器IP:8000` 即可。管理员账号在首次启动时自动生成，
查看初始密码：

```bash
cat data/初始密码.txt
```

登录后请立即在右上角修改密码。

- 发票等运行数据保存在宿主机 `./data/`（compose 卷），升级/重建容器不丢
- 保留期调整：编辑 docker-compose.yml 里的 `RETENTION_DAYS` 后 `docker compose up -d` 生效
- 自动清理在每天凌晨 03:00（容器时区 Asia/Shanghai）

## 方式二：无 Docker 的 Linux（systemd）

```bash
sudo apt install -y python3-pip nodejs npm git
git clone git@github.com:lumin-rise/invoice-system.git && cd invoice-system
python3 -m pip install -r requirements.txt
(cd frontend && npm install && npm run build)
sudo tee /etc/systemd/system/invoice-system.service <<'EOF'
[Unit]
Description=Invoice System
After=network.target

[Service]
WorkingDirectory=/opt/invoice-system/backend
ExecStart=/usr/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
Environment=TZ=Asia/Shanghai

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload && sudo systemctl enable --now invoice-system
```

> 注意：用 nginx 反代时需保留较大 `client_max_body_size`（发票单文件上限 30MB）。

## 反向代理（可选）

```nginx
server {
    listen 80;
    server_name your.domain.com;
    client_max_body_size 30m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

安全建议：公网部署时务必改掉初始密码；有域名的话加 HTTPS（如 certbot），
Cookie 会自动受益于 SameSite=Strict。
