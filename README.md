# 课程问卷智能分析工具 v1.0

批量读取课程问卷 Excel，自动清洗、映射、统计分析，生成多维度分析报告。

## 当前 FastAPI 分析流程

`/analysis`、`/generate_report` 和 `/dify/analyze` 共用同一条问卷分析流程。评分由 Python 计算；有效文本反馈默认调用 DeepSeek，一次返回意见拆分、分类、情感和原文证据。空白及低信息反馈不会发送给模型。

运行服务前需设置 `.env.example` 中的 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL` 和 `DEEPSEEK_MODEL`。若模型分析失败，评分统计仍会生成，结果状态为 `partial`，失败明细会返回到接口并写入报告的“AI分析错误”工作表。`feedback_count` 表示拆分出的意见数；`feedback_response_count` 表示文本题记录数。

## 环境要求

- Python 3.13（部署环境；已有的 Python 3.10 本地环境也可运行，但不再接收安全更新）
- pandas
- openpyxl
- numpy
- Streamlit（仅网页界面需要，见 `requirements-ui.txt`）

## 安装

在本项目根目录安装 API 与命令行依赖：

```cmd
python -m pip install -r requirements.txt
```

需要运行 Streamlit 网页界面时安装：

```cmd
python -m pip install -r requirements-ui.txt
```

## 目录结构

```
course-insight-ai-agent/
├── app.py                     # Streamlit 网页界面入口
├── main.py                    # 命令行主入口
├── core/                      # 数据读取、清洗、评分统计和 Excel 输出
├── api/                       # FastAPI 接口
├── agent/                     # 单文件分析流程
├── llm/                       # 模型调用与校验
├── scripts/                   # 批量 AI 分析流程
├── requirements.txt
├── requirements-ui.txt
├── README.md
├── config/
│   └── question_mapping.xlsx  # 题目映射配置
└── data/
    ├── input/                  # 输入：课程问卷 Excel 文件
    │   ├── 产品经理训练营_第01期.xlsx
    │   ├── 产品经理训练营_第02期.xlsx
    │   ├── 数据分析实战课_第01期.xlsx
    │   └── 数据分析实战课_第02期.xlsx
    └── output/                 # 输出目录
        ├── course_survey_analysis.xlsx
        └── survey_analysis_*.log
```

## 输入文件格式

### 问卷数据文件 (data/input/*.xlsx)

- 文件名格式：`课程名称_第XX期.xlsx`
- 第一行为表头，必须包含：
  - 学员编号列（含"学员"或"编号"字样）
  - 提交时间列（含"提交"或"时间"字样）
  - 若干评分/文本题目列
- 评分题值为 1 到 max_score 之间的数字
- 文本题为自由文本

### 题目映射配置 (config/question_mapping.xlsx)

包含以下列：

| 列名 | 说明 | 示例 |
|---|---|---|
| original_question | 原始题目文本 | 课程整体满意度 |
| standard_question | 标准题目名称 | 课程整体满意度 |
| question_type | 题目类型 | rating / text |
| max_score | 满分值（评分题） | 5 |
| category | 题目分类 | common / course_common / period_specific / feedback |

category 说明：
- `common`：全局公共题（所有课程所有期次均出现）
- `course_common`：课程公共题（同一课程各期次均出现）
- `period_specific`：单期特有题（仅某期次出现）
- `feedback`：开放式反馈题

## 运行

### FastAPI 与部署

本地启动 API：

```cmd
python -m uvicorn api.main_api:app --host 0.0.0.0 --port 8000
```

`render.yaml` 配置的是 FastAPI 服务，`Dockerfile` 也启动同一个 API；两者都不会自动启动 Streamlit 界面。首次通过 Render Blueprint 创建服务时，Render 会提示填写 `DEEPSEEK_API_KEY` 和 `SERVICE_API_KEY`；已有服务需要在 Render 后台手动添加。`DEEPSEEK_BASE_URL` 和 `DEEPSEEK_MODEL` 已在 Blueprint 中设置。`SERVICE_API_KEY` 应使用独立生成的长随机值，不要与 DeepSeek 密钥相同，也不要提交到 Git。若未配置该值，受保护接口会返回 503；无效或缺失的令牌会返回 401。调用分析、反馈、报告生成和下载接口时，发送请求头 `Authorization: Bearer <SERVICE_API_KEY>`。根路径 `/` 可用于无需密钥的运行状态检查。每次分析生成独立的报告文件，避免同一课程、期次重复分析时覆盖旧报告。报告默认保存在服务本地的 `data/output/`；若部署环境提供持久化目录，可通过 `REPORT_OUTPUT_DIR` 指向该目录。下载链接仍依赖处理请求的服务实例能访问该文件；多实例共享报告需要后续接入共享存储。

GitHub Actions 会在 PR 上运行无密钥的自动测试。本地构建 Docker 镜像时，`.dockerignore` 会排除 `.env` 和运行数据；线上密钥应通过部署环境变量提供。

### 方式一：网页界面（推荐）

通过浏览器上传文件、在线查看结果、下载分析报告：

```cmd
streamlit run app.py
```

如果 `streamlit` 命令未加入 PATH，可使用：

```cmd
python -m streamlit run app.py
```

启动后浏览器访问 `http://localhost:8501`。

