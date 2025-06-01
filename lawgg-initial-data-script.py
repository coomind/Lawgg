import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db, Member, Bill
import csv

def init_basic_data():
    """기본 데이터 초기화"""
    with app.app_context():
        # 데이터베이스 테이블 생성
        db.create_all()
        
        # 기본 샘플 데이터가 없으면 추가
        if Member.query.count() == 0:
            print("샘플 국회의원 데이터 추가 중...")
            
            # CSV 파일에서 데이터 로드
            csv_file = '국회의원_당선자_통합명부_20_21_22대.csv'
            if os.path.exists(csv_file):
                with open(csv_file, 'r', encoding='utf-8-sig') as file:
                    reader = csv.DictReader(file)
                    count = 0
                    
                    for row in reader:
                        name = row.get('name', '').strip()
                        age = row.get('age', '').strip()
                        constituency = row.get('constituency', '').strip()
                        vote_percent = row.get('vote_percent', '').strip()
                        status = row.get('status', '').strip()
                        
                        if not name or status != '당선':
                            continue
                        
                        # 대수 파싱
                        try:
                            session_num = int(age) if age else 22
                        except:
                            session_num = 22
                        
                        # 득표율 파싱
                        vote_rate = None
                        if vote_percent and vote_percent != 'nan%':
                            try:
                                vote_rate = float(vote_percent.replace('%', ''))
                            except:
                                pass
                        
                        # 정당 추측 (실제로는 API에서 가져와야 함)
                        party = '더불어민주당' if count % 3 == 0 else '국민의힘' if count % 3 == 1 else '무소속'
                        
                        member = Member(
                            name=name,
                            party=party,
                            district=constituency,
                            session_num=session_num,
                            vote_rate=vote_rate,
                            view_count=0
                        )
                        db.session.add(member)
                        count += 1
                        
                        if count >= 50:  # 처음 50명만 추가
                            break
                    
                    db.session.commit()
                    print(f"{count}명의 국회의원 데이터를 추가했습니다.")
            
            # 샘플 법률안 데이터
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
                {
                    'number': '2100003',
                    'name': '교육기본법 일부개정법률안',
                    'proposer': '이영희',
                    'propose_date': '2024-02-01',
                    'committee': '교육위원회',
                    'view_count': 0
                },
                {
                    'number': '2100004',
                    'name': '근로기준법 일부개정법률안',
                    'proposer': '박민수',
                    'propose_date': '2024-02-10',
                    'committee': '환경노동위원회',
                    'view_count': 0
                },
                {
                    'number': '2100005',
                    'name': '도로교통법 일부개정법률안',
                    'proposer': '정수진',
                    'propose_date': '2024-02-15',
                    'committee': '국토교통위원회',
                    'view_count': 0
                }
            ]
            
            for bill_data in sample_bills:
                bill = Bill(**bill_data)
                db.session.add(bill)
            
            db.session.commit()
            print(f"{len(sample_bills)}개의 법률안 데이터를 추가했습니다.")
            
        else:
            print(f"이미 {Member.query.count()}명의 국회의원 데이터가 있습니다.")
            print(f"이미 {Bill.query.count()}개의 법률안 데이터가 있습니다.")

if __name__ == '__main__':
    init_basic_data()
    print("\n초기 데이터 로드 완료!")