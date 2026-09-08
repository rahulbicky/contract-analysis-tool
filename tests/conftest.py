import os
import sys
import types
from unittest.mock import MagicMock

SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, SRC_DIR)

# sentence-transformers and unstructured pull in heavy native/ML dependencies
# (torch, poppler, etc.) that aren't needed to test our own logic — stub them
# out so tests don't require the full ML stack to be installed.
if "sentence_transformers" not in sys.modules:
    stub = types.ModuleType("sentence_transformers")
    stub.CrossEncoder = MagicMock()
    sys.modules["sentence_transformers"] = stub

if "unstructured.partition.pdf" not in sys.modules:
    unstructured_stub = types.ModuleType("unstructured")
    partition_stub = types.ModuleType("unstructured.partition")
    partition_pdf_stub = types.ModuleType("unstructured.partition.pdf")
    partition_pdf_stub.partition_pdf = MagicMock()
    sys.modules["unstructured"] = unstructured_stub
    sys.modules["unstructured.partition"] = partition_stub
    sys.modules["unstructured.partition.pdf"] = partition_pdf_stub

os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("CONTRACTLENS_API_KEY", "test-api-key")
