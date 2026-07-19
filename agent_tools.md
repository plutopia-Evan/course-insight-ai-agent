

星期六 22:30

是这样吗？什么叫做把映射表放入config



5d611687-7c5c-4f93-8e71-5a94bce2379f.png

ae03f545-2680-4b27-8578-ac0551bf90d4.png

d1247a06-477e-4961-95ee-ad14112ca1a1.png

32cf941e-36a7-42f9-827a-e0db0d35db9c.png

1addf2ad-ba33-417c-a9e5-5f7692d6ddb6.png

就是这样对吗



我这样打开吗



为什么



eed607e2-6da1-4a46-8de0-6d90e5565258.png

6033ff8e-6b69-41a4-886a-1ce75cfe62db.png

e7648acf-04df-438e-8d43-c3ac762126ce.png

这是输出结果



星期日 22:41



README.md

文件



requirements(1).txt

文档

这是刚刚生成的文件



哪一个？



报错



仍报错



c7fe08fe-4732-42e2-81bf-c2e9e63bbabe.png

eb214a7a-0398-47d3-bb5e-aac62674641e.png



app(1).py

Python



requirements(3).txt

文档



README(2).md

文件

情分析上述



25c50350-7b0f-4c80-8858-d1a168636e8d.png

4a2bdfb9-b77a-4fe5-8af0-90b47c78303b.png



app(2).py

Python



statistics.py

Python



survey\_processor.py

Python



0869033d-5e95-49ff-bd78-635558adca0a.xlsx

电子表格

上述为结果



34feaee3-2112-423b-bd31-39662e769807.png

116bea74-2e82-4a43-b94a-b3c1f4e5b3f0.png

a4ee19c7-2672-4e7a-ae76-f0431902d632.png



app(3).py

Python



statistics(1).py

Python



output\_writer(1).py

Python



星期二 15:22



mock\_ai\_feedback\_result.xlsx

电子表格



ai\_feedback\_analyzer.py

Python



feedback\_classification\_prompt.md

文件



feedback\_taxonomy.yaml

文件

以上文件





.env

文件



这样的话得删掉这些，复制你发的，对吗







deepseek\_feedback\_analyzer.py

Python



deepseek\_config.py

Python



test\_deepseek\_feedback.py

Python



deepseek\_feedback\_test\_result.xlsx

电子表格



requirements(4).txt

文档



跳过缓存为什么还这样





ai\_feedback\_statistics.xlsx

电子表格



ai\_feedback\_statistics.py

Python





ai\_summary\_generator.py

Python



ai\_course\_summary.xlsx

电子表格



course\_summary\_prompt.md

文件





ai\_summary\_generator(1).py

Python



course\_summary\_prompt(1).md

文件



ai\_course\_summary(1).xlsx

电子表格





ai\_course\_summary(2).xlsx

电子表格

这是修改完的表格



报错



这是终端







对吗



第一步



测试了







粘贴的文本 (1)(2).txt

文档



修改后页面已出



报错





第二步测试接口是这样的





analysis\_api.py

Python





survey\_processor(1).py

Python



statistics(2).py

Python

如上



这是修改后再运行的结果





deepseek\_feedback\_analyzer(1).py

Python



llm\_feedback\_analyzer.py

Python



这是运行完的结果





output\_writer.py

Python



第三个tool声测会给你的Excel为什么成这样



现在三个 Tool 都已经验证通过，下一阶段我们不要继续写后端代码，而是进入真正的 Agent 编排阶段。



目前你的项目状态：



课程问卷智能分析系统



后端能力：



✅ Tool1：课程数据分析

&#x20;  /analysis



&#x20;  Excel

&#x20;     ↓

&#x20;  survey\_processor

&#x20;     ↓

&#x20;  statistics

&#x20;     ↓

&#x20;  JSON结果





✅ Tool2：反馈智能分析

&#x20;  /feedback\_analysis



&#x20;  文本反馈

&#x20;     ↓

&#x20;  DeepSeek

&#x20;     ↓

&#x20;  问题分类+建议





✅ Tool3：报告生成

&#x20;  /generate\_report



&#x20;  分析结果

&#x20;     ↓

&#x20;  output\_writer

&#x20;     ↓

&#x20;  Excel报告

现在缺少的是：



用户

&#x20;|

&#x20;|

Agent

&#x20;|

&#x20;|

决定调用哪个Tool

&#x20;|

&#x20;|

组合结果

这一步就是你面试中说的：



基于Agent架构，将课程问卷分析能力工具化，通过大模型进行任务规划和工具调用，实现从数据上传、指标分析、反馈理解到报告生成的自动化闭环。



下一阶段：Dify搭建 Course Insight Agent

整体流程：



&#x20;                用户



&#x20;                 |

&#x20;                 ↓



