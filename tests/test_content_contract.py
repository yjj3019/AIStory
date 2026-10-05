"""Educational source/HTML contract checks; no network and no speech rendering."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import build_aistory as story
from extract_narration import narration_from_source, audio_status

class ContentContractTests(unittest.TestCase):
    def test_every_chapter_has_learning_check_sources_and_people(self):
        self.assertEqual(len(story.CHAPTERS),19)
        self.assertEqual(len(story.PART_OF),19)
        for n,(_,title,people,lines) in enumerate(story.CHAPTERS,1):
            with self.subTest(chapter=n):
                visual=story.CHAPTER_VISUALS[n]
                self.assertTrue(title and lines and people)
                self.assertTrue(visual['learning_question'] and visual['learning_answer'])
                self.assertTrue(visual['src'])
                self.assertTrue(all(ref[2].startswith('https://') for ref in visual['src']))
                self.assertTrue(all(key in story.P or key in story.RIVALS for key in people))
    def test_verified_registry_statuses_are_not_all_claimed_as_primary(self):
        records=json.loads((ROOT/'review/verified_sources.json').read_text())
        self.assertEqual({r['chapter'] for r in records},set(range(1,20)))
        self.assertTrue(any(r['verification']=='primary_fetch_blocked' for r in records))
        blocked={r['url'] for r in records if r['verification'] in {'primary_fetch_blocked','current_page_stale_or_conflicting'}}
        shown={r[2] for v in story.CHAPTER_VISUALS.values() for r in v['src']}
        self.assertFalse(blocked & shown)
    def test_all_generated_javascript_parses(self):
        html=story.build_html()
        scripts=re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>',html,re.S)
        self.assertTrue(scripts)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'aistory.js';path.write_text('\n'.join(scripts),encoding='utf-8')
            result=subprocess.run(['node','--check',str(path)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
    def test_manual_reading_has_no_silent_tts_fallback(self):
        html=story.build_html()
        self.assertNotIn('SpeechSynthesisUtterance',html)
        self.assertNotIn('speechSynthesis',html)
        self.assertIn('음성 재렌더링 대기',html)
        self.assertIn('learning_question',html)
        self.assertNotIn('__TOTAL__',html)
    def test_legacy_slide_wrapper_produces_same_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'slide.html'
            subprocess.run([sys.executable,str(ROOT/'build_slide.py'),'-o',str(target)],check=True,capture_output=True)
            self.assertEqual(target.read_text(),story.build_html())
    def test_legacy_slide_wrapper_rejects_unverified_alternate_audio(self):
        result=subprocess.run([sys.executable,str(ROOT/'build_slide.py'),'--audio-dir','other/'],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
    def test_current_unverified_audio_has_no_current_duration_claim(self):
        statuses=audio_status(narration_from_source(story),ROOT)
        for status in statuses.values():
            if status['status']=='pending':self.assertIsNone(status['rendered_seconds'])

if __name__=='__main__':unittest.main()
