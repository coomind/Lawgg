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
    """국회 OpenAPI에서 국회의원 정보 동기화"""
    print("\n=== 국회 OpenAPI에서 국회의원 정보 가져오기 ===")
    
    # API 연결 테스트 먼저
    if not test_api_connection():
        print("API 연결 실패! 종료합니다.")
        return
    
    # CSV 데이터 로드
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
    
    # 22대만 먼저 테스트
    term = 22
    print(f"\n{term}대 국회의원 정보 동기화 중...")
    
    url = f"{BASE_URL}/ALLNAMEMBER"
    params = {
        'KEY': API_KEY,
        'Type': 'xml',
        'pIndex': 1,
        'pSize': 100,  # 처음 100명만
        'UNIT_CD': f'{term:02d}'
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        print(f"응답 상태: {response.status_code}")
        
        if response.status_code != 200:
            print(f"HTTP 오류: {response.status_code}")
            print(f"응답 내용: {response.text[:500]}")
            return
        
        root = ET.fromstring(response.content)
        
        # 결과 확인
        result_code = root.findtext('.//RESULT_CODE')
        result_msg = root.findtext('.//RESULT_MESSAGE')
        
        print(f"API 응답 - 코드: {result_code}, 메시지: {result_msg}")
        
        if result_code != 'INFO-000':
            print(f"API 오류: {result_msg}")
            return
        
        # 데이터 파싱
        count = 0
        rows = root.findall('.//row')
        print(f"찾은 데이터: {len(rows)}개")
        
        for row in rows[:10]:  # 처음 10명만 테스트
            name = row.findtext('HG_NM', '')
            party = row.findtext('POLY_NM', '')
            
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
            
            # 정보 업데이트
            member.party = party or '무소속'
            member.gender = row.findtext('SEX_GBN_NM', '')
            member.phone = row.findtext('TEL_NO', '')
            member.email = row.findtext('E_MAIL', '')
            member.homepage = row.findtext('HOMEPAGE', '')
            member.photo_url = row.findtext('jpgLink', '')
            
            # CSV 정보 매칭
            csv_key = (name, term)
            if csv_key in csv_data:
                csv_info = csv_data[csv_key]
                member.district = csv_info['constituency']
                member.vote_rate = csv_info['vote_rate']
            else:
                member.district = row.findtext('ORIG_NM', '')
            
            count += 1
            print(f"처리: {name} ({party})")
        
        db.session.commit()
        print(f"\n✅ {count}명의 국회의원 정보를 동기화했습니다.")
        
    except Exception as e:
        print(f"❌ 오류 발생: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        db.session.rollback()

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