&#x20;       Course Insight Agent



&#x20;                 |

&#x20;      ----------------------

&#x20;      |          |          |

&#x20;      ↓          ↓          ↓



&#x20;  Tool1       Tool2       Tool3



课程分析     反馈分析    报告生成





&#x20;      |

&#x20;      ↓



&#x20; 综合回答用户

第一步：准备三个API接口

现在你的三个接口：



Tool1

地址：



http://127.0.0.1:8000/analysis

输入：



{

&#x20;"file\_path":"xxx.xlsx"

}

Tool2

地址：



http://127.0.0.1:8000/feedback\_analysis

输入：



{

&#x20;"feedback\_texts":\[]

}

Tool3

地址：



http://127.0.0.1:8000/generate\_report

输入：



{

...

}

第二步：不要马上连接Dify

先做一个关键优化：



给三个接口写“工具说明文档”

因为Agent调用工具，不只是知道URL。



它需要知道：



什么时候调用



输入什么



输出什么



例如 Tool1：



名字：



course\_analysis

描述：



用于分析课程问卷Excel文件。



当用户上传课程问卷，需要获取：

\- 学员人数

\- 平均评分

\- 有效评分数量

\- 异常数据数量

时调用。



输入：

file\_path



输出：

课程基础统计指标。

这个就是Agent的Tool Description。



第三步：进入Dify

创建：



Agent应用

名字：



Course Insight AI Agent

系统提示词：



类似：



你是课程运营分析助手。



你的任务：

1\. 分析课程问卷数据

2\. 识别学员反馈问题

3\. 输出课程优化建议

4\. 根据需求生成分析报告



你拥有以下工具：



course\_analysis:

用于课程数据统计。



feedback\_analysis:

用于文本反馈分析。



report\_generation:

用于生成分析报告。



根据用户需求选择工具。

第四步：接入工具

Dify里面：



进入：



工具

&#x20;↓

自定义工具

&#x20;↓

OpenAPI导入

导入：



FastAPI自动生成的：



http://127.0.0.1:8000/openapi.json

Dify会自动识别：



POST /analysis



POST /feedback\_analysis



POST /generate\_report

然后生成工具。



第五步：测试Agent

输入：



例如：



请分析产品经理训练营第01期课程效果，并总结学员反馈问题



理想流程：



Agent：



发现需要课程数据

↓

调用analysis



得到：



评分4.6

学生32

异常10





发现需要反馈分析

↓

调用feedback\_analysis



得到：



案例不足

希望增加实战





需要报告

↓

调用generate\_report



生成Excel

最终回复：



课程整体满意度较高。



优势：

1\. 教师讲解清晰



问题：

1\. 案例不足

2\. 实战环节不足



建议：

增加企业案例和项目练习。



报告已生成。

但是这里有一个现实问题

你的FastAPI现在运行：



127.0.0.1

只能自己电脑访问。



Dify云端无法访问。



所以后面需要：



方案：



方案A（推荐学习）

部署到：



阿里云



腾讯云



Railway



Render



得到：



https://xxx.com/analysis

Dify调用。



方案B

本地测试：



使用：



ngrok

暴露：



localhost:8000

生成公网URL。



所以现在你的下一步不是代码。



按顺序：



Step 1

整理三个API的OpenAPI文档



Step 2

本地用Dify接入测试



Step 3

解决公网访问



Step 4

完成Agent Workflow



你现在已经完成了一个很重要的阶段：



从：



Python数据分析项目



升级到了：



具有三个业务Tool能力的AI Agent后端。



下一步我们开始做 Dify Agent搭建。我建议先不用部署云端，先用你本机+ngrok跑通完整Agent链路。





我没有ngrok，只能用coze或者dify。然后我现在也只是写了course\_analysis的工具说明文档，其他两个tool的说明文档你也给我发一下



可以。你现在没有 ngrok 也没关系，当前阶段不需要马上接入公网。



因为你现在是本地开发验证阶段，可以有两个路线：



Dify 本地/私有部署接入（推荐后期）



Coze通过自定义插件/HTTP工具调用（需要公网地址）



目前你的 FastAPI：



http://127.0.0.1:8000

只能你的电脑访问。



所以现在建议：



先把 Agent 的工具定义、输入输出、调用逻辑设计完整。



等全部跑通后，再处理部署。



你已经有 Tool1：



Tool 1：course\_analysis

下面给你 Tool2 和 Tool3 的工具说明文档。



Tool2：feedback\_analysis

工具名称

feedback\_analysis

工具描述（直接复制到Dify/Coze）

用于对课程学员开放式反馈文本进行智能分析。



当用户需要了解：

\- 学员对课程的具体评价

\- 高频问题

\- 课程优势

\- 课程不足

\- 优化建议



时调用该工具。



该工具基于大语言模型对反馈文本进行结构化分析，包括：

