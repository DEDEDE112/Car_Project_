"""
ui.py — 二手車租約風險評估系統 · 重構版
架構原則：
  - UI 只呼叫兩個後端介面（與 engine.py 的真實簽名完全對齊）：
      1. search_callback(user_input: str) -> str   # RAGEngine.search
      2. get_legal_summary(query: str, docs: str) -> str  # engine.get_legal_summary
  - 所有量化指標均從這兩個回傳的「字串」推導，不新增任何後端呼叫
  - analysis_results dict 作為 UI 各區塊的統一資料來源，方便後續整合
"""

import streamlit as st
# ✅ 修改後：同時 import 這兩個函式
from engine import get_legal_summary, check_input_sanity


# ─────────────────────────────────────────────
# 【Step 1】從兩個後端字串推導所有 UI 所需數值
# 只做字串解析，不呼叫任何後端函式
# ─────────────────────────────────────────────

def _parse_risk_level(ai_report: str) -> str:
    """
    從 get_legal_summary 回傳的報告字串解析風險等級。
    對齊 engine.py prompt 的【強制規定】：最後一行為 【風險等級：高/中/低】
    與原始 ui.py 的清洗邏輯相同，保持相容。
    """
    clean = ai_report.replace(" ", "").replace("*", "").replace(":", "：")
    if "風險等級：高" in clean:
        return "高"
    elif "風險等級：中" in clean:
        return "中"
    else:
        return "低"


def _estimate_case_similarity(raw_documents: str) -> float:
    """
    從 RAGEngine.search 回傳的字串估算「案例相似度」。
    engine.py 的 search() 用 FAISS L2 distance，距離越小越相似。
    由於目前 search() 只回傳合併文字（不含 Distance 數值），
    此處以「成功找到的案例數量」作為相似度代理指標：
      - 找到 3 筆 → 0.85（最高，代表索引飽和）
      - 找到 2 筆 → 0.65
      - 找到 1 筆 → 0.45
      - 0 筆     → 0.20
    ※ 待 engine.py 日後回傳 Distance 數值時，直接替換此函式即可。
    """
    count = raw_documents.count("--- 參考判決案例")
    mapping = {3: 0.85, 2: 0.65, 1: 0.45}
    return mapping.get(count, 0.20)


def _estimate_info_completeness(user_input: str) -> float:
    """
    從使用者輸入字串估算「資訊完整度」。
    不呼叫任何後端，純粹做啟發式計算：
      - 基礎分：0.40
      - 含金額數字（數字＋元）：+0.20
      - 含時間資訊（天/月/年/期間）：+0.15
      - 字數 > 30 字：+0.15
      - 含具體條款關鍵詞（折舊/賠償/違約/逸失）：+0.10
    上限 1.0
    """
    score = 0.40
    if any(c.isdigit() for c in user_input) and "元" in user_input:
        score += 0.20
    if any(kw in user_input for kw in ["天", "月", "年", "期間", "日"]):
        score += 0.15
    if len(user_input) > 30:
        score += 0.15
    if any(kw in user_input for kw in ["折舊", "賠償", "違約", "逸失", "條款"]):
        score += 0.10
    return min(round(score, 2), 1.0)


def _estimate_confidence(case_similarity: float, info_completeness: float) -> int:
    """
    綜合案例相似度與資訊完整度推導 AI 信心指數（1～5 顆星）。
    不呼叫任何後端。
    """
    combined = (case_similarity * 0.4) + (info_completeness * 0.6)
    if combined >= 0.80:
        return 5
    elif combined >= 0.68:
        return 4
    elif combined >= 0.55:
        return 3
    elif combined >= 0.40:
        return 2
    else:
        return 1


def _detect_intent(user_input: str) -> str:
    """
    純 UI 層的意圖標籤，用於 Agent 分流展示。
    完全不影響 engine.py，只做關鍵詞比對。
    """
    complex_kws = ["賠償", "損失", "引擎", "全額", "折舊", "違約", "逸失", "條款"]
    if len(user_input) > 50 or any(kw in user_input for kw in complex_kws):
        return "複雜法律爭議"
    return "一般條款諮詢"


