#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Law.GG 데이터 동기화 스크립트 - 최종 개선 버전
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db, Member, Bill
import csv
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from datetime import datetime
import time
from sqlalchemy import func, or_, and_

# API 설정
API_KEY = 'a3fada8210244129907d945abe2beada'
BASE_URL = 'https://open.assembly.go.kr/portal/openapi'

def test_api_connection():
    """API 연결 테스트"""
    print("\n=== API 연결 테스트 ===")
    test_url = f"{BASE_URL}/ALLNAMEMBER"
    params = {
        'KEY': API_KEY,
        'Type': 'xml',
        'pIndex': 1,
        'pSize': 1
    }
    
    try:
        print(f"테스트 URL: {test_url}")
        print(f"파라미터: {params}")
        
        response = requests.get(test_url, params=params, timeout=30)
        print(f"응답 코드: {response.status_code}")
        print(f"응답 내용 (처음 500자): {response.text[:500]}")
        
        if response.status_code == 200:
            # XML 파싱 시도
            try:
                root = ET.fromstring(response.content)
                # 다양한 방법으로 결과 코드 찾기
                result_code = None
                result_msg = None
                
                # 방법 1: .//RESULT/CODE
                code_elem = root.find('.//RESULT/CODE')
                if code_elem is not None:
                    result_code = code_elem.text
                
                # 방법 2: .//CODE  
                if result_code is None:
                    code_elem = root.find('.//CODE')
                    if code_elem is not None:
                        result_code = code_elem.text
                
                # 메시지도 찾기
                msg_elem = root.find('.//RESULT/MESSAGE')
                if msg_elem is not None:
                    result_msg = msg_elem.text
                elif root.find('.//MESSAGE') is not None:
                    result_msg = root.find('.//MESSAGE').text
                
                print(f"API 결과 코드: {result_code}")
                print(f"API 결과 메시지: {result_msg}")
                
                if result_code == 'INFO-000':
                    print("✅ API 연결 성공!")
                    return True
                else:
                    print(f"❌ API 오류: {result_msg}")
                    return False
                    
            except ET.ParseError as e:
                print(f"❌ XML 파싱 오류: {str(e)}")
                # 하지만 200 응답이므로 성공으로 처리
                if 'INFO-000' in response.text:
                    print("✅ 응답 텍스트에서 INFO-000 확인됨, 연결 성공!")
                    return True
                return False
        else:
            print(f"❌ HTTP 오류: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 연결 오류: {type(e).__name__}: {str(e)}")
        return False

def get_hunjunghoi_education_career(name, session_num):
    """헌정회 API에서 20, 21대 의원의 학력/경력 정보 가져오기"""
    try:
        url = f"{BASE_URL}/nprlapfmaufmqytet"
        params = {
            'KEY': API_KEY,
            'Type': 'xml',
            'pIndex': 1,
            'pSize': 10,
            'DAESU': str(session_num),
            'NAME': name
        }
        
        print(f"   📚 헌정회 API 호출: {name} ({session_num}대)")
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code == 200 and 'INFO-000' in response.text:
            root = ET.fromstring(response.content)
            rows = root.findall('.//row')
            
            if rows:
                for row in rows:
                    hak_data = row.findtext('HAK', '').strip()
                    if hak_data:
                        # HTML 엔티티 변환
                        hak_data = hak_data.replace('&middot;', '·')
                        hak_data = hak_data.replace('&nbsp;', ' ')
                        hak_data = hak_data.replace('&amp;', '&')
                        
                        print(f"   ✅ 헌정회 약력 찾음: {name} - {len(hak_data)}자")
                        return parse_assembly_profile_text(hak_data, name)
        
        return None, None
        
    except Exception as e:
        print(f"   ❌ 헌정회 API 오류: {str(e)}")
        return None, None

# sync_data.py의 crawl_member_profile_with_detection() 함수를 이것으로 교체

def crawl_member_profile_with_detection(member_name, english_name, session_num=22):
    """개선된 홈페이지 크롤링 - 다양한 영문명 변형 지원"""
    try:
        if not english_name:
            print(f"   ❌ 영문명 없음: {member_name}")
            return None, None, None, True
            
        # 🔥 다양한 영문명 변형 생성
        clean_name = english_name.replace(' ', '').strip()
        
        name_variations = [
            clean_name.upper(),           # KIMHYUN (기존 방식)
            clean_name.title(),           # Kimhyun
            clean_name.lower(),           # kimhyun
        ]
        
        # 한국식 성명 패턴 추가 (성 대문자 + 이름 첫글자 대문자)
        if len(clean_name) >= 4:
            surname_2 = clean_name[:2].upper()
            given_name_2 = clean_name[2:]
            name_variations.extend([
                f"{surname_2}{given_name_2.title()}",      # KIMHyun ← 김현 의원!
                f"{surname_2}{given_name_2.lower()}",      # KIMhyun
            ])
        
        if len(clean_name) >= 5:
            surname_3 = clean_name[:3].upper()
            given_name_3 = clean_name[3:]
            name_variations.extend([
                f"{surname_3}{given_name_3.title()}",      # LEEJongSuk
                f"{surname_3}{given_name_3.lower()}",      # LEEjongsuk
            ])
        
        # 중복 제거
        unique_variations = list(dict.fromkeys(name_variations))
        
        print(f"   🔍 영문명 변형 시도: {member_name} (원본: {english_name})")
        print(f"   📝 시도할 변형들: {unique_variations[:5]}...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
            'Referer': 'https://www.assembly.go.kr/',
            'Connection': 'keep-alive'
        }
        
        # 각 변형에 대해 시도
        for i, name_var in enumerate(unique_variations):
            url = f"https://www.assembly.go.kr/members/{session_num}nd/{name_var}"
            
            try:
                print(f"   🌐 시도 {i+1}: {name_var}")
                response = requests.get(url, timeout=30, headers=headers)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # 실제 의원 페이지인지 확인
                    page_text = soup.get_text()
                    if member_name in page_text or "국회의원" in page_text:
                        print(f"   ✅ URL 성공: {url}")
                        
                        # 메뉴 텍스트만 있는지 확인
                        if is_menu_text_only(page_text, member_name):
                            print(f"   ⚠️ 메뉴 텍스트만 감지됨 - 다음 변형 시도")
                            continue
                        
                        # 구조적 파싱 시도
                        education_items, career_items = parse_structured_html(soup, member_name)
                        
                        if education_items or career_items:
                            print(f"   ✅ 파싱 성공: 학력 {len(education_items or [])}개, 경력 {len(career_items or [])}개")
                            return education_items, career_items, url, False
                        else:
                            print(f"   ⚠️ 파싱 결과 없음 - API fallback 필요")
                            return None, None, None, True
                            
            except Exception as e:
                # 조용히 다음 변형 시도
                continue
            
            # 최대 6-7개까지만 시도 (성능 최적화)
            if i >= 6:
                break
        
        print(f"   ❌ 모든 영문명 변형 실패: {member_name}")
        return None, None, None, True
        
    except Exception as e:
        print(f"   ❌ 크롤링 오류 ({member_name}): {str(e)}")
        return None, None, None, True

def parse_structured_html(soup, member_name):
    education_items = []
    career_items = []
    
    try:
        # 🔥 방법 1: <pre> 태그 파싱 (기존 방식)
        pre_tags = soup.find_all('pre')
        for pre in pre_tags:
            text = pre.get_text(strip=True)
            if text and len(text) > 50:
                if is_menu_text_content(text):
                    return None, None
                
                # 🔥 기존 방식 대신 무조건 분할 적용
                print(f"   📋 <pre> 태그 데이터에 무조건 분할 방식 적용: {member_name}")
                education_items, career_items = parse_assembly_profile_text(text, member_name)
                
                if education_items or career_items:
                    break
        
        # 🔥 방법 2: <pre> 태그 없는 경우
        if not education_items and not career_items:
            page_text = soup.get_text()
            if is_menu_text_only(page_text, member_name):
                return None, None
            
            print(f"   🌐 페이지 전체에 무조건 분할 방식 적용: {member_name}")
            education_items, career_items = parse_assembly_profile_text(page_text, member_name)
        
        return education_items, career_items
        
    except Exception as e:
        print(f"   ❌ 파싱 오류: {str(e)}")
        return None, None
        
