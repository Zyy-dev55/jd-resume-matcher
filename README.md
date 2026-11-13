# JD 简历适配助手

一个面向求职场景的大模型应用工程实践：粘贴一段岗位 JD，先从自己的项目库里检索可核对的证据片段，再让模型按固定 JSON 结构输出「匹配点 / 能力缺口 / 简历改写建议 / 适配分」，并用 25 条固定评测集守住每次改动。模型不可用时自动降级为纯检索结果，绝不阻塞、绝不编造。

## 为什么要做这个

杭州在招的 AI 应用开发实习岗位，JD 里反复出现 RAG、Agent、结构化输出、评测集、失败降级、多服务商这些词。这个项目把「招聘助手 Chrome 扩展」里已经做过的三条底线，用一套可运行、可评测的管线重新实现了一遍，也顺便把简历里的技术表述和 JD 对齐。

## 架构

```
JD 文本
  │
  ├─ ① 检索：BM25 + 中文 2-gram，从 4 个项目的证据片段里召回 Top-K
  │         （retrieval.py，零依赖，可替换为向量检索 / RAGFlow）
  │
  ├─ ② 证据：每条片段带 chunk_id 与项目归属，生成时只能引用这些原文
  │
  ├─ ③ 生成：OpenAI 兼容接口，强制 JSON 结构输出，逐家失败降级
  │         （llm.py，Key 只从环境变量或本地 config 读）
  │
  ├─ ④ 降级：全部服务商失败 / JSON 解析失败 → 返回规则检索结果，标记 fallback
  │
  └─ ⑤ 评测：25 条固定 JD，统计 Hit@K、证据引用合规率、JSON 遵守率、降级率、延迟
            （evaluate.py → reports/eval_report.md）
```

三条底线（与 Chrome 扩展项目一致）：

1. 有证据才写：`evidence` 必须引用片段原文，不允许凭空推断；
2. 没写的标缺口：证据里没有的能力进 `gaps`，不包装成「了解」；
3. 模型失败一律放行：超时、限流、格式错误都降级，不把异常抛给用户。

## 快速开始

零依赖，Python 3.9+ 即可：

```bash
python matcher.py --demo --offline          # 离线规则模式，直接看效果
python matcher.py --eval --offline          # 跑 25 条评测集，生成报告
python matcher.py --providers               # 查看服务商配置状态
python matcher.py --jd "熟悉 RAG 与结构化输出，能用 Python 做 Agent 开发"
```

结构化结果写入 `reports/last_match.json`，评测报告写入 `reports/eval_report.md`。

## 接真实模型

完整步骤见 [接入大模型指南.md](接入大模型指南.md)。最快的是永久免费的智谱 GLM，已预置在默认配置 `config.example.json` 第一位：

```powershell
cd jd-resume-matcher                  # 先进入项目文件夹
$env:ZHIPU_API_KEY = "你的key"
python matcher.py --providers        # 确认 ready=true
python matcher.py --selftest         # 真实端点连通性自检
python matcher.py --demo             # 真实模型生成结构化匹配结果
python matcher.py --eval             # 25 条评测集，输出 JSON 遵守率与延迟
```

> `$env:变量 = "值"` 是 **PowerShell** 写法，只对当前窗口有效，关掉窗口即失效；Git Bash 用 `export ZHIPU_API_KEY=你的key`，cmd 用 `set ZHIPU_API_KEY=你的key`。三种 shell 语法不通用。
> 真要调用模型时**不要加 `--offline`**，加了就强制走本地规则、不会发请求。

配置是 OpenAI 兼容格式（`base_url` + `model`），支持各家官方环境变量名（`ZHIPU_API_KEY` / `DASHSCOPE_API_KEY` / `SILICONFLOW_API_KEY` / `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`）以及本项目专用变量 `JDMATCH_<NAME>_KEY`；本地 Ollama / LM Studio 端点无需 Key。`providers` 数组顺序即失败降级顺序；`response_format=json_object` 不被支持时自动去掉重试；全部失败返回 fallback。

> 仓库只提交 `config.example.json`（无任何密钥）。程序在缺少 `config.json` 时会自动读它，所以 clone 下来不用改任何文件就能跑 `--providers`、`--demo --offline` 和 `--eval --offline`；要自定义模型名或端口，复制一份为 `config.json` 再改（已被 .gitignore 忽略，不会误提交）。

## Windows 一键脚本（离线演示）

双击 `run_all.bat` 会依次跑 demo / eval / 负例三条命令，末尾自动暂停；中文 JD 从 `sample_jd_negative.txt` 读取，避免 cmd 中文参数乱码。脚本三条命令都带 `--offline`，**只做本地检索评测，不调用模型**。接了 Key 之后请按上一节在**同一个 PowerShell 窗口**手动敲命令——双击启动的是新进程，读不到该窗口里用 `$env:` 临时设的环境变量。

没有 Key 也能验证接入层写对了：

```bash
python matcher.py --selftest --mock
```

