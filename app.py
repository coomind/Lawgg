import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, timedelta
import requests
import json
import csv
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import re
from bs4 import BeautifulSoup
import threading
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # 실제 배포시 변경 필요
# PostgreSQL 데이터베이스 설정
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    # Render.com PostgreSQL URL 수정 (postgres:// -> postgresql://)
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    # 로컬 개발용 SQLite
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lawgg.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# API 키 설정
ASSEMBLY_API_KEY = 'a3fada8210244129907d945abe2beada'

db = SQLAlchemy(app)
CORS(app)
# 데이터베이스 모델들
class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # unique 추가
    english_name = db.Column(db.String(100))
    party = db.Column(db.String(50))  # 현재 소속 정당
    district = db.Column(db.String(100))  # 현재 선거구
    photo_url = db.Column(db.String(200))
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    education = db.Column(db.Text)
    career = db.Column(db.Text)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(100))
    homepage = db.Column(db.String(200))
    vote_rate = db.Column(db.Float)  # 최신 득표율
    view_count = db.Column(db.Integer, default=0)
    birth_date = db.Column(db.String(10))
    def get_assembly_homepage_url(self):
        """국회 홈페이지 URL 생성"""
        if self.current_session and self.english_name:
            clean_english_name = self.english_name.replace(' ', '')
            return f"https://www.assembly.go.kr/members/{self.current_session}nd/{clean_english_name}"
        return None
    
    # 새로운 필드들
    sessions = db.Column(db.String(50))  # "20,21,22" 형태
    current_session = db.Column(db.Integer)  # 현재/최신 대수
    first_session = db.Column(db.Integer)  # 첫 당선 대수
    
    # 대수별 상세 정보 (JSON 형태로 저장)
    session_details = db.Column(db.Text)  # JSON: {"20": {"party": "A당", "district": "서울"}, "21": {...}}
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def get_session_list(self):
        """대수 리스트 반환"""
        if self.sessions:
            return [int(x) for x in self.sessions.split(',')]
        return []
    
    def add_session(self, session_num):
        """새 대수 추가"""
        sessions = self.get_session_list()
        if session_num not in sessions:
            sessions.append(session_num)
            sessions.sort()
            self.sessions = ','.join(map(str, sessions))
            
            # 첫 당선 대수 설정
            if not self.first_session:
                self.first_session = min(sessions)
            
            # 현재 대수 업데이트 (가장 최신)
            self.current_session = max(sessions)
    
    def get_session_details(self):
        """대수별 상세 정보 반환"""
        if self.session_details:
            import json
            return json.loads(self.session_details)
        return {}
    
    def update_session_details(self, session_num, party, district, vote_rate=None):
        """대수별 상세 정보 업데이트"""
        import json
        details = self.get_session_details()
        
        details[str(session_num)] = {
            'party': party,
            'district': district,
            'vote_rate': vote_rate
        }
        
        self.session_details = json.dumps(details, ensure_ascii=False)

class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(50))
    name = db.Column(db.String(200), nullable=False)
    proposer = db.Column(db.String(50))
    propose_date = db.Column(db.String(20))
    committee = db.Column(db.String(50))
    detail_link = db.Column(db.String(200))
    summary = db.Column(db.Text)
    view_count = db.Column(db.Integer, default=0)
    assembly_result = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class BillVote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'))
    ip_address = db.Column(db.String(50))
    vote_type = db.Column(db.String(10))  # 'agree' or 'disagree'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=True)
    proposal_id = db.Column(db.Integer, db.ForeignKey('proposal.id'), nullable=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    author = db.Column(db.String(50))
    content = db.Column(db.Text, nullable=False)
    stance = db.Column(db.String(10))  # 'agree' or 'disagree'
    ip_address = db.Column(db.String(50))
    report_count = db.Column(db.Integer, default=0)
    is_under_review = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]))
    likes = db.relationship('CommentLike', backref='comment', lazy='dynamic')

class Proposal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(50))
    target_law = db.Column(db.String(100))
    draft_number = db.Column(db.String(100))
    current_situation = db.Column(db.Text)
    problems = db.Column(db.Text)
    proposal_reasons = db.Column(db.Text)
    improvement_type = db.Column(db.String(20))
    is_public = db.Column(db.Boolean, default=True)
    is_draft = db.Column(db.Boolean, default=False)
    view_count = db.Column(db.Integer, default=0)
    report_count = db.Column(db.Integer, default=0)
    ip_address = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ProposalVote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    proposal_id = db.Column(db.Integer, db.ForeignKey('proposal.id'))
    ip_address = db.Column(db.String(50))
    vote_type = db.Column(db.String(10))  # 'agree' or 'disagree'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    proposal_id = db.Column(db.Integer, db.ForeignKey('proposal.id'), nullable=True)
    reporter_ip = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
class CommentLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'))
    ip_address = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('comment_id', 'ip_address'),)


class BlockedIP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(50), unique=True)
    reason = db.Column(db.String(200))
    blocked_at = db.Column(db.DateTime, default=datetime.utcnow)


# 유틸리티 함수들
def get_client_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0]
    return request.remote_addr

def time_ago(created_at):
    now = datetime.utcnow()
    diff = now - created_at
    
    if diff.days > 365:
        return f"{diff.days // 365}년 전"
    elif diff.days > 30:
        return f"{diff.days // 30}개월 전"
    elif diff.days > 0:
        return f"{diff.days}일 전"
    elif diff.seconds > 3600:
        return f"{diff.seconds // 3600}시간 전"
    elif diff.seconds > 60:
        return f"{diff.seconds // 60}분 전"
    else:
        return "방금 전"

def get_anonymous_name(ip_address):
    """IP별 고유한 익명 이름 생성"""
    import hashlib
    
    # IP를 해시하여 숫자로 변환
    hash_object = hashlib.md5(ip_address.encode())
    hash_hex = hash_object.hexdigest()
    
    # 해시의 앞 6자리를 숫자로 변환하여 사용 (1~999999 범위)
    anonymous_number = int(hash_hex[:6], 16) % 999999 + 1
    
    return f'익명{anonymous_number}'

def is_admin():
    return session.get('is_admin', False)


@app.route('/admin/lawgg2025')
def admin_login():
    session['is_admin'] = True
    return redirect('/admin/dashboard')

# 관리자 로그아웃
@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect('/')

# 관리자 대시보드
@app.route('/admin/dashboard')
def admin_dashboard():
    if not is_admin():
        return "접근 거부", 403
    
    # 신고된 입법제안들 (신고 수 1개 이상)
    reported_proposals = Proposal.query.filter(Proposal.report_count > 0).order_by(Proposal.report_count.desc()).all()
    
    # 신고된 댓글들 (신고 수 1개 이상)
    reported_comments = Comment.query.filter(Comment.report_count > 0).order_by(Comment.report_count.desc()).all()
    
    # 차단된 IP 목록
    blocked_ips = BlockedIP.query.order_by(BlockedIP.blocked_at.desc()).all()
    
    return render_template('admin_dashboard.html', 
                         reported_proposals=reported_proposals,
                         reported_comments=reported_comments,
                         blocked_ips=blocked_ips)

# 입법제안 삭제
# 입법제안 삭제 함수 수정
@app.route('/admin/proposals/<int:proposal_id>/delete', methods=['POST'])
def admin_delete_proposal(proposal_id):
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        proposal = Proposal.query.get_or_404(proposal_id)
        
        # 1. 관련 신고들 먼저 삭제
        Report.query.filter_by(proposal_id=proposal_id).delete()
        
        # 2. 관련 댓글들의 좋아요 삭제
        comment_ids = [c.id for c in Comment.query.filter_by(proposal_id=proposal_id).all()]
        if comment_ids:
            CommentLike.query.filter(CommentLike.comment_id.in_(comment_ids)).delete(synchronize_session=False)
            
        # 3. 관련 댓글 신고들 삭제
        Report.query.filter(Report.comment_id.in_(comment_ids)).delete(synchronize_session=False)
        
        # 4. 관련 댓글들 삭제
        Comment.query.filter_by(proposal_id=proposal_id).delete()
        
        # 5. 관련 투표들 삭제
        ProposalVote.query.filter_by(proposal_id=proposal_id).delete()
        
        # 6. 마지막으로 입법제안 삭제
        db.session.delete(proposal)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '입법제안이 삭제되었습니다.'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'삭제 중 오류 발생: {str(e)}'}), 500

