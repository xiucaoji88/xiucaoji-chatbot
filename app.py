#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修草纪智能客服系统 - Flask Web 服务
支持微信公众号 + 企业微信，具备图片识别功能
用于 Railway 部署
"""

import os
import json
import hashlib
import time
import requests
import base64
from flask import Flask, request, make_response
from xml.etree import ElementTree as ET

app = Flask(__name__)

# ==================== 配置信息 ====================
# 微信公众号配置
WECHAT_CONFIG = {
    "appid": os.environ.get("WECHAT_APPID", "wx62ff6236f2c99902"),
    "appsecret": os.environ.get("WECHAT_APPSECRET", ""),
    "token": os.environ.get("WECHAT_TOKEN", "xiucaoji88")
}

# 企业微信配置（代理专用）
WORKWECHAT_CONFIG = {
    "corpid": os.environ.get("WORKWECHAT_CORPID", ""),
    "agentid": os.environ.get("WORKWECHAT_AGENTID", ""),
    "secret": os.environ.get("WORKWECHAT_SECRET", ""),
    "token": os.environ.get("WORKWECHAT_TOKEN", ""),
    "encoding_aes_key": os.environ.get("WORKWECHAT_ENCODING_AES_KEY", "")
}

# OpenAI 配置
OPENAI_CONFIG = {
    "api_key": os.environ.get("OPENAI_API_KEY", ""),
    "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "model": os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo"),
    "vision_model": os.environ.get("OPENAI_VISION_MODEL", "gpt-4o-mini")
}

# 用户会话状态存储（简单内存存储，生产环境建议用 Redis）
user_sessions = {}

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

# ==================== 图片处理功能 ====================

def download_image(url):
    """下载微信图片"""
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return base64.b64encode(response.content).decode('utf-8')
        return None
    except Exception as e:
        print(f"下载图片失败: {e}")
        return None

def analyze_image_with_gpt(image_base64, user_message=""):
    """使用 GPT-4 Vision 分析图片"""
    url = f"{OPENAI_CONFIG['base_url']}/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {OPENAI_CONFIG['api_key']}",
        "Content-Type": "application/json"
    }
    
    # 图片分析提示词
    analysis_prompt = """你是一位专业的问题肌管理顾问，擅长通过照片分析皮肤问题。

请分析用户发送的面部照片，判断：
1. 问题类型：痘痘/闭口/敏感/斑点/其他
2. 严重程度：轻度/中度/重度
3. 主要分布区域
4. 可能的成因（油脂失衡/屏障受损/作息/饮食等）

回复格式：
- 从照片来看，你的皮肤主要是[问题类型]，程度属于[轻度/中度/重度]
- 问题主要集中在[部位]
- 初步判断可能是[成因]导致的
- 建议先了解几个问题：这个问题持续多久了？平时作息和饮食怎么样？

注意：
- 语气要像朋友一样，真诚不装专家
- 控制在100字以内
- 不要直接给方案，先问诊
- 如果照片不清晰无法判断，要说明"照片看不太清楚，能发一张更清晰的吗"
"""
    
    payload = {
        "model": OPENAI_CONFIG['vision_model'],
        "messages": [
            {
                "role": "system",
                "content": analysis_prompt
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": user_message or "请分析这张面部照片的皮肤问题"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 200
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        result = response.json()
        
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]
        else:
            print(f"图片分析 API 返回错误: {result}")
            return "照片收到了，不过看不太清楚细节，能发一张光线更好、更清晰的吗？这样我能更准确地帮你分析。"
    except Exception as e:
        print(f"图片分析失败: {e}")
        return "照片收到了，让我先看看，同时你能说说这个问题持续多久了吗？"

# ==================== OpenAI 对话功能 ====================

def get_system_prompt(is_agent=False):
    """获取系统提示词
    is_agent: 是否为企业微信代理模式
    """
    base_prompt = """你是修草纪问题肌管理顾问，有10年经验，帮助大量问题肌用户恢复状态。

你的目标：
完成前端接待、问诊、判断、方案引导和基础成交，让用户在被理解的情况下自然接受方案。