def _build_analysis_results(
    user_input: str,
    raw_documents: str,
    ai_report: str,
) -> dict:
    """
    統一組裝 analysis_results dict。
    輸入：engine.py 兩個函式的真實回傳字串。
    輸出：所有 UI 區塊共用的資料來源。

    ── 後端整合說明 ──
    若未來 engine.py 新增回傳結構化資料（如 Distance、structured_cases），
    只需在此函式替換對應的推導邏輯，UI 渲染層完全不用動。
    """
    case_similarity   = _estimate_case_similarity(raw_documents)
    info_completeness = _estimate_info_completeness(user_input)
    ai_confidence     = _estimate_confidence(case_similarity, info_completeness)
    final_risk_score  = round((case_similarity * 0.4) + (info_completeness * 0.6), 3)
    risk_level        = _parse_risk_level(ai_report)
    intent_label      = _detect_intent(user_input)

    # 結構化判決書：從 RAGEngine.search 回傳的字串解析
    # engine.py 的格式固定為「--- 參考判決案例 N ---\n{內容}\n\n」
    raw_clean = raw_documents.replace("_x000D_", "\n")
    raw_cases = [c.strip() for c in raw_clean.split("--- 參考判決案例") if c.strip()]
    structured_cases = []
    for chunk in raw_cases:
        # 取第一行作為案例標題，其餘為內容
        lines = [l for l in chunk.splitlines() if l.strip()]
        title = lines[0].strip(" -") if lines else "—"
        body  = "\n".join(lines[1:]) if len(lines) > 1 else "（內容待解析）"
        structured_cases.append({
            "id":      title,    # 案件編號（原始文字，未結構化）
            "court":   "—",      # 待 engine 回傳結構化資料後填入
            "verdict": "—",      # 同上
            "rule":    body,     # 判決書主體文字
        })

    return {
        # ── 量化指標 ──
        "case_similarity":   case_similarity,
        "info_completeness": info_completeness,
        "ai_confidence":     ai_confidence,
        "final_risk_score":  final_risk_score,
        # ── 質化結果 ──
        "risk_level":        risk_level,
        "ai_report":         ai_report,
        "raw_documents":     raw_documents,
        # ── Agent 分流（UI 展示用） ──
        "agent_used":        "P1: GPT-4o-mini",   # engine.py 固定使用此模型
        "intent_label":      intent_label,
        # ── 結構化判決書 ──
        "structured_cases":  structured_cases,
    }


# ─────────────────────────────────────────────
# 【Step 2】UI 渲染元件（只讀 analysis_results）
# ─────────────────────────────────────────────

def _render_quantitative_dashboard(results: dict):
    """
    量化風險儀表板：4 欄佈局
      欄 1（感性）：預估法律風險 — 表情圖標 + 狀態標籤
      欄 2～4（理性）：判決匹配度、資訊完整度、AI 信心指數
    下方：公式展開 + 進度條
    """
    sim   = results["case_similarity"]
    comp  = results["info_completeness"]
    conf  = results["ai_confidence"]
    final = results["final_risk_score"]
    level = results["risk_level"]

    st.markdown("#### 📊 風險量化計算儀表板")

    # ── 欄 1 風險等級對應設定 ──
    risk_config = {
        "高": {
            "icon":       "🚩",
            "label":      "極高",
            "delta":      "↓ -需高度注意",
            "delta_color": "inverse",        # st.metric delta 紅色
            "badge_bg":   "#ffd7d7",
            "badge_fg":   "#7d0000",
        },
        "中": {
            "icon":       "😐",
            "label":      "中等",
            "delta":      "↕ -存在爭議",
            "delta_color": "off",
            "badge_bg":   "#fff3cd",
            "badge_fg":   "#7d5c00",
        },
        "低": {
            "icon":       "✅",
            "label":      "安全",
            "delta":      "↑ 法律保障",
            "delta_color": "normal",         # 綠色
            "badge_bg":   "#d4edda",
            "badge_fg":   "#155724",
        },
    }
    cfg = risk_config.get(level, risk_config["低"])

    # ── 四欄 metric 區 ──
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        # st.metric 顯示圖標與等級；badge 用 HTML 補背景色標籤
        st.metric(
            label="🎯 預估法律風險",
            value=f"{cfg['icon']} {cfg['label']}",
            delta=cfg["delta"],
            delta_color=cfg["delta_color"],
            help="依 AI 報告末行的【風險等級】標籤判定，對應法院實務傾向。",
        )
        st.markdown(
            f"""<div style="
                display:inline-block;
                background:{cfg['badge_bg']};
                color:{cfg['badge_fg']};
                padding:2px 10px;
                border-radius:12px;
                font-size:0.78rem;
                font-weight:600;
                margin-top:2px;
            ">風險值 {final:.1%}</div>""",
            unsafe_allow_html=True,
        )

    with c2:
        sign = "+" if sim >= 0.5 else ""
        st.metric(
            label="🔗 判決匹配度",
            value=f"{sim:.0%}",
            delta=f"↑ 高相關" if sim >= 0.7 else f"{sign}{(sim - 0.5):.0%} 匹配",
            delta_color="normal",
            help="由 RAGEngine.search 找到的案例數量估算。"
                 "待 engine.py 回傳 FAISS Distance 數值後可精確換算。",
        )

    with c3:
        info_label = "充足" if comp >= 0.7 else "普通" if comp >= 0.5 else "不足"
        st.metric(
            label="📋 資訊完整度",
            value=f"{comp:.0%}",
            delta=f"↑ 判定：{info_label}" if comp >= 0.7 else f"判定：{info_label}",
            delta_color="normal" if comp >= 0.5 else "inverse",
            help="依使用者輸入是否含金額、時間、條款關鍵詞進行啟發式評估。",
        )

    with c4:
        stars = "⭐" * conf + "☆" * (5 - conf)
        st.metric(
            label="🤖 AI 信心指數",
            value=stars,
            delta="Seed 42 / 穩定",
            delta_color="off",
            help="綜合案例相似度與資訊完整度加權計算（temperature=0, seed=42）。",
        )

    # ── 公式展開 + 進度條 ──
    st.markdown("")
    with st.container(border=True):
        st.markdown(
            f"""**AI信心指數計算公式：**
```
AI信心指數 = (判決匹配度 × 0.4) + (資訊完整度 × 0.6)
           = ({sim:.2f} × 0.4) + ({comp:.2f} × 0.6)
           = {sim * 0.4:.3f}   +   {comp * 0.6:.3f}
           = {final:.3f}
```"""
        )
        st.progress(final, text=f"AI信心指數：{final:.1%}")


