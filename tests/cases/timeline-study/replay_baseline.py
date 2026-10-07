"""Evidence-bounded functional reconstruction of all current timeline entries."""
import json, hashlib, argparse
from pathlib import Path
CASE=Path(__file__).resolve().parent
ap=argparse.ArgumentParser(description='Replay the pinned case-specific baseline; not general model extraction.')
ap.add_argument('--output',type=Path,required=True)
args=ap.parse_args()
ROOT=args.output.resolve(); ROOT.mkdir(parents=True,exist_ok=True)
D=ROOT/'data'; D.mkdir(exist_ok=True)
source_path=CASE/'input/data/timeline-revised.json'
src=json.loads(source_path.read_text())

def fld(text,status='project_reconstruction',**kwargs):return dict(text=text,status=status,**kwargs)
profiles={
'judgment':('场地、聚落或环境条件','观察与文字描述','expert_judgment',['g','theta','f']),
'representation':('规划区域、环境或设计方案','调查、图像与空间图层组织','representation_or_cartographic_operation',['g']),
'evaluation':('土地、资源、生态或用途相关空间对象','场地属性与用途相关指标','use_related_evaluation_structure_not_fully_extracted',['g','theta','f']),
'operators':('抽象候选方案或土地利用评价对象，具体案例须核','多准则表现及必要的尺度转换','evaluation_operator_not_fully_extracted',['theta','f']),
'elicitation':('方案、视觉刺激或群体评价对象；按原文区分','判断材料及候选方案表现','preference_generation_or_learning',['g','theta','f']),
'uncertainty':('受多准则评价的候选方案或空间对象','准则值、参数约束与必要的抽样表示','ensemble_or_robustness_analysis',['theta','f']),
'learning':('景观视觉或审美评价对象','图像、遥感或社交媒体及目标标签','learned_prediction',['g','theta','f'])}
# Only bounded input labels supported by the existing evidence are supplied;
# uninspected units/resolution are null, never invented.
variables={
'H01':['城址环境条件','风向与街道布置'], 'H02':['场地条件','景观关系与借景'], 'H03':['城市烟害及环境状况'],
'H11':['边界与道路图层','水系图层','地形晕渲图层'], 'H18':['同尺度专题图层'],
'DS039':['Sentinel-2数据／土地覆盖语义表示'], 'DS038':['户外景观图像'], 'DS040':['社交媒体图像']}
objects={'H05':'修改前后景观设计方案','H09':'Buffalo公园系统','H10':'Boston跨市镇公园规划区域','H11':'区域调查与公共表达对象','H15':'Billerica城镇规划区域','H16':'美国全国尺度规划对象','DS006':'都市边缘土地与土地利用规划','DS033':'GIS水文模型对象；非直接景观审美案例','T30':'景观感知刺激与美感判断','T32':'森林景观与美感预测','DS023':'具有偏好排序的多准则候选方案'}
# Family assignment uses the audited statement/formal reading and carries analyst status.
families={
'DS014':('weighted_aggregation','y=Σᵢwᵢcᵢ(xᵢ;αᵢ)','score','pointwise_template'),
'DS016':('multiattribute_value_function','y=f_value(x;θ)','value','not_fully_extracted'),
'DS020':('ordered_weighted_aggregation','y=Σᵢvᵢs_(i)','score','pointwise_template'),
'DS022':('gis_quantifier_guided_owa','y=f_OWA(Cα(x);v)','score','not_fully_extracted'),
'DS024':('outranking','y=f_ELECTRE(X;θ)','comparison_or_choice','candidate_set'),
'DS025':('outranking_classification','y=f_ELECTRE_TRI(X;θ)','class','candidate_set_or_profiles_detail_pending'),
'DS026':('outranking_ranking','y=f_PROMETHEE(X;θ)','partial_or_complete_preorder','candidate_set'),
'DS018':('ahp_priority_scaling','θ=q_AHP(J); y=f_AHP(X;θ)','priorities','hierarchy_or_candidate_set'),
'DS019':('ahp_elicitation_and_synthesis','θ=q_AHP(J); y=f_AHP(X;θ)','priorities','hierarchy_or_candidate_set'),
'DS023':('additive_preference_disaggregation','θ̂=q_UTA(J); y=f_additive(x;θ̂)','utility_or_ranking','fit_depends_on_preference_examples'),
'DS017':('robust_ordinal_regression','𝒴(X)={f_additive(X;θ):θ∈Θ(J)}','necessary_possible_relations','candidate_set'),
'DS027':('stochastic_acceptability_analysis','Y=f(X;θ), θ~pθ','acceptability_statistics','candidate_set'),
'DS028':('stochastic_rank_acceptability','Y=f(X;θ), θ~pθ','all_rank_acceptability_statistics','candidate_set'),
'DS035':('topsis_and_group_rank_aggregation','y⁽ᵏ⁾=f_TOPSIS(X;θ⁽ᵏ⁾); y_group=Borda({y⁽ᵏ⁾})','individual_and_group_ranking','candidate_set'),
'DS031':('one_at_a_time_spatial_sensitivity','y_j=f(x;θ₀+δ_j)','spatial_sensitivity_results','case_specific'),
'DS032':('spatial_uncertainty_sensitivity','Y=f(x;θ), θ~pθ','spatial_uncertainty_and_sensitivity_results','case_specific'),
'DS038':('machine_learning_prediction','ŷ=fφ(x); φ̂=ℒ(D_train)','predicted_scenicness','not_fully_extracted'),
'DS039':('semantic_bottleneck_learning','ŷ=fφ(gρ(L)); (ρ̂,φ̂)=ℒ(D_train)','predicted_beauty','not_fully_extracted'),
'DS040':('machine_learning_prediction','ŷ=fφ(x); φ̂=ℒ(D_train)','predicted_aesthetic_quality','not_fully_extracted'),
'T32':('statistical_prediction','ŷ=fβ(x); β̂=ℒ(D_train)','predicted_scenic_beauty','not_fully_extracted'),
'T30':('perceptual_measurement','y=f_SBE(J;θ)','scenic_beauty_measure','measurement_design_pending'),
'T20':('fuzzy_set_foundation','μ_A(x)∈[0,1]','membership','no_complete_landscape_pipeline_extracted'),
'T10':('fuzzy_land_evaluation','y=f_fuzzy(x;θ)','evaluation_output_detail_pending','not_fully_extracted')}
records=[]
for r in src['records']:
 ax=r['axis']; meta=ax in ('reflection','institution'); old=r['formal_reading']; b=profiles.get(ax)
 if meta:
  family='institutional_context' if ax=='institution' else 'review_or_framework'
  L=fld('术语、职业与教育制度事件' if ax=='institution' else '方法文献、规划问题或框架；不是此记录自身实施的景观评价案例','source_bounded')
  g=fld('此条不适用景观L到x的具体提取；如编码综述研究须另建元研究对象。','not_applicable')
  inp=[]; theta=fld('具体景观模型参数不适用；分析或制度选择可作为背景研究对象。','not_applicable')
  func=fld('此条不是已抽取的景观评价函数。','not_applicable',formula=None,output_domain=None,candidate_set_dependence=None)
  chain=fld('作为背景／方法反思节点保留，不绘制具体L→D管线。','not_applicable',formula=None)
  loc=[]
 else:
  family,formula,domain,depend=families.get(r['id'],(b[2],'y=f(x;θ)',old['y'],'not_checked'))
  L=fld(objects.get(r['id'],b[0]))
  g=fld(b[1]+'。'+old['x'],formula='x=gρ(L)',represented=old['x'],possibly_excluded='当前表示未说明的生活经验、文化与时序关系须另查，不能视为已证明不存在。')
  inp=[dict(name=v,meaning=v,variable_kind=None,measurement_scale=None,spatial_resolution=None,data_source=None,status='source_bounded_label_details_not_checked') for v in variables.get(r['id'],[])]
  theta=fld(old['theta'],components_status='not_fully_extracted',generation=fld('权重、判断材料、拟合／抽样约束的来源依该节点原文进一步定位。','not_checked'),full_judgment_parameters='Θ_all=(ρ,θ_eval,η); 模型选择m另记')
  if r['id'] in ('DS018','DS019','DS023'):
   theta['generation']=fld('从成对比较获取优先度' if r['id']!='DS023' else '从排序偏好约束拟合加法函数','source_bounded',formula='θ=q(J)')
  elif ax=='learning' or r['id']=='T32':theta['generation']=fld('训练数据估计参数；标签、样本和目标的具体设置仍须原文核查',formula='θ̂=ℒ(D_train)')
  func=fld(old['f'],formula=formula,output_domain=domain,candidate_set_dependence=depend)
  chain=fld('适用部分：L→gρ→x→f(·;θ_eval)→y；h与最终D尚未核到，保持开放。',formula='L → gρ → x → f_m(·;θ_eval) → y → hη[not_checked] → D[not_checked]')
  loc=b[3]
 h=fld('尚未核到由评价输出到最终行动的转换规则；不能补造保护区、禁建阈值或项目优先级。','not_applicable' if meta else 'not_checked',formula=None if meta else 'D=hη(y)',decision_consequence=None)
 feedback=fld('此条不适用具体景观干预闭环。' if meta else '尚未核到实施后的景观变化、复测及参数更新；反馈为可继续追问的环节。','not_applicable' if meta else 'not_checked',implemented=None)
 unc={k:fld('此条不适用具体景观模型的不确定性抽取。' if meta else text,'not_applicable' if meta else 'project_reconstruction',implemented_analysis_status='not_applicable' if meta else 'not_checked') for k,text in {
 'representation':'gρ的选择是否充分表达该对象，需独立检验。','data':'测量、分类、尺度及样本误差；具体误差模型未核。','parameter':'θ估计或获取的未知程度；多群体分歧另记，不自动视为误差。','structural':'f及模型选择m是否适用；不能仅由方法标签判断。','decision':'hη把结果变为行动的阈值与制度选择未核。'}.items()}
 if ax=='uncertainty':unc['parameter']['implemented_analysis_status']='bounded_method_support_see_evidence_not_full_formula_review'
 remainder=fld('背景节点没有具体模型的余项边界可抽取。' if meta else '当前重构未覆盖的历史意义、记忆、生活体验或文化关系是后续审查问题；是否有关、是否已被原方法表达须逐案确认。','not_applicable' if meta else 'project_reconstruction',source_asserts_irreducibility=False,permanently_nonformalizable_claim=False)
 interpretation={
 'newly_formalized':fld('此条提供制度背景或方法反思，不作为新评价算子的出现。' if meta else old['f']),
 'human_judgment_remaining':fld('分类及框架选择仍是研究者判断。' if meta else old['theta']),
 'uncertainty_reduced':fld('来源未核到可比较的减少程度；不从数值化或自动化推定效度提升。','not_applicable' if meta else 'not_checked'),
 'uncertainty_introduced':fld('新选择可能发生于g、θ、f或h；是否新增不确定性需前后方法对照。','not_applicable' if meta else 'project_reconstruction'),
 'landscape_representation_changed':fld('不适用具体案例' if meta else old['x'],'not_applicable' if meta else 'project_reconstruction'),
 'capacity_without_structure_change':fld('计算能力与结构差异需分别对照，当前不足以判定结构等价。','not_applicable' if meta else 'not_checked')}
 records.append(dict(id=r['id'],title=r['title'],date_label=r['date_label'],historical_description=fld(r['supported_statement'],'source_bounded'),decision_object=L,representation=g,inputs=dict(formula=None if meta else 'x=(x₁,…,xₙ)',variables=inp,completeness='not_applicable' if meta else 'partial_or_not_checked',note='空变量清单表示未完成抽取，不表示方法没有输入。'),judgment_parameters=theta,functional_structure=func,decision_translation=h,full_canonical_form=chain,model_family=dict(label=family,status='not_applicable_as_evaluation_family' if meta else 'project_reconstruction',mutually_exclusive=False),primary_location_of_judgment=dict(locations=loc,status='not_applicable' if meta else 'project_reconstruction',not_a_measured_dominance=True),uncertainty=unc,primary_uncertainty=fld('尚无依据对五类不确定性作主次排序。','not_applicable' if meta else 'not_checked'),irreducible_remainder=remainder,feedback=feedback,historical_interpretation=interpretation,evidence=r['evidence'],caveat=r['caveat'],source_records=r['source_records'],doi=r.get('doi'),fulltext_review_complete=r['fulltext_review_complete'],reconstruction_status='analyst_functional_reconstruction_not_original_equation',applicability='context_or_meta' if meta else 'operational_reconstruction'))
