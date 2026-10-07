# Timeline：SCIBooster检索与DOI证据核验

日期：2026-10-07（Europe/Zurich）。

完成两条真实API检索线：历史分支21篇、模型分支58篇；去重后79条候选。按具体限定陈述选出41条直接支持记录，对应41个唯一DOI。

## 文件入口

- [按论点分组的精简DOI JSON](doi_by_claim.json)
- [完整证据与书目JSON](direct_support_doi.json)
- [纯DOI数组](doi_list.json)
- [Zotero可导入CSL JSON](direct_support.csl.json)
- [排除、无DOI与待核记录](not_in_direct_doi.json)
- [现有52项书目身份审计](existing_reference_identity_audit.json)
- [Zotero后续全文核验队列](zotero-verification-queue.json)

## 方法与覆盖

使用SCIBooster生产管线build_corpus：DeepSeek解析与筛选、WoS六条固定查询、OpenAlex摘要补全及向后引文扩展、共引补缺。另用OpenAlex精确DOI/题名检索和Crossref核对书目。框架代码未修改。本轮没有启动其独立agent命令；检索参数与实际调用日志保存在 research/runs/2026-10-07-scibooster/。

已对现有40个DOI逐一建立Crossref与OpenAlex记录；另核新文献及疑似误匹配，合计57个Crossref记录。初次Crossref有19次429限流，降低频率后重试全部成功。Roy1968补得原先未填的DOI：10.1051/ro/196802v100571。

原始输入按运行前状态保存并计算SHA-256。初筛相关性不等于事实支持；书评、题名相似和强制保留种子不能直接进入证据清单。所谓直接支持仅针对JSON中supported_statement的限定表述，所有fulltext_review_complete仍为false。

## 影响研究定位的结果

1. 分类与共同框架有直接前例：Hopkins1977、Jankowski1995、Malczewski2006、Cinelli2020。研究新颖性应转为比较分类维度及解释增益。
2. 权重空间与空间敏感性已有Feick/Hall2004、Chen等2010、Ligmann-Zielinska/Jankowski2014等先例。只做权重扰动或绘制稳定区域不足以构成独创性。
3. Dias/Vetschera2019关于效用函数抽样偏差的研究是本次新补的重要限制：探索参数空间仍需要说明采样分布及函数空间的选择。
4. Steinitz1990六层框架现已核到原作身份和摘要；精确六模型名称、顺序和图形继续等待原页。
5. 历史部分获得Steinitz2014参与者回顾、Shoshkes2009研究及Kiefer1965原论文等可用DOI。它们不能替代Eliot、Manning、Tyrwhitt各原始报告的页码核验。

## 避免误引用

