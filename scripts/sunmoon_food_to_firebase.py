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
DEFAULT_URL = "https://smi.sunmoon.ac.kr/PageN/ContentN/Food.aspx"

RESTAURANTS = [
    {
        "key": "student",
        "app_name": "학생회관식당",
        "source_name": "학생회관식당",
        "location": "학생회관 식당",
        "default_open_time": "운영시간은 학교 식단 페이지 기준으로 확인",
    },
    {
        "key": "orange",
        "app_name": "오렌지식당",
        "source_name": "오렌지식당",
        "location": "오렌지식당",
        "default_open_time": "운영시간은 학교 식단 페이지 기준으로 확인",
    },
    {
        "key": "main",
        "app_name": "본관식당",
        "source_name": "교직원식당",
        "location": "본관 또는 교직원식당",
        "default_open_time": "운영시간은 학교 식단 페이지 기준으로 확인",
    },
]

CATEGORY_WORDS = {
    "한식", "양식", "분식", "일식", "점심", "저녁",
    "조식", "중식", "석식", "메뉴", "오늘의 식단"
}

JUNK_PATTERNS = [
    r"^open_in_new$",
    r"^##$",
    r"^\*$",
    r"^-$",
    r"^arrow_upward$",
]

TEXT_FIXES = {
    "순두부지깨": "순두부찌개",
    "함밤카레": "함박카레",
    "떢볶이": "떡볶이",
}


class LegacyTLSAdapter(HTTPAdapter):
    """선문대 서버 SSL handshake 실패 대응용 adapter."""

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

        pool_kwargs["ssl_context"] = ctx
        return super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)


def clean_line(line: str) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    for wrong, right in TEXT_FIXES.items():
        line = line.replace(wrong, right)
    return line


def is_junk(line: str) -> bool:
    if not line:
        return True

    for pattern in JUNK_PATTERNS:
        if re.match(pattern, line, flags=re.IGNORECASE):
            return True

    lower = line.lower()

    if lower.startswith("today"):
        return True

    if line.startswith("- today"):
        return True

    if "방학기간중에는 운영을 하지 않습니다" in line:
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
        headers={
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        },
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
        error_text = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(error_text[:1000])

    return decode_bytes(result.stdout)


def read_local_html_if_set() -> Optional[str]:
    html_file = os.getenv("SUNMOON_FOOD_HTML_FILE", "").strip()

    if not html_file:
        return None

    path = Path(html_file)

    if not path.exists():
        raise FileNotFoundError(f"SUNMOON_FOOD_HTML_FILE 경로가 없습니다: {path}")

    print(f"[INFO] 로컬 HTML 파일 사용: {path}")
    return decode_bytes(path.read_bytes())


def fetch_html(url: str) -> str:
    local_html = read_local_html_if_set()

    if local_html:
        return local_html

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
                print(f"[INFO] 식단 페이지 요청 시도: {method_name} / {target_url}")
                html = request_func()

                has_food_keyword = (
                    "학생회관식당" in html
                    or "오렌지식당" in html
                    or "오늘의 식단" in html
                )

                if has_food_keyword:
                    print(f"[OK] 식단 페이지 요청 성공: {method_name}")
                    return html

                if len(html) > 500:
                    print(f"[WARN] 식당 키워드는 없지만 HTML을 받았습니다: {method_name}")
                    return html

                raise RuntimeError("응답 HTML이 너무 짧습니다.")

            except Exception as exc:
                message = f"{method_name} / {target_url} -> {type(exc).__name__}: {exc}"
                errors.append(message)
                print(f"[WARN] 실패: {message}")

    error_message = (
        "선문대 식단 페이지를 가져오지 못했습니다.\n"
        "원인 후보: 학교 서버 SSL/TLS 호환 문제, 네트워크 차단, 페이지 구조 변경.\n\n"
        "시도한 오류 목록:\n- "
        + "\n- ".join(errors)
        + "\n\n긴급 우회 방법:\n"
        "1) 브라우저에서 https://smi.sunmoon.ac.kr/PageN/ContentN/Food.aspx 열기\n"
        "2) Ctrl+S로 food.html 저장\n"
        "3) PowerShell에서 $env:SUNMOON_FOOD_HTML_FILE='C:\\Users\\soma\\Desktop\\food.html'\n"
        "4) 다시 실행"
    )
    raise RuntimeError(error_message)