1\. 反馈分类

2\. 情感倾向判断

3\. 问题归因

4\. 关键观点提取

5\. 优化建议生成



输入：

feedback\_texts



类型：

Array\[String]



表示多条课程学员反馈文本。



输出：

结构化反馈分析结果，包括：

\- feedback\_count：分析反馈数量

\- category：反馈所属类别

\- subcategory：具体问题分类

\- sentiment：情感倾向

\- summary：问题总结

\- evidence：原始反馈依据



适用场景：

\- 课程满意度分析

\- 学员反馈洞察

\- 教学质量优化

\- 课程运营分析

参数定义

输入参数：



字段	类型	说明

feedback\_texts	Array\[String]	需要分析的课程反馈文本列表

示例：



{

&#x20;"feedback\_texts":\[

&#x20;  "老师讲解非常清晰",

&#x20;  "希望增加更多项目案例",

&#x20;  "课程节奏稍快"

&#x20;]

}

输出示例

{

&#x20;"feedback\_count":3,

&#x20;"analysis":\[

&#x20;  {

&#x20;   "category":"讲师表现",

&#x20;   "subcategory":"讲解清晰",

&#x20;   "sentiment":"positive",

&#x20;   "summary":"认可教师授课能力",

&#x20;   "evidence":"老师讲解非常清晰"

&#x20;  },

&#x20;  {

&#x20;   "category":"实操与案例",

&#x20;   "subcategory":"案例不足",

&#x20;   "sentiment":"negative",

&#x20;   "summary":"希望增加项目案例",

&#x20;   "evidence":"希望增加更多项目案例"

&#x20;  }

&#x20;]

}

Tool3：report\_generation

工具名称

report\_generation

工具描述（直接复制）

用于根据课程分析结果和反馈分析结果自动生成完整课程分析报告。



当用户需要：

\- 生成课程运营分析报告

\- 导出Excel分析结果

\- 保存课程评估结果

\- 输出管理层汇报材料



时调用该工具。



该工具将多个分析模块结果整合，并生成结构化Excel报告。



报告内容包括：

1\. 数据总览

2\. 文件识别结果

3\. 题目映射结果

4\. 评分统计

5\. 课程公共题分析

6\. 单期特色题分析

7\. 开放式反馈分析

8\. 异常数据记录

9\. 待人工确认数据



输入：

\- course\_name：课程名称

\- session：课程期次

\- overview：课程整体指标

\- feedback\_analysis：AI反馈分析结果



输出：

\- status：生成状态

\- file\_path：生成报告文件路径



适用场景：

\- 自动生成课程复盘报告

\- 教学运营分析

\- 培训效果评估

\- 课程优化决策支持

参数定义

输入：



字段	类型	说明

course\_name	string	课程名称

session	string	课程期次

overview	object	课程统计结果

feedback\_analysis	array	反馈分析结果

示例：



{

"course\_name":"产品经理训练营",



"session":"第01期",



"overview":{

&#x20;"student\_count":32,

&#x20;"average\_score":4.56,

&#x20;"valid\_rating\_count":150

},



"feedback\_analysis":\[

&#x20;{

&#x20; "problem":"案例不足",

&#x20; "suggestion":"增加企业案例"

&#x20;}

]

}

输出：



{

&#x20;"status":"success",

&#x20;"file\_path":

&#x20;"data/output/产品经理训练营\_分析报告.xlsx"

}

现在你的 Agent Tool 设计就是：

Course Insight Agent



&#x20;       |

&#x20;       |

&#x20;----------------------------

&#x20;|             |             |

&#x20;↓             ↓             ↓



course\_     feedback\_    report\_

analysis    analysis     generation





课程指标     反馈洞察      报告生成

下一步建议

现在不要急着连接 Dify。



你下一步应该做：



第一步

整理一个：



agent\_tools.md

里面包含：



Tool名称



描述



输入



输出



调用条件



这个在面试中非常有价值。



第二步

优化 Tool3。



目前 Tool3 只是：



JSON → Excel

后面应该升级为：



file\_path

&#x20;   ↓

自动调用Tool1

&#x20;   ↓

自动调用Tool2

&#x20;   ↓

自动生成报告

这样才是真正Agent。



第三步

再接 Dify。



因为 Dify Agent 最重要的是：



不是写代码，而是：



让大模型知道什么时候调用哪个工具。



你现在三个工具能力已经基本齐了。下一阶段就是 Agent 编排设计。





好，按你的步骤来



md格式文档如何创建



创建 .md 文件非常简单，本质上就是创建一个纯文本文件，只是后缀改成 .md。



你现在是在 Windows + course-survey-tool 项目中操作，我建议用下面两种方式之一。



方法一（推荐）：VS Code 创建

你之前应该已经打开项目目录。



