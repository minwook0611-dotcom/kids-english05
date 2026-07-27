#!/usr/bin/env python3
"""
kids-english-bot (Gemini 버전)
매일 아침 초등학생용 영어 10선을 텔레그램 단체방으로 발송한다.
- 대상: 초등 3학년 + 6학년 남매 (한 단체방에서 함께 학습)
- 소재: 게임(로블록스·포켓몬고·브롤스타즈), 아이돌/K-pop, 초등 눈높이 뉴스, 교과(영어·사회·과학)
- 기존 시사영어 봇과 동일하게 GitHub Actions cron으로 매일 07:00(KST) 실행
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

MODEL = "gemini-flash-latest"   # 기존 봇이 쓰는 모델명과 동일하게 맞추면 됨

# 한국 시간 기준 오늘 날짜
KST   = datetime.timezone(datetime.timedelta(hours=9))
today = datetime.datetime.now(KST).strftime("%Y.%m.%d")

# ── 프롬프트 ────────────────────────────────────────────────
SYSTEM = (
    "너는 초등학생 영어 선생님이야. 초등학교 3학년과 6학년 남매를 위해 "
    "매일 영어 단어 10개를 뽑아준다. 아이들이 좋아하는 소재(게임: 로블록스·포켓몬고·"
    "브롤스타즈, 아이돌/K-pop, 초등 눈높이 뉴스)와 학교 교과(영어·사회·과학)를 엮어 "
    "재미있게 만든다. 요즘 실제로 화제인 게임 이벤트나 아이돌 소식을 구글 검색으로 "
    "확인해서 자연스럽게 반영해라. 항상 안전하고 긍정적인 내용만 다룬다."
)

USER = f"""오늘({today}) '초등 영어 10선'을 만들어줘.

[대상 — 두 아이 맞춤]
● 앞 4개 = [초3] 여아용. 아주 쉬운 단어(파닉스·기초 어휘). 소재는 이 아이가 좋아하는 것 위주:
  K-pop·걸그룹·아이돌, 댄스/무대, 문구·소품샵, 최신 유행. 예문도 이 세계관으로.
● 뒤 6개 = [초6] 남아용. 짧은 구/문장 수준이되 조금 더 도전적으로.
  소재는 이 아이가 좋아하는 것 + 학습 목표를 섞어라:
  - 스포츠 경기, 게임, 보드게임(전략·주사위·카드 등)
  - 수학 어휘(예: equation, multiply, angle, average, probability 등)
  - 과학 어휘(예: gravity, energy, molecule, experiment, gravity, orbit 등)
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
- 오늘 날짜 기준 실제 화제를 구글 검색으로 확인해 반영하라
  (최신 컴백·걸그룹 소식, 스포츠 경기, 포켓몬/브롤스타즈/로블록스 이벤트 등).
 
[마무리]
- 맨 끝에 '🎯 오늘의 미션' 한 줄: 오늘 단어 하나로 아이가 직접 영어 문장 만들어보기.
  가능하면 초3용·초6용 미션을 각각 한 줄씩(총 2줄) 줘도 좋다.
- 욕설·폭력·과금 유도 없이 안전하게. 텔레그램 발송용이므로 단어는 *별표*로 강조.
 
맨 위 제목은 반드시 이 형식으로 시작:
📚 오늘의 초등 영어 10선 ({today})
 
설명·머리말 없이 제목부터 바로 시작해."""

# ── 생성 (Gemini + 구글 검색 그라운딩) ─────────────────────
client = genai.Client(api_key=GEMINI_API_KEY)

resp = client.models.generate_content(
    model=MODEL,
    contents=USER,
    config=types.GenerateContentConfig(
        system_instruction=SYSTEM,
        tools=[types.Tool(google_search=types.GoogleSearch())],
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
