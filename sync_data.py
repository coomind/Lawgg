#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Law.GG 데이터 동기화 스크립트 - 디버깅 버전
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
from sqlalchemy import func, or_

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
        
# sync_data.py 수정 - 학력/경력 정보 수집 개선
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
                        # 🔥 새로운 파싱 함수 사용
                        return parse_assembly_profile_text(hak_data, name)
        
        return None, None
        
    except Exception as e:
        print(f"   ❌ 헌정회 API 오류: {str(e)}")
        return None, None

def crawl_member_profile_with_detection(member_name, english_name, session_num=22):
    """홈페이지 크롤링 with 메뉴 텍스트 감지 및 fallback"""
    try:
        if not english_name:
            print(f"   ❌ 영문명 없음: {member_name}")
            return None, None, True  # fallback 필요 표시 추가
            
        # 띄어쓰기 제거하고 대문자로
        clean_english_name = english_name.replace(' ', '').upper()
        url = f"https://www.assembly.go.kr/members/{session_num}nd/{clean_english_name}"
        
        print(f"   🌐 크롤링 시도: {url}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, timeout=30, headers=headers)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            page_text = soup.get_text()
            
            # 🔥 핵심: 메뉴 텍스트만 크롤링된 경우 감지
            if is_menu_text_only(page_text, member_name):
                print(f"   ⚠️ 메뉴 텍스트만 감지됨: {member_name} - API fallback 필요")
                return None, None, True  # fallback 필요 표시
            
            # 정상적인 페이지인 경우 파싱
            education_items, career_items = parse_assembly_profile_text(page_text, member_name)
            
            if education_items or career_items:
                print(f"   ✅ 크롤링 성공: {member_name} - 학력:{len(education_items or [])}개, 경력:{len(career_items or [])}개")
                return education_items, career_items, False
            else:
                print(f"   ⚠️ 파싱 실패: {member_name} - API fallback 필요")
                return None, None, True  # fallback 필요
        else:
            print(f"   ❌ HTTP {response.status_code}: {url}")
            return None, None, True  # fallback 필요
        
    except requests.exceptions.Timeout:
        print(f"   ⏰ 타임아웃: {member_name}")
        return None, None, True  # fallback 필요
    except requests.exceptions.RequestException as e:
        print(f"   🚫 요청 오류: {member_name} - {str(e)}")
        return None, None, True  # fallback 필요
    except Exception as e:
        print(f"   ❌ 크롤링 오류 ({member_name}): {str(e)}")
        return None, None, True  # fallback 필요

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
        '대학교', '고등학교', '졸업', '수료',
        '위원장', '장관', '청장', '교수', '변호사', '판사'
    ]
    
    # 메뉴 텍스트 개수 세기
    menu_count = sum(1 for indicator in menu_indicators if indicator in page_text)
    
    # 실제 컨텐츠 개수 세기
    content_count = sum(1 for indicator in real_content_indicators if indicator in page_text)
    
    # 🔥 판단 로직
    # 1. 메뉴 텍스트가 3개 이상이고 실제 컨텐츠가 거의 없으면 메뉴만 크롤링된 것
    if menu_count >= 3 and content_count <= 1:
        return True
    
    # 2. 텍스트가 매우 짧고 메뉴 텍스트만 있는 경우
    if len(page_text.strip()) < 500 and menu_count >= 2:
        return True
    
    # 3. "외 XX개" 패턴이 있고 실제 정보가 없는 경우 (강경숙 의원 케이스)
    import re
    if re.search(r'외\s*\d+개', page_text) and content_count == 0:
        return True
    
    return False
    
