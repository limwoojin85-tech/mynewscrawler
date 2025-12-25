import streamlit as st
import asyncio
from telethon import TelegramClient, events
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# [고정 정보]
API_ID = 31483914
API_HASH = '1962ae18860f8433f4ecfcfa24c4e2e0'
SHEET_URL = 'https://docs.google.com/spreadsheets/d/15MtSL0NZRbPCP9P_0LanlORFm9MYUVhk4F0LzaM9Rlw/edit'

st.set_page_config(page_title="뉴스 수집 제어 센터", layout="wide", page_icon="📡")

# --- 1. 세션 상태 초기화 (채널 목록 관리) ---
if 'channel_list' not in st.session_state:
    # 기본 목록에서 요청하신 3개 채널 제외
    st.session_state.channel_list = [
        '시그널리포트', '만담채널', 'AWAKE', 
        '정부정책 알리미', 'newsguy', 'Signal Search', 'Seeking Signal'
    ]

# --- 2. 텔레그램 클라이언트 캐싱 (에러 방지 핵심) ---
@st.cache_resource
def get_client(api_id, api_hash):
    # 이벤트 루프 고정
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return TelegramClient(f'session_{api_id}', api_id, api_hash, loop=loop)

# --- 3. UI 구성 ---
st.title("📡 실시간 뉴스 수집 제어판")

# 사이드바: 채널 관리 권한
with st.sidebar:
    st.header("🛠 채널 목록 관리")
    
    # 채널 추가
    new_ch = st.text_input("추가할 채널명 입력:")
    if st.button("채널 추가") and new_ch:
        if new_ch not in st.session_state.channel_list:
            st.session_state.channel_list.append(new_ch)
            st.rerun()

    st.write("---")
    st.header("⚙️ 수집 활성화 선택")
    selected_names = []
    for ch_name in st.session_state.channel_list:
        col1, col2 = st.columns([4, 1])
        with col1:
            if st.checkbox(ch_name, value=True, key=f"check_{ch_name}"):
                selected_names.append(ch_name)
        with col2:
            # 채널 삭제 버튼
            if st.button("❌", key=f"del_{ch_name}"):
                st.session_state.channel_list.remove(ch_name)
                st.rerun()

status_log = st.empty()
message_log = st.container()

# --- 4. 메인 수집 로직 ---
async def start_monitoring():
    try:
        # 구글 시트 연결
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        gc = gspread.authorize(creds)
        doc = gc.open_by_url(SHEET_URL)
        
        client = get_client(API_ID, API_HASH)
        
        # 이미 연결되어 있다면 새로 시작하지 않음 (Event Loop 에러 방지)
        if not client.is_connected():
            await client.start()
        
        status_log.info("🔍 구독 목록 매칭 중...")
        dialogs = await client.get_dialogs()
        
        target_ids = []
        for name in selected_names:
            for d in dialogs:
                if name.lower() in d.name.lower():
                    target_ids.append(d.id)
                    break
        
        if not target_ids:
            status_log.error("❌ 매칭된 채널이 없습니다.")
            return

        # 기존 핸들러 청소 후 새로 등록
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
                print(f"📥 {clean_title} 저장 성공")
            except Exception as e:
                print(f"기록 중 오류: {e}")

        status_log.success(f"✅ {len(target_ids)}개 채널 감시 가동 중! (웹창을 닫지 마세요)")
        await client.run_until_disconnected()

    except Exception as e:
        st.error(f"시스템 오류: {e}")
        # 에러 발생 시 클라이언트 연결 강제 종료 후 재시도 가능케 함
        if 'client' in locals() and client.is_connected():
            await client.disconnect()

if st.button("🚀 실시간 수집 시작"):
    asyncio.run(start_monitoring())