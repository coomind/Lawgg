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
API_KEY = '79deed587e6043f291a36420cfd972de'
BASE_URL = 'https://open.assembly.go.kr/portal/openapi'

# CSV 데이터를 메모리에 로드
def load_csv_data_to_memory():
    """CSV 파일에서 선거구/득표율 정보를 메모리에 로드"""
    csv_data = {}
    csv_file = '국회의원_당선자_통합명부_20_21_22대.csv'
    
    if not os.path.exists(csv_file):
        print(f"CSV 파일을 찾을 수 없습니다: {csv_file}")
        return csv_data
    
    with open(csv_file, 'r', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        
        for row in reader:
            name = row.get('name', '').strip()
            age = row.get('age', '').strip()  # 실제로는 대수
            constituency = row.get('constituency', '').strip()
            vote_percent = row.get('vote_percent', '').strip()
            status = row.get('status', '').strip()
            
            if not name or status != '당선':
                continue
            
            # 대수 파싱
            try:
                session_num = int(age) if age else None
            except:
                session_num = None
            
            # 득표율 파싱
            vote_rate = None
            if vote_percent and vote_percent != 'nan%':
                try:
                    vote_rate = float(vote_percent.replace('%', ''))
                except:
                    pass
            
            # 키: (이름, 대수)
            key = (name, session_num)
            csv_data[key] = {
                'constituency': constituency,
                'vote_rate': vote_rate
            }
    
    print(f"CSV에서 {len(csv_data)}개의 선거 데이터를 로드했습니다.")
    return csv_data

def sync_members_from_api():
    """국회 OpenAPI에서 국회의원 정보 동기화"""
    print("\n=== 국회 OpenAPI에서 국회의원 정보 가져오기 ===")
    
    # CSV 데이터 먼저 로드
    csv_data = load_csv_data_to_memory()
    
    # 20, 21, 22대 국회의원 정보 가져오기
    for term in [20, 21, 22]:
        print(f"\n{term}대 국회의원 정보 동기화 중...")
        
        url = f"{BASE_URL}/ALLNAMEMBER"
        params = {
            'KEY': API_KEY,
            'Type': 'xml',
            'pIndex': 1,
            'pSize': 300,
            'UNIT_CD': f'{term:02d}'
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            
            # 헤더 정보 확인
            result_code = root.findtext('.//RESULT_CODE')
            if result_code != 'INFO-000':
                print(f"API 오류 ({term}대): {root.findtext('.//RESULT_MESSAGE')}")
                continue
            
            count = 0
            for row in root.findall('.//row'):
                # API에서 정보 파싱
                name = row.findtext('HG_NM', '')
                party = row.findtext('POLY_NM', '')
                orig_nm = row.findtext('ORIG_NM', '')  # 선거구
                birth_date = row.findtext('BTH_DATE', '')
                gender = row.findtext('SEX_GBN_NM', '')
                phone = row.findtext('TEL_NO', '')
                email = row.findtext('E_MAIL', '')
                homepage = row.findtext('HOMEPAGE', '')
                mem_title = row.findtext('MEM_TITLE', '')  # 약력
                jpg_link = row.findtext('jpgLink', '')
                
                # 나이 계산
                age = None
                if birth_date:
                    try:
                        birth_year = int(birth_date[:4])
                        age = datetime.now().year - birth_year + 1
                    except:
                        pass
                
                # DB에 저장 또는 업데이트
                member = Member.query.filter_by(name=name, session_num=term).first()
                
                if not member:
                    member = Member(
                        name=name,
                        session_num=term,
                        view_count=0
                    )
                    db.session.add(member)
                
                # API 정보 업데이트
                member.party = party
                member.age = age
                member.gender = gender
                member.phone = phone
                member.email = email
                member.homepage = homepage
                member.career = mem_title
                member.photo_url = jpg_link
                
                # CSV에서 선거구/득표율 정보 매칭
                csv_key = (name, term)
                if csv_key in csv_data:
                    csv_info = csv_data[csv_key]
                    member.district = csv_info['constituency']
                    member.vote_rate = csv_info['vote_rate']
                else:
                    # CSV에 없으면 API의 ORIG_NM 사용
                    member.district = orig_nm
                
                count += 1
                if count % 10 == 0:
                    print(f"  처리 중: {count}명...")
            
            db.session.commit()
            print(f"{term}대: {count}명 동기화 완료")
            time.sleep(1)  # API 호출 간격
            
        except Exception as e:
            print(f"오류 발생 ({term}대): {e}")
            db.session.rollback()
            continue
    
    print("\n국회의원 정보 동기화 완료!")

def sync_bills_from_api():
    """국회 OpenAPI에서 법률안 정보 동기화"""
    print("\n=== 국회 OpenAPI에서 법률안 정보 가져오기 ===")
    
    url = f"{BASE_URL}/nzmimeepazxkubdpn"
    
    # 최근 법률안 500개 가져오기 (100개씩 5페이지)
    total_count = 0
    
    for page in range(1, 6):
        print(f"\n페이지 {page}/5 처리 중...")
        
        params = {
            'KEY': API_KEY,
            'Type': 'xml',
            'pIndex': page,
            'pSize': 100,
            'AGE': '22'  # 22대 국회
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            
            # 헤더 정보 확인
            result_code = root.findtext('.//RESULT_CODE')
            if result_code != 'INFO-000':
                print(f"API 오류: {root.findtext('.//RESULT_MESSAGE')}")
                continue
            
            count = 0
            for row in root.findall('.//row'):
                # API에서 정보 파싱
                bill_no = row.findtext('BILL_NO', '')
                bill_name = row.findtext('BILL_NAME', '')
                proposer = row.findtext('PROPOSER', '')
                committee = row.findtext('COMMITTEE', '')
                propose_dt = row.findtext('PROPOSE_DT', '')
                detail_link = row.findtext('DETAIL_LINK', '')
                
                # 날짜 형식 변환
                if propose_dt and len(propose_dt) == 8:
                    propose_dt = f"{propose_dt[:4]}-{propose_dt[4:6]}-{propose_dt[6:8]}"
                
                # DB에 저장 또는 업데이트
                bill = Bill.query.filter_by(number=bill_no).first()
                
                if not bill:
                    bill = Bill(
                        number=bill_no,
                        name=bill_name,
                        view_count=0
                    )
                    db.session.add(bill)
                
                # 정보 업데이트
                bill.proposer = proposer
                bill.committee = committee
                bill.propose_date = propose_dt
                bill.detail_link = detail_link
                
                count += 1
            
            db.session.commit()
            total_count += count
            print(f"  {count}개 법률안 처리 완료")
            time.sleep(1)  # API 호출 간격
            
        except Exception as e:
            print(f"오류 발생 (페이지 {page}): {e}")
            db.session.rollback()
            continue
    
    print(f"\n총 {total_count}개의 법률안 동기화 완료!")

if __name__ == '__main__':
    with app.app_context():
        # 데이터베이스 테이블 생성
        db.create_all()
        
        # 1. 국회의원 정보 동기화 (API + CSV)
        sync_members_from_api()
        
        # 2. 법률안 정보 동기화
        sync_bills_from_api()
        
        # 3. 결과 확인
        member_count = Member.query.count()
        bill_count = Bill.query.count()
        
        print("\n=== 동기화 완료 ===")
        print(f"총 국회의원 수: {member_count}명")
        print(f"총 법률안 수: {bill_count}개")
        
        # 샘플 데이터 확인
        print("\n샘플 데이터:")
        sample_members = Member.query.limit(5).all()
        for m in sample_members:
            print(f"- {m.name} ({m.party}) - {m.district} - 득표율: {m.vote_rate}%")
