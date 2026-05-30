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
        "text": """[학생회관식당 메뉴별 원재료/주의 성분 안내]

※ 본 정보는 선문대학교 학생의 메뉴 선택을 돕기 위한 참고용 정보입니다.
※ 실제 원재료, 육수, 소스, 조리도구 교차오염 여부는 식당에 직접 확인해야 합니다.
※ 이슬람 식단 이용자는 돼지고기, 비할랄 육류, 육류 육수, 젤라틴, 알코올성 소스 여부를 주의해야 합니다.

소불고기덮밥
- 주요 가능 성분: 소고기, 쌀, 양파, 간장, 대두, 밀
- 주의: 소고기 도축 방식 확인 필요
- 이슬람 식단: 확인 필요

부대찌개
- 주요 가능 성분: 햄, 소시지, 김치, 라면사리, 육수, 대두, 밀
- 주의: 돼지고기 가공육 포함 가능성 높음
- 이슬람 식단: 피함 권장

알밥
- 주요 가능 성분: 쌀, 생선알, 김, 단무지, 참기름, 간장, 대두
- 주의: 생선알, 소스 성분 확인 필요
- 이슬람 식단: 소스 확인 필요

명란알밥
- 주요 가능 성분: 쌀, 명란, 김, 단무지, 참기름, 간장, 대두
- 주의: 생선, 대두
- 이슬람 식단: 소스 확인 필요

닭고기덮밥
- 주요 가능 성분: 닭고기, 쌀, 양파, 간장, 대두, 밀
- 주의: 닭고기 도축 방식 확인 필요
- 이슬람 식단: 확인 필요

꼬막비빔밥
- 주요 가능 성분: 쌀, 꼬막, 고추장, 참기름, 채소, 대두, 밀
- 주의: 조개류, 고추장 소스
- 이슬람 식단: 해산물 섭취 기준 및 소스 확인 필요

고기국밥
- 주요 가능 성분: 쌀, 돼지고기 또는 소고기, 육수, 파, 마늘
- 주의: 고기 종류와 육수 성분 확인 필요
- 이슬람 식단: 피함 권장

제육덮밥
- 주요 가능 성분: 돼지고기, 쌀, 고추장, 간장, 대두, 밀
- 주의: 돼지고기
- 이슬람 식단: 피함 권장

등심돈가스
- 주요 가능 성분: 돼지고기, 빵가루, 밀, 계란, 대두, 튀김유
- 주의: 돼지고기, 밀, 계란
- 이슬람 식단: 피함 권장

고구마돈가스
- 주요 가능 성분: 돼지고기, 고구마, 빵가루, 밀, 계란, 우유 가능성
- 주의: 돼지고기, 우유, 밀, 계란
- 이슬람 식단: 피함 권장

치즈돈가스
- 주요 가능 성분: 돼지고기, 치즈, 빵가루, 밀, 계란, 우유
- 주의: 돼지고기, 우유, 밀, 계란
- 이슬람 식단: 피함 권장

빠네크림스파게티
- 주요 가능 성분: 밀, 우유, 생크림, 치즈, 빵, 양파, 베이컨 가능성
- 주의: 우유, 밀, 육류 토핑 여부
- 이슬람 식단: 육류 성분 확인 필요

로제파스타
- 주요 가능 성분: 밀, 우유, 토마토소스, 생크림, 치즈, 육류 토핑 가능성
- 주의: 우유, 밀, 소스 성분
- 이슬람 식단: 소스 및 육류 성분 확인 필요

크림스파게티
- 주요 가능 성분: 밀, 우유, 생크림, 치즈, 양파, 베이컨 가능성
- 주의: 우유, 밀, 육류 토핑 여부
- 이슬람 식단: 육류 성분 확인 필요

토마토스파게티
- 주요 가능 성분: 밀, 토마토소스, 양파, 마늘, 대두 가능성
- 주의: 밀, 소스 성분
- 이슬람 식단: 소스 확인 필요

명란로제파스타
- 주요 가능 성분: 명란, 밀, 우유, 토마토소스, 생크림
- 주의: 생선, 우유, 밀
- 이슬람 식단: 소스 확인 필요

명란크림파스타
- 주요 가능 성분: 명란, 밀, 우유, 생크림, 치즈
- 주의: 생선, 우유, 밀
- 이슬람 식단: 소스 확인 필요

돈가스김밥
- 주요 가능 성분: 쌀, 김, 돼지고기 돈가스, 계란, 단무지, 밀, 대두
- 주의: 돼지고기, 계란, 밀
- 이슬람 식단: 피함 권장

참치김밥
- 주요 가능 성분: 쌀, 김, 참치, 마요네즈, 계란, 단무지, 대두
- 주의: 생선, 계란, 마요네즈
- 이슬람 식단: 소스 확인 필요

치즈김밥
- 주요 가능 성분: 쌀, 김, 치즈, 계란, 단무지, 대두
- 주의: 우유, 계란
- 이슬람 식단: 소스 확인 필요

치즈라면
- 주요 가능 성분: 라면면, 밀, 대두, 치즈, 라면스프
- 주의: 우유, 밀, 스프 내 육류 성분 가능성
- 이슬람 식단: 스프 성분 확인 필요

떡라면
- 주요 가능 성분: 라면면, 밀, 대두, 떡, 라면스프
- 주의: 밀, 스프 내 육류 성분 가능성
- 이슬람 식단: 스프 성분 확인 필요

만두라면
- 주요 가능 성분: 라면면, 밀, 대두, 만두, 돼지고기 만두 가능성
- 주의: 만두 속 돼지고기 가능성
- 이슬람 식단: 피함 권장

야채김밥
- 주요 가능 성분: 쌀, 김, 채소, 단무지, 계란 가능성, 참기름
- 주의: 계란, 대두
- 이슬람 식단: 소스 및 계란 확인 필요

계란라면
- 주요 가능 성분: 라면면, 밀, 대두, 계란, 라면스프
- 주의: 계란, 스프 내 육류 성분 가능성
- 이슬람 식단: 스프 성분 확인 필요

베이컨라면
- 주요 가능 성분: 라면면, 밀, 대두, 베이컨, 라면스프
- 주의: 돼지고기
- 이슬람 식단: 피함 권장

떡볶이&오뎅 SET
- 주요 가능 성분: 떡, 고추장, 어묵, 밀, 대두, 생선
- 주의: 어묵, 고추장, 소스 성분
- 이슬람 식단: 소스 및 어묵 성분 확인 필요

김밥&오뎅 SET
- 주요 가능 성분: 김밥, 어묵, 쌀, 김, 단무지, 계란 가능성, 대두, 생선
- 주의: 어묵, 계란, 소스 성분
- 이슬람 식단: 소스 및 어묵 성분 확인 필요
"""
    },
    "orange": {
        "text": """[오렌지식당 메뉴별 원재료/주의 성분 안내]

※ 본 정보는 선문대학교 학생의 메뉴 선택을 돕기 위한 참고용 정보입니다.
※ 실제 원재료, 육수, 소스, 조리도구 교차오염 여부는 식당에 직접 확인해야 합니다.
※ 이슬람 식단 이용자는 돼지고기, 비할랄 육류, 육류 육수, 젤라틴, 알코올성 소스 여부를 주의해야 합니다.

제육덮밥
- 주요 가능 성분: 돼지고기, 쌀, 고추장, 간장, 대두, 밀
- 주의: 돼지고기
- 이슬람 식단: 피함 권장

김치제육덮밥
- 주요 가능 성분: 돼지고기, 김치, 쌀, 고추장, 간장, 대두, 밀
- 주의: 돼지고기, 김치 양념
- 이슬람 식단: 피함 권장

순두부찌개
- 주요 가능 성분: 순두부, 대두, 계란 가능성, 해산물 또는 고기 육수 가능성
- 주의: 대두, 계란, 육수 성분
- 이슬람 식단: 육수 성분 확인 필요

김치찌개
- 주요 가능 성분: 김치, 돼지고기 가능성, 두부, 대두, 육수
- 주의: 돼지고기 및 육수 성분
- 이슬람 식단: 피함 권장

순대국밥
- 주요 가능 성분: 순대, 돼지고기, 내장, 선지, 육수, 쌀
- 주의: 돼지고기, 내장, 선지
- 이슬람 식단: 피함 권장

불고기덮밥
- 주요 가능 성분: 소고기, 쌀, 간장, 양파, 대두, 밀
- 주의: 소고기 도축 방식 확인 필요
- 이슬람 식단: 확인 필요

부대찌개
- 주요 가능 성분: 햄, 소시지, 라면사리, 김치, 육수, 밀, 대두
- 주의: 돼지고기 가공육 포함 가능성 높음
- 이슬람 식단: 피함 권장

한우설렁탕
- 주요 가능 성분: 소고기, 사골 육수, 쌀, 파
- 주의: 소고기 도축 방식 및 육수 확인 필요
- 이슬람 식단: 확인 필요

카레덮밥
- 주요 가능 성분: 쌀, 카레소스, 밀, 우유 가능성, 대두, 육류 성분 가능성
- 주의: 카레 소스 성분
- 이슬람 식단: 소스 확인 필요

치즈카레
- 주요 가능 성분: 쌀, 카레소스, 치즈, 우유, 밀, 대두
- 주의: 우유, 소스 성분
- 이슬람 식단: 소스 확인 필요

치킨카츠카레
- 주요 가능 성분: 닭고기, 카레소스, 밀, 계란, 우유 가능성, 대두
- 주의: 닭고기 도축 방식, 밀, 계란
- 이슬람 식단: 확인 필요

돈가스덮밥
- 주요 가능 성분: 돼지고기, 쌀, 계란, 밀, 대두, 소스
- 주의: 돼지고기
- 이슬람 식단: 피함 권장

돈가스카레
- 주요 가능 성분: 돼지고기, 카레소스, 밀, 계란, 대두, 우유 가능성
- 주의: 돼지고기, 카레 소스
- 이슬람 식단: 피함 권장

치즈돈가스덮밥
- 주요 가능 성분: 돼지고기, 치즈, 쌀, 밀, 계란, 우유
- 주의: 돼지고기, 우유
- 이슬람 식단: 피함 권장

치즈돈가스카레
- 주요 가능 성분: 돼지고기, 치즈, 카레소스, 밀, 계란, 우유
- 주의: 돼지고기, 우유, 카레 소스
- 이슬람 식단: 피함 권장

가츠돈
- 주요 가능 성분: 돼지고기, 계란, 쌀, 간장, 밀, 대두
- 주의: 돼지고기, 계란
- 이슬람 식단: 피함 권장

치즈가츠돈
- 주요 가능 성분: 돼지고기, 치즈, 계란, 쌀, 밀, 대두
- 주의: 돼지고기, 우유, 계란
- 이슬람 식단: 피함 권장

함박카레
- 주요 가능 성분: 소고기/돼지고기 혼합육 가능성, 카레소스, 밀, 계란, 대두
- 주의: 돼지고기 혼합 가능성
- 이슬람 식단: 피함 권장

치즈함박카레
- 주요 가능 성분: 소고기/돼지고기 혼합육 가능성, 치즈, 카레소스, 밀, 계란, 우유
- 주의: 돼지고기 혼합 가능성, 우유
- 이슬람 식단: 피함 권장

라면
- 주요 가능 성분: 밀, 대두, 라면스프
- 주의: 스프 내 육류 성분 가능성
- 이슬람 식단: 스프 성분 확인 필요

떡라면
- 주요 가능 성분: 밀, 대두, 떡, 라면스프
- 주의: 스프 내 육류 성분 가능성
- 이슬람 식단: 스프 성분 확인 필요

치즈라면
- 주요 가능 성분: 밀, 대두, 치즈, 우유, 라면스프
- 주의: 우유, 스프 내 육류 성분 가능성
- 이슬람 식단: 스프 성분 확인 필요

얼큰콩나물라면
- 주요 가능 성분: 밀, 대두, 콩나물, 라면스프
- 주의: 스프 내 육류 성분 가능성
- 이슬람 식단: 스프 성분 확인 필요

물냉면(계절메뉴)
- 주요 가능 성분: 면, 밀, 메밀 가능성, 계란 가능성, 육수
- 주의: 육수 성분, 계란
- 이슬람 식단: 육수 성분 확인 필요

비빔냉면(계절메뉴)
- 주요 가능 성분: 면, 밀, 메밀 가능성, 고추장, 계란 가능성, 육수
- 주의: 소스와 육수 성분
- 이슬람 식단: 소스 및 육수 확인 필요
"""
    },
    "main": {
        "text": """[본관/교직원식당 성분/주의 정보]

본관/교직원식당은 식단이 매일 변경되므로 고정 원재료/성분표를 제공하지 않습니다.

알레르기, 이슬람 식단, 채식 등 식이 제한이 있는 경우
실제 배식 전 식당에 직접 확인해 주세요.
"""
    },
}


