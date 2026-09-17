#!/usr/bin/env python3
"""extract_narration: 교육 22클립 + 동적 엔딩 id 검증."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from extract_narration import (  # noqa: E402
    build_items,
    ending_id,
    scene_label,
)


EDU_HTML = ROOT / "education" / "why-ai-bots.html"
EDU_NARRATION = ROOT / "samples" / "narration.education-22.json"
SOURCE_JSON = Path("/workspace/aistory-22clips.json")


class EndingIdTests(unittest.TestCase):
    def test_dynamic_ending_ids(self):
        self.assertEqual(ending_id(15), "16-ending")
        self.assertEqual(ending_id(16), "17-ending")
        self.assertEqual(ending_id(20), "21-ending")


class SceneLabelTests(unittest.TestCase):
    def test_keeps_chapter_prefixed_year(self):
        self.assertEqual(scene_label(1, "1장 · 표지"), "1장 · 표지")

    def test_prefixes_plain_year(self):
        self.assertEqual(scene_label(3, "1956년 · 다트머스"), "3장 · 1956년 · 다트머스")


class Education22ExtractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EDU_HTML.exists():
            raise unittest.SkipTest(f"missing {EDU_HTML}")
        html = EDU_HTML.read_text(encoding="utf-8")
        cls.items, cls.title = build_items(html)

    def test_clip_count_and_ids(self):
        ids = [i["id"] for i in self.items]
        self.assertEqual(len(ids), 22)
        self.assertEqual(ids[0], "00-opening")
        self.assertEqual(ids[-1], "21-ending")
        self.assertEqual(
            ids[1:-1],
            [f"{i:02d}-scene" for i in range(1, 21)],
        )

    def test_matches_committed_sample_narration(self):
        if not EDU_NARRATION.exists():
            self.skipTest("sample narration not generated yet")
        sample = json.loads(EDU_NARRATION.read_text(encoding="utf-8"))
        self.assertEqual(
            [i["id"] for i in sample["items"]],
            [i["id"] for i in self.items],
        )
        for a, b in zip(sample["items"], self.items):
            self.assertEqual(a["lines"], b["lines"], a["id"])

    def test_matches_source_of_truth_json(self):
        if not SOURCE_JSON.exists():
            self.skipTest("workspace source JSON not present")
        src = json.loads(SOURCE_JSON.read_text(encoding="utf-8"))
        self.assertEqual(len(src), 22)
        for a, b in zip(src, self.items):
            self.assertEqual(a["id"], b["id"])
            self.assertEqual(a["lines"], b["lines"], a["id"])

    def test_clip16_grok_bot_wording(self):
        line = self.items[16]["lines"][0]
        self.assertIn("Grok Bot은", line)
        self.assertNotIn("Grok는", line)


class TinyHtmlDynamicEndingTests(unittest.TestCase):
    def test_two_scenes_yield_03_ending(self):
        html = """<!doctype html><html><head><title>T · Tiny</title></head><body>
<script>
const OPENING_TEXT = '오프닝 문장.';
const ENDING_TEXT = '엔딩 문장.';
const SCENES = [
  {
    year: '1장 · A',
    title: 'A',
    lines: [
      '첫째 장.'
    ]
  },
  {
    year: '2장 · B',
    title: 'B',
    lines: [
      '둘째 장.'
    ]
  }
];
</script></body></html>
"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.html"
            path.write_text(html, encoding="utf-8")
            items, title = build_items(path.read_text(encoding="utf-8"))
        self.assertEqual(title, "Tiny")
        self.assertEqual([i["id"] for i in items], ["00-opening", "01-scene", "02-scene", "03-ending"])
        self.assertEqual(items[0]["lines"], ["오프닝 문장."])
        self.assertEqual(items[-1]["lines"], ["엔딩 문장."])


if __name__ == "__main__":
    unittest.main()