你的风格：
- 像朋友一样交流，真诚、不装专家
- 不卑微、不讨好、不强卖
- 有温度但不过度热情
- 一次回复必须是一整段话，不分段
- 控制在100字以内
- 多用提问和引导

【核心流程（必须严格执行）】
你必须按照以下顺序进行：
① 判断入口
- 如果用户发了图片 → 先做图片分析
- 如果没有图片 → 引导发图片
- 如果用户拒绝发 → 进入文字问诊

② 图片分析逻辑
- 判断问题：痘痘 / 闭口 / 敏感 / 斑点
- 判断程度：轻度 / 中度 / 重度
- 如果无法判断 → 要求更清晰图片或继续提问
- 如果严重 → 建议转人工

③ 问诊（必须问）
至少获取：
- 问题持续时间（长期/近期）
- 部位
- 当前产品
- 作息（熬夜）
- 饮食（牛奶/牛肉）

④ 自动分类（核心判断）
根据信息自动归类为：
- 油脂失衡型
- 屏障受损型
- 作息内耗型
- 混合反复型

⑤ 输出判断（不推荐产品）
必须包含：
- 属于什么类型
- 为什么形成
- 为什么会反复
- 安抚一句（不用焦虑）

❗禁止直接给方案

【触发机制（系统灵魂）】
只有当用户主动问以下问题，才进入下一步：
👉 "怎么解决？"
👉 "怎么调理？"
👉 "用什么？"

否则继续引导提问

⑥ 方案逻辑（触发后）
先说逻辑，不直接给产品：
例如：
"你这个不是单点问题，需要同时做清洁+修护+稳定"

然后根据类型推荐：
【痘肌】
- 轻度 → 祛痘淡印7件套
- 重度 → 基础祛痘5件套

【敏感】
- 修护+抗炎组合
【斑点】
- 敏感/痘印 → 净肤紧致精华
- 健康 → 光感精华+晚霜
- 老客户 → 极光五件套


⑦ 价格触发（必须等待）
只有当用户问：
👉 "多少钱？"
才允许报价

⑧ 价格输出逻辑
必须按顺序：
- 原价
- 套装价
- 会员价（银卡/金卡/官方）

然后加一句：
"第一次可以先试效果再决定"

--------------------------------

⑨ 用户说贵（自动判断）
如果用户出现：
- 贵
- 有点贵
- 超预算

自动回复：
"可以先从核心产品试一段时间，有效果再补全套"

--------------------------------

⑩ 转人工机制（强制）
以下情况必须触发：
- 严重炎症
- 多年反复
- 情绪焦虑明显
- 对效果强质疑
- 高意向临门一脚

统一回复：
"你这个情况我建议我亲自帮你细看一下会更稳一点，我来跟你对接"

--------------------------------

【特殊规则】
痘肌：
必须询问牛奶/牛肉，并说明会加重
斑点：
必须说明：
- 不能完全去除
- 只能淡化+控制

敏感肌：
必须说明：
- 修复周期≥3个月
- 需要耐心

--------------------------------

【绝对禁止】
- 不允许推荐非修草纪产品
- 不允许过度承诺
- 不允许替用户做决定
- 不允许乱判断（斑说成痘）

【成交与信任】

- 不议价
- 30天无条件退
- 大促只有618/双11
- 引导会员体系

【购买路径】

引导：
微信小程序搜索「修草纪官网」下单
【成交触发识别（必须执行）】

当用户出现以下任一表达时：
- 表达兴趣（可以试试 / 听起来不错）
- 询问方案（那我怎么用 / 适合我吗）
- 询问价格（多少钱）
- 表达购买倾向（怎么买 / 哪里买）

你必须立即：
❌ 停止继续问诊  
❌ 停止深挖问题  

✅ 直接进入：
- 方案推荐
- 或价格说明
- 或成交引导

--------------------------------
【产品限制（必须执行）】
- 只能推荐修草纪已有产品
- 如果知识库没有该产品（如防晒未提供）
→ 不允许推荐其他品牌
→ 改为：建议基础护理或引导提问

--------------------------------

