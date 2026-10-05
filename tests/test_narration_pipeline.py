"""Standard-library regression tests. No model, network or real audio writes."""

import copy
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_aistory
from extract_narration import (SPOKEN, audio_status, json_text, kor_num,
                               narration_from_html, narration_from_source,
                               numbers_to_spoken, parse_scenes, strip_tags,
                               text_sha256, to_spoken, validate_narration)
from tools.export_narration import make_bundle, write_bundle


def fixture():
    return {
        "OPENING_PARAS": ["첫 인사예요.", "AI 이야기예요."],
        "CHAPTERS": [("1950년", "질문", [], ["1950년 이야기에요."]),
                     ("2026년", "배움", [], ["수츠케버와 AMI Labs 이야기예요."])],
        "PART_OF": [1, 2],
        "PART_INFO": {1: {"name": "첫 부분"}, 2: {"name": "두 번째 부분"}},
        "PART_TEXT": {1: "첫 부예요.", 2: "두 번째 부예요."},
        "ENDING_TEXT": "끝이에요.",
    }


class NumberTests(unittest.TestCase):
    def test_zero_negative_and_group_boundaries(self):
        for number, expected in [(0, "영"), (1, "일"), (10, "십"), (10000, "일만"),
                                 (100000000, "일억"), (100010001, "일억일만일"),
                                 (1000000000000, "일조"), (-2026, "마이너스 이천이십육")]:
            with self.subTest(number=number):
                self.assertEqual(kor_num(number), expected)

    def test_decimal_and_grouped_units(self):
        self.assertEqual(numbers_to_spoken("0억 1.05억 1,234만 -2년 +3년"),
                         "영억 일점영오억 천이백삼십사만 마이너스 이년 플러스 삼년")

    def test_native_counters(self):
        self.assertEqual(numbers_to_spoken("1명 11명 20명 21명 99명 1,000개 0건"),
                         "한명 열한명 스무명 스물한명 아흔아홉명 천 개 영 건")

    def test_calendar_and_duration(self):
        self.assertEqual(numbers_to_spoken("6월 5일, 10월 10일, 5일 동안, 12일 만에"),
                         "유월 오일, 시월 십일, 닷새 동안, 십이일 만에")

    def test_ambiguous_numbers_are_not_partially_rewritten(self):
        for value in ("1.5명", "-2개", "123", "13월", "1,23억"):
            with self.subTest(value=value):
                self.assertEqual(numbers_to_spoken(value), value)

    def test_confirmed_pronunciations_retained(self):
        expected = {"수츠케버": "수츠케 버", "AMI Labs": "에이엠아이 랩스", "LawZero": "로 제로",
                    "Azure": "애저", "Thinking Machines Lab": "씽킹 머신스 랩",
                    "Attention Is All You Need": "어텐션 이즈 올 유 니드"}
        for display, spoken in expected.items():
            with self.subTest(display=display):
                self.assertIn((display, spoken), SPOKEN)
                self.assertEqual(to_spoken(display), spoken)

    def test_tags_and_entities(self):
        self.assertEqual(strip_tags('<span>AI</span><br> A &amp; B'), 'AI  A & B')


