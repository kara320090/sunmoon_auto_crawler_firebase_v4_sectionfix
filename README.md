# 선문대 식단 자동 크롤링 → Firebase 업데이트 v4

## v4 수정 사항

- 학생회관 메뉴가 오렌지식당으로 밀리고, 오렌지 메뉴가 본관식당으로 밀리는 문제를 수정했습니다.
- 페이지에 빈 `today` 블록이 먼저 잡히는 경우를 제외하고 실제 메뉴가 있는 섹션만 식당 순서대로 매핑합니다.
- 교직원식당 식단이 없는 날에는 `본관식당`에 `오늘 등록된 식단이 없습니다.`가 들어갑니다.
- 일부 오탈자 보정: `순두부지깨 → 순두부찌개`, `함밤카레 → 함박카레`, `떢볶이 → 떡볶이`.

# 선문대 식단 자동 크롤링 → Firebase 업데이트 v3

## v3 수정 사항

v2에서 발생한 `SyntaxError: unterminated string literal` 문제를 수정한 버전입니다.

## 설치

```powershell
pip install -r requirements.txt
```

## 실행

```powershell
$env:FIREBASE_DATABASE_URL="https://sunmoonmealapp-default-rtdb.firebaseio.com"
python scripts/sunmoon_food_to_firebase.py
```

## 업로드 없이 크롤링 결과만 확인

```powershell
$env:DRY_RUN="1"
python scripts/sunmoon_food_to_firebase.py
```

확인 후 다시 실제 업로드하려면:

```powershell
Remove-Item Env:DRY_RUN
python scripts/sunmoon_food_to_firebase.py
```

## SSL 문제가 계속 날 때

### 1차 우회: HTTP 주소로 시도

```powershell
$env:SUNMOON_FOOD_URL="http://smi.sunmoon.ac.kr/PageN/ContentN/Food.aspx"
python scripts/sunmoon_food_to_firebase.py
```

### 2차 우회: 브라우저 HTML 저장

1. 브라우저에서 아래 페이지 열기

```text
https://smi.sunmoon.ac.kr/PageN/ContentN/Food.aspx
```

2. `Ctrl + S`로 `food.html` 저장

3. 실행

```powershell
$env:SUNMOON_FOOD_HTML_FILE="C:\Users\soma\Desktop\food.html"
$env:FIREBASE_DATABASE_URL="https://sunmoonmealapp-default-rtdb.firebaseio.com"
python scripts/sunmoon_food_to_firebase.py
```

## Firebase에 올라가는 경로

```text
restaurants/student/menuText
restaurants/orange/menuText
restaurants/main/menuText
randomMenus/1
randomMenus/2
meta/lastUpdated
```

MIT App Inventor에서는 FirebaseDB의 `GetValue`로 위 태그를 읽으면 됩니다.
