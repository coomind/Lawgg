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
def classify_education_career(text_data):
    """텍스트 데이터를 학력과 경력으로 분류 - 개선 버전"""
    education_data = []
    career_data = []
    
    # 입력 데이터 정리
    if isinstance(text_data, str):
        # 다양한 구분자로 분리 시도
        separators = ['\n', '/', '·', '◦', '•', ',', ';']
        items = [text_data]
        
        for sep in separators:
            if sep in text_data:
                items = [item.strip() for item in text_data.split(sep) if item.strip() and len(item.strip()) > 2]
                break
    else:
        items = text_data if isinstance(text_data, list) else [str(text_data)]
    
    print(f"    📋 분류할 항목들 ({len(items)}개): {items[:3]}..." if len(items) > 3 else f"    📋 분류할 항목들: {items}")
    
    for item in items:
        item = item.strip()
        if len(item) < 3:
            continue
            
        # 🎓 학력 키워드 (강화)
        education_keywords = [
            '대학교', '대학원', '고등학교', '중학교', '초등학교', '대학', '고교',
            '졸업', '수료', '입학', '전공', '학부', '학과', '석사', '박사', '학위',
            '서울대', '연세대', '고려대', '성균관대', '한양대', '중앙대', '경희대',
            '이화여대', '숙명여대', '동국대', '홍익대', '건국대', '국민대'
        ]
        
        # 💼 경력 키워드 (강화)
        career_keywords = [
            '대표', '사장', '회장', '이사', '부장', '과장', '팀장', '소장', '원장',
            '의원', '장관', '차관', '국장', '실장', '센터장', '위원장', '이사장',
            '변호사', '의사', '교수', '연구원', '기자', '작가', '판사', '검사',
            '시장', '도지사', '구청장', '군수', '국회의원', '공무원',
            '근무', '재직', '활동', '역임', '담당', '맡음', '봉사',
            '회사', '기업', '법무법인', '병원', '방송', '신문', '연구소', '재단'
        ]
        
        # 학력/경력 판단
        is_education = any(keyword in item for keyword in education_keywords)
        is_career = any(keyword in item for keyword in career_keywords)
        
        if is_education and not is_career:
            education_data.append(item)
            print(f"      🎓 학력: {item}")
        elif is_career and not is_education:
            career_data.append(item)
            print(f"      💼 경력: {item}")
        elif is_education and is_career:
            # 학력 키워드가 더 강하면 학력으로
            education_score = sum(1 for kw in ['졸업', '전공', '학과', '학부', '대학'] if kw in item)
            if education_score > 0:
                education_data.append(item)
                print(f"      🎓 학력 (우선): {item}")
            else:
                career_data.append(item)
                print(f"      💼 경력 (우선): {item}")
        else:
            # 기본적으로 경력으로 분류
            career_data.append(item)
            print(f"      💼 경력 (기본): {item}")
    
    return education_data, career_data
    
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
                    if not name:
                        continue
                    
                    # 🔥 학력/경력 정보 수집 🔥
                    # API에서 제공되는 다양한 필드들 확인
                    # 🔥 BRF_HST 필드에서 학력/경력 정보 추출 🔥
                    brf_hst = row.findtext('BRF_HST', '').strip()

                    if brf_hst:
                        print(f"   📋 {name} BRF_HST: {brf_hst[:100]}...")
                        
                        # 🔥 공통 분류 함수 사용 🔥
                        education_data, career_data = classify_education_career(brf_hst)
                    else:
                        education_data = []
                        career_data = []
                                        
                    # 생년월일에서 출생연도 추출
                    birth_year = None
                    if birth_str and len(birth_str) >= 4:
                        try:
                            birth_year = int(birth_str[:4])
                        except:
                            pass
                    
                    age = datetime.now().year - birth_year if birth_year else None

                    # CSV에서 매칭되는 대수들 찾기
                    matched_terms = [term for (csv_name, term) in csv_data.keys() 
                                     if csv_name == name and term in [20, 21, 22]]
                    if not matched_terms or (age is not None and age > 90):
                        continue  # CSV에 없으면 건너뜀

                    # 🔥 중복 방지 로직 개선 (김문수 중복 문제 해결) 🔥
                    # 1단계: 이름만으로 먼저 찾기
                    existing_member = Member.query.filter_by(name=name).first()
                    
                    if existing_member:
                        # 기존 의원이 있으면 업데이트
                        member = existing_member
                        print(f"🔄 기존 의원 업데이트: {name}")
                        
                        # 생년월일이 비어있거나 다르면 업데이트
                        if not member.birth_date and birth_str:
                            member.birth_date = birth_str
                            print(f"   📅 생년월일 업데이트: {birth_str}")
                        elif member.birth_date != birth_str and birth_str:
                            print(f"   ⚠️ 생년월일 불일치: 기존({member.birth_date}) vs 새로운({birth_str})")
                            # 더 완전한 데이터를 선택 (길이가 더 긴 것)
                            if len(birth_str) > len(member.birth_date or ''):
                                member.birth_date = birth_str
                                print(f"   📅 더 완전한 생년월일로 업데이트: {birth_str}")
                    else:
                        # 새로운 의원 생성
                        member = Member(
                            name=name, 
                            birth_date=birth_str, 
                            view_count=0
                        )
                        db.session.add(member)
                        print(f"✨ 신규 의원: {name}")
                    
                    # 🔥 학력/경력 정보 업데이트 🔥
                    if education_data:
                        # 기존 데이터와 병합
                        existing_education = member.education.split(',') if (member.education and member.education.strip()) else []
                        all_education = existing_education + education_data
                        
                        # 중복 제거
                        unique_education = []
                        for item in all_education:
                            if item not in unique_education:
                                unique_education.append(item)
                        
                        member.education = ','.join(unique_education)
                        print(f"   📚 학력 업데이트: {len(unique_education)}개 항목")
                    
                    if career_data:
                        # 기존 데이터와 병합
                        existing_career = member.career.split(',') if (member.career and member.career.strip()) else []
                        all_career = existing_career + career_data
                        
                        # 중복 제거
                        unique_career = []
                        for item in all_career:
                            if item not in unique_career:
                                unique_career.append(item)
                        
                        member.career = ','.join(unique_career)
                        print(f"   💼 경력 업데이트: {len(unique_career)}개 항목")
                    
                    # 대수별 정보 처리
                    for term in matched_terms:
                        member.add_session(term)
        
                        # 최신 정보 업데이트 (가장 높은 대수 기준)
                        if term >= (member.current_session or 0):
                            # 더 최신 대수일 때만 기본 정보 업데이트
                            if term > (member.current_session or 0):
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
                                if not member.photo_url or term > (member.current_session or 0):
                                    member.photo_url = photo_url
                                    print(f"   📸 사진 URL 업데이트: {name}")
                            
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
        
                time.sleep(1)
        
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


