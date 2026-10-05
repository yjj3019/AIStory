# Repository guidance

AIStory is a Korean educational interactive HTML page about AI contributors and research history. These instructions apply to any assistant editing the repository.

## Canonical data and build

- Edit narrative, people, visual facts, sources, learning checks, opening/ending and part text in `build_aistory.py` only.
- Edit layout/player in `slide.template.html` only. `AIStory.html` and `AIStory-slide.html` are generated aliases.
- `extract_narration.py` derives spoken text and hashes from canonical data. Keep display and spoken forms separate and deterministic.
- `narration.json` and `narration-export/` are derived. Never hand-edit them to repair inconsistency.
- Do not rerun historical `review/splice_build.py`, `review/new_data.py`, or `render_fix*.py` against the new source.

## Scope and factual care

- The 2026-10-05 revision excludes all audio rendering. Do not call any TTS engine or browser speech synthesis as a substitute.
- Preserve existing MP3 and manifest bytes. Unknown audio provenance is pending, not proof that the sound is wrong.
- Reference `SOURCES.md` and `review/verified_sources.json`; distinguish primary verification, metadata-only reads, and blocked/conflicting sources.
- Research-team contributions matter. Avoid sole-genius myths, company-goal-as-outcome claims, and treating valuation as revenue or model quality.
- Keep 19 chapters unless the user asks to change structure. No minimum duration is inferred from another project. Actual audio duration can only be stated after rendering and measurement.
- Korean narration uses accessible 해요체. Preserve historically tested pronunciation substitutions unless fresh evidence supports changing them.

## Verification

Run `python build_aistory.py`, `python extract_narration.py AIStory.html -o narration.json`, `python tools/export_narration.py --verify-html`, then `python tools/check_project.py`.

UI changes require a supported actual browser inspection. Unit tests/DOM stubs are not visual verification. If the environment blocks the browser, report the exact limit without disabling security or routing around it. Cover all 23 screens, mobile/desktop, keyboard navigation, modal focus, reduced motion, and interrupted/repeated playback.

Publication and merge require explicit authorization. Validate the exact commit and distinguish local tests from remote CI.