# 댓글 삭제 함수 수정
@app.route('/admin/comments/<int:comment_id>/delete', methods=['POST'])
def admin_delete_comment(comment_id):
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        comment = Comment.query.get_or_404(comment_id)
        
        # 1. 답글들의 좋아요 먼저 삭제
        reply_ids = [r.id for r in Comment.query.filter_by(parent_id=comment_id).all()]
        if reply_ids:
            CommentLike.query.filter(CommentLike.comment_id.in_(reply_ids)).delete(synchronize_session=False)
            Report.query.filter(Report.comment_id.in_(reply_ids)).delete(synchronize_session=False)
        
        # 2. 답글들 삭제
        Comment.query.filter_by(parent_id=comment_id).delete()
        
        # 3. 댓글의 좋아요들 삭제
        CommentLike.query.filter_by(comment_id=comment_id).delete()
        
        # 4. 댓글의 신고들 삭제
        Report.query.filter_by(comment_id=comment_id).delete()
        
        # 5. 댓글 삭제
        db.session.delete(comment)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '댓글이 삭제되었습니다.'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'삭제 중 오류 발생: {str(e)}'}), 500

# IP 차단
@app.route('/admin/ban-ip', methods=['POST'])
def admin_ban_ip():
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    ip_address = data.get('ip_address')
    reason = data.get('reason', '관리자에 의한 차단')
    
    if not ip_address:
        return jsonify({'error': 'IP 주소가 필요합니다.'}), 400
    
    # 이미 차단된 IP인지 확인
    existing = BlockedIP.query.filter_by(ip_address=ip_address).first()
    if existing:
        return jsonify({'error': '이미 차단된 IP입니다.'}), 400
    
    # IP 차단 추가
    blocked_ip = BlockedIP(ip_address=ip_address, reason=reason)
    db.session.add(blocked_ip)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'IP {ip_address}가 차단되었습니다.'})

# IP 차단 해제
@app.route('/admin/unban-ip/<int:blocked_ip_id>', methods=['POST'])
def admin_unban_ip(blocked_ip_id):
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    
    blocked_ip = BlockedIP.query.get_or_404(blocked_ip_id)
    ip_address = blocked_ip.ip_address
    
    db.session.delete(blocked_ip)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'IP {ip_address} 차단이 해제되었습니다.'})

# 입법제안 작성자 IP로 차단
@app.route('/admin/proposals/<int:proposal_id>/ban-author', methods=['POST'])
def admin_ban_proposal_author(proposal_id):
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    
    proposal = Proposal.query.get_or_404(proposal_id)
    ip_address = proposal.ip_address
    
    if not ip_address:
        return jsonify({'error': 'IP 정보가 없습니다.'}), 400
    
    # 이미 차단된 IP인지 확인
    existing = BlockedIP.query.filter_by(ip_address=ip_address).first()
    if existing:
        return jsonify({'error': '이미 차단된 IP입니다.'}), 400
    
    # IP 차단
    blocked_ip = BlockedIP(ip_address=ip_address, reason=f'입법제안 신고로 인한 차단 (제안 ID: {proposal_id})')
    db.session.add(blocked_ip)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'작성자 IP {ip_address}가 차단되었습니다.'})

# 댓글 작성자 IP로 차단
@app.route('/admin/comments/<int:comment_id>/ban-author', methods=['POST'])
def admin_ban_comment_author(comment_id):
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    
    comment = Comment.query.get_or_404(comment_id)
    ip_address = comment.ip_address
    
    if not ip_address:
        return jsonify({'error': 'IP 정보가 없습니다.'}), 400
    
    # 이미 차단된 IP인지 확인
    existing = BlockedIP.query.filter_by(ip_address=ip_address).first()
    if existing:
        return jsonify({'error': '이미 차단된 IP입니다.'}), 400
    
    # IP 차단
    blocked_ip = BlockedIP(ip_address=ip_address, reason=f'댓글 신고로 인한 차단 (댓글 ID: {comment_id})')
    db.session.add(blocked_ip)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'작성자 IP {ip_address}가 차단되었습니다.'})
    
# 라우트들

@app.route('/')
def index():
    # 화제의 법률안 (최근 24시간 조회수 기준)
    yesterday = datetime.utcnow() - timedelta(days=1)
    trending_bills = Bill.query.order_by(Bill.view_count.desc()).limit(5).all()
    trending_members = Member.query.order_by(Member.view_count.desc()).limit(5).all()
    
    trending_bills_data = [{
        'id': bill.id,
        'title': bill.name[:30] + '...' if len(bill.name) > 30 else bill.name,
        'status': bill.committee,
        'view_count': bill.view_count
    } for bill in trending_bills]
    
    trending_members_data = [{
        'id': member.id,
        'name': member.name,
        'party': member.party,
        'view_count': member.view_count,
        'photo_url' : member.photo_url
    } for member in trending_members]
    
    return render_template('index.html',
                         trending_bills=trending_bills_data,
                         trending_members=trending_members_data)

@app.route('/members')
def members_list():
    page = request.args.get('page', 1, type=int)
    party = request.args.get('party', '전체')
    search = request.args.get('search', '')
    per_page = 20
    
    # 🔥 Python에서 한글 가나다순 정렬
    query = Member.query
    if search:
        query = query.filter(
            db.or_(
                Member.name.contains(search),
                Member.party.contains(search),
                Member.district.contains(search)
            )
        )
    
    if party and party != '전체':
        if party == '기타':
            # 주요 4개 정당에 속하지 않는 의원들
            major_parties = ['더불어민주당', '국민의힘', '정의당', '국민의당']
            query = query.filter(~db.or_(*[Member.party.contains(p) for p in major_parties]))
        else:
            query = query.filter(Member.party.contains(party))
    
    all_members = query.all()
    
    # 한글 가나다순 정렬
    import locale
    try:
        locale.setlocale(locale.LC_COLLATE, 'ko_KR.UTF-8')
        sorted_members = sorted(all_members, key=lambda x: locale.strxfrm(x.name or ''))
    except:
        # fallback: 기본 정렬
        sorted_members = sorted(all_members, key=lambda x: x.name or '')
    
    # 수동 페이지네이션
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_members = sorted_members[start_idx:end_idx]
    
    total_count = len(sorted_members)
    total_pages = (total_count + per_page - 1) // per_page
    
    # 정당 목록
    parties = [
        {'code': '전체', 'name': '전체'},
        {'code': '더불어민주당', 'name': '더불어민주당'},
        {'code': '국민의힘', 'name': '국민의힘'},
        {'code': '정의당', 'name': '정의당'},
        {'code': '국민의당', 'name': '국민의당'},
        {'code': '기타', 'name': '기타'}
    ]
    
    # 페이지네이션 데이터 재구성
    pagination_data = {
        'current_page': page,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'page_range': get_page_range(page, total_pages),
        'prev_url_params': f"page={page-1}&party={party}&search={search}" if page > 1 else '',
        'next_url_params': f"page={page+1}&party={party}&search={search}" if page < total_pages else '',
        'page_size': per_page
    }
    
    def get_url_params(page_num):
        params = []
        if page_num > 1:
            params.append(f"page={page_num}")
        if party != '전체':
            params.append(f"party={party}")
        if search:  # 🔥 이 3줄 추가
            params.append(f"search={search}")
        return '&'.join(params)
    
    pagination_data['get_url_params'] = get_url_params
    
    # 🔥 page_members 사용 (pagination.items 대신)
    members_data = [{
        'id': m.id,
        'name': m.name,
        'party': m.party,
        'age': calculate_age(m.age) if m.age else None,
        'gender': m.gender,
        'photo_url': m.photo_url
    } for m in page_members]
    
    if search:
        page_title = f'"{search}" 검색 결과 - 국회의원 ({total_count}명)'
    else:
        page_title = '국회의원 목록'
    
    return render_template('NAlist.html',
                         page_title=page_title,
                         members=members_data,
                         parties=parties,
                         current_party=party,
                         pagination=pagination_data)
    
