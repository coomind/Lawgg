from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, timedelta
import requests
import json
import csv
import os
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import re
from bs4 import BeautifulSoup

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # 실제 배포시 변경 필요
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lawgg.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# API 키 설정
ASSEMBLY_API_KEY = '79deed587e6043f291a36420cfd972de'

db = SQLAlchemy(app)
CORS(app)

# 데이터베이스 모델들
class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    party = db.Column(db.String(50))
    district = db.Column(db.String(100))
    photo_url = db.Column(db.String(200))
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    education = db.Column(db.Text)
    career = db.Column(db.Text)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(100))
    homepage = db.Column(db.String(200))
    vote_rate = db.Column(db.Float)
    view_count = db.Column(db.Integer, default=0)
    session_num = db.Column(db.Integer)  # 20, 21, 22대
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
        'view_count': member.view_count
    } for member in trending_members]
    
    return render_template('index.html',
                         trending_bills=trending_bills_data,
                         trending_members=trending_members_data)

@app.route('/members')
def members_list():
    page = request.args.get('page', 1, type=int)
    party = request.args.get('party', '전체')
    per_page = 20
    
    query = Member.query
    if party and party != '전체':
        query = query.filter_by(party=party)
    
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # 정당 목록
    parties = [
        {'code': '전체', 'name': '전체'},
        {'code': '더불어민주당', 'name': '더불어민주당'},
        {'code': '국민의힘', 'name': '국민의힘'},
        {'code': '정의당', 'name': '정의당'},
        {'code': '국민의당', 'name': '국민의당'},
        {'code': '무소속', 'name': '무소속'}
    ]
    
    # 페이지네이션 데이터
    pagination_data = {
        'current_page': page,
        'total_pages': pagination.pages,
        'has_prev': pagination.has_prev,
        'has_next': pagination.has_next,
        'page_range': get_page_range(page, pagination.pages),
        'prev_url_params': f"page={page-1}&party={party}" if pagination.has_prev else '',
        'next_url_params': f"page={page+1}&party={party}" if pagination.has_next else '',
        'page_size': per_page
    }
    
    # URL 파라미터 생성 함수
    def get_url_params(page_num):
        params = []
        if page_num > 1:
            params.append(f"page={page_num}")
        if party != '전체':
            params.append(f"party={party}")
        return '&'.join(params)
    
    pagination_data['get_url_params'] = get_url_params
    
    members_data = [{
        'id': m.id,
        'name': m.name,
        'party': m.party,
        'age': calculate_age(m.age) if m.age else None,
        'gender': m.gender,
        'photo_url': m.photo_url
    } for m in pagination.items]
    
    return render_template('NAlist.html',
                         page_title='국회의원 목록',
                         members=members_data,
                         parties=parties,
                         current_party=party,
                         pagination=pagination_data)

