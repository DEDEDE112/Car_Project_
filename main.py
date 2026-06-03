import os
import sys

# 🚨 【核心防禦 1】強制對齊雲端工作目錄，讓 processor 找得到 data/ 資料夾
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
os.chdir(current_dir)

import streamlit as st
from processor import load_and_filter_data
from engine import RAGEngine
from ui import run_ui

@st.cache_resource
def init_system():
    # 讀取 Excel
    data = load_and_filter_data()
    
    if data is None or data.empty:
        st.error("❌ 完全找不到 Excel 資料，請檢查 data 資料夾路徑與檔案名稱！")
        return None

    # 🚨 【核心防禦 2】清除欄位前後空白，並進行動態模糊比對，不寫死 '完整判決內容'
    data.columns = data.columns.str.strip()
    possible_names = ['完整判決內容', '內容', '全文', '內文', '判決內容', '文字', 'Content']
    target_col = None
    
    for col in data.columns:
        if any(name in str(col) for name in possible_names):
            target_col = col
            break
            
    if not target_col:
        st.error(f"❌ 找不到判決內文欄位。目前的欄位有：{data.columns.tolist()}")
        return None
        
    docs = data[target_col].astype(str).tolist()
    engine = RAGEngine(docs)
    return engine

# 啟動系統
engine = init_system()

if __name__ == "__main__":
    if engine is not None:
        run_ui(engine.search)
