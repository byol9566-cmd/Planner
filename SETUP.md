# 새 PC 인수인계 셋업 가이드

이 문서는 새 PC에서 GitHub 저장소를 clone 한 직후, 곧바로 앱을 실행할 수 있도록 정리한 체크리스트입니다.

대상 환경: **Windows 10/11 + Python 3.10+**

---

## 0. 사전 준비물

| 항목 | 비고 |
|---|---|
| Python 3.10 이상 | `python --version` 으로 확인 |
| Git | `git --version` 으로 확인 |
| (선택) PyInstaller | `.exe` 빌드용. `pip install pyinstaller` |
| (선택) Notion Integration token | Notion 동기화를 쓸 경우만 |

이전 PC에서 챙겨갈 것 (git에는 없음, `.gitignore` 로 제외됨):
- `config.json` — 개인 설정(테마, 템플릿, Notion 토큰 등)
- `data/` — `notify_history.jsonl`, `notion_map.json` (알림 이력 / Notion page 매핑)
- `overrides/` — 날짜별 일정 수정본
- `planner_*.ics` — 백업/내보내기 결과

위 4개를 USB·클라우드 등으로 옮기지 않으면 **개인 일정 데이터와 Notion 매핑이 초기화**됩니다.
(템플릿·테마 정도만 다시 짜도 되면 굳이 안 옮겨도 됨.)

---

## 1. 저장소 클론

```powershell
git clone https://github.com/byol9566-cmd/Planner.git
cd Planner
```

## 2. 가상환경 + 의존성

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`requirements.txt` 에 들어 있는 패키지:
`apscheduler`, `winotify`, `edge-tts`, `pyttsx3`, `PySide6`, `pywin32`, `notion-client`

> `pywin32` 가 처음 설치 후 동작 안 하면:
> `python .\.venv\Scripts\pywin32_postinstall.py -install`

## 3. 설정 파일 복원

### A. 이전 PC `config.json` 을 그대로 가져오는 경우 (권장)

이전 PC의 `config.json` 을 프로젝트 루트에 그대로 복사해 넣으면 끝.
(이 파일은 `.gitignore` 로 제외되어 있어 다음 commit/push 시에도 안전.)

### B. 처음부터 새로 만드는 경우

```powershell
copy config.example.json config.json
```

필요한 항목을 채워 넣음:
- `settings.timezone` (기본 `Asia/Seoul`)
- `settings.pre_alert_minutes`, `daily_refresh_time`, `silent_hours_*`
- `settings.tts_voice` / `tts_rate`
- `settings.theme` (`light` / `dark`)
- `weekday_themes` (요일별 키워드)
- `templates` (A/B/C... 일과 템플릿)
- `settings.notion.{token, database_id, enabled}` — 아래 4번 참고

## 4. Notion 동기화 (선택)

**우선순위: 환경변수 > `config.json`**

옵션 1) `config.json` 에 직접 적기:
```json
"notion": { "token": "ntn_...", "database_id": "xxxx", "enabled": true }
```

옵션 2) 환경변수 (권장, 토큰을 파일에 남기지 않음):
```powershell
copy .env.example .env
# .env 편집
#   NOTION_TOKEN=ntn_xxx
#   NOTION_DATABASE_ID=xxxxxxxx
```

> ⚠️ 이전 PC `config.json` 에 들어 있던 Notion 토큰(`ntn_...`)은 한 번 평문 노출 이력이 있으므로,
> https://www.notion.so/my-integrations 에서 해당 integration 의 **Refresh** 또는 새 토큰 발급 후 사용.

> ⚠️ `.env` 파일은 Python 이 자동 로드하지 않음. 셸에서 직접 `set NOTION_TOKEN=...` 하거나,
> 자동 로드를 원하면 `pip install python-dotenv` 후 `app.py` 상단에
> `from dotenv import load_dotenv; load_dotenv()` 한 줄 추가.

Notion DB 스키마(컬럼)는 다음을 따라야 함 (`core/notion_sync.py` 참고):
- `Title` (title), `Date` (date), `Time` (rich_text), `Kind` (select),
  `Done` (checkbox), `Note` (rich_text), `BlockKey` (rich_text)

## 5. 데이터 디렉터리

```powershell
mkdir data overrides 2>$null
```

이전 PC 의 `data/notify_history.jsonl`, `data/notion_map.json`, `overrides/*.json` 을 그대로 덮어쓰기.
(특히 `notion_map.json` 이 없으면 Notion 쪽에 **중복 페이지가 새로 생성**됨.)

## 6. 실행

```powershell
python app.py
```

트레이 아이콘으로 동작. 메인 윈도우는 트레이 메뉴에서 열기.

## 7. (선택) `.exe` 빌드

`app.spec` 이 이미 포함되어 있음:
```powershell
pip install pyinstaller
pyinstaller app.spec
# 결과: dist\app\app.exe
```

## 8. (선택) 윈도우 시작 시 자동 실행

`Win+R` → `shell:startup` → 해당 폴더에 `app.exe` (또는 `python app.py` 를 호출하는 `.bat`) 의 바로가기 생성.

---

## 트러블슈팅

| 증상 | 원인/해결 |
|---|---|
| `ModuleNotFoundError: PySide6` | 가상환경 활성화 안 됨. `.\.venv\Scripts\Activate.ps1` |
| 알림이 안 뜸 | Windows 설정 → 시스템 → 알림 → Python/앱 허용 확인 |
| TTS 가 안 나옴 | `edge-tts` 는 인터넷 필요. 오프라인은 `pyttsx3` fallback |
| Notion 동기화 안 됨 | `settings.notion.enabled=true` 인지, 토큰/DB ID 정확한지, integration 이 해당 DB 에 share 되어 있는지 확인 |
| 일정이 비어 보임 | `config.json` 의 `templates`, `weekday_themes` 가 채워져 있는지 / `overrides/` 가 복사됐는지 확인 |
| Notion 에 중복 페이지 생김 | `data/notion_map.json` 을 안 옮긴 것. 옮긴 뒤 중복 페이지 archive |

---

## 푸시·풀 작업 시 안전 체크

`.gitignore` 가 다음을 자동으로 제외함:
`config.json`, `.env`, `data/`, `overrides/`, `*.ics`, `__pycache__/`, `build/`, `dist/`, `.claude/`, `.cursor/`

추가로 변경/추가한 파일에 토큰·개인 일정이 섞이지 않았는지 `git status` / `git diff` 로 한 번 더 확인 후 push.