# 기존 함수 전체를 이것으로 교체:
@app.route('/members/<int:member_id>')
def member_detail(member_id):
    member = Member.query.get_or_404(member_id)
    member.view_count += 1
    db.session.commit()
    
    # 해당 의원이 발의한 법률안
    bills = Bill.query.filter(Bill.proposer.contains(member.name)).limit(10).all()
    
    # 🔥 학력/경력 분리 로직 개선 🔥
    education = []
    career = []
    
    # 1. education 필드에서 학력 추출
    if member.education:
        education_items = [item.strip() for item in member.education.split(',') if item.strip()]
        education.extend(education_items)
    
    # 2. career 필드에서 경력 추출
    if member.career:
        career_items = [item.strip() for item in member.career.split(',') if item.strip()]
        career.extend(career_items)
    
    # 3. 기존 로직 (career 필드가 학력과 경력이 섞여있는 경우를 위한 fallback)
    if not education and not career and member.career:
        items = member.career.split(',')
        for item in items:
            item = item.strip()
            if item:
                # 학력 키워드 체크 (학교, 학원, 졸업, 수료 등)
                education_keywords = ['학교', '학원', '대학교', '고등학교', '중학교', '초등학교', '대학원', '학과', '졸업', '수료', '입학']
                
                if any(keyword in item for keyword in education_keywords):
                    education.append(item)
                else:
                    career.append(item)
    
    # 중복 제거 (순서 유지)
    def remove_duplicates(items):
        seen = set()
        result = []
        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result
    
    education = remove_duplicates(education)
    career = remove_duplicates(career)
    
    member_data = {
        'id': member.id,
        'name': member.name,
        'party': member.party,
        'district_name': member.district,
        'photo_url': member.photo_url,
        'education': education,  # 학력 전체
        'career': career,        # 경력 전체 (길이 제한 제거)
        'phone': member.phone,
        'email': member.email,
        'homepage': member.get_assembly_homepage_url(),
        'vote_rate': member.vote_rate,
        'terms': [{'session': s } for s in member.get_session_list()] if member.sessions else []
    }
    
    bills_data = [{
        'id': bill.id,
        'title': bill.name,
        'propose_date': bill.propose_date,
        'committee': bill.committee
    } for bill in bills]
    
    return render_template('NAdetail.html',
                         member=member_data,
                         bills=bills_data)

@app.route('/bills')
def bills_list():
    page = request.args.get('page', 1, type=int)
    committee = request.args.get('committee', '')
    search = request.args.get('search', '')
    per_page = 20
    
    query = Bill.query.order_by(Bill.propose_date.desc().nulls_last())
    
    if committee:
        query = query.filter_by(committee=committee)
    if search:
        query = query.filter(Bill.name.contains(search))
    
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # 위원회 목록
    committees = [
        {'code': '', 'display_name': '전체'},
        {'code': '법제사법위원회', 'display_name': '법제사법'},
        {'code': '정무위원회', 'display_name': '정무'},
        {'code': '기획재정위원회', 'display_name': '기획재정'},
        {'code': '교육위원회', 'display_name': '교육'},
        {'code': '과학기술정보방송통신위원회', 'display_name': '과방'},
        {'code': '외교통일위원회', 'display_name': '외교통일'},
        {'code': '국방위원회', 'display_name': '국방'},
        {'code': '행정안전위원회', 'display_name': '행안'},
        {'code': '문화체육관광위원회', 'display_name': '문체'},
        {'code': '농림축산식품해양수산위원회', 'display_name': '농축해수'},
        {'code': '산업통상자원중소벤처기업위원회', 'display_name': '산자중기'},
        {'code': '보건복지위원회', 'display_name': '보건복지'},
        {'code': '환경노동위원회', 'display_name': '환노'},
        {'code': '국토교통위원회', 'display_name': '국토교통'},
        {'code': '정보위원회', 'display_name': '정보'},
        {'code': '여성가족위원회', 'display_name': '여성가족'},
        {'code': '특별위원회', 'display_name': '특별'}
    ]
    
    # 페이지네이션 데이터
    pagination_data = {
        'current_page': page,
        'total_pages': pagination.pages,
        'total_count': pagination.total,
        'has_prev': pagination.has_prev,
        'has_next': pagination.has_next,
        'page_range': get_page_range(page, pagination.pages),
        'page_size': per_page
    }
    
    # URL 파라미터 생성
    def get_url_params(page_num=None):
        params = []
        if page_num and page_num > 1:
            params.append(f"page={page_num}")
        if committee:
            params.append(f"committee={committee}")
        if search:
            params.append(f"search={search}")
        return '&'.join(params)
    
    pagination_data['prev_url_params'] = get_url_params(page - 1) if pagination.has_prev else ''
    pagination_data['next_url_params'] = get_url_params(page + 1) if pagination.has_next else ''
    pagination_data['get_url_params'] = get_url_params
    
    bills_data = [{
        'id': bill.id,
        'number': bill.number,
        'name': bill.name,
        'proposer': bill.proposer,
        'propose_date': bill.propose_date,
        'committee': bill.committee
    } for bill in pagination.items]
    
    # 현재 위원회 이름 찾기
    current_committee_name = next((c['display_name'] for c in committees if c['code'] == committee), None)
    
    if search:
        page_title = f'"{search}" 검색 결과 - 법률안 ({pagination.total}건)'
    else:
        page_title = '법률안 목록'
    
    return render_template('LAWlist.html',
                     page_title=page_title,  # 🔥 이 부분도 수정
                     bills=bills_data,
                     committees=committees,
                     current_committee=committee,
                     current_committee_name=current_committee_name,
                     current_search_term=search,
                     search_placeholder='법률안 검색',
                     pagination=pagination_data)
                

@app.route('/bills/<int:bill_id>')
def bill_detail(bill_id):
    bill = Bill.query.get_or_404(bill_id)
    bill.view_count += 1
    db.session.commit()
    
    ip_address = get_client_ip()
    
    # 사용자의 투표 여부 확인
    user_vote = BillVote.query.filter_by(bill_id=bill_id, ip_address=ip_address).first()
    user_vote_type = user_vote.vote_type if user_vote else None
    
    # 투표 통계
    agree_count = BillVote.query.filter_by(bill_id=bill_id, vote_type='agree').count()
    disagree_count = BillVote.query.filter_by(bill_id=bill_id, vote_type='disagree').count()
    
    vote_stats = {
        'agree_count': agree_count,
        'disagree_count': disagree_count
    }
    
    # 댓글 가져오기 (부모 댓글만)
    parent_comments = Comment.query.filter_by(bill_id=bill_id, parent_id=None).order_by(Comment.created_at.desc()).limit(5).all()
    total_parent_comments = Comment.query.filter_by(bill_id=bill_id, parent_id=None).count()
    
    # 사용자가 신고한 댓글 ID들
    user_reports = Report.query.filter_by(reporter_ip=ip_address).all()
    reported_comment_ids = [r.comment_id for r in user_reports if r.comment_id]
    
    # 사용자가 좋아요한 댓글 ID들
    user_likes = CommentLike.query.filter_by(ip_address=ip_address).all()
    liked_comment_ids = [l.comment_id for l in user_likes]
    
    # 댓글 데이터 준비
    comments_data = []
    comment_reports = {}
    
    for comment in parent_comments:
        # 좋아요 수 계산
        like_count = CommentLike.query.filter_by(comment_id=comment.id).count()
        
        comment_data = {
            'id': comment.id,
            'author': comment.author or f'익명{comment.id}',
            'content': comment.content,
            'stance': comment.stance,
            'time_ago': time_ago(comment.created_at),
            'report_count': comment.report_count,
            'is_under_review': comment.is_under_review or comment.report_count >= 3,
            'is_reported_by_user': comment.id in reported_comment_ids,
            'like_count': like_count,
            'is_liked_by_user': comment.id in liked_comment_ids
        }
        comments_data.append(comment_data)
        comment_reports[str(comment.id)] = comment.report_count
        
        # 답글들도 추가
        for reply in comment.replies:
            reply_like_count = CommentLike.query.filter_by(comment_id=reply.id).count()
            
            reply_data = {
                'id': reply.id,
                'parent_id': reply.parent_id,
                'author': reply.author or f'익명{reply.id}',
                'content': reply.content,
                'stance': reply.stance,
                'time_ago': time_ago(reply.created_at),
                'report_count': reply.report_count,
                'is_under_review': reply.is_under_review or reply.report_count >= 3,
                'is_reported_by_user': reply.id in reported_comment_ids,
                'like_count': reply_like_count,
                'is_liked_by_user': reply.id in liked_comment_ids
            }
            comments_data.append(reply_data)
            comment_reports[str(reply.id)] = reply.report_count
    
    # 관련 법률안 (같은 위원회) - 실제 데이터만
    related_bills = Bill.query.filter(
        Bill.committee == bill.committee,
        Bill.id != bill.id
    ).limit(5).all()
    
    # 관련 법률안이 있을 때만 데이터 생성
    related_bills_data = []
    if related_bills:
        related_bills_data = [{
            'id': rb.id,
            'name': rb.name[:50] + '...' if len(rb.name) > 50 else rb.name
        } for rb in related_bills]
    
    # 법률안 상세 내용 크롤링
    bill_content = crawl_bill_content(bill.number if bill.number else '')
    
    bill_data = {
        'id': bill.id,
        'number': bill.number,
        'name': bill.name,
        'proposer': bill.proposer,
        'propose_date': bill.propose_date,
        'committee': bill.committee,
        'detail_link': bill.detail_link,
        'content': bill_content.get('content', ''),
        'assembly_result': bill.assembly_result
    }
    
    return render_template('LAWdetail.html',
                         bill=bill_data,
                         vote_stats=vote_stats,
                         user_vote=user_vote_type,
                         comments=comments_data,
                         reported_comment_ids=reported_comment_ids,
                         liked_comment_ids=liked_comment_ids,
                         comment_reports=comment_reports,
                         related_bills=related_bills_data,
                         has_more_comments=total_parent_comments > 5)

