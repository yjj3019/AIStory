# SESSION_LOG.md

Notion MCP 미연결 시 개발 이력 폴백 기록. 날짜별 누적 append만 — 기존 블록 삭제/덮어쓰기 금지.
Notion 재연결 시 아래 블록을 프로젝트 Notion 페이지 `## 개발 이력`에 표준 포맷으로 옮기고, 옮긴 블록에는 `[synced]` 표시만 남긴다.

---

## 📅 세션 백업: 2026-09-18 08:45

### ✅ 완료 작업
- **(2026-09-17) 사진 없는 인물 11명의 이니셜 폴백 스타일 개선** — 사용자 지적("빈 칸처럼 매끄럽지 않다")에 따라 `.por` 배지를 단색 원 → 135도 2톤 그라디언트 + inset 링 + `.mono`(letter-spacing/text-shadow)로 개선. `AIStory.html`의 `initialColor()`/`attachPortraitFallback()` 수정. JS 문법 검증(`new Function()`) 통과.
- **(2026-09-18) 히어로(장 좌측 상단 대형 카드) 영역 사진 누락 버그 수정** — 사용자 지적("설명에는 등장하는 인물이 사진엔 없어 스토리 매치가 안 됨")에 따라 원인 파악: `heroPeople`이 `PORTRAIT_KEYS`(사진 보유자)로만 필터링돼 사진 없는 인물은 히어로 영역에서 통째로 제외됨(8장 트랜스포머는 3명 전원 사진 없어 히어로가 완전히 비어 있었음). 필터 제거 + 히어로 이미지에도 `attachPortraitFallback()` 연결 + `P[k]||RIVALS[k]` 조회로 수정(16장은 전원 `RIVALS` 소속이라 기존 코드였다면 `undefined` 에러 발생 지점).
- **검증**: 실제 `AIStory.html`을 로컬 서버로 띄우고 헤드리스 Chrome(`--dump-dom`, `--virtual-time-budget`)으로 런타임 DOM 직접 확인. 8장(전원 사진없음)·13장(혼합)·16장(RIVALS 전용) 3개 케이스 모두 정상 렌더링, 에러 없음 확인. 데이터 정합성도 Node vm으로 `P`/`RIVALS`/`SCENES` 파싱해 이름/이니셜 결측·카드 참조 무결성 검증 완료.

### 🚧 진행 중
- 없음 (이번 두 건 모두 완료 처리)

### ⏭️ 다음 세션 즉시 실행 항목
- 18개 오디오 클립 전수 청취(발음/톤) 아직 미완료
- Chrome 확장이 이 세션 내내 연결되지 않음 — 다음 세션에서 재시도해 실제 브라우저 눈으로 최종 확인 권장(이번엔 헤드리스 Chrome DOM 덤프로 대체 검증)
- Notion 프로젝트 페이지 미생성 — Notion MCP 연결 시 이 SESSION_LOG.md 전체를 프로젝트 페이지로 이관 필요

### 🧩 런타임 스냅샷
- Branch/Path: `main` · `C:\AI-Codding\claude\AIStory`
- Last File: `AIStory.html` (gitignore 대상, git 이력에는 안 남음 — PROGRESS.md가 유일한 변경 추적 수단)
- Active Errors: 없음
- Last CMD: 헤드리스 Chrome `--dump-dom` 검증 (`chrome.exe --headless --disable-gpu --virtual-time-budget=4000 --dump-dom ...`)

### 💬 인계 메모
- 이 PC는 background job이라 worktree 격리가 강제되는데, `AIStory.html`/`SESSION_LOG.md` 같은 파일은 `.gitignore` 대상이거나 신규 파일이라 worktree에 자동으로 안 보임 → 매번 worktree 안으로 수동 복사 후 편집, 원본 경로로 다시 복사하는 방식으로 우회 중. 이 두 건은 git 커밋 대상이 아니므로(AIStory.html) 또는 이번에 처음 생성됨(SESSION_LOG.md) git 이력만으로는 추적 불가 — PROGRESS.md + 이 파일을 함께 봐야 전체 그림이 보임.
- PROGRESS.md는 이번 두 건 모두 이미 기록 완료된 상태(2026-09-17, 2026-09-18 항목), 아직 git 커밋 전(사용자 커밋 요청 시에만 커밋).
