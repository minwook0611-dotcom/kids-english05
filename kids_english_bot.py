#!/usr/bin/env python3
"""
kids-english-bot (Groq 버전) — 시인성 개선 + 발음 링크
매일 아침 초등학생용 영어 10선을 텔레그램 단체방으로 발송한다.

[이번 개선]
1) 시인성: 영어 단어를 <code> 회색 박스로 강조(탭하면 복사), 초3/초6 구역 분리 + 구분선
2) 발음: 각 단어 옆에 🔊 네이버 영어사전 링크(원어민 음성) 자동 삽입
3) 안정성: 모델이 'JSON'으로만 내용을 내고, 파이썬이 텔레그램 HTML로 조립
   → 서식 깨짐/마크다운 특수문자 문제 없음
* 텔레그램 봇은 임의 '글자 배경색'은 지원하지 않아, 배경 느낌은 <code> 박스로 대체.
"""

import os
import re
import html
import json
import datetime
from urllib.parse import quote

import requests
from openai import OpenAI

# ── 환경변수 (GitHub Secrets) ──────────────────────────────
GROQ_API_KEY       = os.environ["GROQ_API_KEY"]        # gsk_... 로 시작
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]     # 단체방은 음수 (예: -1001234567890)

# 한국어가 어색하면(예: '배웠다'가 '學んだ'로 나옴) "qwen/qwen3-32b" 로 바꿔보면 됨.
MODEL = "llama-3.3-70b-versatile"

# 한국 시간 기준 오늘 날짜
KST   = datetime.timezone(datetime.timedelta(hours=9))
today = datetime.datetime.now(KST).strftime("%Y.%m.%d")

# ── 프롬프트 (JSON 출력) ────────────────────────────────────
SYSTEM = (
    "너는 초등학생 영어 선생님이야. 두 남매를 위해 매일 영어 단어 10개를 뽑아준다. "
    "두 아이의 성향이 뚜렷이 다르니 각자에게 맞춰라.\n"
    "● 첫째 [초3] 여아: 아이돌·댄스·걸그룹·최신 트렌드에 민감하고, 문구/소품샵을 좋아한다. "
    "영어는 아직 기초 단계라 아주 쉬운 단어 위주로, 좋아하는 소재로 흥미를 끈다.\n"
    "● 둘째 [초6] 남아: 수학을 좋아하고, 스포츠 경기와 게임을 즐기며, 보드게임 카페에 자주 간다. "
    "'과학고 진학'을 준비하는 아이라 과학·수학 개념 어휘와 조금 더 도전적인 표현을 학습 목표로 삼는다.\n"
    "아이들이 좋아하는 소재와 학교 교과를 엮되, 특정 날짜의 실제 뉴스·경기 결과·컴백 소식 같은 "
    "'확인 불가능한 최신 사실'은 절대 지어내지 말고, 시점에 무관한 일반적인 장면으로 예문을 만들어라. "
    "모든 한국어 설명·해석은 반드시 자연스러운 한국어로만 쓴다(일본어·중국어 문자 혼용 절대 금지). "
    "항상 안전하고 긍정적인 내용만 다룬다. 출력은 지정한 JSON 형식만, 그 외 어떤 글자도 쓰지 않는다."
)

USER = f"""오늘({today})의 '초등 영어 10선'을 아래 JSON 형식으로만 만들어줘.

[구성]
- items 배열은 정확히 10개.
- 앞 4개는 grade="초3" (여아용): 아주 쉬운 단어. 소재는 K-pop·걸그룹·아이돌·댄스·문구/소품·유행.
- 뒤 6개는 grade="초6" (남아용): 조금 더 도전적. 소재는 스포츠·게임·보드게임 + 수학/과학 개념 어휘.
  이 6개 중 최소 3개는 수학·과학 개념 어휘(예: equation, probability, molecule, gravity, orbit 등).
- 너무 뻔한 기초 단어(cat, dog, run, win, happy 등)는 피하고, 매일 소재를 조금씩 순환시켜라.

[각 item 필드]
- grade: "초3" 또는 "초6"
- emoji: 소재에 맞는 이모지 1개 (🎤아이돌 💃댄스 🛍️소품 🎮게임 🎲보드게임 ⚽스포츠 ➗수학 🔬과학 중 택1)
- word: 영어 단어 (첫 글자 대문자)
- meaning: 한국어 뜻 (짧게)
- example_en: 아이 눈높이의 짧은 예문. 한국어 문장 안에 그 영어 단어를 넣되,
  그 단어는 반드시 **별표두개**로 감싸라. 예: "무대를 위해 **choreographer**와 함께 연습한다."
- example_kr: 위 예문의 한국어 해석

[미션]
- mission_cho3: 초3 아이가 오늘 단어 하나로 영어 문장 만들어보는 미션 한 줄
- mission_cho6: 초6 아이용 미션 한 줄

아래 형식의 JSON 객체 하나만 출력해(코드펜스·설명 없이):
{{
  "items": [
    {{"grade":"초3","emoji":"💃","word":"Choreographer","meaning":"안무가","example_en":"새로운 무대를 위해 **choreographer**와 함께 연습한다.","example_kr":"새로운 무대를 위해 안무가와 함께 연습한다."}}
  ],
  "mission_cho3":"...",
  "mission_cho6":"..."
}}"""