def supplement_missing_education_career():
    """학력/경력이 없는 의원들을 헌정회 API로 보완 - 수정 버전"""
    with app.app_context():
        print("\n=== 학력/경력 누락 의원 헌정회 API로 보완 ===")
        
        # 학력/경력이 없는 의원들 찾기
        members_without_info = Member.query.filter(
            or_(
                Member.education.is_(None),
                Member.education == '',
                Member.career.is_(None), 
                Member.career == ''
            )
        ).all()
        
        print(f"학력/경력 정보가 없는 의원: {len(members_without_info)}명")
        
        updated_count = 0
        
        for i, member in enumerate(members_without_info):
            print(f"\n🔍 [{i+1}/{len(members_without_info)}] {member.name} 헌정회 API 조회 중...")
            
            url = f"{BASE_URL}/nprlapfmaufmqytet"
            params = {
                'KEY': API_KEY,
                'Type': 'xml',
                'pIndex': 1,
                'pSize': 100,
                'NAME': member.name
            }
            
            try:
                response = requests.get(url, params=params, timeout=15)
                
                if response.status_code == 200 and 'INFO-000' in response.text:
                    root = ET.fromstring(response.content)
                    rows = root.findall('.//row')
                    
                    for row in rows:
                        api_name = row.findtext('NAME', '').strip()
                        
                        if api_name == member.name:
                            print(f"   ✅ {member.name} 헌정회 데이터 발견!")
                            
                            # HAK 필드에서 학력/경력 정보 추출
                            hak_field = row.findtext('HAK', '').strip()
                            
                            if hak_field and len(hak_field) > 10:  # 의미있는 데이터만
                                print(f"      📋 HAK 필드: {hak_field[:100]}...")
                                
                                # 분류 함수 사용
                                education_data, career_data = classify_education_career(hak_field)
                                
                                # 🔥 데이터베이스에 실제 저장 🔥
                                if education_data and (not member.education or member.education.strip() == ''):
                                    member.education = ','.join(education_data)
                                    print(f"   📚 학력 저장: {len(education_data)}개 항목")
                                
                                if career_data and (not member.career or member.career.strip() == ''):
                                    member.career = ','.join(career_data)
                                    print(f"   💼 경력 저장: {len(career_data)}개 항목")
                                
                                if education_data or career_data:
                                    updated_count += 1
                                    # 🔥 즉시 커밋해서 확실히 저장 🔥
                                    db.session.commit()
                                    print(f"   ✅ {member.name} 정보 저장 완료!")
                            else:
                                print(f"      ❌ HAK 필드 데이터 부족: {hak_field}")
                            
                            break
                
                time.sleep(0.5)  # API 부하 방지
                
            except Exception as e:
                print(f"❌ {member.name} 처리 중 오류: {str(e)}")
                continue
        
        print(f"\n🎉 헌정회 API 보완 완료!")
        print(f"총 {updated_count}명의 의원 학력/경력 정보 추가됨")
        
        return updated_count
        
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
    """국회 OpenAPI에서 법률안 정보 동기화 (20, 21, 22대) - 최적화 버전"""
    with app.app_context():
        print("\n=== 국회 OpenAPI에서 법률안 정보 가져오기 (최적화) ===")
        
        if not test_api_connection():
            print("API 연결 실패! 종료합니다.")
            return
        
        terms = [20, 21, 22]
        total_all_count = 0
        
        for term in terms:
            print(f"\n{'='*50}")
            print(f"{term}대 법률안 정보 동기화 중...")
            print(f"{'='*50}")
            
            term_count = 0
            page = 1
            page_size = 1000  # 최대 1000건
            batch_bills = []  # 배치 처리용 리스트
            
            while True:
                print(f"\n--- {term}대 법률안 {page}페이지 처리 중 ---")
                
                url = f"{BASE_URL}/nzmimeepazxkubdpn"
                params = {
                    'KEY': API_KEY,
                    'Type': 'xml',
                    'pIndex': page,
                    'pSize': page_size,
                    'AGE': str(term)
                }
                
                try:
                    response = requests.get(url, params=params, timeout=30)  # 타임아웃 단축
                    
                    if response.status_code != 200:
                        print(f"HTTP 오류: {response.status_code}")
                        break
                    
                    if 'INFO-000' not in response.text:
                        print(f"{term}대 법률안 API 오류 발생")
                        break
                    
                    root = ET.fromstring(response.content)
                    rows = root.findall('.//row')
                    print(f"이번 페이지에서 찾은 데이터: {len(rows)}개")
                    
                    if len(rows) == 0:
                        break
                    
                    # 🚀 배치 처리 최적화 🚀
                    page_bills = []
                    
                    for row in rows:
                        bill_id = row.findtext('BILL_ID', '').strip()
                        bill_name = row.findtext('BILL_NAME', '').strip()
                        committee = row.findtext('COMMITTEE', '').strip()
                        propose_dt = row.findtext('PROPOSE_DT', '').strip()
                        proposer = row.findtext('PROPOSER', '').strip()
                        member_list = row.findtext('MEMBER_LIST', '').strip()
                        detail_link = row.findtext('DETAIL_LINK', '').strip()
                        
                        if not bill_name or not bill_id:
                            continue
                        
                        if not proposer and member_list:
                            proposer = member_list.split(',')[0].strip()
                        
                        # 🔥 기존 법률안 확인을 한 번에 처리 🔥
                        page_bills.append({
                            'bill_id': bill_id,
                            'bill_name': bill_name,
                            'proposer': proposer,
                            'propose_dt': propose_dt,
                            'committee': committee,
                            'detail_link': detail_link
                        })
                    
                    # 🚀 배치로 기존 법률안 확인 🚀
                    existing_bill_ids = [bill['bill_id'] for bill in page_bills]
                    existing_bills = Bill.query.filter(Bill.number.in_(existing_bill_ids)).all()
                    existing_bill_numbers = {bill.number for bill in existing_bills}
                    
                    # 새로운 법률안만 추가
                    new_bills = []
                    update_bills = []
                    
                    for bill_data in page_bills:
                        if bill_data['bill_id'] not in existing_bill_numbers:
                            # 새로 추가
                            new_bill = Bill(
                                number=bill_data['bill_id'],
                                name=bill_data['bill_name'],
                                proposer=bill_data['proposer'],
                                propose_date=bill_data['propose_dt'],
                                committee=bill_data['committee'],
                                detail_link=bill_data['detail_link'],
                                view_count=0
                            )
                            new_bills.append(new_bill)
                        else:
                            # 기존 법률안 업데이트 정보 저장
                            update_bills.append(bill_data)
                    
                    # 🚀 대량 삽입 🚀
                    if new_bills:
                        db.session.add_all(new_bills)
                        print(f"   ✨ 새로 추가: {len(new_bills)}건")
                    
                    # 🚀 기존 법률안 업데이트 🚀
                    if update_bills:
                        for bill_data in update_bills:
                            existing_bill = next((b for b in existing_bills if b.number == bill_data['bill_id']), None)
                            if existing_bill:
                                existing_bill.name = bill_data['bill_name']
                                existing_bill.proposer = bill_data['proposer']
                                existing_bill.propose_date = bill_data['propose_dt']
                                existing_bill.committee = bill_data['committee']
                                existing_bill.detail_link = bill_data['detail_link']
                        print(f"   🔄 업데이트: {len(update_bills)}건")
                    
                    term_count += len(page_bills)
                    total_all_count += len(page_bills)
                    
                    # 🚀 페이지별 커밋 (배치 처리) 🚀
                    db.session.commit()
                    print(f"{term}대 {page}페이지 완료: {len(page_bills)}건 처리 (총 {term_count}건)")
                    
                    page += 1
                    
                    if len(rows) < page_size:
                        break
                    
                    # 🚀 API 대기시간 단축 🚀
                    time.sleep(0.5)  # 2초 → 0.5초
                    
                    # 🚀 페이지 제한 제거 (필요시) 🚀
                    # if page > 30:  # 10 → 30으로 확장 또는 제거
                    #     break
                    
                except Exception as e:
                    print(f"❌ {term}대 {page}페이지 처리 중 오류: {str(e)}")
                    db.session.rollback()
                    break
            
            print(f"\n✅ {term}대 완료: {term_count}건 처리")
            time.sleep(1)  # 3초 → 1초
        
        print(f"\n🎉 전체 법률안 동기화 완료!")
        print(f"총 {total_all_count}건의 법률안 정보를 동기화했습니다.")
        
        # 최종 통계
        total_bills = Bill.query.count()
        print(f"데이터베이스 총 법률안: {total_bills}건")

def sync_all_data():
    """국회의원 + 법률안 전체 동기화"""
    print("\n🚀 전체 데이터 동기화 시작!")
    
    # 1. 국회의원 기본 정보 동기화 (ALLNAMEMBER API)
    print("\n1️⃣ 국회의원 기본 정보 동기화...")
    sync_members_from_api()
    
    print("\n잠시 대기 중...")
    time.sleep(3)
    
    # 2. 학력/경력 누락 의원들 헌정회 API로 보완
    print("\n2️⃣ 학력/경력 누락 정보 보완...")
    supplement_missing_education_career()
    
    print("\n잠시 대기 중...")
    time.sleep(3)
    
    # 3. 법률안 동기화
    print("\n3️⃣ 법률안 데이터 동기화...")
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