def is_menu_text_only(page_text, member_name):
    """메뉴 텍스트만 크롤링된 경우인지 감지 - 포괄적 개선 버전"""
    
    # 🔥 실제 프로필 컨텐츠 지표들 (모든 의원 공통)
    real_content_indicators = [
        # 학력/경력 섹션 마커
        '■ 학력', '□ 학력', '[학력]', '○ 학력', '▶학력', '▶ 학력',
        '■ 경력', '□ 경력', '[경력]', '○ 경력', '▶경력', '▶ 경력',
        '■ 약력', '□ 약력', '[약력]', '○ 약력', '▶약력', '▶ 약력',
        '주요학력', '주요경력', '주요약력',
        
        # 구체적 학력 정보
        '졸업', '수료', '입학', '편입', '학사', '석사', '박사', '학위',
        '대학교', '대학원', '고등학교', '중학교', '사관학교',
        
        # 구체적 경력 정보  
        '장관', '차관', '청장', '실장', '국장', '과장', '팀장',
        '위원장', '부위원장', '간사', '위원', '의장', '부의장',
        '대표이사', '사장', '부사장', '전무', '상무', '이사', '부장',
        '회장', '부회장', '원장', '부원장', '소장', '센터장',
        '교수', '부교수', '조교수', '겸임교수', '객원교수',
        '변호사', '판사', '검사', '기자', '논설위원', '편집위원',
        '의사', '약사', '회계사', '세무사', '건축사',
        
        # 시간 정보 (실제 약력에 포함)
        '1960년', '1961년', '1962년', '1963년', '1964년', '1965년', '1966년', '1967년', '1968년', '1969년',
        '1970년', '1971년', '1972년', '1973년', '1974년', '1975년', '1976년', '1977년', '1978년', '1979년',
        '1980년', '1981년', '1982년', '1983년', '1984년', '1985년',
        '2020년', '2021년', '2022년', '2023년', '2024년', '2025년',
        
        # 정치 관련 (실제 약력)
        '제19대', '제20대', '제21대', '제22대', '19대', '20대', '21대', '22대',
        '더불어민주당', '국민의힘', '정의당', '국민의당', '조국혁신당', '개혁신당',
        '민주당', '한나라당', '새누리당',
        
        # 연대/기간 표시
        '~', '-', '부터', '까지', '동안', '간',
        '전)', '현)', '前)', '現)', '前', '現',
        
        # 기관/조직명
        '청와대', '국회', '정부', '부처', '법원', '검찰', '경찰',
        '대학', '연구소', '재단', '협회', '학회', '위원회',
    ]
    
    # 🔥 메뉴 텍스트 지표들
    menu_indicators = [
        f'국회의원 - {member_name}',
        f'국회의원-{member_name}',
        '의원실알림', '역대국회의원', '국회의원통계',
        '22대국회의원', '21대국회의원', '20대국회의원',
        '국회의원 이력', '위원회 경력', '대표발의법률안',
        '위원회 의사일정', '의정활동', '정책자료', '보도자료',
        '의정보고서', '정책세미나', '토론회', '간담회',
        '외 XX개', '외 \d+개',  # 강경숙 의원 케이스
    ]
    
    # 실제 컨텐츠 개수 세기
    content_count = sum(1 for indicator in real_content_indicators if indicator in page_text)
    menu_count = sum(1 for indicator in menu_indicators if indicator in page_text)
    
    # 정규식 패턴도 체크
    import re
    if re.search(r'외\s*\d+개', page_text):
        menu_count += 1
    
    # 연도 패턴이 있으면 실제 컨텐츠 가산점
    if re.search(r'\d{4}년|\d{4}\.\d{1,2}|\d{4}-\d{1,2}', page_text):
        content_count += 2
    
    print(f"   📊 컨텐츠 분석: {member_name} - 실제컨텐츠: {content_count}개, 메뉴지표: {menu_count}개")
    
    # 🔥 포괄적 판단 로직
    # 1. 실제 컨텐츠가 5개 이상이면 확실히 정상 페이지
    if content_count >= 5:
        print(f"   ✅ 실제 컨텐츠 풍부: {member_name} - 정상 페이지")
        return False
    
    # 2. 실제 컨텐츠가 2-4개이고 텍스트가 충분하면 정상 페이지
    if content_count >= 2 and len(page_text.strip()) > 600:
        print(f"   ✅ 컨텐츠 + 충분한 길이: {member_name} - 정상 페이지")
        return False
    
    # 3. 메뉴 지표가 많고 실제 컨텐츠가 부족하면 메뉴 페이지
    if menu_count >= 3 and content_count <= 1:
        print(f"   ❌ 메뉴 텍스트 감지: {member_name}")
        return True
    
    # 4. 텍스트가 매우 짧고 컨텐츠가 없으면 메뉴 페이지
    if len(page_text.strip()) < 400 and content_count == 0:
        print(f"   ❌ 텍스트 부족: {member_name} ({len(page_text.strip())}자)")
        return True
    
    # 5. 의심스러운 패턴들 체크
    suspicious_patterns = [
        '게시물 저장 중입니다',
        '외 \d+개',
        '더보기',
        '접기',
        '펼치기'
    ]
    
    suspicious_count = sum(1 for pattern in suspicious_patterns if re.search(pattern, page_text))
    if suspicious_count >= 2 and content_count <= 1:
        print(f"   ❌ 의심스러운 패턴 감지: {member_name}")
        return True
    
    # 6. 기본적으로는 정상 페이지로 판단 (보수적)
    print(f"   ✅ 정상 페이지로 판단: {member_name}")
    return False
    
def parse_pre_tag_career(text):
    """<pre> 태그 내용을 스마트하게 파싱 - 22대 의원 개선 버전"""
    items = []
    
    # 🔥 먼저 메뉴 텍스트인지 확인
    if is_menu_text_content(text):
        print(f"   ⚠️ 메뉴 텍스트 감지됨, fallback 진행")
        return []
    
    import re
    
    # 🔥 1단계: 22대 의원 특화 - 현/전 구분자로 강력 분할
    modern_patterns = [
        r'(?=•\s*現\s)',    # "• 現 " 앞에서 분할
        r'(?=•\s*前\s)',    # "• 前 " 앞에서 분할  
        r'(?=現\s)',        # "現 " 앞에서 분할
        r'(?=前\s)',        # "前 " 앞에서 분할
        r'(?=전\)\s)',      # "전) " 앞에서 분할
        r'(?=현\)\s)',      # "현) " 앞에서 분할
    ]
    
    # 현/전 패턴으로 분할 시도
    for pattern in modern_patterns:
        parts = re.split(pattern, text)
        if len(parts) > 1:  # 분할이 성공한 경우
            print(f"   🔥 현/전 패턴으로 분할 성공: {len(parts)}개")
            for part in parts:
                part = part.strip()
                if len(part) > 10 and len(part) < 500:  # 적절한 길이
                    cleaned = clean_career_item_advanced(part)
                    if cleaned and is_valid_career_item(cleaned):
                        items.append(cleaned)
            
            if items:  # 성공적으로 분할됨
                return items
    
    # 2단계: 연도 기반 분할 (기존 방식)
    year_pattern = r'(\d{4}\.?\d*[-~]\d{4}\.?\d*|\d{4}\.?\d+)'
    year_matches = list(re.finditer(year_pattern, text))
    
    if len(year_matches) >= 2:  # 연도가 2개 이상 있으면 연도 기준으로 분할
        prev_end = 0
        for i, match in enumerate(year_matches[1:], 1):
            # 이전 연도부터 현재 연도 직전까지
            start = prev_end
            end = match.start()
            
            segment = text[start:end].strip()
            if len(segment) > 15 and len(segment) < 300:
                cleaned = clean_career_item_advanced(segment)
                if cleaned and is_valid_career_item(cleaned):
                    items.append(cleaned)
            
            prev_end = match.start()
        
        # 마지막 부분
        last_segment = text[prev_end:].strip()
        if len(last_segment) > 15 and len(last_segment) < 300:
            cleaned = clean_career_item_advanced(last_segment)
            if cleaned and is_valid_career_item(cleaned):
                items.append(cleaned)
    
    # 3단계: 기존 패턴 분할 (연도 분할 실패시)
    if not items:
        patterns = [
            r'(?=전\))',      # "전)" 앞에서 분할
            r'(?=現\))',      # "現)" 앞에서 분할  
            r'(?=현\))',      # "현)" 앞에서 분할
        ]
        
        for pattern in patterns:
            parts = re.split(pattern, text)
            if len(parts) > 1:
                for part in parts:
                    part = part.strip()
                    if len(part) > 15 and len(part) < 300:
                        cleaned = clean_career_item_advanced(part)
                        if cleaned and is_valid_career_item(cleaned):
                            items.append(cleaned)
                break
    
    # 4단계: 분할 실패시 전체를 하나로
    if not items and len(text) > 20:
        cleaned = clean_career_item_advanced(text)
        if cleaned and is_valid_career_item(cleaned):
            items.append(cleaned)
    
    return items