comp=[dict(ids=['DS014','DS023'],shared_template='additive value/utility aggregation',difference='给定／获取权重与从偏好例子拟合函数不同；转换、定义域及条件仍须逐案核',status='candidate_similarity_not_equivalence'),dict(ids=['DS018','DS019','DS014'],shared_template='仅在AHP负责赋权且下游确为WLC的应用中，可能共享加法聚合',difference='完整AHP不是自动等于AHP–WLC；本时间线未抽取一对可确证同构应用',status='conditional_hypothesis'),dict(ids=['DS020','DS014'],shared_template=None,difference='排序位置权重与固定准则权重不同；不能因都写加权和就判等价',status='structural_distinction_in_project_formalism')]
obj=dict(schema_version='functional-1.0',created_at='2026-10-07',protocol='../../../skills/landscape-functional-analysis/references/protocol-original.md',application_notes='../../../skills/landscape-functional-analysis/references/execution-boundaries.md',source='timeline-revised.json',source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),record_count=len(records),scope='All current nodes including pending and context/meta entries; no new literature search.',status_dictionary=dict(source_bounded='有限来源所支持的内容，不表示原公式已核',project_reconstruction='本项目的功能重构或潜在分析问题',not_checked='现有证据未核到',not_applicable='该类型节点不适用此字段'),records=records,comparative_normalization=comp,core_proposition_status='research_hypothesis_not_established',family_count_claim=None)
(D/'timeline-functional.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
# Human-readable complete canonical output; all records, including N/A, are retained.
labels={'historical_description':'历史描述','decision_object':'决策对象 L','representation':'表示 g','judgment_parameters':'判断参数 θ','functional_structure':'函数 f 与输出 y','decision_translation':'决策转换 h 与 D','full_canonical_form':'完整规范链条','primary_uncertainty':'主要不确定性','irreducible_remainder':'当前重构未覆盖的余项','feedback':'反馈'}
md=['# Timeline：逐节点功能语言包装','2026-10-07｜'+str(len(records))+'条完整字段输出。依据既有证据重构，未新增全文核验。','协议：[Readme.md](protocols/timeline-to-fx/Readme.md)；执行约定：[APPLICATION_NOTES.md](protocols/timeline-to-fx/APPLICATION_NOTES.md)；数据：[timeline-functional.json](data/timeline-functional.json)。','统一链条：L → gρ → x → fₘ(·;θ_eval) → y → hη → D。当前模型之外的相关方面是研究问题；尚未核到不等于不存在。']
for r in records:
 md+=['\n## '+r['date_label']+'｜'+r['id']+'｜'+r['title']]
 for k,label in labels.items():
  z=r[k];md+=['\n**'+label+'** ['+z['status']+']：'+z['text']]
  if z.get('formula'):md+=['\n表达：`'+z['formula']+'`。']
  if k=='functional_structure' and z.get('output_domain'):md+=['\n输出域：'+z['output_domain']+'；候选集依赖：'+z['candidate_set_dependence']+'。']
  if k=='judgment_parameters' and z.get('generation'):md+=['\n参数获取：'+z['generation']['text']+' ['+z['generation']['status']+']。']
 md+=['\n**输入变量**：'+('；'.join(v['name'] for v in r['inputs']['variables']) or '未完成变量抽取／该类型不适用，详见数据状态。')+'。量纲、尺度、分辨率、变量类型和来源细节未核者为null。','\n**模型家族**：'+r['model_family']['label']+' ['+r['model_family']['status']+']。','\n**判断位置**：'+(', '.join(r['primary_location_of_judgment']['locations']) or '该类型不适用')+'；为分析性定位，未测量主次。','\n**五类不确定性**：']
 for k,z in r['uncertainty'].items():md+=['\n- '+k+' ['+z['status']+']：'+z['text']+' 分析实施状态：'+z['implemented_analysis_status']+'。']
 md+=['\n**历史解释的六个问题**：']
 for k,z in r['historical_interpretation'].items():md+=['\n- '+k+' ['+z['status']+']：'+z['text']]
 md+=['\n**来源及限制**：'+r['caveat']]
 for ev in r['evidence']:md+=['\n- [来源]('+ev['url']+')；'+str(ev['locator'])+'；'+ev.get('inspection_level',ev.get('inspection_scope',''))+'。']
md+=['\n## 跨节点结构比较','结构相似候选须进一步核输入域、转换、比较／聚合规则和输出域，当前不宣布已证明等价，也不估计领域的真实函数家族数。']
for c in comp:md+=['\n- '+', '.join(c['ids'])+'：'+c['difference']+' ['+c['status']+']。']
(ROOT/'TIMELINE_FUNCTIONAL.md').write_text('\n'.join(md)+'\n')
print(f'Functional conversion: {len(records)} records; '+str(sum(r['applicability']=='context_or_meta' for r in records))+' context/meta entries.')
