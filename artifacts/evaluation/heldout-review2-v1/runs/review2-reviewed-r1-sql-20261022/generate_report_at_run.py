from pathlib import Path
import importlib.util,json,numpy as np
p=Path('/home/eroz/projects/enterprise-knowledge-ai-agent/artifacts/evaluation/heldout-review2-v1')
folder=p/'runs/review2-reviewed-r1-sql-20261022'
report=json.loads((folder/'results.json').read_text())
assert report['configuration']['status']=='completed'
spec=importlib.util.spec_from_file_location('heldout_report_run',p/'run.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
d=m.load();qrels,_=m.gold(d)
rows=report['results'];summary=report['summary'];methods=list(summary)
assert json.loads((folder/'verification.json').read_text())['status']=='passed'
translations=json.loads((p/'prepared/translations.json').read_text())['records']
byquery={r['question']:r for r in translations}
ceiling=float(np.mean([min(10,len(qrels[c['intent_id'],c['target_language']]))/10 for c in d['cases']]))
losses=[];wins=[];regressions=[]
for row in rows:
 final=row['methods']['translated_hybrid_bge'];raw=row['methods']['translated_hybrid_raw']
 case=next(c for c in d['cases'] if c['id']==row['id'])
 if not final['full_evidence_at_10']:
  pool=m.evidence(d,case,final['candidates'])
  losses.append({'case_id':row['id'],'question':row['question'],'missing_components':final['missing_components'],
   'stage':'reranker_dropped_from_top10' if pool['full_evidence_success'] else 'candidate_pool_missing_evidence',
   'gold_positions':{key:final['ranking'].index(key)+1 if key in final['ranking'] else None for key in sorted(qrels[row['intent_id'],row['target_language']])},
   'queries':byquery[row['question']]['queries']})
 if not raw['full_evidence_at_10'] and final['full_evidence_at_10']:wins.append(row['id'])
 if raw['full_evidence_at_10'] and not final['full_evidence_at_10']:regressions.append(row['id'])
ids=sorted({r['intent_id'] for r in rows});bootstrap={}
for base in ['dense','dense_bge','translated_hybrid_raw']:
 delta=np.array([np.mean([r['methods']['translated_hybrid_bge']['full_evidence_at_10']-r['methods'][base]['full_evidence_at_10'] for r in rows if r['intent_id']==i]) for i in ids])
 rng=np.random.default_rng(20261022)
 estimates=delta[rng.integers(0,20,size=(10000,20))].mean(axis=1)
 bootstrap[base]={'gain_pp':float(delta.mean()*100),'ci95_pp':list(map(float,np.quantile(estimates,[.025,.975])*100)),'clusters':20,'resamples':10000,'seed':20261022}
api=[r['api_seconds'] for r in translations]
analysis={'precision_at_10_label_ceiling':ceiling,'final_method_losses':losses,
 'reranker_rescues_over_translated_raw':wins,'reranker_regressions_over_translated_raw':regressions,
 'paired_intent_bootstrap':bootstrap,'translation_preparation':{'questions':40,'failures':sum(r['error'] is not None for r in translations),'api_mean_seconds':float(np.mean(api)),'api_median_seconds':float(np.median(api)),'api_p95_seconds':float(np.quantile(api,.95))}}
m.save(folder/'analysis.json',analysis)
labels={'dense':'Dense E5','dense_bge':'Dense + BGE','translated_hybrid_raw':'Translated hybrid','translated_hybrid_bge':'Translated hybrid + BGE'}
lines=['# Benchmark Review 2 — bộ mới reviewed-r1','',
 '**Đã hoàn tất 80/80 ca; kiểm tra lại logits, thứ hạng và metric đạt.** Kết quả thực, không phải diagnostic nhãn.','',
 '20 ý hỏi × câu VI/EN × corpus VI/EN; chỉ có 20 cụm ý hỏi. H10 mới dùng hàng không-chênh-lệch của SOP; H13/H19 đã sửa trước inference. Bản draft lưu trong history/. Không sửa nhãn hoặc bản dịch theo kết quả.','',
 '## Kết quả tổng','',
 '| Phương pháp | P@10 | R@10 | MRR@10 | nDCG@10 | Đủ bằng chứng | Thành phần đạt | Latency TB / median / p95 (ms) |',
 '|---|---:|---:|---:|---:|---:|---:|---:|']
for method in methods:
 a=summary[method]['all']
 lines.append(f"| {labels[method]} | {a['precision_at_10']:.4f} | {a['recall_at_10']:.4f} | {a['mrr_at_10']:.4f} | {a['ndcg_at_10']:.4f} | {int(a['complete_cases'])}/80 ({a['full_evidence_at_10']:.1%}) | {a['components_met']}/{a['components_total']} | {a['mean_latency_ms']:.0f} / {a['median_latency_ms']:.0f} / {a['p95_latency_ms']:.0f} |")
lines+=['',f'Trần P@10 trung bình theo nhãn: **{ceiling:.1%}**. Mỗi ca chỉ có vài gold chunk trong top10. Recall đếm cả gold chunk thay thế; Full evidence đo đã đủ mọi thành phần trả lời. Hai metric không đồng nghĩa.']
for title,groups in [('Theo hướng ngôn ngữ',['vi->vi','vi->en','en->vi','en->en']),('Theo nhóm câu hỏi',['narrative','table_numeric','multi_chunk','paraphrase_terminology'])]:
 lines+=['','## '+title,'','| Nhóm | Dense | Dense + BGE | Translated hybrid | Translated hybrid + BGE |','|---|---:|---:|---:|---:|']
 for group in groups:
  lines.append('| '+group+' | '+' | '.join(f"{int(summary[method][group]['complete_cases'])}/20" for method in methods)+' |')
 lines+=['','Các ô là số ca đủ toàn bộ bằng chứng trong top10.']
lines+=['','## Ca nhánh cuối chưa đủ bằng chứng','']
if losses:
 for f in losses:
  lines += [f"- **{f['case_id']}**: {f['question']}",f"  Thiếu: {', '.join(f['missing_components'])}. Tầng: {f['stage']}. Vị trí gold trong top30: {json.dumps(f['gold_positions'],ensure_ascii=False)}."]
else:lines+=['Không có ca thiếu bằng chứng bắt buộc trong top10 trên bộ này; không suy ra kết quả tương tự cho mọi câu hỏi/tài liệu thực tế.']
lines+=['',f"Reranker cứu {len(wins)} ca so với translated hybrid thô và làm mất đủ bằng chứng ở {len(regressions)} ca. ID cụ thể nằm trong analysis.json.",'','## Chênh lệch và độ chắc chắn','']
for base,b in bootstrap.items():
 lines.append(f"- Nhánh cuối so với {labels[base]}: {b['gain_pp']:+.2f} điểm phần trăm đủ bằng chứng; bootstrap95% CI [{b['ci95_pp'][0]:+.2f}, {b['ci95_pp'][1]:+.2f}] điểm phần trăm.")
lines+=['','Bootstrap10.000 lần theo20 ý hỏi, seed20261022; các bản ngôn ngữ cùng một ý thuộc cùng cụm. Khoảng tin cậy không chứng minh tổng quát hóa sang miền mới.','',
 '## Điều kiện đo và hạn chế','',
 '- E5 multilingual-e5-base768 chiều + BGE reranker-v2-m3, revision cố định, FP32/CUDA, batch4,30 candidate,top10. Document vectors dùng lại. Xem config.json/protocol.json.',
 '- SQL production chạy trên TEMP tables chứa corpus cố định1063 chunk/10 bản tài liệu; mỗi ca scope5 tài liệu ngôn ngữ đích, admin. Không đổi dữ liệu/vector public Supabase.',
 '- Không cắt token: query E5 tối đa50 token; cận trên bảo thủ cho cặp BGE521/1024. Model đọc cache, không tải trọng số mới.',
 '- Một lần chạy/ca/nhánh, thứ tự nhánh ngẫu nhiên cố định seed. Latency warm gồm encode+retrieve+rerank, không gồm tải model,API dịch,generation. Encode đo một lần cho mỗi40 văn bản rồi dùng chung hai corpus đích.',
 f"- Dịch40/40 câu không lỗi: API trung bình {np.mean(api):.3f}s, median {np.median(api):.3f}s, p95 {np.quantile(api,.95):.3f}s, đo riêng trong bước chuẩn bị. Không coi đây là end-to-end production latency. Bản dịch lưu cố định, không dùng bản EN đã soạn làm bản dịch oracle câu VI.",
 '- 8 ý số liệu workbook giữ tên cột tiếng Anh và cùng dòng đáp án;6 ý có cả chunk giống hệt VI/EN. Cần xem riêng nhóm văn bản và từng hướng ngôn ngữ khi kết luận lợi ích dịch.',
 '- Nhóm table_numeric có H10 là bảng quy tắc SOP; không phải cả nhóm đọc số. Một số câu số liệu ghép hai dòng nằm trong multi_chunk.',
 '- Corpus mô phỏng đã biết, nhãn do trợ lý soạn/đối chiếu; người dùng duyệt hướng sửa. Chưa có kiểm định độc lập về người gán nhãn. Các chủ đề liên quan bộ cũ có trong overlap-audit.json.',
 '- Chưa đo generation/faithfulness, từ chối khi thiếu đáp án, RBAC hoặc OCR. Phần generation/LLM cần An đánh giá riêng theo proposal/Review2.',
 '- Bộ mới chưa có nhánh hybrid chỉ dùng query gốc: chênh lệch so với dense + BGE gộp tác động BM25/fusion và dịch, không tách riêng lợi ích dịch. Embedding giữ E5, không phải phép chọn lại model embedding.','',
 '## Tìm và chạy lại','',
 'Từ gốc project, kiểm artifact đã lưu bằng lệnh (không inference mới):','',
 '    .venv/bin/python artifacts/evaluation/heldout-review2-v1/run.py verify-run artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022','',
 'Chạy inference lại, giữ nguyên bản dịch và toàn bộ đầu vào; dùng tên mới để không ghi đè:','',
 '    .venv/bin/python artifacts/evaluation/heldout-review2-v1/run.py run --name review2-reviewed-r1-sql-repeat-02','',
 'Giữ cả folder, đặc biệt inputs/,code/,prepared/,runs/ khi chuyển máy. Chi tiết lần chạy: metrics.csv,results.json,config.json,verification.json,analysis.json,query_vectors.npy và hai ma trận reranker logits.']
(folder/'REPORT.vi.md').write_text('\n'.join(lines)+'\n')
(p/'RESULTS.vi.md').write_text('# Kết quả bộ mới reviewed-r1\n\nĐã hoàn tất80/80 ca. Xem [báo cáo](runs/review2-reviewed-r1-sql-20261022/REPORT.vi.md) và [metric CSV](runs/review2-reviewed-r1-sql-20261022/metrics.csv).\n\nREADME.md có lệnh chạy lại với tên mới; không cần dịch lại hoặc tải lại model.\n')
print(json.dumps({'summary':{method:summary[method]['all'] for method in methods},'losses':losses,'wins':wins,'regressions':regressions,'bootstrap':bootstrap},ensure_ascii=False,indent=2))
