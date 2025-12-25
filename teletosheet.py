import streamlit as st
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz  # 시간대 설정을 위한 라이브러리
import json
import re

# [설정]
API_ID = 31483914
API_HASH = '1962ae18860f8433f4ecfcfa24c4e2e0'
SHEET_URL = 'https://docs.google.com/spreadsheets/d/15MtSL0NZRbPCP9P_0LanlORFm9MYUVhk4F0LzaM9Rlw/edit'

st.set_page_config(page_title="24/7 스마트 뉴스 수집기", layout="wide", page_icon="🕒")

# 중복 체크 및 채널 목록 초기화
if 'collected_titles' not in st.session_state:
    st.session_state.collected_titles = set()
if 'channel_list' not in st.session_state:
    st.session_state.channel_list = ['시그널리포트', '만담채널', 'AWAKE', '정부정책 알리미', 'Signal Search', 'Seeking Signal']

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
    """한국 시간 기준으로 장중/장마감 구분"""
    # 평일(월~금: 0~4) 확인
    is_weekday = now_kst.weekday() < 5
    # 시간 확인 (08:00 ~ 20:00)
    is_market_time = 8 <= now_kst.hour < 20
    
    # 공휴일 체크 로직은 별도 API가 필요하므로, 여기서는 평일/시간으로 1차 구분
    if is_weekday and is_market_time:
        return "☀️ 장중"
    else:
        return "🌙 장마감"

st.title("🕒 KST 적용 및 장중 구분 수집기")

with st.sidebar:
    st.header("🛠 설정 관리")
    new_ch = st.text_input("추가할 채널명:")
    if st.button("추가") and new_ch:
        st.session_state.channel_list.append(new_ch)
        st.rerun()
    if st.button("⚠️ 초기화"):
        st.cache_resource.clear()
        st.session_state.clear()
        st.rerun()
    st.write(f"필터링 중인 제목: {len(st.session_state.collected_titles)}건")
    st.write("---")
    selected_names = [name for name in st.session_state.channel_list if st.checkbox(name, value=True, key=f"v_kst_{name}")]

status_ui = st.empty()

async def start_monitoring():
    try:
        creds_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        gc = gspread.authorize(creds)
        doc = gc.open_by_url(SHEET_URL)
        
        client = get_client()
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
                # 1. 한국 시간대 설정
                kst = pytz.timezone('Asia/Seoul')
                now_kst = datetime.now(kst)
                
                title, link = extract_link(event.raw_text)
                
                # 2. 중복 체크
                if title in st.session_state.collected_titles:
                    return
                st.session_state.collected_titles.add(title)
                if len(st.session_state.collected_titles) > 1000:
                    st.session_state.collected_titles.pop()

                # 3. 장중/장마감 구분
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
                
                # 4. 시트에 데이터 기록 (상태 필드 추가)
                worksheet.insert_row([date_str, market_status, title, link], 2)
                st.toast(f"📥 [{market_status}] {tab_name} 저장")
            except: pass

        status_ui.success(f"📡 {len(target_ids)}개 채널 한국 시간으로 감시 중...")
        await client.run_until_disconnected()
    except Exception as e:
        status_ui.error(f"❌ 오류: {e}")

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