class SourceTests(unittest.TestCase):
    def test_play_order_and_derived_fields(self):
        narration = narration_from_source(fixture())
        self.assertEqual([item["id"] for item in narration["items"]],
                         ["00-opening", "part1", "01-scene", "part2", "02-scene", "03-ending"])
        validate_narration(narration)
        for item in narration["items"]:
            self.assertEqual(item["text"], " ".join(item["lines"]))
            self.assertEqual(item["chars"], len(item["text"]))
            self.assertEqual(item["text_sha256"], text_sha256(item["text"]))

    def test_source_is_not_mutated(self):
        source = fixture()
        original = copy.deepcopy(source)
        narration_from_source(source)
        self.assertEqual(source, original)

    def test_opening_part_ending_have_one_source(self):
        source = fixture()
        source["OPENING_PARAS"][0] = "수정한 인사예요."
        source["PART_TEXT"][2] = "수정한 부예요."
        source["ENDING_TEXT"] = "수정한 끝이에요."
        narration = narration_from_source(source)
        texts = [item["text"] for item in narration["items"]]
        self.assertIn("수정한 인사예요.", texts[0])
        self.assertIn("수정한 부예요.", texts)
        self.assertEqual(texts[-1], "수정한 끝이에요.")

    def test_parts_fail_closed(self):
        for change in ("count", "repeated"):
            source = fixture()
            if change == "count":
                source["PART_OF"] = [1]
            else:
                source["CHAPTERS"].append(source["CHAPTERS"][0])
                source["PART_OF"] = [1, 2, 1]
            with self.subTest(change=change), self.assertRaises(ValueError):
                narration_from_source(source)

    def test_corrupt_derived_fields_fail(self):
        narration = narration_from_source(fixture())
        for field, value in (("text", "wrong"), ("chars", -1), ("text_sha256", "bad"), ("display_lines", ["wrong"])):
            broken = copy.deepcopy(narration)
            broken["items"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_narration(broken)

    def test_duplicate_ids_fail(self):
        narration = narration_from_source(fixture())
        narration["items"][1]["id"] = narration["items"][0]["id"]
        with self.assertRaises(ValueError):
            validate_narration(narration)

    def test_embedded_json_round_trip(self):
        expected = narration_from_source(fixture())
        html = '<script>const NARRATION = ' + json_text(expected) + ';</script>'
        self.assertEqual(narration_from_html(html), expected)
        with self.assertRaises(ValueError):
            narration_from_html('<script>const SCENES = [];</script>')

    def test_generated_html_matches_source_and_scene_display(self):
        expected = narration_from_source(build_aistory)
        html = build_aistory.build_html()
        self.assertEqual(narration_from_html(html), expected)
        scenes = parse_scenes(html)
        expected_scenes = [item for item in expected["items"] if item["id"].endswith("-scene")]
        self.assertEqual(len(scenes), len(expected_scenes))
        for scene, item in zip(scenes, expected_scenes):
            self.assertEqual(scene["id"], item["id"])
            self.assertEqual(scene["lines"], item["display_lines"])

    def test_legacy_parser_requires_explicit_opt_in(self):
        html = """const OPENING_TEXT='과거 인사예요.';
const SCENES = [
 {year:'1950년', part:1, lines:[
 'AI예요.'
 ]}
];
const PARTS = {"1":{"name":"첫 부"}};
const PART_TEXT = {"1":"첫 부예요."};
const END_QUOTE = "끝이에요.";
"""
        with self.assertRaises(ValueError):
            narration_from_html(html)
        narration = narration_from_html(html, legacy=True)
        self.assertEqual(narration["items"][0]["text"], "과거 인사예요.")
        self.assertEqual(narration["items"][2]["text"], "에이아이예요.")


class AudioEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.audio = self.root / "audio18"
        self.audio.mkdir()
        self.narration = narration_from_source(fixture())
        self.item = self.narration["items"][0]
        (self.audio / "00-opening.mp3").write_bytes(b"test fixture, not playable audio")

    def write_manifest(self, entries):
        (self.audio / "manifest.json").write_text(json_text({"items": entries}), encoding="utf-8")

    def approved(self, **fields):
        return {"id": "00-opening", "text_sha256": self.item["text_sha256"],
                "audio_sha256": hashlib.sha256((self.audio / "00-opening.mp3").read_bytes()).hexdigest(),
                "quality_status": "approved", "seconds": 5, **fields}

    def state(self):
        return audio_status(self.narration, self.root)["00-opening"]

    def test_historical_seconds_do_not_establish_freshness(self):
        self.write_manifest([{"id": "00-opening", "file": "00-opening.mp3", "seconds": 48.9}])
        self.assertEqual(self.state()["status"], "pending")
        self.assertEqual(self.state()["existing_audio_seconds"], 48.9)
        self.assertIsNone(self.state()["rendered_seconds"])

    def test_each_supported_text_evidence_can_verify(self):
        for key, value in (("text", self.item["text"]),
                           ("text_sha256", self.item["text_sha256"])):
            entry = self.approved()
            del entry["text_sha256"]
            entry[key] = value
            self.write_manifest([entry])
            with self.subTest(field=key):
                self.assertEqual(self.state()["status"], "verified")
                self.assertEqual(self.state()["rendered_seconds"], 5)

    def test_sha1_alone_is_insufficient_script_proof(self):
        entry = self.approved()
        del entry["text_sha256"]
        entry["text_sha1"] = hashlib.sha1(self.item["text"].encode()).hexdigest()
        self.write_manifest([entry])
        self.assertEqual(self.state()["status"], "pending")
        self.assertFalse(self.state()["script_verified"])

    def test_text_proof_alone_cannot_verify_copied_audio(self):
        self.write_manifest([{"id": "00-opening", "text": self.item["text"], "quality_status": "approved"}])
        self.assertEqual(self.state()["status"], "pending")
        self.assertTrue(self.state()["script_verified"])
        self.assertFalse(self.state()["audio_verified"])

    def test_audio_bytes_change_invalidates_approval(self):
        self.write_manifest([self.approved()])
        self.assertEqual(self.state()["status"], "verified")
        (self.audio / "00-opening.mp3").write_bytes(b"copied or changed audio")
        self.assertEqual(self.state()["status"], "pending")
        self.assertEqual(self.state()["reason"], "audio_hash_mismatch")

    def test_quality_review_must_be_approved(self):
        for quality in ("unreviewed", "pending_review", "rejected", "unknown", None, {}):
            self.write_manifest([self.approved(quality_status=quality)])
            with self.subTest(quality=quality):
                self.assertEqual(self.state()["status"], "pending")
                self.assertTrue(self.state()["script_verified"])
                self.assertTrue(self.state()["audio_verified"])
                self.assertIsNone(self.state()["rendered_seconds"])

    def test_conflicting_evidence_fails_closed(self):
        self.write_manifest([{"id": "00-opening", "text": self.item["text"], "text_sha256": "old"}])
        self.assertEqual(self.state()["status"], "pending")

    def test_wav_sidecar_alone_does_not_verify_mp3(self):
        (self.audio / "00-opening.sha1").write_text(hashlib.sha1(self.item["text"].encode()).hexdigest())
        self.write_manifest([{"id": "00-opening", "seconds": 5}])
        self.assertEqual(self.state()["status"], "pending")

    def test_missing_or_mismatched_mp3_stays_pending(self):
        self.write_manifest([{"id": "00-opening", "file": "different.mp3", "text": self.item["text"]}])
        self.assertEqual(self.state()["status"], "pending")
        (self.audio / "00-opening.mp3").unlink()
        self.write_manifest([{"id": "00-opening", "text": self.item["text"]}])
        self.assertEqual(self.state()["status"], "pending")

    def test_duplicate_manifest_id_fails_closed(self):
        entry = {"id": "00-opening", "text": self.item["text"]}
        self.write_manifest([entry, entry])
        self.assertEqual(self.state()["status"], "pending")

    def test_invalid_manifest_and_durations_are_safe(self):
        (self.audio / "manifest.json").write_text("not JSON")
        self.assertEqual(self.state()["status"], "pending")
        for value in (None, -1, 0, True, "48.9"):
            self.write_manifest([self.approved(seconds=value)])
            with self.subTest(seconds=value):
                self.assertIsNone(self.state()["rendered_seconds"])


class ExportTests(unittest.TestCase):
    def test_bundle_deterministic_and_hashes_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            narration = narration_from_source(fixture())
            first = make_bundle(narration, root)
            second = make_bundle(narration, root)
            self.assertEqual(first, second)
            for line in first["SHA256SUMS"].decode().splitlines():
                expected_hash, filename = line.split("  ", 1)
                self.assertEqual(hashlib.sha256(first[filename]).hexdigest(), expected_hash)
            self.assertEqual(json.loads(first["bundle-manifest.json"])["pending_clip_count"], 6)
            self.assertIsNone(json.loads(first["mp3-map.json"])["current_script_rendered_total_seconds"])

    def test_readthrough_is_exact_spoken_content(self):
        with tempfile.TemporaryDirectory() as directory:
            narration = narration_from_source(fixture())
            files = make_bundle(narration, pathlib.Path(directory))
            expected = "\n\n".join(line for item in narration["items"] for line in item["lines"]) + "\n"
            self.assertEqual(files["readthrough.txt"].decode(), expected)
            mapping = json.loads(files["mp3-map.json"])
            self.assertEqual([row["expected_mp3"] for row in mapping["items"]],
                             ["audio18/" + item["id"] + ".mp3" for item in narration["items"]])

    def test_check_is_read_only_and_detects_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory) / "export"
            files = {"one.txt": b"canonical\n"}
            self.assertEqual(write_bundle(files, output, check=True), ["one.txt"])
            self.assertFalse(output.exists())
            write_bundle(files, output)
            self.assertEqual(write_bundle(files, output, check=True), [])
            (output / "one.txt").write_bytes(b"manual edit\n")
            self.assertEqual(write_bundle(files, output, check=True), ["one.txt"])
            self.assertEqual((output / "one.txt").read_bytes(), b"manual edit\n")

    def test_export_cli_no_audio_writes_and_check_exit(self):
        audio_before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in (ROOT / "audio18").glob("*") if path.is_file()}
        with tempfile.TemporaryDirectory() as directory:
            command = [sys.executable, str(ROOT / "tools/export_narration.py"), "--out", directory]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run(command + ["--check"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            (pathlib.Path(directory) / "readthrough.txt").write_text("drift")
            result = subprocess.run(command + ["--check"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
        audio_after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in (ROOT / "audio18").glob("*") if path.is_file()}
        self.assertEqual(audio_before, audio_after)


if __name__ == "__main__":
    unittest.main()
