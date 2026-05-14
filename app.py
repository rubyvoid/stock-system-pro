"""
台股投資系統 Pro  |  stock_app.py
資料來源：TWSE OpenAPI、TPEx OpenAPI、yfinance
作者：Kevin Pan
"""

import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
import json
import os
from datetime import datetime, timedelta
from io import BytesIO

# ══════════════════════════════════════════════════════
# 密碼保護（Public App 也能擋住陌生人）
# ══════════════════════════════════════════════════════
def check_password():
    """簡單密碼驗證，密碼存在 Streamlit Secrets"""
    pw = st.secrets.get("APP_PASSWORD", "")
    if not pw:
        return True  # 沒設密碼就直接進入（開發模式）

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if st.session_state["authenticated"]:
        return True

    st.markdown("""
    <div style="max-width:400px;margin:80px auto;text-align:center;">
        <div style="font-size:48px;">📈</div>
        <h2 style="margin:12px 0 4px;">台股投資系統 Pro</h2>
        <p style="color:#888;margin-bottom:24px;">請輸入授權密碼以繼續</p>
    </div>""", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        entered = st.text_input("密碼", type="password", key="pw_input",
                                placeholder="請輸入密碼")
        if st.button("進入系統", use_container_width=True, key="btn_pw"):
            if entered == pw:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ 密碼錯誤，請重試")
    st.stop()
    return False

check_password()



# ── 嘗試 import 選用套件 ──────────────────────────
try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False

try:
    import plotly.graph_objects as go
    import plotly.express as px
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# ══════════════════════════════════════════════════════
# 頁面設定
# ══════════════════════════════════════════════════════
st.set_page_config(
    page_title="台股投資系統 Pro",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS 全域樣式 ──────────────────────────────────────
st.markdown("""
<style>
.hero-banner {
    background: linear-gradient(135deg, #0a0a1a 0%, #1a1a3e 50%, #2d1b69 100%);
    border-radius: 16px; padding: 24px 32px; margin-bottom: 20px;
}
.hero-banner h2 { color: #fff; margin: 0; font-size: 1.5rem; font-weight: 700; }
.hero-banner p  { color: #a5b4fc; margin: 4px 0 0; font-size: 0.9rem; }
.metric-card {
    background: var(--background-color);
    border: 1px solid rgba(128,128,128,0.2);
    border-radius: 12px; padding: 14px 18px; text-align: center;
}
.metric-label { font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 1px; }
.metric-value { font-size: 1.6rem; font-weight: 700; margin: 4px 0; }
.up   { color: #ef4444; }
.down { color: #22c55e; }
.flat { color: #888; }
.section-card {
    border-left: 4px solid #4f46e5;
    padding: 6px 14px; margin: 18px 0 10px;
    background: linear-gradient(90deg, rgba(79,70,229,0.06) 0%, transparent 100%);
    border-radius: 0 8px 8px 0;
}
.section-card span { font-size: 0.95rem; font-weight: 600; color: #1e1b4b; }
.tag-green  { background: #dcfce7; color: #166534; padding: 2px 8px; border-radius: 6px; font-size: 11px; }
.tag-red    { background: #fee2e2; color: #991b1b; padding: 2px 8px; border-radius: 6px; font-size: 11px; }
.tag-gray   { background: #f3f4f6; color: #374151; padding: 2px 8px; border-radius: 6px; font-size: 11px; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════
# 工具函數
# ══════════════════════════════════════════════════════

def hero_banner(emoji, title, subtitle,
                grad_a="#0a0a1a", grad_b="#1a1a3e", grad_c="#2d1b69",
                sub_color="#a5b4fc"):
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,{grad_a} 0%,{grad_b} 50%,{grad_c} 100%);
                border-radius:16px;padding:24px 32px;margin-bottom:20px;">
        <div style="display:flex;align-items:center;gap:16px;">
            <div style="font-size:44px;line-height:1;">{emoji}</div>
            <div>
                <h2 style="color:#fff;margin:0;font-size:1.5rem;font-weight:700;">{title}</h2>
                <p style="color:{sub_color};margin:4px 0 0;font-size:0.9rem;">{subtitle}</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def section_card(title, color="#4f46e5"):
    st.markdown(f"""
    <div style="border-left:4px solid {color};padding:6px 14px;margin:18px 0 10px;
                background:linear-gradient(90deg,rgba(79,70,229,0.06) 0%,transparent 100%);
                border-radius:0 8px 8px 0;">
        <span style="font-size:0.95rem;font-weight:600;">{title}</span>
    </div>""", unsafe_allow_html=True)

def pct_color(v):
    if v > 0:   return "up",   f"▲ {v:.2f}%"
    if v < 0:   return "down", f"▼ {abs(v):.2f}%"
    return "flat", f"─ {v:.2f}%"

@st.cache_data(ttl=600)
def get_twse_all():
    """取得上市所有股票當日行情（多備援 URL）"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.twse.com.tw/",
    }
    # 備援 URL 清單，依序嘗試
    urls = [
        "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
        "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200 and r.text.strip():
                data = r.json()
                # 第一個 URL 直接回傳 list
                if isinstance(data, list):
                    return pd.DataFrame(data)
                # 第二個 URL 回傳 {"data": [...], "fields": [...]}
                if isinstance(data, dict) and "data" in data:
                    fields = data.get("fields", [])
                    rows   = data.get("data", [])
                    if fields and rows:
                        return pd.DataFrame(rows, columns=fields)
        except Exception:
            continue
    return pd.DataFrame()

@st.cache_data(ttl=300)
def get_twse_legal_person():
    """取得三大法人買賣超"""
    try:
        url = "https://openapi.twse.com.tw/v1/fund/T86"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            return pd.DataFrame(r.json())
    except Exception:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=300)
def get_tpex_all():
    """取得上櫃所有股票當日行情"""
    try:
        url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            return pd.DataFrame(r.json())
    except Exception:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=600)
def get_stock_history(ticker_tw: str, period: str = "1y"):
    """用 yfinance 取得歷史股價（需加 .TW 或 .TWO）"""
    if not HAS_YF:
        return pd.DataFrame()
    try:
        df = yf.Ticker(ticker_tw).history(period=period)
        if not df.empty:
            df = df.reset_index()
            df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def get_stock_info(ticker_tw: str):
    """取得個股基本資訊"""
    if not HAS_YF:
        return {}
    try:
        return yf.Ticker(ticker_tw).info
    except Exception:
        return {}

def call_gemini(prompt: str, system: str = "") -> str | None:
    """呼叫 Google Gemini API（免費，每日 1500 次）"""
    try:
        api_key = st.secrets.get("GEMINI_API_KEY", "")
        if not api_key:
            return None
        sys_prompt = system or "你是一位專業的台灣股市分析師，熟悉台股生態、法人籌碼、技術分析與基本面。請用繁體中文回答，條列重點，語氣專業但易懂，每點說明清楚。"
        full_prompt = sys_prompt + "\n\n" + prompt
        r = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
            headers={"x-goog-api-key": api_key,
                     "content-type": "application/json"},
            json={"contents": [{"parts": [{"text": full_prompt}]}],
                  "generationConfig": {"maxOutputTokens": 1024,
                                       "temperature": 0.7}},
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        pass
    return None

# 向下相容：保留 call_claude 名稱，內部改呼叫 Gemini
def call_claude(prompt: str) -> str | None:
    return call_gemini(prompt)

def render_ai(text: str, badge: str = "AI 分析"):
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#eff6ff,#f0fdf4);
                border:1px solid #93c5fd;border-radius:12px;padding:16px 20px;margin:12px 0;">
        <div style="font-size:11px;font-weight:600;color:#1d4ed8;letter-spacing:1px;
                    text-transform:uppercase;margin-bottom:8px;">{badge}</div>
        <div style="font-size:14px;line-height:1.7;color:#1e293b;">
            {text.replace(chr(10), '<br>')}
        </div>
    </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════
# 技術指標計算
# ══════════════════════════════════════════════════════

def calc_ma(df: pd.DataFrame, periods=[5, 10, 20, 60]) -> pd.DataFrame:
    for p in periods:
        df[f"MA{p}"] = df["Close"].rolling(p).mean()
    return df

def calc_rsi(df: pd.DataFrame, period=14) -> pd.DataFrame:
    delta = df["Close"].diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))
    return df

