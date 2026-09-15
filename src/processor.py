import pandas as pd
import re
import os
from pathlib import Path
import streamlit as st

def load_and_filter_data():
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data"
    
    # 用萬用字元比對「中古車_dataset_」開頭、.xlsx 結尾的檔案，
    # 避免因為檔名裡有沒有「~」符號（例如 2000~2020 vs 20002020）
    # 或年份格式微調而找不到檔案。
    files = sorted(data_dir.glob("中古車_dataset_*.xlsx"))
    all_dfs = []

    if not files:
        print(f"⚠️ 在 {data_dir} 找不到任何符合「中古車_dataset_*.xlsx」的檔案")

    for p in files:
        if p.exists():
            df = pd.read_excel(p)
            # 🚨 修正點：自動修正欄位名稱左右空白
            df.columns = df.columns.str.strip()
            all_dfs.append(df)
            print(f"📖 讀取檔案成功：{p.name}，欄位有：{df.columns.tolist()}")
        else:
            print(f"⚠️ 找不到檔案：{p}")

    if not all_dfs:
        st.error("❌ 完全找不到 Excel 資料，請檢查 data 資料夾路徑！")
        return None

    full_df = pd.concat(all_dfs, ignore_index=True)

    # 🔍 【自動偵測目標欄位】
    # 我們不寫死 '內容'，而是找包含這些關鍵字的欄位
    possible_names = ['內容', '全文', '內文', '判決內容', '文字', 'Content']
    target_col = None
    for col in full_df.columns:
        if any(name in str(col) for name in possible_names):
            target_col = col
            break

    if not target_col:
        st.error(f"❌ 找不到存放判決內容的欄位！目前欄位：{full_df.columns.tolist()}")
        return None

    print(f"🎯 鎖定判決欄位：【{target_col}】")

    # ── 清洗資料 ──
    def clean_text(text):
        if not isinstance(text, str): return ""
        text = text.replace("_x000D_", "\n")
        return re.sub(r'\n+', '\n', text).strip()

    full_df[target_col] = full_df[target_col].apply(clean_text)

    # ── 租賃案例過濾 ──
    # 使用我們偵測到的 target_col
    mask_car = full_df[target_col].str.contains('車|小客車', na=False)
    mask_leasing = full_df[target_col].str.contains('租賃|租車|承租|出租|租金', na=False)
    mask_not_pure_sales = ~full_df[target_col].str.contains('買賣糾紛|請求給付價金|調表', na=False)
    
    final_df = full_df[mask_car & mask_leasing & mask_not_pure_sales].copy()
    print(f"✅ 資料過濾完成，剩餘 {len(final_df)} 筆。")
    
    return final_df.reset_index(drop=True)