第一步

在 VS Code 左侧找到：



course-survey-tool

右键：



New File（新建文件）

第二步

输入文件名：



agent\_tools.md

注意：



必须是：



agent\_tools.md

不是：



agent\_tools.md.txt

第三步

打开文件。



把我刚刚给你的内容复制进去。



例如第一行：



\# Course Insight Agent Tools

保存：



Ctrl + S

完成。



方法二：Windows资源管理器创建

如果不用VS Code：



进入：



D:\\course-survey-tool

空白处：



右键：



新建

→ 文本文档

生成：



新建文本文档.txt

改名：



agent\_tools.md

Windows会提示：



确定要改变文件扩展名吗？



点击：



是

然后用记事本打开，粘贴内容。



方法三：终端创建（适合开发）

进入项目目录：



cd D:\\course-survey-tool

输入：



ni agent\_tools.md

会创建：



agent\_tools.md

然后：



notepad agent\_tools.md

打开编辑。



创建完成后，你的目录应该变成：

course-survey-tool



│  agent\_tools.md   ⭐新增

│

├─api

│  ├─analysis\_api.py

│  ├─feedback\_api.py

│  └─report\_api.py

│

├─data

│

├─config

│

├─survey\_processor.py

├─statistics.py

├─output\_writer.py

建议你现在用 VS Code 创建

原因：



后面我们还会创建：



agent\_prompt.md

architecture.md

README\_agent.md

这些都是项目文档。



统一用 VS Code 管理更方便。



你创建完成后，不需要发整个文件内容。



直接发：



左侧目录截图，确认：



agent\_tools.md

存在。



然后我们进入下一步：



Step 2：优化三个 Tool 接口，让它们符合真正 Agent 调用规范。





fece8030-f052-4ede-907e-908e5a19785d.png

我就这样吗？这是全部的md里的内容吗？



对，你现在这个操作方向是对的。



但是从你截图来看，这不是完整的 agent\_tools.md 内容，应该只是你复制进去的一部分（目前看到的是 Tool1 的后半部分）。



你现在文件内容应该从第一行开始完整包含：



\# Course Insight Agent Tools

然后依次：



项目介绍



Tool 1：course\_analysis



Tool 2：feedback\_analysis



Tool 3：report\_generation



Agent调用逻辑



你截图里面目前停留的位置：



\## 调用场景



当用户：



\- 上传课程问卷Excel

\- 询问课程满意度

\- 需要查看课程评分

\- 需要统计学员规模



调用该工具。





\## Input

说明：



你已经写到了：



Tool1 → 调用场景 → Input

这部分没有问题。



但是后面还应该继续有：



Tool1 Output

例如：



\## Output



```json

{

&#x20;"course\_name":"产品经理训练营",

&#x20;"session":"第01期",

&#x20;"student\_count":32,

&#x20;"rating\_total":160,

&#x20;"valid\_rating\_count":150,

&#x20;"feedback\_count":32,

&#x20;"anomaly\_count":10

}



\---



然后继续：



\# Tool 2：feedback\_analysis



内容：



```markdown

\## 功能描述



课程反馈智能分析工具。



基于大语言模型，对开放式反馈文本进行理解。



分析：



\- 情感判断

\- 问题分类

\- 高频问题识别

\- 优化建议生成

然后：



Tool 3：report\_generation

最后：



Agent调用逻辑

所以你的当前状态：



✅ 文件创建正确

✅ markdown格式正确

✅ Tool1已经开始写入



现在不要保存成其他格式。



确认文件名：



顶部标签那里显示：



应该是：



agent\_tools.md

不要是：



agent\_tools.md.txt

你现在做两件事：



第一步

按 Ctrl + End



跳到文件最后。



看一下是否还有内容。



如果没有，就继续粘贴剩余部分。



第二步

建议在最顶部检查一下：



第一行是否：



\# Course Insight Agent Tools

如果没有，加上。



完成后，你可以直接截图整个文件目录或者顶部第一行，我确认一下。



然后进入下一步：



Step 2：优化 Tool 接口（把三个API改造成真正Agent可调用的形式）。





\# Course Insight Agent Tools





\## 项目名称



Course Insight AI Agent



课程问卷智能分析与运营洞察 Agent





\---



\# Tool 1：course\_analysis





\## 功能描述



课程数据分析工具。



用于解析课程问卷 Excel 文件，

自动完成：



\- 文件识别

\- 课程信息提取

\- 题目映射

\- 评分统计

\- 异常数据检测



输出课程整体表现指标。





\## 调用场景



当用户：



\- 上传课程问卷Excel

\- 询问课程满意度

\- 需要查看课程评分

\- 需要统计学员规模



调用该工具。





\## Input



json

{

&#x20;"file\_path":"课程问卷路径"

}



\## Output

