import pandas as pd
import re
from pathlib import Path
import streamlit as st

def load_and_filter_data():
    base_dir = Path(__file__).resolve().parent
    
    # 🚨 【無敵大絕招】：不要寫死檔名！讓程式自動抓取目錄下所有的 Excel 檔案
    # 這樣就能完全避開「波浪號 ~」或全半形字元造成的檔名不吻合問題
    excel_files = list(base_dir.rglob("*.xlsx"))
    all_dfs = []
    
    for p in excel_files:
        try:
            df = pd.read_excel(p)
            df.columns = df.columns.str.strip() # 自動清掉欄位前後的空白
            all_dfs.append(df)
            print(f"📖 讀取檔案成功：{p.name}")
        except Exception as e:
            print(f"⚠️ 讀取 {p.name} 失敗：{e}")

    # 如果還是抓不到，印出路徑方便除錯
    if not all_dfs:
        st.error(f"❌ 完全找不到 Excel 資料！目前系統搜尋的路徑是：{base_dir}")
        return None

    # 將所有讀取到的 Excel 完美合併
    full_df = pd.concat(all_dfs, ignore_index=True)

    # 🔍 自動偵測目標欄位（包含你們可能用到的所有名字）
    possible_names = ['內容', '全文', '內文', '判決內容', '文字', 'Content', '完整判決內容', '整判決內容']
    target_col = None
    for col in full_df.columns:
        if any(name in str(col) for name in possible_names):
            target_col = col
            break

    if not target_col:
        st.error(f"❌ 找不到存放判決內容的欄位！目前欄位有：{full_df.columns.tolist()}")
        return None

    # ── 清洗資料 ──
    def clean_text(text):
        if not isinstance(text, str): return ""
        text = text.replace("_x000D_", "\n")
        return re.sub(r'\n+', '\n', text).strip()

    full_df[target_col] = full_df[target_col].apply(clean_text)

    # ── 租賃案例過濾 ──
    mask_car = full_df[target_col].str.contains('車|小客車', na=False)
    mask_leasing = full_df[target_col].str.contains('租賃|租車|承租|出租|租金', na=False)
    mask_not_pure_sales = ~full_df[target_col].str.contains('買賣糾紛|請求給付價金|調表', na=False)
    
    final_df = full_df[mask_car & mask_leasing & mask_not_pure_sales].copy()
    
    return final_df.reset_index(drop=True)
