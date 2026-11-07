"""Structural/oracle and artifact replay checks; no model inference/network."""
import copy
import importlib.util
import json
from pathlib import Path
import numpy as np
import unittest
import tempfile
from unittest.mock import patch

spec=importlib.util.spec_from_file_location("heldout_runner",Path(__file__).with_name("run.py"))
bundle=importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)

def exact_source_and_two_chunk_oracles(data):
    qrels,audit=bundle.gold(data)
    assert len(qrels)==40
    assert sum(row["multi_chunk_checked"] for row in audit)==10
    assert len(data["cases"])==80

def changed_frozen_input_rejected(tmp_path):
    (tmp_path/"frozen.txt").write_text("original")
    bundle.save(tmp_path/"manifest.json",{"files":{"frozen.txt":bundle.sha(tmp_path/"frozen.txt")}})
    (tmp_path/"frozen.txt").write_text("changed")
    with patch.object(bundle,"HOME",tmp_path), unittest.TestCase().assertRaisesRegex(ValueError,"Changed frozen input"):
        bundle.load()

def synthetic_artifact_replay_and_corruption(data,tmp_path):
    # These arbitrary candidates/logits are fixtures, never benchmark predictions.
    (tmp_path/"prepared").mkdir()
    bundle.save(tmp_path/"prepared/manifest.json",{"files":{}})
    output=tmp_path/"synthetic";output.mkdir()
    qrels,_=bundle.gold(data)
    scores=np.tile(np.arange(30,dtype=np.float32),(80,1))
    vectors=np.zeros((80,768),dtype=np.float32);vectors[:,0]=1
    np.save(output/"query_vectors.npy",vectors)
    for method in ("dense_bge","translated_hybrid_bge"):
        np.save(output/(method+"-scores.npy"),scores)
    records=[]
    for case in data["cases"]:
        candidates=[key for key,row in data["byid"].items() if row["language"]==case["target_language"]][:30]
        methods={}
        for method in ("dense","dense_bge","translated_hybrid_raw","translated_hybrid_bge"):
            ranking=list(reversed(candidates)) if method.endswith("bge") else candidates
            methods[method]={**bundle.values(data,case,ranking,qrels[(case["intent_id"],case["target_language"])]),"candidates":candidates,"ranking":ranking,"latency_ms":1.0}
        records.append({**case,"methods":methods})
    config={"status":"completed","dataset_manifest_sha256":bundle.sha(tmp_path/"manifest.json"),"prepared_manifest_sha256":bundle.sha(tmp_path/"prepared/manifest.json"),"output_hashes":{name:bundle.sha(output/name) for name in ("query_vectors.npy","dense_bge-scores.npy","translated_hybrid_bge-scores.npy")}}
    report={"configuration":config,"results":records,"summary":bundle.summaries(records)}
    bundle.save(output/"config.json",config);bundle.save(output/"results.json",report)
    bundle.verify_run(data,output)
    assert bundle.read(output/"verification.json")["status"]=="passed"
    altered=copy.deepcopy(report);ranking=altered["results"][0]["methods"]["dense_bge"]["ranking"]
    ranking[0],ranking[1]=ranking[1],ranking[0]
    bundle.save(output/"results.json",altered)
    with unittest.TestCase().assertRaisesRegex(ValueError,"Ranking/logit replay mismatch"):
        bundle.verify_run(data,output)
    bundle.save(output/"results.json",report)
    changed=copy.deepcopy(report)
    del changed["results"][0]["methods"]["dense"]
    bundle.save(output/"results.json",changed)
    with unittest.TestCase().assertRaisesRegex(ValueError,"Missing benchmark method"):
        bundle.verify_run(data,output)


class BundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=bundle.load()
    def test_exact_source_and_two_chunk_oracles(self):
        exact_source_and_two_chunk_oracles(self.data)
    def test_changed_frozen_input_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            changed_frozen_input_rejected(Path(folder))
    def test_synthetic_artifact_replay_and_corruption(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(bundle,"HOME",Path(folder)):
            # Synthetic fixture uses a real manifest only as an immutable version identifier.
            (Path(folder)/"manifest.json").write_bytes(Path(__file__).with_name("manifest.json").read_bytes())
            synthetic_artifact_replay_and_corruption(self.data,Path(folder))

if __name__=="__main__":unittest.main()