json

{

&#x20;"course\_name":"产品经理训练营",

&#x20;"session":"第01期",

&#x20;"student\_count":32,

&#x20;"rating\_total":160,

&#x20;"valid\_rating\_count":150,

&#x20;"feedback\_count":32,

&#x20;"anomaly\_count":10

}



\#Tool 2：feedback\_analysis

\##功能描述



课程反馈智能分析工具。



基于大语言模型，对开放式反馈文本进行理解。



分析内容：



情感判断

问题分类

高频问题识别

优化建议生成



\##调用场景



当用户：



想知道学生为什么满意/不满意

需要分析课程问题

需要提取优化建议



调用该工具。



\##Input

{

&#x20;"feedback\_texts":\[

&#x20;   "反馈1",

&#x20;   "反馈2"

&#x20;]

}



\## Output

{

&#x20;"feedback\_count":2,



&#x20;"analysis":\[



&#x20;{

&#x20;"category":"实操与案例",

&#x20;"subcategory":"案例不足",

&#x20;"sentiment":"negative",

&#x20;"summary":"案例数量不足",

&#x20;"evidence":"案例太少"

&#x20;}



&#x20;]



}



\#Tool 3：report\_generation

\##功能描述



课程分析报告生成工具。



根据分析结果自动生成：



Excel分析报告

课程复盘材料

\##调用场景



当用户：



需要下载分析报告

需要输出课程复盘文件

需要形成管理汇报材料



调用该工具。



\## Input

{



"course\_name":"产品经理训练营",



"session":"第01期",



"overview":{},



"feedback\_analysis":\[]



}



\## Output

{



"status":"success",



"file\_path":

"data/output/report.xlsx"



}























&#x20;这是md文档内容，你看如何



整体方向是正确的，你已经完成了 Agent Tool 文档化的主体内容。但是这个 Markdown 文档目前有几个格式问题，建议现在修正，否则后续放 GitHub、导入知识库或者作为项目文档展示时不够规范。



主要有 4 个问题：



1\. JSON代码块没有闭合（最重要）

你这里：



\## Input



```json

{

&#x20;"file\_path":"课程问卷路径"

}



\## Output

问题：



你打开了：



```json

但是没有关闭：





所以 Markdown 会认为后面的内容都是 JSON。



正确：



```markdown

\## Input



```json

{

&#x20;"file\_path":"课程问卷路径"

}

Output

{

&#x20;"course\_name":"产品经理训练营",

&#x20;"session":"第01期",

&#x20;"student\_count":32,

&#x20;"rating\_total":160,

&#x20;"valid\_rating\_count":150,

&#x20;"feedback\_count":32,

&#x20;"anomaly\_count":10

}



\---



\## 2. 标题格式不规范



你现在：



```markdown

\#Tool 2：feedback\_analysis

Markdown标准：



\# 后面需要空格。



改：



\# Tool 2：feedback\_analysis

同理：



\##功能描述

改：



\## 功能描述

所有：



\##调用场景

\##Input

\##Output

都建议改。



3\. Tool 2、Tool 3 缺少代码块

例如：



现在：



\##Input

{

&#x20;"feedback\_texts":\[

&#x20;   "反馈1",

&#x20;   "反馈2"

&#x20;]

}

虽然能看懂，但是不是标准 Markdown。



应该：



\## Input



```json

{

&#x20;"feedback\_texts":\[

&#x20;   "反馈1",

&#x20;   "反馈2"

&#x20;]

}



\---



Tool3：



改：



```markdown

\## Input



```json

{

&#x20;"course\_name":"产品经理训练营",

&#x20;"session":"第01期",

&#x20;"overview":{},

&#x20;"feedback\_analysis":\[]

}



\---



\## 4. 最后缺少 Agent 调用流程



现在你的文档到：



```markdown

Tool3 Output

结束。



但是对于 Agent 项目来说，最重要的是：



Agent什么时候调用哪个Tool。



建议最后增加：



\---



\# Agent调用逻辑





用户上传课程问卷Excel



↓



调用 course\_analysis



↓



获取课程评分、学生规模、异常数据



↓



调用 feedback\_analysis



↓



分析学生反馈、发现课程问题



↓



调用 report\_generation



↓



生成课程分析报告



修改后整体评价

现在版本：



部分	状态

项目名称	✅

Tool1说明	✅

Tool2说明	✅

Tool3说明	✅

输入输出定义	✅

Agent调用逻辑	缺少

Markdown规范	需要修正

目前完成度：



80%左右。



修正之后，这个文件就可以作为：



GitHub项目文档 ✅



面试项目附件 ✅



Dify Agent设计说明 ✅



AI产品经理项目沉淀文档 ✅



你现在不要重新写。



直接做三个修改：



所有 #Tool 改成 # Tool



补齐所有 ```json 的结束符



