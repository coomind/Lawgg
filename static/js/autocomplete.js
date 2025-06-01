// 자동완성 기능을 위한 JavaScript

// API 엔드포인트 설정 (배포 시 실제 URL로 변경)
if (typeof API_BASE_URL === 'undefined') {
  var API_BASE_URL = window.location.hostname === 'localhost'
    ? 'http://localhost:5000'
    : 'https://lawgg-backend.onrender.com';
}
// 디바운스 함수 (과도한 API 호출 방지)
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// 자동완성 초기화
function initAutocomplete(inputId, type = 'all') {
    const input = document.getElementById(inputId);
    if (!input) return;

    // 자동완성 결과를 표시할 컨테이너 생성
    const autocompleteContainer = document.createElement('div');
    autocompleteContainer.className = 'autocomplete-results';
    autocompleteContainer.style.cssText = `
        position: absolute;
        top: 100%;
        left: 0;
        right: 0;
        background: white;
        border: 1px solid #e9ecef;
        border-radius: 8px;
        max-height: 400px;
        overflow-y: auto;
        display: none;
        z-index: 1000;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        margin-top: 4px;
    `;

    // input 요소를 relative 컨테이너로 감싸기
    const wrapper = document.createElement('div');
    wrapper.style.position = 'relative';
    wrapper.style.flex = '1';  // 검색창이 컨테이너 내에서 확장되도록
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);
    wrapper.appendChild(autocompleteContainer);

    let currentFocus = -1;

    // 검색 함수
    const search = debounce(async (query) => {
        if (query.length < 1) {
            autocompleteContainer.style.display = 'none';
            return;
        }

        try {
            let results = [];

            // 검색 타입에 따라 다른 API 호출
            if (type === 'members' || type === 'all') {
                const memberResponse = await fetch(`${API_BASE_URL}/api/autocomplete/members?q=${encodeURIComponent(query)}`);
                const members = await memberResponse.json();
                results = results.concat(members.map(m => ({
                    ...m,
                    type: 'member',
                    display: `${m.name} (${m.party || '무소속'})`
                })));
            }

            if (type === 'bills' || type === 'all') {
                const billResponse = await fetch(`${API_BASE_URL}/api/autocomplete/bills?q=${encodeURIComponent(query)}`);
                const bills = await billResponse.json();
                results = results.concat(bills.map(b => ({
                    ...b,
                    type: 'bill',
                    display: b.name
                })));
            }

            // 결과 표시
            displayResults(results);
        } catch (error) {
            console.error('자동완성 오류:', error);
        }
    }, 300);

    // 결과 표시 함수
    function displayResults(results) {
        autocompleteContainer.innerHTML = '';
        currentFocus = -1;

        if (results.length === 0) {
            autocompleteContainer.style.display = 'none';
            return;
        }

        // 타입별로 그룹화
        const groupedResults = {
            member: results.filter(r => r.type === 'member'),
            bill: results.filter(r => r.type === 'bill')
        };

        // 국회의원 섹션
        if (groupedResults.member.length > 0) {
            const memberSection = document.createElement('div');
            memberSection.style.cssText = 'padding: 8px 0;';
            
            const memberTitle = document.createElement('div');
            memberTitle.style.cssText = `
                padding: 8px 16px;
                font-size: 12px;
                color: #6c757d;
                font-weight: 600;
                text-transform: uppercase;
            `;
            memberTitle.textContent = '국회의원';
            memberSection.appendChild(memberTitle);

            groupedResults.member.forEach((result, index) => {
                const item = createResultItem(result, index);
                memberSection.appendChild(item);
            });
            
            autocompleteContainer.appendChild(memberSection);
        }

        // 법률안 섹션
        if (groupedResults.bill.length > 0) {
            const billSection = document.createElement('div');
            billSection.style.cssText = 'padding: 8px 0; border-top: 1px solid #e9ecef;';
            
            const billTitle = document.createElement('div');
            billTitle.style.cssText = `
                padding: 8px 16px;
                font-size: 12px;
                color: #6c757d;
                font-weight: 600;
                text-transform: uppercase;
            `;
            billTitle.textContent = '법률안';
            billSection.appendChild(billTitle);

            groupedResults.bill.forEach((result, index) => {
                const item = createResultItem(result, index + groupedResults.member.length);
                billSection.appendChild(item);
            });
            
            autocompleteContainer.appendChild(billSection);
        }

        autocompleteContainer.style.display = 'block';
    }

    // 결과 아이템 생성 함수
    function createResultItem(result, index) {
        const item = document.createElement('div');
        item.className = 'autocomplete-item';
        item.setAttribute('data-index', index);
        item.style.cssText = `
            padding: 12px 16px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 12px;
            transition: background-color 0.2s;
        `;

        // 프로필 이미지 또는 아이콘
        const avatar = document.createElement('div');
        avatar.style.cssText = `
            width: 32px;
            height: 32px;
            border-radius: 50%;
            background-color: ${result.type === 'member' ? '#e3f2fd' : '#f3e5f5'};
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            flex-shrink: 0;
            overflow: hidden;
        `;
        if (result.type === 'member' && result.photo_url) {
            const img = document.createElement('img');
            img.src = result.photo_url;
            img.alt = result.name;
            img.style.cssText = `
                width: 100%;
                height: 100%;
                object-fit: cover;
                border-radius: 50%;
            `;
            avatar.appendChild(img);
        } else {
            avatar.textContent = result.type === 'member' ? '👤' : '📋';
        }

        // 텍스트 정보
        const textContainer = document.createElement('div');
        textContainer.style.cssText = 'flex: 1; min-width: 0;';
        
        const mainText = document.createElement('div');
        mainText.style.cssText = `
            font-size: 14px;
            font-weight: 500;
            color: #212529;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        `;
        mainText.textContent = result.name;
        
        const subText = document.createElement('div');
        subText.style.cssText = `
            font-size: 12px;
            color: #6c757d;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        `;
        subText.textContent = result.type === 'member' ? (result.party || '무소속') : '법률안';
        
        textContainer.appendChild(mainText);
        textContainer.appendChild(subText);

        item.appendChild(avatar);
        item.appendChild(textContainer);

        // 마우스 이벤트
        item.addEventListener('mouseenter', () => {
            removeActive();
            currentFocus = index;
            item.classList.add('active');
            item.style.backgroundColor = '#f8f9fa';
        });

        item.addEventListener('mouseleave', () => {
            item.classList.remove('active');
            item.style.backgroundColor = '';
        });

        item.addEventListener('click', () => {
            selectItem(result);
        });

        return item;
    }

    // 항목 선택 함수
    function selectItem(result) {
        input.value = result.name;
        autocompleteContainer.style.display = 'none';

        // 선택 이벤트 발생
        const event = new CustomEvent('autocomplete-select', {
            detail: result
        });
        input.dispatchEvent(event);

        // 페이지 이동 (메인페이지에서만)
        if (input.id === 'searchInput') {
            if (result.type === 'member') {
                window.location.href = `/members/${result.id}`;
            } else if (result.type === 'bill') {
                window.location.href = `/bills/${result.id}`;
            }
        }
    }

    // 활성 항목 제거
    function removeActive() {
        const items = autocompleteContainer.querySelectorAll('.autocomplete-item');
        items.forEach(item => {
            item.classList.remove('active');
            item.style.backgroundColor = '';
        });
    }

    // 키보드 이벤트
    input.addEventListener('keydown', (e) => {
        const items = autocompleteContainer.querySelectorAll('.autocomplete-item');
        
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            currentFocus++;
            if (currentFocus >= items.length) currentFocus = 0;
            removeActive();
            if (items[currentFocus]) {
                items[currentFocus].classList.add('active');
                items[currentFocus].style.backgroundColor = '#f8f9fa';
                items[currentFocus].scrollIntoView({ block: 'nearest' });
            }
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            currentFocus--;
            if (currentFocus < 0) currentFocus = items.length - 1;
            removeActive();
            if (items[currentFocus]) {
                items[currentFocus].classList.add('active');
                items[currentFocus].style.backgroundColor = '#f8f9fa';
                items[currentFocus].scrollIntoView({ block: 'nearest' });
            }
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (currentFocus > -1 && items[currentFocus]) {
                items[currentFocus].click();
            }
        } else if (e.key === 'Escape') {
            autocompleteContainer.style.display = 'none';
        }
    });

    // 입력 이벤트
    input.addEventListener('input', (e) => {
        search(e.target.value);
    });

    // 포커스 이벤트
    input.addEventListener('focus', () => {
        if (input.value.length >= 1) {
            search(input.value);
        }
    });

    // 외부 클릭 시 닫기
    document.addEventListener('click', (e) => {
        if (!wrapper.contains(e.target)) {
            autocompleteContainer.style.display = 'none';
        }
    });
}

// DOM 로드 시 자동완성 초기화
document.addEventListener('DOMContentLoaded', () => {
    // 메인 페이지 통합 검색
    if (document.getElementById('searchInput')) {
        initAutocomplete('searchInput', 'all');
    }

    // 입법제안 작성 페이지 - 대상법안 자동완성
    if (document.getElementById('target_law')) {
        initAutocomplete('target_law', 'bills');
    }
});

// 외부에서 사용할 수 있도록 전역 함수로 등록
window.initAutocomplete = initAutocomplete;
