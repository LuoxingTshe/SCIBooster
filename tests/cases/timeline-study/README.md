# TimelineStudy：本地案例

来源为EssayI截至2026-10-07的研究快照。它包含研究输入、来源记录和已有功能重构，可作为skill使用案例与回归测试材料。

## 材料层次

|位置|性质|
|---|---|
|input/original/conversation.json|早期研究聊天，是研究意图和讨论来源，不是文献证据|
|input/original/timeline-original.txt|最初时间线文字；年代和论断仍需核验|
|input/original/structured-draft-before-verification.json|核验前结构草案，保留历史状态|
|input/data/timeline-revised.json|当前73条综合视图，含既有分析标签与有限形式解读|
|input/data/pre-mcharg-nodes.json|22条早期历史节点及其证据限制|
|input/data/references.json、claims.json、models.json|书目、论断审计与模型模板；模板不等于逐论文提取|
|input/data/doi-verification-2026-10-07/|41条DOI支持记录、审计报告与离线Zotero队列|
|input/forward-test.json|9节点的有限内容和证据，不含既有formal_reading或axis|
|expected/timeline-functional.json|73条旧功能重构；比较基线，不是独立金标准|
|expected/TIMELINE_FUNCTIONAL.md|逐节点阅读稿，含未知和不适用项|
|expected/TIMELINE_SYNTHESIS.md|当前时间线的综合解释|
|expected/figures/|73节点时间线PNG、SVG及节点标签|
|SOURCE_MANIFEST.json|复制文件与原项目路径、SHA-256对应关系|

## 如何测试

**转换测试**：让agent只读取skill和input/forward-test.json，生成新的功能记录与说明。输出独立保存；不在转换期间读取expected或EVALUATION.md。测试输入已有有限来源转述，也不等于完全未经整理的原始论文。

**结果评估**：完成输出后再读EVALUATION.md。比较证据状态、缺失处理、结构差异及决策/反馈边界，不要求文字逐字匹配。

**旧结果复现**：replay_baseline.py使用冻结的逐节点设定和线索模板，输出到指定新目录。用于检验包的可移动性和原有结果复现；它不验证skill在新输入上的学术判断能力。

**已有数据校验**：运行包根目录README中的validate_profiles.py与tools/check_case.py。结构完整与来源不变检查不证明内容正确。

## 证据边界

没有论文PDF或全文附件随包提供。所有73条记录的全文通读标记保留为false，部分证据仅为摘要或元数据。20条context/meta节点不计算为已抽取的景观评价模型；H17仍待核。73是记录数，不是方法家族数。

已有基线常以通用线索描述补齐重构字段，原文精确输入、量纲、参数来源、h及实际反馈仍有缺失。该事实是测试案例的重要条件，不应通过再运行脚本消除。更强的框架效度与“结构多样性较小”命题仍需独立全文编码和比较实验。