@app.route('/proposals')
def proposals_list():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # 공개된 제안만 표시 (또는 작성자 본인 것)
    ip_address = get_client_ip()
    query = Proposal.query.filter(
        db.or_(Proposal.is_public == True, Proposal.ip_address == ip_address)
    ).filter(Proposal.is_draft == False)
    
    pagination = query.order_by(Proposal.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # 페이지네이션 데이터
    pagination_data = {
        'current_page': page,
        'total_pages': pagination.pages,
        'has_prev': pagination.has_prev,
        'has_next': pagination.has_next,
        'page_range': get_page_range(page, pagination.pages),
        'page_size': per_page
    }
    
    def get_url_params(page_num=None):
        if page_num and page_num > 1:
            return f"page={page_num}"
        return ''
    
    pagination_data['prev_url_params'] = get_url_params(page - 1) if pagination.has_prev else ''
    pagination_data['next_url_params'] = get_url_params(page + 1) if pagination.has_next else ''
    pagination_data['get_url_params'] = get_url_params
    
    proposals_data = [{
        'id': p.id,
        'number': p.id,
        'title': p.title,
        'author_display_name': p.author or '익명',
        'created_date': p.created_at.strftime('%Y-%m-%d'),
        'view_count': p.view_count,
        'is_public': p.is_public
    } for p in pagination.items]
    
    return render_template('PROPlist.html',
                         page_title='입법제안',
                         proposals=proposals_data,
                         pagination=pagination_data,
                         user_can_create=True)  # 로그인 기능 없으므로 항상 True

@app.route('/proposals/new', methods=['GET', 'POST'])
def proposal_write():
    ip_address = get_client_ip()
    
    if request.method == 'POST':
        # 폼 데이터 수집
        form_data = {
            'title': request.form.get('title', '').strip(),
            'target_law': request.form.get('target_law', '').strip(),
            'draft_number': request.form.get('draft_number', '').strip(),
            'current_situation': request.form.get('current_situation', '').strip(),
            'problems': request.form.get('problems', '').strip(),
            'proposal_reasons': request.form.get('proposal_reasons', '').strip(),
            'improvement_type': request.form.get('improvement_type', 'improve'),
            'is_public': request.form.get('is_public', 'true').lower() == 'true',
            'is_draft': request.form.get('is_draft', 'false').lower() == 'true'
        }
        
        # 유효성 검사
        errors = []
        if not form_data['title']:
            errors.append('제목을 입력해주세요.')
        if not form_data['is_draft']:  # 임시저장이 아닌 경우만
            if not form_data['current_situation']:
                errors.append('현황을 입력해주세요.')
            if not form_data['proposal_reasons']:
                errors.append('제안사유를 입력해주세요.')
        
        if errors:
            return render_template('PROPwrite.html',
                                 page_title='입법제안 작성',
                                 form_data=form_data,
                                 error_message=', '.join(errors),
                                 is_edit_mode=False,
                                 allow_draft_save=True,
                                 has_draft=False)
        
        # 새 제안 생성
        proposal = Proposal(
            title=form_data['title'],
            target_law=form_data['target_law'],
            draft_number=form_data['draft_number'],
            current_situation=form_data['current_situation'],
            problems=form_data['problems'],
            proposal_reasons=form_data['proposal_reasons'],
            improvement_type=form_data['improvement_type'],
            is_public=form_data['is_public'],
            is_draft=form_data['is_draft'],
            ip_address=ip_address,
            author=get_anonymous_name(ip_address)
        )
        
        db.session.add(proposal)
        db.session.commit()
        
        if form_data['is_draft']:
            return render_template('PROPwrite.html',
                                 page_title='입법제안 작성',
                                 form_data=form_data,
                                 success_message='임시저장되었습니다.',
                                 is_edit_mode=False,
                                 allow_draft_save=True,
                                 has_draft=True)
        else:
            return redirect(url_for('proposal_detail', proposal_id=proposal.id))
    
    # GET 요청: 폼 표시
    # 임시저장된 글 확인
    draft = Proposal.query.filter_by(ip_address=ip_address, is_draft=True).first()
    
    form_data = {
        'title': '',
        'target_law': '',
        'draft_number': '',
        'current_situation': '',
        'problems': '',
        'proposal_reasons': '',
        'improvement_type': 'improve',
        'is_public': True
    }
    
    draft_restored = False
    if draft:
        form_data = {
            'title': draft.title,
            'target_law': draft.target_law or '',
            'draft_number': draft.draft_number or '',
            'current_situation': draft.current_situation or '',
            'problems': draft.problems or '',
            'proposal_reasons': draft.proposal_reasons or '',
            'improvement_type': draft.improvement_type or 'improve',
            'is_public': draft.is_public
        }
        draft_restored = True
    
    return render_template('PROPwrite.html',
                         page_title='입법제안 작성',
                         form_data=form_data,
                         form_action=url_for('proposal_write'),
                         is_edit_mode=False,
                         allow_draft_save=True,
                         has_draft=bool(draft),
                         draft_restored=draft_restored)

# app.py의 proposal_detail() 함수를 이것으로 교체하세요

@app.route('/proposals/<int:proposal_id>')
def proposal_detail(proposal_id):
    proposal = Proposal.query.get_or_404(proposal_id)
    proposal.view_count += 1
    db.session.commit()
    
    ip_address = get_client_ip()
    
    # 사용자의 투표 여부 확인
    user_vote = ProposalVote.query.filter_by(proposal_id=proposal_id, ip_address=ip_address).first()
    user_vote_type = user_vote.vote_type if user_vote else None
    
    # 투표 통계
    agree_count = ProposalVote.query.filter_by(proposal_id=proposal_id, vote_type='agree').count()
    disagree_count = ProposalVote.query.filter_by(proposal_id=proposal_id, vote_type='disagree').count()
    
    vote_stats = {
        'agree_count': agree_count,
        'disagree_count': disagree_count,
        'total_votes': agree_count + disagree_count
    }
    
    # 사용자가 이 제안을 신고했는지 확인
    user_reported_proposal = Report.query.filter_by(
        proposal_id=proposal_id,
        reporter_ip=ip_address
    ).first() is not None
    
    # 🔥 수정: 모든 댓글 가져오기 (부모 댓글과 답글 모두)
    parent_comments = Comment.query.filter_by(proposal_id=proposal_id, parent_id=None).order_by(Comment.created_at.desc()).limit(5).all()
    total_parent_comments = Comment.query.filter_by(proposal_id=proposal_id, parent_id=None).count()
    
    # 사용자가 신고한 댓글 ID들
    user_reports = Report.query.filter_by(reporter_ip=ip_address).all()
    user_reported_comments = [r.comment_id for r in user_reports if r.comment_id]
    
    # 🔥 수정: 사용자가 좋아요한 댓글 ID들
    user_likes = CommentLike.query.filter_by(ip_address=ip_address).all()
    liked_comment_ids = [l.comment_id for l in user_likes]
    
    # 🔥 수정: 댓글 데이터 준비 (좋아요 수 포함)
    comments_data = []
    comment_reports = {}
    
    for comment in parent_comments:
        # 좋아요 수 계산
        like_count = CommentLike.query.filter_by(comment_id=comment.id).count()
        
        comment_data = {
            'id': comment.id,
            'parent_id': comment.parent_id,  # 🔥 추가: parent_id 포함
            'author': comment.author or f'익명{comment.id}',
            'content': comment.content,
            'stance': comment.stance,
            'time_ago': time_ago(comment.created_at),
            'report_count': comment.report_count,
            'is_under_review': comment.is_under_review or comment.report_count >= 3,
            'is_reported_by_user': comment.id in user_reported_comments,
            'like_count': like_count,  # 🔥 추가: 좋아요 수
            'is_liked_by_user': comment.id in liked_comment_ids  # 🔥 추가: 사용자 좋아요 상태
        }
        comments_data.append(comment_data)
        comment_reports[str(comment.id)] = comment.report_count
    
    # 제안사유 파싱 (리스트 형태로 변환)
    proposal_reasons = proposal.proposal_reasons
    if proposal_reasons and '\n' in proposal_reasons:
        proposal_reasons = [reason.strip() for reason in proposal_reasons.split('\n') if reason.strip()]
    
    proposal_data = {
        'id': proposal.id,
        'title': proposal.title,
        'target_law': proposal.target_law,
        'draft_number': proposal.draft_number,
        'current_situation': proposal.current_situation,
        'problems': proposal.problems,
        'proposal_reasons': proposal_reasons,
        'created_date': proposal.created_at.strftime('%Y-%m-%d'),
        'view_count': proposal.view_count,
        'report_count': proposal.report_count
    }
    
    return render_template('PROPdetail.html',
                         proposal=proposal_data,
                         vote_stats=vote_stats,
                         user_vote=user_vote_type,
                         user_reported_proposal=user_reported_proposal,
                         user_reported_comments=user_reported_comments,
                         liked_comment_ids=liked_comment_ids,  # 🔥 추가: 좋아요한 댓글 ID들
                         comments=comments_data,
                         comment_reports=comment_reports,
                         has_more_comments=total_parent_comments > 5)

# AJAX API 엔드포인트들

@app.route('/api/bills/<int:bill_id>/vote', methods=['POST'])
def vote_bill(bill_id):
    data = request.get_json()
    vote_type = data.get('vote')
    ip_address = get_client_ip()
    
    if vote_type not in ['agree', 'disagree']:
        return jsonify({'error': 'Invalid vote type'}), 400
    
    # 기존 투표 확인
    existing_vote = BillVote.query.filter_by(bill_id=bill_id, ip_address=ip_address).first()
    
    current_user_vote = None
    
    if existing_vote:
        if existing_vote.vote_type == vote_type:
            # 같은 투표 취소
            db.session.delete(existing_vote)
            current_user_vote = None
        else:
            # 투표 변경
            existing_vote.vote_type = vote_type
            current_user_vote = vote_type
    else:
        # 새 투표
        new_vote = BillVote(bill_id=bill_id, ip_address=ip_address, vote_type=vote_type)
        db.session.add(new_vote)
        current_user_vote = vote_type
    
    db.session.commit()
    
    # 업데이트된 투표 수 반환
    agree_count = BillVote.query.filter_by(bill_id=bill_id, vote_type='agree').count()
    disagree_count = BillVote.query.filter_by(bill_id=bill_id, vote_type='disagree').count()
    
    return jsonify({
        'vote_counts': {
            'agree': agree_count,
            'disagree': disagree_count
        },
        'total_votes': agree_count + disagree_count,
        'user_vote': current_user_vote
    })


@app.route('/api/bills/<int:bill_id>/comments', methods=['POST'])
def add_bill_comment(bill_id):
    data = request.get_json()
    content = data.get('content', '').strip()
    stance = data.get('stance')
    parent_id = data.get('parent_id')  # 🔥 추가: 답글 지원
    ip_address = get_client_ip()
    
    if not content or stance not in ['agree', 'disagree']:
        return jsonify({'error': 'Invalid data'}), 400
    
    # 투표 확인
    user_vote = BillVote.query.filter_by(bill_id=bill_id, ip_address=ip_address).first()
    if not user_vote:
        return jsonify({'error': 'Vote required'}), 403
    
    # 🔥 개선: parent_id가 있는 경우 부모 댓글 확인
    if parent_id:
        parent_comment = Comment.query.get(parent_id)
        if not parent_comment or parent_comment.bill_id != bill_id:
            return jsonify({'error': 'Invalid parent comment'}), 400
        
        # 🔥 답글의 답글인 경우, 최상위 부모로 설정 (깊이 제한)
        if parent_comment.parent_id:
            parent_id = parent_comment.parent_id
    
    comment = Comment(
        bill_id=bill_id,
        parent_id=parent_id,
        content=content,
        stance=stance,
        ip_address=ip_address,
        author=get_anonymous_name(ip_address)
    )
    
    db.session.add(comment)
    db.session.commit()
    
    # 🔥 개선: 생성된 댓글의 좋아요 정보도 함께 반환
    like_count = CommentLike.query.filter_by(comment_id=comment.id).count()
    is_liked_by_user = CommentLike.query.filter_by(
        comment_id=comment.id, 
        ip_address=ip_address
    ).first() is not None
    
    return jsonify({
        'id': comment.id,
        'author': comment.author,
        'content': comment.content,
        'stance': comment.stance,
        'time_ago': '방금 전',
        'parent_id': comment.parent_id,
        'like_count': like_count,
        'report_count': 0,
        'is_under_review': False,
        'is_liked_by_user': is_liked_by_user,
        'is_reported_by_user': False
    })
    
def crawl_bill_content(bill_number):
    """국회 법률안 상세 페이지에서 제안이유 및 주요내용 크롤링 (중복 문제 해결)"""
    if not bill_number:
        return {'content': ''}
    
    url = f"https://likms.assembly.go.kr/bill/billDetail.do?billId={bill_number}"
    
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 🔥 핵심 해결책: 숨겨진 전체 내용만 가져오기
        # 1순위: summaryHiddenContentDiv (전체 내용)
        hidden_content = soup.find('div', id='summaryHiddenContentDiv')
        
        if hidden_content:
            content_text = hidden_content.get_text()
        else:
            # 2순위: summaryContentDiv (기본 표시 - fallback)
            content_div = soup.find('div', id='summaryContentDiv')
            if content_div:
                content_text = content_div.get_text()
            else:
                # 3순위: 전체 텍스트에서 찾기 (기존 방식)
                content_text = soup.get_text()
                
                if "▶ 제안이유 및 주요내용" in content_text:
                    start_marker = "▶ 제안이유 및 주요내용"
                    start_idx = content_text.find(start_marker)
                    if start_idx != -1:
                        start_idx += len(start_marker)
                        content_text = content_text[start_idx:]
        
        # 🔥 기본 정리만 (중복 제거 알고리즘 불필요!)
        content = clean_content_basic(content_text)
        
        return {'content': content.strip()}
                
    except Exception as e:
        print(f"크롤링 오류: {e}")
    
    return {'content': ''}


def clean_content_basic(content):
    """기본적인 내용 정리만"""
    import re
    
    # 기본 정리
    content = re.sub(r'[ \t]+', ' ', content)
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = content.strip()
    
    # UI 관련 텍스트 제거
    ui_patterns = [
        "+ 더보기감추기",
        "더보기감추기", 
        "+ 더보기",
        "더보기",
        "감추기",
        "펼치기",
        "접기"
    ]
    
    for pattern in ui_patterns:
        content = content.replace(pattern, "")
    
    # 구조적 끝점으로 자르기
    end_markers = [
        '위원회 심사', '심사경과', '검토보고', '전문위원 검토보고',
        '◎ 검토의견', '◎ 위원회 심사', '◎ 심사경과',
        '▶ 검토의견', '▶ 위원회 심사', '▶ 심사경과',
        '○ 검토의견', '○ 위원회 심사', '○ 심사경과'
    ]
    
    end_idx = len(content)
    for marker in end_markers:
        marker_idx = content.find(marker)
        if marker_idx != -1 and marker_idx < end_idx:
            end_idx = marker_idx
    
    content = content[:end_idx]
    
    # 고립된 기호 제거
    lines = content.split('\n')
    cleaned_lines = []
    
    for line in lines:
        stripped_line = line.strip()
        
        # 기호만 있는 줄은 제거
        if re.match(r'^[▶○◎◦■□●◆※\-\*\+\s]*$', stripped_line):
            continue
        
        if stripped_line:
            cleaned_lines.append(line)
        else:
            cleaned_lines.append(line)  # 빈 줄 유지
    
    # 최종 정리
    content = '\n'.join(cleaned_lines)
    while content.startswith('\n'):
        content = content[1:]
    
    return content

@app.route('/api/bills/<int:bill_id>/comments', methods=['GET'])
def get_bill_comments(bill_id):
    offset = request.args.get('offset', 0, type=int)
    limit = 5
    
    # 부모 댓글들 가져오기 (offset 적용)
    parent_comments = Comment.query.filter_by(bill_id=bill_id, parent_id=None)\
        .order_by(Comment.created_at.desc())\
        .offset(offset).limit(limit).all()
    
    # 더 있는지 확인
    total_parent_comments = Comment.query.filter_by(bill_id=bill_id, parent_id=None).count()
    has_more = (offset + limit) < total_parent_comments
    
    # 댓글 데이터 처리
    ip_address = get_client_ip()
    user_reports = Report.query.filter_by(reporter_ip=ip_address).all()
    reported_comment_ids = [r.comment_id for r in user_reports if r.comment_id]
    user_likes = CommentLike.query.filter_by(ip_address=ip_address).all()
    liked_comment_ids = [l.comment_id for l in user_likes]
    
    comments_data = []
    for comment in parent_comments:
        # 부모 댓글 처리
        like_count = CommentLike.query.filter_by(comment_id=comment.id).count()
        
        comment_data = {
            'id': comment.id,
            'parent_id': comment.parent_id,
            'author': comment.author or f'익명{comment.id}',
            'content': comment.content,
            'stance': comment.stance,
            'time_ago': time_ago(comment.created_at),
            'report_count': comment.report_count,
            'is_under_review': comment.is_under_review or comment.report_count >= 3,
            'is_reported_by_user': comment.id in reported_comment_ids,
            'like_count': like_count,
            'is_liked_by_user': comment.id in liked_comment_ids
        }
        comments_data.append(comment_data)
        
        # ✅ 여기에 답글 처리 추가
        replies = Comment.query.filter_by(
            bill_id=bill_id,
            parent_id=comment.id
        ).order_by(Comment.created_at.asc()).all()
        
        for reply in replies:
            reply_like_count = CommentLike.query.filter_by(comment_id=reply.id).count()
            reply_data = {
                'id': reply.id,
                'parent_id': reply.parent_id,
                'author': reply.author or f'익명{reply.id}',
                'content': reply.content,
                'stance': reply.stance,
                'time_ago': time_ago(reply.created_at),
                'report_count': reply.report_count,
                'is_under_review': reply.is_under_review or reply.report_count >= 3,
                'is_reported_by_user': reply.id in reported_comment_ids,
                'like_count': reply_like_count,
                'is_liked_by_user': reply.id in liked_comment_ids
            }
            comments_data.append(reply_data)
    
    return jsonify({
        'comments': comments_data,
        'has_more': has_more
    })

# 입법제안 댓글 더보기 API
@app.route('/api/proposals/<int:proposal_id>/comments', methods=['GET'])
def get_proposal_comments(proposal_id):
    offset = request.args.get('offset', 0, type=int)
    limit = 5
    
    # 부모 댓글들 가져오기 (offset 적용)
    parent_comments = Comment.query.filter_by(proposal_id=proposal_id, parent_id=None)\
        .order_by(Comment.created_at.desc())\
        .offset(offset).limit(limit).all()
    
    # 더 있는지 확인
    total_parent_comments = Comment.query.filter_by(proposal_id=proposal_id, parent_id=None).count()
    has_more = (offset + limit) < total_parent_comments
    
    # 댓글 데이터 처리
    ip_address = get_client_ip()
    user_reports = Report.query.filter_by(reporter_ip=ip_address).all()
    reported_comment_ids = [r.comment_id for r in user_reports if r.comment_id]
    user_likes = CommentLike.query.filter_by(ip_address=ip_address).all()
    liked_comment_ids = [l.comment_id for l in user_likes]
    
    comments_data = []
    for comment in parent_comments:
        # 부모 댓글 처리
        like_count = CommentLike.query.filter_by(comment_id=comment.id).count()
        
        comment_data = {
            'id': comment.id,
            'parent_id': comment.parent_id,
            'author': comment.author or f'익명{comment.id}',
            'content': comment.content,
            'stance': comment.stance,
            'time_ago': time_ago(comment.created_at),
            'report_count': comment.report_count,
            'is_under_review': comment.is_under_review or comment.report_count >= 3,
            'is_reported_by_user': comment.id in reported_comment_ids,
            'like_count': like_count,
            'is_liked_by_user': comment.id in liked_comment_ids
        }
        comments_data.append(comment_data)
        
        # ✅ 답글 처리 추가
        replies = Comment.query.filter_by(
            proposal_id=proposal_id,
            parent_id=comment.id
        ).order_by(Comment.created_at.asc()).all()
        
        for reply in replies:
            reply_like_count = CommentLike.query.filter_by(comment_id=reply.id).count()
            reply_data = {
                'id': reply.id,
                'parent_id': reply.parent_id,
                'author': reply.author or f'익명{reply.id}',
                'content': reply.content,
                'stance': reply.stance,
                'time_ago': time_ago(reply.created_at),
                'report_count': reply.report_count,
                'is_under_review': reply.is_under_review or reply.report_count >= 3,
                'is_reported_by_user': reply.id in reported_comment_ids,
                'like_count': reply_like_count,
                'is_liked_by_user': reply.id in liked_comment_ids
            }
            comments_data.append(reply_data)
    
    return jsonify({
        'comments': comments_data,
        'has_more': has_more
    })
    
@app.route('/api/proposals/<int:proposal_id>/vote', methods=['POST'])
def vote_proposal(proposal_id):
    data = request.get_json()
    vote_type = data.get('vote')
    ip_address = get_client_ip()
    
    if vote_type not in ['agree', 'disagree']:
        return jsonify({'error': 'Invalid vote type'}), 400
    
    # 기존 투표 확인
    existing_vote = ProposalVote.query.filter_by(proposal_id=proposal_id, ip_address=ip_address).first()
    
    current_user_vote = None  # 사용자의 현재 투표 상태
    
    if existing_vote:
        if existing_vote.vote_type == vote_type:
            # 같은 투표 취소
            db.session.delete(existing_vote)
            current_user_vote = None  # 투표 취소됨
        else:
            # 투표 변경
            existing_vote.vote_type = vote_type
            current_user_vote = vote_type
    else:
        # 새 투표
        new_vote = ProposalVote(proposal_id=proposal_id, ip_address=ip_address, vote_type=vote_type)
        db.session.add(new_vote)
        current_user_vote = vote_type
    
    db.session.commit()
    
    # 업데이트된 투표 수 계산
    agree_count = ProposalVote.query.filter_by(proposal_id=proposal_id, vote_type='agree').count()
    disagree_count = ProposalVote.query.filter_by(proposal_id=proposal_id, vote_type='disagree').count()
    
    return jsonify({
        'vote_counts': {
            'agree': agree_count,
            'disagree': disagree_count
        },
        'total_votes': agree_count + disagree_count,
        'user_vote': current_user_vote  # 사용자의 현재 투표 상태
    })

# app.py의 add_proposal_comment() 함수를 이것으로 교체하세요

@app.route('/api/proposals/<int:proposal_id>/comments', methods=['POST'])
def add_proposal_comment(proposal_id):
    data = request.get_json()
    content = data.get('content', '').strip()
    stance = data.get('stance')
    parent_id = data.get('parent_id')
    ip_address = get_client_ip()
    
    if not content or stance not in ['agree', 'disagree']:
        return jsonify({'error': 'Invalid data'}), 400
    
    # 투표 확인
    user_vote = ProposalVote.query.filter_by(proposal_id=proposal_id, ip_address=ip_address).first()
    if not user_vote:
        return jsonify({'error': 'Vote required'}), 403
    
    # 🔥 개선: parent_id가 있는 경우 부모 댓글 확인
    if parent_id:
        parent_comment = Comment.query.get(parent_id)
        if not parent_comment or parent_comment.proposal_id != proposal_id:
            return jsonify({'error': 'Invalid parent comment'}), 400
        
        # 🔥 답글의 답글인 경우, 최상위 부모로 설정 (깊이 제한)
        if parent_comment.parent_id:
            parent_id = parent_comment.parent_id
    
    comment = Comment(
        proposal_id=proposal_id,
        parent_id=parent_id,
        content=content,
        stance=stance,
        ip_address=ip_address,
        author=get_anonymous_name(ip_address)
    )
    
    db.session.add(comment)
    db.session.commit()
    
    # 🔥 개선: 생성된 댓글의 좋아요 정보도 함께 반환
    like_count = CommentLike.query.filter_by(comment_id=comment.id).count()
    is_liked_by_user = CommentLike.query.filter_by(
        comment_id=comment.id, 
        ip_address=ip_address
    ).first() is not None
    
    return jsonify({
        'id': comment.id,
        'author': comment.author,
        'content': comment.content,
        'stance': comment.stance,
        'time_ago': '방금 전',
        'parent_id': comment.parent_id,
        'like_count': like_count,
        'report_count': 0,
        'is_under_review': False,
        'is_liked_by_user': is_liked_by_user,
        'is_reported_by_user': False
    })

@app.route('/api/proposals/<int:proposal_id>/report', methods=['POST'])
def report_proposal(proposal_id):
    ip_address = get_client_ip()
    
    # 이미 신고했는지 확인
    existing_report = Report.query.filter_by(proposal_id=proposal_id, reporter_ip=ip_address).first()
    if existing_report:
        return jsonify({'error': 'Already reported'}), 400
    
    # 신고 추가
    report = Report(proposal_id=proposal_id, reporter_ip=ip_address)
    db.session.add(report)
    
    # 제안의 신고 수 증가
    proposal = Proposal.query.get(proposal_id)
    if proposal:
        proposal.report_count += 1
    
    db.session.commit()
    
    # ✅ 신고수 정보 포함하여 반환
    return jsonify({
        'success': True,
        'report_count': proposal.report_count,
        'message': 'Report submitted successfully',
        'new_report_text': f'신고됨 ({proposal.report_count})' if proposal.report_count > 1 else '신고됨'
    })

@app.route('/api/autocomplete/bills')
def autocomplete_bills():
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])
    
    bills = Bill.query.filter(Bill.name.contains(query)).limit(10).all()
    results = [{'id': b.id, 'name': b.name} for b in bills]
    
    return jsonify(results)

