#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import re
import shutil
import ssl
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter


KST = timezone(timedelta(hours=9))

RESTAURANT_URLS = {
    "main": "https://lily.sunmoon.ac.kr/Page2/UnivLife/WeekFoodMenu.aspx?ca=001",
    "orange": "https://lily.sunmoon.ac.kr/Page2/UnivLife/WeekFoodMenu.aspx?ca=002",
    "student": "https://lily.sunmoon.ac.kr/Page2/UnivLife/WeekFoodMenu.aspx?ca=003",
}

RESTAURANTS = {
    "student": {
        "name": "학생회관식당",
        "sourceName": "학생회관 식당",
        "location": "학생회관 식당",
        "openTime": "11:00 ~ 15:00",
    },
    "orange": {
        "name": "오렌지식당",
        "sourceName": "오렌지식당",
        "location": "오렌지식당",
        "openTime": "한식/분식 10:30 ~ 16:00, 돈가스/우동 10:30 ~ 15:00",
    },
    "main": {
        "name": "본관식당",
        "sourceName": "본관 교직원식당",
        "location": "본관 교직원식당",
        "openTime": "점심 11:30 ~ 13:30, 저녁 17:30 ~ 18:30",
    },
}

CATEGORY_WORDS = {
    "한식", "양식", "분식", "일식", "즉석", "양식&분식",
    "점심", "저녁", "조식", "중식", "석식",
    "메뉴", "식단", "일자", "오늘의 식단",
}

TEXT_FIXES = {
    "순두부지깨": "순두부찌개",
    "함밤카레": "함박카레",
    "떢볶이": "떡볶이",
    "떡볶이 & 오뎅 SET": "떡볶이&오뎅 SET",
    "김밥 & 오뎅 SET": "김밥&오뎅 SET",
}

STATIC_INGREDIENTS = {
    "student": {
        "text": "[학생회관식당 성분/주의 정보]\n\n메뉴별 원재료 정보는 고정 메뉴 기준으로 별도 관리합니다.\n돼지고기, 육류 육수, 우유, 계란, 밀, 대두, 해산물 등은 실제 조리 상황에 따라 달라질 수 있으므로 식당에 확인이 필요합니다."
    },
    "orange": {
        "text": "[오렌지식당 성분/주의 정보]\n\n메뉴별 원재료 정보는 고정 메뉴 기준으로 별도 관리합니다.\n제육, 돈가스, 순대국밥, 부대찌개 등은 돼지고기 포함 가능성이 높으므로 이슬람 식단 이용자는 주의가 필요합니다."
    },
    "main": {
        "text": "[본관/교직원식당 성분/주의 정보]\n\n본관/교직원식당은 식단이 매일 변경되므로 고정 성분표를 제공하지 않습니다.\n알레르기, 이슬람 식단, 채식 등 식이 제한이 있는 경우 실제 배식 전 식당에 직접 확인해 주세요."
    },
}


class LegacyTLSAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        ctx = ssl.create_default_context()

        try:
            ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        except Exception:
            pass

        if hasattr(ssl, "OP_LEGACY_SERVER_CONNECT"):
            ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT

        if hasattr(ssl, "TLSVersion"):
            try:
                ctx.minimum_version = ssl.TLSVersion.TLSv1
                ctx.maximum_version = ssl.TLSVersion.MAXIMUM_SUPPORTED
            except Exception:
                pass

        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        pool_kwargs["ssl_context"] = ctx

        return super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()

    for wrong, right in TEXT_FIXES.items():
        text = text.replace(wrong, right)

    return text


def split_cell_text(text: str) -> List[str]:
    result = []

    for raw in text.splitlines():
        line = clean_text(raw)

        if not line:
            continue

        if line in CATEGORY_WORDS:
            continue

        if is_date_or_day(line):
            continue

        if is_junk(line):
            continue

        result.append(line)

    return result


def is_date_or_day(line: str) -> bool:
    if re.match(r"^\d{2}월\s*\d{1,2}일", line):
        return True

    if re.match(r"^\([월화수목금토일]\)$", line):
        return True

    if re.match(r"^\d{4}-\d{2}-\d{2}", line):
        return True

    return False