def is_menu_text_content(text):
    """메뉴 텍스트만 있는 내용인지 판단"""
    menu_patterns = [
        '국회의원 -', '의원실알림', '역대국회의원', '국회의원통계',
        '국회의원 이력', '위원회 경력', '대표발의법률안', '위원회 의사일정',
        '의정활동', '정책자료', '보도자료', '더보기', '접기', '펼치기'
    ]
    
    menu_count = sum(1 for pattern in menu_patterns if pattern in text)
    
    # 메뉴 텍스트가 3개 이상이고 전체 길이가 짧으면 메뉴만 있는 것
    return menu_count >= 3 and len(text) < 500

def clean_career_item_advanced(item):
    """고급 경력 항목 정리"""
    if not item:
        return None
    
    # 앞뒤 공백 및 따옴표 제거
    item = item.strip().strip('"').strip("'")
    
    # 🔥 괄호 내용 보호 (제6회, 제7회 등)
    import re
    
    # 불필요한 접두사 제거 (괄호 보호하면서)
    prefixes_to_remove = [
        '(현)', '(전)', '現)', '前)', 
        '-', '•', '·', '※', '▶', '▪', '▫', '◦'
    ]
    
    for prefix in prefixes_to_remove:
        if item.startswith(prefix):
            item = item[len(prefix):].strip()
    
    # 🔥 중요한 괄호는 보호하면서 쉼표 분할 방지
    # (제6회, 제7회) 같은 패턴은 분할하지 않음
    protected_patterns = [
        r'\(제\d+회[,\s]*제?\d*회?\)',  # (제6회, 제7회)
        r'\(제\d+대[,\s]*제?\d*대?\)',  # (제20대, 제21대)
        r'\(\d{4}[,\s]*\d{4}\)',       # (2020, 2021)
    ]
    
    # 보호된 패턴이 있으면 분할하지 않음
    has_protected = any(re.search(pattern, item) for pattern in protected_patterns)
    
    if not has_protected:
        # 일반적인 정리만 수행
        item = re.sub(r'\s+', ' ', item)  # 공백 정리
    
    return item if len(item) > 5 else None

def is_education_item(item):
    """학력 항목인지 판단"""
    education_keywords = [
        '학교', '학원', '대학교', '고등학교', '중학교', '초등학교', '대학원',
        '학과', '졸업', '수료', '입학', '전공', '학사', '석사', '박사',
        '사관학교', '교육대학', '기술대학', '전문대학',
        # 🔥 교수직 추가 - 학교 관련 경력
        '교수', '전임교수', '부교수', '조교수', '겸임교수', '객원교수', 
        '초빙교수', '명예교수', '연구교수', '임상교수', '시간강사',
        '강사', '교육과정', '교육연구'
    ]
    
    return any(keyword in item for keyword in education_keywords)

def is_menu_text_only(page_text, member_name):
    """메뉴 텍스트만 크롤링된 경우인지 감지"""
    
    # 🔥 조국 의원처럼 메뉴 텍스트만 나오는 패턴들
    menu_indicators = [
        f'국회의원 - {member_name}',
        f'국회의원-{member_name}',
        '의원실알림',
        '역대국회의원',
        '국회의원통계',
        '22대국회의원',
        '21대국회의원', 
        '20대국회의원',
        '국회의원 이력',
        '위원회 경력',
        '대표발의법률안',
        '위원회 의사일정',
        '의정활동',
        '정책자료',
        '보도자료'
    ]
    
    # 실제 학력/경력 정보 패턴들
    real_content_indicators = [
        '■ 학력', '□ 학력', '[학력]', '○ 학력', '▶학력',
        '■ 경력', '□ 경력', '[경력]', '○ 경력', '▶경력',
        '■ 약력', '□ 약력', '[약력]', '○ 약력', '▶약력',
        '주요약력', '주요경력', '주요학력',  # 🔥 추가
        '대학교', '고등학교', '졸업', '수료',
        '위원장', '장관', '청장', '교수', '변호사', '판사'
    ]
    
    # 메뉴 텍스트 개수 세기
    menu_count = sum(1 for indicator in menu_indicators if indicator in page_text)
    
    # 실제 컨텐츠 개수 세기
    content_count = sum(1 for indicator in real_content_indicators if indicator in page_text)
    
    # 🔥 개선된 판단 로직
    # 1. 실제 컨텐츠가 3개 이상 있으면 정상 페이지로 판단
    if content_count >= 3:
        return False
    
    # 2. 메뉴 텍스트가 3개 이상이고 실제 컨텐츠가 거의 없으면 메뉴만 크롤링된 것
    if menu_count >= 3 and content_count <= 1:
        return True
    
    # 3. 텍스트가 매우 짧고 메뉴 텍스트만 있는 경우
    if len(page_text.strip()) < 500 and menu_count >= 2:
        return True
    
    # 4. "외 XX개" 패턴이 있고 실제 정보가 없는 경우 (강경숙 의원 케이스)
    import re
    if re.search(r'외\s*\d+개', page_text) and content_count == 0:
        return True
    
    return False

def parse_assembly_profile_text(text, member_name):
    """무조건 분할 후 스마트 분류 방식"""
    education_items = []
    career_items = []
    
    try:
        print(f"   📋 무조건 분할 방식 적용: {member_name}")
        
        # 🔥 1단계: 무조건 분할
        all_items = force_split_text_completely(text)
        print(f"   📊 분할 결과: {len(all_items)}개 항목")
        
        # 🔥 2단계: 학력/경력 분류
        for item in all_items:
            cleaned = clean_item_thoroughly(item)
            if not cleaned:
                continue
                
            if is_education_strict(cleaned):
                education_items.append(cleaned)
                print(f"   📚 학력: {cleaned[:50]}...")
            else:
                career_items.append(cleaned)
                print(f"   💼 경력: {cleaned[:50]}...")
        
        # 🔥 3단계: 중복 제거
        education_items = remove_duplicates_final(education_items)
        career_items = remove_duplicates_final(career_items)
        
        print(f"   ✅ 최종 결과: {member_name} - 학력:{len(education_items)}개, 경력:{len(career_items)}개")
        return education_items, career_items
        
    except Exception as e:
        print(f"   ❌ 분할 오류: {str(e)}")
        return [], []
        
def force_split_text_completely(text):
    """텍스트를 최대한 세분화"""
    import re
    
    # 모든 가능한 구분자로 분할
    separators = [
        r'•\s*',           # • 
        r'·\s*',           # ·
        r'(?<=졸업)\s+',    # 졸업 뒤
        r'(?<=수료)\s+',    # 수료 뒤  
        r'(?<=위원)\s+',    # 위원 뒤
        r'(?<=의원)\s+',    # 의원 뒤
        r'(?<=장관)\s+',    # 장관 뒤
        r'(?<=청장)\s+',    # 청장 뒤
        r'(?<=교수)\s+',    # 교수 뒤
        r'(?<=대표)\s+',    # 대표 뒤
        r'(?<=회장)\s+',    # 회장 뒤
        r'(?<=\))\s+',     # 괄호 뒤
        r'\n+',            # 줄바꿈
        r'\s{3,}',         # 3칸 이상 공백
        # 🔥 추가: 섹션 헤더 구분자 (김건 사례)
        r'학력\s*:?\s*',    # 학력: 또는 학력
        r'경력\s*:?\s*',    # 경력: 또는 경력  
        r'약력\s*:?\s*',    # 약력: 또는 약력
        r'■\s*학력\s*',     # ■ 학력
        r'■\s*경력\s*',     # ■ 경력
        r'□\s*학력\s*',     # □ 학력  
        r'□\s*경력\s*',     # □ 경력
        r'■\s*주요 학력\s*',     # ■ 학력
        r'■\s*주요 경력\s*',     # ■ 경력
        r'□\s*주요 학력\s*',     # □ 학력  
        r'□\s*주요 경력\s*',     # □ 경력
    ]
    
    items = [text]
    for separator in separators:
        new_items = []
        for item in items:
            parts = re.split(separator, item)
            new_items.extend([p.strip() for p in parts if p.strip()])
        items = new_items
    
    return [item for item in items if len(item.strip()) > 3]
    
