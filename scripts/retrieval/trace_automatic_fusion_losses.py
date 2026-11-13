"""Replay saved automatic queries and trace fusion losses; no translation calls."""
import hashlib,json,sys
from pathlib import Path
from datetime import datetime,timezone
from statistics import mean
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts/retrieval')]
from evaluate_bilingual_two_document_benchmark import fuse
from core.database.document_chunks_repository import DocumentChunkRepository
from core.evaluation.retrieval_metrics import recall_at_k,reciprocal_rank
from core.retrieval.retrieval import make_chunk_id


def main():
    folder=ROOT/'artifacts/evaluation/retrieval'
    saved=json.loads((folder/'scoped-automatic-translation.json').read_text())
    ids=saved['scope']['document_ids'];scopes=saved['configuration']['lexical_document_scopes']
    repo=DocumentChunkRepository()
    try:
        repo.conn.rollback();repo.conn.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        repo.conn.execute("SET LOCAL statement_timeout='30s'")
        rows=repo.conn.execute("SELECT c.chunk_index,c.content,c.metadata,c.embedding::text,d.document_id,d.allowed_roles,d.fiscal_year,d.company FROM document_chunks c JOIN documents d ON d.document_id=c.metadata->>'document_id' WHERE d.document_id=ANY(%s::text[]) AND coalesce(d.processing_status,'ready')='ready' ORDER BY d.document_id,c.chunk_index,c.id",(ids,)).fetchall()
        assert hashlib.sha256(json.dumps(rows,ensure_ascii=False,default=str).encode()).hexdigest()==saved['corpus_sha256'],'Corpus changed'
        text={make_chunk_id(row[4],row[0]):row[1] for row in rows}
        metadata={make_chunk_id(row[4],row[0]):row[2] for row in rows}
        from langchain_huggingface import HuggingFaceEmbeddings
        embedding=HuggingFaceEmbeddings(model_name=saved['embedding_model'],model_kwargs={'device':'cuda'})
        by={(x['language'],x['id'],x['method']):x for x in saved['results']}
        traces=[];matches=0
        for original in [x for x in saved['results'] if x['method'].endswith('_bm25')]:
            lang=original['language'];qid=original['id'];gold=set(original['gold_chunk_ids'])
            hybrid_saved=by[lang,qid,'automatic_language_aware_hybrid']
            components={}
            for qlang in ('en','vn'):
                chunks=repo.similarity_search(None,100,query=original['lexical_queries'][qlang],method='bm25',document_ids=scopes[qlang],roles=['admin'])
                components[qlang]=[make_chunk_id(c.document_id,c.chunk_index) for c in chunks]
            lexical=fuse(list(components.values()),[1.0,1.0])
            vector=embedding.embed_query(original['question'])
            chunks=repo.similarity_search(vector,len(rows),query=original['question'],method='dense',document_ids=ids,roles=['admin'])
            dense_all=[make_chunk_id(c.document_id,c.chunk_index) for c in chunks];dense=dense_all[:100]
            hybrid=fuse([dense,lexical[:100]],[1.0,2.0])
            assert lexical[:10]==original['ranked_chunk_ids'],(lang,qid,'lexical differs')
            assert hybrid[:10]==hybrid_saved['ranked_chunk_ids'],(lang,qid,'hybrid differs')
            matches+=1
            lost=(gold & set(lexical[:10]))-set(hybrid[:10]);gained=(gold & set(hybrid[:10]))-set(lexical[:10])
            def detail(chunk_id):
                dr=dense_all.index(chunk_id)+1 if chunk_id in dense_all else None
                lr=lexical.index(chunk_id)+1 if chunk_id in lexical else None
                ds=1.0/(60+dr) if dr is not None and dr<=100 else 0.0
                ls=2.0/(60+lr) if lr is not None and lr<=100 else 0.0
                return {'chunk_id':chunk_id,'dense_rank_full_corpus':dr,'dense_rank_top100':dr if dr is not None and dr<=100 else None,'english_bm25_rank':components['en'].index(chunk_id)+1 if chunk_id in components['en'] else None,'vietnamese_bm25_rank':components['vn'].index(chunk_id)+1 if chunk_id in components['vn'] else None,'bilingual_bm25_rank':lr,'hybrid_rank':hybrid.index(chunk_id)+1 if chunk_id in hybrid else None,'dense_rrf':ds,'lexical_rrf':ls,'combined_rrf':ds+ls,'page_number':metadata[chunk_id].get('page_number'),'text_excerpt':text[chunk_id][:1000]}
            row={'id':qid,'language':lang,'question':original['question'],'lexical_queries':original['lexical_queries'],'lost_gold':[detail(c) for c in sorted(lost)],'gained_gold':[detail(c) for c in sorted(gained)],'bm25_recall':recall_at_k(gold,lexical,10),'hybrid_recall':recall_at_k(gold,hybrid,10),'hybrid_top10_english_chunks':sum(c.rsplit('::chunk::',1)[0]==ids[0] for c in hybrid[:10])}
            if lost or gained:
                row['hybrid_top10']=[detail(c) for c in hybrid[:10]]
                row['bm25_top10']=[detail(c) for c in lexical[:10]]
                row['gold_evidence']=[detail(c) for c in sorted(gold)]
            traces.append(row)
            print(lang,qid,'lost',[(x['bilingual_bm25_rank'],x['dense_rank_full_corpus'],x['hybrid_rank']) for x in row['lost_gold']],flush=True)
        report={'created_at':datetime.now(timezone.utc).isoformat(),'source_artifact':'scoped-automatic-translation.json','source_sha256':hashlib.sha256((folder/'scoped-automatic-translation.json').read_bytes()).hexdigest(),'corpus_sha256':saved['corpus_sha256'],'embedding_model':saved['embedding_model'],'scope':saved['scope'],'reproduced_cases':matches,'protocol':'Read-only snapshot; saved generated translations reused exactly; no API translation or answer generation; full dense ranks traced and top100 used for original fusion. Gold labels used only for analysis, not ranking.','results':traces}
        (folder/'automatic-fusion-loss-investigation-20261016.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print('Completed',matches,'exact lexical and hybrid ranking reproductions',flush=True)
    finally:repo.close()


if __name__=='__main__':main()