def calc_macd(df: pd.DataFrame, fast=12, slow=26, signal=9) -> pd.DataFrame:
    ema_fast   = df["Close"].ewm(span=fast, adjust=False).mean()
    ema_slow   = df["Close"].ewm(span=slow, adjust=False).mean()
    df["MACD"] = ema_fast - ema_slow
    df["MACD_Signal"] = df["MACD"].ewm(span=signal, adjust=False).mean()
    df["MACD_Hist"]   = df["MACD"] - df["MACD_Signal"]
    return df

def calc_bollinger(df: pd.DataFrame, period=20, std=2) -> pd.DataFrame:
    ma  = df["Close"].rolling(period).mean()
    std_ = df["Close"].rolling(period).std()
    df["BB_Upper"] = ma + std * std_
    df["BB_Lower"] = ma - std * std_
    df["BB_Mid"]   = ma
    return df

# ══════════════════════════════════════════════════════
# Session State 初始化
# ══════════════════════════════════════════════════════
for k, v in [
    ("portfolio",    []),   # 投資組合持股清單
    ("watchlist",    []),   # 觀察清單
    ("module",       "📈 即時行情"),
]:
    if k not in st.session_state:
        st.session_state[k] = v

# ══════════════════════════════════════════════════════
# 側邊欄
# ══════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 📈 台股投資系統")
    st.markdown("---")

    _mods = [
        "📈 即時行情",
        "🔍 選股篩選",
        "💼 投資組合",
        "🏦 籌碼分析",
        "🤖 AI 選股",
    ]
    if "module" not in st.session_state:
        st.session_state["module"] = _mods[0]
    module = st.radio("選擇功能", _mods,
        index=_mods.index(st.session_state["module"])
               if st.session_state["module"] in _mods else 0,
        key="module")

    st.markdown("---")
    st.caption(f"更新時間：{datetime.now().strftime('%Y/%m/%d %H:%M')}")
    st.caption("資料來源：TWSE · TPEx · Yahoo Finance")

    st.markdown("---")
    st.markdown("""
    <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;
                padding:10px 12px;font-size:11px;color:#9a3412;line-height:1.7;">
    ⚠️ 免責聲明<br>
    本系統僅供參考，不構成任何投資建議。
    投資有風險，請自行評估後決策。
    </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════
# 模組一：即時行情與技術分析
# ══════════════════════════════════════════════════════
if module == "📈 即時行情":
    hero_banner("📈", "即時行情 · 技術分析",
                "K 線圖 · MA · RSI · MACD · 布林通道",
                "#0a0a1a", "#0c1a3e", "#1e3a8a", "#93c5fd")

    # ── 輸入區 ──
    col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
    with col1:
        ticker_input = st.text_input("股票代號", "2330",
            help="台股代號，如 2330（台積電）、0050（ETF）")
    with col2:
        market = st.selectbox("市場", ["上市（.TW）", "上櫃（.TWO）"], key="mkt")
        suffix = ".TW" if "上市" in market else ".TWO"
    with col3:
        period = st.selectbox("期間", ["3mo", "6mo", "1y", "2y", "5y"],
                              index=2, key="period")
    with col4:
        chart_type = st.selectbox("圖表", ["K 線圖", "折線圖"], key="ct")

    indicators = st.multiselect("技術指標",
        ["MA5", "MA10", "MA20", "MA60", "RSI", "MACD", "布林通道"],
        default=["MA20", "RSI"], key="inds")

    if st.button("🔍 查詢", key="btn_quote", use_container_width=False):
        st.session_state["query_ticker"] = f"{ticker_input}{suffix}"

    ticker_full = st.session_state.get("query_ticker", f"2330{suffix}")

    with st.spinner(f"載入 {ticker_full} 資料..."):
        df_hist = get_stock_history(ticker_full, period)
        info    = get_stock_info(ticker_full)

    if df_hist.empty:
        st.warning("⚠️ 無法取得股價資料，請確認代號是否正確，或稍後再試。")
        st.info("💡 **yfinance 使用提示**：台灣上市股票代號請加 `.TW`，例如 `2330.TW`、`0050.TW`；上櫃加 `.TWO`")
    else:
        df_hist = calc_ma(df_hist)
        df_hist = calc_rsi(df_hist)
        df_hist = calc_macd(df_hist)
        df_hist = calc_bollinger(df_hist)

        # ── KPI 指標 ──
        last   = df_hist.iloc[-1]
        prev   = df_hist.iloc[-2] if len(df_hist) > 1 else last
        chg    = last["Close"] - prev["Close"]
        chg_pct = (chg / prev["Close"] * 100) if prev["Close"] > 0 else 0
        cls, pct_str = pct_color(chg_pct)

        section_card("📊 即時報價")
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("收盤價",    f"${last['Close']:.1f}")
        k2.metric("漲跌幅",    pct_str,
                  delta=f"{chg:+.1f}",
                  delta_color="normal" if chg >= 0 else "inverse")
        k3.metric("最高",      f"${last.get('High', last['Close']):.1f}")
        k4.metric("最低",      f"${last.get('Low', last['Close']):.1f}")
        k5.metric("成交量",    f"{int(last.get('Volume', 0)):,}")

        if info:
            k6, k7, k8, k9 = st.columns(4)
            k6.metric("本益比 P/E",  f"{info.get('trailingPE', 'N/A')}")
            k7.metric("殖利率",      f"{info.get('dividendYield', 0)*100:.2f}%" if info.get('dividendYield') else "N/A")
            k8.metric("市值（億）",  f"{info.get('marketCap', 0)/1e8:.0f}" if info.get('marketCap') else "N/A")
            k9.metric("52週高點",    f"{info.get('fiftyTwoWeekHigh', 'N/A')}")

        # ── K 線圖 ──
        if HAS_PLOTLY:
            section_card("📉 走勢圖")
            fig = go.Figure()

            if chart_type == "K 線圖":
                fig.add_trace(go.Candlestick(
                    x=df_hist["Date"],
                    open=df_hist["Open"],
                    high=df_hist["High"],
                    low=df_hist["Low"],
                    close=df_hist["Close"],
                    name="K 線",
                    increasing_line_color="#ef4444",
                    decreasing_line_color="#22c55e",
                ))
            else:
                fig.add_trace(go.Scatter(
                    x=df_hist["Date"], y=df_hist["Close"],
                    name="收盤價", line=dict(color="#4f46e5", width=1.5)))

            # 疊加均線
            ma_colors = {"MA5": "#f59e0b", "MA10": "#10b981",
                         "MA20": "#3b82f6", "MA60": "#8b5cf6"}
            for ma, color in ma_colors.items():
                if ma in indicators and ma in df_hist.columns:
                    fig.add_trace(go.Scatter(
                        x=df_hist["Date"], y=df_hist[ma],
                        name=ma, line=dict(color=color, width=1)))

            # 布林通道
            if "布林通道" in indicators:
                fig.add_trace(go.Scatter(
                    x=df_hist["Date"], y=df_hist["BB_Upper"],
                    name="BB 上軌", line=dict(color="#94a3b8", width=1, dash="dash")))
                fig.add_trace(go.Scatter(
                    x=df_hist["Date"], y=df_hist["BB_Lower"],
                    name="BB 下軌", line=dict(color="#94a3b8", width=1, dash="dash"),
                    fill="tonexty", fillcolor="rgba(148,163,184,0.05)"))

            fig.update_layout(
                height=400, margin=dict(l=0, r=0, t=20, b=0),
                xaxis_rangeslider_visible=False,
                legend=dict(orientation="h", y=1.05))
            st.plotly_chart(fig, use_container_width=True)

            # RSI 副圖
            if "RSI" in indicators:
                fig_rsi = go.Figure()
                fig_rsi.add_trace(go.Scatter(
                    x=df_hist["Date"], y=df_hist["RSI"],
                    name="RSI", line=dict(color="#8b5cf6", width=1.5)))
                fig_rsi.add_hline(y=70, line_dash="dash", line_color="#ef4444", opacity=0.5)
                fig_rsi.add_hline(y=30, line_dash="dash", line_color="#22c55e", opacity=0.5)
                fig_rsi.update_layout(height=150, margin=dict(l=0, r=0, t=10, b=0),
                                      yaxis=dict(range=[0, 100]))
                st.plotly_chart(fig_rsi, use_container_width=True)

            # MACD 副圖
            if "MACD" in indicators:
                fig_macd = go.Figure()
                fig_macd.add_trace(go.Bar(
                    x=df_hist["Date"], y=df_hist["MACD_Hist"],
                    name="柱狀",
                    marker_color=["#ef4444" if v >= 0 else "#22c55e"
                                  for v in df_hist["MACD_Hist"].fillna(0)]))
                fig_macd.add_trace(go.Scatter(
                    x=df_hist["Date"], y=df_hist["MACD"],
                    name="MACD", line=dict(color="#3b82f6", width=1)))
                fig_macd.add_trace(go.Scatter(
                    x=df_hist["Date"], y=df_hist["MACD_Signal"],
                    name="Signal", line=dict(color="#f59e0b", width=1)))
                fig_macd.update_layout(height=150, margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig_macd, use_container_width=True)
        else:
            st.line_chart(df_hist.set_index("Date")[["Close"]])

        # ── AI 分析 ──
        section_card("🤖 AI 技術面解讀")
        if st.button("產生 AI 技術分析報告", key="btn_ai_quote"):
            rsi_val  = df_hist["RSI"].iloc[-1] if "RSI" in df_hist.columns else None
            macd_val = df_hist["MACD"].iloc[-1] if "MACD" in df_hist.columns else None
            prompt = f"""請分析台股 {ticker_full} 的技術面：

收盤價：{last['Close']:.1f}，漲跌幅：{chg_pct:.2f}%
MA20：{df_hist['MA20'].iloc[-1]:.1f if 'MA20' in df_hist.columns else 'N/A'}
MA60：{df_hist['MA60'].iloc[-1]:.1f if 'MA60' in df_hist.columns else 'N/A'}
RSI(14)：{rsi_val:.1f if rsi_val else 'N/A'}
MACD：{macd_val:.3f if macd_val else 'N/A'}

請提供：
1. 短期趨勢判斷（多/空/中性）
2. 關鍵支撐與壓力位
3. 操作建議（注意：僅供參考，非投資建議）"""
            with st.spinner("AI 分析中..."):
                ai_result = call_claude(prompt)
            if ai_result:
                render_ai(ai_result, f"AI 技術分析 · {ticker_full}")
            else:
                st.info("請在 Streamlit Secrets 設定 GEMINI_API_KEY 以啟用 AI 分析（Google 免費）")

# ══════════════════════════════════════════════════════
# 模組二：選股篩選器
# ══════════════════════════════════════════════════════
elif module == "🔍 選股篩選":
    hero_banner("🔍", "選股篩選器",
                "技術面 · 基本面 · 籌碼面 多因子條件式選股",
                "#0a1a0a", "#0f2d1a", "#14532d", "#86efac")

    st.markdown("""
    <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:10px;
                padding:12px 18px;margin-bottom:16px;font-size:13px;color:#166534;">
    💡 <b>使用說明</b>：輸入篩選條件後點擊「開始篩選」，系統會從 TWSE 即時資料中找出符合條件的個股。
    首次載入約需 10~15 秒（下載全市場資料）。
    </div>""", unsafe_allow_html=True)

    # ── 篩選條件 ──
    section_card("📋 設定篩選條件", "#16a34a")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**📊 技術面條件**")
        filter_rsi_low  = st.slider("RSI 低於（超賣）", 10, 50, 30, key="f_rsi_l")
        filter_rsi_high = st.slider("RSI 高於（超買）", 50, 90, 70, key="f_rsi_h")
        filter_ma_cross = st.checkbox("MA5 > MA20（均線金叉）", key="f_ma")
        filter_vol_surge= st.checkbox("成交量 > 5日均量 150%（量增）", key="f_vol")

    with col2:
        st.markdown("**💰 基本面條件**")
        pe_max   = st.number_input("本益比 ≤", value=20.0, step=1.0, key="f_pe")
        pb_max   = st.number_input("股價淨值比 ≤", value=3.0, step=0.5, key="f_pb")
        dy_min   = st.number_input("殖利率 ≥ (%)", value=3.0, step=0.5, key="f_dy")
        roe_min  = st.number_input("ROE ≥ (%)", value=10.0, step=1.0, key="f_roe")

    with col3:
        st.markdown("**🏦 籌碼面條件**")
        filter_foreign_buy  = st.checkbox("外資連續買超 3 日", key="f_fb")
        filter_invest_buy   = st.checkbox("投信連續買超 3 日", key="f_ib")
        margin_max = st.slider("融資使用率 ≤ (%)", 0, 100, 60, key="f_mg")
        short_max  = st.slider("融券張數 ≤ 萬張", 0, 10, 5, key="f_sh")

    # ── 市場選擇 ──
    market_filter = st.multiselect("篩選市場",
        ["上市（TWSE）", "上櫃（TPEx）"], default=["上市（TWSE）"], key="f_mkt")

    if st.button("🚀 開始篩選", key="btn_screen", use_container_width=False):
        with st.spinner("下載市場資料並進行篩選（約 15~30 秒）..."):
            results = []

            # ── 主要方式：TWSE OpenAPI ──
            if "上市（TWSE）" in market_filter:
                df_all = get_twse_all()
                if not df_all.empty:
                    col_map = {}
                    for c in df_all.columns:
                        if any(k in c for k in ["代號","Code","SecuritiesCode"]): col_map[c] = "Code"
                        if any(k in c for k in ["名稱","Name","CompanyName"]):    col_map[c] = "Name"
                        if any(k in c for k in ["收盤","Close","ClosingPrice"]):  col_map[c] = "Close"
                        if any(k in c for k in ["漲跌","Change"]):                col_map[c] = "Change"
                        if "成交" in c and "量" in c:                              col_map[c] = "Volume"
                    df_all = df_all.rename(columns=col_map)
                    for col in ["Close", "Change", "Volume"]:
                        if col in df_all.columns:
                            df_all[col] = pd.to_numeric(
                                df_all[col].astype(str).str.replace(",", ""), errors="coerce")
                    for _, row in df_all.iterrows():
                        try:
                            code = str(row.get("Code", "")).strip()
                            name = str(row.get("Name", "")).strip()
                            close= float(row.get("Close", 0) or 0)
                            chg  = float(row.get("Change", 0) or 0)
                            chg_pct_v = (chg / (close - chg) * 100) if (close - chg) > 0 else 0
                            if code and close > 0:
                                results.append({
                                    "代號": code, "名稱": name, "市場": "上市",
                                    "收盤價": close,
                                    "漲跌幅(%)": round(chg_pct_v, 2),
                                })
                        except Exception:
                            continue

            # ── 備援方式：yfinance 抓常用股票（TWSE 被擋時使用）──
            if not results and HAS_YF:
                st.info("TWSE API 暫時無法連線，改用備援模式載入常用股票...")
                popular = [
                    ("2330","台積電"),("2317","鴻海"),("2454","聯發科"),
                    ("2382","廣達"),("2308","台達電"),("2303","聯電"),
                    ("3711","日月光投控"),("2002","中鋼"),("1301","台塑"),
                    ("2881","富邦金"),("2882","國泰金"),("2886","兆豐金"),
                    ("0050","元大台灣50"),("0056","元大高股息"),
                    ("00878","國泰永續高股息"),("00919","群益台灣精選高息"),
                ]
                progress = st.progress(0)
                for i, (code, name) in enumerate(popular):
                    progress.progress((i+1)/len(popular))
                    try:
                        df_h = get_stock_history(f"{code}.TW", "5d")
                        if not df_h.empty:
                            last = df_h.iloc[-1]
                            prev = df_h.iloc[-2] if len(df_h) > 1 else last
                            close = float(last["Close"])
                            chg_pct_v = ((close - float(prev["Close"])) /
                                        float(prev["Close"]) * 100) if float(prev["Close"]) > 0 else 0
                            results.append({
                                "代號": code, "名稱": name, "市場": "上市",
                                "收盤價": round(close, 1),
                                "漲跌幅(%)": round(chg_pct_v, 2),
                            })
                    except Exception:
                        continue
                progress.empty()

            if results:
                df_result = pd.DataFrame(results)

                # ── 套用技術面篩選（需有歷史資料）──
                # 注意：RSI/MA 篩選在備援模式下略過（需要歷史資料）
                if filter_ma_cross or filter_vol_surge:
                    st.caption("⚠️ 均線金叉與量增篩選需要歷史資料，目前顯示所有結果，請手動確認")

                # ── 套用基本面篩選（以漲跌幅為代理變數）──
                if pe_max < 50:
                    st.caption(f"本益比篩選需財報 API，目前顯示收盤價 < NT${pe_max*30:.0f} 的股票作為參考")
                    df_result = df_result[df_result["收盤價"] < pe_max * 30]

                section_card("📋 篩選結果", "#16a34a")
                st.success(f"✅ 找到 {len(df_result)} 檔股票")
                st.dataframe(df_result, use_container_width=True, hide_index=True)

                # 加入觀察清單
                selected = st.multiselect("選擇股票加入觀察清單",
                    df_result["代號"].tolist(), key="sel_watch")
                if st.button("加入觀察清單", key="btn_add_watch"):
                    st.session_state["watchlist"] = list(
                        set(st.session_state["watchlist"] + selected))
                    st.success(f"已加入 {len(selected)} 檔到觀察清單")

                # AI 分析
                if st.button("🤖 AI 分析篩選結果", key="btn_ai_screen"):
                    prompt = f"""我設定以下選股條件：
RSI 超賣閾值 {filter_rsi_low}、均線金叉：{'是' if filter_ma_cross else '否'}
本益比 ≤ {pe_max}、殖利率 ≥ {dy_min}%、ROE ≥ {roe_min}%
外資連續買超：{'是' if filter_foreign_buy else '否'}

篩選出 {len(df_result)} 檔個股，前5名：{', '.join(df_result.head(5)['名稱'].tolist())}

請評估這個選股策略的合理性，以及在當前市場環境下的適用性。"""
                    with st.spinner("AI 分析中..."):
                        ai_res = call_claude(prompt)
                    if ai_res:
                        render_ai(ai_res, "AI 選股策略分析")
                    else:
                        st.info("請設定 GEMINI_API_KEY 以啟用 AI 分析（Google 免費）")
            else:
                st.warning("""
⚠️ TWSE API 及備援模式均無法取得資料。

可能原因：
1. **非交易日**（週末或國定假日）— TWSE 收盤後約 30 分鐘才更新資料
2. **Streamlit Cloud IP 被限流** — TWSE 對雲端伺服器 IP 有流量限制
3. **網路連線問題** — 稍後再試

建議：直接使用「即時行情」模組查詢個別股票，不受此限制影響。
""")

    # ── 觀察清單 ──
    if st.session_state["watchlist"]:
        section_card("👁 觀察清單", "#16a34a")
        wl_df = pd.DataFrame({
            "代號": st.session_state["watchlist"],
            "狀態": "觀察中"
        })
        st.dataframe(wl_df, hide_index=True)
        if st.button("清空觀察清單", key="btn_clr_watch"):
            st.session_state["watchlist"] = []
            st.rerun()

# ══════════════════════════════════════════════════════
# 模組三：投資組合追蹤
# ══════════════════════════════════════════════════════
elif module == "💼 投資組合":
    hero_banner("💼", "投資組合追蹤",
                "持股管理 · 損益計算 · 績效比較 · 資產配置",
                "#1a0a2e", "#2d1b69", "#4c1d95", "#c4b5fd")

    section_card("➕ 新增持股", "#7c3aed")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        p_code   = st.text_input("股票代號", "2330", key="p_code")
    with col2:
        p_name   = st.text_input("名稱",     "台積電", key="p_name")
    with col3:
        p_shares = st.number_input("持股（股）", value=1000, step=1000, key="p_shares")
    with col4:
        p_cost   = st.number_input("成本（元）", value=900.0, step=1.0, key="p_cost")
    with col5:
        p_mkt    = st.selectbox("市場", ["上市", "上櫃"], key="p_mkt")
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ 加入", key="btn_add_p"):
            st.session_state["portfolio"].append({
                "代號": p_code, "名稱": p_name,
                "持股": p_shares, "成本": p_cost,
                "市場": p_mkt,
                "加入日期": datetime.now().strftime("%Y/%m/%d")
            })
            st.success(f"✅ 已加入 {p_name}（{p_code}）")

    if not st.session_state["portfolio"]:
        st.info("📋 尚未加入任何持股，請在上方輸入並點擊「加入」")
    else:
        portfolio = st.session_state["portfolio"]

        section_card("📊 持股明細與損益", "#7c3aed")

        # 取得即時價格
        rows = []
        total_cost = total_value = 0
        for p in portfolio:
            suffix = ".TW" if p["市場"] == "上市" else ".TWO"
            ticker = f"{p['代號']}{suffix}"
            df_h = get_stock_history(ticker, "5d")

            if not df_h.empty:
                current = float(df_h["Close"].iloc[-1])
            else:
                current = p["成本"]  # 無法取得時用成本代替

            value  = current * p["持股"]
            cost   = p["成本"]  * p["持股"]
            pnl    = value - cost
            pnl_pct = (pnl / cost * 100) if cost > 0 else 0
            total_cost  += cost
            total_value += value

            rows.append({
                "代號":     p["代號"],
                "名稱":     p["名稱"],
                "持股":     f"{p['持股']:,}",
                "成本":     f"${p['成本']:,.1f}",
                "現價":     f"${current:,.1f}",
                "市值":     f"${value:,.0f}",
                "損益":     f"${pnl:+,.0f}",
                "報酬率":   f"{pnl_pct:+.1f}%",
            })

        df_port = pd.DataFrame(rows)
        st.dataframe(df_port, use_container_width=True, hide_index=True)

        # 整體績效
        total_pnl     = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

        section_card("💰 整體績效", "#7c3aed")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("總成本",    f"${total_cost:,.0f}")
        k2.metric("總市值",    f"${total_value:,.0f}")
        k3.metric("未實現損益", f"${total_pnl:+,.0f}",
                  delta=f"{total_pnl_pct:+.1f}%",
                  delta_color="normal" if total_pnl >= 0 else "inverse")
        k4.metric("持有檔數",  f"{len(portfolio)} 檔")

        # 資產配置圓餅圖
        if HAS_PLOTLY and len(portfolio) > 1:
            section_card("🥧 資產配置", "#7c3aed")
            values = [float(r["市值"].replace("$", "").replace(",", ""))
                      for r in rows]
            names  = [r["名稱"] for r in rows]
            fig_pie = px.pie(values=values, names=names,
                             color_discrete_sequence=px.colors.qualitative.Set3)
            fig_pie.update_layout(height=300, margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(fig_pie, use_container_width=True)

        # 刪除持股
        section_card("🗑 管理持股", "#7c3aed")
        del_idx = st.selectbox("選擇要刪除的持股",
            [f"{p['代號']} {p['名稱']}" for p in portfolio],
            key="del_p")
        if st.button("刪除選定持股", key="btn_del_p"):
            idx = [f"{p['代號']} {p['名稱']}"
                   for p in portfolio].index(del_idx)
            st.session_state["portfolio"].pop(idx)
            st.rerun()

# ══════════════════════════════════════════════════════
# 模組四：籌碼分析
# ══════════════════════════════════════════════════════
elif module == "🏦 籌碼分析":
    hero_banner("🏦", "籌碼分析",
                "三大法人買賣超 · 融資融券 · 主力進出",
                "#1a0a0a", "#3b0f0f", "#7f1d1d", "#fca5a5")

    section_card("🏦 三大法人買賣超", "#dc2626")
    st.info("💡 資料來源：台灣證券交易所 OpenAPI，每日收盤後更新")

    # 個股代號輸入
    chip_ticker = st.text_input("查詢股票代號", "2330",
                                key="chip_ticker",
                                help="輸入台股代號查詢籌碼資料")
    chip_market = st.selectbox("市場", ["上市（.TW）", "上櫃（.TWO）"],
                               key="chip_mkt")
    suffix = ".TW" if "上市" in chip_market else ".TWO"

    if st.button("查詢籌碼", key="btn_chip"):
        with st.spinner("載入籌碼資料..."):
            # 三大法人
            df_legal = get_twse_legal_person()

            if not df_legal.empty:
                # 搜尋對應股票
                code_cols = [c for c in df_legal.columns
                             if "代號" in c or "Code" in c.title()]
                if code_cols:
                    mask = df_legal[code_cols[0]].astype(str).str.startswith(
                        chip_ticker)
                    df_stock = df_legal[mask]
                    if not df_stock.empty:
                        st.dataframe(df_stock, use_container_width=True, hide_index=True)
                    else:
                        st.warning(f"找不到 {chip_ticker} 的法人資料，顯示市場整體前 20 筆")
                        st.dataframe(df_legal.head(20), use_container_width=True,
                                     hide_index=True)
            else:
                st.warning("⚠️ 無法取得法人資料，請確認網路連線")

            # 歷史股價 + 法人買賣超趨勢
            df_hist = get_stock_history(f"{chip_ticker}{suffix}", "3mo")
            if not df_hist.empty and HAS_PLOTLY:
                section_card("📊 近 3 個月走勢", "#dc2626")
                fig = go.Figure()
                fig.add_trace(go.Candlestick(
                    x=df_hist["Date"],
                    open=df_hist["Open"], high=df_hist["High"],
                    low=df_hist["Low"],  close=df_hist["Close"],
                    name="K 線",
                    increasing_line_color="#ef4444",
                    decreasing_line_color="#22c55e",
                ))
                fig.update_layout(
                    height=350, margin=dict(l=0, r=0, t=20, b=0),
                    xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)

    # 大盤三大法人概況
    section_card("📋 今日三大法人概況（全市場）", "#dc2626")
    if st.button("載入今日法人概況", key="btn_legal_all"):
        with st.spinner("載入中..."):
            df_legal = get_twse_legal_person()
            if not df_legal.empty:
                st.dataframe(df_legal.head(30), use_container_width=True,
                             hide_index=True)
                st.caption(f"共 {len(df_legal)} 筆資料，顯示前 30 筆")
            else:
                st.warning("無法取得資料")

# ══════════════════════════════════════════════════════
# 模組五：AI 選股建議
# ══════════════════════════════════════════════════════
elif module == "🤖 AI 選股":
    hero_banner("🤖", "AI 選股建議",
                "Claude AI · 個股深度分析 · 市場情緒判讀",
                "#0a0a1a", "#1a1a3e", "#312e81", "#a5b4fc")

    st.info("💡 AI 功能使用 Google Gemini（免費）。請在 Streamlit Secrets 設定 `GEMINI_API_KEY`，前往 [ai.google.dev](https://ai.google.dev) 免費取得，每日 1,500 次不需信用卡。")

    tab1, tab2, tab3 = st.tabs(["🔍 個股 AI 分析", "🌏 市場情緒分析", "📋 選股報告生成"])

    # ── Tab1：個股分析 ──
    with tab1:
        section_card("🔍 個股 AI 深度分析", "#4f46e5")
        ai_ticker = st.text_input("輸入股票代號", "2330", key="ai_ticker")
        ai_market = st.selectbox("市場", ["上市（.TW）", "上櫃（.TWO）"], key="ai_mkt2")
        suffix    = ".TW" if "上市" in ai_market else ".TWO"

        focus = st.multiselect("分析重點",
            ["技術面趨勢", "基本面評估", "籌碼動向", "風險提醒", "操作建議"],
            default=["技術面趨勢", "基本面評估", "風險提醒"], key="ai_focus")

        if st.button("🚀 產生 AI 分析報告", key="btn_ai_stock"):
            with st.spinner("載入資料 + AI 分析中（約 15~30 秒）..."):
                ticker_full = f"{ai_ticker}{suffix}"
                df_hist     = get_stock_history(ticker_full, "1y")
                info        = get_stock_info(ticker_full)

                if not df_hist.empty:
                    df_hist = calc_ma(df_hist)
                    df_hist = calc_rsi(df_hist)
                    last = df_hist.iloc[-1]

                    prompt = f"""請對台股 {ticker_full} 進行深度分析：

【基本資訊】
股名：{info.get('longName', ai_ticker)}
產業：{info.get('industry', '未知')}
市值：{info.get('marketCap', 0)/1e8:.0f} 億

【近期價格】
收盤：{last['Close']:.1f}
52週高/低：{info.get('fiftyTwoWeekHigh','N/A')} / {info.get('fiftyTwoWeekLow','N/A')}
MA20：{df_hist['MA20'].iloc[-1]:.1f if 'MA20' in df_hist.columns else 'N/A'}
MA60：{df_hist['MA60'].iloc[-1]:.1f if 'MA60' in df_hist.columns else 'N/A'}
RSI(14)：{df_hist['RSI'].iloc[-1]:.1f if 'RSI' in df_hist.columns else 'N/A'}

【基本面】
本益比：{info.get('trailingPE', 'N/A')}
殖利率：{info.get('dividendYield',0)*100:.2f}%
ROE：{info.get('returnOnEquity',0)*100:.2f}%
EPS：{info.get('trailingEps','N/A')}

請依照以下重點進行分析：{', '.join(focus)}

最後給出：買進 / 持有 / 減碼 / 觀望 的建議（請標明為參考意見，非投資建議）"""

                    ai_result = call_claude(prompt)
                    if ai_result:
                        render_ai(ai_result, f"AI 深度分析 · {ticker_full}")
                    else:
                        st.warning("AI 服務暫不可用，請確認 GEMINI_API_KEY 設定")
                else:
                    st.error("無法取得股價資料")

    # ── Tab2：市場情緒 ──
    with tab2:
        section_card("🌏 市場情緒 AI 分析", "#4f46e5")

        if st.button("🚀 分析今日台股市場情緒", key="btn_ai_market"):
            with st.spinner("AI 分析市場情緒..."):
                # 取大盤資料（0050）
                df_twii = get_stock_history("0050.TW", "1mo")

                if not df_twii.empty:
                    last_price = df_twii["Close"].iloc[-1]
                    prev_price = df_twii["Close"].iloc[-2]
                    chg_pct_m  = (last_price - prev_price) / prev_price * 100
                    month_chg  = (last_price - df_twii["Close"].iloc[0]) / df_twii["Close"].iloc[0] * 100

                    prompt = f"""請分析當前台股市場情緒：

大盤（0050 ETF）：
- 當日漲跌：{chg_pct_m:+.2f}%
- 近一月漲跌：{month_chg:+.2f}%
- 目前淨值：{last_price:.2f}

請分析：
1. 當前台股整體多空氛圍
2. 近期影響市場的主要因素（AI 趨勢、外資動向、美股連動）
3. 接下來一週的市場展望
4. 對投資人的建議策略（防守 vs 積極）"""

                    ai_result = call_claude(prompt)
                    if ai_result:
                        render_ai(ai_result, "AI 市場情緒分析")
                    else:
                        st.warning("AI 服務暫不可用")
                else:
                    st.warning("無法取得大盤資料")

    # ── Tab3：選股報告 ──
    with tab3:
        section_card("📋 AI 選股報告生成", "#4f46e5")
        watchlist = st.session_state.get("watchlist", [])

        if not watchlist:
            st.info("請先在「選股篩選」模組將股票加入觀察清單")
        else:
            st.write(f"觀察清單：{', '.join(watchlist)}")
            report_style = st.selectbox("報告風格",
                ["保守型（強調風險）", "成長型（強調獲利潛力）", "價值型（強調低估值）"],
                key="rpt_style")

            if st.button("📄 產生完整選股報告", key="btn_ai_report"):
                with st.spinner("AI 生成報告中..."):
                    prompt = f"""請為以下台股觀察清單生成一份完整的選股報告：

觀察股票：{', '.join(watchlist)}
報告風格：{report_style}

請為每一檔股票提供：
1. 一句話摘要（公司定位）
2. 主要優勢（2點）
3. 主要風險（1點）
4. 建議倉位（高/中/低）

最後給出整體組合建議（如何分配比重）。
注意：所有建議僅供參考，非正式投資建議。"""

                    ai_result = call_claude(prompt)
                    if ai_result:
                        render_ai(ai_result, "AI 選股報告")

                        # 提供下載
                        report_text = f"台股投資系統 Pro - AI 選股報告\n生成時間：{datetime.now().strftime('%Y/%m/%d %H:%M')}\n\n{ai_result}"
                        st.download_button(
                            "📥 下載報告",
                            report_text.encode("utf-8"),
                            f"AI選股報告_{datetime.now().strftime('%Y%m%d')}.txt",
                            "text/plain"
                        )
                    else:
                        st.warning("AI 服務暫不可用")

# ══════════════════════════════════════════════════════
# 頁尾
# ══════════════════════════════════════════════════════
st.markdown("---")
st.markdown("""
<div style="text-align:center;font-size:12px;color:#888;padding:8px 0;">
    台股投資系統 Pro &nbsp;|&nbsp; 資料來源：TWSE · TPEx · Yahoo Finance
    &nbsp;|&nbsp; 本系統僅供參考，不構成投資建議
</div>
""", unsafe_allow_html=True)