@app.route('/members/<int:member_id>')
def member_detail(member_id):
    member = Member.query.get_or_404(member_id)
    member.view_count += 1
    db.session.commit()
    
    # 해당 의원이 발의한 법률안
    bills = Bill.query.filter(Bill.proposer.contains(member.name)).limit(10).all()
    
    # 학력/경력 분리
    education = []
    career = []
    if member.career:
        items = member.career.split(',')
        for item in items:
            if '학교' in item or '학원' in item:
                education.append(item.strip())
            else:
                career.append(item.strip())
    
    member_data = {
        'id': member.id,
        'name': member.name,
        'party': member.party,
        'district_name': member.district,
        'photo_url': member.photo_url,
        'education': education,
        'career': career[:5],  # 대표 경력 5개만
        'phone': member.phone,
        'email': member.email,
        'homepage': member.homepage,
        'vote_rate': member.vote_rate,
        'terms': [{'session': member.session_num}] if member.session_num else []
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
    
    query = Bill.query
    
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
    
    return render_template('LAWlist.html',
                         page_title='법률안 목록',
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
    
    # 댓글 가져오기
    comments = Comment.query.filter_by(bill_id=bill_id, parent_id=None).order_by(Comment.created_at.desc()).limit(10).all()
    
    # 사용자가 신고한 댓글 ID들
    user_reports = Report.query.filter_by(reporter_ip=ip_address).all()
    reported_comment_ids = [r.comment_id for r in user_reports if r.comment_id]
    
    # 댓글 데이터 준비
    comments_data = []
    comment_reports = {}
    
    for comment in comments:
        comment_data = {
            'id': comment.id,
            'author': comment.author or f'익명{comment.id}',
            'content': comment.content,
            'stance': comment.stance,
            'time_ago': time_ago(comment.created_at),
            'report_count': comment.report_count,
            'is_under_review': comment.is_under_review or comment.report_count >= 3,
            'is_reported_by_user': comment.id in reported_comment_ids
        }
        comments_data.append(comment_data)
        comment_reports[str(comment.id)] = comment.report_count
        
        # 답글들도 추가
        for reply in comment.replies:
            reply_data = {
                'id': reply.id,
                'parent_id': reply.parent_id,
                'author': reply.author or f'익명{reply.id}',
                'content': reply.content,
                'stance': reply.stance,
                'time_ago': time_ago(reply.created_at),
                'report_count': reply.report_count,
                'is_under_review': reply.is_under_review or reply.report_count >= 3,
                'is_reported_by_user': reply.id in reported_comment_ids
            }
            comments_data.append(reply_data)
            comment_reports[str(reply.id)] = reply.report_count
    
    # 관련 법률안 (같은 위원회)
    related_bills = Bill.query.filter(
        Bill.committee == bill.committee,
        Bill.id != bill.id
    ).limit(5).all()
    
    related_bills_data = [{
        'id': rb.id,
        'name': rb.name[:30] + '...' if len(rb.name) > 30 else rb.name
    } for rb in related_bills]
    
    bill_data = {
        'id': bill.id,
        'number': bill.number,
        'name': bill.name,
        'proposer': bill.proposer,
        'propose_date': bill.propose_date,
        'committee': bill.committee,
        'detail_link': bill.detail_link
    }
    
    return render_template('LAWdetail.html',
                         bill=bill_data,
                         vote_stats=vote_stats,
                         user_vote=user_vote_type,
                         comments=comments_data,
                         reported_comment_ids=reported_comment_ids,
                         comment_reports=comment_reports,
                         related_bills=related_bills_data,
                         has_more_comments=len(comments) >= 10)

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
            author=f'사용자{len(Proposal.query.all()) + 1}'
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
    
    # 댓글 가져오기
    comments = Comment.query.filter_by(proposal_id=proposal_id).order_by(Comment.created_at.desc()).limit(10).all()
    
    # 사용자가 신고한 댓글 ID들
    user_reports = Report.query.filter_by(reporter_ip=ip_address).all()
    user_reported_comments = [r.comment_id for r in user_reports if r.comment_id]
    
    # 댓글 데이터 준비
    comments_data = []
    comment_reports = {}
    
    for comment in comments:
        comment_data = {
            'id': comment.id,
            'author': comment.author or f'익명{comment.id}',
            'content': comment.content,
            'stance': comment.stance,
            'time_ago': time_ago(comment.created_at),
            'report_count': comment.report_count,
            'is_under_review': comment.is_under_review or comment.report_count >= 3,
            'is_reported_by_user': comment.id in user_reported_comments,
            'likes_count': 0  # 좋아요 기능은 구현 필요시 추가
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
                         comments=comments_data,
                         comment_reports=comment_reports,
                         has_more_comments=len(comments) >= 10)

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
    
    if existing_vote:
        if existing_vote.vote_type == vote_type:
            # 같은 투표 취소
            db.session.delete(existing_vote)
        else:
            # 투표 변경
            existing_vote.vote_type = vote_type
    else:
        # 새 투표
        new_vote = BillVote(bill_id=bill_id, ip_address=ip_address, vote_type=vote_type)
        db.session.add(new_vote)
    
    db.session.commit()
    
    # 업데이트된 투표 수 반환
    agree_count = BillVote.query.filter_by(bill_id=bill_id, vote_type='agree').count()
    disagree_count = BillVote.query.filter_by(bill_id=bill_id, vote_type='disagree').count()
    
    return jsonify({
        'agree_count': agree_count,
        'disagree_count': disagree_count
    })

@app.route('/api/bills/<int:bill_id>/comments', methods=['POST'])
def add_bill_comment(bill_id):
    data = request.get_json()
    content = data.get('content', '').strip()
    stance = data.get('stance')
    parent_id = data.get('parent_id')
    ip_address = get_client_ip()
    
    if not content or stance not in ['agree', 'disagree']:
        return jsonify({'error': 'Invalid data'}), 400
    
    # 투표 확인
    user_vote = BillVote.query.filter_by(bill_id=bill_id, ip_address=ip_address).first()
    if not user_vote:
        return jsonify({'error': 'Vote required'}), 403
    
    comment = Comment(
        bill_id=bill_id,
        parent_id=parent_id,
        content=content,
        stance=stance,
        ip_address=ip_address,
        author=f'익명{Comment.query.count() + 1}'
    )
    
    db.session.add(comment)
    db.session.commit()
    
    return jsonify({
        'id': comment.id,
        'author': comment.author,
        'content': comment.content,
        'stance': comment.stance,
        'time_ago': '방금 전'
    })

@app.route('/api/comments/<int:comment_id>/report', methods=['POST'])
def report_comment(comment_id):
    ip_address = get_client_ip()
    
    # 이미 신고했는지 확인
    existing_report = Report.query.filter_by(comment_id=comment_id, reporter_ip=ip_address).first()
    if existing_report:
        return jsonify({'error': 'Already reported'}), 400
    
    # 신고 추가
    report = Report(comment_id=comment_id, reporter_ip=ip_address)
    db.session.add(report)
    
    # 댓글의 신고 수 증가
    comment = Comment.query.get(comment_id)
    if comment:
        comment.report_count += 1
        if comment.report_count >= 3:
            comment.is_under_review = True
    
    db.session.commit()
    
    return jsonify({
        'report_count': comment.report_count,
        'is_under_review': comment.is_under_review
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
    
    if existing_vote:
        if existing_vote.vote_type == vote_type:
            # 같은 투표 취소
            db.session.delete(existing_vote)
        else:
            # 투표 변경
            existing_vote.vote_type = vote_type
    else:
        # 새 투표
        new_vote = ProposalVote(proposal_id=proposal_id, ip_address=ip_address, vote_type=vote_type)
        db.session.add(new_vote)
    
    db.session.commit()
    
    # 업데이트된 투표 수 반환
    agree_count = ProposalVote.query.filter_by(proposal_id=proposal_id, vote_type='agree').count()
    disagree_count = ProposalVote.query.filter_by(proposal_id=proposal_id, vote_type='disagree').count()
    
    return jsonify({
        'agree_count': agree_count,
        'disagree_count': disagree_count,
        'total_votes': agree_count + disagree_count
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
    
    return jsonify({
        'report_count': proposal.report_count
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
    results = [{'id': m.id, 'name': m.name, 'party': m.party} for m in members]
    
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

# 오류 핸들러
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# 메인 실행
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # init_sample_data()  # 샘플 데이터 초기화
        load_election_csv()  # CSV 데이터 로드
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
