#!/usr/bin/env python3
"""
kids-english-bot (Groq / gpt-oss-120b) — 중복 단어 제외 기능 추가
매일 아침 초등학생용 영어 10선을 텔레그램 단체방으로 발송한다.

[이번 개선]
1) 중복 방지: 이미 배포한 단어를 sent_words.json 에 누적 저장하고,
   다음 실행 때 그 목록을 프롬프트에 넣어 '다시 쓰지 마라'고 지시 → 매일 새 단어만.
   (워크플로우가 sent_words.json 을 리포에 커밋해줘야 기억이 유지됨 — .yml 참고)
2) 예문 구조 변경: 2번째 줄을 '완전한 영어 문장'으로, 3번째 줄은 그 한국어 해석으로.

* 시인성(<code> 강조/구분선) + 발음(🔊 네이버 사전 링크) 기능은 그대로.
"""

import os
import re
import sys
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
- sentence_en: 그 단어를 사용한 '완전한 영어 문장' 한 개. 아이 눈높이의 짧고 문법에 맞는 문장이어야 한다.
  대상 단어는 반드시 **별표두개**로 감싸라. 예: "I sing a **song**."
  (초3은 아주 짧고 쉬운 영어 3~6단어 문장, 초6은 조금 더 길어도 됨. 반드시 완전한 영어 문장!)
- sentence_kr: 위 영어 문장의 자연스러운 한국어 해석 (오직 한글로만, 다른 언어 문자 금지)

[미션]
- mission_cho3: 초3 아이가 오늘 단어 하나로 영어 문장 만들어보는 쉬운 미션 한 줄
- mission_cho6: 초6 아이용 미션 한 줄

아래 형식의 JSON 객체 하나만 출력해(코드펜스·설명·다른 언어 문자 없이):
{{
  "items": [
    {{"grade":"초3","emoji":"🎤","word":"Song","meaning":"노래","sentence_en":"I sing a **song**.","sentence_kr":"나는 노래를 불러요."}}
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
        max_tokens=4000,          # gpt-oss는 '생각'에도 토큰을 쓰므로 넉넉히
        temperature=0.8,
        # gpt-oss 계열: 불필요한 장고를 줄여 JSON 출력에 토큰을 확보 (핵심 안정화)
        extra_body={"reasoning_effort": "low"},
    )
    if use_json:
        kwargs["response_format"] = {"type": "json_object"}
    return client.chat.completions.create(**kwargs)

def _extract(resp):
    raw = (resp.choices[0].message.content or "").strip()
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


# ── JSON 파싱 (안전장치) ────────────────────────────────────
def parse_json(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if m:
        text = m.group(0)
    return json.loads(text)


def fetch_data(max_attempts: int = 3) -> dict:
    """모델 호출 → JSON 파싱까지 최대 max_attempts번 재시도. 실패 시 마지막 에러를 던진다."""
    last = None
    for _ in range(max_attempts):
        try:
            data = parse_json(_extract(generate(use_json=True)))
            if data.get("items"):
                return data
            last = ValueError("items 비어있음")
        except Exception as e:
            last = e
    # 최후: JSON 모드 없이 한 번 더
    try:
        data = parse_json(_extract(generate(use_json=False)))
        if data.get("items"):
            return data
    except Exception as e:
        last = e
    raise last if last else RuntimeError("알 수 없는 실패")


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
        L.append(render_rich(it.get("sentence_en", "")))
        L.append(f"→ {esc(it.get('sentence_kr', ''))}")
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
    data = fetch_data()                      # 재시도 포함
    body = build_message(data)
    send_telegram(body, use_html=True)

    # 발송 성공 시에만 이력 갱신 (중복 방지)
    today_words = [str(it.get("word", "")).strip().lower()
                   for it in data.get("items", []) if it.get("word")]
    merged = sent_words + [w for w in today_words if w and w not in sent_words]
    save_history(merged)
    print(f"발송 완료: {today} / 누적 단어 {len(merged)}개")

except Exception as e:
    # 여러 번 재시도해도 실패한 경우: 단체방을 지저분하게 만들지 않고 조용히 종료.
    # 단, GitHub Actions에는 '실패(빨간불)'로 남겨 사용자가 인지하도록 exit 1.
    print("최종 실패(재시도 소진):", repr(e))
    sys.exit(1)