def clean_item_thoroughly(item):
    """아이템 철저히 정리"""
    if not item:
        return None
    
    # 기본 정리
    item = item.strip().strip('"').strip("'")
    
    # 🔥 괄호 안의 연도 정보 제거
    import re
    item = re.sub(r'\((\d{4})\)', '', item)  # (2020) 제거
    item = re.sub(r'\((\d{4}년)\)', '', item)  # (2020년) 제거
    
    # 불필요한 접두사 제거
    prefixes = ['(현)', '(전)', '現)', '前)', '現', '前', '-', '•', '·', '※', '▶']
    for prefix in prefixes:
        if item.startswith(prefix):
            item = item[len(prefix):].strip()
    
    # 🔥 섹션 헤더 제거 (포괄적으로 확장)
    section_headers = [
        # 기본 형태
        '학력:', '경력:', '약력:', 
        '주요학력:', '주요경력:', '주요약력:',
        '학력사항:', '경력사항:', '약력사항:',
        
        # ■ 형태
        '■ 학력', '■ 경력', '■ 약력', 
        '■ 주요학력', '■ 주요경력', '■ 주요약력',
        '■ 학력사항', '■ 경력사항', '■ 약력사항',
        
        # □ 형태 (강명구 사례)
        '□ 학력', '□ 경력', '□ 약력',
        '□ 주요학력', '□ 주요경력', '□ 주요약력',
        '□ 학력사항', '□ 경력사항', '□ 약력사항',
        '□ 주요 학력', '□ 주요 경력', '□ 주요 약력',  # 공백 있는 버전
        
        # ○ 형태
        '○ 학력', '○ 경력', '○ 약력',
        '○ 주요학력', '○ 주요경력', '○ 주요약력',
        
        # [대괄호] 형태
        '[학력]', '[경력]', '[약력]',
        '[주요학력]', '[주요경력]', '[주요약력]',
        '[학력사항]', '[경력사항]', '[약력사항]',
        
        # ▶ 형태
        '▶ 학력', '▶ 경력', '▶ 약력',
        '▶ 주요학력', '▶ 주요경력', '▶ 주요약력'
    ]
    
    for header in section_headers:
        if item.startswith(header):
            item = item[len(header):].strip()
            break  # 하나 찾으면 중단
    
    # 너무 짧거나 의미없는 것 제외
    if len(item) < 4:
        return None
    
    # 🔥 섹션 헤더만 남은 경우 제외 (확장)
    header_only = [
        '학력', '경력', '약력', '주요학력', '주요경력', '주요약력',
        '학력사항', '경력사항', '약력사항', '주요 학력', '주요 경력', '주요 약력'
    ]
    if item.lower() in [h.lower() for h in header_only]:
        return None
    
    # 연락처나 UI 요소 제외
    exclude_patterns = ['T:', 'F:', '@', 'http', '전화', '팩스', '이메일', '더보기', '감추기']
    if any(pattern in item for pattern in exclude_patterns):
        return None
    
    return item
    
def is_education_strict(item):
    """엄격한 학력 판별"""
    education_keywords = [
        # 학교 관련
        '초등학교', '중학교', '고등학교', '대학교', '대학원', '사관학교',
        # 학위/과정 관련  
        '졸업', '수료', '입학', '학사', '석사', '박사', '학과', '학부', '전공',
        # 교육 직책 (학력으로 분류)
        '교수', '부교수', '조교수', '겸임교수', '객원교수', '석좌교수', 
        '강사', '연구원', '연구교수'
        '교사', '교원', '선생님', '선생', 
        '특수교육', '유치원교사', '초등교사', '중등교사', '고등학교교사'
    ]
    
    return any(keyword in item for keyword in education_keywords)

def remove_duplicates_final(items):
    """최종 중복 제거"""
    if not items:
        return []
    
    result = []
    seen_keywords = set()
    
    for item in items:
        # 주요 키워드로 중복 판별
        import re
        keywords = re.findall(r'[가-힣]+(?:대학교?|고등학교|중학교|교수|위원장|장관|청장)', item)
        keyword_signature = tuple(sorted(set(keywords)))
        
        if keyword_signature not in seen_keywords or not keyword_signature:
            seen_keywords.add(keyword_signature)
            result.append(item)
    
    return result
    
def find_sections(text, markers):
    """텍스트에서 특정 마커들로 시작하는 섹션들 찾기"""
    sections = []
    
    for marker in markers:
        marker_pos = text.find(marker)
        if marker_pos != -1:
            # 마커 이후부터 다음 주요 섹션까지 추출
            section_start = marker_pos
            
            # 다음 섹션 구분자들 찾기
            next_markers = [
                '□ ', '■', '○ ', '[', '<', '**', '* ',
                '\n\n\n',  # 3줄 이상 공백
                '내일을 여는',  # 페이지 하단
                '지역사무실',  # 연락처 섹션
                'T:', 'F:'  # 전화번호 섹션
            ]
            
            section_end = len(text)
            for next_marker in next_markers:
                next_pos = text.find(next_marker, marker_pos + len(marker))
                if next_pos != -1 and next_pos < section_end:
                    section_end = next_pos
            
            section = text[section_start:section_end].strip()
            if len(section) > len(marker):  # 마커만 있는 게 아닌 경우
                sections.append(section)
    
    return sections

def extract_items_from_section(section_text, is_education=False):
    """섹션 텍스트에서 항목들 추출 - 스마트 파싱으로 분할 오류 방지"""
    items = []
    
    # 섹션 헤더 제거 (모든 발견된 패턴 포함)
    headers_to_remove = [
        # ■ 계열
        '■ 학력', '■학력', '■ 학력:', '■학력:', '■ 주요경력', '■주요경력', '■ 경력', '■경력', '■ 경력:', '■경력:', '■ 약력', '■약력',
        # □ 계열  
        '□ 학력', '□학력', '□ 주요 약력', '□ 약력', '□ 경력', '□ 주요경력', '□주요 약력', '□약력', '□경력', '□주요경력',
        # [대괄호] 계열
        '[학력사항]', '[학력]', '[ 학력 ]', '[경력사항]', '[경력]', '[ 경력 ]', '[약력사항]', '[약력]', '[ 약력 ]',
        # ○ 계열
        '○ 학력', '○학력', '○ 약력', '○ 경력', '○약력', '○경력', '○ 주요 경력', '○주요 경력',
        # * 계열
        '*학력', '* 학력', '*주요학력', '* 주요학력', '*주요경력', '* 주요경력', '*경력', '* 경력', '*약력', '* 약력',
        # < > 계열
        '<학력사항>', '<학력>', '<주요학력>', '<경력사항>', '<경력>', '<약력사항>', '<약력>', '<주요경력>',
        # ▶ 계열
        '▶학력', '▶ 학력', '▶주요학력', '▶ 주요학력', '▶경력', '▶ 경력', '▶약력', '▶ 약력', '▶주요경력', '▶ 주요경력',
        # · 점 계열
        '· 학력', '·학력', '• 학력', '•학력', '· 경력', '·경력', '• 경력', '•경력', '· 약력', '·약력', '• 약력', '•약력',
        # 숫자 계열
        '1. 학력', '1) 학력', '가. 학력', '① 학력', '㉠ 학력', '2. 경력', '2) 경력', '나. 경력', '② 경력', '㉡ 경력',
        # ** 마크다운
        '**학력', '** 학력', '**주요학력', '** 주요학력', '**경력', '** 경력', '**약력', '** 약력', '**주요경력', '** 주요경력',
        # 기타 특수 기호
        '◆ 학력', '◇ 학력', '▲ 학력', '▽ 학력', '※ 학력', '☞ 학력', '◆ 경력', '◇ 경력', '▲ 경력', '▽ 경력', '※ 경력', '☞ 경력',
        # 일반사항
        '■ 일반사항'
    ]
    
    for header in headers_to_remove:
        if section_text.startswith(header):
            section_text = section_text[len(header):].strip()
            break
    
    # 🔥 스마트 파싱: 줄바꿈 기반이지만 의미 단위 보존
    items = smart_parse_career_items(section_text)
    
    # 후처리: 유효한 항목만 필터링
    filtered_items = []
    for item in items:
        if is_valid_career_item(item):
            cleaned_item = clean_career_item(item)
            if cleaned_item:
                filtered_items.append(cleaned_item)
    
    return filtered_items

