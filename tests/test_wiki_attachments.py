from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from knoarbor.services.wiki_attachments import attachments_for_wiki_page


class WikiAttachmentEvidenceTests(unittest.TestCase):
    def test_resolves_renderable_attachment_from_source_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "wiki" / "sources").mkdir(parents=True)
            (vault / "raw" / "normalized" / "markdown").mkdir(parents=True)
            (vault / "raw" / "sidecars" / "sources").mkdir(parents=True)

            raw_source = vault / "raw" / "normalized" / "markdown" / "AC1中文.md"
            raw_source.write_text("# AC1", encoding="utf-8")
            (vault / "wiki" / "sources" / "AC1-Source-Digest.md").write_text(
                "\n".join(
                    [
                        "# AC1 Source Digest",
                        "",
                        "- Raw source: raw/normalized/markdown/AC1中文.md",
                        "- Source digest ids: sd_ac1",
                    ]
                ),
                encoding="utf-8",
            )
            (vault / "raw" / "sidecars" / "sources" / "AC1中文.attachments.json").write_text(
                json.dumps(
                    {
                        "schema_version": "knoarbor.attachments.v1",
                        "source": "test",
                        "attachments": [
                            {
                                "attachment_type": "image",
                                "name": "hashy-name.jpg",
                                "description": "3D FOV rendering.",
                                "relative_path": "images/ac1-fov.jpg",
                                "mime_type": "image/jpeg",
                                "metadata": {"topic": "图2 AC1 激光雷达 FOV 分布图"},
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            page_content = "\n".join(
                [
                    "# AC1",
                    "",
                    "## Evidence",
                    "",
                    "| Claim | Source | Range | Basis | Confidence |",
                    "|---|---|---|---|---|",
                    "| C1 | sd_ac1 | unit:0 | AC1 includes a LiDAR FOV diagram. | high |",
                    "",
                    "## Attachments",
                    "",
                    "| Topic | Description |",
                    "|---|---|",
                    "| 图2 AC1 激光雷达 FOV 分布图 | 说明激光雷达 FOV 覆盖范围。 |",
                ]
            )

            attachments = attachments_for_wiki_page(vault, page_content)

            self.assertEqual(len(attachments), 1)
            self.assertEqual(attachments[0]["topic"], "图2 AC1 激光雷达 FOV 分布图")
            self.assertEqual(attachments[0]["path"], "raw/assets/images/ac1-fov.jpg")
            self.assertTrue(
                attachments[0]["markdown_src"].startswith("/ui/api/vault-assets/images%2Fac1-fov.jpg?vault_path=")
            )

    def test_falls_back_to_page_topic_matching_when_digest_id_changed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "raw" / "normalized" / "markdown").mkdir(parents=True)
            (vault / "raw" / "sidecars" / "sources").mkdir(parents=True)
            raw_source = vault / "raw" / "normalized" / "markdown" / "AC1中文.md"
            raw_source.write_text("# AC1", encoding="utf-8")
            (vault / "raw" / "sidecars" / "sources" / "AC1中文.attachments.json").write_text(
                json.dumps(
                    {
                        "schema_version": "knoarbor.attachments.v1",
                        "source": "test",
                        "attachments": [
                            {
                                "attachment_type": "image",
                                "name": "image.jpg",
                                "description": "Interface diagram.",
                                "relative_path": "images/ac1-interface.jpg",
                                "metadata": {"topic": "图4 AC1 接口示意图"},
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            attachments = attachments_for_wiki_page(vault, "## Attachments\n\n| 图4 AC1 接口示意图 | 端口布局 |")

            self.assertEqual(len(attachments), 1)
            self.assertEqual(attachments[0]["path"], "raw/assets/images/ac1-interface.jpg")
            self.assertTrue(
                attachments[0]["markdown_src"].startswith(
                    "/ui/api/vault-assets/images%2Fac1-interface.jpg?vault_path="
                )
            )


if __name__ == "__main__":
    unittest.main()
