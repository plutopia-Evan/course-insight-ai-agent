# 课程问卷智能分析工具 v1.0

批量读取课程问卷 Excel，自动清洗、映射、统计分析，生成多维度分析报告。

## 环境要求

- Python 3.11+
- pandas
- openpyxl
- numpy
- streamlit

## 安装

```cmd
cd D:\course-survey-tool
pip install -r requirements.txt
```

## 目录结构

```
course-survey-tool/
├── app.py                     # Streamlit 网页界面入口
├── main.py                    # 命令行主入口
├── survey_processor.py        # 数据读取、宽转长、题目映射、异常检测
├── statistics.py              # 评分统计计算
├── text_cleaner.py            # 文本反馈清洗
├── output_writer.py           # Excel 输出生成
├── requirements.txt
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

### 方式一：网页界面（推荐）

通过浏览器上传文件、在线查看结果、下载分析报告：

```cmd
cd D:\course-survey-tool
streamlit run app.py
```

如果 `streamlit` 命令未加入 PATH，可使用：

```cmd
cd D:\course-survey-tool
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
cd D:\course-survey-tool
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
