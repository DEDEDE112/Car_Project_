import streamlit as st
from processor import load_and_filter_data
from engine import RAGEngine
from ui import run_ui

# 加上快取魔法咒語，讓系統只在第一次啟動時讀取大數據
@st.cache_resource
def init_system():
    data = load_and_filter_data()
    
    # 🌟 關鍵修改：明確告訴程式去抓「完整判決內容」這一個欄位
    docs = data['完整判決內容'].astype(str).tolist() 
    
    engine = RAGEngine(docs)
    return engine

# 啟動系統並將結果存進快取
engine = init_system()

if __name__ == "__main__":
    run_ui(engine.search)
