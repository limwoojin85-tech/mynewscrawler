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

st.set_page_config(page_title="보안 뉴스 수집기", layout="wide", page_icon="🛡️")

if 'channel_list' not in st.session_state:
    st.session_state.channel_list = [
        '시그널리포트', '만담채널', 'AWAKE', 
        '정부정책 알리미', 'newsguy', 'Signal Search', 'Seeking Signal'
    ]

# 1. 클라이언트 생성 방식 변경 (루프 고정 제거)
@st.cache_resource
def get_client():
    session_str = st.secrets["TELEGRAM_SESSION"]
    # 루프를 명시적으로 지정하지 않고 세션 문자열만 사용
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
    st.write("---")
    selected_names = [name for name in st.session_state.channel_list if st.checkbox(name, value=True, key=f"ch_{name}")]

status_ui = st.empty()

async def start_monitoring():
    try:
        creds_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        gc = gspread.authorize(creds)
        doc = gc.open_by_url(SHEET_URL)
        
        client = get_client()
        
        # [핵심] 현재 실행 중인 루프에 연결
        if not client.is_connected():
            await client.connect()
        
        # 세션 유효성 확인 및 시작
        if not await client.is_user_authorized():
            status_ui.error("❌ 텔레그램 세션이 만료되었습니다. 다시 세션을 추출하세요.")
            return

        status_ui.info("🔍 채널 목록 스캔 중...")
        dialogs = await client.get_dialogs()
        
        target_ids = []
        for name in selected_names:
            for d in dialogs:
                if name.replace(" ", "").lower() in d.name.replace(" ", "").lower():
                    target_ids.append(d.id)
                    break
        
        # 기존 핸들러 초기화
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
                st.toast(f"📥 {clean_title} 수집 성공")
            except: pass

        status_ui.success(f"📡 {len(target_ids)}개 채널 실시간 감시 가동 중")
        await client.run_until_disconnected()
    except Exception as e:
        # 특정 에러(Event loop closed) 발생 시 재연결 시도 로직
        if "closed" in str(e).lower():
            st.rerun()
        status_ui.error(f"❌ 오류 발생: {e}")

# [자동 실행 로직 개선]
if selected_names:
    try:
        # 기존 루프를 가져오거나 없으면 새로 만듦
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(start_monitoring())
    except Exception as e:
        if "already running" in str(e).lower():
            # 이미 루프가 도는 중이면 start_monitoring 직접 호출
            asyncio.create_task(start_monitoring())
        else:
            st.error(f"비동기 실행 오류: {e}")
else:
    status_ui.warning("사이드바에서 수집할 채널을 하나 이상 선택해 주세요.")