最后增加 Agent调用逻辑



修改完成后，我们进入 Step 2：优化三个 Tool 接口。



这一步会让你的项目从：



“三个独立API”



变成：



“真正可以被Agent调用的业务工具”。





根据错误，你重新生成一版



根据刚才的问题，我重新整理一版完整、规范、可直接复制到 agent\_tools.md 的 Markdown 文档。



这版修复了：



✅ JSON代码块未闭合问题



✅ #Tool 标题格式问题



✅ ##功能描述 格式问题



✅ Tool2、Tool3 缺少代码块问题



✅ 增加 Agent 调用逻辑



✅ 增加输入输出规范



✅ 适合作为项目文档/面试材料



你直接全部删除当前 md 内容，然后复制下面这一版。



\# Course Insight Agent Tools





\## 项目名称



Course Insight AI Agent



课程问卷智能分析与运营洞察 Agent





\---



\# Tool 1：course\_analysis





\## 功能描述



课程数据分析工具。



用于解析课程问卷 Excel 文件，

自动完成：



\- 文件识别

\- 课程信息提取

\- 题目映射

\- 评分统计

\- 异常数据检测



输出课程整体表现指标。





\## 调用场景



当用户：



\- 上传课程问卷 Excel

\- 询问课程满意度

\- 需要查看课程评分

\- 需要统计学员规模



调用该工具。





\## Input



```json

{

&#x20; "file\_path":"课程问卷路径"

}

Output

{

&#x20; "course\_name":"产品经理训练营",

&#x20; "session":"第01期",

&#x20; "student\_count":32,

&#x20; "rating\_total":160,

&#x20; "valid\_rating\_count":150,

&#x20; "feedback\_count":32,

&#x20; "anomaly\_count":10

}

Tool 2：feedback\_analysis

功能描述

课程反馈智能分析工具。



基于大语言模型，对课程开放式反馈文本进行分析。



主要完成：



情感倾向判断



反馈类别识别



问题归因分析



高频问题发现



优化建议生成



调用场景

当用户：



想了解学生满意或不满意原因



需要分析课程问题



需要提取优化方向



需要总结学员反馈



调用该工具。



Input

{

&#x20; "feedback\_texts":\[

&#x20;   "老师讲解非常清晰",

&#x20;   "希望增加更多项目案例"

&#x20; ]

}

Output

{

&#x20; "feedback\_count":2,

&#x20; "analysis":\[

&#x20;   {

&#x20;     "category":"讲师表现",

&#x20;     "subcategory":"讲解清晰",

&#x20;     "sentiment":"positive",

&#x20;     "summary":"认可教师授课能力",

&#x20;     "evidence":"老师讲解非常清晰"

&#x20;   },

&#x20;   {

&#x20;     "category":"实操与案例",

&#x20;     "subcategory":"案例不足",

&#x20;     "sentiment":"negative",

&#x20;     "summary":"案例数量不足",

&#x20;     "evidence":"希望增加更多项目案例"

&#x20;   }

&#x20; ]

}

Tool 3：report\_generation

功能描述

课程分析报告生成工具。



根据课程分析结果和反馈分析结果，

自动生成完整课程分析报告。



报告包含：



数据总览



文件识别结果



课程评分统计



题目映射结果



公共题分析



单期特色题分析



开放式反馈分析



异常数据记录



调用场景

当用户：



需要下载课程分析报告



需要生成课程复盘材料



需要输出管理汇报文件



需要保存分析结果



调用该工具。



Input

{

&#x20; "course\_name":"产品经理训练营",

&#x20; "session":"第01期",

&#x20; "overview":{

&#x20;   "student\_count":32,

&#x20;   "average\_score":4.56

&#x20; },

&#x20; "feedback\_analysis":\[

&#x20;   {

&#x20;     "problem":"案例不足",

&#x20;     "suggestion":"增加企业案例"

&#x20;   }

&#x20; ]

}

Output

{

&#x20; "status":"success",

&#x20; "file\_path":"data/output/report.xlsx"

}

Agent调用逻辑

用户提出课程分析需求：



例如：



分析产品经理训练营第01期课程效果，并生成优化建议。



Agent执行流程：



Step 1：课程数据分析

调用：



course\_analysis



输入：



课程问卷 Excel 文件。



输出：



学员数量



平均评分



有效评分数量



异常数据数量



↓



Step 2：反馈智能分析

调用：



feedback\_analysis



输入：



课程开放式反馈文本。



输出：



课程优势



学员问题



情感倾向



优化建议



↓



Step 3：生成分析报告

调用：



report\_generation



输入：



课程指标 + 反馈分析结果。



输出：



完整课程分析报告文件。



Agent整体架构

&#x20;                Course Insight Agent





&#x20;                        |

&#x20;                        |



&#x20;       ---------------------------------



&#x20;       |               |               |



&#x20;       ↓               ↓               ↓





&#x20;course\_analysis   feedback\_analysis   report\_generation





&#x20;       |               |               |



&#x20;       ↓               ↓               ↓





&#x20;Excel分析        DeepSeek分析       Excel报告生成



Tool调用原则

用户上传课程问卷文件：



调用 course\_analysis。



用户询问课程问题原因：



调用 feedback\_analysis。



用户要求生成报告：



调用 report\_generation。



用户同时需要课程表现和优化建议：



按照：



course\_analysis



↓



feedback\_analysis



↓



report\_generation



顺序执行。





\---



复制完成后，你的 `agent\_tools.md` 就可以作为正式项目文档。



下一步进入 \*\*Step 2：优化三个 Tool 接口\*\*。



主要改两个地方：



1\. `feedback\_analysis` 增加：

&#x20;  - course\_name

&#x20;  - session

&#x20;  - respondent\_id



让反馈结果可以关联课程。



2\. `report\_generation` 改造成：

&#x20;  - 输入 Excel 文件路径

&#x20;  - 自动调用分析流程



这样三个 Tool 才是真正的 Agent Tool，而不是三个独立 API。



直接生辰记事本，发给我



已生成 agent\_tools.md 文件。



你可以点击下载：



agent\_tools.md



这个版本已经修复了之前的问题：



Markdown标题格式规范



JSON代码块闭合



Tool1/Tool2/Tool3结构统一



增加Agent调用逻辑



可直接作为项目文档、GitHub说明、面试材料使用



下一步继续按照计划进入 Step 2：优化三个 Tool 接口。主要目标是：



feedback\_analysis 增加课程上下文（课程名、期次），让反馈分析结果可追溯；



report\_generation 从“接收分析结果生成Excel”升级为“输入文件自动完成分析并生成报告”，使其更符合真正 Agent Tool 设计。 





库

/

agent\_tools.md





\# Course Insight Agent Tools



\## 项目名称



Course Insight AI Agent



课程问卷智能分析与运营洞察 Agent



\------------------------------------------------------------------------



\# Tool 1：course\_analysis



\## 功能描述



课程数据分析工具。



用于解析课程问卷 Excel 文件，自动完成：



\-   文件识别

\-   课程信息提取

\-   题目映射

\-   评分统计

\-   异常数据检测



输出课程整体表现指标。



\## 调用场景



当用户： - 上传课程问卷 Excel - 询问课程满意度 - 需要查看课程评分 -

需要统计学员规模



调用该工具。



\## Input



``` json

