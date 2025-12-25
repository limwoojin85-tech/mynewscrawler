import streamlit as st
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import json

# [설정] 환경 변수 및 보안 정보 (Streamlit Secrets에서 불러옴)
API_ID = 31483914
API_HASH = '1962ae18860f8433f4ecfcfa24c4e2e0'
SHEET_URL = 'https://docs.google.com/spreadsheets/d/15MtSL0NZRbPCP9P_0LanlORFm9MYUVhk4F0LzaM9Rlw/edit'

st.set_page_config(page_title="보안 뉴스 수집기", layout="wide", page_icon="🛡️")

# 세션 상태 초기화
if 'channel_list' not in st.session_state:
    st.session_state.channel_list = ['시그널리포트', '만담채널', 'AWAKE', '정부정책 알리미', 'newsguy', 'Signal Search', 'Seeking Signal']

# 텔레그램 클라이언트 캐싱
@st.cache_resource
def get_client():
    # Secrets에 저장된 세션 문자열 사용
    session_str = st.secrets["TELEGRAM_SESSION"]
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return TelegramClient(StringSession(session_str), API_ID, API_HASH, loop=loop)

st.title("🛡️ 보안 강화형 뉴스 수집 제어판")

# --- 사이드바 및 UI ---
with st.sidebar:
    st.header("🛠 채널 관리")
    new_ch = st.text_input("추가할 채널명:")
    if st.button("추가") and new_ch:
        st.session_state.channel_list.append(new_ch)
        st.rerun()
    st.write("---")
    selected_names = [name for name in st.session_state.channel_list if st.checkbox(name, value=True)]

status_ui = st.empty()

async def start_monitoring():
    try:
        # 구글 인증 (Secrets에 저장된 JSON 데이터 사용)
        creds_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        gc = gspread.authorize(creds)
        doc = gc.open_by_url(SHEET_URL)
        
        client = get_client()
        if not client.is_connected():
            await client.start()
        
        dialogs = await client.get_dialogs()
        target_ids = [d.id for name in selected_names for d in dialogs if name.lower() in d.name.lower()]
        
        client.list_event_handlers().clear()

        @client.on(events.NewMessage(chats=target_ids))
        async def handler(event):
            try:
                chat = await event.get_chat()
                msg = event.raw_text
                date = event.date.strftime("%Y-%m-%d %H:%M:%S")
                clean_title = "".join(x for x in chat.title if x.isalnum() or x in " -_")[:30].strip()
                try:
                    worksheet = doc.worksheet(clean_title)
                except:
                    worksheet = doc.add_worksheet(title=clean_title, rows="1000", cols="5")
                    worksheet.insert_row(["날짜", "내용"], 1)
                worksheet.insert_row([date, msg], 2)
                st.toast(f"📥 {clean_title} 수집!")
            except: pass

        status_ui.success(f"📡 보안 모드로 {len(target_ids)}개 채널 감시 중...")
        await client.run_until_disconnected()
    except Exception as e:
        status_ui.error(f"❌ 오류: {e}")

if st.button("🚀 보안 수집 시작"):
    asyncio.run(start_monitoring())
