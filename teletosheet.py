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

# 채널 목록 (여기에 자주 쓰는 채널을 미리 적어두면 배포 시 자동 반영됩니다)
if 'channel_list' not in st.session_state:
    st.session_state.channel_list = [
        '시그널리포트', '만담채널', 'AWAKE', 
        '정부정책 알리미', 'newsguy', 'Signal Search', 'Seeking Signal'
    ]

@st.cache_resource
def get_client():
    session_str = st.secrets["TELEGRAM_SESSION"]
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return TelegramClient(StringSession(session_str), API_ID, API_HASH, loop=loop)

def extract_link(text):
    """텍스트에서 URL만 추출하고 제목 분리"""
    url_pattern = r'(https?://[^\s]+)'
    urls = re.findall(url_pattern, text)
    clean_text = re.sub(url_pattern, '', text).strip()
    link = urls[0] if urls else ""
    # 제목이 너무 길면 첫 줄만 사용 (가독성용)
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
        # 구글 인증
        creds_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        gc = gspread.authorize(creds)
        doc = gc.open_by_url(SHEET_URL)
        
        client = get_client()
        if not client.is_connected():
            await client.start()
        
        status_ui.info("🔍 채널 목록 스캔 중...")
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
                
                # 시트에 분리하여 저장
                worksheet.insert_row([date, title, link], 2)
                st.toast(f"📥 {clean_title} 수집 성공")
            except: pass

        status_ui.success(f"📡 {len(target_ids)}개 채널 실시간 감시 가동 중")
        await client.run_until_disconnected()
    except Exception as e:
        status_ui.error(f"❌ 오류 발생: {e}")

# [자동 실행 로직] 버튼 클릭 없이 바로 실행
if selected_names:
    asyncio.run(start_monitoring())
else:
    status_ui.warning("사이드바에서 수집할 채널을 하나 이상 선택해 주세요.")
