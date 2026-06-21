# 생활 플랜 알림 프로그램 — 개발 스펙 (Claude Code 인수용)

> 이 문서를 프로젝트 폴더에 넣고 Claude Code에게 "이 스펙대로 만들어줘"라고 하면 됩니다.
> 일정 데이터는 아래 `config.json`에 전부 들어 있으니, 날짜를 다시 계산할 필요 없습니다.

---

## 1. 목표

컴퓨터에서 백그라운드로 실행되며, **하루 일정의 각 블록 시작 시각마다 데스크톱 알림**을 띄우는 프로그램.
- 시작 5분 전 "곧 시작" 사전 알림(설정 가능)
- 블록 시작 시 본 알림 (제목 + 시간 범위 + 다음 블록 안내)
- 매일 00:05에 그날 날짜를 보고 일정을 자동 재생성
- `now` / `next` 같은 CLI로 현재·다음 일정 즉시 확인
- 실행 로그 기록

## 2. 기술 스택 (권장)

- **Python 3.10+**
- **APScheduler** — 시각별 스케줄링
- **plyer** (크로스 플랫폼 알림) 또는 OS별: Windows `winotify`, macOS `osascript`/`pync`, Linux `notify-send`
  - 우선 `plyer`로 구현하고, 알림이 안 뜨는 OS면 OS별 폴백 추가
- 설정/일정은 외부 `config.json` 으로 분리 (코드 수정 없이 일정 변경 가능)

> ⚠️ 내 OS는 (Windows / macOS / Linux 중 무엇인지 Claude Code에게 알려주세요). 자동 시작(부팅 시 실행) 설정은 OS별로 다릅니다:
> - Windows: 작업 스케줄러 또는 시작프로그램 등록
> - macOS: launchd `.plist` LaunchAgent
> - Linux: systemd user service 또는 cron @reboot

## 3. 동작 로직

1. 시작 시 `config.json` 로드
2. 오늘 날짜(`Asia/Seoul`)로 `calendar`에서 `type`을 찾음
3. 해당 `templates[type].blocks`를 펼쳐 오늘의 알림 스케줄 생성
   - `type == "A"`(휴가일)이면 `theme` 블록 제목 뒤에 그날 요일의 `weekday_themes` 텍스트를 붙임
   - 그날 `events`(예: 피부과 예약)가 있으면 추가 알림으로 등록
   - `type == "E"` 또는 `"OFF"`면 알림 없음 (쉬는 날 / 전역). 단, OFF에 `note`가 있으면 아침에 한 번 안내 알림
4. 각 블록마다: (a) 시작 `pre_alert_minutes`분 전 사전 알림, (b) 시작 시각 본 알림
5. 매일 00:05에 2~4단계를 다시 실행 (다음 날 일정 로드)
6. `kind == "buffer"` 블록은 알림 문구에 "🔲 여유시간 — 밀린 거 흡수하거나 그냥 쉬기"를 명시

## 4. 알림 문구 형식

- 제목: `⏰ {title}`
- 본문: `{start}~{end} · 다음: {next_title} ({next_start})`
- buffer 블록: `🔲 버퍼 {start}~{end} · 밀렸으면 여기서 흡수, 아니면 휴식`

## 5. CLI

- `python notifier.py run` — 백그라운드 스케줄러 실행 (기본)
- `python notifier.py now` — 지금 블록 + 남은 시간 출력
- `python notifier.py next` — 다음 블록 출력
- `python notifier.py today` — 오늘 전체 일정 출력

## 6. config.json (전체 일정 데이터 — 그대로 사용)

