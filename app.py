#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修草纪智能客服系统 - Flask Web 服务
用于 Railway 部署，对接微信公众号
"""

import os
import json
import hashlib
import time
import requests
from flask import Flask, request, make_response
from xml.etree import ElementTree as ET

app = Flask(__name__)

# ==================== 配置信息 ====================
# 微信公众号配置
WECHAT_CONFIG = {
    "appid": os.environ.get("WECHAT_APPID", "wx62ff6236f2c99902"),
    "appsecret": os.environ.get("WECHAT_APPSECRET", ""),
    "token": os.environ.get("WECHAT_TOKEN", "xiucaoji88")  # 用于服务器验证
}

# OpenAI 配置
OPENAI_CONFIG = {
    "api_key": os.environ.get("OPENAI_API_KEY", ""),
    "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "model": os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")
}

# ==================== 微信相关功能 ====================

def verify_signature(token, signature, timestamp, nonce):
    """验证微信服务器签名"""
    tmp_list = [token, timestamp, nonce]
    tmp_list.sort()
    tmp_str = ''.join(tmp_list)
    tmp_str = hashlib.sha1(tmp_str.encode()).hexdigest()
    return tmp_str == signature

def parse_xml(xml_data):
    """解析微信推送的 XML 消息"""
    root = ET.fromstring(xml_data)
    msg = {}
    for child in root:
        msg[child.tag] = child.text
    return msg

def create_xml_response(to_user, from_user, content):
    """创建 XML 回复消息"""
    timestamp = int(time.time())
    xml = f"""<xml>
<ToUserName><![CDATA[{to_user}]]></ToUserName>
<FromUserName><![CDATA[{from_user}]]></FromUserName>
<CreateTime>{timestamp}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{content}]]></Content>
</xml>"""
    return xml

# ==================== OpenAI 对接 ====================

def call_openai(user_message, user_id="default"):
    """调用 OpenAI API 获取回复"""
    url = f"{OPENAI_CONFIG['base_url']}/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {OPENAI_CONFIG['api_key']}",
        "Content-Type": "application/json"
    }
    
    # 系统提示词 - 修草纪品牌设定
    system_prompt = """你是修草纪品牌的专业护肤顾问，名叫"果冻"。

品牌背景：
- 修草纪是以真实皮肤问题为核心、以结果为导向的专业肌肤调理品牌
- 创始人果冻因自身多年长痘经历创立品牌
- 品牌理念：不炒成分只解决问题、一人一方因人调配、植物提取温和不伤肤、以结果为准不搞引导式消费
- 品牌Slogan：不炒成分，只解决问题；护肤不走弯路，效果自有答案；用结果做承诺，30天无效退款

你的职责：
1. 专业分析用户的皮肤问题（痘痘、痘印、敏感、色斑等）
2. 推荐合适的产品搭配方案
3. 解答产品使用方法和注意事项
4. 提供护肤知识和建议

产品体系：
- 祛痘系列：焕颜祛痘霜、苗山斗痘液
- 美白淡斑系列：净肤紧致精华、极光奢宠5件套
- 敏感肌修复系列：臻养多效舒缓霜、修护面膜
- 日常护理：氨基酸洁面、玻尿酸保湿水、润养水光精华

接待原则：
- 先诊断，再给方案
- 一人一方，因人调配
- 温和有效，售后兜底
- 28天代谢周期，30天无理由退款