def is_junk(line: str) -> bool:
    if not line:
        return True

    junk_keywords = [
        "개인정보처리방침",
        "이메일",
        "대학정보공시",
        "찾아오시는길",
        "원격지원",
        "교내웹사이트",
        "교내전화번호",
        "교직원찾기",
        "SUN MOON",
        "Tel",
        "Fax",
        "All rights reserved",
        "선문바로가기",
        "운영시간",
        "메뉴가격",
        "운영안내",
        "기타사항",
        "학사일정",
        "토요일/일요일",
        "방학",
        "금액",
        "카드",
        "현금",
        "키오스크",
    ]

    if any(keyword in line for keyword in junk_keywords):
        return True

    if line in CATEGORY_WORDS:
        return True

    return False


def decode_bytes(data: bytes) -> str:
    for encoding in ["utf-8", "cp949", "euc-kr"]:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    return data.decode("utf-8", errors="replace")


def candidate_urls(url: str) -> List[str]:
    urls = [url]

    if url.startswith("https://"):
        urls.append("http://" + url[len("https://"):])

    return list(dict.fromkeys(urls))


def fetch_with_requests(url: str, legacy_tls: bool = False) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/148.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Connection": "close",
    }

    session = requests.Session()

    if legacy_tls:
        session.mount("https://", LegacyTLSAdapter())

    response = session.get(
        url,
        headers=headers,
        timeout=25,
        verify=False if legacy_tls else True,
        allow_redirects=True,
    )

    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding or "utf-8"

    return response.text


def fetch_with_curl_cffi(url: str) -> str:
    from curl_cffi import requests as curl_requests

    response = curl_requests.get(
        url,
        impersonate="chrome120",
        timeout=25,
        verify=False,
        headers={"Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"},
    )

    response.raise_for_status()

    return response.text


def fetch_with_curl_command(url: str) -> str:
    curl_path = shutil.which("curl")

    if not curl_path:
        raise RuntimeError("curl 명령어를 찾지 못했습니다.")

    cmd = [
        curl_path,
        "-L",
        "-k",
        "--http1.1",
        "--tlsv1.2",
        "-A",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/148 Safari/537.36",
        "--max-time",
        "30",
        url,
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[:1000])

    return decode_bytes(result.stdout)


def fetch_html(url: str) -> str:
    errors = []

    for target_url in candidate_urls(url):
        methods = [
            ("requests", lambda: fetch_with_requests(target_url, legacy_tls=False)),
            ("requests_legacy_tls", lambda: fetch_with_requests(target_url, legacy_tls=True)),
            ("curl_cffi", lambda: fetch_with_curl_cffi(target_url)),
            ("curl_command", lambda: fetch_with_curl_command(target_url)),
        ]

        for method_name, request_func in methods:
            try:
                print(f"[INFO] 요청 시도: {method_name} / {target_url}")
                html = request_func()

                if "금주의식단" in html or "식단" in html:
                    print(f"[OK] 요청 성공: {method_name}")
                    return html

                if len(html) > 500:
                    print(f"[WARN] 식단 키워드는 없지만 HTML을 받았습니다: {method_name}")
                    return html

                raise RuntimeError("응답 HTML이 너무 짧습니다.")

            except Exception as exc:
                message = f"{method_name} / {target_url} -> {type(exc).__name__}: {exc}"
                errors.append(message)
                print(f"[WARN] 실패: {message}")

    raise RuntimeError("식단 페이지를 가져오지 못했습니다.\n- " + "\n- ".join(errors))