def ingredient_text(menu: str, possible: str, caution: str, islam: str) -> dict:
    return {
        "text": (
            f"{menu}\n"
            f"- 주요 가능 성분: {possible}\n"
            f"- 주의: {caution}\n"
            f"- 이슬람 식단: {islam}\n\n"
            "※ 본 정보는 참고용입니다.\n"
            "※ 실제 원재료, 육수, 소스, 조리도구 교차오염 여부는 식당에 직접 확인해야 합니다."
        )
    }


INGREDIENTS_BY_MENU = {
    "student": {
        "소불고기덮밥": ingredient_text("소불고기덮밥", "소고기, 쌀, 양파, 간장, 대두, 밀", "소고기 도축 방식 확인 필요", "확인 필요"),
        "부대찌개": ingredient_text("부대찌개", "햄, 소시지, 김치, 라면사리, 육수, 대두, 밀", "돼지고기 가공육 포함 가능성 높음", "피함 권장"),
        "알밥": ingredient_text("알밥", "쌀, 생선알, 김, 단무지, 참기름, 간장, 대두", "생선알 및 소스 성분 확인 필요", "소스 확인 필요"),
        "명란알밥": ingredient_text("명란알밥", "쌀, 명란, 김, 단무지, 참기름, 대두", "명란, 생선, 소스 성분 확인 필요", "소스 확인 필요"),
        "닭고기덮밥": ingredient_text("닭고기덮밥", "닭고기, 쌀, 양파, 간장, 대두, 밀", "닭고기 도축 방식 확인 필요", "확인 필요"),
        "꼬막비빔밥": ingredient_text("꼬막비빔밥", "쌀, 꼬막, 고추장, 참기름, 채소, 대두, 밀", "조개류 및 고추장 소스 확인 필요", "해산물 섭취 기준 및 소스 확인 필요"),
        "고기국밥": ingredient_text("고기국밥", "쌀, 돼지고기 또는 소고기, 육수, 파, 마늘", "고기 종류와 육수 성분 확인 필요", "피함 권장"),
        "제육덮밥": ingredient_text("제육덮밥", "돼지고기, 쌀, 고추장, 간장, 대두, 밀", "돼지고기 포함", "피함 권장"),
        "등심돈가스": ingredient_text("등심돈가스", "돼지고기, 빵가루, 밀, 계란, 대두, 튀김유", "돼지고기, 밀, 계란 포함 가능성", "피함 권장"),
        "고구마돈가스": ingredient_text("고구마돈가스", "돼지고기, 고구마, 빵가루, 밀, 계란, 우유 가능성", "돼지고기, 우유, 밀, 계란 주의", "피함 권장"),
        "치즈돈가스": ingredient_text("치즈돈가스", "돼지고기, 치즈, 빵가루, 밀, 계란, 우유", "돼지고기, 우유, 밀, 계란 주의", "피함 권장"),
        "빠네크림스파게티": ingredient_text("빠네크림스파게티", "밀, 우유, 생크림, 치즈, 빵, 베이컨 가능성", "우유, 밀, 육류 토핑 여부 확인 필요", "육류 성분 확인 필요"),
        "로제파스타": ingredient_text("로제파스타", "밀, 우유, 토마토소스, 생크림, 치즈, 육류 토핑 가능성", "우유, 밀, 소스 성분 확인 필요", "소스 및 육류 성분 확인 필요"),
        "크림스파게티": ingredient_text("크림스파게티", "밀, 우유, 생크림, 치즈, 베이컨 가능성", "우유, 밀, 육류 토핑 여부 확인 필요", "육류 성분 확인 필요"),
        "토마토스파게티": ingredient_text("토마토스파게티", "밀, 토마토소스, 양파, 마늘, 대두 가능성", "밀, 소스 성분 확인 필요", "소스 확인 필요"),
        "명란로제파스타": ingredient_text("명란로제파스타", "명란, 밀, 우유, 토마토소스, 생크림", "생선, 우유, 밀 주의", "소스 확인 필요"),
        "명란크림파스타": ingredient_text("명란크림파스타", "명란, 밀, 우유, 생크림, 치즈", "생선, 우유, 밀 주의", "소스 확인 필요"),
        "돈가스김밥": ingredient_text("돈가스김밥", "쌀, 김, 돼지고기 돈가스, 계란, 단무지, 밀, 대두", "돼지고기, 계란, 밀 주의", "피함 권장"),
        "참치김밥": ingredient_text("참치김밥", "쌀, 김, 참치, 마요네즈, 계란, 단무지, 대두", "생선, 계란, 마요네즈 확인 필요", "소스 확인 필요"),
        "치즈김밥": ingredient_text("치즈김밥", "쌀, 김, 치즈, 계란, 단무지, 대두", "우유, 계란 주의", "소스 확인 필요"),
        "치즈라면": ingredient_text("치즈라면", "라면면, 밀, 대두, 치즈, 라면스프", "우유, 밀, 스프 내 육류 성분 가능성", "스프 성분 확인 필요"),
        "떡라면": ingredient_text("떡라면", "라면면, 밀, 대두, 떡, 라면스프", "밀, 스프 내 육류 성분 가능성", "스프 성분 확인 필요"),
        "만두라면": ingredient_text("만두라면", "라면면, 밀, 대두, 만두, 돼지고기 만두 가능성", "만두 속 돼지고기 가능성", "피함 권장"),
        "야채김밥": ingredient_text("야채김밥", "쌀, 김, 채소, 단무지, 계란 가능성, 참기름", "계란, 대두, 소스 확인 필요", "소스 및 계란 확인 필요"),
        "계란라면": ingredient_text("계란라면", "라면면, 밀, 대두, 계란, 라면스프", "계란, 스프 내 육류 성분 가능성", "스프 성분 확인 필요"),
        "베이컨라면": ingredient_text("베이컨라면", "라면면, 밀, 대두, 베이컨, 라면스프", "돼지고기 포함 가능성 높음", "피함 권장"),
        "떡볶이&오뎅 SET": ingredient_text("떡볶이&오뎅 SET", "떡, 고추장, 어묵, 밀, 대두, 생선", "어묵, 고추장, 소스 성분 확인 필요", "소스 및 어묵 성분 확인 필요"),
        "김밥&오뎅 SET": ingredient_text("김밥&오뎅 SET", "김밥, 어묵, 쌀, 김, 단무지, 계란 가능성, 대두, 생선", "어묵, 계란, 소스 성분 확인 필요", "소스 및 어묵 성분 확인 필요"),
    },
    "orange": {
        "제육덮밥": ingredient_text("제육덮밥", "돼지고기, 쌀, 고추장, 간장, 대두, 밀", "돼지고기 포함", "피함 권장"),
        "김치제육덮밥": ingredient_text("김치제육덮밥", "돼지고기, 김치, 쌀, 고추장, 간장, 대두, 밀", "돼지고기, 김치 양념 확인 필요", "피함 권장"),
        "순두부찌개": ingredient_text("순두부찌개", "순두부, 대두, 계란 가능성, 해산물 또는 고기 육수 가능성", "육수 성분 확인 필요", "육수 성분 확인 필요"),
        "김치찌개": ingredient_text("김치찌개", "김치, 돼지고기 가능성, 두부, 대두, 육수", "돼지고기 및 육수 성분 확인 필요", "피함 권장"),
        "순대국밥": ingredient_text("순대국밥", "순대, 돼지고기, 내장, 선지, 육수, 쌀", "돼지고기, 내장, 선지 포함 가능성", "피함 권장"),
        "불고기덮밥": ingredient_text("불고기덮밥", "소고기, 쌀, 간장, 양파, 대두, 밀", "소고기 도축 방식 확인 필요", "확인 필요"),
        "부대찌개": ingredient_text("부대찌개", "햄, 소시지, 라면사리, 김치, 육수, 밀, 대두", "돼지고기 가공육 포함 가능성 높음", "피함 권장"),
        "한우설렁탕": ingredient_text("한우설렁탕", "소고기, 사골 육수, 쌀, 파", "소고기 도축 방식 및 육수 확인 필요", "확인 필요"),
        "카레덮밥": ingredient_text("카레덮밥", "쌀, 카레소스, 밀, 우유 가능성, 대두, 육류 성분 가능성", "카레 소스 성분 확인 필요", "소스 확인 필요"),
        "치즈카레": ingredient_text("치즈카레", "쌀, 카레소스, 치즈, 우유, 밀, 대두", "우유, 소스 성분 확인 필요", "소스 확인 필요"),
        "치킨카츠카레": ingredient_text("치킨카츠카레", "닭고기, 카레소스, 밀, 계란, 우유 가능성, 대두", "닭고기 도축 방식, 밀, 계란 확인 필요", "확인 필요"),
        "돈가스덮밥": ingredient_text("돈가스덮밥", "돼지고기, 쌀, 계란, 밀, 대두, 소스", "돼지고기 포함", "피함 권장"),
        "돈가스카레": ingredient_text("돈가스카레", "돼지고기, 카레소스, 밀, 계란, 대두, 우유 가능성", "돼지고기, 카레 소스 확인 필요", "피함 권장"),
        "치즈돈가스덮밥": ingredient_text("치즈돈가스덮밥", "돼지고기, 치즈, 쌀, 밀, 계란, 우유", "돼지고기, 우유 포함", "피함 권장"),
        "치즈돈가스카레": ingredient_text("치즈돈가스카레", "돼지고기, 치즈, 카레소스, 밀, 계란, 우유", "돼지고기, 우유, 카레 소스 확인 필요", "피함 권장"),
        "가츠돈": ingredient_text("가츠돈", "돼지고기, 계란, 쌀, 간장, 밀, 대두", "돼지고기, 계란 포함 가능성", "피함 권장"),
        "치즈가츠돈": ingredient_text("치즈가츠돈", "돼지고기, 치즈, 계란, 쌀, 밀, 대두", "돼지고기, 우유, 계란 주의", "피함 권장"),
        "함박카레": ingredient_text("함박카레", "소고기/돼지고기 혼합육 가능성, 카레소스, 밀, 계란, 대두", "돼지고기 혼합 가능성", "피함 권장"),
        "치즈함박카레": ingredient_text("치즈함박카레", "소고기/돼지고기 혼합육 가능성, 치즈, 카레소스, 밀, 계란, 우유", "돼지고기 혼합 가능성, 우유 주의", "피함 권장"),
        "라면": ingredient_text("라면", "밀, 대두, 라면스프", "스프 내 육류 성분 가능성", "스프 성분 확인 필요"),
        "떡라면": ingredient_text("떡라면", "밀, 대두, 떡, 라면스프", "스프 내 육류 성분 가능성", "스프 성분 확인 필요"),
        "치즈라면": ingredient_text("치즈라면", "밀, 대두, 치즈, 우유, 라면스프", "우유, 스프 내 육류 성분 가능성", "스프 성분 확인 필요"),
        "얼큰콩나물라면": ingredient_text("얼큰콩나물라면", "밀, 대두, 콩나물, 라면스프", "스프 내 육류 성분 가능성", "스프 성분 확인 필요"),
        "물냉면(계절메뉴)": ingredient_text("물냉면(계절메뉴)", "면, 밀, 메밀 가능성, 계란 가능성, 육수", "육수 성분, 계란 확인 필요", "육수 성분 확인 필요"),
        "비빔냉면(계절메뉴)": ingredient_text("비빔냉면(계절메뉴)", "면, 밀, 메밀 가능성, 고추장, 계란 가능성, 육수", "소스와 육수 성분 확인 필요", "소스 및 육수 확인 필요"),
    },
    "main": {
        "백미밥": ingredient_text("백미밥", "쌀", "특이 성분은 적으나 조리 환경 확인 필요", "대체로 가능"),
        "열무국수": ingredient_text("열무국수", "면, 밀, 열무김치, 육수", "육수 성분 확인 필요", "육수 성분 확인 필요"),
        "생선까스": ingredient_text("생선까스", "생선, 밀, 계란, 대두, 튀김유", "생선, 밀, 계란 주의", "대체로 가능하나 튀김유와 소스 확인 필요"),
        "건파래볶음": ingredient_text("건파래볶음", "파래, 참기름, 대두 가능성", "대두, 참기름 확인 필요", "대체로 가능"),
        "도라지무침": ingredient_text("도라지무침", "도라지, 고추장, 식초, 대두, 밀 가능성", "양념 성분 확인 필요", "소스 확인 필요"),
        "고들빼기": ingredient_text("고들빼기", "고들빼기, 고춧가루, 젓갈 가능성", "젓갈 포함 여부 확인 필요", "젓갈 성분 확인 필요"),
        "계절나물": ingredient_text("계절나물", "계절 채소, 참기름, 대두 가능성", "양념 성분 확인 필요", "대체로 가능"),
        "포기김치": ingredient_text("포기김치", "배추, 고춧가루, 마늘, 젓갈 가능성", "젓갈 포함 여부 확인 필요", "젓갈 성분 확인 필요"),
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
        "ingredientsByMenu": INGREDIENTS_BY_MENU,
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
