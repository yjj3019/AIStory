#!/usr/bin/env python3
"""Compatibility entry point: build the slide page from canonical Python data.

AIStory.html is generated and is no longer an editable source. For both aliases,
run build_aistory.py. This wrapper retains --out/--audio-dir for local previews.
"""
import argparse
from pathlib import Path
from build_aistory import ROOT, build_html


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--src', help='Deprecated: only the canonical AIStory.html path is accepted')
    ap.add_argument('--template', help='Deprecated: only the canonical slide.template.html path is accepted')
    ap.add_argument('-o', '--out', default=str(ROOT / 'AIStory-slide.html'))
    ap.add_argument('--audio-dir', default='audio18/')
    args = ap.parse_args()
    if args.src and Path(args.src).resolve() != ROOT / 'AIStory.html':
        ap.error('Custom HTML sources are no longer supported; edit build_aistory.py data.')
    if args.template and Path(args.template).resolve() != ROOT / 'slide.template.html':
        ap.error('Custom templates are no longer supported; edit slide.template.html.')
    if args.audio_dir != 'audio18/':
        ap.error('Audio provenance is verified against audio18/; alternate folders require a separate verified build.')
    path = Path(args.out)
    path.write_text(build_html(), encoding='utf-8', newline='\n')
    print(f'생성: {path}')


if __name__ == '__main__':
    main()
