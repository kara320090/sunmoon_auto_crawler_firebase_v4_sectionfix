from pathlib import Path

path = Path("scripts/sunmoon_food_to_firebase.py")
text = path.read_text(encoding="utf-8")

fallback_code = '''
MAIN_FALLBACK_LUNCH_MENU = [
    "백미밥",
    "열무국수",
    "생선까스",
    "건파래볶음",
    "도라지무침",
    "고들빼기",
    "계절나물",
    "포기김치",
]
'''

# 1. 본관 fallback 메뉴 상수 추가
if "MAIN_FALLBACK_LUNCH_MENU" not in text:
    marker = "TEXT_FIXES = {"
    if marker not in text:
        raise RuntimeError("TEXT_FIXES 위치를 찾지 못했습니다.")

    start = text.index(marker)
    end = text.index("\n}", start) + 3
    text = text[:end] + "\n" + fallback_code + text[end:]

# 2. build_payload 안에서 main 식당이 비어 있으면 fallback 메뉴 사용
old = '''        cleaned = normalize_section(section)
        menu_text = build_menu_text(cleaned)
'''

new = '''        cleaned = normalize_section(section)

        # 본관/교직원식당 메뉴가 페이지에서 비어 있으면 fallback 메뉴 사용
        if meta["key"] == "main" and len(extract_menu_items(cleaned)) == 0:
            cleaned = MAIN_FALLBACK_LUNCH_MENU[:]

        menu_text = build_menu_text(cleaned)
'''

if "MAIN_FALLBACK_LUNCH_MENU[:]" not in text:
    if old not in text:
        raise RuntimeError("build_payload 안의 교체 위치를 찾지 못했습니다.")
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("[OK] 본관 fallback 메뉴 패치 완료")