@app.route('/api/autocomplete/members')
def autocomplete_members():
    query = request.args.get('q', '')
    if len(query) < 1:
        return jsonify([])
    
    members = Member.query.filter(Member.name.contains(query)).limit(10).all()
    results = [{'id': m.id, 'name': m.name, 'party': m.party, 'photo_url': m.photo_url} for m in members]
    
    return jsonify(results)

# 유틸리티 함수들

def get_page_range(current_page, total_pages, window=2):
    """페이지네이션 범위 계산"""
    if total_pages <= 7:
        return list(range(1, total_pages + 1))
    
    if current_page <= window + 1:
        return list(range(1, window * 2 + 2)) + ['...', total_pages]
    elif current_page >= total_pages - window:
        return [1, '...'] + list(range(total_pages - window * 2, total_pages + 1))
    else:
        return [1, '...'] + list(range(current_page - window, current_page + window + 1)) + ['...', total_pages]

def calculate_age(birth_year):
    """출생년도로 나이 계산"""
    if not birth_year:
        return None
    current_year = datetime.now().year
    return current_year - birth_year + 1

# 데이터베이스 초기화 함수 (개발용)
def init_sample_data():
    """샘플 데이터 초기화"""
    # 샘플 국회의원 데이터
    sample_members = [
        {'name': '홍길동', 'party': '더불어민주당', 'district': '서울 종로구', 'session_num': 22},
        {'name': '김철수', 'party': '국민의힘', 'district': '부산 해운대구갑', 'session_num': 22},
        {'name': '이영희', 'party': '정의당', 'district': '비례대표', 'session_num': 22},
        {'name': '박민수', 'party': '국민의당', 'district': '광주 동구남구갑', 'session_num': 21},
        {'name': '최정훈', 'party': '무소속', 'district': '제주 제주시갑', 'session_num': 21},
    ]
    
    for data in sample_members:
        if not Member.query.filter_by(name=data['name']).first():
            member = Member(**data)
            db.session.add(member)
    
    # 샘플 법률안 데이터
    sample_bills = [
        {
            'number': '2100001',
            'name': '개인정보 보호법 일부개정법률안',
            'proposer': '홍길동',
            'propose_date': '2024-01-15',
            'committee': '정무위원회'
        },
        {
            'number': '2100002',
            'name': '국민건강보험법 일부개정법률안',
            'proposer': '김철수',
            'propose_date': '2024-01-20',
            'committee': '보건복지위원회'
        },
        {
            'number': '2100003',
            'name': '교육기본법 일부개정법률안',
            'proposer': '이영희',
            'propose_date': '2024-02-01',
            'committee': '교육위원회'
        },
    ]
    
    for data in sample_bills:
        if not Bill.query.filter_by(number=data['number']).first():
            bill = Bill(**data)
            db.session.add(bill)
    
    db.session.commit()

