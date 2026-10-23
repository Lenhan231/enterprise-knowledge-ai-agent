"""Offline replay/SQL-formula checks; no API, database or GPU inference."""
import contextlib
import copy
import io
import math
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/retrieval'))
import evaluate_translated_fresh_reranker as runner
from fresh_translated_candidates import bm25_scores,build_candidates,FrozenRepository

class TranslatedReplayTest(unittest.TestCase):
    def test_bm25_and_scope(self):
        terms=[{'a':2},{'b':1},{}]
        values=dict(bm25_scores([0,1,2],terms,['a','a']))
        expected=math.log(1+(3-1+.5)/(1+.5))*(2*2.2)/(2+1.2*(.25+.75*2/1))
        self.assertEqual(set(values),{0})
        self.assertAlmostEqual(values[0],expected)
        self.assertEqual(bm25_scores([1,2],terms,['a']),[])
        self.assertEqual(bm25_scores([],terms,['a']),[])
    def test_failed_translation_falls_back_and_filters_hold(self):
        with contextlib.redirect_stdout(io.StringIO()):data=runner.load()
        translation=copy.deepcopy(runner.base.frozen.read(runner.INPUT/'translations.json'))
        translation['records'][0]['error']='SyntheticFailure'
        lexical=runner.base.frozen.read(runner.INPUT/'lexical-inputs.json')
        queries=np.load(runner.BASELINE/'query-vectors.npy',allow_pickle=False)
        pools,details=build_candidates(data['rows'],data['vectors'],queries,data['cases'],lexical['document_terms'],lexical['query_terms'],translation)
        self.assertEqual(pools[:2],data['candidates']['dense'][:2])
        self.assertTrue(all(r['retrieval_details']['dense_fallback'] for r in details[:2]))
        repo=FrozenRepository(data['rows'],data['vectors'],lexical['document_terms'],lexical['query_terms'])
        self.assertEqual(repo.similarity_search(queries[0],5,query=data['cases'][0]['question'],method='dense',roles=['no_such_role']),[])
        self.assertEqual(repo.similarity_search(queries[0],5,query=data['cases'][0]['question'],method='dense',roles=['admin'],document_ids=[]),[])
    def test_full_saved_replay_rejects_wrong_rank(self):
        with contextlib.redirect_stdout(io.StringIO()):data=runner.load()
        # Synthetic logits keyed by original anchor identity; no model used.
        matrices={arm:np.asarray([[10000-i for i in indices] for indices in data['candidates'][arm]],dtype=np.float32) for arm in runner.ARMS}
        records,summary=runner.summarize(data,matrices)
        self.assertEqual(len(records),48)
        self.assertEqual(set(summary),{'dense_top10','dense','translated_hybrid','dense_candidate30','translated_hybrid_candidate30'})
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            for a,m in matrices.items():np.save(out/(a+'-scores.npy'),m)
            config={'status':'completed','provenance':data['translated_provenance'],'revision':runner.base.previous.REVISION,
                    'dtype':'float32','truncated_inputs':0,'candidate_k':30,'final_k':10,'output_hashes':{a+'-scores.npy':runner.base.file_sha(out/(a+'-scores.npy')) for a in runner.ARMS}}
            runner.base.save(out/'config.json',config);runner.base.save(out/'results.json',{'configuration':config,'summary':summary,'results':records})
            with contextlib.redirect_stdout(io.StringIO()):runner.verify(data,out)
            records[0]['translated_hybrid_ranking'][0]='wrong-anchor'
            runner.base.save(out/'results.json',{'configuration':config,'summary':summary,'results':records})
            with self.assertRaisesRegex(ValueError,'Ranking/evidence'):runner.verify(data,out)

if __name__=='__main__':unittest.main()