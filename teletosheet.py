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

st.set_page_config(page_title="24/7 스마트 수집기", layout="wide", page_icon="🕒")

if 'collected_titles' not in st.session_state:
    st.session_state.collected_titles = set()
if 'channel_list' not in st.session_state:
    st.session_state.channel_list = ['시그널리포트', '만담채널', 'AWAKE', '정부정책 알리미', 'Signal Search', 'Seeking Signal']

# 1. 클라이언트 생성 시 루프를 고정하지 않음
@st.cache_resource
def get_client():
    session_str = st.secrets["TELEGRAM_SESSION"]
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

st.title("🕒 중복/루프 오류 방지 수집기")

with st.sidebar:
    st.header("🛠 관리")
    if st.button("⚠️ 강제 시스템 리셋"):
        st.cache_resource.clear()
        st.session_state.clear()
        st.rerun()
    st.write("---")
    selected_names = [name for name in st.session_state.channel_list if st.checkbox(name, value=True, key=f"v_final_{name}")]

status_ui = st.empty()

async def start_monitoring():
    client = get_client()
    try:
        # 2. 구글 인증 정보 로드 (파일 대신 Secrets 사용)
        creds_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        gc = gspread.authorize(creds)
        doc = gc.open_by_url(SHEET_URL)
        
        # 3. 현재 루프에 맞춰 연결
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
                kst = pytz.timezone('Asia/Seoul')
                now_kst = datetime.now(kst)
                title, link = extract_link(event.raw_text)
                
                if title in st.session_state.collected_titles:
                    return
                st.session_state.collected_titles.add(title)
                
                market_status = get_market_status(now_kst)
                date_str = now_kst.strftime("%Y-%m-%d %H:%M:%S")
                today_label = now_kst.strftime("%Y-%m-%d")
                
                chat = await event.get_chat()
                clean_title = "".join(x for x in chat.title if x.isalnum() or x in " -_")[:20].strip()
                tab_name = f"{clean_title}_{today_label}"
                
                try:
                    worksheet = doc.worksheet(tab_name)
                except:
                    worksheet = doc.add_worksheet(title=tab_name[:30], rows="2000", cols="6")
                    worksheet.insert_row(["날짜", "상태", "제목", "링크"], 1)
                
                worksheet.insert_row([date_str, market_status, title, link], 2)
                st.toast(f"📥 {tab_name} 저장")
            except: pass

        status_ui.success(f"📡 감시 가동 중 ({len(target_ids)}개 채널)")
        await client.run_until_disconnected()

    except Exception as e:
        # [핵심] 루프 관련 에러 발생 시 즉시 캐시 비우고 앱 재시작
        if "loop" in str(e).lower() or "connection" in str(e).lower():
            st.cache_resource.clear()
            st.rerun()
        status_ui.error(f"❌ 오류: {e}")

# 4. 실행 방식 최적화
if selected_names:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(start_monitoring())
    except Exception as e:
        if "running" in str(e).lower():
            asyncio.create_task(start_monitoring())
else:
    status_ui.warning("채널을 선택하세요.")
