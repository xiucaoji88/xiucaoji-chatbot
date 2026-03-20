# 修草纪智能客服系统

基于 Flask + OpenAI GPT 的微信公众号智能客服系统。

## 功能特性

- ✅ 微信公众号消息自动回复
- ✅ 对接 OpenAI GPT AI 对话
- ✅ 支持文字咨询和图片诊断
- ✅ 新用户关注自动欢迎语
- ✅ 健康检查端点

## 技术栈

- Python 3.11
- Flask 3.0
- Gunicorn
- OpenAI GPT API

## 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 运行开发服务器
python app.py
```

## 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `WECHAT_APPID` | 微信公众号 AppID | - |
| `WECHAT_APPSECRET` | 微信公众号 AppSecret | - |
| `WECHAT_TOKEN` | 服务器验证 Token | xiucaoji88 |
| `OPENAI_API_KEY` | OpenAI API Key | - |
| `OPENAI_BASE_URL` | OpenAI API 地址 | https://api.openai.com/v1 |
| `OPENAI_MODEL` | OpenAI 模型 | gpt-3.5-turbo |
| `PORT` | 服务端口 | 5000 |

## API 端点

- `GET /` - 首页/健康检查
- `GET /health` - 健康检查
- `GET/POST /wechat` - 微信公众号消息接口
- `POST /api/chat` - 直接对话 API

## 部署

### Railway 部署

1. Fork 本仓库到 GitHub
2. 在 Railway 中创建新项目，选择 GitHub 仓库
3. 配置环境变量
4. 自动部署完成

### 微信公众号配置

1. 登录公众号后台 → 开发 → 基本配置
2. 设置服务器 URL: `https://你的域名/wechat`
3. Token: 与 `WECHAT_TOKEN` 环境变量一致
4. 消息加密方式：明文模式

## 项目结构

```
.
├── app.py              # 主应用
├── requirements.txt    # Python 依赖
├── Procfile           # Railway 启动配置
├── runtime.txt        # Python 版本
└── README.md          # 项目说明
```

## 许可证

MIT License
