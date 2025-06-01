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
        
def sync_members_from_api():
    """국회 OpenAPI에서 국회의원 정보 동기화 (20, 21, 22대)"""
    with app.app_context():
        print("\n=== 국회 OpenAPI에서 국회의원 정보 가져오기 ===")
        
        # API 연결 테스트 먼저
        if not test_api_connection():
            print("API 연결 실패! 종료합니다.")
            return
        
        # CSV 데이터 로드 (기존 코드 그대로)
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
        else:
            print("CSV 파일을 찾을 수 없습니다. API 데이터만 사용합니다.")
        
        # 20, 21, 22대 국회의원 각각 처리
        terms = [20, 21, 22]
        total_all_count = 0
        
        for term in terms:
            print(f"\n{'='*50}")
            print(f"{term}대 국회의원 정보 동기화 중...")
            print(f"{'='*50}")
            
            term_count = 0
            page = 1
            page_size = 1000  # 최대 1000건
            
            while True:
                print(f"\n--- {term}대 {page}페이지 처리 중 ---")
                
                url = f"{BASE_URL}/ALLNAMEMBER"
                params = {
                    'KEY': API_KEY,
                    'Type': 'xml',
                    'pIndex': page,
                    'pSize': page_size,
                    'UNIT_CD': f'{term:02d}'  # 20, 21, 22
                }
                
                try:
                    response = requests.get(url, params=params, timeout=60)
                    print(f"응답 상태: {response.status_code}")
                    
                    if response.status_code != 200:
                        print(f"HTTP 오류: {response.status_code}")
                        break
                    
                    root = ET.fromstring(response.content)
                    
                    # 결과 확인
                    if 'INFO-000' not in response.text:
                        print(f"{term}대 API 오류 발생")
                        break
                    
                    # 총 데이터 수 확인
                    total_count_elem = root.find('.//list_total_count')
                    total_available = total_count_elem.text if total_count_elem is not None else "알 수 없음"
                    print(f"{term}대 총 데이터 수: {total_available}")
                    
                    # 데이터 파싱
                    rows = root.findall('.//row')
                    print(f"이번 페이지에서 찾은 데이터: {len(rows)}개")
                    
                    if len(rows) == 0:
                        print(f"{term}대 더 이상 데이터가 없습니다.")
                        break
                    
                    page_count = 0
                    for row in rows:
                        # 다양한 필드명 시도 (API 버전에 따라 다를 수 있음)
                        name = (row.findtext('HG_NM', '') or 
                               row.findtext('NAAS_NM', '') or 
                               row.findtext('KOR_NM', ''))
                        
                        party = (row.findtext('POLY_NM', '') or 
                                row.findtext('PLPT_NM', '') or 
                                row.findtext('PARTY_NM', ''))
                        
                        if not name:
                            continue
                        
                        # 기존 의원 확인 또는 생성
                        member = Member.query.filter_by(name=name, session_num=term).first()
                        
                        if not member:
                            member = Member(
                                name=name,
                                session_num=term,
                                view_count=0
                            )
                            db.session.add(member)
                            print(f"새로 추가: {name} ({term}대)")
                        else:
                            print(f"업데이트: {name} ({term}대)")
                        
                        # 정보 업데이트
                        member.party = party or '무소속'
                        member.gender = (row.findtext('SEX_GBN_NM', '') or 
                                       row.findtext('NTR_DIV', '') or 
                                       row.findtext('GENDER', ''))
                        member.phone = (row.findtext('TEL_NO', '') or 
                                      row.findtext('NAAS_TEL_NO', ''))
                        member.email = (row.findtext('E_MAIL', '') or 
                                      row.findtext('NAAS_EMAIL_ADDR', ''))
                        member.homepage = (row.findtext('HOMEPAGE', '') or 
                                         row.findtext('NAAS_HP_URL', ''))
                        member.photo_url = (row.findtext('jpgLink', '') or 
                                          row.findtext('NAAS_PIC', ''))
                        
                        # CSV 정보 매칭 (득표율, 선거구)
                        csv_key = (name, term)
                        if csv_key in csv_data:
                            csv_info = csv_data[csv_key]
                            member.district = csv_info['constituency']
                            member.vote_rate = csv_info['vote_rate']
                        else:
                            member.district = (row.findtext('ORIG_NM', '') or 
                                             row.findtext('ELECD_NM', '') or 
                                             row.findtext('DISTRICT', ''))
                        
                        page_count += 1
                        term_count += 1
                        total_all_count += 1
                        
                        if page_count % 100 == 0:  # 100명마다 진행상황 출력
                            print(f"{term}대 처리 중... ({term_count}명)")
                    
                    # 페이지 별로 커밋
                    db.session.commit()
                    print(f"{term}대 {page}페이지 완료: {page_count}명 처리")
                    
                    # 다음 페이지로
                    page += 1
                    
                    # 데이터가 page_size보다 적으면 마지막 페이지
                    if len(rows) < page_size:
                        print(f"{term}대 마지막 페이지입니다.")
                        break
                    
                    # API 부하 방지를 위한 대기
                    time.sleep(2)  # 2초 대기
                    
                except Exception as e:
                    print(f"❌ {term}대 {page}페이지 처리 중 오류: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    db.session.rollback()
                    break
            
            print(f"\n✅ {term}대 완료: {term_count}명 처리")
            
            # 각 대수 처리 후 잠시 대기
            if term < 22:  # 마지막 대수가 아니면
                print("다음 대수 처리를 위해 3초 대기...")
                time.sleep(3)
        
        print(f"\n🎉 전체 동기화 완료!")
        print(f"총 {total_all_count}명의 국회의원 정보를 동기화했습니다.")
        print(f"20대: {Member.query.filter_by(session_num=20).count()}명")
        print(f"21대: {Member.query.filter_by(session_num=21).count()}명") 
        print(f"22대: {Member.query.filter_by(session_num=22).count()}명")

def add_sample_data():
    """테스트용 샘플 데이터 추가"""
    print("\n=== 샘플 데이터 추가 ===")
    
    # 샘플 국회의원
    sample_members = [
        {'name': '홍길동', 'party': '더불어민주당', 'district': '서울 종로구', 'session_num': 22},
        {'name': '김철수', 'party': '국민의힘', 'district': '부산 해운대구갑', 'session_num': 22},
        {'name': '이영희', 'party': '정의당', 'district': '비례대표', 'session_num': 22},
    ]
    
    for data in sample_members:
        if not Member.query.filter_by(name=data['name']).first():
            member = Member(**data, view_count=0)
            db.session.add(member)
    
    # 샘플 법률안
    sample_bills = [
        {
            'number': '2100001',
            'name': '개인정보 보호법 일부개정법률안',
            'proposer': '홍길동',
            'propose_date': '2024-01-15',
            'committee': '정무위원회',
            'view_count': 0
        },
        {
            'number': '2100002',
            'name': '국민건강보험법 일부개정법률안',
            'proposer': '김철수',
            'propose_date': '2024-01-20',
            'committee': '보건복지위원회',
            'view_count': 0
        },
    ]
    
    for data in sample_bills:
        if not Bill.query.filter_by(number=data['number']).first():
            bill = Bill(**data)
            db.session.add(bill)
    
    db.session.commit()
    print("✅ 샘플 데이터 추가 완료")
