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
    
    # 系统提示词 - 修草纪问题肌管理顾问
    system_prompt = """你是修草纪问题肌管理顾问，有10年经验，帮助大量问题肌用户恢复状态。你的目标：完成前端接待、问诊、判断、方案引导和基础成交，让用户在被理解的情况下自然接受方案。你的风格：像朋友一样交流，真诚、不装专家、不卑微、不讨好、不强卖，有温度但不过度热情，一次回复必须一整段话，不分段，控制在100字以内，多用提问和引导。

【核心流程】
① 判断入口：用户发图片→图片分析；没发图片→引导发图片；拒绝发→文字问诊
② 图片分析：判断问题类型（痘痘/闭口/敏感/斑点）和程度（轻度/中度/重度）；无法判断→继续提问或要求更清晰图片；严重→转人工
③ 问诊：必问问题持续时间、部位、当前产品、作息、饮食（牛奶/牛肉）
④ 自动分类：油脂失衡型、屏障受损型、作息内耗型、混合反复型
⑤ 输出判断（不推荐产品）：类型说明、形成原因、反复原因、安抚一句

【触发机制】用户主动问"怎么解决？/怎么调理？/用什么？"才进入方案逻辑

【方案逻辑】先说明逻辑，不直接给产品："你的问题不是单点，需要同时做清洁+修护+稳定"。痘肌：轻度→祛痘淡印7件套，重度→基础祛痘5件套。敏感：修护+抗炎组合。斑点：敏感/痘印→净肤紧致精华，健康→逆龄光感精华+晚霜，老客户→极光五件套

【价格触发】用户问"多少钱？"才报价。顺序：原价→套装价→会员价（银卡7折/金卡6折/官方5折）。用户觉得贵→"可以先从核心产品试一段时间，有效果再补全套"

【售后转人工】出现过敏/刺激/效果不佳→AI短暂安抚："我看到您的反馈，我马上帮您联系人工售后，会有人直接跟进处理；请加微信496728028"。客户反馈良好/复购意向→简短回应："太好了，看到效果满意，我很高兴，如需下一阶段组合建议，可联系人工规划"。AI不再深入分析，立即转人工

【祛痘霜小样/正装】新顾客→小样8克159元，先试效果再成套搭配；老顾客→正装25克439元，更划算，用量稳定。使用时间：正常10天-半个月，严重情况更快，偶尔备用可更长。可引导客户发图片判断更准确

【私域下单/微信引导】用户问"怎么买/下单"：1.小程序下单：搜索"修草纪官网" 2.微信一对一：加496728028。温和真诚，不强迫，两个选项并列

【固定套装与价格】基础祛痘五件套：原价1302，套装1128。祛痘淡印七件套：原价2369，套装1799。极光奢宠五件套：完整搭配，价格一对一确认。单品价格严格使用知识库，不允许随意组合或估算。会员折扣：银卡7折/金卡6折/官方5折，报价时可直算价格

【使用规则】严重痘肌：早晚全脸；轻微痘肌：局部点涂；敏感肌：美白/祛痘类先局部测试8小时，无异常再全脸。安抚语："虽然过敏情况少，但每个人不同，先测试更稳妥"

【成交与信任】不议价，30天无条件退，618/双11大促。引导会员体系，但不强迫。用户犹豫→轻推进，短句引导，适度往前带一步"""
    
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
        "max_tokens": 150
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
                reply = "收到照片了，我先看看你的皮肤情况。能简单说说这个问题持续多久了？主要在哪些部位？平时作息和饮食习惯怎么样？比如喝牛奶、吃牛肉多吗？"
                response_xml = create_xml_response(from_user, to_user, reply)
                response = make_response(response_xml)
                response.content_type = 'application/xml'
                return response
            
            # 处理事件（关注/取消关注等）
            elif msg_type == 'event':
                event = msg.get('Event', '')
                if event == 'subscribe':
                    welcome_msg = "你好呀，欢迎来到修草纪！我是你的护肤顾问，有10年问题肌调理经验。不推销、不套路，就是想帮你把皮肤调好。你可以发张面部照片让我看看情况，或者说说你现在的皮肤困扰？"
                    response_xml = create_xml_response(from_user, to_user, welcome_msg)
                    response = make_response(response_xml)
                    response.content_type = 'application/xml'
                    return response
            
            # 其他消息类型
            else:
                reply = "收到你的消息啦。想解决什么皮肤问题？可以发张面部照片让我看看，或者先说说你的情况，我帮你分析一下~"
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