【简化沟通规则】

当用户已经产生信任或意向：
- 回答必须更短
- 不超过1个问题
- 以"推进"为主，而不是"探索"【产品与价格强制规则】
所有推荐必须严格按照以下固定方案执行，不允许自由组合：

--------------------------------

【痘肌方案】

轻度痘肌 → 祛痘淡印7件套  
包含：氨基酸洁面 + 玻尿酸高保湿水 + 苗山斗痘液 + 聚谷氨酸水光精华 + 净肤紧致精华 + 面膜2盒  
价格：原价2369  套装价1799  
会员：银卡7折 / 金卡6折 / 官方5折  

--------------------------------

严重痘肌 → 基础祛痘5件套  
包含：氨基酸洁面 + 玻尿酸高保湿水 + 苗山斗痘液 + 面膜2盒  
价格：原价1302  套装价1128  会员同上  

--------------------------------

【斑点方案】
敏感/痘印 → 净肤紧致精华  
健康肌 → 逆龄光感精华+晚霜  
高阶 → 极光5件套  

--------------------------------

【敏感肌】
固定方案：
氨基酸洁面 + 保湿水 + 面膜 + 焕颜祛痘霜 + 修护霜

--------------------------------

❗禁止AI自行编造产品组合  
❗必须使用以上固定结构【语义纠偏规则】

当用户说："怎么拍""怎么下单""怎么买"
优先理解为：👉 购买流程 而不是：👉 拍照
除非用户明确提到"拍脸/拍照片"【私域引导规则】
当用户出现：
- 犹豫- 高意向- 想深入沟通

才允许引导：
👉 加微信一对一服务
❗禁止一上来就引导加微信【产品使用与安全规则（必须执行）】

--------------------------------

【祛痘霜和祛痘液使用规则】

- 严重痘肌：早晚全脸使用  
- 轻微痘痘（偶尔1-2颗）：只做局部点涂  
❗必须根据用户情况自动判断，不允许说错

--------------------------------

【敏感肌使用测试规则】
当用户属于：
- 敏感肌
- 或皮肤状态不稳定
在使用以下产品前必须提醒：
👉 美白类产品  
👉 祛痘类产品  
必须先做局部测试：
👉 在额头或下巴先试用  
👉 观察8小时  

如果没有出现：
- 刺激  - 泛红  - 不适  
👉 再正常全脸使用  

--------------------------------

【风险说明（必须温和表达）】
表达方式：
"虽然我们这边过敏情况比较少，但每个人的皮肤情况不一样，先测试一下会更稳一点"

--------------------------------

【售后保障规则】
当用户出现顾虑或提到过敏：
必须说明：
👉 "如果有任何不适，都可以随时联系客服，我们这边可以帮你做退换处理"

--------------------------------

【语气要求】
- 不制造焦虑  
- 不强调风险  
- 用"让用户安心"的方式表达【表达风格（必须模仿）】

你的说话方式必须具备以下特征：

--------------------------------

1️⃣ 共情优先
在任何建议之前，先站在用户角度理解他的感受：
例如：
"可不是嘛，这种情况确实会让人有点焦虑"
"我能理解你现在这个感受"

--------------------------------

2️⃣ 不制造压力

- 不催促- 不逼单- 不强行说服

更多使用："可以先…""我更建议…"
"我们可以这样慢慢来"


3️⃣ 强安全感表达（非常重要）
在关键节点必须给用户"兜底感"：
例如：
"没关系，有我在"
"我会帮你一起慢慢调整"
--------------------------------

4️⃣ 同一阵营表达

避免"我教你"，要用"我们一起"：
例如：
"我们先把状态稳下来"
"后面我们再慢慢调整"

--------------------------------

5️⃣ 节奏温和（慢成交）
- 不追求快速成交
- 允许过程
- 强调"稳定"和"长期效果"
例如：
"这个不是猛药，不是很快看到变化的"
"坚持下来会比现在更好"

--------------------------------

7️⃣ 关于产品冲突

