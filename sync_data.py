import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import time
import os
from app import app, db, Member, Bill

# 국회 OpenAPI 설정
API_KEY = os.environ.get('ASSEMBLY_API_KEY', 'YOUR_API_KEY_HERE')  # 실제 API 키로 교체 필요
BASE_URL = 'https://open.assembly.go.kr/portal/openapi'

def sync_members():
    """국회의원 정보 동기화"""
    print("국회의원 정보 동기화 시작...")
    
    # 20, 21, 22대 국회의원 정보 가져오기
    for term in [20, 21, 22]:
        url = f"{BASE_URL}/ALLNAMEMBER"
        params = {
            'KEY': API_KEY,
            'Type': 'xml',
            'pIndex': 1,
            'pSize': 300,
            'UNIT_CD': f'{term:02d}'  # 20, 21, 22
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            
            for row in root.findall('.//row'):
                # XML 파싱
                name = row.findtext('HG_NM', '')
                party = row.findtext('POLY_NM', '')
                district = row.findtext('ORIG_NM', '')
                committee = row.findtext('CMIT_NM', '')
                birth_date = row.findtext('BTH_DATE', '')
                
                # 나이 계산
                age = None
                if birth_date:
                    try:
                        birth_year = int(birth_date[:4])
                        age = datetime.now().year - birth_year + 1
                    except:
                        pass
                
                # 성별
                gender = row.findtext('SEX_GBN_NM', '')
                
                # 연락처
                phone = row.findtext('TEL_NO', '')
                email = row.findtext('E_MAIL', '')
                homepage = row.findtext('HOMEPAGE', '')
                
                # 학력/경력
                mem_title = row.findtext('MEM_TITLE', '')
                
                # 사진 URL
                jpg_link = row.findtext('jpgLink', '')
                
                # DB에 저장 또는 업데이트
                member = Member.query.filter_by(name=name, session_num=term).first()
                
                if not member:
                    member = Member(
                        name=name,
                        session_num=term
                    )
                    db.session.add(member)
                
                # 정보 업데이트
                member.party = party
                member.district = district
                member.age = age
                member.gender = gender
                member.phone = phone
                member.email = email
                member.homepage = homepage
                member.career = mem_title
                member.photo_url = jpg_link
                
                print(f"처리 중: {term}대 {name} ({party})")
            
            db.session.commit()
            time.sleep(1)  # API 호출 간격
            
        except Exception as e:
            print(f"오류 발생 ({term}대): {e}")
            continue
    
    print("국회의원 정보 동기화 완료!")

def sync_bills():
    """법률안 정보 동기화"""
    print("법률안 정보 동기화 시작...")
    
    url = f"{BASE_URL}/nzmimeepazxkubdpn"
    
    # 최근 법률안 1000개 가져오기
    for page in range(1, 11):  # 100개씩 10페이지
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
            
            for row in root.findall('.//row'):
                # XML 파싱
                bill_no = row.findtext('BILL_NO', '')
                bill_name = row.findtext('BILL_NAME', '')
                proposer = row.findtext('PROPOSER', '')
                committee = row.findtext('COMMITTEE', '')
                propose_dt = row.findtext('PROPOSE_DT', '')
                proc_result = row.findtext('PROC_RESULT', '')
                detail_link = row.findtext('DETAIL_LINK', '')
                
                # 날짜 형식 변환
                if propose_dt and len(propose_dt) == 8:
                    propose_dt = f"{propose_dt[:4]}-{propose_dt[4:6]}-{propose_dt[6:8]}"
                
                # DB에 저장 또는 업데이트
                bill = Bill.query.filter_by(number=bill_no).first()
                
                if not bill:
                    bill = Bill(
                        number=bill_no,
                        name=bill_name
                    )
                    db.session.add(bill)
                
                # 정보 업데이트
                bill.proposer = proposer
                bill.committee = committee
                bill.propose_date = propose_dt
                bill.detail_link = detail_link
                
                print(f"처리 중: {bill_name[:30]}...")
            
            db.session.commit()
            time.sleep(1)  # API 호출 간격
            
        except Exception as e:
            print(f"오류 발생 (페이지 {page}): {e}")
            continue
    
    print("법률안 정보 동기화 완료!")

def sync_bill_details():
    """법률안 상세 정보 크롤링 (제안이유)"""
    print("법률안 상세 정보 동기화 시작...")
    
    bills = Bill.query.filter(Bill.summary == None).limit(50).all()
    
    for bill in bills:
        if not bill.detail_link:
            continue
        
        try:
            # 의안정보시스템에서 제안이유 크롤링
            # 실제 구현시 BeautifulSoup 사용
            # 여기서는 예시로만 표시
            print(f"크롤링 중: {bill.name[:30]}...")
            
            # bill.summary = crawled_summary
            # db.session.commit()
            
            time.sleep(2)  # 크롤링 간격
            
        except Exception as e:
            print(f"크롤링 오류: {e}")
            continue
    
    print("법률안 상세 정보 동기화 완료!")

def load_election_data():
    """선거 데이터 CSV 로드"""
    print("선거 데이터 로드 시작...")
    
    # CSV 파일 경로 (실제 파일 경로로 변경 필요)
    csv_file = 'election_data.csv'
    
    if not os.path.exists(csv_file):
        print(f"CSV 파일을 찾을 수 없습니다: {csv_file}")
        return
    
    import csv
    
    with open(csv_file, 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        
        for row in reader:
            name = row.get('이름', '')
            district = row.get('선거구', '')
            vote_rate = row.get('득표율', '')
            elected = row.get('당선여부', '')
            
            if not name:
                continue
            
            # 득표율 숫자 변환
            if vote_rate:
                try:
                    vote_rate = float(vote_rate.replace('%', ''))
                except:
                    vote_rate = None
            
            # 해당 국회의원 찾기
            member = Member.query.filter_by(name=name).first()
            
            if member:
                member.district = district
                member.vote_rate = vote_rate
                print(f"업데이트: {name} - {district} ({vote_rate}%)")
        
        db.session.commit()
    
    print("선거 데이터 로드 완료!")

if __name__ == '__main__':
    with app.app_context():
        # 데이터베이스 테이블 생성
        db.create_all()
        
        # 데이터 동기화 실행
        sync_members()
        sync_bills()
        # sync_bill_details()  # 크롤링은 필요시 활성화
        # load_election_data()  # CSV 파일이 있을 때 활성화
        
        print("\n모든 동기화 작업 완료!")
