# Emby + Telegram 用户管理容器项目

这是一个面向 **Debian / Docker** 的轻量项目，用于：

- 对接 Emby Server API，管理 Emby 用户
- 提供 **管理员 1 号 Telegram Bot**
- 提供 **客户端 2 号 Telegram Bot**
- 使用 **SQLite + WAL** 保存本地用户信息、注册码、到期时间
- 不提供对外 Web 面板，默认只使用两个 Telegram 机器人
- 所有 Emby 操作都走 **HTTP API**，不直接碰 Emby 数据库，避免锁库

## 重要说明

### 1) 不能从 Emby 反向读出明文密码
Emby API 可创建用户、删除用户、改密码、查询用户和会话，但不会返回用户明文密码。  
因此“从 Emby 导入到本地”只能导入 **用户名 / 状态 / 最近活动**，密码会在本地标记为未知。  
如果你需要把本地密码同步回 Emby，本项目支持。

### 2) 模板用户
新注册账号的权限和模板用户 `EMBY_TEMPLATE_USER=testone` 一样。  
项目会在创建新用户后，复制模板用户的 **Policy + Configuration**。

### 3) Telegram 菜单
Telegram 原生 Bot 菜单样式受 Telegram 客户端限制，不能完全自定义成 App Store UI。  
本项目只保留 Telegram Bot 菜单，不再开放对外 Web 面板。

---

## 目录结构

```text
.
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── app
    ├── main.py
    ├── config.py
    ├── db.py
    ├── models.py
    ├── security.py
    ├── logging_setup.py
    ├── emby.py
    ├── services
    ├── bots
    └── web  # 目录保留，但默认不对外启用
```

## 隐私与去敏说明

仓库中的 `.env.example` 已经替换为占位符示例，不包含任何真实的：

- Emby 服务器地址
- Emby API Key
- Telegram Bot Token
- 管理员 Telegram ID / 用户名
- 其他私密配置

真实部署时请复制示例文件并自行填写：

```bash
cp .env.example .env
```

## 一键启动

```bash
mkdir -p /opt/emby_tg_admin
cd /opt/emby_tg_admin

# 把本项目文件放到这个目录后执行：
cp .env.example .env
nano .env

docker compose up -d --build
docker compose logs -f --tail=200
```

## 首次检查

- 查看容器日志里是否出现：
  - `Emby API Key 校验成功`
  - `管理员机器人 Token 校验成功`
  - `客户端机器人 Token 校验成功`

## 管理员 Bot 功能

- 生成注册码
- 查询注册码库存
- 清空注册码库存
- 同步 Emby 到本地（本地多余账号会删除，本地默认密码统一写成 1234）
- 同步本地用户到 Emby
- 查询有效账号
- 删除用户
- 修改用户到期时间
- 查询登录设备/IP
- 查询在线播放人数
- 到期账号自动删除并通知管理员

## 客户端 Bot 功能

- 注册账号
- 查询我的账号
- 查询我的到期时间
- 查询在线播放人数
- 一键联系管理员

## 资源建议

2C2G40G 完全足够跑这个项目，建议同机部署，不要和大量转码业务混跑.
![对您有帮助吗，打赏一下](https://github.com/sd87671067/picx-images-hosting/raw/master/IMG_8831.362632xhlz.jpeg)
