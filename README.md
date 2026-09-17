# 선문대학교 식단 수집·Firebase 연동

학교 식당별 웹페이지에서 식단을 읽고 정리한 뒤, JSON 파일과 Firebase Realtime Database로 제공하는 자동화 프로젝트입니다.

**Python · Requests · BeautifulSoup · Firebase REST API · GitHub Actions**

## 주요 기능

- 학생회관식당·오렌지식당·본관식당 페이지의 식단 수집
- 날짜·식당 구분, 메뉴 문자열 정리와 일부 오탈자 보정
- 식단이 없는 경우의 안내 문구 처리
- 메뉴 설명과 참고 재료 정보를 포함한 JSON 생성
- Firebase 업로드 없이 확인하는 `DRY_RUN` 모드
- GitHub Actions 정기 실행과 결과 JSON 아티팩트 보관

재료·식이 관련 보조 정보에는 코드에 정의된 규칙과 정적 매핑이 포함됩니다. 식당이 확인한 원재료·알레르기 정보와 동일한 자료로 해석하지 않습니다.

## 처리 흐름

```text
식당별 웹페이지 → HTML 해석·날짜/메뉴 정리 → JSON 저장 → Firebase 업데이트
                                             └→ DRY_RUN에서는 업로드 생략
```

현재 실행 파일은 [`scripts/sunmoon_food_to_firebase.py`](scripts/sunmoon_food_to_firebase.py)입니다. 식당별 원본 URL은 코드의 `RESTAURANT_URLS`에서 관리합니다.

## 로컬에서 결과 확인

Python 3.11 환경, 저장소 루트 기준입니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:DRY_RUN="1"
python scripts/sunmoon_food_to_firebase.py
```

기본 출력은 `outputs/sunmoon_food_latest.json`입니다. 이 모드는 Firebase 내용을 변경하지 않습니다.

### Firebase에 반영

```powershell
$env:FIREBASE_DATABASE_URL="https://YOUR_PROJECT-default-rtdb.firebaseio.com"
$env:FIREBASE_AUTH_TOKEN="YOUR_AUTH_TOKEN"
Remove-Item Env:DRY_RUN -ErrorAction SilentlyContinue
python scripts/sunmoon_food_to_firebase.py
```

업로드는 실제 데이터베이스에 반영됩니다. 토큰 필요 여부는 해당 Firebase 프로젝트의 인증·규칙 설정을 따릅니다.

## 현재 사용하는 환경변수

| 이름 | 용도 |
|---|---|
| `DRY_RUN` | `1`이면 JSON만 생성 |
| `OUTPUT_JSON` | 결과 파일 경로 |
| `CRAWL_DATE` | 수집 기준 날짜 지정 |
| `FIREBASE_DATABASE_URL` | 업로드할 Realtime Database |
| `FIREBASE_AUTH_TOKEN` | Firebase 인증 토큰 |

예전 안내의 `SUNMOON_FOOD_URL`, `SUNMOON_FOOD_HTML_FILE`은 현재 실행 파일이 읽는 설정이 아닙니다. 웹페이지 주소를 바꾸려면 `RESTAURANT_URLS`를 확인합니다. `.env` 파일은 스크립트에서 자동으로 로드하지 않으므로 위처럼 실행 환경에 설정합니다.

## 자동 갱신

[update_sunmoon_food.yml](.github/workflows/update_sunmoon_food.yml)은 매일 08:30 KST 실행과 수동 실행을 지원합니다. Repository Secrets에 `FIREBASE_DATABASE_URL`, `FIREBASE_AUTH_TOKEN`을 등록해 사용합니다.

## 파일 구성

- `scripts/sunmoon_food_to_firebase.py`: 현재 수집·출력·업로드 흐름
- `scripts/sunmoon_food_to_firebase_backup.py`: 이전 코드 참고본
- `outputs/`: 저장된 JSON 결과
- `patch_ingredients.py`, `patch_main_fallback.py`: 개발 과정의 수정 도구
- [기존 수정 이력](V4_수정내역.txt): 식당 섹션 매핑·빈 메뉴 처리 개선 기록

원본 학교 페이지의 구조가 변경되면 파싱 규칙을 점검해야 합니다. 기본 실행에는 패치 스크립트 실행이 필요하지 않습니다.