检索系统把10.2307/254268评分为核心专著，但JSTOR将其列在Book Selection，作者为书评者C. Leake，不能将该DOI归给Malczewski原书。10.2307/2584151为JORS书评记录；10.5860/choice.27-6399属于Choice Reviews。它们已从直接支持清单排除。另有疑似书评先保留为待核，不能直接改造成书籍DOI。参见[JSTOR当期目录](https://www.jstor.org/stable/i302771)。

年份使用卷期/印刷日期作为引用锚点，同时保留在线日期与OpenAlex年份。例如某些2004、2008论文在OpenAlex显示2003、2007；不能用DOI中的数字或数据库单一年份直接移动Timeline节点。差异详见身份审计JSON。

## 分类清单

### 场地分析、区域调查与叠图前史

|记录|可支持的限定陈述|文献／DOI|
|---|---|---|
|DS001|城市设计中利用自然以服务健康、安全与公共福祉的传统早于现代生态规划。|[Urban Nature and Human Design: Renewing the Great Tradition（1985）](https://doi.org/10.1177/0739456x8500500106)|
|DS002|美国土地适宜性分析在20世纪初已有文献记录的应用；2001综述已讨论神经计算和演化程序等技术。|[Land-Use Suitability Analysis in the United States: Historical Development and Promising Technological Achievements（2001）](https://doi.org/10.1007/s002670010247)|
|DS003|Hein与van Mil的研究将Geddes、Tyrwhitt的先调查后规划与叠合地图观察空间模式联系起来，并明确讨论Tyrwhitt1950文本。|[Mapping as Gap-Finder: Geddes, Tyrwhitt, and the Comparative Spatial Analysis of Port City Regions（2020）](https://doi.org/10.17645/up.v5i2.2803)|
|DS004|Tyrwhitt在1941—1951年参与跨国规划话语，并将Geddes的生物区域思想与欧洲现代主义相结合。|[Jaqueline Tyrwhitt and transnational discourse on modern urban planning and design, 1941–1951（2009）](https://doi.org/10.1017/s0963926809006282)|
|DS005|Steinitz以参与者身份回顾1963—1970年Harvard计算制图实验室的早期GIS开发与应用实验。|[The beginnings of geographical information systems: a personal historical perspective（2014）](https://doi.org/10.1080/02665433.2013.860762)|
|DS006|Kiefer1965年论文提出为都市边缘地区土地利用总体规划分析土地物理特征的方法与建议。|[Land evaluation for land use planning（1965）](https://doi.org/10.1016/0007-3628(65)90013-7)|

### 已有分类与跨方法比较

|记录|可支持的限定陈述|文献／DOI|
|---|---|---|
|DS007|Hopkins1977年已经提出土地适宜性方法分类，并比较同质区域识别及用途适宜性评级方法。|[Methods for Generating Land Suitability Maps: A Comparative Evaluation（1977）](https://doi.org/10.1080/01944367708977903)|
|DS008|Zube等1982年从1965—1980年160余篇研究中区分专家、心理物理、认知与体验四种景观感知范式。|[Landscape perception: Research, application and theory（1982）](https://doi.org/10.1016/0304-3924(82)90009-0)|
|DS009|Malczewski2006年综述对1990—2004年的300余篇GIS-MCDA期刊论文进行分类并辨识发展趋势。|[GIS‐based multicriteria decision analysis: a survey of the literature（2006）](https://doi.org/10.1080/13658810600661508)|
|DS010|Cinelli等2020年把MCDA过程的特征组织为问题表述、决策建议构建及定性特征与技术支持三个部分。|[How to support the application of multiple criteria decision analysis? Let us start with a comprehensive taxonomy（2020）](https://doi.org/10.1016/j.omega.2020.102261)|
|DS011|Jankowski1995年给出GIS与MCDM整合框架，对MCDM方法分类并匹配决策者的选择方式。|[Integrating geographical information systems and multiple criteria decision-making methods（1995）](https://doi.org/10.1080/02693799508902036)|

### 模型结构、价值尺度与科学化边界

|记录|可支持的限定陈述|文献／DOI|
|---|---|---|
|DS012|Steinitz1990年提出组织景观设计问题的六层框架，每层对应一种建模类型。|[A Framework for Theory Applicable to the Education of Landscape Architects (and Other Environmental Design Professionals)（1990）](https://doi.org/10.3368/lj.9.2.136)|
|DS013|Rittel与Webber指出，社会政策规划中的问题界定、公共利益和最优解都受到价值分歧与条件限制。|[Dilemmas in a general theory of planning（1973）](https://doi.org/10.1007/bf01405730)|
|DS014|WLC是GIS复合地图的一种决策规则；忽视其适用假设可能导致不当应用和可疑结果。|[On the Use of Weighted Linear Combination Method in GIS: Common and Best Practice Approaches（2000）](https://doi.org/10.1111/1467-9671.00035)|
|DS015|准则权重在不同聚合规则下具有不同解释，必须结合测量尺度、可通约性及所采用的模型理解。|[Interpretation of criteria weights in multicriteria decision making（1999）](https://doi.org/10.1016/s0360-8352(00)00019-x)|
|DS016|Dyer与Sarin1979年讨论可测多属性价值函数，并给出加法、乘法及更复杂形式成立的条件。|[Measurable Multiattribute Value Functions（1979）](https://doi.org/10.1287/opre.27.4.810)|
|DS017|Greco等2008年利用与偏好信息兼容的一组加法价值函数，分别定义对全部函数成立的必要偏好和至少一个函数成立的可能偏好。|[Ordinal regression revisited: Multiple criteria ranking using a set of additive value functions（2008）](https://doi.org/10.1016/j.ejor.2007.08.013)|

### 偏好获取及不同聚合／比较方法

|记录|可支持的限定陈述|文献／DOI|
|---|---|---|
|DS018|Saaty1977年研究成对比较矩阵主特征向量标度、一致性及层级结构中的综合优先度。|[A scaling method for priorities in hierarchical structures（1977）](https://doi.org/10.1016/0022-2496(77)90033-5)|
|DS019|AHP不仅从专家成对比较得到优先尺度，还通过父节点优先度进行层级综合。|[Decision making with the analytic hierarchy process（2008）](https://doi.org/10.1504/ijssci.2008.017590)|
|DS020|Yager1988年提出OWA聚合算子，并研究其介于AND与OR型聚合之间的性质。|[On ordered weighted averaging aggregation operators in multicriteria decisionmaking（1988）](https://doi.org/10.1109/21.87068)|
|DS021|Jiang与Eastman2000年讨论GIS中的Boolean与WLC，并以模糊测度及OWA连接因子标准化和聚合问题。|[Application of fuzzy measures in multi-criteria evaluation in GIS（2000）](https://doi.org/10.1080/136588100240903)|
|DS022|Malczewski2006年把模糊语言量词引入GIS土地适宜性的OWA程序，通过参数变化表达不同决策策略。|[Ordered weighted averaging with fuzzy quantifiers: GIS-based multicriteria evaluation for land-use suitability analysis（2006）](https://doi.org/10.1016/j.jag.2006.01.003)|
|DS023|UTA用方案的多准则评价和主观弱序，通过序数回归与线性规划估计加法效用函数，并进行稳定性分析。|[Assessing a set of additive utility functions for multicriteria decision-making, the UTA method（1982）](https://doi.org/10.1016/0377-2217(82)90155-2)|
|DS024|Roy1968年发表多观点排序与选择论文；原文参考文献列有1966年ELECTRE技术报告。|[Classement et choix en présence de points de vue multiples（1968）](https://doi.org/10.1051/ro/196802v100571)|
|DS025|Joerin等将GIS与ELECTRE-TRI结合，用于瑞士地区住房土地适宜性分类。|[Using GIS and outranking multicriteria analysis for land-use suitability assessment（2001）](https://doi.org/10.1080/13658810051030487)|
|DS026|PROMETHEE I给出部分预序，PROMETHEE II给出全预序，体现不同方法的输出结构差异。|[Note—A Preference Ranking Organisation Method（1985）](https://doi.org/10.1287/mnsc.31.6.647)|

### 权重空间、不确定性与敏感性

|记录|可支持的限定陈述|文献／DOI|
|---|---|---|
|DS027|SMAA1998通过探索权重空间描述哪些评价支持某个方案成为首选，并允许以概率分布表达不确定输入。|[SMAA - Stochastic multiobjective acceptability analysis（1998）](https://doi.org/10.1016/s0377-2217(97)00163-x)|
|DS028|SMAA-2在2001年将原SMAA扩展到所有名次，并考虑部分偏好信息。|[SMAA-2: Stochastic Multicriteria Acceptability Analysis for Group Decision Making（2001）](https://doi.org/10.1287/opre.49.3.444.11220)|
|DS029|2004年的空间多准则敏感性综述考察28项研究，指出当时敏感性分析不普遍，常见做法是改变因素权重。|[Sensitivity Analysis in Multicriteria Spatial Decision-Making: A Review（2004）](https://doi.org/10.1080/10807030490887221)|
|DS030|Feick与Hall2004年提出研究多准则权重敏感性的空间维度，结合不同参与者的评价和地图表达。|[A method for examining the spatial dimension of multi-criteria weight sensitivity（2004）](https://doi.org/10.1080/13658810412331280185)|
|DS031|Chen、Yu与Khan2010年把逐一改变权重的OAT敏感性分析与AHP、ArcGIS结合，显示土地适宜性结果的空间变化。|[Spatial sensitivity analysis of multi-criteria weights in GIS-based land suitability evaluation（2010）](https://doi.org/10.1016/j.envsoft.2010.06.001)|
|DS032|Ligmann-Zielinska与Jankowski2014年通过Monte Carlo探索准则权重空间，并为每个空间单元生成适宜性、不确定性及敏感性图。|[Spatially-explicit integrated uncertainty and sensitivity analysis of criteria weights in multicriteria land suitability evaluation（2014）](https://doi.org/10.1016/j.envsoft.2014.03.007)|
|DS033|GIS模型中的不确定性分析研究输入与参数不确定性向输出的传播，敏感性分析研究不同来源对输出不确定性的重要性。|[Uncertainty and sensitivity analysis: tools for GIS-based model implementation（2001）](https://doi.org/10.1080/13658810110053125)|
|DS034|Dias与Vetschera2019年指出直接随机生成效用值可能使效用函数形状产生抽样偏差，并提出减轻偏差的方法。|[On generating utility functions in Stochastic Multicriteria Acceptability Analysis（2019）](https://doi.org/10.1016/j.ejor.2019.04.031)|

### 群体偏好、参与及审议

|记录|可支持的限定陈述|文献／DOI|
|---|---|---|
|DS035|Malczewski1996年在栅格GIS中用TOPSIS生成个人排序，再用Borda规则组合群体偏好。|[A GIS-based approach to multiple criteria group decision-making（1996）](https://doi.org/10.1080/02693799608902119)|
|DS036|协作式空间多准则评价已有专门综述，讨论参与过程中的任务、工具和可用性评价。|[Collaborative spatial multicriteria evaluation: a review and directions for future research（2021）](https://doi.org/10.1080/13658816.2020.1776870)|
|DS037|te Boveldt等2021年比较多准则方法的数学结构及参与框架，认为政治敏感的参与阶段需要重视透明性和易用性。|[How can multi-criteria analysis support deliberative spatial planning? A critical review of methods and participatory frameworks（2021）](https://doi.org/10.1177/13563890211020334)|

### 视觉景观与学习型评价

|记录|可支持的限定陈述|文献／DOI|
|---|---|---|
|DS038|2017年已有利用Scenic-Or-Not图像评分和卷积神经网络研究、预测户外景观美感的工作。|[Using deep learning to quantify the beauty of outdoor places（2017）](https://doi.org/10.1098/rsos.170170)|
|DS039|ScenicNet2021年将土地覆盖预测作为美感回归的可解释中间任务，连接遥感表示与众包景观评分。|[On the relation between landscape beauty and land cover: A case study in the U.K. at Sentinel-2 resolution with interpretable AI（2021）](https://doi.org/10.1016/j.isprsjprs.2021.04.020)|
|DS040|Havinga等2021年用英国众包调查检验Flickr与深度学习的景观美感模型，并与环境指标模型比较。|[Social media and deep learning capture the aesthetic quality of the landscape（2021）](https://doi.org/10.1038/s41598-021-99282-0)|
|DS041|2023年视觉景观综述区分感知与评价，以及人眼视角与鸟瞰视角，并梳理相应的技术与度量。|[Modeling the Visual Landscape: A Review on Approaches, Methods and Techniques（2023）](https://doi.org/10.3390/s23198135)|

## 尚未证明

“首次跨传统分类”“判断位置变化是全史规律”“框架已提高可理解性”“已建成AGI景观原型”均未被本次检索证实。支持研究动机的理论与证明本项目效度的证据不能混同。

早期史料很多没有在本轮建立DOI。22个历史节点逐项登记其原有来源与本轮相关历史研究；不凭后来的研究DOI冒充古籍或历史报告DOI。本轮WoS查询实际受1900—2026出版年范围限制，前1900材料依赖既有档案线索；检索上限是2026，不表示穷尽到当天。

一条关于偏好获取的新网页线索未在OpenAlex精确题名匹配成功，未获得可靠DOI和出版日期，已列待核，不进入引用清单。

## API用量与检查

{"deepseek_prompt_tokens": 49062, "deepseek_completion_tokens": 14151, "deepseek_calls": 23, "wos_requests": 6, "openalex_requests": 49}

数据检查12项全部通过。计数属于定向检索流程，不是预注册系统综述、独立召回率或全文质量评价。Zotero接口保持离线。
