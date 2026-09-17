# Education track — AI Bot 시대

주제: **사람들이 왜 AI 봇에 열광하는가** (제품 카탈로그가 아닌 위임·격리·승인 교육 트랙).

| 파일 | 역할 |
|---|---|
| `why-ai-bots.html` | 커밋되는 HTML 셸 (SCENES 20장 + OPENING/ENDING). 로고·스크린샷 없음. |
| `../samples/narration.education-22.json` | `extract_narration.py` 산출물 (22클립) |

루트 `AIStory.html`은 `.gitignore`라 저장소에 없을 수 있으므로, 이 경로를 extract 대상으로 쓴다.

```bash
python extract_narration.py education/why-ai-bots.html -o samples/narration.education-22.json
python render_tts.py --narration samples/narration.education-22.json --out-dir ./audio --dry-run
# TTS 실렌더는 참조 음성 준비 후 (이 PR 범위 밖)
python -m unittest tests.test_extract_narration -v
```

클립 id: `00-opening` … `20-scene` … `21-ending`.
