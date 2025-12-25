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

st.set_page_config(page_title="24/7 날짜별 뉴스 수집기", layout="wide", page_icon="📅")

# 세션 상태 초기화
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
    """텍스트에서 제목과 URL 분리"""
    url_pattern = r'(https?://[^\s]+)'
    urls = re.findall(url_pattern, text)
    clean_text = re.sub(url_pattern, '', text).strip()
    link = urls[0] if urls else ""
    title = clean_text.split('\n')[0][:100] if clean_text else "내용 없음"
    return title, link

st.title("📅 날짜별 탭 생성 뉴스 수집기")

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
    selected_names = [name for name in st.session_state.channel_list if st.checkbox(name, value=True, key=f"date_v1_{name}")]

status_ui = st.empty()

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
        
        # 3. 채널 매칭
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
                # 현재 날짜 및 시간 정보
                now = event.date
                date_str = now.strftime("%Y-%m-%d %H:%M:%S")
                today_label = now.strftime("%Y-%m-%d") # 탭 이름용 날짜
                
                title, link = extract_link(msg)
                
                # 채널명에서 특수문자 제거
                clean_title = "".join(x for x in chat.title if x.isalnum() or x in " -_")[:20].strip()
                
                # [핵심] 탭 이름을 '채널명_날짜'로 설정
                tab_name = f"{clean_title}_{today_label}"
                
                try:
                    worksheet = doc.worksheet(tab_name)
                except:
                    # 탭이 없으면 새로 생성 (최대 30자 제한 고려)
                    worksheet = doc.add_worksheet(title=tab_name[:30], rows="2000", cols="5")
                    worksheet.insert_row(["날짜", "제목", "링크"], 1)
                
                worksheet.insert_row([date_str, title, link], 2)
                st.toast(f"📅 {tab_name}에 저장 완료")
            except Exception as e:
                print(f"저장 중 에러: {e}")

        status_ui.success(f"📡 {len(target_ids)}개 채널 날짜별 수집 중...")
        await client.run_until_disconnected()

    except Exception as e:
        if "loop" in str(e).lower():
            st.cache_resource.clear()
            st.rerun()
        status_ui.error(f"❌ 오류: {e}")

# 실행 로직 (백그라운드 태스크)
if selected_names:
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        asyncio.create_task(start_monitoring())
    else:
        loop.run_until_complete(start_monitoring())
else:
    status_ui.warning("채널을 선택해 주세요.")