def parse_assembly_profile_text(text, member_name):
    """국회 홈페이지 텍스트에서 학력/경력 파싱 - 모든 패턴 지원 (개선된 버전)"""
    education_items = []
    career_items = []
    
    try:
        # 전처리: 줄바꿈 정리
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # 🔥 패턴별 섹션 찾기 (이 부분이 빠져있었음!)
        patterns = [
            # 패턴 1: ■ 학력, ■ 경력
            {
                'education_markers': ['■ 학력', '■학력', '■ 학력:', '■학력:', '■ 주요학력', '■주요학력'],
                'career_markers': ['■ 경력', '■경력', '■ 경력:', '■경력:', '■ 주요경력', '■주요경력', '■ 약력', '■약력']
            },
            # 패턴 2: □ 학력, □ 경력  
            {
                'education_markers': ['□ 학력', '□학력', '□ 주요학력', '□주요학력'],
                'career_markers': ['□ 경력', '□경력', '□ 주요경력', '□주요경력', '□ 약력', '□약력', '□ 주요 약력', '□주요 약력']
            },
            # 패턴 3: [학력], [경력]
            {
                'education_markers': ['[학력사항]', '[학력]', '[ 학력 ]', '[주요학력]', '[주요 학력]'],
                'career_markers': ['[경력사항]', '[경력]', '[ 경력 ]', '[약력사항]', '[약력]', '[ 약력 ]', '[주요경력]', '[주요 경력]']
            },
            # 패턴 4: ○ 학력, ○ 경력
            {
                'education_markers': ['○ 학력', '○학력', '○ 주요학력', '○주요학력'],
                'career_markers': ['○ 경력', '○경력', '○ 약력', '○약력', '○ 주요경력', '○주요경력', '○ 주요 경력', '○주요 경력']
            },
            # 패턴 5: < > 마크
            {
                'education_markers': ['<학력사항>', '<학력>', '<주요학력>', '<주요 학력>'],
                'career_markers': ['<경력사항>', '<경력>', '<약력사항>', '<약력>', '<주요경력>', '<주요 경력>']
            },
            # 패턴 6: ▶ 화살표
            {
                'education_markers': ['▶학력', '▶ 학력', '▶주요학력', '▶ 주요학력'],
                'career_markers': ['▶경력', '▶ 경력', '▶약력', '▶ 약력', '▶주요경력', '▶ 주요경력']
            },
            # 패턴 7: ** 마크다운
            {
                'education_markers': ['**학력', '** 학력', '**주요학력', '** 주요학력'],
                'career_markers': ['**경력', '** 경력', '**약력', '** 약력', '**주요경력', '** 주요경력']
            },
            # 패턴 8: * 학력, * 경력
            {
                'education_markers': ['* 학력', '*학력'],
                'career_markers': ['* 경력', '*경력', '* 약력', '*약력']
            }
        ]
        
        # 각 패턴 시도
        for pattern in patterns:
            education_sections = find_sections(text, pattern['education_markers'])
            career_sections = find_sections(text, pattern['career_markers'])
            
            if education_sections or career_sections:
                print(f"   📋 패턴 매치: {pattern['education_markers'][0]} / {pattern['career_markers'][0]}")
                
                # 학력 섹션 파싱
                for section in education_sections:
                    items = extract_items_from_section(section, is_education=True)
                    education_items.extend(items)
                
                # 경력 섹션 파싱
                for section in career_sections:
                    items = extract_items_from_section(section, is_education=False)
                    career_items.extend(items)
                
                break
        
        # 패턴이 없는 경우: 전체 텍스트에서 키워드로 분류
        if not education_items and not career_items:
            print(f"   🔍 패턴 없음, 키워드 분류 시도: {member_name}")
            education_items, career_items = classify_by_keywords(text)
        
        # 중복 제거
        education_items = remove_duplicates_preserve_order(education_items)
        career_items = remove_duplicates_preserve_order(career_items)
        
        print(f"   📚 파싱 결과: {member_name} - 학력:{len(education_items)}개, 경력:{len(career_items)}개")
        return education_items, career_items
        
    except Exception as e:
        print(f"   ❌ 텍스트 파싱 오류: {str(e)}")
        return None, None

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
                    member_key = (name, birth_str)
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
                    
                    # processed_members에 추가
                    processed_members.add(member_key)
                    
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
                    
                    # 🔥 CSV 필터링 (기존 코드 그대로 유지!)
                    matched_terms = [term for (csv_name, term) in csv_data.keys() 
                                     if csv_name == name and term in [20, 21, 22]]
                    if not matched_terms:
                        continue  # CSV에 없으면 건너뜀
                    
                    print(f"   ✅ API+CSV 일치: {name}")
                    
                    
                    if member_key in processed_members:
                        print(f"   ⏭️ 이미 처리됨: {name} ({birth_str})")
                        continue
                                    
                    # 🔥 학력/경력 정보 수집 🔥
                    # API에서 제공되는 다양한 필드들 확인
                    education_data = []
                    career_data = []
                    info_collected = False
                    
                    # 1단계: 20, 21대는 헌정회 API 우선 시도
                    for term in matched_terms:
                        if term in [20, 21] and not info_collected:
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
                    
                    # 2단계: 22대 또는 헌정회 실패시 홈페이지 크롤링 시도 (메뉴 텍스트 감지 포함)
                    if not info_collected and english_name:
                        session_to_crawl = max(matched_terms) if matched_terms else 22
                        print(f"   🌐 {session_to_crawl}대 홈페이지 크롤링 시도: {name}")
                        
                        try:
                            edu_items, career_items, need_fallback = crawl_member_profile_with_detection(name, english_name, session_to_crawl)
                            
                            if edu_items or career_items:
                                education_data.extend(edu_items or [])
                                career_data.extend(career_items or [])
                                info_collected = True
                                print(f"   ✅ {session_to_crawl}대 홈페이지 성공: 학력 {len(edu_items or [])}개, 경력 {len(career_items or [])}개")
                            elif need_fallback:
                                print(f"   ⚠️ 홈페이지에서 메뉴 텍스트만 감지 - API fallback 진행")
                                # 즉시 3단계로 이동
                            else:
                                print(f"   ❌ {session_to_crawl}대 홈페이지에서 정보 없음")
                        except Exception as e:
                            print(f"   ⚠️ 홈페이지 크롤링 실패: {str(e)} - API fallback 진행")
                            need_fallback = True
                    
                    # 3단계: BRF_HST 필드 사용 (API 데이터) - 크롤링 실패시 또는 메뉴 텍스트만 감지시
                    if not info_collected:
                        brf_hst = row.findtext('BRF_HST', '').strip()
                        if brf_hst:
                            print(f"   📋 BRF_HST 필드 사용 (fallback): {name}")
                            edu_items, career_items = parse_brf_hst_fallback(brf_hst, name)  # 🔥 전용 함수 사용
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

                    member = Member.query.filter_by(name=name, birth_date=birth_str).first()
                    if not member:
                        member = Member(name=name, birth_date=birth_str, english_name=english_name)
                        db.session.add(member)

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
            print(f"⚠️ {missing_count}명의 의원은 학력/경력 정보가 부족합니다.")