def smart_parse_career_items(text):
    """스마트 파싱으로 의미 단위 유지하면서 항목 분할"""
    import re
    
    # 1단계: 명확한 구분자로 분할 (줄바꿈 + 리스트 마커)
    list_pattern = r'\n\s*(?:[-•·▶▪▫◦‣⁃]|\d+[.)]\s*|[가-힣][.)]\s*|\([가-힣]\)\s*)'
    primary_items = re.split(list_pattern, text)
    
    result_items = []
    
    for item in primary_items:
        item = item.strip()
        if not item or len(item) < 3:
            continue
            
        # 2단계: 연도 범위나 기간이 포함된 경우 보존
        if has_date_range(item):
            # 날짜 범위가 있는 항목은 분할하지 않음
            result_items.append(item)
            continue
        
        # 3단계: 복합어나 연결어가 있는 경우 보존
        if has_compound_words(item):
            # 복합어가 있는 항목은 분할하지 않음
            result_items.append(item)
            continue
        
        # 4단계: 기관명이나 학교명이 있는 경우 보존
        if has_institution_name(item):
            # 기관명이 있는 항목은 분할하지 않음
            result_items.append(item)
            continue
        
        # 5단계: 위 조건에 해당하지 않는 경우만 추가 분할 시도
        sub_items = split_if_needed(item)
        result_items.extend(sub_items)
    
    return result_items

def has_date_range(text):
    """날짜 범위나 연도가 포함되어 있는지 확인"""
    import re
    
    # 연도 패턴들
    year_patterns = [
        r'\d{4}년',  # 2020년
        r'\d{4}\.\d{1,2}',  # 2020.05
        r'\d{4}-\d{1,2}',  # 2020-05
        r'\d{4}~\d{4}',  # 2020~2024
        r'\d{4}\.\d{1,2}~\d{4}\.\d{1,2}',  # 2020.05~2024.05
        r'\d{4}-\d{1,2}-\d{1,2}',  # 2020-05-30
        r'\(\d{4}\)',  # (2020)
        r'\d{4}\s*-\s*\d{4}',  # 2020 - 2024
        r'제\d+대',  # 제21대
        r'\d+기',  # 28기
        r'\d+회',  # 31회
    ]
    
    for pattern in year_patterns:
        if re.search(pattern, text):
            return True
    return False

def has_compound_words(text):
    """복합어나 연결어가 포함되어 있는지 확인"""
    compound_patterns = [
        '석박사', '전후반기', '상하반기', '좌우', '동서남북',
        '전반기', '후반기', '상반기', '하반기',
        '전·후반기', '상·하반기', 
        '국회의원', '대통령', '총리', '장관', '청장', '실장', '국장', '과장', '팀장',
        '위원장', '부위원장', '간사', '위원',
        '대표', '부대표', '회장', '부회장', '이사', '감사',
        '교수', '부교수', '조교수', '겸임교수', '객원교수',
        '변호사', '판사', '검사', '사법연수원',
        '대학교', '고등학교', '중학교', '초등학교', '대학원',
        '학과', '학부', '대학', '연구소', '연구원'
    ]
    
    for pattern in compound_patterns:
        if pattern in text:
            return True
    return False

def has_institution_name(text):
    """기관명이나 학교명이 포함되어 있는지 확인"""
    institution_keywords = [
        '대학교', '대학원', '고등학교', '중학교', '초등학교',
        '청와대', '국회', '정부', '부처', '청', '원', '위원회',
        '법원', '검찰', '경찰', '군', '공사', '공단', '공기업',
        '회사', '기업', '법인', '연구소', '재단', '협회',
        '시청', '구청', '도청', '시의회', '도의회',
        '민주당', '국민의힘', '정의당', '국민의당'
    ]
    
    for keyword in institution_keywords:
        if keyword in text:
            return True
    return False

def split_if_needed(text):
    """필요한 경우에만 추가 분할"""
    # 매우 긴 텍스트(200자 이상)인 경우에만 분할 시도
    if len(text) < 200:
        return [text]
    
    # 문장 단위로 분할 (마침표, 쉼표 기준)
    import re
    sentences = re.split(r'[.·,]\s*', text)
    
    result = []
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) > 10:  # 너무 짧은 조각은 제외
            result.append(sentence)
    
    return result if result else [text]

def is_valid_career_item(item):
    """유효한 경력/학력 항목인지 확인"""
    if not item or len(item.strip()) < 3:
        return False
    
    # 연락처나 기타 정보 제외
    exclude_keywords = [
        'T:', 'F:', 'TEL:', 'FAX:', 'E-mail:', '@', 'http', 'www',
        '전화', '팩스', '이메일', '홈페이지', '주소', '사무실',
        '내일을 여는', '국회를 열다', '게시물 저장',
        '더보기', '감추기', '펼치기', '접기'
    ]
    
    for keyword in exclude_keywords:
        if keyword in item:
            return False
    
    # 너무 짧거나 긴 항목 제외
    if len(item) < 5 or len(item) > 300:
        return False
    
    return True

def clean_career_item(item):
    """경력 항목 정리"""
    if not item:
        return None
    
    # 앞뒤 공백 제거
    item = item.strip()
    
    # 불필요한 접두사 제거
    prefixes_to_remove = [
        '(현)', '(전)', '現)', '前)', '現', '前', 
        '-', '•', '·', '※', '▶', '▪', '▫', '◦',
        '1.', '2.', '3.', '4.', '5.',
        '가.', '나.', '다.', '라.', '마.',
        '①', '②', '③', '④', '⑤'
    ]
    
    for prefix in prefixes_to_remove:
        if item.startswith(prefix):
            item = item[len(prefix):].strip()
    
    # 끝의 불필요한 문자 제거
    suffixes_to_remove = ['-', '·', '•', '※']
    for suffix in suffixes_to_remove:
        if item.endswith(suffix):
            item = item[:-len(suffix)].strip()
    
    return item if item else None

def classify_by_keywords(text):
    """키워드 기반 학력/경력 분류"""
    education_items = []
    career_items = []
    
    # 전체 텍스트를 줄 단위로 분리
    lines = text.split('\n')
    
    education_keywords = [
        '학교', '학원', '대학교', '고등학교', '중학교', '초등학교', '대학원', 
        '학과', '졸업', '수료', '입학', '전공', '학사', '석사', '박사',
        '사관학교', '교육대학', '기술대학', '전문대학'
    ]
    
    for line in lines:
        line = line.strip()
        if len(line) < 5 or len(line) > 200:
            continue
            
        # 접두사 제거
        for prefix in ['(현)', '(전)', '現)', '前)', '現', '前', '-', '•', '·', '※']:
            if line.startswith(prefix):
                line = line[len(prefix):].strip()
                break
        
        if not line:
            continue
            
        # 연락처 정보 제외
        if any(keyword in line for keyword in ['T:', 'F:', 'TEL:', 'FAX:', 'E-mail:', '@', 'http', 'www']):
            continue
            
        # 학력 키워드 체크
        is_education = any(keyword in line for keyword in education_keywords)
        
        if is_education:
            education_items.append(line)
        else:
            # 의미 있는 경력 정보인지 체크
            career_keywords = ['위원', '의원', '장관', '청장', '실장', '국장', '과장', '팀장', 
                             '회장', '이사', '교수', '변호사', '판사', '검사', '대표', '원장']
            if any(keyword in line for keyword in career_keywords):
                career_items.append(line)
    
    return education_items, career_items

def remove_duplicates_preserve_order(items):
    """순서를 유지하면서 중복 제거"""
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

def parse_brf_hst_fallback(brf_hst_text, member_name):
    """BRF_HST를 무조건 분할 방식으로 처리"""
    if not brf_hst_text:
        print(f"   ❌ BRF_HST 데이터 없음: {member_name}")
        return None, None
    
    print(f"   📋 BRF_HST 무조건 분할 방식 적용: {member_name}")
    
    # HTML 엔티티 변환
    text = brf_hst_text.replace('&middot;', '·').replace('&nbsp;', ' ').replace('&amp;', '&')
    
    if len(text.strip()) < 10:
        print(f"   ❌ 텍스트 너무 짧음: {len(text)}자")
        return None, None
    
    # 🔥 무조건 분할 방식 적용
    return parse_assembly_profile_text(text, member_name)
    
