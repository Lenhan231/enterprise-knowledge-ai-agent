import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class KaggleNotebookTest(unittest.TestCase):
    def load(self, name):
        return json.loads((ROOT / "notebooks" / name).read_text(encoding="utf-8"))

    def test_benchmark_notebooks_find_the_attached_dataset_by_mount_contents(self):
        for name in ("kaggle_ocr_benchmark.ipynb", "kaggle_embedding_benchmark.ipynb"):
            with self.subTest(notebook=name):
                notebook = self.load(name)
                code = ["".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"]
                setup = [cell for cell in code if "assets_candidates" in cell]
                self.assertEqual(len(setup), 1)
                if name == "kaggle_embedding_benchmark.ipynb":
                    self.assertIn('input_root.rglob("project")', setup[0])
                    self.assertIn('"evaluate_embeddings.py"', setup[0])
                else:
                    self.assertIn('input_root.glob("*/project")', setup[0])
                    self.assertIn('input_root.glob("datasets/*/*/project")', setup[0])
                self.assertNotIn('"/kaggle/input/datasets/', "".join(code))
                self.assertIn("scripts", setup[0])

    def test_embedding_notebook_imports_runner_dependencies_and_checks_cuda(self):
        notebook = self.load("kaggle_embedding_benchmark.ipynb")
        code = ["".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"]
        all_code = "\n".join(code)
        self.assertIn("import subprocess, sys", all_code)
        self.assertIn("sentence-transformers==6.0.1", all_code)
        self.assertIn("torch.cuda.is_available()", all_code)
        self.assertNotIn('"/kaggle/input/datasets/', all_code)

    def test_tesseract_notebook_path_does_not_require_cuda(self):
        notebook = self.load("kaggle_ocr_benchmark.ipynb")
        all_code = "\n".join(
            "".join(cell["source"])
            for cell in notebook["cells"] if cell["cell_type"] == "code"
        )
        self.assertIn('ENGINE in {"easyocr", "surya"}', all_code)
        self.assertIn("REQUIRE_GPU and not cuda_available", all_code)
        self.assertIn("REQUIRE_GPU = False", all_code)
        self.assertIn('ENGINE == "tesseract"', all_code)

    def test_ocr_notebook_uses_reviewed_v7_dataset_and_psm_pairing(self):
        notebook = self.load("kaggle_ocr_benchmark.ipynb")
        source = "\n".join(
            "".join(cell["source"])
            for cell in notebook["cells"]
        )
        self.assertIn("vinamilk_ocr_ground_truth_v7.json", source)
        self.assertIn("four additional English physical-scan regions", source)
        self.assertIn("ltrngnhn/vinamilk-ocr-v7-benchmark-assets", source)
        self.assertIn("TESSERACT_PSM = 3", source)
        self.assertIn("--tesseract-psm", source)
        self.assertIn("set `REQUIRE_GPU = False`", source)
        self.assertNotIn("vinamilk-proposal-benchmark-assets", source)

    def test_paddle_notebook_uses_official_cpu_wheel_with_retries(self):
        notebook = self.load("kaggle_ocr_benchmark.ipynb")
        all_code = "\n".join(
            "".join(cell["source"])
            for cell in notebook["cells"] if cell["cell_type"] == "code"
        )
        self.assertIn("paddlepaddle==3.3.0", all_code)
        self.assertIn("packages/stable/cpu/", all_code)
        self.assertIn("--default-timeout=300", all_code)
        self.assertIn("--retries=5", all_code)

    def test_cpu_paddle_notebook_does_not_require_nvidia_smi(self):
        notebook = self.load("kaggle_ocr_benchmark.ipynb")
        code = "\n".join(
            "".join(cell["source"])
            for cell in notebook["cells"] if cell["cell_type"] == "code"
        )
        self.assertIn('if shutil.which("nvidia-smi"):', code)
        self.assertIn('    subprocess.run(["nvidia-smi"], check=False)', code)

    def test_surya_notebook_pins_compatible_transformers_and_t4_batches(self):
        notebook = self.load("kaggle_ocr_benchmark.ipynb")
        all_code = "\n".join(
            "".join(cell["source"])
            for cell in notebook["cells"] if cell["cell_type"] == "code"
        )
        self.assertIn("transformers==4.57.3", all_code)
        self.assertIn('os.environ["DETECTOR_BATCH_SIZE"] = "16"', all_code)
        self.assertIn('os.environ["RECOGNITION_BATCH_SIZE"] = "128"', all_code)

    def test_ocr_notebook_uses_attached_source_pdfs_without_live_downloads(self):
        notebook = self.load("kaggle_ocr_benchmark.ipynb")
        all_code = "\n".join(
            "".join(cell["source"])
            for cell in notebook["cells"] if cell["cell_type"] == "code"
        )
        self.assertIn("Missing benchmark source PDF", all_code)
        self.assertNotIn("download_vietnam_enterprise_corpus.py", all_code)

    def test_code_cells_are_valid_python_after_removing_notebook_magics(self):
        for name in ("kaggle_ocr_benchmark.ipynb", "kaggle_embedding_benchmark.ipynb"):
            notebook = self.load(name)
            for index, cell in enumerate(notebook["cells"]):
                if cell["cell_type"] != "code":
                    continue
                source = "".join(cell["source"])
                source = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("%"))
                with self.subTest(notebook=name, cell=index):
                    compile(source, f"{name}:cell-{index}", "exec")


if __name__ == "__main__":
    unittest.main()