def debug_member_api_fields():
    """국회의원 API 응답 필드 디버깅"""
    with app.app_context():
        print("\n=== 국회의원 API 필드 디버깅 ===")
        
        url = f"{BASE_URL}/ALLNAMEMBER"
        params = {
            'KEY': API_KEY,
            'Type': 'xml',
            'pIndex': 1,
            'pSize': 5  # 처음 5명만 확인
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200 and 'INFO-000' in response.text:
                root = ET.fromstring(response.content)
                rows = root.findall('.//row')
                
                if rows:
                    first_row = rows[0]
                    name = (first_row.findtext('HG_NM', '') or 
                           first_row.findtext('NAAS_NM', '') or 
                           first_row.findtext('KOR_NM', '')).strip()
                    
                    print(f"\n첫 번째 의원: {name}")
                    print("="*50)
                    
                    # 모든 필드 출력
                    for child in first_row:
                        field_name = child.tag
                        field_value = child.text
                        
                        if field_value and field_value.strip():
                            print(f"{field_name}: {field_value}")
                    
                    print("\n학력/경력 관련 가능성 있는 필드들:")
                    print("="*50)
                    
                    career_keywords = ['SCH', 'EDUCATION', 'CAREER', 'HIS', 'WORK', 'JOB', 'ACADEMIC', 'PROFILE', 'EXPERIENCE']
                    
                    for child in first_row:
                        field_name = child.tag
                        field_value = child.text
                        
                        if field_value and field_value.strip():
                            if any(keyword in field_name.upper() for keyword in career_keywords):
                                print(f"🎯 {field_name}: {field_value}")
                
        except Exception as e:
            print(f"디버깅 중 오류: {str(e)}")


def update_missing_education_career():
    """학력/경력 정보가 없는 의원들을 위한 추가 API 호출"""
    with app.app_context():
        print("\n=== 학력/경력 정보 보완 ===")
        
        # 학력/경력 정보가 없는 의원들 찾기
        members_without_info = Member.query.filter(
            or_(  # 기존: db.or_() → 변경: or_()
                Member.education.is_(None),
                Member.education == '',
                Member.career.is_(None), 
                Member.career == ''
            )
        ).all()
        
        print(f"학력/경력 정보가 부족한 의원: {len(members_without_info)}명")
        
        if len(members_without_info) > 0:
            print("이러한 의원들은 API에서 학력/경력 정보를 제공하지 않을 수 있습니다.")
            print("또는 다른 API 엔드포인트를 시도해볼 수 있습니다.")
            
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
