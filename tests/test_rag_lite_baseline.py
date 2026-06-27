from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path("scripts/eval/rag_lite_baseline.py")


def load_module():
    spec = importlib.util.spec_from_file_location("rag_lite_baseline", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RagLiteBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_load_fixture_reads_six_turns(self) -> None:
        fixture = self.module.load_fixture(Path("tests/fixtures/chat/agent_architecture_6turn_mixed.json"))

        self.assertEqual(fixture.id, "agent_architecture_6turn_mixed")
        self.assertEqual(len(fixture.turns), 6)
        self.assertIn("Agent Loop", fixture.turns[0].question)

    def test_tokenize_handles_cjk_and_technical_terms(self) -> None:
        tokens = self.module.tokenize("Agent Loop 和 MCP/JSON-RPC 多路由调度")

        self.assertIn("agent", tokens)
        self.assertIn("loop", tokens)
        self.assertIn("mcp", tokens)
        self.assertIn("json-rpc", tokens)
        self.assertIn("多路", tokens)

    def test_build_chunks_and_bm25_search_raw_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            agent = root / "Agent.md"
            agent.write_text(
                "# Agent Loop\n\nAgent Loop 是智能体执行循环，包含推理、工具调用和观察。\n\n## Memory\n\n长期记忆保存用户偏好。",
                encoding="utf-8",
            )
            mcp = root / "MCP.md"
            mcp.write_text("# MCP\n\nMCP 是工具上下文协议，和 JSON-RPC 相关。", encoding="utf-8")

            chunks = self.module.build_chunks([agent, mcp], target_chars=80, overlap_chars=10)
            results = self.module.bm25_search(chunks, "Agent Loop 工具调用", top_k=3)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(results)
        self.assertEqual(results[0].chunk.source_path, str(agent))

    def test_build_report_includes_inputs_and_turns(self) -> None:
        metadata = {
            "fixture": "fixture",
            "preset": "none",
            "input_files": [{"source": "Agent.md", "size": 10}],
            "chunk_count": 2,
            "chunk_chars": 1000,
            "overlap_chars": 100,
            "top_k": 3,
            "retrieval_only": True,
            "elapsed_seconds": 0.1,
        }
        report = self.module.build_report(
            metadata,
            [
                {
                    "turn": 1,
                    "question": "Agent Loop 是什么？",
                    "expected_pages": ["Agent-Loop.md"],
                    "retrieved_chunks": [
                        {
                            "source_path": "Agent.md",
                            "index": 0,
                            "score": 1.2,
                            "title": "Agent Loop",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
                }
            ],
        )

        self.assertIn("RAG-lite Baseline Report", report)
        self.assertIn("total_tokens: 12", report)
        self.assertIn("Agent.md", report)
        self.assertIn("Agent-Loop.md", report)


if __name__ == "__main__":
    unittest.main()
