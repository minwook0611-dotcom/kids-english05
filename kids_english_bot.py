#!/usr/bin/env python3
"""
kids-english-bot (Groq 버전) — 한국어 품질 개선 + 시인성/발음 링크
매일 아침 초등학생용 영어 10선을 텔레그램 단체방으로 발송한다.

[이번 개선]
1) 모델을 llama → qwen/qwen3-32b 로 교체 (한국어 훨씬 자연스러움, 언어 혼입 감소)
2) 프롬프트 강화:
   - 초3은 '짧고 쉬운 기초 단어'만 (choreographer 같은 어려운 단어 금지)
   - 한국어 문장에 일본어·중국어·베트남어 등 다른 언어 문자 사용 절대 금지
3) 시인성: 영어 단어 <code> 강조 + 초3/초6 구역 분리 + 구분선
4) 발음: 단어 옆 🔊 네이버 영어사전 링크(원어민 음성)

* 최고의 한국어 품질을 원하면 Gemini(gemini-2.5-flash)가 더 낫다. (하단 주석 참고)
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

# 한국어 품질이 더 좋은 Qwen 사용. 속도가 더 필요하면 "llama-3.3-70b-versatile" 로 되돌릴 수 있음.
MODEL = "qwen/qwen3-32b"

# 한국 시간 기준 오늘 날짜
KST   = datetime.timezone(datetime.timedelta(hours=9))
today = datetime.datetime.now(KST).strftime("%Y.%m.%d")

# ── 프롬프트 (JSON 출력) ────────────────────────────────────
SYSTEM = (
    "너는 초등학생 영어 선생님이야. 두 남매를 위해 매일 영어 단어 10개를 뽑아준다.\n"
    "● 첫째 [초3] 여아: 영어 '초보'다. 아주 쉬운 기초 단어만 다룬다. "
    "아이돌·댄스·걸그룹·문구/소품 같은 좋아하는 소재로 흥미를 끈다.\n"
    "● 둘째 [초6] 남아: 수학·게임·스포츠·보드게임을 좋아하고 '과학고 진학'을 준비한다. "
    "과학·수학 개념 어휘와 조금 더 도전적인 표현을 학습 목표로 삼는다.\n"
    "[매우 중요 — 한국어 규칙] 모든 한국어 뜻·예문·해석은 오직 '한글'과 '지정된 영어 단어'로만 써라. "
    "일본어 한자(私 등)·중국어·베트남어 등 다른 언어의 문자나 단어를 절대 섞지 마라. "
    "적절한 한국어가 떠오르지 않으면 더 쉽고 단순한 한국어 문장으로 바꿔라. 어색한 직역도 금지.\n"
    "특정 날짜의 실제 뉴스·경기 결과·컴백 소식 같은 확인 불가능한 최신 사실은 지어내지 말고, "
    "시점에 무관한 일반적인 장면으로 예문을 만든다. 항상 안전하고 긍정적인 내용만 다룬다. "
    "출력은 지정한 JSON 형식만, 그 외 어떤 글자도 쓰지 않는다."
)

USER = f"""오늘({today})의 '초등 영어 10선'을 아래 JSON 형식으로만 만들어줘.

[구성]
- items 배열은 정확히 10개.
- 앞 4개는 grade="초3": 반드시 '짧고 쉬운 기초 단어'만. 대략 3~6글자, 초보가 아는 수준
  (예: star, gift, song, cute, pink, dream, smile, dance, happy, cook, jump 등).
  choreographer, accessorize, harmony 같이 길거나 어려운 단어는 절대 쓰지 마라.
  소재는 K-pop·아이돌·댄스·문구/소품·유행. (초3은 쉬운 게 최우선, 새로움보다 쉬움 우선)
- 뒤 6개는 grade="초6": 조금 더 도전적. 소재는 스포츠·게임·보드게임 + 수학/과학 개념 어휘.
  이 6개 중 최소 3개는 수학·과학 개념 어휘(예: equation, probability, molecule, gravity, orbit 등).
  초6은 너무 뻔한 단어는 피하고 매일 소재를 조금씩 순환시켜라.

