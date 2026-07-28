#!/usr/bin/env python3
"""
kids-english-bot (Groq / gpt-oss-120b) — 중복 단어 제외 기능 추가
매일 아침 초등학생용 영어 10선을 텔레그램 단체방으로 발송한다.

[이번 개선]
1) 중복 방지: 이미 배포한 단어를 sent_words.json 에 누적 저장하고,
   다음 실행 때 그 목록을 프롬프트에 넣어 '다시 쓰지 마라'고 지시 → 매일 새 단어만.
   (워크플로우가 sent_words.json 을 리포에 커밋해줘야 기억이 유지됨 — .yml 참고)
2) 미션 줄의 **단어** 굵게 표시 버그 수정.

* 시인성(<code> 강조/구분선) + 발음(🔊 네이버 사전 링크) 기능은 그대로.
"""

import os
import re
import html
import json
import pathlib
import datetime
from urllib.parse import quote

import requests
from openai import OpenAI

# ── 환경변수 (GitHub Secrets) ──────────────────────────────
GROQ_API_KEY       = os.environ["GROQ_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

# Groq에서 현재 사용 가능 + 무료 티어 모델.
MODEL = "openai/gpt-oss-120b"

# 한국 시간 기준 오늘 날짜
KST   = datetime.timezone(datetime.timedelta(hours=9))
today = datetime.datetime.now(KST).strftime("%Y.%m.%d")

# ── 배포 이력(중복 방지) ────────────────────────────────────
HISTORY_FILE = pathlib.Path("sent_words.json")

def load_history() -> list:
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8")).get("words", [])
    except Exception:
        return []

def save_history(words: list) -> None:
    HISTORY_FILE.write_text(
        json.dumps({"words": words}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

sent_words = load_history()                     # 이미 배포한 단어(소문자) 목록
avoid_block = ", ".join(sent_words) if sent_words else "(아직 없음)"

# ── 프롬프트 (JSON 출력) ────────────────────────────────────
SYSTEM = (
    "너는 초등학생 영어 선생님이야. 두 남매를 위해 매일 영어 단어 10개를 뽑아준다.\n"
    "● 첫째 [초3] 여아: 영어 '초보'다. 아주 쉬운 기초 단어만 다룬다. "
    "아이돌·댄스·걸그룹·문구/소품 같은 좋아하는 소재로 흥미를 끈다.\n"
    "● 둘째 [초6] 남아: 수학·게임·스포츠·보드게임을 좋아하고 '과학고 진학'을 준비한다. "
    "과학·수학 개념 어휘와 조금 더 도전적인 표현을 학습 목표로 삼는다.\n"
    "[매우 중요 — 한국어 규칙] 모든 한국어 뜻·예문·해석은 오직 '한글'과 '지정된 영어 단어'로만 써라. "
    "일본어 한자(私 등)·중국어·베트남어 등 다른 언어의 문자나 단어를 절대 섞지 마라. "
    "적절한 한국어가 떠오르지 않으면 더 쉽고 단순한 한국어 문장으로 바꿔라.\n"
    "특정 날짜의 실제 뉴스·경기 결과·컴백 소식 같은 확인 불가능한 최신 사실은 지어내지 말고, "
    "시점에 무관한 일반적인 장면으로 예문을 만든다. 항상 안전하고 긍정적인 내용만 다룬다. "
    "출력은 지정한 JSON 형식만, 그 외 어떤 글자도 쓰지 않는다."
)

USER = f"""오늘({today})의 '초등 영어 10선'을 아래 JSON 형식으로만 만들어줘.

[이미 배포한 단어 — 절대 다시 쓰지 마라] (대소문자 무관)
{avoid_block}
- 위 목록에 있는 단어는 뜻이 같아도 반드시 '다른 새 단어'로 대체하라.
- 오늘 뽑는 10개는 전부 위 목록에 '없는' 단어여야 한다.

[구성]
- items 배열은 정확히 10개.
- 앞 4개는 grade="초3": 반드시 '짧고 쉬운 기초 단어'만. 대략 3~6글자, 초보가 아는 수준
  (예: sky, rain, doll, ribbon, jump, smile, cook, paint 등). 길거나 어려운 단어 금지.
  소재는 K-pop·아이돌·댄스·문구/소품·유행. (초3은 쉬운 게 최우선)
- 뒤 6개는 grade="초6": 조금 더 도전적. 소재는 스포츠·게임·보드게임 + 수학/과학 개념 어휘.
  이 6개 중 최소 3개는 수학·과학 개념 어휘(예: fraction, angle, gravity, energy, orbit 등).

[각 item 필드]
- grade: "초3" 또는 "초6"
- emoji: 소재에 맞는 이모지 1개 (🎤아이돌 💃댄스 🛍️소품 🎮게임 🎲보드게임 ⚽스포츠 ➗수학 🔬과학 중 택1)
- word: 영어 단어 (첫 글자 대문자)
- meaning: 한국어 뜻 (짧고 자연스럽게)
- example_en: 아이 눈높이의 짧은 예문. 한국어 문장 안에 그 영어 단어를 넣되,
  그 단어는 반드시 **별표두개**로 감싸라. 예: "하늘에서 **rain**이 내린다."
  (예문의 나머지는 오직 한글로만! 다른 언어 문자 금지)
- example_kr: 위 예문의 자연스러운 한국어 해석

[미션]
- mission_cho3: 초3 아이가 오늘 단어 하나로 영어 문장 만들어보는 쉬운 미션 한 줄
- mission_cho6: 초6 아이용 미션 한 줄

아래 형식의 JSON 객체 하나만 출력해(코드펜스·설명·다른 언어 문자 없이):
{{
  "items": [
    {{"grade":"초3","emoji":"💃","word":"Rain","meaning":"비","example_en":"하늘에서 **rain**이 내린다.","example_kr":"하늘에서 비가 내린다."}}
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
    resp = generate(False)

raw = (resp.choices[0].message.content or "").strip()
raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


# ── JSON 파싱 (안전장치) ────────────────────────────────────
def parse_json(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
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

def render_rich(text: str) -> str:
    """이스케이프 후 **단어** → 굵게 변환 (예문·미션 공통)"""
    e = esc(text)
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
        L.append(render_rich(it.get("example_en", "")))
        L.append(f"→ {esc(it.get('example_kr', ''))}")
        L.append("")

    L.append("━━━━━━━━━━━━")
    L.append("🎯 <b>오늘의 미션</b>")
    if data.get("mission_cho3"):
        L.append(f"👧 {render_rich(data['mission_cho3'])}")
    if data.get("mission_cho6"):
        L.append(f"👦 {render_rich(data['mission_cho6'])}")
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

    # 발송 성공 시에만 이력 갱신 (중복 방지)
    today_words = [str(it.get("word", "")).strip().lower()
                   for it in data.get("items", []) if it.get("word")]
    merged = sent_words + [w for w in today_words if w and w not in sent_words]
    save_history(merged)
    print(f"발송 완료: {today} / 누적 단어 {len(merged)}개")

except Exception as e:
    send_telegram(f"⚠️ 서식 생성 실패, 원문 발송\n\n{raw}", use_html=False)
    print("파싱 실패:", e)
