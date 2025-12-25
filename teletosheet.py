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

# 강제로 세션 초기화 (newsguy 제거를 위해 체크)
if 'init_done' not in st.session_state:
    st.session_state.channel_list = [
        '시그널리포트', '만담채널', 'AWAKE', 
        '정부정책 알리미', 'Signal Search', 'Seeking Signal'
    ]
    st.session_state.init_done = True

@st.cache_resource
def get_client():
    # 루프 에러 방지를 위해 클라이언트 생성 시점의 루프를 사용하지 않음
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
    # 체크박스 key 값을 v4로 변경하여 이전 세션 무시
    selected_names = [name for name in st.session_state.channel_list if st.checkbox(name, value=True, key=f"v4_{name}")]

status_ui = st.empty()

async def start_monitoring():
    client = get_client()
    try:
        creds_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        gc = gspread.authorize(creds)
        doc = gc.open_by_url(SHEET_URL)
        
        # 연결 시도
        if not client.is_connected():
            await client.connect()
        
        dialogs = await client.get_dialogs()
        target_ids = []
        for name in selected_names:
            for d in dialogs:
                if name.replace(" ", "").lower() in d.name.replace(" ", "").lower():
                    target_ids.append(d.id)
                    break
        
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

        status_ui.success(f"📡 {len(target_ids)}개 채널 감시 중")
        await client.run_until_disconnected()

    except Exception as e:
        if "loop" in str(e).lower() or "connection" in str(e).lower():
            # 루프나 연결 에러 시 캐시 비우고 재도전
            st.cache_resource.clear()
            st.rerun()
        status_ui.error(f"❌ 오류: {e}")

# 실행부 최적화
if selected_names:
    try:
        asyncio.run(start_monitoring())
    except RuntimeError:
        # 이미 루프가 도는 중이라면 태스크로 처리
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(start_monitoring())
else:
    status_ui.warning("채널을 선택해 주세요.")