def get_table_rows(html: str) -> List[List[str]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")

    if table is None:
        return []

    rows = []

    for tr in table.find_all("tr"):
        cells = []

        for cell in tr.find_all(["th", "td"]):
            text = cell.get_text("\n", strip=True)
            cells.append(text)

        if cells:
            rows.append(cells)

    return rows


def unique_keep_order(items: List[str]) -> List[str]:
    seen = set()
    result = []

    for item in items:
        item = clean_text(item)

        if not item:
            continue

        if item in seen:
            continue

        seen.add(item)
        result.append(item)

    return result


def extract_static_menu(rows: List[List[str]]) -> List[str]:
    """
    오렌지식당/학생회관식당용.
    일주일 표 전체에서 메뉴명을 뽑고 중복 제거한다.
    """

    items = []

    for row in rows[1:]:
        for cell in row[1:]:
            items.extend(split_cell_text(cell))

    return unique_keep_order(items)


def parse_date_label(date_text: str) -> Optional[str]:
    match = re.search(r"(\d{2})월\s*(\d{1,2})일", date_text)

    if not match:
        return None

    month = int(match.group(1))
    day = int(match.group(2))

    return f"{month:02d}-{day:02d}"


def extract_main_today_menu(rows: List[List[str]], target_date: datetime) -> List[str]:
    """
    본관/교직원식당용.
    오늘 날짜 행의 점심 메뉴를 우선 가져온다.
    점심이 없으면 저녁 메뉴를 사용한다.
    """

    target_md = target_date.strftime("%m-%d")

    for row in rows[1:]:
        if not row:
            continue

        row_md = parse_date_label(row[0])

        if row_md != target_md:
            continue

        lunch_items = split_cell_text(row[1]) if len(row) > 1 else []
        dinner_items = split_cell_text(row[2]) if len(row) > 2 else []

        if lunch_items:
            return lunch_items

        if dinner_items:
            return dinner_items

        return []

    return []


def build_menu_text(items: List[str]) -> str:
    items = unique_keep_order(items)

    if not items:
        return "오늘 등록된 식단이 없습니다."

    return "\n".join(items)


def build_payload() -> Dict:
    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")

    crawl_date_raw = os.getenv("CRAWL_DATE", "").strip()

    if crawl_date_raw:
        target_date = datetime.strptime(crawl_date_raw, "%Y-%m-%d").replace(tzinfo=KST)
    else:
        target_date = now

    restaurants: Dict[str, Dict] = {}
    random_items: List[str] = []

    for key in ["student", "orange", "main"]:
        meta = RESTAURANTS[key]
        url = RESTAURANT_URLS[key]

        html = fetch_html(url)
        rows = get_table_rows(html)

        if key == "main":
            items = extract_main_today_menu(rows, target_date)
        else:
            items = extract_static_menu(rows)

        menu_text = build_menu_text(items)

        restaurants[key] = {
            "name": meta["name"],
            "sourceName": meta["sourceName"],
            "location": meta["location"],
            "openTime": meta["openTime"],
            "menuText": menu_text,
            "lastUpdated": today,
            "sourceUrl": url,
        }

        for item in items:
            random_items.append(f'{meta["name"]} - {item}')

    random_items = unique_keep_order(random_items)
    random_menus = {}

    for i, item in enumerate(random_items[:40], start=1):
        random_menus[str(i)] = item

    if not random_menus:
        random_menus = {
            "1": "학생회관식당 - 메뉴 확인 필요",
            "2": "오렌지식당 - 메뉴 확인 필요",
            "3": "본관식당 - 메뉴 확인 필요",
        }

    return {
        "restaurants": restaurants,
        "randomMenus": random_menus,
        "ingredients": STATIC_INGREDIENTS,
        "meta": {
            "source": "선문대학교 금주의식단 페이지",
            "sourceUrls": RESTAURANT_URLS,
            "lastUpdated": today,
            "updatedAtKST": now.isoformat(timespec="seconds"),
            "targetDate": target_date.strftime("%Y-%m-%d"),
            "randomMenuCount": len(random_menus),
            "notice": "식단과 운영시간은 학교 사정에 따라 변경될 수 있습니다.",
        },
    }


def upload_to_firebase(
    payload: Dict,
    database_url: str,
    auth_token: Optional[str] = None,
) -> None:
    if not database_url:
        raise ValueError("FIREBASE_DATABASE_URL 환경변수가 비어 있습니다.")

    database_url = database_url.rstrip("/")
    endpoint = f"{database_url}/sunmoon.json"

    params = {}

    if auth_token:
        params["auth"] = auth_token

    response = requests.put(
        endpoint,
        params=params,
        json=payload,
        timeout=20,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Firebase 업로드 실패: HTTP {response.status_code}\n{response.text[:500]}"
        )


def main() -> None:
    output_json = Path(os.getenv("OUTPUT_JSON", "outputs/sunmoon_food_latest.json"))
    dry_run = os.getenv("DRY_RUN", "").strip() == "1"

    payload = build_payload()

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] JSON 생성: {output_json}")

    if dry_run:
        print("[DRY_RUN] Firebase 업로드는 건너뜁니다.")
        return

    database_url = os.getenv("FIREBASE_DATABASE_URL", "").strip()
    auth_token = os.getenv("FIREBASE_AUTH_TOKEN", "").strip() or None

    upload_to_firebase(payload, database_url, auth_token)
    print("[OK] Firebase Realtime Database 업데이트 완료")


if __name__ == "__main__":
    main()
