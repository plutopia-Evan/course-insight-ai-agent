# 质量评测

仓库目前没有真实人工金标准。examples/ 是人工编写的合成演示，预测故意包含漏拆和否定误判，用于说明评分器，不代表 DeepSeek 的真实表现。

## 不调用模型的演示

```text
python -m evaluation.evaluate --gold evaluation/examples/gold.synthetic.jsonl --predictions evaluation/examples/predictions.synthetic.jsonl --output data/output/evaluation-demo.json
```

报告显示数据来源、失败率、意见级 Precision/Recall/F1、一级/二级分类与反馈类型的 Micro/Macro-F1、原文引用合法率及错误案例。缺失预测、失败和重复输出不会从评测中消失；匹配采用原文证据跨度 IoU >= 0.5 的一对一最大匹配。该规则只是自动匹配近似，不能替代人工语义审核。

## 准备真实数据

每行一个 JSON 对象，含 id、source=real、split=dev/test、text、items。items 包含 category、subcategory、sentiment 和原文 evidence。原文重复出现的证据可提供 evidence_start 指定位置。编号必须唯一。

1. 对反馈脱敏；原始业务数据与预测结果保存在被 Git 忽略的 data/ 目录，不提交公开仓库。
2. 两位标注者独立拆意见、定标签、选证据，再讨论分歧。
3. 定义标签边界，例如“课程内容重复”属于课程内容，“跟不上已有基础要求”优先归入课程难度；含糊反馈保留人工备注，不以猜测补全。
4. dev 用于调提示词，test 用于最终检验。同文和近重复文本不得跨集合，尽量按课程/期次留出检验样本。
5. 保存标签配置、提示词和模型版本。人工另外检查证据是否真正支持标签、总结是否遗漏、建议是否可执行。

## 真实调用（需独立配置模型）

```text
python -m evaluation.predict --dataset data/input/gold.test.jsonl --output data/output/predictions.test.jsonl --allow-api
python -m evaluation.evaluate --gold data/input/gold.test.jsonl --predictions data/output/predictions.test.jsonl --output data/output/evaluation.test.json
```

预测文件不覆盖已有文件，关闭分类缓存，不自动重跑失败样本。--allow-api 明确允许该次真实模型调用。报告记录输入文件哈希；应另行记录模型版本、提示词版本和业务样本组成。