回复风格：
- 专业但亲切，像朋友一样交流
- 不夸大承诺，实事求是
- 强调测试和循序渐进
- 体现品牌的真诚和专业"""
    
    payload = {
        "model": OPENAI_CONFIG['model'],
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_message
            }
        ],
        "temperature": 0.7,
        "max_tokens": 1000
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        result = response.json()
        
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]
        else:
            print(f"OpenAI API 返回错误: {result}")
            return "抱歉，我暂时无法回答这个问题，请稍后再试。"
    except Exception as e:
        print(f"OpenAI API 调用失败: {e}")
        return "抱歉，服务暂时不可用，请稍后再试。"

# ==================== 路由定义 ====================

@app.route('/')
def index():
    """首页 - 健康检查"""
    return {
        "status": "ok",
        "service": "修草纪智能客服系统",
        "version": "1.0.0"
    }

@app.route('/health')
def health():
    """健康检查端点"""
    return {"status": "healthy"}

@app.route('/wechat', methods=['GET', 'POST'])
def wechat_handler():
    """微信公众号消息处理入口"""
    
    # GET 请求 - 服务器验证
    if request.method == 'GET':
        signature = request.args.get('signature', '')
        timestamp = request.args.get('timestamp', '')
        nonce = request.args.get('nonce', '')
        echostr = request.args.get('echostr', '')
        
        if verify_signature(WECHAT_CONFIG['token'], signature, timestamp, nonce):
            return echostr
        else:
            return '验证失败', 403
    
    # POST 请求 - 接收用户消息
    elif request.method == 'POST':
        try:
            xml_data = request.data
            msg = parse_xml(xml_data)
            
            # 获取消息信息
            msg_type = msg.get('MsgType', '')
            from_user = msg.get('FromUserName', '')
            to_user = msg.get('ToUserName', '')
            
            # 处理文本消息
            if msg_type == 'text':
                user_message = msg.get('Content', '')
                
                # 调用 OpenAI 获取回复
                reply_content = call_openai(user_message, from_user)
                
                # 返回 XML 回复
                response_xml = create_xml_response(from_user, to_user, reply_content)
                response = make_response(response_xml)
                response.content_type = 'application/xml'
                return response
            
            # 处理图片消息（肌肤诊断）
            elif msg_type == 'image':
                reply = "收到您的图片！请稍等，我正在分析您的肌肤状况...\n\n如需肌肤诊断，建议发送清晰的面部照片，我会帮您分析皮肤问题并推荐合适的护理方案。"
                response_xml = create_xml_response(from_user, to_user, reply)
                response = make_response(response_xml)
                response.content_type = 'application/xml'
                return response
            
            # 处理事件（关注/取消关注等）
            elif msg_type == 'event':
                event = msg.get('Event', '')
                if event == 'subscribe':
                    welcome_msg = """🌿 欢迎来到修草纪！

我是您的专属护肤顾问，专注于解决：
• 反复长痘、痘印困扰
• 皮肤敏感、屏障受损
• 色斑暗沉、肤色不均

💬 您可以：
1. 发送皮肤照片，获取专业诊断
2. 咨询产品搭配方案
3. 了解护肤知识和用法

我们不炒成分，只解决问题。
用结果做承诺，30天无效退款！

请告诉我您想解决什么皮肤问题？"""
                    response_xml = create_xml_response(from_user, to_user, welcome_msg)
                    response = make_response(response_xml)
                    response.content_type = 'application/xml'
                    return response
            
            # 其他消息类型
            else:
                reply = "收到您的消息！目前我支持文字咨询和图片诊断，请用文字描述您的皮肤问题，或发送面部照片进行肌肤分析。"
                response_xml = create_xml_response(from_user, to_user, reply)
                response = make_response(response_xml)
                response.content_type = 'application/xml'
                return response
                
        except Exception as e:
            print(f"消息处理错误: {e}")
            return 'success'  # 微信要求必须返回 success

@app.route('/api/chat', methods=['POST'])
def api_chat():
    """API 接口 - 直接对话"""
    data = request.json
    user_message = data.get('message', '')
    user_id = data.get('user_id', 'api_user')
    
    if not user_message:
        return {"error": "消息不能为空"}, 400
    
    reply = call_openai(user_message, user_id)
    return {"reply": reply}

# ==================== 主程序 ====================

if __name__ == '__main__':
    # 本地开发使用，生产环境由 Gunicorn 启动
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
