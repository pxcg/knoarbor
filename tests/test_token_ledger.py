from knoarbor.audit.token_ledger import build_ingest_token_records, build_token_analysis


def test_build_ingest_token_records_from_segment_metrics():
    record = {
        "run_id": "run-1",
        "started_at": "2026-01-01 00:00:00",
        "finished_at": "2026-01-01 00:00:10",
        "sources": [
            {
                "connector": "codex",
                "source_id": "codex:1",
                "source_file": "raw/chats/example.jsonl",
                "status": "processed",
                "mode": "new_source",
                "segments": [
                    {
                        "index": 0,
                        "title": "turns 1-3",
                        "chars": 1200,
                        "generated_pages": ["concepts/Agent-Loop.md"],
                        "metrics": {
                            "semantic": {
                                "calls": [
                                    {
                                        "contract_name": "wiki_page_plan",
                                        "provider": "deepseek",
                                        "model": "deepseek-v4-flash",
                                        "prompt_tokens": 100,
                                        "prompt_cached_tokens": 40,
                                        "prompt_stable_chars": 1000,
                                        "prompt_dynamic_chars": 2500,
                                        "payload_char_total": 1800,
                                        "payload_top_field": "knowledge_extract",
                                        "payload_char_breakdown": {
                                            "knowledge_extract": 1200,
                                            "wiki_context": 600,
                                        },
                                        "completion_tokens": 20,
                                        "total_tokens": 120,
                                        "elapsed_seconds": 2.0,
                                    }
                                ]
                            }
                        },
                    }
                ],
            }
        ],
    }

    rows = build_ingest_token_records(record)

    assert len(rows) == 1
    assert rows[0]["flow"] == "ingest"
    assert rows[0]["agent"] == "wiki_page_plan"
    assert rows[0]["source_file"] == "raw/chats/example.jsonl"
    assert rows[0]["page_paths"] == ["concepts/Agent-Loop.md"]
    assert rows[0]["prompt_cache_rate"] == 0.4
    assert rows[0]["prompt_stable_chars"] == 1000
    assert rows[0]["prompt_dynamic_chars"] == 2500
    assert rows[0]["dynamic_to_stable_ratio"] == 2.5
    assert rows[0]["payload_char_total"] == 1800
    assert rows[0]["payload_top_field"] == "knowledge_extract"
    assert rows[0]["payload_char_breakdown"]["knowledge_extract"] == 1200


def test_build_token_analysis_groups_by_flow_agent_source_and_page():
    records = [
        {
            "flow": "ingest",
            "agent": "wiki_page_plan",
            "source_file": "raw/a.md",
            "connector": "markdown",
            "model": "m",
            "page_paths": ["concepts/A.md"],
            "prompt_tokens": 100,
            "prompt_cached_tokens": 25,
            "prompt_stable_chars": 1000,
            "prompt_dynamic_chars": 4500,
            "payload_char_total": 4000,
            "payload_top_field": "wiki_context",
            "payload_char_breakdown": {"wiki_context": 3000, "knowledge_extract": 1000},
            "completion_tokens": 20,
            "total_tokens": 120,
            "elapsed_seconds": 2.0,
        },
        {
            "flow": "lint",
            "agent": "lint_diagnose",
            "source_file": "",
            "connector": "",
            "model": "m",
            "page_paths": ["concepts/A.md"],
            "prompt_tokens": 50,
            "prompt_cached_tokens": 0,
            "prompt_stable_chars": 1000,
            "prompt_dynamic_chars": 1000,
            "payload_char_total": 800,
            "payload_top_field": "lint_context",
            "payload_char_breakdown": {"lint_context": 800},
            "completion_tokens": 10,
            "total_tokens": 60,
            "elapsed_seconds": 1.0,
        },
    ]

    analysis = build_token_analysis(records)

    assert analysis["totals"]["total_tokens"] == 180
    assert analysis["totals"]["prompt_stable_chars"] == 2000
    assert analysis["totals"]["prompt_dynamic_chars"] == 5500
    assert analysis["totals"]["dynamic_to_stable_ratio"] == 2.75
    assert analysis["by_flow"][0]["name"] == "ingest"
    assert analysis["by_agent"][0]["name"] == "wiki_page_plan"
    assert analysis["by_page"][0]["name"] == "concepts/A.md"
    assert analysis["by_payload_field"][0]["name"] == "wiki_context"
    assert analysis["by_payload_field"][0]["payload_chars"] == 3000
    assert len(analysis["cache_diagnostics"]["low_cache_calls"]) == 1
    assert len(analysis["cache_diagnostics"]["high_dynamic_calls"]) == 1