```json
{
  "settings": {
    "timezone": "Asia/Seoul",
    "pre_alert_minutes": 5,
    "daily_refresh_time": "00:05"
  },
  "weekday_themes": {
    "Mon": "주간 킥오프(이번 주 개발·마케팅 목표 세팅) + 개발",
    "Tue": "인스타툰/릴스 기획·콘티",
    "Wed": "AI 공부",
    "Thu": "인스타툰/릴스 제작·업로드"
  },
  "templates": {
    "A": {
      "name": "휴가일",
      "blocks": [
        {"time": "08:30", "title": "기상 · AI에 개발 task 투척 · 오늘 계획 확인", "kind": "wake"},
        {"time": "09:00", "title": "헬스 (1시간 30분)", "kind": "workout"},
        {"time": "10:30", "title": "복귀 · 샤워", "kind": "buffer"},
        {"time": "11:15", "title": "아점(식단) · AI 작업물 1차 리뷰", "kind": "meal"},
        {"time": "12:15", "title": "버퍼 / 휴식", "kind": "buffer"},
        {"time": "12:45", "title": "딥워크 ① 앱 개발", "kind": "deepwork"},
        {"time": "15:00", "title": "낮잠 / 휴식", "kind": "buffer"},
        {"time": "15:30", "title": "딥워크 ② 개발 or 마케팅", "kind": "deepwork"},
        {"time": "17:15", "title": "저녁(식단)", "kind": "meal"},
        {"time": "18:30", "title": "독서 50p", "kind": "reading"},
        {"time": "19:30", "title": "요일 테마 블록", "kind": "theme"},
        {"time": "21:00", "title": "자유 버퍼", "kind": "buffer"},
        {"time": "21:45", "title": "X 빌드인퍼블릭 · 인스타 관리", "kind": "marketing"},
        {"time": "22:30", "title": "마무리 · 내일 계획 작성", "kind": "wrap"},
        {"time": "23:30", "title": "취침 준비", "kind": "winddown"},
        {"time": "24:00", "title": "취침", "kind": "sleep"}
      ]
    },
    "B": {
      "name": "부대 금요일",
      "blocks": [
        {"time": "12:00", "title": "낮 틈틈이 폰: X 포스팅 · 개발 모바일 리뷰 · 독서", "kind": "light"},
        {"time": "17:30", "title": "저녁", "kind": "meal"},
        {"time": "18:30", "title": "독서 50p", "kind": "reading"},
        {"time": "19:30", "title": "앱 개발 (모바일)", "kind": "deepwork"},
        {"time": "20:45", "title": "버퍼", "kind": "buffer"},
        {"time": "21:15", "title": "X · 인스타 마케팅", "kind": "marketing"},
        {"time": "22:15", "title": "마무리 · 내일 계획", "kind": "wrap"},
        {"time": "23:00", "title": "취침 준비", "kind": "winddown"}
      ]
    },
    "C": {
      "name": "부대 주말 (컴퓨터 데이)",
      "blocks": [
        {"time": "09:30", "title": "헬스(체력단련실) or 개발 워밍업", "kind": "workout"},
        {"time": "11:00", "title": "개발", "kind": "deepwork"},
        {"time": "12:00", "title": "점심", "kind": "meal"},
        {"time": "13:00", "title": "딥워크 ① 앱 개발 (가장 무거운 작업)", "kind": "deepwork"},
        {"time": "15:00", "title": "버퍼 / 휴식", "kind": "buffer"},
        {"time": "15:30", "title": "딥워크 ② 개발 or AI 공부", "kind": "deepwork"},
        {"time": "17:30", "title": "버퍼", "kind": "buffer"},
        {"time": "18:00", "title": "저녁", "kind": "meal"},
        {"time": "19:00", "title": "독서 50p", "kind": "reading"},
        {"time": "20:00", "title": "마케팅 콘텐츠 제작 · X", "kind": "marketing"},
        {"time": "21:15", "title": "마무리 · SNS · 다음날 계획", "kind": "wrap"},
        {"time": "23:00", "title": "취침 준비", "kind": "winddown"}
      ]
    },
    "D": {
      "name": "외출일 (07:30~20:00 밖)",
      "blocks": [
        {"time": "08:00", "title": "헬스", "kind": "workout"},
        {"time": "10:00", "title": "카페 이동 · 딥워크 개발 2~3h", "kind": "deepwork"},
        {"time": "13:00", "title": "점심 · 개인 볼일", "kind": "buffer"},
        {"time": "20:00", "title": "복귀", "kind": "light"},
        {"time": "20:30", "title": "부대 컴퓨터로 개발 마무리 or 독서", "kind": "deepwork"},
        {"time": "22:30", "title": "마무리 · 내일 계획", "kind": "wrap"}
      ]
    },
    "F": {
      "name": "부대 평일 (전역 마무리)",
      "blocks": [
        {"time": "17:30", "title": "저녁", "kind": "meal"},
        {"time": "18:30", "title": "독서 50p", "kind": "reading"},
        {"time": "19:30", "title": "가벼운 개발 / 전역 준비·정리", "kind": "deepwork"},
        {"time": "20:45", "title": "버퍼", "kind": "buffer"},
        {"time": "21:15", "title": "마케팅 · SNS", "kind": "marketing"},
        {"time": "22:15", "title": "마무리", "kind": "wrap"}
      ]
    },
    "E": {
      "name": "외박 (펜션 · 완전 휴식)",
      "blocks": []
    },
    "OFF": {
      "name": "전역",
      "blocks": []
    }
  },
  "calendar": {
    "2026-06-15": {"type": "A"},
    "2026-06-16": {"type": "A", "events": [{"time": "14:00", "title": "피부과 예약 (시간 확인해서 수정)"}]},
    "2026-06-17": {"type": "A"},
    "2026-06-18": {"type": "A"},
    "2026-06-19": {"type": "B"},
    "2026-06-20": {"type": "D"},
    "2026-06-21": {"type": "C"},
    "2026-06-22": {"type": "A"},
    "2026-06-23": {"type": "A"},
    "2026-06-24": {"type": "A"},
    "2026-06-25": {"type": "A"},
    "2026-06-26": {"type": "B"},
    "2026-06-27": {"type": "C"},
    "2026-06-28": {"type": "C"},
    "2026-06-29": {"type": "A"},
    "2026-06-30": {"type": "A", "events": [{"time": "14:00", "title": "피부과 예약 (시간 확인해서 수정)"}]},
    "2026-07-01": {"type": "A"},
    "2026-07-02": {"type": "A"},
    "2026-07-03": {"type": "B"},
    "2026-07-04": {"type": "C"},
    "2026-07-05": {"type": "C"},
    "2026-07-06": {"type": "A"},
    "2026-07-07": {"type": "A"},
    "2026-07-08": {"type": "A"},
    "2026-07-09": {"type": "A"},
    "2026-07-10": {"type": "B"},
    "2026-07-11": {"type": "E", "note": "외박 — 펜션, 친구들과 휴식. 알림 없음."},
    "2026-07-12": {"type": "E", "note": "외박 마지막날."},
    "2026-07-13": {"type": "A"},
    "2026-07-14": {"type": "A", "events": [{"time": "14:00", "title": "피부과 예약 (시간 확인해서 수정)"}]},
    "2026-07-15": {"type": "A"},
    "2026-07-16": {"type": "A"},
    "2026-07-17": {"type": "B"},
    "2026-07-18": {"type": "C"},
    "2026-07-19": {"type": "C"},
    "2026-07-20": {"type": "A"},
    "2026-07-21": {"type": "A"},
    "2026-07-22": {"type": "A"},
    "2026-07-23": {"type": "A"},
    "2026-07-24": {"type": "B"},
    "2026-07-25": {"type": "C"},
    "2026-07-26": {"type": "C"},
    "2026-07-27": {"type": "F"},
    "2026-07-28": {"type": "F", "events": [{"time": "14:00", "title": "피부과 예약 (잠정 — 외출 가능 여부 확인)"}]},
    "2026-07-29": {"type": "F"},
    "2026-07-30": {"type": "F"},
    "2026-07-31": {"type": "F"},
    "2026-08-01": {"type": "C"},
    "2026-08-02": {"type": "OFF", "note": "🎉 전역! 수고했다."}
  }
}
```

## 7. 구현 시 주의 / 확장 아이디어

- `24:00`은 자정이므로 다음 날 `00:00`으로 처리 (날짜 경계 주의).
- 알림이 OS에서 차단되지 않도록 첫 실행 시 권한 안내.
- 향후: 블록 완료 체크 → 일별 달성률 로그(`log.csv`) → 주간 리포트. (예전에 만든 친구 3명 목표추적 시스템과 연결해도 좋음.)
- "최소 성공 기준"(헬스 / 개발 1세션 / 독서 50p / X 1포스트) 4개만 따로 체크하는 모드도 추가하면 컨디션 나쁜 날 관리에 좋음.
- 설정 변경은 `config.json`만 수정하고 프로그램 재시작하면 반영되게 할 것.