def load_election_csv():
    """CSV 파일에서 국회의원 선거 데이터 로드"""
    csv_file = '국회의원_당선자_통합명부_20_21_22대.csv'
    
    if not os.path.exists(csv_file):
        print(f"CSV 파일을 찾을 수 없습니다: {csv_file}")
        return
    
    import csv
    
    with open(csv_file, 'r', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        
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
                session_num = int(age) if age else None
                age = None  # age 열이 실제로는 대수(session)를 나타냄
            except:
                session_num = None
            
            # 득표율 파싱
            vote_rate = None
            if vote_percent and vote_percent != 'nan%':
                try:
                    vote_rate = float(vote_percent.replace('%', ''))
                except:
                    pass
            
            # 정당 추출 (선거구에서 추론 - 실제로는 API에서 가져와야 함)
            party = None
            if '비례대표' in constituency:
                party = '비례대표'
            
            # 기존 의원 확인 또는 새로 생성
            member = Member.query.filter_by(name=name, session_num=session_num).first()
            
            if not member:
                member = Member(
                    name=name,
                    session_num=session_num,
                    district=constituency,
                    vote_rate=vote_rate
                )
                db.session.add(member)
                print(f"추가: {name} ({session_num}대) - {constituency} ({vote_percent})")
            else:
                # 기존 의원 정보 업데이트
                member.district = constituency
                member.vote_rate = vote_rate
                print(f"업데이트: {name} ({session_num}대) - {constituency} ({vote_percent})")
        
        db.session.commit()
        print("CSV 데이터 로드 완료!")



# app.py에 검색 라우트 추가 (오류 핸들러 위에 추가)

@app.route('/search')
def search():
    query = request.args.get('q', '')
    
    if not query:
        return redirect(url_for('index'))
    
    # 국회의원 검색
    members = Member.query.filter(
        db.or_(
            Member.name.contains(query),
            Member.party.contains(query),
            Member.district.contains(query)
        )
    ).all()
    
    if len(members) > 0:
        # 국회의원 결과가 있으면 국회의원 페이지로
        return redirect(url_for('members_list', search=query))
    else:
        # 국회의원 결과가 없으면 법률안 페이지로
        return redirect(url_for('bills_list', search=query))
        
# 좋아요 API 엔드포인트
@app.route('/api/comments/<int:comment_id>/like', methods=['POST'])
def toggle_comment_like(comment_id):
    ip_address = get_client_ip()
    
    # 기존 좋아요 확인
    existing_like = CommentLike.query.filter_by(
        comment_id=comment_id,
        ip_address=ip_address
    ).first()
    
    if existing_like:
        # 좋아요 취소
        db.session.delete(existing_like)
        liked = False
    else:
        # 좋아요 추가
        new_like = CommentLike(
            comment_id=comment_id,
            ip_address=ip_address
        )
        db.session.add(new_like)
        liked = True
    
    db.session.commit()
    
    # 총 좋아요 수 계산
    like_count = CommentLike.query.filter_by(comment_id=comment_id).count()
    
    return jsonify({
        'liked': liked,
        'like_count': like_count
    })

@app.route('/api/comments/<int:parent_id>/reply', methods=['POST'])
def add_reply(parent_id):
    data = request.get_json()
    content = data.get('content', '').strip()
    stance = data.get('stance')
    ip_address = get_client_ip()
    
    if not content:
        return jsonify({'error': 'Content required'}), 400
    
    # 부모 댓글 확인
    parent_comment = Comment.query.get_or_404(parent_id)
    
    # 투표 확인 (법률안 또는 입법제안)
    if parent_comment.bill_id:
        user_vote = BillVote.query.filter_by(
            bill_id=parent_comment.bill_id, 
            ip_address=ip_address
        ).first()
    elif parent_comment.proposal_id:
        user_vote = ProposalVote.query.filter_by(
            proposal_id=parent_comment.proposal_id, 
            ip_address=ip_address
        ).first()
    else:
        return jsonify({'error': 'Invalid parent comment'}), 400
    
    if not user_vote:
        return jsonify({'error': 'Vote required'}), 403
    
    # 답글 생성
    reply = Comment(
        bill_id=parent_comment.bill_id,
        proposal_id=parent_comment.proposal_id,
        parent_id=parent_id,
        content=content,
        stance=stance or user_vote.vote_type,  # 사용자 투표와 동일한 stance
        ip_address=ip_address,
        author=get_anonymous_name(ip_address)
    )
    
    db.session.add(reply)
    db.session.commit()
    
    return jsonify({
        'id': reply.id,
        'author': reply.author,
        'content': reply.content,
        'stance': reply.stance,
        'time_ago': '방금 전',
        'parent_id': reply.parent_id,
        'like_count': 0,
        'report_count': 0,
        'is_under_review': False,
        'is_liked_by_user': False,
        'is_reported_by_user': False
    })

@app.route('/api/comments/<int:comment_id>/report', methods=['POST'])
def report_comment(comment_id):
    ip_address = get_client_ip()
    
    # IP 차단 확인
    if BlockedIP.query.filter_by(ip_address=ip_address).first():
        return jsonify({'error': 'Blocked IP'}), 403
    
    # 이미 신고했는지 확인
    existing_report = Report.query.filter_by(
        comment_id=comment_id, 
        reporter_ip=ip_address
    ).first()
    
    if existing_report:
        return jsonify({'error': 'Already reported'}), 400
    
    # 신고 추가
    report = Report(comment_id=comment_id, reporter_ip=ip_address)
    db.session.add(report)
    
    # 댓글의 신고 수 증가
    comment = Comment.query.get(comment_id)
    if comment:
        comment.report_count += 1
        is_under_review = comment.report_count >= 3
        if is_under_review:
            comment.is_under_review = True
            
        # 특정 IP가 너무 많은 신고를 하는 경우 차단
        reporter_total = Report.query.filter_by(reporter_ip=ip_address).count()
        if reporter_total > 50:  # 임계값
            blocked = BlockedIP(
                ip_address=ip_address,
                reason='과도한 신고'
            )
            db.session.add(blocked)
    
    db.session.commit()
    
    # ✅ 신고수와 상태 정보 모두 반환
    return jsonify({
        'success': True,
        'report_count': comment.report_count,
        'is_under_review': comment.is_under_review,
        'message': 'Report submitted successfully',
        'new_report_text': f'신고됨 ({comment.report_count})' if comment.report_count > 1 else '신고됨'
    })


# 미들웨어로 차단된 IP 확인
@app.before_request
def check_blocked_ip():
    # 관리자 관련 모든 경로 제외
    admin_paths = [
        '/admin/',
        '/admin/lawgg2025',
        '/admin/dashboard', 
        '/admin/logout',
        '/admin/proposals',
        '/admin/comments',
        '/admin/ban-ip',
        '/admin/unban-ip',
        '/admin/reset-db'
    ]
    
    # 현재 경로가 관리자 경로면 차단 검사 생략
    if any(request.path.startswith(path) for path in admin_paths):
        return
    
    ip_address = get_client_ip()
    blocked = BlockedIP.query.filter_by(ip_address=ip_address).first()
    
    if blocked:
        if request.endpoint and 'api' in request.endpoint:
            return jsonify({'error': 'Access denied'}), 403
        else:
            return render_template('blocked.html', reason=blocked.reason), 403

@app.route('/debug/ip')
def debug_ip():
    ip_address = get_client_ip()
    headers = dict(request.headers)
    
    return jsonify({
        'detected_ip': ip_address,
        'remote_addr': request.remote_addr,
        'x_forwarded_for': request.headers.get('X-Forwarded-For'),
        'x_real_ip': request.headers.get('X-Real-IP'),
        'headers': headers
    })
# 오류 핸들러
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Page not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({'error': 'Internal server error'}), 500

@app.route('/favicon.ico')
def favicon():
    return '', 204  # No Content
    
#with app.app_context():
    #db.create_all()


sync_status = {
    'running': False,
    'progress': 0,
    'message': '',
    'error': None,
    'completed': False,
    'start_time': None,
    'processed_count': 0
}

# app.py의 background_sync() 함수 수정

def background_sync():
    """백그라운드에서 동기화 실행"""
    global sync_status
    
    # Flask 애플리케이션 컨텍스트 설정
    with app.app_context():
        try:
            sync_status.update({
                'running': True,
                'progress': 5,
                'message': 'API 연결 테스트 중...',
                'error': None,
                'completed': False,
                'start_time': datetime.now().isoformat(),
                'processed_count': 0
            })
            
            try:
                # 🔥 수정된 부분 🔥
                from sync_data import test_api_connection, cleanup_and_sync
            except ImportError as e:
                sync_status.update({
                    'running': False,
                    'error': f'함수 import 실패: {str(e)}',
                    'completed': True,
                    'progress': 0
                })
                return
            
            # API 연결 테스트
            sync_status.update({
                'progress': 10,
                'message': 'API 연결 확인 중...'
            })
            
            if not test_api_connection():
                sync_status.update({
                    'running': False,
                    'error': 'API 연결 실패',
                    'completed': True,
                    'progress': 0
                })
                return
            
            sync_status.update({
                'progress': 30,
                'message': '중복 데이터 정리 및 전체 동기화 시작...'
            })
            
            # 🔥 실제 동기화 실행 (중복 정리 + 국회의원 + 법률안) 🔥
            cleanup_and_sync()
            
            sync_status.update({
                'progress': 90,
                'message': '데이터 저장 중...'
            })
            
            time.sleep(1)
            
            # 완료 - 최종 결과 확인
            member_count = Member.query.count()
            bill_count = Bill.query.count()
            
            sync_status.update({
                'running': False,
                'progress': 100,
                'message': f'동기화 완료! 국회의원 {member_count}명, 법률안 {bill_count}건 업데이트 (중복 정리 포함)',
                'completed': True,
                'processed_count': member_count + bill_count
            })
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            
            sync_status.update({
                'running': False,
                'error': f'동기화 중 오류 발생: {str(e)}',
                'completed': True,
                'progress': 0,
                'error_detail': error_detail
            })

@app.route('/sync/start')
def start_sync():
    """동기화 시작"""
    global sync_status
    
    if sync_status['running']:
        return jsonify({
            'status': 'error',
            'message': '이미 동기화가 진행 중입니다. 잠시 후 다시 시도해주세요.'
        })
    
    # 상태 초기화
    sync_status = {
        'running': False,
        'progress': 0,
        'message': '',
        'error': None,
        'completed': False,
        'start_time': None,
        'processed_count': 0
    }
    
    # 백그라운드 스레드로 실행
    thread = threading.Thread(target=background_sync)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'status': 'success',
        'message': '동기화가 시작되었습니다. 진행상황을 확인해주세요.'
    })