def sync_members_from_api():
    """국회 OpenAPI에서 국회의원 정보 동기화 (학력/경력 포함)"""
    with app.app_context():
        print("\n=== 국회 OpenAPI에서 국회의원 정보 가져오기 (학력/경력 포함) ===")
        
        # API 연결 테스트 먼저
        if not test_api_connection():
            print("API 연결 실패! 종료합니다.")
            return
        
        # CSV 데이터 로드 (기존 코드와 동일)
        csv_data = {}
        csv_file = '국회의원_당선자_통합명부_20_21_22대.csv'
        
        if os.path.exists(csv_file):
            with open(csv_file, 'r', encoding='utf-8-sig') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    name = row.get('name', '').strip()
                    age = row.get('age', '').strip()
                    constituency = row.get('constituency', '').strip()
                    vote_percent = row.get('vote_percent', '').strip()
                    
                    try:
                        session_num = int(age) if age else None
                    except:
                        session_num = None
                    
                    vote_rate = None
                    if vote_percent and vote_percent != 'nan%':
                        try:
                            vote_rate = float(vote_percent.replace('%', ''))
                        except:
                            pass
                    
                    if name and session_num:
                        key = (name, session_num)
                        csv_data[key] = {
                            'constituency': constituency,
                            'vote_rate': vote_rate
                        }
            
            print(f"CSV에서 {len(csv_data)}개의 선거 데이터를 로드했습니다.")
        
        print(f"\n{'='*50}")
        print(f"국회의원 전체 정보 동기화 중...")
        print(f"{'='*50}")
        
        page = 1
        page_size = 1000
        total_processed = 0
        processed_members = set()
        while True:
            print(f"\n--- {page}페이지 처리 중 ---")
        
            url = f"{BASE_URL}/ALLNAMEMBER"
            params = {
                'KEY': API_KEY,
                'Type': 'xml',
                'pIndex': page,
                'pSize': page_size
            }
        
            try:
                response = requests.get(url, params=params, timeout=60)
                print(f"응답 상태: {response.status_code}")
        
                if response.status_code != 200:
                    print(f"HTTP 오류: {response.status_code}")
                    break
        
                if 'INFO-000' not in response.text:
                    print("API 오류 발생")
                    break
        
                root = ET.fromstring(response.content)
                rows = root.findall('.//row')
                print(f"이번 페이지에서 찾은 데이터: {len(rows)}개")
        
                if len(rows) == 0:
                    break
                
                for row in rows:
                    name = (row.findtext('HG_NM', '') or 
                            row.findtext('NAAS_NM', '') or 
                            row.findtext('KOR_NM', '')).strip()
                
                    party = (row.findtext('POLY_NM', '') or 
                             row.findtext('PLPT_NM', '') or 
                             row.findtext('PARTY_NM', '')).strip()
                    
                    birth_str = row.findtext('BIRDY_DT', '').strip()
                    birth_year = None
                    if birth_str and len(birth_str) >= 4:
                        try:
                            birth_year = int(birth_str[:4])
                        except:
                            birth_year = None
                    english_name = row.findtext('NAAS_EN_NM', '').strip()
                    
                    if not name:
                        continue

                    # 🔥 API 대수 정보로 먼저 필터링
                    api_sessions = row.findtext('GTELT_ERACO', '').strip()
                    if api_sessions:
                        print(f"   🔍 API 대수 정보: {name} - {api_sessions}")
                        
                        # 20, 21, 22대가 포함되어 있는지 확인
                        has_modern_session = False
                        if any(session in api_sessions for session in ['제20대', '제21대', '제22대', '20대', '21대', '22대']):
                            has_modern_session = True
                            print(f"   ✅ 현재 대수 포함: {name}")
                        
                        if not has_modern_session:
                            print(f"   ❌ 이전 대수만 포함: {name} ({api_sessions})")
                            continue
                    else:
                        print(f"   ⚠️ API 대수 정보 없음: {name} - 일단 통과")
                    
                    # 🔥 CSV 필터링을 Member 생성 전에 먼저 실행
                    matched_terms = [term for (csv_name, term) in csv_data.keys() 
                                     if csv_name == name and term in [20, 21, 22]]
                    if not matched_terms:
                        print(f"   ❌ CSV에 없음: {name} - 건너뜀")
                        continue  # CSV에 없으면 완전히 건너뜀
                    
                    # 중복 체크
                    member_key = (name, birth_str)
                    if member_key in processed_members:
                        print(f"   ⏭️ 이미 처리됨: {name} ({birth_str})")
                        continue

                    processed_members.add(member_key)
                    print(f"   ✅ API+CSV 일치: {name}")

                    # 이제 Member 생성/조회
                    member = Member.query.filter_by(name=name, birth_date=birth_str).first()
                    if not member:
                        member = Member(
                            name=name,
                            birth_date=birth_str,
                            english_name=english_name
                        )
                        db.session.add(member)
                        print(f"   ➕ 새 의원 생성: {name}")
                    else:
                        print(f"   🔄 기존 의원 업데이트: {name}")
                    
                    # 영문명 업데이트 (없는 경우에만)
                    if english_name and not member.english_name:
                        member.english_name = english_name
                                    
                    # 🔥 학력/경력 정보 수집 🔥
                    # API에서 제공되는 다양한 필드들 확인
                    # 🔥 학력/경력 정보 수집 🔥
                    education_data = []
                    career_data = []
                    info_collected = False
                    
                    # 🔥 0단계: 22대 API 데이터 직접 처리 (새로 추가)
                    if 22 in matched_terms:
                        raw_education = row.findtext('EDUCATION', '').strip()
                        raw_career = row.findtext('CAREER', '').strip()
                        
                        if raw_education or raw_career:
                            print(f"   📋 22대 API 데이터 분류 처리: {name}")
                            
                            # 전체 텍스트 결합
                            combined_text = ""
                            if raw_education:
                                combined_text += raw_education
                            if raw_career:
                                if combined_text:
                                    combined_text += "\n"
                                combined_text += raw_career
                            
                            # 🔥 분류 함수 적용
                            if combined_text.strip():
                                edu_items, career_items = parse_assembly_profile_text(combined_text, name)
                                
                                if edu_items:
                                    education_data.extend(edu_items)
                                    print(f"   📚 22대 학력 분류: {len(edu_items)}개 항목")
                                
                                if career_items:
                                    career_data.extend(career_items)
                                    print(f"   💼 22대 경력 분류: {len(career_items)}개 항목")
                                
                                info_collected = True
                    
                    # 1단계: 20, 21대는 헌정회 API 우선 시도
                    if not info_collected:
                        for term in matched_terms:
                            if term in [20, 21]:
                                print(f"   📚 {term}대 헌정회 API 시도: {name}")
                                edu_items, career_items = get_hunjunghoi_education_career(name, term)
                                if edu_items or career_items:
                                    education_data.extend(edu_items or [])
                                    career_data.extend(career_items or [])
                                    info_collected = True
                                    print(f"   ✅ {term}대 헌정회 성공: 학력 {len(edu_items or [])}개, 경력 {len(career_items or [])}개")
                                    break
                                else:
                                    print(f"   ❌ {term}대 헌정회에서 정보 없음")
                    
                    # 2단계: 22대 또는 헌정회 실패시 홈페이지 크롤링 시도
                    if not info_collected and english_name:
                        session_to_crawl = max(matched_terms) if matched_terms else 22
                        print(f"   🌐 {session_to_crawl}대 홈페이지 크롤링 시도: {name}")
                        
                        try:
                            edu_items, career_items, working_url, need_fallback = crawl_member_profile_with_detection(name, english_name, session_to_crawl)
                            
                            if edu_items or career_items:
                                education_data.extend(edu_items or [])
                                career_data.extend(career_items or [])
                                info_collected = True
                                
                                # 🔥 성공한 URL을 홈페이지로 저장
                                if working_url:
                                    member.homepage = working_url
                                    print(f"   🌐 실제 동작하는 홈페이지 URL 저장: {working_url}")
                                
                                print(f"   ✅ {session_to_crawl}대 홈페이지 성공: 학력 {len(edu_items or [])}개, 경력 {len(career_items or [])}개")
                            elif need_fallback:
                                print(f"   ⚠️ 홈페이지에서 메뉴 텍스트만 감지 - API fallback 진행")
                            else:
                                print(f"   ❌ {session_to_crawl}대 홈페이지에서 정보 없음")
                                
                        except Exception as e:
                            print(f"   ⚠️ 홈페이지 크롤링 실패: {str(e)} - API fallback 진행")
                            working_url = None
                            need_fallback = True
                    
                    # 3단계: BRF_HST 필드 사용 (API 데이터) - 크롤링 실패시 또는 메뉴 텍스트만 감지시
                    if not info_collected:
                        brf_hst = row.findtext('BRF_HST', '').strip()
                        if brf_hst:
                            print(f"   📋 BRF_HST 필드 사용 (fallback): {name}")
                            edu_items, career_items = parse_brf_hst_fallback(brf_hst, name)
                            if edu_items or career_items:
                                education_data.extend(edu_items or [])
                                career_data.extend(career_items or [])
                                info_collected = True
                                print(f"   ✅ BRF_HST fallback 성공: 학력 {len(edu_items or [])}개, 경력 {len(career_items or [])}개")
                            else:
                                print(f"   ❌ BRF_HST에서도 정보 추출 실패")
                    
                    # 정보 없는 경우 로그
                    if not info_collected:
                        print(f"   ❌ 학력/경력 정보 없음: {name}")
    
                    # 🔥 학력/경력 정보 업데이트 🔥
                    if education_data:
                        member.education = ','.join(education_data)
                        print(f"   📚 학력 업데이트: {len(education_data)}개 항목")
                    
                    if career_data:
                        member.career = ','.join(career_data)
                        print(f"   💼 경력 업데이트: {len(career_data)}개 항목")
                    
                    # 대수별 정보 처리
                    for term in matched_terms:
                        member.add_session(term)
        
                        # 최신 정보 업데이트 (가장 높은 대수 기준)
                        if term >= (member.current_session or 0):
                            # 기본 정보 업데이트
                            if party:
                                member.party = party
                            
                            member.gender = (row.findtext('SEX_GBN_NM', '') or 
                                           row.findtext('NTR_DIV', ''))
                            
                            # 연락처 정보 (기존 값이 없을 때만 업데이트)
                            phone = (row.findtext('TEL_NO', '') or 
                                    row.findtext('NAAS_TEL_NO', ''))
                            if phone and not member.phone:
                                member.phone = phone
                            
                            email = (row.findtext('E_MAIL', '') or 
                                    row.findtext('NAAS_EMAIL_ADDR', ''))
                            if email and not member.email:
                                member.email = email
                            
                            homepage = (row.findtext('HOMEPAGE', '') or 
                                       row.findtext('NAAS_HP_URL', ''))
                            if homepage and not member.homepage:
                                member.homepage = homepage
                            
                            # 사진 URL 업데이트 (더 최신 것 우선)
                            photo_url = (row.findtext('jpgLink', '') or 
                                        row.findtext('NAAS_PIC', ''))
                            if photo_url:
                                # 생년월일이 일치하는 경우에만 사진 업데이트
                                api_birth = row.findtext('BIRDY_DT', '').strip()
                                
                                if api_birth and member.birth_date == api_birth:
                                    member.photo_url = photo_url
                                    print(f"   📸 사진 URL 업데이트: {name} (생년월일 일치: {api_birth})")
                                elif not member.photo_url and not api_birth:
                                    # 생년월일 정보가 없고 기존 사진도 없는 경우만
                                    member.photo_url = photo_url
                                    print(f"   📸 사진 URL 업데이트: {name} (생년월일 정보 없음)")
                                else:
                                    print(f"   ⚠️ 사진 URL 건너뛰기: {name} (생년월일 불일치 또는 이미 사진 있음)")
                            
                            if birth_year:
                                member.age = birth_year
                            
                            # CSV 정보 (선거구, 득표율)
                            csv_key = (name, term)
                            if csv_key in csv_data:
                                district = csv_data[csv_key]['constituency']
                                vote_rate = csv_data[csv_key]['vote_rate']
                                member.district = district
                                member.vote_rate = vote_rate
                                
                                # 대수별 상세 정보 업데이트
                                member.update_session_details(term, party or '무소속', district, vote_rate)
        
                            print(f"처리: {name} ({term}대) - {party} (학력:{len(education_data)}, 경력:{len(career_data)})")
        
                    total_processed += 1
        
                db.session.commit()
                print(f"{page}페이지 완료: {len(rows)}명 처리")
        
                page += 1
                if len(rows) < page_size:
                    break
        
                time.sleep(2)
        
            except Exception as e:
                print(f"❌ {page}페이지 처리 중 오류: {str(e)}")
                import traceback
                traceback.print_exc()
                db.session.rollback()
                break
        
        print(f"\n🎉 동기화 완료: 총 {total_processed}명 처리됨")
        
        # 최종 통계
        total_members = Member.query.count()
        members_with_education = Member.query.filter(Member.education.isnot(None), Member.education != '').count()
        members_with_career = Member.query.filter(Member.career.isnot(None), Member.career != '').count()
        
        print(f"\n🎉 전체 동기화 완료!")
        print(f"총 의원 수: {total_members}명")
        print(f"학력 정보 있는 의원: {members_with_education}명")
        print(f"경력 정보 있는 의원: {members_with_career}명")
        
        # 학력/경력 정보가 부족한 의원들 확인
        missing_count = update_missing_education_career()
        if missing_count > 0:
            print(f"⚠️ {missing_count}명의 의원은 학력/경력 정보가 모두 부족합니다.")

