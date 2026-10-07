# 本轮核验方法与复核入口
日期：2026-09-25；研究对象是当前聊天与其附件，非开放式穷尽综述。

## 来源取得
read_thread 返回8轮、hasMore=false、nextCursor=null；每项最大文本上限20000字符，最长返回助手文本13612字符。最后一轮只有用户的制图请求，未取得对应助手图或回答，不推定其存在。
conversation.json 为返回快照；timeline-original.txt 为工具返回附件的内容副本。用户原始 AGENTS.md 与 sources/ 未作修改。

## 检索过程
先按作者/年份/题名寻找出版社记录，再检索作者机构库或作者上传的原文。主要核查：书目身份、出版与上线年份、样本数、方法功能、可接受的表述边界。
下列为本轮检索词组的代表性摘录，不是可复现的系统综述查询协议，也不是完整浏览历史：

- Hopkins 1977 Methods for Generating Land Suitability Maps taxonomy
- Zube Sell Taylor 1982 Landscape perception 160
- Malczewski 2006 GIS based multicriteria decision analysis 319
- Cinelli 2020 taxonomy multiple criteria decision analysis process
- FAO 1976 framework land evaluation
- Yager 1988 ordered weighted averaging
- SMAA 1998 / SMAA-2 2001
- Sensitivity Analysis in Multicriteria Spatial Decision-Making 2004 28
- Spatially-explicit integrated uncertainty and sensitivity 2014
- collaborative spatial multicriteria 2020 / deliberative spatial planning 2021
- Seresinhe Preis Moat 2017 beauty outdoor places
- landscape land cover 2021 interpretable AI
- Zotero CSL JSON / Web API v3

所有实际采用入口、检视位置、证据范围见 references.json / claims.json；出版商索引摘要也可能在open时403或失败，故区分 indexed_excerpt、abstract、fulltext_sections 和 primary_access_unavailable。
没有把搜索排序当成文献重要性或起源证据。没有用商业聚合站的AI摘要替代原文内容证据；R29保留候选状态。书目年份优先使用卷期引用年份，早期在线出版另存。

## 仍需下一轮的内容
精确论文页码、具体模型全文编码、全文版本/撤稿核查、系统性新颖性检索、纳入排除日志、双人编码及真实Zotero文库匹配。下一轮应在本次稳定ID上补充证据，而非覆盖原始快照。