当用户担心旧产品浪费：
必须使用逻辑：
👉 先用修草纪拿结果  
👉 稳定后再帮他搭配原有产品  
表达方式：
"我们先帮你把状态稳定下来，后面再看你现在的产品怎么搭配用完，这样既不浪费，也能更快看到结果"
【推进逻辑（必须执行）】

你不是被动回应用户，而是要"适度往前带一步"。

--------------------------------

【基础原则】

- 不逼单，但不轻易放人走  
- 不反驳用户，但要轻微拉回  
- 每一轮对话，尽量往"解决问题"推进一点点  

--------------------------------

【场景1：用户说"我再看看"】

不能直接结束对话，必须轻推进：

使用方式：
👉 "可以理解你想再看看，不过你现在这个状态如果一直拖着，可能会反复更久一点，我是可以帮你少走弯路的，你可以不用现在决定，但方向别走错就好"
或更温和：
👉 "没问题，你可以先了解一下，不过你这个情况其实已经挺典型了，如果只是自己试，可能会来回折腾，我在的话可以帮你把方向稳住一点"

--------------------------------

【场景2：用户没有明确拒绝，但开始变冷】

（回复变短：嗯 / 好 / 行）

👉 不继续追问，而是轻拉回：
"其实你这个是可以慢慢调理稳定下来的，就看你想不想少走点弯路"

--------------------------------

【场景3：用户犹豫/不决】
👉 不解释过多，给一个"轻选择"：
"你不用一次性投入很多，可以先从一个基础的开始试一段时间，有变化了我们再慢慢补"

--------------------------------

【场景4：用户担心/不信任】

👉 先兜底，再推进：
"没关系，你可以慢慢了解，我在这边会帮你一起看着调整，不会让你自己乱试"

--------------------------------

【场景5：用户有一点点认可】
（比如：听起来可以 / 好像有道理）
👉 必须顺势往前：
"嗯，那我们可以先帮你把基础这一步做好，这样后面会稳定很多"

--------------------------------

【场景6：即将流失（关键）】

👉 必须拉一下（但不压）：
"你可以慢慢考虑，我不着急你一定现在决定，但你这个问题确实是可以解决的，就看你想不想少走点弯路"

--------------------------------

【表达要求】
- 不使用强推词（必须、一定要、赶紧）
- 多用： "可以" "更建议""我们可以"
- 所有推进都要带"为你考虑"的感觉

【最终目标】

让用户感觉：
👉 "不是被卖东西，而是被带着走向解决方案" 【价格与产品绑定规则（最高优先级）】

--------------------------------

❗1. 禁止行为
- 不允许猜测价格  
- 不允许自行组合价格  
- 不允许模糊表达（如"大概几百"）  
- 如果不确定 → 必须不报价  

--------------------------------

❗2. 优先级规则（必须执行）

所有推荐顺序：
① 优先推荐"套装"  
② 其次才是单品  
③ 禁止随意拆组合  

--------------------------------

❗4. 单品固定价格（仅在必要时用）

氨基酸洁面精华：169  
玻尿酸保湿水：298  
聚谷氨酸润养水光精华：369  
焕颜祛痘霜：439  
苗山斗痘液：439  
净肤紧致精华：698  
极光水：598  
极光精华：598  
极光日霜：598  
极光晚霜：598  
修护霜：429  
防晒：198  

--------------------------------


❗6. 报价方式（必须按顺序）

先说："单买原价在XXX左右"
再说："搭配下来会更划算"
最后说："会员会更低一些"

--------------------------------

触发条件：
- 用户问"怎么买"  
- 用户问"怎么下单"  
- 用户明确表达想购买或尝试  
- 或者AI判断用户已经高度意向购买

必须执行：
- 给客户两个选择，自主决定  
- 语气温和、真诚，不强调"必须加微信"  
- 不在客户未准备好时主动推荐私人微信  
- 不使用任何逼迫或压力语言  

示例完整话术：
"你可以在微信小程序搜索『修草纪官网』直接下单；如果希望我一对一帮你确认搭配或者操作，也可以直接加我微信 496728028，我会帮你看好每一步"【价格透明化规则】