def update_missing_education_career():
    """학력/경력 정보가 없는 의원들을 위한 추가 API 호출"""
    with app.app_context():
        print("\n=== 학력/경력 정보 보완 ===")
        
        # 🔥 수정: 학력 AND 경력이 모두 없는 의원들만 찾기
        members_without_info = Member.query.filter(
            and_(
                or_(Member.education.is_(None), Member.education == ''),
                or_(Member.career.is_(None), Member.career == '')
            )
        ).all()
        
        print(f"학력/경력 정보가 모두 부족한 의원: {len(members_without_info)}명")
        
        # 🔥 추가: 통계 정보
        total_members = Member.query.count()
        members_with_education = Member.query.filter(
            and_(Member.education.isnot(None), Member.education != '')
        ).count()
        members_with_career = Member.query.filter(
            and_(Member.career.isnot(None), Member.career != '')
        ).count()
        members_with_either = Member.query.filter(
            or_(
                and_(Member.education.isnot(None), Member.education != ''),
                and_(Member.career.isnot(None), Member.career != '')
            )
        ).count()
        
        print(f"\n📊 상세 통계:")
        print(f"전체 의원: {total_members}명")
        print(f"학력 정보 있음: {members_with_education}명")
        print(f"경력 정보 있음: {members_with_career}명")
        print(f"학력 또는 경력 중 하나 이상 있음: {members_with_either}명")
        print(f"학력/경력 모두 없음: {len(members_without_info)}명")
        
        if len(members_without_info) > 0:
            print("\n이러한 의원들은 API에서 정보를 제공하지 않을 수 있습니다:")
            
            # 몇 명의 예시만 출력
            for i, member in enumerate(members_without_info[:5]):
                print(f"{i+1}. {member.name} - 학력: {member.education or '없음'}, 경력: {member.career or '없음'}")
            
            if len(members_without_info) > 5:
                print(f"... 외 {len(members_without_info) - 5}명")
        
        return len(members_without_info)

