#!/usr/bin/env python3
"""
kids-english-bot (Gemini 버전) — B안 (그라운딩 제거 / 무료 티어 안정 운영)
매일 아침 초등학생용 영어 10선을 텔레그램 단체방으로 발송한다.
- 대상: 초등 3학년 + 6학년 남매 (한 단체방에서 함께 학습)
- 소재: 게임(로블록스·포켓몬고·브롤스타즈), 아이돌/K-pop, 초등 눈높이 소재, 교과(영어·사회·과학)
- cron-job.org가 매일 08:30(KST) GitHub API로 트리거하여 실행

[B안 변경점]
1) 구글 검색 그라운딩(google_search 도구) 제거 → 별도 할당량 소모 없음 → 429 방지
2) 모델을 별칭(gemini-flash-latest) → 고정 버전(gemini-2.5-flash)으로 변경
3) '실시간 검색' 지시를 없애고, 대신 '실제 뉴스를 지어내지 말 것 + 시점 무관 소재로 예문 구성'
   으로 프롬프트 수정 → 할루시네이션(가짜 컴백/경기 소식) 방지
"""

import os
import datetime
import requests
from google import genai
from google.genai import types

# ── 환경변수 (GitHub Secrets) ──────────────────────────────
GEMINI_API_KEY     = os.environ["GEMINI_API_KEY"]      # 기존 봇과 같은 시크릿 이름 사용
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]     # 단체방은 음수 (예: -1001234567890)

# 별칭 대신 고정 버전 사용. 무료 한도가 더 필요하면 "gemini-2.5-flash-lite"로 바꾸면 됨.
MODEL = "gemini-2.5-flash"

# 한국 시간 기준 오늘 날짜
KST   = datetime.timezone(datetime.timedelta(hours=9))
today = datetime.datetime.now(KST).strftime("%Y.%m.%d")

# ── 프롬프트 ────────────────────────────────────────────────
SYSTEM = (
    "너는 초등학생 영어 선생님이야. 두 남매를 위해 매일 영어 단어 10개를 뽑아준다. "
    "두 아이의 성향이 뚜렷이 다르니 각자에게 맞춰라.\n"
    "● 첫째 [초3] 여아: 아이돌·댄스·걸그룹·최신 트렌드에 민감하고, 문구/소품샵을 좋아한다. "
    "영어는 아직 기초 단계라 아주 쉬운 단어 위주로, 좋아하는 소재로 흥미를 끈다.\n"
    "● 둘째 [초6] 남아: 수학을 좋아하고, 스포츠 경기와 게임을 즐기며, 보드게임 카페에 자주 간다. "
    "영어에 막 흥미가 붙는 중이고, '과학고 진학'을 준비하는 아이라 과학·수학 개념 어휘와 "
    "조금 더 도전적인 표현을 학습 목표로 삼는다.\n"
    "아이들이 좋아하는 소재와 학교 교과를 엮어 재미와 공부가 같이 가게 한다. "
    "아이들이 평소 좋아하는 세계관(게임·아이돌·스포츠·보드게임 등)을 활용하되, "
    "특정 날짜의 실제 뉴스·사건·경기 결과·컴백 소식 같은 '확인 불가능한 최신 사실'은 절대 지어내지 마라. "
    "누가 언제 무엇을 했다는 식의 시의성 정보 대신, 시간이 지나도 맞는 일반적인 상황과 표현만 사용하라. "
    "항상 안전하고 긍정적인 내용만 다룬다."
)

USER = f"""오늘({today}) '초등 영어 10선'을 만들어줘.

[대상 — 두 아이 맞춤]
● 앞 4개 = [초3] 여아용. 아주 쉬운 단어(파닉스·기초 어휘). 소재는 이 아이가 좋아하는 것 위주:
  K-pop·걸그룹·아이돌, 댄스/무대, 문구·소품샵, 최신 유행. 예문도 이 세계관으로.
● 뒤 6개 = [초6] 남아용. 짧은 구/문장 수준이되 조금 더 도전적으로.
  소재는 이 아이가 좋아하는 것 + 학습 목표를 섞어라:
  - 스포츠 경기, 게임, 보드게임(전략·주사위·카드 등)
  - 수학 어휘(예: equation, multiply, angle, average, probability 등)
  - 과학 어휘(예: gravity, energy, molecule, experiment, orbit 등)
  → 이 아이는 '과학고 준비생'이므로, 6개 중 최소 3개는 수학·과학 개념 어휘로 채워
    실제 공부에 도움이 되게 하라. 나머지는 스포츠·게임·보드게임으로 흥미를 유지.

[형식] 각 항목은 그대로 지켜:
   *N. [초3]/[초6] 이모지 English — 한글 뜻*
   아이 눈높이의 짧은 예문 (English 단어는 *별표*로 강조)
   → 한글 해석
   (이모지: 🎤아이돌 / 💃댄스 / 🛍️소품 / 🎮게임 / 🎲보드게임 / ⚽스포츠 / ➗수학 / 🔬과학 / 📰뉴스)

[신선도 — 매우 중요]
- 너무 뻔한 기초 단어(cat, dog, run, win, catch, dance, happy 등)는 되도록 피하고,
  같은 뜻이라도 조금 더 새롭거나 상황이 있는 표현을 골라라.
- 소재 축을 매일 조금씩 순환시켜 겹치지 않게 하라
  (초3: 아이돌↔댄스↔소품↔유행 / 초6: 수학↔과학↔스포츠↔게임↔보드게임).
- 특정 날짜의 실제 뉴스·사건·경기 결과·컴백 소식 등을 지어내지 마라.
  '오늘 XX가 컴백했다', '어제 누가 이겼다' 같은 확인 불가능한 최신 사실은 절대 쓰지 말고,
  대신 아이들이 평소 좋아하는 소재의 '시점에 무관한 일반적인 장면'으로 예문을 구성하라
  (예: 걸그룹 무대 연습, 브롤스타즈 배틀, 축구 경기 장면, 보드게임 전략 등).

[마무리]
- 맨 끝에 '🎯 오늘의 미션' 한 줄: 오늘 단어 하나로 아이가 직접 영어 문장 만들어보기.
  가능하면 초3용·초6용 미션을 각각 한 줄씩(총 2줄) 줘도 좋다.
- 욕설·폭력·과금 유도 없이 안전하게. 텔레그램 발송용이므로 단어는 *별표*로 강조.

맨 위 제목은 반드시 이 형식으로 시작:
📚 오늘의 초등 영어 10선 ({today})

설명·머리말 없이 제목부터 바로 시작해."""

# ── 생성 (Gemini) ──────────────────────────────────────────
# ※ B안: google_search 그라운딩 도구를 제거했다. (별도 할당량 소모 → 429 원인 제거)
client = genai.Client(api_key=GEMINI_API_KEY)

resp = client.models.generate_content(
    model=MODEL,
    contents=USER,
    config=types.GenerateContentConfig(
        system_instruction=SYSTEM,
        max_output_tokens=2000,
        temperature=0.9,
    ),
)

body = (resp.text or "").strip()


# ── 텔레그램 발송 ───────────────────────────────────────────
def send_telegram(msg: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # 텔레그램 4096자 제한 → 넉넉히 분할
    for i in range(0, len(msg), 3500):
        chunk = msg[i:i + 3500]
        r = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": chunk,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=30,
        )
        # 마크다운 특수문자로 실패하면 서식 없이 재전송(안전장치)
        if not r.ok:
            requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID, "text": chunk,
                      "disable_web_page_preview": True},
                timeout=30,
            )


send_telegram(body)
print("발송 완료:", today)