{

&#x20; "file\_path":"课程问卷路径"

}

```



\## Output



``` json

{

&#x20; "course\_name":"产品经理训练营",

&#x20; "session":"第01期",

&#x20; "student\_count":32,

&#x20; "rating\_total":160,

&#x20; "valid\_rating\_count":150,

&#x20; "feedback\_count":32,

&#x20; "anomaly\_count":10

}

```



\------------------------------------------------------------------------



\# Tool 2：feedback\_analysis



\## 功能描述



课程反馈智能分析工具。



基于大语言模型，对课程开放式反馈文本进行分析。



主要完成：



\-   情感倾向判断

\-   反馈类别识别

\-   问题归因分析

\-   高频问题发现

\-   优化建议生成



\## 调用场景



当用户： - 想了解学生满意或不满意原因 - 需要分析课程问题 -

需要提取优化方向 - 需要总结学员反馈



调用该工具。



\## Input



``` json

{

&#x20; "feedback\_texts":\[

&#x20;   "老师讲解非常清晰",

&#x20;   "希望增加更多项目案例"

&#x20; ]

}

```



\## Output



``` json

{

&#x20; "feedback\_count":2,

&#x20; "analysis":\[

&#x20;   {

&#x20;     "category":"讲师表现",

&#x20;     "subcategory":"讲解清晰",

&#x20;     "sentiment":"positive",

&#x20;     "summary":"认可教师授课能力",

&#x20;     "evidence":"老师讲解非常清晰"

&#x20;   }

&#x20; ]

}

```



\------------------------------------------------------------------------



\# Tool 3：report\_generation



\## 功能描述



课程分析报告生成工具。



根据课程分析结果和反馈分析结果，自动生成完整课程分析报告。



报告包含：



\-   数据总览

\-   文件识别结果

\-   课程评分统计

\-   题目映射结果

\-   公共题分析

\-   开放式反馈分析

\-   异常数据记录



\## 调用场景



当用户： - 需要下载课程分析报告 - 需要生成课程复盘材料 -

需要输出管理汇报文件



调用该工具。



\## Input



``` json

{

&#x20; "course\_name":"产品经理训练营",

&#x20; "session":"第01期",

&#x20; "overview":{},

&#x20; "feedback\_analysis":\[]

}

