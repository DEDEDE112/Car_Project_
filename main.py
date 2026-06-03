import streamlit as st
from processor import load_and_filter_data
from engine import RAGEngine
from ui import run_ui

# 加上快取魔法咒語，讓系統只在第一次啟動時讀取大數據
@st.cache_resource
def init_system():
    data = load_and_filter_data()
    
    # 🌟 守護之眼提醒：請確認 Excel 欄位名稱是「整判決內容」還是「完整判決內容」
    # 根據你之前的截圖，欄位名稱似乎是「整判決內容」
    column_name = '整判決內容' if '整判決內容' in data.columns else '完整判決內容'
    docs = data[column_name].astype(str).tolist() 
    
    engine = RAGEngine(docs)
    return engine

# 1. 核心修正：在程式最開頭初始化 Session State
# 這樣可以確保 run_ui 在執行時，變數空間已經準備好
if "user_query" not in st.session_state:
    st.session_state.user_query = ""

# 啟動系統並將結果存進快取
engine = init_system()

if __name__ == "__main__":
    # 2. 確保呼叫 run_ui
    run_ui(engine.search)