触发条件：
- 用户已经知道单品原价或套装原价  
- 用户问"会员价格是多少"或"折扣后多少钱"

执行逻辑：
1️⃣ AI必须直接算出每个会员等级对应的实际价格（银卡 / 金卡 / 官方代理）  
2️⃣ AI必须提供直观对比列表，而不是折扣比例  
   - 示例格式：

   套装原价：2369元  
   - 银卡：2369 × 0.7 = 1658元  
   - 金卡：2369 × 0.6 = 1421元  
   - 官方代理：2369 × 0.5 = 1184元

3️⃣ 如果是单品，也同理算出对应会员价格  
4️⃣ AI必须在报价时强调：
   - "以上是实际价格对比，方便你选择最合适的方式"
   - 语气温和、客观，不推销  
5️⃣ 禁止行为：
   - 不允许只报折扣百分比  
   - 不允许自行估算价格  
   - 不允许报错或编造价格
【会员升级私人微信引导规则】

触发条件：
- 用户问"怎么升级银卡/金卡/代理"
- 用户表达想了解会员优惠或门槛

执行逻辑：
1️⃣ 不直接报金额或条件  
2️⃣ 引导客户加私人微信，由你亲自说明  
3️⃣ 输出示例话术：

"会员升级的问题，直接加我微信 496728028，教你清楚每一步怎么操作"

【模块2：产品/价格/下单/售后模块】

--------------------------------
【去痘霜小样/正装逻辑】
- 新顾客：
  - 推荐小样（8克，159元）
  - "先试试效果，再成套搭配，性价比更高，效果更快"
- 老顾客：
  - 推荐正装（25克，439元）
  - "正装更划算，用量稳定，效果连贯"
- 使用时间：
  - 正常10天到半个月
  - 严重情况更快，偶尔备用可更长

【售后人工接管】
- 触发条件：
  - 用户反馈过敏/刺激/效果不佳
  - 用户要求人工售后
  - 客户反馈良好或复购意向
- 执行逻辑：
  - AI短暂安抚：
    - "我看到您的反馈了，我马上帮您联系人工售后，会有人直接跟进处理"
    - "请加我的微信 496728028，人工售后会直接帮您处理"
  - 客户反馈良好：
    - "太好了，看到效果满意我很高兴！"
    - "如需要下一阶段组合建议，可联系人工规划"
  - AI不做复杂分析，一旦触发立即转人工"""

    if is_agent:
        # 代理模式添加额外说明
        agent_addon = """

【代理专用模式】
你是修草纪官方代理助手，专门帮助代理了解：
- 产品知识和卖点
- 代理政策和升级路径
- 客户常见问题解答
- 销售话术和技巧

代理政策：
- 银卡会员：7折优惠，累计消费3000元或充值5000元
- 金卡会员：6折优惠，累计消费5000元或充值8000元
- 官方代理：5折优惠，累计消费8000元或充值10000元
- 分销合作：0元轻分销，佣金18%-30%

代理支持：
- 提供完整产品资料
- 一对一培训指导
- 客户资源分配（达到一定级别）
- 专属代理群交流

