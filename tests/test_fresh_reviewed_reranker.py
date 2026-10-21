"""Offline end-to-end artifact replay; synthetic arrays are never benchmark results."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/retrieval'))
import evaluate_fresh_reviewed_reranker as runner

class FreshReplayTest(unittest.TestCase):
    def test_replay_and_reject_changed_scores(self):
        with contextlib.redirect_stdout(io.StringIO()):
            data=runner.load_inputs()
        texts=list(dict.fromkeys(c['question'] for c in data['cases']))
        queries=np.asarray([np.eye(1,768,texts.index(c['question']))[0] for c in data['cases']],dtype=np.float32)
        candidates=runner.pools(data,queries)
        matrices={a:np.tile(np.arange(30,0,-1,dtype=np.float32),(48,1)) for a in runner.ARMS}
        for n,indices in enumerate(candidates):
            for j,i in enumerate(indices):
                if data['rendered'][i]['parent-plain']!=data['rendered'][i]['plain']:
                    matrices['parent-plain'][n,j]+=0.25
                matrices['narrative-parent'][n,j]=matrices['plain' if runner.context.is_structured_table(data['rows'][i]) else 'parent-plain'][n,j]
        records,summary=runner.summarize(data,candidates,matrices)
        self.assertEqual(len(records),48)
        self.assertEqual(set(summary),{'dense_top10','candidate_pool30',*runner.ARMS})
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)
            np.save(output/'query-vectors.npy',queries)
            runner.save(output/'candidate-pools.json',candidates)
            runner.save(output/'rendered-inputs.json',data['rendered'])
            for a,m in matrices.items():np.save(output/(a+'-scores.npy'),m)
            names=[p.name for p in output.iterdir()]
            config={'status':'completed','provenance':data['provenance'],'e5_revision':runner.REVISION,
                    'reranker_revision':runner.previous.REVISION,'dtype':'float32','candidate_k':30,'final_k':10,
                    'truncated_inputs':0,'output_hashes':{n:runner.file_sha(output/n) for n in names}}
            runner.save(output/'config.json',config)
            runner.save(output/'results.json',{'configuration':config,'summary':summary,'results':records})
            with contextlib.redirect_stdout(io.StringIO()):runner.verify(data,output)
            self.assertEqual(json.loads((output/'verification.json').read_text())['scores_verified'],4320)
            matrices['plain'][0,0]+=10
            np.save(output/'plain-scores.npy',matrices['plain'])
            with self.assertRaisesRegex(ValueError,'Changed output'):runner.verify(data,output)
            matrices['plain'][0,0]-=10
            np.save(output/'plain-scores.npy',matrices['plain'])
            report=json.loads((output/'results.json').read_text())
            report['results'][0]['plain_ranking'][0]='wrong-anchor'
            runner.save(output/'results.json',report)
            with self.assertRaisesRegex(ValueError,'Saved ranking'):runner.verify(data,output)

if __name__=='__main__':unittest.main()