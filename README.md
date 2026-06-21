# Planner

데스크톱 일정 알림 / Notion 동기화 도구.

## 설정

1. `config.example.json` 을 `config.json` 으로 복사 후 본인 환경에 맞게 수정.
2. Notion 동기화를 사용하려면 다음 중 하나:
   - `config.json` 의 `settings.notion.token`, `settings.notion.database_id` 를 채우거나
   - 환경변수 `NOTION_TOKEN`, `NOTION_DATABASE_ID` 를 설정 (env 가 우선).
3. 의존성 설치:
   ```
   pip install -r requirements.txt
   ```
4. 실행:
   ```
   python app.py
   ```

## 보안

- `config.json`, `data/`, `overrides/`, `*.ics` 는 개인정보/시크릿을 포함하므로 git 에 커밋되지 않습니다 (`.gitignore` 참고).
- Notion 토큰은 절대 공개 저장소에 커밋하지 마세요.
