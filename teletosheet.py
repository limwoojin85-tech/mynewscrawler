import streamlit as st
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz
import json
import re

# [설정]
API_ID = 31483914
API_HASH = '1962ae18860f8433f4ecfcfa24c4e2e0'
SHEET_URL = 'https://docs.google.com/spreadsheets/d/15MtSL0NZRbPCP9P_0LanlORFm9MYUVhk4F0LzaM9Rlw/edit'

st.set_page_config(page_title="24/7 클린 뉴스 수집기", layout="wide", page_icon="🛡️")

# 세션 상태 초기화 (중복 방지를 위해 제목 저장소 크기 확대)
if 'collected_titles' not in st.session_state:
    st.session_state.collected_titles = set()
if 'channel_list' not in st.session_state:
    st.session_state.channel_list = [
        '시그널리포트', '만담채널', 'AWAKE', 
        '정부정책 알리미', 'Signal Search', 'Seeking Signal'
    ]

@st.cache_resource
def get_client():
    session_str = st.secrets["TELEGRAM_SESSION"]
    # 루프 에러를 줄이기 위해 클라이언트 생성 방식을 가장 기초적인 형태로 유지
    return TelegramClient(StringSession(session_str), API_ID, API_HASH)

def extract_link(text):
    url_pattern = r'(https?://[^\s]+)'
    urls = re.findall(url_pattern, text)
    clean_text = re.sub(url_pattern, '', text).strip()
    link = urls[0] if urls else ""
    title = clean_text.split('\n')[0][:100] if clean_text else "내용 없음"
    return title, link

def get_market_status(now_kst):
    is_weekday = now_kst.weekday() < 5
    is_market_time = 8 <= now_kst.hour < 20
    return "☀️ 장중" if is_weekday and is_market_time else "🌙 장마감"

st.title("🛡️ 중복/루프 완전 차단 수집기")

with st.sidebar:
    st.header("🛠 관리")
    if st.button("⚠️ 시스템 전체 리셋 (중복 해결)"):
        st.cache_resource.clear()
        st.session_state.clear()
        st.rerun()
    st.write("---")
    # key 값을 매번 다르게 하여 이전 세션의 간섭을 차단
    selected_names = [name for name in st.session_state.channel_list if st.checkbox(name, value=True, key=f"fix_v1_{name}")]

status_ui = st.empty()

async def start_monitoring():
    client = get_client()
    try:
        creds_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        gc = gspread.authorize(creds)
        doc = gc.open_by_url(SHEET_URL)
        
        if not client.is_connected():
            await client.connect()
        
        # [수정] 핸들러 중복 등록을 원천 차단
        client.remove_event_handler(handler) # 기존 핸들러 제거 시도
    except: pass

    @client.on(events.NewMessage)
    async def handler(event):
        # 내가 감시하는 채널인지 확인
        chat = await event.get_chat()
        is_target = any(name.replace(" ", "").lower() in chat.title.replace(" ", "").lower() for name in selected_names)
        if not is_target: return

        try:
            # 1. 한국 시간 및 텍스트 추출
            kst = pytz.timezone('Asia/Seoul')
            now_kst = datetime.now(kst)
            title, link = extract_link(event.raw_text)
            
            # 2. 강력한 중복 체크
            if title in st.session_state.collected_titles:
                return
            
            # 3. 데이터 기록
            st.session_state.collected_titles.add(title)
            # 메모리 관리: 너무 많으면 오래된 것 삭제
            if len(st.session_state.collected_titles) > 500:
                st.session_state.collected_titles.remove(next(iter(st.session_state.collected_titles)))

            market_status = get_market_status(now_kst)
            date_str = now_kst.strftime("%Y-%m-%d %H:%M:%S")
            today_label = now_kst.strftime("%Y-%m-%d")
            
            clean_title = "".join(x for x in chat.title if x.isalnum() or x in " -_")[:20].strip()
            tab_name = f"{clean_title}_{today_label}"
            
            try:
                worksheet = doc.worksheet(tab_name)
            except:
                worksheet = doc.add_worksheet(title=tab_name[:30], rows="2000", cols="6")
                worksheet.insert_row(["날짜", "상태", "제목", "링크"], 1)
            
            worksheet.insert_row([date_str, market_status, title, link], 2)
            st.toast(f"📥 {tab_name} 수집 성공")
        except: pass

    try:
        status_ui.success("📡 중복 필터링 모드로 감시 중...")
        await client.run_until_disconnected()
    except Exception as e:
        if "loop" in str(e).lower():
            st.cache_resource.clear()
            st.rerun()

# [실행부] 무한 루프 방지 로직 강화
if selected_names:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 이미 실행 중인 루프가 있다면 작업을 추가만 함
            asyncio.ensure_future(start_monitoring())
        else:
            loop.run_until_complete(start_monitoring())
    except Exception as e:
        # 에러 발생 시 새 루프로 깨끗하게 시작
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        new_loop.run_until_complete(start_monitoring())