**使用步骤：**
1. 在左侧上传区域选择问卷 Excel 文件（可多选）
2. 上传题目映射配置文件 `question_mapping.xlsx`
3. 点击"开始分析"按钮
4. 查看分析结果概览和各维度统计表
5. 点击"下载完整分析报告"保存 Excel 文件

**特点：**
- 上传文件保存到临时目录，不会覆盖 `data/input/` 中的原始测试文件
- 分析完成后自动清理临时文件
- 全中文界面，适合课程运营或数据分析人员使用

### 方式二：命令行

批处理 `data/input/` 目录下的所有问卷文件：

```cmd
python main.py
```

输出文件保存至 `data/output/course_survey_analysis.xlsx`。

## 输出工作表说明

| 工作表 | 内容 |
|---|---|
| 数据总览 | 核心指标汇总（文件数、学员数、评分数、反馈统计等） |
| 文件识别结果 | 文件名→课程名+期次解析结果 |
| 标准化长表 | 宽表转长表后的全部数据 |
| 题目映射结果 | question_mapping.xlsx 的完整内容 |
| 题目覆盖情况 | 各题目的分类与映射情况 |
| 全局公共题统计 | 所有课程汇总的评分统计 |
| 课程公共题统计 | 按课程分组的评分统计 |
| 单期特有题统计 | 单期题目的评分统计 |
| 期次评分统计 | 各期次所有题目的评分统计 |
| 开放式反馈 | 清洗后的文本反馈（含标记类型、重复次数） |
| 反馈频次汇总 | 按课程、期次、反馈文本的出现频次 |
| 异常数据 | 异常评分明细（缺失、超范围、非数字） |
| 人工待确认 | 未映射题目、解析失败、需人工判断的异常记录 |

## 统计指标说明

评分题统计包含：
- 有效样本数、缺失数
- 平均分、标准差、中位数
- 最低分、最高分
- 满分率、低分率（≤2分）
- 百分制标准分（平均分/满分×100）

文本反馈标记类型：
- 纯空白反馈：学员未填写任何内容
- 低信息量反馈：仅包含"无""挺好""很好"等无实质信息的内容
- 有效反馈：包含实质性建议或意见

### AI 反馈统计口径

- `已分类反馈人数`：同一课程、同一期次中，至少有一条意见成功分类且通过数据校验的去重学员数。它不等于课程总学员数，也不等于全部问卷答卷人数。
- 标签和正向、负向、建议汇总中的人数占比，均以该课程该期的`已分类反馈人数`为分母；同一学员提出多条相同意见只计一人，反馈次数仍按意见条数计算。
- 概览中的 `positive占比` 等以拆分意见总数为分母，属于意见条数占比，不是学员人数占比。
- 跨期趋势仅描述已分类反馈中的观察结果。最新一期未观察到某标签，不能据此判断该问题已经改善；各期分类失败或样本差异也可能影响占比。

### AI 分类标签与缓存

分类标签以 `config/feedback_taxonomy.yaml` 为准，分类提示词会从该文件生成可选标签。修改标签配置或分类提示词后，分类缓存会自动失效；命中缓存时也会重新校验标签、情感和原文证据。

标签配置同时规定情感方向：明确的正向标签只接受 `positive`，"希望增加/提供"类标签只接受 `suggestion`，问题类标签接受 `negative` 或 `suggestion`。"其他问题"也可用于中性陈述。模型返回不符合方向的组合时会重试，仍不符合则记录失败。

课程 AI 总结在读取缓存时会重新校验课程、期次和结构化人数与占比；无效缓存会被忽略并重新生成。单期及跨期总结中的数字会按原单位核对，不能把输入中的人数当成天数或小时数使用。

### 自动测试

在项目根目录运行 `python -m pytest -q`。其中 `tests/test_end_to_end_api.py` 会生成脱敏问卷，使用模拟反馈分类器核对三个 API 返回值、报告内容和下载路径，不需要模型密钥。`tests/test_production_model_flow.py` 会用受控模型响应检查默认 DeepSeek 分析器是否接入完整问卷流程。`tests/conftest.py` 将需要真实服务、密钥或手工数据文件的旧脚本排除在自动测试收集之外；这些脚本仍保留在 `tests/` 中供手工检查。

配置好 `.env` 后，可在项目根目录运行 `python -m scripts.smoke_deepseek`，用一条固定、无个人信息的反馈发起一次不使用缓存的真实模型调用。该检查不生成问卷报告；线上 HTTP 部署仍需单独验收。