# ── 생성 (Groq / OpenAI 호환, JSON 모드) ───────────────────
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY,
)

resp = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": SYSTEM},
        {"role": "user",   "content": USER},
    ],
    max_tokens=2500,
    temperature=0.9,
    response_format={"type": "json_object"},
)

raw = (resp.choices[0].message.content or "").strip()


# ── JSON 파싱 (안전장치) ────────────────────────────────────
def parse_json(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return json.loads(text)


# ── 텔레그램 HTML 조립 ──────────────────────────────────────
def esc(s) -> str:
    return html.escape(str(s or "").strip())

def naver_link(word: str) -> str:
    # 네이버 영어사전(뜻+원어민 음성). 캠브리지로 바꾸려면:
    #   https://dictionary.cambridge.org/dictionary/english/<word>
    return f"https://en.dict.naver.com/#/search?query={quote(word)}"

def render_example(ex: str) -> str:
    e = esc(ex)                                     # 먼저 이스케이프
    e = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", e)    # **단어** → 굵게
    e = e.replace("*", "")                           # 남은 별표 제거
    return e

def build_message(data: dict) -> str:
    L = []
    L.append(f"📚 <b>오늘의 초등 영어 10선 ({today})</b>")
    L.append("━━━━━━━━━━━━")

    prev = None
    for i, it in enumerate(data.get("items", []), 1):
        grade = str(it.get("grade", ""))
        if grade != prev:
            if "초3" in grade:
                L.append("")
                L.append("👧 <b>[초3] 쉬운 단어</b>")
            else:
                L.append("")
                L.append("👦 <b>[초6] 도전 단어</b>")
            prev = grade

        word    = it.get("word", "")
        w_e     = esc(word)
        emoji   = esc(it.get("emoji", ""))
        meaning = esc(it.get("meaning", ""))
        link    = f'🔊 <a href="{naver_link(word)}">발음</a>'

        L.append(f"<b>{i}. {emoji} <code>{w_e}</code></b> — {meaning}   {link}")
        L.append(render_example(it.get("example_en", "")))
        L.append(f"→ {esc(it.get('example_kr', ''))}")
        L.append("")   # 항목 사이 빈 줄

    L.append("━━━━━━━━━━━━")
    L.append("🎯 <b>오늘의 미션</b>")
    if data.get("mission_cho3"):
        L.append(f"👧 {esc(data['mission_cho3'])}")
    if data.get("mission_cho6"):
        L.append(f"👦 {esc(data['mission_cho6'])}")
    return "\n".join(L)


# ── 텔레그램 발송 ───────────────────────────────────────────
def send_telegram(msg: str, use_html: bool = True) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # 4096자 제한 → 줄 경계에서만 분할(태그 안 깨지게)
    chunks, cur = [], ""
    for line in msg.split("\n"):
        if len(cur) + len(line) + 1 > 3500:
            chunks.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        chunks.append(cur)

    for chunk in chunks:
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "disable_web_page_preview": True,
        }
        if use_html:
            data["parse_mode"] = "HTML"
        r = requests.post(url, data=data, timeout=30)
        if not r.ok:  # 서식 문제 시 서식 없이 재전송
            requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID, "text": chunk,
                      "disable_web_page_preview": True},
                timeout=30,
            )


# ── 실행 ────────────────────────────────────────────────────
try:
    data = parse_json(raw)
    body = build_message(data)
    send_telegram(body, use_html=True)
except Exception as e:
    # JSON이 깨진 드문 경우: 원문이라도 발송(서식 없이)
    send_telegram(f"⚠️ 서식 생성 실패, 원문 발송\n\n{raw}", use_html=False)
    print("파싱 실패:", e)

print("발송 완료:", today)