def html_to_lines(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text("\n")
    lines = [clean_line(line) for line in text.splitlines()]
    return [line for line in lines if line]


def find_restaurant_tab_end(lines: List[str]) -> int:
    indices = []

    for restaurant in RESTAURANTS:
        try:
            indices.append(lines.index(restaurant["source_name"]))
        except ValueError:
            pass

    if indices:
        return max(indices) + 1

    for i, line in enumerate(lines):
        if "오늘의 식단" in line:
            return i + 1

    return 0


def count_real_menu_items(section: List[str]) -> int:
    """섹션 안에 실제 메뉴로 볼 수 있는 줄이 몇 개인지 센다."""
    count = 0
    for line in normalize_section(section):
        if not line:
            continue
        if line in CATEGORY_WORDS:
            continue
        if len(line) > 35:
            continue
        if any(word in line for word in ["운영", "공지", "식단 페이지", "확인", "Today"]):
            continue
        count += 1
    return count


def split_food_sections(lines: List[str]) -> List[List[str]]:
    """
    today 기준 후보 섹션을 모두 만든 뒤 실제 메뉴가 거의 없는 빈 섹션을 제외한다.
    빈 today 블록 때문에 student/orange/main 데이터가 한 칸씩 밀리는 문제를 방지한다.
    """
    start_after_tabs = find_restaurant_tab_end(lines)

    starts = []
    for i in range(start_after_tabs, len(lines)):
        if "today" in lines[i].lower():
            starts.append(i)

    if starts:
        candidates = []

        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else len(lines)

            for j in range(start + 1, end):
                if "맛집 정보" in lines[j]:
                    end = j
                    break

            candidates.append(lines[start:end])

        non_empty = [
            section for section in candidates
            if count_real_menu_items(section) >= 2
        ]

        if non_empty:
            while len(non_empty) < len(RESTAURANTS):
                non_empty.append([])
            return non_empty[:len(RESTAURANTS)]

    sections = []
    for restaurant in RESTAURANTS:
        try:
            index = lines.index(restaurant["source_name"], start_after_tabs)
            sections.append(lines[index:index + 80])
        except ValueError:
            sections.append([])

    return sections


def normalize_section(section: List[str]) -> List[str]:
    cleaned = []

    for line in section:
        line = clean_line(line)

        if is_junk(line):
            continue

        if "맛집 정보" in line:
            break

        if "SUN MOON University" in line:
            break

        cleaned.append(line)

    return cleaned


def build_menu_text(lines: List[str]) -> str:
    if not lines:
        return "오늘 등록된 식단이 없습니다."

    result = []

    for line in lines:
        if line in CATEGORY_WORDS and result:
            result.append("")

        result.append(line)

    return "\n".join(result).strip()


def extract_menu_items(lines: List[str]) -> List[str]:
    items = []

    for line in lines:
        if not line:
            continue

        if line in CATEGORY_WORDS:
            continue

        if len(line) > 35:
            continue

        if any(word in line for word in ["운영", "공지", "식단 페이지", "확인"]):
            continue

        items.append(line)

    return items


def build_payload(url: str) -> Dict:
    html = fetch_html(url)
    lines = html_to_lines(html)
    sections = split_food_sections(lines)

    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")

    restaurants: Dict[str, Dict] = {}
    random_items: List[str] = []

    for meta, section in zip(RESTAURANTS, sections):
        cleaned = normalize_section(section)
        menu_text = build_menu_text(cleaned)

        restaurants[meta["key"]] = {
            "name": meta["app_name"],
            "sourceName": meta["source_name"],
            "location": meta["location"],
            "openTime": meta["default_open_time"],
            "menuText": menu_text,
            "lastUpdated": today,
            "sourceUrl": url,
        }

        for item in extract_menu_items(cleaned):
            random_items.append(f'{meta["app_name"]} - {item}')

    random_menus = {}

    for i, item in enumerate(random_items[:30], start=1):
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
        "meta": {
            "source": "선문대학교 식단 페이지",
            "sourceUrl": url,
            "lastUpdated": today,
            "updatedAtKST": now.isoformat(timespec="seconds"),
            "randomMenuCount": len(random_menus),
            "notice": "식단과 운영시간은 학교 사정에 따라 변경될 수 있습니다.",
        },
    }


def upload_to_firebase(payload: Dict, database_url: str, auth_token: Optional[str] = None) -> None:
    if not database_url:
        raise ValueError("FIREBASE_DATABASE_URL 환경변수가 비어 있습니다.")

    database_url = database_url.rstrip("/")
    endpoint = f"{database_url}/.json"
    params = {}

    if auth_token:
        params["auth"] = auth_token

    response = requests.patch(endpoint, params=params, json=payload, timeout=20)

    if response.status_code >= 400:
        raise RuntimeError(
            f"Firebase 업로드 실패: HTTP {response.status_code}\n{response.text[:500]}"
        )


def main() -> None:
    url = os.getenv("SUNMOON_FOOD_URL", DEFAULT_URL)
    output_json = Path(os.getenv("OUTPUT_JSON", "outputs/sunmoon_food_latest.json"))
    dry_run = os.getenv("DRY_RUN", "").strip() == "1"

    payload = build_payload(url)

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
