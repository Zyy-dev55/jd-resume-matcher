"""项目知识库：把简历里的四个项目拆成可检索的证据片段。

每条片段必须是一句可核对的原文事实，不允许出现推断或包装过的形容词。
检索与生成都只能引用这里的内容，这是「有证据才写」的落点。
"""

PROJECTS = [
    {
        "id": "P1",
        "name": "招聘信息筛选与投递助手（Chrome 扩展）",
        "stack": "Chrome MV3 / 大模型 API / 结构化输出 / Service Worker / 单元测试",
        "chunks": [
            "对接 8 家 OpenAI 兼容大模型服务商，统一由 Service Worker 代理转发，API Key 不落页面、不暴露于 CSP；支持服务商切换与调用失败自动放行。",
            "将模型判定拆为纯函数 + 结构化输出，设定「有明确硬门槛且原文有证据才拦截 / 未写明不推断 / 模型失败一律放行」三条约束抑制幻觉，并配单元测试保障可回归。",
            "针对招聘页薪资字体加密，在主世界被动拦截接口响应取明文薪资与 encryptBrandId，实现公司级精确去重。",
            "判断模块只返回结构化判定结果，不修改页面原有数据；模型异常、超时或返回格式错误时自动降级为放行。",
        ],
        "tags": ["大模型", "LLM", "API", "结构化输出", "Prompt", "幻觉抑制", "失败降级", "多服务商", "Agent", "工具调用", "Chrome 扩展", "密钥安全"],
    },
    {
        "id": "P2",
        "name": "生活用品电商系统（毕业设计）",
        "stack": "Spring Boot / MyBatis-Plus / MySQL / JWT / Vue 3 / GitHub Actions",
        "chunks": [
            "多店铺场景：以店铺标识做数据隔离边界、按店铺拆单分算运费；库存用条件更新 WHERE stock>=n 在 SQL 层防超卖；退款提现统一落商家余额形成资金闭环。",
            "安全侧做源 IP 识别、滑动窗口限流、登录防爆破、XSS / SQL 注入 / 路径穿越过滤与访问审计。",
            "质量体系：41 个 JUnit + 20 个 Vitest + 31 条端到端断言，GitHub Actions 自动回归，失败信息直指故障归属层。",
            "前后端分离架构，负责接口设计与联调；后端 Spring Boot + MyBatis-Plus + MySQL/H2，前端 Vue 3，JWT 鉴权。",
        ],
        "tags": ["Java", "Spring Boot", "MySQL", "SQL", "Python", "后端", "接口联调", "CI", "回归测试", "并发", "数据一致性", "电商"],
    },
    {
        "id": "P3",
        "name": "低压配电模拟器（电路仿真调试平台）",
        "stack": "图论建模 / 并查集 / 实时仿真 / 分层排障",
        "chunks": [
            "按实物端子数建模引脚，用并查集求等电位后求解回路并为导线着色；诊断模块校验线类别、线径与 PE/N 混接，支持 8 类故障注入。",
            "L1 到 L4 分层排障定位「首个故障层」而非只报现象；67 条断言用例全部通过。",
        ],
        "tags": ["分层排障", "断言", "测试", "图论", "仿真", "故障注入", "Python"],
    },
    {
        "id": "P4",
        "name": "修仙炼体 · 宗门养成小程序",
        "stack": "纯逻辑引擎 / tick(dt) 帧循环 / 配置驱动 / 单文件",
        "chunks": [
            "用 tick(dt) 帧循环写纯逻辑内核并与 UI 解耦，一份内核同时驱动小程序与 H5；境界装备数值外置配置表。",
            "整体压进约 220KB 单 HTML，图形全用 Canvas/SVG 现画、零外部资源，无网络可运行。",
        ],
        "tags": ["前端", "H5", "小程序", "配置驱动", "离线", "Canvas"],
    },
]


def all_chunks():
    """展开成扁平的检索单元，每项带项目归属，保证每条证据可溯源。"""
    out = []
    for p in PROJECTS:
        for i, text in enumerate(p["chunks"], 1):
            out.append({
                "chunk_id": f'{p["id"]}-C{i}',
                "project_id": p["id"],
                "project_name": p["name"],
                "stack": p["stack"],
                "text": text,
                "tags": p["tags"],
            })
    return out


def project_by_id(pid):
    for p in PROJECTS:
        if p["id"] == pid:
            return p
    return None