def _render_risk_banner(results: dict):
    """風險等級橫幅：依 engine.py prompt 輸出的風險標籤渲染"""
    level = results["risk_level"]
    score = results["final_risk_score"]

    if level == "高":
        st.error(f"🚩 高風險判定（{score:.0%}）：法律實務多傾向支持對造，建議尋求專業法律協助。")
    elif level == "中":
        st.warning(f"⚠️ 中度風險（{score:.0%}）：雙方各有勝負空間，取決於舉證細節。")
    else:
        st.success(f"✅ 低度風險（{score:.0%}）：法律明確保障承租人，實務傾向您這方。")


def _render_ai_report(results: dict):
    """AI 報告主體 + 下載按鈕"""
    with st.container(border=True):
        st.markdown(results["ai_report"])

    col_dl, col_agent = st.columns([2, 1])
    with col_dl:
        st.download_button(
            label="📥 下載完整分析報告 (.md)",
            data=results["ai_report"],
            file_name="二手車法律風險評估報告.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with col_agent:
        st.info(f"分析引擎：{results['agent_used']}", icon="🤖")


def _render_structured_cases(results: dict):
    """
    判決書展示（美化版）：
    - st.tabs 按案例分頁
    - 每個案例用 HTML 卡片渲染，解析出案件資訊列＋段落區塊
    - 關鍵法律詞彙自動高亮
    """
    import re as _re
    import html as _html

    raw_documents = results.get("raw_documents", "")
    clean_docs = raw_documents.replace("_x000D_", "\n")
    cases = [c.strip() for c in clean_docs.split("--- 參考判決案例") if c.strip()]

    # ── 關鍵詞高亮清單（與 processor.py 的過濾關鍵詞對齊）──
    HIGHLIGHT_KEYWORDS = [
        "賠償", "違約", "折舊", "營業損失", "逸失利益", "租金", "承租人", "出租人",
        "租賃", "解除契約", "損害賠償", "原廠", "修復費用", "全損", "市場價值",
    ]

    def _highlight(text: str) -> str:
        """對關鍵詞套上黃底標記（HTML-safe）"""
        escaped = _html.escape(text)
        for kw in HIGHLIGHT_KEYWORDS:
            escaped = escaped.replace(
                _html.escape(kw),
                f'<mark style="background:#fff3cd;color:#7d5c00;'
                f'border-radius:3px;padding:0 2px;">{_html.escape(kw)}</mark>',
            )
        return escaped

    def _parse_case_html(raw: str, case_num: int) -> str:
        """
        將單份判決書原始文字轉為 HTML 卡片。
        解析邏輯：
          - 第一行若含「---」為殘留編號頭，跳過
          - 嘗試從前 5 行抓取法院名稱與案號
          - 其餘段落每 3 行一組，用 <p> 包裝並高亮
        """
        lines = [l.rstrip() for l in raw.splitlines()]

        # 去掉殘留的「N ---」編號行
        if lines and _re.match(r'^\d+\s*-+\s*$', lines[0]):
            lines = lines[1:]

        # ── 嘗試抽取法院 & 案號（前 6 行掃描）──
        court_name = ""
        case_id    = ""
        header_end = 0
        for idx, line in enumerate(lines[:6]):
            if not court_name and any(kw in line for kw in ["法院", "地方", "高等"]):
                court_name = line.strip()
            if not case_id and _re.search(r'\d+年度.+字第\d+號', line):
                case_id = _re.search(r'\d+年度.+字第\d+號', line).group()
            if idx >= 2 and (court_name or case_id):
                header_end = idx + 1
                break

        # ── 正文段落（header 之後的行）──
        body_lines = lines[header_end:] if header_end else lines
        # 過濾空行並分段（每 4 行一個 <p>）
        non_empty = [l for l in body_lines if l.strip()]
        paragraphs = []
        chunk_size = 4
        for i in range(0, len(non_empty), chunk_size):
            chunk = "　".join(non_empty[i:i + chunk_size])
            paragraphs.append(f"<p style='margin:0 0 8px 0;line-height:1.9;'>{_highlight(chunk)}</p>")

        body_html = "\n".join(paragraphs) if paragraphs else "<p>（判決內文解析中）</p>"

        # ── 組裝 HTML 卡片 ──
        meta_badges = ""
        if court_name:
            meta_badges += (
                f'<span style="background:#e8f4fd;color:#1a6fa8;'
                f'padding:2px 10px;border-radius:12px;font-size:0.78rem;'
                f'font-weight:600;margin-right:6px;">🏛️ {_html.escape(court_name)}</span>'
            )
        if case_id:
            meta_badges += (
                f'<span style="background:#f0f0f0;color:#444;'
                f'padding:2px 10px;border-radius:12px;font-size:0.78rem;'
                f'font-weight:600;margin-right:6px;">📋 {_html.escape(case_id)}</span>'
            )
        if not meta_badges:
            meta_badges = (
                f'<span style="background:#f0f0f0;color:#888;'
                f'padding:2px 10px;border-radius:12px;font-size:0.78rem;">'
                f'案例 {case_num}</span>'
            )

        html = f"""
<div style="
    font-family: 'Noto Sans TC', '微軟正黑體', sans-serif;
    font-size: 0.88rem;
    color: #2c2c2c;
">
  <!-- 案件資訊列 -->
  <div style="
      display:flex; align-items:center; flex-wrap:wrap; gap:6px;
      padding:10px 14px; margin-bottom:12px;
      background:#f8f9fa; border-radius:8px;
      border-left:4px solid #4a90d9;
  ">
    {meta_badges}
  </div>

  <!-- 判決正文 -->
  <div style="
      padding:4px 6px;
      max-height:300px;
      overflow-y:auto;
      border-radius:6px;
  ">
    {body_html}
  </div>

  <!-- 底部提示 -->
  <div style="
      margin-top:10px; padding:6px 12px;
      background:#fffbe6; border-radius:6px;
      font-size:0.76rem; color:#7d6608;
      border:1px solid #ffe58f;
  ">
    💡 黃色標記為法律關鍵詞，判決書原文由 RAGEngine 自向量索引取得。
  </div>
</div>
"""
        return html

    # ── 渲染 ──
    if len(cases) > 1:
        tabs = st.tabs([f"📌 判決案例 {i + 1}" for i in range(len(cases))])
        for i, tab in enumerate(tabs):
            with tab:
                st.markdown(
                    _parse_case_html(cases[i], i + 1),
                    unsafe_allow_html=True,
                )
    else:
        st.markdown(
            _parse_case_html(clean_docs, 1),
            unsafe_allow_html=True,
        )



# ─────────────────────────────────────────────
# 【主 UI 進入點】
# ─────────────────────────────────────────────

def run_ui(search_callback):
    """
    主 UI 函式。
    簽名與原始 ui.py 完全相同：run_ui(search_callback)
    search_callback：RAGEngine.search，簽名為 (query: str) -> str
    """
    st.set_page_config(
        page_title="二手車租約風險評估",
        page_icon="🛡️",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
        [data-testid="stMetricDelta"] { white-space: normal !important; }
        hr { border-color: rgba(128,128,128,0.2) !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── 頁首 ──
    st.title("🛡️ 二手車租約風險評估系統")
    st.caption(
        "整合向量語義搜尋（FAISS）× GPT-4o-mini 法律推理 × 歷年法院判決大數據，"
        "量化預析您的合約法律風險。"
    )
    st.markdown("---")

    # ── 主版面 ──
    left_col, right_col = st.columns([1, 1.4], gap="large")

    with left_col:
        st.subheader("📝 爭議情境輸入")

        with st.expander("📖 提問範例與操作指南"):
            st.markdown(
                """
**操作步驟**
1. 描述租約條文或車損爭議情境
2. 點擊「開始深度分析」
3. 閱讀 AI 量化風險報告

**提問範例**
- `合約規定車損賠償原廠全新品，法院會支持計算折舊嗎？`
- `租車期間引擎過熱損壞，合約說壞掉都算我的，這合理嗎？`
- `維修期間業者要求賠償全額營業損失，每日 3,000 元共 15 天，合法嗎？`

> 💡 **提示**：描述中包含金額、天數、具體條款，AI 比對精準度顯著提升。
                """
            )

        user_input = st.text_area(
            "請描述具體情境：",
            placeholder="例如：維修期間被要求賠償全額營業損失，業者主張每日 3,000 元，共 15 天...",
            height=280,
        )

        analyze_btn = st.button(
            "🚀 開始法律風險深度分析",
            use_container_width=True,
            type="primary",
        )

    with right_col:
        st.subheader("🤖 AI 風險評估報告")

        if analyze_btn:
            if not user_input.strip():
                st.warning("⚠️ 請先輸入爭議情境再進行分析。")
            else:
                with st.spinner("🔍 系統正在進行輸入安全性檢查..."):
                    sanity_check = check_input_sanity(user_input)
                
                if not sanity_check["is_valid"]:
                    st.error(f"🛑 偵測到無效輸入：{sanity_check['reason']}")
                    st.info("💡 提示：請輸入與二手車租約、合約條款、車損折舊、或營業損失相關的具體爭議情境。")
                else:
                    try:
                            # ── 呼叫後端（對齊 engine.py 真實介面）──
                        # 1. RAGEngine.search(query) -> str
                        raw_documents = search_callback(user_input)
                        # 2. get_legal_summary(query, docs) -> str
                        ai_report = get_legal_summary(user_input, raw_documents)

                        # ── 組裝 analysis_results（所有 UI 的唯一資料來源）──
                        results = _build_analysis_results(user_input, raw_documents, ai_report)

                        # ── 渲染各區塊 ──
                        _render_quantitative_dashboard(results)
                        st.markdown("")

                        _render_risk_banner(results)
                        st.markdown("")

                        st.markdown("#### 📄 完整法律風險分析報告")
                        _render_ai_report(results)
                        st.markdown("")

                        with st.expander("📚 查看 AI 參考的原始法院判決書（結構化展示）", expanded=False):
                            _render_structured_cases(results)

                    except Exception as e:
                        st.error(f"❌ 分析過程中發生錯誤：{e}")
                        st.exception(e)
        else:
            st.info("請於左側輸入爭議情境並點擊「開始法律風險深度分析」，報告將顯示於此。")
            st.markdown(
                """
| 功能 | 說明 |
|---|---|
| 🔗 FAISS 向量語義搜尋 | 比對歷年法院判決書，精準找出相似案例 |
| 🤖 GPT-4o-mini 法律推理 | 綜合多份判決書進行風險評估 |
| 📊 量化風險儀表板 | 公式化計算，呈現可解釋的風險數值 |
| 📚 結構化判決書展示 | 解析案件編號、判決內文、核心規則 |
                """
            )

    # ── 頁尾 ──
    st.markdown("---")
    st.caption(
        "⚠️ 免責聲明：本系統報告僅供學術研究與初步參考，不代表正式法律建議。"
        "如涉及重大財務或法律決定，請諮詢持照律師。"
    )