[각 item 필드]
- grade: "초3" 또는 "초6"
- emoji: 소재에 맞는 이모지 1개 (🎤아이돌 💃댄스 🛍️소품 🎮게임 🎲보드게임 ⚽스포츠 ➗수학 🔬과학 중 택1)
- word: 영어 단어 (첫 글자 대문자)
- meaning: 한국어 뜻 (짧고 자연스럽게)
- example_en: 아이 눈높이의 짧은 예문. 한국어 문장 안에 그 영어 단어를 넣되,
  그 단어는 반드시 **별표두개**로 감싸라. 예: "무대에서 예쁜 **dance**를 춘다."
  (예문의 나머지는 오직 한글로만! 다른 언어 문자 금지)
- example_kr: 위 예문의 자연스러운 한국어 해석

[미션]
- mission_cho3: 초3 아이가 오늘 단어 하나로 영어 문장 만들어보는 쉬운 미션 한 줄
- mission_cho6: 초6 아이용 미션 한 줄

아래 형식의 JSON 객체 하나만 출력해(코드펜스·설명·다른 언어 문자 없이):
{{
  "items": [
    {{"grade":"초3","emoji":"💃","word":"Dance","meaning":"춤, 춤추다","example_en":"무대에서 예쁜 **dance**를 춘다.","example_kr":"무대에서 예쁜 춤을 춘다."}}
  ],
  "mission_cho3":"...",
  "mission_cho6":"..."
}}"""

# ── 생성 (Groq / OpenAI 호환, JSON 모드 + 안전장치) ────────
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY,
)

def generate(use_json: bool):
    kwargs = dict(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user",   "content": USER},
        ],
        max_tokens=2500,
        temperature=0.8,
    )
    if use_json:
        kwargs["response_format"] = {"type": "json_object"}
    return client.chat.completions.create(**kwargs)

try:
    resp = generate(True)
except Exception:
    resp = generate(False)   # 모델이 JSON 모드 미지원이면 일반 모드로 재시도

raw = (resp.choices[0].message.content or "").strip()
# qwen 계열은 <think>...</think> 사고과정을 붙일 수 있어 제거
raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


# ── JSON 파싱 (안전장치) ────────────────────────────────────
def parse_json(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    # 본문 어딘가에 {} 객체만 뽑아내는 최후 보정
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if m:
        text = m.group(0)
    return json.loads(text)


# ── 텔레그램 HTML 조립 ──────────────────────────────────────
def esc(s) -> str:
    return html.escape(str(s or "").strip())

def naver_link(word: str) -> str:
    # 네이버 영어사전(뜻+원어민 음성). 캠브리지로 바꾸려면:
    #   https://dictionary.cambridge.org/dictionary/english/<word>
    return f"https://en.dict.naver.com/#/search?query={quote(word)}"

def render_example(ex: str) -> str:
    e = esc(ex)
    e = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", e)
    e = e.replace("*", "")
    return e

def build_message(data: dict) -> str:
    L = []
    L.append(f"📚 <b>오늘의 초등 영어 10선 ({today})</b>")
    L.append("━━━━━━━━━━━━")

    prev = None
    for i, it in enumerate(data.get("items", []), 1):
        grade = str(it.get("grade", ""))
        if grade != prev:
            L.append("")
            L.append("👧 <b>[초3] 쉬운 단어</b>" if "초3" in grade
                     else "👦 <b>[초6] 도전 단어</b>")
            prev = grade

        word    = it.get("word", "")
        w_e     = esc(word)
        emoji   = esc(it.get("emoji", ""))
        meaning = esc(it.get("meaning", ""))
        link    = f'🔊 <a href="{naver_link(word)}">발음</a>'

        L.append(f"<b>{i}. {emoji} <code>{w_e}</code></b> — {meaning}   {link}")
        L.append(render_example(it.get("example_en", "")))
        L.append(f"→ {esc(it.get('example_kr', ''))}")
        L.append("")

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
        if not r.ok:
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
    send_telegram(f"⚠️ 서식 생성 실패, 원문 발송\n\n{raw}", use_html=False)
    print("파싱 실패:", e)

print("발송 완료:", today)
