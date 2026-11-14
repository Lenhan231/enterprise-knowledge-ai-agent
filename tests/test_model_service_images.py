"""Service images must copy the source files imported by their runtime branch."""
import ast
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
# Entry modules per SERVICE_KIND: core.services.runtime imports these inside its lifespan and handlers.
SERVICES = {
    "embeddings": ["core.services.runtime", "core.embeddings.embedding_service", "core.embeddings.settings"],
    "reranker": ["core.services.runtime", "core.retrieval.reranker"],
    "retrieval": ["core.services.runtime", "core.retrieval.retrieval_service"],
}
# runtime.py imports unrelated service branches lazily; each image copies only its own branch.
OTHER_BRANCHES = {
    "embeddings": ("document_processing", "core.retrieval"),
    "reranker": ("document_processing", "core.embeddings", "core.retrieval"),
    "retrieval": ("document_processing",),
}


def module_file(module):
    base = SRC.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def local_imports(path, package, skip=()):
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = ".".join(package.split(".")[: len(package.split(".")) - node.level + 1] + ([module] if module else []))
            names = [module] + [f"{module}.{alias.name}" for alias in node.names]
        else:
            continue
        found |= {n for n in names if n.split(".")[0] in ("core", "document_processing", "app") and not n.startswith(skip)}
    return found


def needed_files(entries, service):
    files, todo = set(), list(entries)
    while todo:
        parts = todo.pop().split(".")
        for i in range(1, len(parts) + 1):  # parent packages' __init__ files run first
            module = ".".join(parts[:i])
            path = module_file(module)
            if path and path not in files:
                files.add(path)
                package = module if path.name == "__init__.py" else ".".join(parts[: i - 1])
                skip = OTHER_BRANCHES[service] if module == "core.services.runtime" else ()
                todo += local_imports(path, package, skip)
    return {p.relative_to(ROOT).as_posix() for p in files}


def copied_files(dockerfile):
    copied = set()
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*COPY\s+(.+)\s+\S+\s*$", line)
        if not match:
            continue
        for source in match[1].split():
            path = ROOT / source
            copied |= {p.relative_to(ROOT).as_posix() for p in path.rglob("*.py")} if path.is_dir() else {source}
    return copied


class ModelServiceImagesTest(unittest.TestCase):
    def test_each_image_copies_every_source_file_it_imports(self):
        for service, entries in SERVICES.items():
            with self.subTest(service=service):
                missing = needed_files(entries, service) - copied_files(ROOT / "docker" / f"Dockerfile.{service}")
                self.assertFalse(missing, f"add to docker/Dockerfile.{service}: {sorted(missing)}")


if __name__ == "__main__":
    unittest.main()
