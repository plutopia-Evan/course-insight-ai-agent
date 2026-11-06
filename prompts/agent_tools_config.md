# Course Insight Agent 工具契约

此文件描述当前 FastAPI 的真实输入与输出，供 Dify 或其他客户端配置。接口入口见 api/main_api.py；以服务 OpenAPI 为最终字段依据。

所有接口需要 Authorization: Bearer <SERVICE_API_KEY>。服务地址由部署方配置，本文不提供未经验证的线上地址。

## course_analysis：首次分析

- HTTP：POST /analysis
- Content-Type：multipart/form-data
- 参数：file，一份 .xlsx 问卷文件；不是 JSON file_path，也不是上传平台的文件 URL。
- 能力：读取、清洗、评分统计、有效文本反馈分类、生成 Excel 报告。
- 返回：analysis_id、result_url、download_url、status、course_name、session、统计计数、feedback_errors、feedback_results；另含标准化长表和异常评分明细。
- 限制：10 MB、100 条有效反馈、每条 2000 字符。映射表使用服务端 config/question_mapping.xlsx。
- Dify 兼容入口 POST /dify/analyze 也返回上述通用计数、标识和链接；另外保留 success、feedback_summary、report_path。标准化长表和异常明细仅在 /analysis 中直接返回。

该调用已生成报告，不要再把全量 feedback_analysis 和全量 report_generation 接在后面。

## get_analysis：查询已分析结果

- HTTP：GET /analyses/{analysis_id}
- 参数：首次分析返回的 analysis_id。
- 返回：已有统计、反馈分类、失败信息、result_url 和 download_url。
- 不包含首次 /analysis 的完整标准化长表与异常评分明细；这些可查看原报告。
- 不调用模型，不生成新报告。partial 状态保持原样。
- 分析编号无效，或记录/报告已失效时返回 404。

## report_generation：获取已有报告

- HTTP：POST /generate_report
- Content-Type：application/x-www-form-urlencoded 或 multipart/form-data
- 推荐参数：analysis_id。
- 返回：已有分析信息和同一 download_url；不触发新分析。
- 兼容参数：也可提供 file 首次上传并完整分析。file 与 analysis_id 必须二选一，缺失或同时提供返回 422。
- 已有 download_url 时，可直接 GET 下载，不需要额外调用本工具。

## feedback_analysis：独立新文本

- HTTP：POST /feedback_analysis
- Content-Type：application/json
- 参数示例：{"feedback_texts":["老师讲解清晰，但课程节奏太快"]}
- 返回：意见分类列表、响应/意见/失败计数和状态。
- 用于用户新提交的独立文本，不用于重新处理 course_analysis 已返回的反馈。
- 不创建 analysis_id 或完整问卷报告。

## 正确的调用路径

1. 用户首次上传问卷并要求报告：course_analysis → 展示摘要及 download_url。
2. 用户追问同一份分析：get_analysis(analysis_id) → 基于既有数据回答。
3. 用户要求再下载：直接使用 download_url，或 report_generation(analysis_id)。
4. 用户明确要求重新分析/提交修正文件：创建新分析，更新当前 analysis_id。

相对链接要和实际 API 地址拼接；下载同样需要 Bearer 令牌。Dify 的文件上传适配、工具配置及真实调用轨迹需在目标平台单独验收。

## 状态与持久化

complete 表示该次有效反馈分类没有记录失败；partial 表示有失败项，可查看其余结果和报告。该状态不等同于模型语义准确率。

结果记录保存在 REPORT_OUTPUT_DIR（默认 data/output）的 analyses/ 子目录。必须与 Excel 一起保留；当前是实例本地存储、服务级鉴权。还没有个人账户隔离、跨实例共享或自动过期清理。

## 批量完整分析（新增）

POST /analysis/batch：multipart 的 files 为 1—10 份问卷，可选 mapping 为映射表，可选 enable_ai=true 启用模型；默认仅统计。该入口与网页共用服务，支持课程总结与跨期趋势。返回 analysis_id、result_url、download_url、data_quality_issues 和 ai_tables。后续同样按 analysis_id 复用结果。

原 /analysis 和 /dify/analyze 保持单文件兼容范围。批量 AI 请求最多 100 条有效反馈、每条 2000 字符，上传合计不超过 10 MB。