@app.route('/sync/status')
def sync_status_api():
    """동기화 진행상황 확인"""
    return jsonify(sync_status)

@app.route('/sync/test')
def test_api():
    """국회 API 연결 테스트만"""
    try:
        from sync_data import test_api_connection
        
        if test_api_connection():
            return jsonify({
                "status": "success",
                "message": "국회 OpenAPI 연결 성공!"
            })
        else:
            return jsonify({
                "status": "error",
                "message": "국회 OpenAPI 연결 실패"
            }), 500
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"테스트 중 오류 발생: {str(e)}"
        }), 500

@app.route('/debug/api')
def debug_api():
    """API 디버그 정보"""
    try:
        import requests
        
        # 기본 연결 테스트
        test_url = "https://open.assembly.go.kr/portal/openapi/ALLNAMEMBER"
        params = {
            'KEY': 'a3fada8210244129907d945abe2beada',
            'Type': 'xml',
            'pIndex': 1,
            'pSize': 1
        }
        
        response = requests.get(test_url, params=params, timeout=30)
        
        return jsonify({
            'status': 'debug',
            'url': test_url,
            'params': params,
            'status_code': response.status_code,
            'response_text': response.text[:1000],
            'headers': dict(response.headers)
        })
        
    except Exception as e:
        return jsonify({
            'status': 'debug_error',
            'error': str(e),
            'error_type': type(e).__name__
        })

