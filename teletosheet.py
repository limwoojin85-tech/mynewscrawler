import streamlit as st
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import json
import re

# [기본 설정]
API_ID = 31483914
API_HASH = '1962ae18860f8433f4ecfcfa24c4e2e0'
SHEET_URL = 'https://docs.google.com/spreadsheets/d/15MtSL0NZRbPCP9P_0LanlORFm9MYUVhk4F0LzaM9Rlw/edit'

st.set_page_config(page_title="24/7 뉴스 수집기", layout="wide", page_icon="🛡️")

# 세션 초기화 (newsguy 제외 확인)
if 'channel_list' not in st.session_state:
    st.session_state.channel_list = [
        '시그널리포트', '만담채널', 'AWAKE', 
        '정부정책 알리미', 'Signal Search', 'Seeking Signal'
    ]

# 텔레그램 클라이언트 캐싱 (최대한 단순하게 변경)
@st.cache_resource
def get_client():
    session_str = st.secrets["TELEGRAM_SESSION"]
    return TelegramClient(StringSession(session_str), API_ID, API_HASH)

def extract_link(text):
    """텍스트에서 제목과 URL을 정밀하게 분리"""
    url_pattern = r'(https?://[^\s]+)'
    urls = re.findall(url_pattern, text)
    clean_text = re.sub(url_pattern, '', text).strip()
    link = urls[0] if urls else ""
    # 첫 줄만 제목으로 가져옴
    title = clean_text.split('\n')[0][:100] if clean_text else "제목 없음"
    return title, link

st.title("🛡️ 24/7 무중단 뉴스 수집기")

# --- UI 구성 ---
with st.sidebar:
    st.header("🛠 채널 관리")
    new_ch = st.text_input("추가할 채널명:")
    if st.button("추가") and new_ch:
        st.session_state.channel_list.append(new_ch)
        st.rerun()
    
    if st.button("⚠️ 모든 캐시 초기화"):
        st.cache_resource.clear()
        st.session_state.clear()
        st.rerun()

    st.write("---")
    selected_names = [name for name in st.session_state.channel_list if st.checkbox(name, value=True, key=f"final_{name}")]

status_ui = st.empty()

# --- 메인 비동기 함수 ---
async def start_monitoring():
    try:
        # 1. 구글 인증
        creds_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        gc = gspread.authorize(creds)
        doc = gc.open_by_url(SHEET_URL)
        
        # 2. 클라이언트 연결
        client = get_client()
        if not client.is_connected():
            await client.connect()
        
        # 3. 채널 ID 매칭
        status_ui.info("🔍 채널 매칭 중...")
        dialogs = await client.get_dialogs()
        target_ids = []
        for name in selected_names:
            for d in dialogs:
                if name.replace(" ", "").lower() in d.name.replace(" ", "").lower():
                    target_ids.append(d.id)
                    break
        
        # 4. 이벤트 핸들러 등록
        client.list_event_handlers().clear()

        @client.on(events.NewMessage(chats=target_ids))
        async def handler(event):
            try:
                chat = await event.get_chat()
                msg = event.raw_text
                date = event.date.strftime("%Y-%m-%d %H:%M:%S")
                title, link = extract_link(msg)
                
                # 시트 탭 관리
                clean_title = "".join(x for x in chat.title if x.isalnum() or x in " -_")[:30].strip()
                try:
                    worksheet = doc.worksheet(clean_title)
                except:
                    worksheet = doc.add_worksheet(title=clean_title, rows="2000", cols="5")
                    worksheet.insert_row(["날짜", "제목", "링크"], 1)
                
                worksheet.insert_row([date, title, link], 2)
                st.toast(f"📥 {clean_title} 수집 완료")
            except: pass

        status_ui.success(f"📡 {len(target_ids)}개 채널 실시간 감시 가동 중")
        await client.run_until_disconnected()

    except Exception as e:
        status_ui.error(f"❌ 오류: {e}")

# --- 실행 로직 (무한 로딩 방지) ---
if selected_names:
    # 현재 실행 중인 루프를 가져오거나 새로 생성
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # 루프가 이미 실행 중이면 백그라운드 태스크로 던짐 (무한 로딩 방지)
    if loop.is_running():
        asyncio.create_task(start_monitoring())
    else:
        loop.run_until_complete(start_monitoring())
else:
    status_ui.warning("사이드바에서 채널을 선택해 주세요.")