```



\## Output



``` json

{

&#x20; "status":"success",

&#x20; "file\_path":"data/output/report.xlsx"

}

```



\------------------------------------------------------------------------



\# Agent调用逻辑



用户提出课程分析需求：



1\.  调用 course\_analysis 获取课程基础指标。

2\.  调用 feedback\_analysis 分析学生反馈。

3\.  调用 report\_generation 生成最终报告。



\------------------------------------------------------------------------



\# Agent整体架构



Course Insight Agent



用户 ↓ Agent ↓ course\_analysis / feedback\_analysis / report\_generation ↓

课程数据分析 + DeepSeek反馈分析 + 报告生成



\------------------------------------------------------------------------



\# Tool调用原则



\-   上传课程问卷文件：调用 course\_analysis。

\-   分析课程问题原因：调用 feedback\_analysis。

\-   生成课程报告：调用 report\_generation。

库

/

agent\_tools.md





\# Course Insight Agent Tools



\## 项目名称



Course Insight AI Agent



课程问卷智能分析与运营洞察 Agent



\------------------------------------------------------------------------



\# Tool 1：course\_analysis



\## 功能描述



课程数据分析工具。



用于解析课程问卷 Excel 文件，自动完成：



\-   文件识别

\-   课程信息提取

\-   题目映射

\-   评分统计

\-   异常数据检测



输出课程整体表现指标。



\## 调用场景



当用户： - 上传课程问卷 Excel - 询问课程满意度 - 需要查看课程评分 -

需要统计学员规模



调用该工具。



\## Input



``` json

{

&#x20; "file\_path":"课程问卷路径"

}

```



\## Output



``` json

{

&#x20; "course\_name":"产品经理训练营",

&#x20; "session":"第01期",

&#x20; "student\_count":32,

&#x20; "rating\_total":160,

&#x20; "valid\_rating\_count":150,

&#x20; "feedback\_count":32,

&#x20; "anomaly\_count":10

}

```



\------------------------------------------------------------------------



\# Tool 2：feedback\_analysis



\## 功能描述



课程反馈智能分析工具。



基于大语言模型，对课程开放式反馈文本进行分析。



主要完成：



\-   情感倾向判断

\-   反馈类别识别

\-   问题归因分析

\-   高频问题发现

\-   优化建议生成



\## 调用场景



当用户： - 想了解学生满意或不满意原因 - 需要分析课程问题 -

需要提取优化方向 - 需要总结学员反馈



调用该工具。



\## Input



``` json

{

&#x20; "feedback\_texts":\[

&#x20;   "老师讲解非常清晰",

&#x20;   "希望增加更多项目案例"

&#x20; ]

}

```



\## Output



``` json

{

&#x20; "feedback\_count":2,

&#x20; "analysis":\[

&#x20;   {

&#x20;     "category":"讲师表现",

&#x20;     "subcategory":"讲解清晰",

&#x20;     "sentiment":"positive",

&#x20;     "summary":"认可教师授课能力",

&#x20;     "evidence":"老师讲解非常清晰"

&#x20;   }

&#x20; ]

}

```



\------------------------------------------------------------------------



\# Tool 3：report\_generation



\## 功能描述



课程分析报告生成工具。



根据课程分析结果和反馈分析结果，自动生成完整课程分析报告。



报告包含：



\-   数据总览

\-   文件识别结果

\-   课程评分统计

\-   题目映射结果

\-   公共题分析

\-   开放式反馈分析

\-   异常数据记录



\## 调用场景



当用户： - 需要下载课程分析报告 - 需要生成课程复盘材料 -

需要输出管理汇报文件



调用该工具。



\## Input



``` json

{

&#x20; "course\_name":"产品经理训练营",

&#x20; "session":"第01期",

&#x20; "overview":{},

&#x20; "feedback\_analysis":\[]

}

```



\## Output



``` json

{

&#x20; "status":"success",

&#x20; "file\_path":"data/output/report.xlsx"

}

```



\------------------------------------------------------------------------



\# Agent调用逻辑



用户提出课程分析需求：



1\.  调用 course\_analysis 获取课程基础指标。

2\.  调用 feedback\_analysis 分析学生反馈。

3\.  调用 report\_generation 生成最终报告。



\------------------------------------------------------------------------



\# Agent整体架构



Course Insight Agent



用户 ↓ Agent ↓ course\_analysis / feedback\_analysis / report\_generation ↓

课程数据分析 + DeepSeek反馈分析 + 报告生成



\------------------------------------------------------------------------



\# Tool调用原则



\-   上传课程问卷文件：调用 course\_analysis。

\-   分析课程问题原因：调用 feedback\_analysis。

\-   生成课程报告：调用 report\_generation。