本机起一个 mock OpenAI 兼容服务，离线跑完 HTTP 请求 → 响应解析 → JSON 校验 → 逐家降级，共 5 项自检（含日志不泄露 Key）。

配置好之后，同一份评测集分别跑不同模型，对比 JSON 格式遵守率、延迟和成本，就是「用过哪些先进大模型、差异在哪」这道题的真实答案。把结果记到下面这张表里：

| 模型 | JSON 遵守率 | 平均延迟 | 降级率 | 备注 |
| --- | --- | --- | --- | --- |
| 智谱 GLM `glm-4-flash` | 100% | 6747 ms | 0% | 2026-11-12 实测，25 条评测集 / API 模式；为加入证据一致性校验**之前**的基线，改动后请重跑覆盖 |

## 评测集说明

`eval_set.json` 有 25 条 JD：20 条正例取材于杭州 AI 应用开发实习岗位的常见要求并标注应召回的项目（`expect_project`），5 条负例是完全无关的岗位（博士论文、医学影像、C++ 引擎、关务、审计），标注 `NONE`。指标含义：

- **正例 Hit@K**：Top-K 检索片段里是否包含期望项目，衡量检索层有没有把对的证据送进上下文；
- **负例正确拒绝率**：无关 JD 的 Top1 得分是否低于证据阈值（`MIN_EVIDENCE_SCORE = 5.0`）。低于阈值时片段不进生成上下文，返回「无可核对证据」而非硬凑匹配点 —— 这是幻觉抑制在检索层的落点；
- **JSON 遵守率**：模型返回能被 `json.loads` 解析且字段齐全的比例（仅在配置了 API 时有效）；
- **证据引用合规率**：返回的 `matched[].evidence` 全部能在送进上下文的片段原文里找到的比例。生成层逐条校验，不合格的匹配点直接剔除并记入 `dropped_invalid_evidence`，不让它混进简历建议；
- **降级率** / **平均延迟**：触发 fallback 的用例占比、单次结构化调用耗时。

阈值不是拍脑袋定的：实测负例 Top1 得分 1.96–3.22，正例 12 以上，取 5.0 留出明显间隔。

> 注意：`--offline` 跑出来的数字只反映检索层，**不能当成模型效果**。真实模型指标见上表：2026-11-12 用智谱 GLM `glm-4-flash` 跑完 25 条（JSON 遵守率 100% / 平均延迟 6747 ms / 降级率 0%），逐条明细见 `reports/eval_report.md`。该次运行发生在「解析层证据引用校验」加入之前，属于基线；改动后请重跑覆盖。

## 目录

```
matcher.py                 命令行入口（demo / eval / jd / selftest / providers）
jd_matcher/knowledge.py    4 个项目经历拆出的证据片段（唯一事实来源）
jd_matcher/retrieval.py    BM25 + 中文 2-gram 检索、证据阈值
jd_matcher/llm.py          OpenAI 兼容客户端 / 结构化输出 / 解析层证据校验 / 逐家降级
jd_matcher/evaluate.py     评测集与报告生成
jd_matcher/selftest.py     mock 端点 5 项链路自检
eval_set.json              25 条评测用例（20 正例 / 5 负例）
config.example.json        默认服务商配置（无密钥，clone 即用）
接入大模型指南.md           Key 获取、三种 shell 语法、本地免 Key 方案
docs/项目设计与实测记录.md   架构取舍、已知局限、真实调用数据出处
run_all.bat / sample_jd_negative.txt   Windows 离线一键演示
reports/                   评测与自检报告（实测证据）
```

## 面试怎么讲

- **为什么不用 LangChain**：短文本、证据量小，BM25 足够且零依赖、可解释；`search()` 接口按可替换设计，向量检索接上就能做 A/B 对比。
- **怎么抑制幻觉**：检索层设证据阈值，无关 JD 直接返回「无可核对证据」；生成层再兜一道——`_parse()` 会拿 `evidence` 和送进上下文的片段原文逐条比对，不是原文子串就剔除该匹配点，并在 `gaps` 里写明剔除了几条。这道校验是接真实模型后才补的：GLM 会把**项目名**当证据填进 `evidence`，光靠 Prompt 里「必须引用原文」拦不住，必须有代码兜底。
- **怎么保证改动不劣化**：25 条固定评测集 + 报告落盘，改 Prompt 或换模型就重跑一次；新增校验后 `--selftest --mock` 仍应 5/5，检索层指标不应变化。
- **多服务商怎么做**：统一 OpenAI 兼容协议，Key 走环境变量，逐家重试，全挂放行。
- **没做过的部分如实说**：向量库、Multi-Agent 编排、Dify/Coze 可视化工作流目前是了解与上手阶段，不写进项目经历。

## 后续可做

- [ ] 把 `search()` 换成向量检索，与 BM25 做混合检索并对比 Hit@K
- [ ] 增加「按 JD 生成一版简历正文」的输出，并加人工确认步骤
- [ ] 评测集扩充到 50 条，覆盖更多无关领域与边界表述
