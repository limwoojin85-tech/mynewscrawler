import streamlit as st
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import json
import re

# [설정]
API_ID = 31483914
API_HASH = '1962ae18860f8433f4ecfcfa24c4e2e0'
SHEET_URL = 'https://docs.google.com/spreadsheets/d/15MtSL0NZRbPCP9P_0LanlORFm9MYUVhk4F0LzaM9Rlw/edit'

st.set_page_config(page_title="24/7 뉴스 수집기", layout="wide", page_icon="🛡️")

# 기본 채널 목록에서 newsguy 제외
if 'channel_list' not in st.session_state:
    st.session_state.channel_list = [
        '시그널리포트', '만담채널', 'AWAKE', 
        '정부정책 알리미', 'Signal Search', 'Seeking Signal'
    ]

@st.cache_resource
def get_client():
    session_str = st.secrets["TELEGRAM_SESSION"]
    return TelegramClient(StringSession(session_str), API_ID, API_HASH)

def extract_link(text):
    url_pattern = r'(https?://[^\s]+)'
    urls = re.findall(url_pattern, text)
    clean_text = re.sub(url_pattern, '', text).strip()
    link = urls[0] if urls else ""
    title = clean_text.split('\n')[0][:100]
    return title, link

st.title("🛡️ 24/7 무중단 뉴스 수집기")

# 사이드바 채널 관리
with st.sidebar:
    st.header("🛠 채널 관리")
    new_ch = st.text_input("추가할 채널명:")
    if st.button("추가") and new_ch:
        st.session_state.channel_list.append(new_ch)
        st.rerun()
    st.write("---")
    # 체크박스 상태 변경 시 즉시 반영되도록 구성
    selected_names = [name for name in st.session_state.channel_list if st.checkbox(name, value=True, key=f"v3_{name}")]

status_ui = st.empty()

async def start_monitoring():
    try:
        creds_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        gc = gspread.authorize(creds)
        doc = gc.open_by_url(SHEET_URL)
        
        client = get_client()
        
        # 연결 시도 및 루프 체크
        if not client.is_connected():
            await client.connect()
        
        if not await client.is_user_authorized():
            status_ui.error("❌ 텔레그램 세션 만료")
            return

        dialogs = await client.get_dialogs()
        target_ids = []
        for name in selected_names:
            for d in dialogs:
                if name.replace(" ", "").lower() in d.name.replace(" ", "").lower():
                    target_ids.append(d.id)
                    break
        
        # 기존 핸들러 제거 후 새로 등록
        client.list_event_handlers().clear()

        @client.on(events.NewMessage(chats=target_ids))
        async def handler(event):
            try:
                chat = await event.get_chat()
                msg = event.raw_text
                date = event.date.strftime("%Y-%m-%d %H:%M:%S")
                title, link = extract_link(msg)
                clean_title = "".join(x for x in chat.title if x.isalnum() or x in " -_")[:30].strip()
                
                try:
                    worksheet = doc.worksheet(clean_title)
                except:
                    worksheet = doc.add_worksheet(title=clean_title, rows="2000", cols="5")
                    worksheet.insert_row(["날짜", "제목", "링크"], 1)
                
                worksheet.insert_row([date, title, link], 2)
                st.toast(f"📥 {clean_title} 수집!")
            except: pass

        status_ui.success(f"📡 {len(target_ids)}개 채널 실시간 감시 중")
        await client.run_until_disconnected()

    except Exception as e:
        if "loop" in str(e).lower():
            # 루프 에러 발생 시 세션 초기화 후 재실행 유도
            st.cache_resource.clear()
            st.rerun()
        status_ui.error(f"❌ 오류: {e}")

# 실행 로직
if selected_names:
    try:
        # 현재 실행 중인 루프가 있는지 확인하고 처리
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 이미 돌아가고 있다면 태스크로 등록
            asyncio.create_task(start_monitoring())
        else:
            loop.run_until_complete(start_monitoring())
    except RuntimeError:
        # 새 루프 생성 및 강제 실행
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        new_loop.run_until_complete(start_monitoring())
else:
    status_ui.warning("채널을 선택해 주세요.")