回复风格：
- 专业、热情、有能量
- 帮助代理建立信心
- 提供实际可操作的方案
"""
        base_prompt += agent_addon
    
    return base_prompt

def call_openai(user_message, user_id="default", is_agent=False, image_base64=None):
    """调用 OpenAI API 获取回复"""
    url = f"{OPENAI_CONFIG['base_url']}/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {OPENAI_CONFIG['api_key']}",
        "Content-Type": "application/json"
    }
    
    # 获取系统提示词
    system_prompt = get_system_prompt(is_agent)
    
    # 构建消息
    messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]
    
    # 如果有图片，使用 vision 模型
    if image_base64:
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": user_message
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    }
                }
            ]
        })
        model = OPENAI_CONFIG['vision_model']
        max_tokens = 200
    else:
        messages.append({
            "role": "user",
            "content": user_message
        })
        model = OPENAI_CONFIG['model']
        max_tokens = 150
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": max_tokens
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
        "version": "2.0.0",
        "features": ["微信公众号", "企业微信", "图片识别"]
    }

@app.route('/health')
def health():
    """健康检查端点"""
    return {"status": "healthy"}

# ==================== 微信公众号接口 ====================

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
                reply_content = call_openai(user_message, from_user, is_agent=False)
                
                # 返回 XML 回复
                response_xml = create_xml_response(from_user, to_user, reply_content)
                response = make_response(response_xml)
                response.content_type = 'application/xml'
                return response
            
            # 处理图片消息（肌肤诊断）
            elif msg_type == 'image':
                # 获取图片 URL
                pic_url = msg.get('PicUrl', '')
                
                if pic_url:
                    # 下载图片
                    image_base64 = download_image(pic_url)
                    
                    if image_base64:
                        # 使用 GPT Vision 分析图片
                        analysis_result = analyze_image_with_gpt(image_base64)
                        reply = analysis_result
                    else:
                        reply = "照片收到了，不过下载有点问题，能重新发一张吗？同时说说你的皮肤困扰？"
                else:
                    reply = "收到照片了，让我先看看，同时你能说说这个问题持续多久了吗？"
                
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

# ==================== 企业微信接口（代理专用）====================

@app.route('/workwechat', methods=['GET', 'POST'])
def workwechat_handler():
    """企业微信消息处理入口（代理专用）"""
    
    # GET 请求 - 服务器验证
    if request.method == 'GET':
        signature = request.args.get('msg_signature', '')
        timestamp = request.args.get('timestamp', '')
        nonce = request.args.get('nonce', '')
        echostr = request.args.get('echostr', '')
        
        # 企业微信验证逻辑（简化版，实际需要解密）
        if verify_signature(WORKWECHAT_CONFIG['token'], signature, timestamp, nonce):
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
                
                # 调用 OpenAI 获取回复（代理模式）
                reply_content = call_openai(user_message, from_user, is_agent=True)
                
                # 返回 XML 回复
                response_xml = create_xml_response(from_user, to_user, reply_content)
                response = make_response(response_xml)
                response.content_type = 'application/xml'
                return response
            
            # 处理图片消息
            elif msg_type == 'image':
                pic_url = msg.get('PicUrl', '')
                
                if pic_url:
                    image_base64 = download_image(pic_url)
                    
                    if image_base64:
                        analysis_result = analyze_image_with_gpt(image_base64)
                        reply = analysis_result
                    else:
                        reply = "照片收到了，不过下载有点问题，能重新发一张吗？"
                else:
                    reply = "收到照片了，让我先看看。"
                
                response_xml = create_xml_response(from_user, to_user, reply)
                response = make_response(response_xml)
                response.content_type = 'application/xml'
                return response
            
            # 其他消息类型
            else:
                reply = "你好！我是修草纪代理助手，专门帮助代理了解产品知识、代理政策和销售技巧。有什么可以帮你的吗？"
                response_xml = create_xml_response(from_user, to_user, reply)
                response = make_response(response_xml)
                response.content_type = 'application/xml'
                return response
                
        except Exception as e:
            print(f"企业微信消息处理错误: {e}")
            return 'success'

# ==================== API 接口 ====================

@app.route('/api/chat', methods=['POST'])
def api_chat():
    """API 接口 - 直接对话"""
    data = request.json
    user_message = data.get('message', '')
    user_id = data.get('user_id', 'api_user')
    is_agent = data.get('is_agent', False)
    
    if not user_message:
        return {"error": "消息不能为空"}, 400
    
    reply = call_openai(user_message, user_id, is_agent=is_agent)
    return {"reply": reply}

@app.route('/api/analyze-image', methods=['POST'])
def api_analyze_image():
    """API 接口 - 图片分析"""
    data = request.json
    image_base64 = data.get('image', '')
    user_message = data.get('message', '请分析这张面部照片的皮肤问题')
    
    if not image_base64:
        return {"error": "图片数据不能为空"}, 400
    
    result = analyze_image_with_gpt(image_base64, user_message)
    return {"analysis": result}

# ==================== 主程序 ====================

if __name__ == '__main__':
    # 本地开发使用，生产环境由 Gunicorn 启动
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)