@app.route('/admin/reset-db')
def reset_database():
    """데이터베이스 초기화 (주의: 모든 데이터 삭제)"""
    try:
        # 모든 테이블 삭제 후 재생성
        db.drop_all()
        db.create_all()
        
        return jsonify({
            'status': 'success',
            'message': '데이터베이스가 초기화되었습니다. 모든 데이터가 삭제되었습니다.'
        })
    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': f'초기화 실패: {str(e)}'
        }), 500

@app.route('/sync/bills')
def sync_bills_route():
    """법률안 데이터 동기화"""
    try:
        from sync_data import sync_bills_from_api
        sync_bills_from_api()
        
        return jsonify({
            "status": "success",
            "message": "20, 21, 22대 법률안 데이터 동기화 완료!"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"오류 발생: {str(e)}"
        }), 500

@app.route('/sync/all')
def sync_all_route():
    """전체 데이터 동기화 (국회의원 + 법률안)"""
    try:
        from sync_data import sync_all_data
        sync_all_data()
        
        return jsonify({
            "status": "success",
            "message": "전체 데이터 동기화 완료!"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"오류 발생: {str(e)}"
        }), 500
        
# 메인 실행
if __name__ == '__main__':
    with app.app_context():
        # 데이터베이스 테이블 생성
        db.create_all()

        
        # 데이터가 없으면 동기화 실행
        if Member.query.count() == 0:
            print("데이터베이스가 비어있습니다. 초기 데이터를 로드합니다...")
            from sync_data import sync_members_from_api, sync_bills_from_api
            
            # API에서 데이터 가져오기
            sync_members_from_api()
            sync_bills_from_api()
            
            print("초기 데이터 로드 완료!")

        member_count = Member.query.count()
        bill_count = Bill.query.count()
        
        print(f"\n=== 최종 결과 ===")
        print(f"총 국회의원 수: {member_count}명")
        print(f"총 법률안 수: {bill_count}개")

        
    app.run(debug=True, host='0.0.0.0', port=5000)
