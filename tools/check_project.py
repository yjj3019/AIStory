#!/usr/bin/env python3
"""Read-only aggregate validation. Does not render audio or install dependencies."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import build_aistory
from extract_narration import narration_from_source,narration_from_html,json_text,parse_scenes

def run(*args):
    subprocess.run(args,cwd=ROOT,check=True)

def main():
    expected=build_aistory.build_html()
    for name in ('AIStory.html','AIStory-slide.html'):
        if not (ROOT/name).is_file() or (ROOT/name).read_text(encoding='utf-8')!=expected:
            raise SystemExit(f'{name} missing or stale; run python build_aistory.py')
    narration=narration_from_source(build_aistory)
    if (ROOT/'narration.json').read_text(encoding='utf-8')!=json_text(narration):
        raise SystemExit('narration.json stale; run extractor')
    if narration_from_html(expected)!=narration:raise SystemExit('Embedded narration mismatch')
    if len(parse_scenes(expected))!=19:raise SystemExit('Unexpected chapter count')
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'audio18').glob('*') if p.is_file()}
    run(sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py','-v')
    run('node','--test','tests/test_slide_player.mjs')
    run(sys.executable,'tools/export_narration.py','--check','--verify-html')
    run(sys.executable,'tools/generate_guides.py','--check')
    run('git','diff','--check')
    after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'audio18').glob('*') if p.is_file()}
    if before!=after:raise SystemExit('Audio assets changed during validation')
    print('PASS: reproducibility, canonical data, Python/Node regressions, exports, guides, audio preservation.')
    print('NOT RUN: real-browser visual QA (separate environment required); speech rendering and listening QA excluded.')

if __name__=='__main__':main()
