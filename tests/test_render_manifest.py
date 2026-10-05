"""Render bookkeeping tests using temp files, synthetic bytes and mocked codecs.

These tests never load a model, invoke an audio encoder, or touch audio18/.
"""

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import render_tts as render


class RenderManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.unit = {"id": "01-scene", "label": "1장", "text": "현재 원고예요."}
        self.wav = self.root / "01-scene.wav"
        self.wav.write_bytes(b"synthetic wav bytes")
        self.mp3 = self.root / "01-scene.mp3"
        self.mp3.write_bytes(b"old synthetic mp3 bytes")

    def entry(self, output=None, verified=True, duration=1.25):
        return render.make_manifest_entry(self.unit, self.wav, output,
                                          wav_verified=verified, output_format="mp3",
                                          duration_probe=lambda path: duration)

    def test_failed_conversion_never_hashes_previous_mp3(self):
        old_bytes = self.mp3.read_bytes()
        with mock.patch.object(render.subprocess, "run", side_effect=FileNotFoundError):
            output = render.to_mp3(self.wav)
        self.assertIsNone(output)
        self.assertEqual(self.mp3.read_bytes(), old_bytes)
        entry = self.entry(output)
        self.assertIsNone(entry["audio_sha256"])
        self.assertIsNone(entry["seconds"])
        self.assertNotIn("text", entry)
        self.assertNotIn("text_sha256", entry)
        self.assertEqual(entry["provenance_status"], "unverified")
        self.assertEqual(entry["quality_status"], "unreviewed")
        self.assertEqual(list(self.root.glob("*.part.mp3")), [])

    def test_partial_failed_conversion_does_not_replace_old_mp3(self):
        old_bytes = self.mp3.read_bytes()

        def fail(command, **kwargs):
            pathlib.Path(command[-1]).write_bytes(b"truncated output")
            raise subprocess.CalledProcessError(1, command)

        with mock.patch.object(render.subprocess, "run", side_effect=fail):
            self.assertIsNone(render.to_mp3(self.wav))
        self.assertEqual(self.mp3.read_bytes(), old_bytes)
        self.assertEqual(list(self.root.glob("*.part.mp3")), [])

    def test_successful_conversion_replaces_atomically(self):
        def convert(command, **kwargs):
            temporary = pathlib.Path(command[-1])
            self.assertNotEqual(temporary, self.mp3)
            self.assertEqual(self.mp3.read_bytes(), b"old synthetic mp3 bytes")
            temporary.write_bytes(b"new synthetic mp3 bytes")
            return subprocess.CompletedProcess(command, 0)

        with mock.patch.object(render.subprocess, "run", side_effect=convert):
            self.assertEqual(render.to_mp3(self.wav), self.mp3)
        self.assertEqual(self.mp3.read_bytes(), b"new synthetic mp3 bytes")
        self.assertEqual(list(self.root.glob("*.part.mp3")), [])

    def test_success_exit_with_empty_file_is_failure(self):
        with mock.patch.object(render.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
            self.assertIsNone(render.to_mp3(self.wav))
        self.assertEqual(self.mp3.read_bytes(), b"old synthetic mp3 bytes")

    def test_unknown_reuse_does_not_gain_text_provenance(self):
        entry = self.entry(self.mp3, verified=False)
        for key in ("text", "text_sha1", "text_sha256"):
            self.assertNotIn(key, entry)
        self.assertEqual(entry["requested_text_sha256"], hashlib.sha256(self.unit["text"].encode()).hexdigest())
        self.assertIsNone(entry["wav_sha256"])
        self.assertEqual(entry["provenance_status"], "unverified")
        self.assertFalse(render.wav_provenance_matches(self.unit, self.wav, entry))

    def test_new_verified_output_is_pending_manual_review(self):
        entry = self.entry(self.mp3)
        self.assertEqual(entry["text"], self.unit["text"])
        self.assertEqual(entry["audio_sha256"], hashlib.sha256(self.mp3.read_bytes()).hexdigest())
        self.assertEqual(entry["wav_sha256"], hashlib.sha256(self.wav.read_bytes()).hexdigest())
        self.assertEqual(entry["quality_status"], "pending_review")
        self.assertEqual(entry["provenance_status"], "verified")
        self.assertTrue(render.wav_provenance_matches(self.unit, self.wav, entry))

    def test_mp3_duration_uses_final_mp3(self):
        probe = mock.Mock(return_value=7.125)
        entry = render.make_manifest_entry(self.unit, self.wav, self.mp3,
                                            wav_verified=True, output_format="mp3", duration_probe=probe)
        probe.assert_called_once_with(self.mp3)
        self.assertEqual(entry["seconds"], 7.125)

    def test_ffprobe_receives_final_mp3_path(self):
        result = subprocess.CompletedProcess([], 0, stdout="7.125\n")
        with mock.patch.object(render.subprocess, "run", return_value=result) as run:
            self.assertEqual(render.probe_audio_seconds(self.mp3), 7.125)
        self.assertEqual(run.call_args.args[0][-1], str(self.mp3))
        self.assertEqual(run.call_args.args[0][0], "ffprobe")

    def test_failed_or_nonfinite_probe_never_falls_back_to_wav(self):
        for output in ("bad", "nan", "inf", "0", "-2"):
            result = subprocess.CompletedProcess([], 0, stdout=output)
            with self.subTest(output=output), mock.patch.object(render.subprocess, "run", return_value=result):
                self.assertIsNone(render.probe_audio_seconds(self.mp3))
        with mock.patch.object(render.subprocess, "run", side_effect=FileNotFoundError):
            self.assertIsNone(render.probe_audio_seconds(self.mp3))
        entry = self.entry(self.mp3, duration=None)
        self.assertIsNone(entry["seconds"])
        self.assertEqual(entry["quality_status"], "unreviewed")

    def test_bound_sidecar_detects_script_and_wav_changes(self):
        self.assertFalse(render.wav_provenance_matches(self.unit, self.wav))
        render.record_wav_provenance(self.unit, self.wav)
        self.assertTrue(render.wav_provenance_matches(self.unit, self.wav))
        changed = {**self.unit, "text": "다른 원고예요."}
        self.assertFalse(render.wav_provenance_matches(changed, self.wav))
        self.wav.write_bytes(b"copied different wav")
        self.assertFalse(render.wav_provenance_matches(self.unit, self.wav))

    def test_old_text_only_manifest_and_sha1_cannot_verify_wav(self):
        self.wav.with_suffix(".sha1").write_text(hashlib.sha1(self.unit["text"].encode()).hexdigest())
        self.assertFalse(render.wav_provenance_matches(self.unit, self.wav, {"text": self.unit["text"]}))

    def test_malformed_sidecar_fails_closed(self):
        entry = self.entry(self.mp3)
        self.wav.with_suffix(".provenance.json").write_text("not JSON")
        self.assertFalse(render.wav_provenance_matches(self.unit, self.wav, entry))

    def test_wav_manifest_must_name_exact_wav(self):
        entry = {"text": self.unit["text"], "file": self.wav.name,
                 "audio_sha256": hashlib.sha256(self.wav.read_bytes()).hexdigest()}
        self.assertTrue(render.wav_provenance_matches(self.unit, self.wav, entry))
        entry["file"] = "another.wav"
        self.assertFalse(render.wav_provenance_matches(self.unit, self.wav, entry))

    def test_default_output_directory_is_audio18(self):
        with mock.patch.object(sys, "argv", ["render_tts.py"]):
            self.assertEqual(render.parse_args().out_dir, "audio18")


if __name__ == "__main__":
    unittest.main()