def fix_duplicate_members():
    """기존 중복된 국회의원 데이터 정리"""
    with app.app_context():
        print("\n=== 중복된 국회의원 데이터 정리 ===")
        
        # 중복된 이름들 찾기
        duplicate_names = db.session.query(Member.name, func.count(Member.id).label('count'))\
            .group_by(Member.name)\
            .having(func.count(Member.id) > 1)\
            .all()
        
        print(f"중복된 의원 이름: {len(duplicate_names)}개")
        
        for name, count in duplicate_names:
            print(f"\n처리 중: {name} ({count}명 중복)")
            
            # 같은 이름의 모든 레코드 가져오기
            members = Member.query.filter_by(name=name).all()
            
            if len(members) <= 1:
                continue
            
            # 가장 완전한 데이터를 가진 레코드를 기준으로 병합
            primary_member = None
            merge_data = {'view_count': 0}
            
            # 모든 레코드에서 데이터 수집
            for member in members:
                # 첫 번째를 기본으로 설정
                if primary_member is None:
                    primary_member = member
                
                # 더 완전한 데이터 수집
                fields_to_merge = [
                    'birth_date', 'party', 'district', 'photo_url', 
                    'phone', 'email', 'homepage', 'sessions', 
                    'vote_rate', 'education', 'career'
                ]
                
                for field in fields_to_merge:
                    current_value = getattr(member, field)
                    if current_value and not merge_data.get(field):
                        merge_data[field] = current_value
                
                # 조회수는 합산
                merge_data['view_count'] += (member.view_count or 0)
            
            # 기본 레코드에 병합된 데이터 적용
            for key, value in merge_data.items():
                if hasattr(primary_member, key) and value:
                    setattr(primary_member, key, value)
            
            print(f"   📋 기본 레코드 업데이트 완료: {primary_member.id}")
            
            # 나머지 레코드들 삭제
            for member in members:
                if member.id != primary_member.id:
                    print(f"   🗑️ 중복 레코드 삭제: {member.id}")
                    db.session.delete(member)
        
        db.session.commit()
        print("\n✅ 중복 데이터 정리 완료!")
        
        # 최종 결과
        final_count = Member.query.count()
        print(f"정리 후 총 의원 수: {final_count}명")
        
        return len(duplicate_names)

def sync_bills_from_api():
    """국회 OpenAPI에서 법률안 정보 동기화 (20, 21, 22대)"""
    with app.app_context():
        print("\n=== 국회 OpenAPI에서 법률안 정보 가져오기 ===")
        
        # API 연결 테스트 먼저
        if not test_api_connection():
            print("API 연결 실패! 종료합니다.")
            return
        
        # 20, 21, 22대 법률안 각각 처리
        terms = [20, 21, 22]
        total_all_count = 0
        
        for term in terms:
            print(f"\n{'='*50}")
            print(f"{term}대 법률안 정보 동기화 중...")
            print(f"{'='*50}")
            
            term_count = 0
            page = 1
            page_size = 1000  # 최대 1000건
            
            while True:
                print(f"\n--- {term}대 법률안 {page}페이지 처리 중 ---")
                
                # 의안정보 API 사용
                url = f"{BASE_URL}/nzmimeepazxkubdpn"
                params = {
                    'KEY': API_KEY,
                    'Type': 'xml',
                    'pIndex': page,
                    'pSize': page_size,
                    'AGE': str(term)  # 대수 지정
                }
                
                try:
                    response = requests.get(url, params=params, timeout=60)
                    print(f"응답 상태: {response.status_code}")
                    
                    if response.status_code != 200:
                        print(f"HTTP 오류: {response.status_code}")
                        print(f"응답 내용: {response.text[:500]}")
                        break
                    
                    if 'INFO-000' not in response.text:
                        print(f"{term}대 법률안 API 오류 발생")
                        print(f"응답 내용: {response.text[:500]}")
                        break
                    
                    root = ET.fromstring(response.content)
                    
                    # 총 데이터 수 확인
                    total_count_elem = root.find('.//list_total_count')
                    total_available = total_count_elem.text if total_count_elem is not None else "알 수 없음"
                    print(f"{term}대 총 법률안 수: {total_available}")
                    
                    # 데이터 파싱
                    rows = root.findall('.//row')
                    print(f"이번 페이지에서 찾은 데이터: {len(rows)}개")
                    
                    if len(rows) == 0:
                        print(f"{term}대 더 이상 데이터가 없습니다.")
                        break
                    
                    page_count = 0
                    for row in rows:
                        # API 문서에 따른 필드명 사용
                        bill_id = row.findtext('BILL_ID', '').strip()
                        bill_no = row.findtext('BILL_NO', '').strip()
                        bill_name = row.findtext('BILL_NAME', '').strip()
                        committee = row.findtext('COMMITTEE', '').strip()
                        propose_dt = row.findtext('PROPOSE_DT', '').strip()
                        proc_result = row.findtext('PROC_RESULT', '').strip()
                        age = row.findtext('AGE', '').strip()
                        proposer = row.findtext('PROPOSER', '').strip()
                        member_list = row.findtext('MEMBER_LIST', '').strip()
                        detail_link = row.findtext('DETAIL_LINK', '').strip()
                        proc_result = row.findtext('PROC_RESULT', '').strip()
                        
                        # 필수 필드 확인
                        if not bill_name or not bill_id:
                            continue
                        
                        # 제안자 정리 (PROPOSER가 없으면 MEMBER_LIST에서 첫 번째 이름 추출)
                        if not proposer and member_list:
                            # 쉼표로 구분된 경우 첫 번째 이름만
                            proposer = member_list.split(',')[0].strip()
                        
                        # 기존 법률안 확인 (bill_id로 중복 체크)
                        existing_bill = Bill.query.filter_by(number=bill_id).first()
                        
                        if not existing_bill:
                            bill = Bill(
                                number=bill_id,
                                name=bill_name,
                                proposer=proposer,
                                propose_date=propose_dt,
                                committee=committee,
                                detail_link=detail_link,
                                assembly_result=proc_result,
                                view_count=0
                            )
                            db.session.add(bill)
                            print(f"새로 추가: {bill_name[:50]}... (제안자: {proposer})")
                        else:
                            # 기존 법률안 정보 업데이트
                            existing_bill.name = bill_name
                            existing_bill.proposer = proposer
                            existing_bill.propose_date = propose_dt
                            existing_bill.committee = committee
                            existing_bill.detail_link = detail_link
                            existing_bill.assembly_result = proc_result
                            print(f"업데이트: {bill_name[:50]}... (제안자: {proposer})")
                        
                        page_count += 1
                        term_count += 1
                        total_all_count += 1
                        
                        if page_count % 100 == 0:
                            print(f"{term}대 처리 중... ({term_count}건)")
                    
                    # 페이지별 커밋
                    db.session.commit()
                    print(f"{term}대 {page}페이지 완료: {page_count}건 처리")
                    
                    # 다음 페이지로
                    page += 1
                    
                    # 데이터가 page_size보다 적으면 마지막 페이지
                    if len(rows) < page_size:
                        print(f"{term}대 마지막 페이지입니다.")
                        break
                    
                    # API 부하 방지
                    time.sleep(2)
                    
                    # 안전을 위해 최대 10페이지까지만
                    if page > 10:
                        print(f"안전을 위해 {term}대는 10페이지까지만 처리합니다.")
                        break
                    
                except Exception as e:
                    print(f"❌ {term}대 {page}페이지 처리 중 오류: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    db.session.rollback()
                    break
            
            print(f"\n✅ {term}대 완료: {term_count}건 처리")
            
            # 각 대수 처리 후 잠시 대기
            if term < 22:  # 마지막 대수가 아니면
                print("다음 대수 처리를 위해 3초 대기...")
                time.sleep(3)
        
        print(f"\n🎉 전체 법률안 동기화 완료!")
        print(f"총 {total_all_count}건의 법률안 정보를 동기화했습니다.")
        
        # 최종 통계
        total_bills = Bill.query.count()
        print(f"데이터베이스 총 법률안: {total_bills}건")

def sync_all_data():
    """국회의원 + 법률안 전체 동기화"""
    print("\n🚀 전체 데이터 동기화 시작!")
    
    # 1. 국회의원 동기화
    print("\n1️⃣ 국회의원 데이터 동기화...")
    sync_members_from_api()
    
    print("\n잠시 대기 중...")
    time.sleep(5)
    
    # 2. 법률안 동기화
    print("\n2️⃣ 법률안 데이터 동기화...")
    sync_bills_from_api()
    
    print("\n🎉 전체 동기화 완료!")

def cleanup_and_sync():
    """중복 정리 후 전체 동기화"""
    print("\n🧹 데이터 정리 및 동기화 시작!")
    
    # 1. 기존 중복 정리
    print("\n1️⃣ 중복 데이터 정리...")
    duplicate_count = fix_duplicate_members()
    
    if duplicate_count > 0:
        print(f"✅ {duplicate_count}개의 중복 항목을 정리했습니다.")
    
    # 2. 전체 동기화
    print("\n2️⃣ 전체 데이터 동기화...")
    sync_all_data()
    
    print("\n🎉 정리 및 동기화 완료!")
