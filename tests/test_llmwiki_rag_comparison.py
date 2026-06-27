from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path("scripts/eval/llmwiki_rag_comparison.py")


def load_module():
    spec = importlib.util.spec_from_file_location("llmwiki_rag_comparison", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class LlmWikiRagComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_rag_source_files_uses_fixed_agent_markdown_set(self) -> None:
        files = self.module.rag_source_files(Path("/tmp/agent-notes"))

        self.assertEqual([path.name for path in files], ["Agent.md", "MCP.md", "OpenClaw架构.md"])

    def test_fixture_can_override_vault_and_rag_sources(self) -> None:
        fixture = {
            "recommended_scope": "ios-audio-project",
            "rag_baseline": {
                "source_files": [
                    "~/.codex/sessions/2026/05/23/ios.jsonl",
                    "/tmp/audio.md",
                ]
            },
        }

        self.assertEqual(self.module.recommended_vault_id(fixture), "ios-audio-project")
        files = self.module.rag_source_files(Path("/tmp/unused"), fixture)

        self.assertEqual(files[0].name, "ios.jsonl")
        self.assertEqual(str(files[1]), "/tmp/audio.md")

    def test_build_llmwiki_report_includes_core_metrics(self) -> None:
        report = self.module.build_llmwiki_report(
            {
                "fixture": "fixture",
                "provider": "deepseek",
                "vault_id": "agent-engineering",
                "session_id": "chat_test",
                "elapsed_seconds": 1.2,
                "turn_count": 1,
                "total_tokens": 42,
                "total_tool_calls": 1,
                "turns": [
                    {
                        "turn": 1,
                        "question": "Agent Loop 是什么？",
                        "answer": "Agent Loop answer",
                        "answer_chars": 17,
                        "citation_paths": ["Agent-Loop.md"],
                        "hidden_evidence_count": 0,
                        "tool_trace": [{"tool": "query_wiki"}],
                        "stats": {"usage": {"total_tokens": 42}},
                        "elapsed_seconds": 1.0,
                    }
                ],
            }
        )

        self.assertIn("provider: deepseek", report)
        self.assertIn("vault_id: agent-engineering", report)
        self.assertIn("Agent-Loop.md", report)

    def test_build_comparison_report_reads_result_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            llmwiki = root / "llmwiki"
            rag = root / "rag"
            llmwiki.mkdir()
            rag.mkdir()
            (llmwiki / "result.json").write_text(
                """
                {
                  "fixture": "fixture",
                  "provider": "deepseek",
                  "vault_id": "agent-engineering",
                  "elapsed_seconds": 1.0,
                  "total_tool_calls": 1,
                  "turns": [
                    {
                      "turn": 1,
                      "question": "Agent Loop 是什么？",
                      "citation_paths": ["Agent-Loop.md"],
                      "stats": {"usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )
            (rag / "result.json").write_text(
                """
                {
                  "metadata": {"elapsed_seconds": 1.0, "chunk_count": 2},
                  "turns": [
                    {
                      "turn": 1,
                      "question": "Agent Loop 是什么？",
                      "retrieved_chunks": [{"source_path": "/tmp/Agent.md", "index": 0}],
                      "usage": {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10}
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            report = self.module.build_comparison_report(
                [
                    self.module.EvalRun("LLM-Wiki / deepseek", "deepseek", "llmwiki", llmwiki),
                    self.module.EvalRun("RAG-lite / deepseek", "deepseek", "rag", rag),
                ],
                root,
            )
            text = report.read_text(encoding="utf-8")
        self.assertIn("Fixed LLM-Wiki vs Markdown Chunk-RAG Evaluation", text)
        self.assertIn("Agent-Loop.md", text)
        self.assertIn("Agent.md#0", text)


if __name__ == "__main__":
    unittest.main()
