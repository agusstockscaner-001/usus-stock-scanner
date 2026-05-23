"""
AI US Stock Scanner - Swing Trading Saham Amerika
Sistem TERPISAH. Data Yahoo Finance lewat Cloudflare Worker.
Target: swing 1-6 hari, +5%. Universe: blue chip + growth populer.
"""

import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from urllib.parse import quote

st.set_page_config(page_title="US Stock Scanner", page_icon="🇺🇸", layout="wide", initial_sidebar_state="collapsed")

# ============================================================
PROXY = "https://yahoo-proxy.agusstockscaner.workers.dev/?url="
# ============================================================

st.markdown("""
<style>
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 1rem !important; max-width: 100%; }
    .stock-card { background: linear-gradient(135deg,#101822,#15202e); border:1px solid #1d2a3a; border-radius:12px; padding:14px; margin-bottom:10px; }
    .priority-card { border:1px solid #2d5a3d; box-shadow:0 0 15px rgba(0,255,136,0.15); }
    .gem-card { border:1px solid #1a3a5a; }
    .badge { display:inline-block; padding:3px 10px; border-radius:12px; font-size:11px; font-weight:700; font-family:monospace; }
    .stButton button { width:100%; border-radius:8px; font-weight:600; }
    @media (max-width:768px){ .stock-card{padding:12px;font-size:13px;} h1{font-size:22px!important;} }
</style>
""", unsafe_allow_html=True)

# Universe US: blue chip + growth populer
SEKTOR = {
    "TECH MEGA": ["AAPL","MSFT","GOOGL","AMZN","META"],
    "SEMICONDUCTOR": ["NVDA","AMD","AVGO","INTC","MU","QCOM","TSM"],
    "GROWTH/EV": ["TSLA","NFLX","UBER","ABNB","SHOP","PLTR"],
    "FINANCE": ["JPM","BAC","V","MA","GS"],
    "CONSUMER": ["KO","PEP","MCD","NKE","SBUX","COST","WMT"],
    "HEALTH": ["JNJ","PFE","UNH","LLY","ABBV"],
    "ENERGY": ["XOM","CVX"],
    "INDUSTRIAL": ["BA","CAT","GE"],
    "ENTERTAINMENT": ["DIS"],
    "AI/SOFTWARE": ["CRM","ORCL","ADBE","NOW"],
}
WATCHLIST = [s for l in SEKTOR.values() for s in l]

@st.cache_data(ttl=300)
def fetch_chart(symbol, rng="1y"):
    yahoo = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={rng}&interval=1d"
    try:
        r = requests.get(PROXY + quote(yahoo, safe=""), timeout=15)
        if r.status_code != 200: return None
        result = r.json()["chart"]["result"][0]
        q = result["indicators"]["quote"][0]
        clean = []
        for o,h,l,c,v in zip(q["open"],q["high"],q["low"],q["close"],q["volume"]):
            if all(x is not None for x in [o,h,l,c,v]) and o>0:
                clean.append((o,h,l,c,v))
        if len(clean) < 50: return None
        o,h,l,c,v = zip(*clean)
        return {"open":list(o),"high":list(h),"low":list(l),"close":list(c),"volume":list(v)}
    except Exception:
        return None

@st.cache_data(ttl=3600)
def fetch_fundamental(symbol):
    yahoo = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules=defaultKeyStatistics,financialData,summaryDetail"
    try:
        r = requests.get(PROXY + quote(yahoo, safe=""), timeout=15)
        if r.status_code != 200: return None
        result = r.json()["quoteSummary"]["result"][0]
        ks = result.get("defaultKeyStatistics",{}); fd = result.get("financialData",{}); sd = result.get("summaryDetail",{})
        def safe(d,k):
            v = d.get(k,{}); return v.get("raw") if isinstance(v,dict) else None
        return {"per":safe(sd,"trailingPE") or safe(ks,"trailingPE"),"pbv":safe(ks,"priceToBook"),
                "roe":safe(fd,"returnOnEquity"),"der":safe(fd,"debtToEquity"),
                "rev_growth":safe(fd,"revenueGrowth")}
    except Exception:
        return None

def ema(d,p):
    if len(d)<p: return []
    out=[sum(d[:p])/p]; m=2/(p+1)
    for x in d[p:]: out.append((x-out[-1])*m+out[-1])
    return out
def rsi(d,p=14):
    if len(d)<p+1: return 50
    g=l=0
    for i in range(1,p+1):
        x=d[-i]-d[-i-1]
        if x>=0: g+=x
        else: l+=abs(x)
    ag,al=g/p,l/p
    if al==0: return 100
    return 100-(100/(1+ag/al))
def macd(d):
    e12,e26=ema(d,12),ema(d,26)
    if not e12 or not e26: return 0,0,0
    n=min(len(e12),len(e26))
    m=[e12[-n+i]-e26[-n+i] for i in range(n)]
    s=ema(m,9)
    h=m[-1]-(s[-1] if s else 0)
    hp=(m[-2]-s[-2]) if len(m)>1 and len(s)>1 else 0
    return m[-1],(s[-1] if s else 0),h-hp

def score_fund(f):
    if not f: return 50,"N/A",{}
    sc,n=0,0; det={}
    # PER US biasanya lebih tinggi dari IDX, sesuaikan threshold
    if f.get("per") and f["per"]>0:
        per=f["per"]; det["PER"]=f"{per:.0f}x"
        sc+=90 if per<15 else 80 if per<25 else 65 if per<35 else 45 if per<50 else 25; n+=1
    if f.get("pbv") and f["pbv"]>0:
        pbv=f["pbv"]; det["PBV"]=f"{pbv:.1f}x"
        sc+=90 if pbv<2 else 75 if pbv<5 else 55 if pbv<10 else 35; n+=1
    if f.get("roe") is not None:
        roe=f["roe"]*100; det["ROE"]=f"{roe:.0f}%"
        sc+=95 if roe>25 else 80 if roe>15 else 60 if roe>10 else 40 if roe>5 else 25 if roe>0 else 5; n+=1
    if f.get("rev_growth") is not None:
        rg=f["rev_growth"]*100; det["Rev Growth"]=f"{rg:+.0f}%"
        sc+=90 if rg>20 else 75 if rg>10 else 55 if rg>0 else 30; n+=1
    if n==0: return 50,"N/A",det
    fin=sc/n
    lbl="💎 EXCELLENT" if fin>=75 else "✅ GOOD" if fin>=60 else "⚠️ FAIR" if fin>=45 else "❌ POOR"
    return fin,lbl,det

def weekly_trend(cl):
    weekly = cl[::5]
    if len(weekly) < 10: return "NETRAL", 0
    we10 = ema(weekly, 10)
    if not we10: return "NETRAL", 0
    if weekly[-1] > we10[-1]: return "BULLISH", 3
    return "BEARISH", -2

def detect_accumulation(cl, vol):
    if len(vol) < 20: return False, 0
    rec = sum(vol[-5:])/5; old = sum(vol[-20:-5])/15
    pc5 = (cl[-1]-cl[-6])/cl[-6]*100 if len(cl)>=6 else 0
    if rec > old*1.2 and -3 < pc5 < 5: return True, 5
    return False, 0

def detect_breakout(cl, hi, vol):
    if len(hi) < 21: return False, 0
    resist = max(hi[-21:-1]); avgv = sum(vol[-20:])/20
    if cl[-1] > resist and vol[-1] > avgv*1.5: return True, 6
    return False, 0

def analyze(symbol, mbonus, regime):
    d = fetch_chart(symbol)
    if not d: return None
    op,hi,lo,cl,vol = d["open"],d["high"],d["low"],d["close"],d["volume"]
    harga = cl[-1]
    e20,e50 = ema(cl,20),ema(cl,50)
    if not e20 or not e50: return None
    avgv = sum(vol[-20:])/20
    vr = vol[-1]/avgv if avgv>0 else 0
    rv = rsi(cl)
    ml,ms,hist_mom = macd(cl)

    score = 0
    if harga>e20[-1]: score+=3
    if harga>e50[-1]: score+=3
    if e20[-1]>e50[-1]: score+=4
    if 45<=rv<=68: score+=4
    elif rv>75: score-=4
    if ml>ms: score+=4
    if hist_mom>0: score+=2
    if vr>=1.8: score+=5
    elif vr>=1.3: score+=3

    wtrend,wbonus = weekly_trend(cl); score+=wbonus
    is_accum,ab = detect_accumulation(cl,vol); score+=ab
    is_breakout,bb = detect_breakout(cl,hi,vol); score+=bb

    if regime=="🔴 BEARISH":
        if harga>e20[-1] and wtrend=="BULLISH": score+=3
        else: score+=mbonus
    else: score+=mbonus

    sup = min(lo[-20:]); res = max(hi[-21:-1])
    rr = (res-harga)/(harga-sup) if harga>sup else 0
    crange = hi[-1]-lo[-1]
    if crange<=0: return None
    cpos = (cl[-1]-lo[-1])/crange
    nearhigh = cpos>=0.7
    of = 0
    if nearhigh: of+=3
    if vr>=1.5: of+=3
    if cl[-1]>op[-1]: of+=2
    upper = hi[-1]-cl[-1]; body = abs(cl[-1]-op[-1])
    dist = vr>=2 and upper>body and cpos<0.5
    if dist: score-=6
    fake = hi[-1]>res and harga<res and vr>=1.3
    if fake: score-=7

    fp = score + of
    fund = fetch_fundamental(symbol)
    fs,fl,fdet = score_fund(fund)
    if fs<30: fp-=8

    tags = []
    if is_accum: tags.append("🐋 Accum")
    if is_breakout: tags.append("🚀 Breakout")
    if wtrend=="BULLISH": tags.append("📈 Weekly Bull")
    if hist_mom>0: tags.append("⚡ MACD↑")
    smart = is_accum or is_breakout

    if fake or dist: dec="🚫 AVOID"
    elif fp>=30 and rr>=1.5 and fs>=45 and smart: dec="🔥 PRIORITY BUY"
    elif fp>=24 and rr>=1.2 and fs>=40 and (smart or wtrend=="BULLISH"): dec="🎯 SWING TARGET"
    elif fp>=15: dec="👀 WATCH"
    else: dec="🚫 AVOID"

    if fake or dist or fs<30: risk="HIGH"
    elif rr>=1.8 and nearhigh and fs>=60 and smart: risk="LOW"
    else: risk="MEDIUM"

    conf = max(0,min(95,int(fp*2.3+(fs-50)*0.2)))
    tpct = ((res-harga)/harga)*100
    slpct = ((harga-sup)/harga)*100
    flow = "🐋 ACCUMULATION" if is_accum else "⚠️ DISTRIBUTION" if dist else "NORMAL"
    sector = next((s for s,l in SEKTOR.items() if symbol in l),"OTHER")
    return {"symbol":symbol,"sector":sector,"harga":harga,
            "change":(cl[-1]-cl[-2])/cl[-2]*100,"fp":fp,"rr":rr,"conf":conf,"risk":risk,
            "flow":flow,"dec":dec,"fs":fs,"fl":fl,"fdet":fdet,"tpct":tpct,"slpct":slpct,"rsi":rv,"vr":vr,
            "is_gem":fp>=22 and fs>=70,"tags":tags,"wtrend":wtrend}

def regime():
    d = fetch_chart("SPY", rng="6mo")  # S&P 500 ETF = patokan market US
    if not d: return "UNKNOWN",0
    cl = d["close"]; e20,e50 = ema(cl,20),ema(cl,50)
    if not e20 or not e50: return "UNKNOWN",0
    h = cl[-1]
    if h>e20[-1]>e50[-1]: return "🟢 STRONG BULLISH",4
    elif h>e50[-1]: return "🟡 NEUTRAL",0
    return "🔴 BEARISH",-4

@st.cache_data(ttl=3600)
def backtest_symbol(symbol, target_pct=5, sl_pct=3, hold_days=6):
    d = fetch_chart(symbol, rng="1y")
    if not d: return None
    cl,hi,lo,vol = d["close"],d["high"],d["low"],d["volume"]
    wins=total=0
    for i in range(60, len(cl)-hold_days):
        sub = cl[:i]; subhi = hi[:i]
        e20,e50 = ema(sub,20),ema(sub,50)
        if not e20 or not e50: continue
        rv = rsi(sub); ml,ms,_ = macd(sub)
        avgv = sum(vol[i-20:i])/20; vr = vol[i]/avgv if avgv>0 else 0
        rec = sum(vol[i-5:i])/5; old = sum(vol[i-20:i-5])/15
        pc5 = (sub[-1]-sub[-6])/sub[-6]*100 if len(sub)>=6 else 0
        is_accum = rec>old*1.2 and -3<pc5<5
        resist = max(subhi[-21:-1]) if len(subhi)>=21 else max(subhi)
        is_breakout = cl[i]>resist and vol[i]>avgv*1.5
        smart = is_accum or is_breakout
        sup = min(lo[i-20:i]); res = max(subhi[-21:-1]) if len(subhi)>=21 else max(subhi)
        rr = (res-cl[i])/(cl[i]-sup) if cl[i]>sup else 0
        sig = (sub[-1]>e20[-1]>e50[-1] and 45<=rv<=68 and ml>ms and vr>=1.3 and smart and rr>=1.2)
        if sig:
            entry=cl[i]; fhigh=max(hi[i+1:i+1+hold_days]); flow=min(lo[i+1:i+1+hold_days])
            gain=(fhigh-entry)/entry*100
            total+=1
            if gain>=target_pct: wins+=1
    if total==0: return None
    return {"symbol":symbol,"total":total,"wins":wins,"win_rate":wins/total*100}

fmtp = lambda p:"$"+format(round(p,2),",")

c1,c2 = st.columns([3,1])
with c1:
    st.markdown("# 🇺🇸 US Stock Scanner")
    st.caption(f"Swing 1-6 hari · Target 5%+ · Blue Chip + Growth · {datetime.now().strftime('%d %b %Y · %H:%M')}")
with c2:
    if st.button("🔄 Refresh", use_container_width=True, type="primary"):
        st.cache_data.clear(); st.rerun()

reg,bonus = regime()
if reg=="UNKNOWN":
    st.error("⚠️ Gagal ambil data S&P 500. Coba Refresh.")
else:
    st.info(f"**Market Regime S&P 500:** {reg}")

st.caption("⏰ Catatan: market US buka jam 20:30-03:00 WIB. Data di luar jam itu = penutupan terakhir.")

if 'us_results' not in st.session_state:
    st.session_state.us_results=None
if st.session_state.us_results is None:
    prog = st.progress(0,text="Scanning US stocks...")
    res=[]
    for i,s in enumerate(WATCHLIST):
        prog.progress((i+1)/len(WATCHLIST),text=f"Scanning {s}... ({i+1}/{len(WATCHLIST)})")
        r = analyze(s,bonus,reg)
        if r: res.append(r)
    prog.empty()
    st.session_state.us_results = sorted(res,key=lambda x:x["conf"],reverse=True)
results = st.session_state.us_results or []

def card(s,cls="stock-card"):
    color = {"🔥 PRIORITY BUY":"#00ff88","🎯 SWING TARGET":"#4da6ff","👀 WATCH":"#ffd32a","🚫 AVOID":"#ff4757"}.get(s["dec"],"#888")
    tp = s["harga"]*(1+s["tpct"]/100); sl = s["harga"]*(1-s["slpct"]/100)
    cc = "#00ff88" if s["change"]>=0 else "#ff4757"; cs = "+" if s["change"]>=0 else ""
    tags_html = " ".join([f'<span class="badge" style="background:#1a3a2a;color:#7fffd4;">{t}</span>' for t in s.get("tags",[])])
    fd = s.get("fdet",{})
    fund_html = " ".join([f'<span class="badge" style="background:#243a50;color:#9cf;">{k}: {v}</span>' for k,v in fd.items()])
    st.markdown(f"""<div class="stock-card {cls}">
    <div style="display:flex;justify-content:space-between;margin-bottom:10px;">
    <div><div style="font-size:20px;font-weight:800;color:#fff;">{s['symbol']}</div>
    <div style="font-size:11px;color:#888;">{s['sector']}</div></div>
    <div style="text-align:right;"><div style="font-size:18px;font-weight:700;color:#fff;">{fmtp(s['harga'])}</div>
    <div style="font-size:12px;color:{cc};">{cs}{s['change']:.2f}%</div></div></div>
    <div style="background:#0a1018;border-radius:8px;padding:10px;margin-bottom:10px;">
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;text-align:center;">
    <div><div style="font-size:10px;color:#666;">CONFIDENCE</div><div style="font-size:18px;font-weight:700;color:{color};">{s['conf']}%</div></div>
    <div><div style="font-size:10px;color:#666;">TARGET</div><div style="font-size:16px;font-weight:700;color:#00ff88;">+{s['tpct']:.1f}%</div></div>
    <div><div style="font-size:10px;color:#666;">R/R</div><div style="font-size:16px;font-weight:700;color:#ffd32a;">{s['rr']:.1f}x</div></div></div></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px;font-size:12px;">
    <div style="background:#0a1018;padding:6px 10px;border-radius:6px;"><span style="color:#666;">🎯 Target:</span> <span style="color:#fff;">{fmtp(tp)}</span></div>
    <div style="background:#0a1018;padding:6px 10px;border-radius:6px;"><span style="color:#666;">🛑 Stop:</span> <span style="color:#fff;">{fmtp(sl)}</span></div></div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px;">
    <span class="badge" style="background:{color}22;color:{color};border:1px solid {color}66;">{s['dec']}</span>
    <span class="badge" style="background:#243a50;color:#ccc;">Fund: {s['fl']}</span>
    <span class="badge" style="background:#243a50;color:#ccc;">Risk: {s['risk']}</span></div>
    <div style="margin-bottom:6px;">{fund_html}</div>
    <div style="margin-bottom:6px;">{tags_html}</div>
    <div style="font-size:11px;color:#666;">RSI: {s['rsi']:.0f} · Vol: {s['vr']:.1f}x · Weekly: {s['wtrend']} · Flow: {s['flow']}</div></div>""",unsafe_allow_html=True)

t1,t2,t3,t4,t5 = st.tabs(["🔥 Hotlist","💎 Quality","📊 All","🧪 Backtest","ℹ️ Info"])
with t1:
    hot = [s for s in results if "PRIORITY BUY" in s["dec"] or "SWING TARGET" in s["dec"]]
    st.markdown(f"### 🔥 {len(hot)} Buy Signals")
    st.caption("Tag 🐋 Accum / 🚀 Breakout / 📈 Weekly Bull = kualitas lebih tinggi")
    if not hot: st.info("Tidak ada sinyal kuat saat ini.")
    for s in hot: card(s,"priority-card")
with t2:
    gems = [s for s in results if s["is_gem"]]
    st.markdown(f"### 💎 {len(gems)} Quality Stocks")
    st.caption("Fundamental EXCELLENT + teknikal bagus")
    if not gems: st.info("Belum ada.")
    for s in gems: card(s,"gem-card")
with t3:
    st.markdown(f"### 📊 All ({len(results)})")
    mc = st.slider("Min Confidence",0,95,40,5)
    fil = [s for s in results if s["conf"]>=mc]
    if fil:
        df = pd.DataFrame([{"Stock":s["symbol"],"Sector":s["sector"],"Price":fmtp(s["harga"]),
            "Conf%":s["conf"],"Target%":f"+{s['tpct']:.1f}","R/R":f"{s['rr']:.1f}x",
            "PER":s["fdet"].get("PER","-"),"ROE":s["fdet"].get("ROE","-"),
            "Weekly":s["wtrend"],"Signal":s["dec"].split()[1] if " " in s["dec"] else s["dec"]} for s in fil])
        st.dataframe(df,use_container_width=True,hide_index=True,height=500)
with t4:
    st.markdown("### 🧪 Backtest (Target 5% / 6 hari)")
    st.caption("Uji: berapa % sinyal historis BENAR naik ≥5% dalam 6 hari (data 1 tahun). Win rate JUJUR.")
    if st.button("▶️ Run Backtest (±1 menit)"):
        prog2 = st.progress(0,text="Backtesting...")
        bt=[]
        for i,s in enumerate(WATCHLIST):
            prog2.progress((i+1)/len(WATCHLIST),text=f"Backtest {s}...")
            r = backtest_symbol(s)
            if r and r["total"]>=3: bt.append(r)
        prog2.empty()
        if bt:
            tt=sum(r["total"] for r in bt); tw=sum(r["wins"] for r in bt)
            wr=tw/tt*100 if tt else 0
            st.metric("📊 Win Rate Keseluruhan", f"{wr:.1f}%", f"{tw}/{tt} trades")
            st.caption(f"Dari {tt} sinyal historis, {tw} berhasil naik ≥5% dalam 6 hari.")
            df_bt = pd.DataFrame([{"Stock":r["symbol"],"Total":r["total"],
                "Wins":r["wins"],"Win Rate":f"{r['win_rate']:.0f}%"} for r in sorted(bt,key=lambda x:x["win_rate"],reverse=True)])
            st.dataframe(df_bt,use_container_width=True,hide_index=True,height=400)
            if wr<50: st.warning("⚠️ Win rate di bawah 50%. Hati-hati, jangan over-trade.")
            elif wr<60: st.info("Win rate 50-60% — wajar untuk swing. Risk management tetap kunci.")
            else: st.success("Win rate di atas 60% — bagus, tapi tetap pakai stop loss.")
with t5:
    st.markdown("""
    ### ℹ️ US Stock Scanner
    
    **Kenapa saham US sering lebih cocok untuk scanner:**
    - Data fundamental Yahoo lebih lengkap (jarang N/A)
    - Likuiditas sangat tinggi, spread kecil
    - Volume & harga lebih bersih untuk analisa teknikal
    
    **Sama seperti scanner IDX:**
    - Multi-timeframe (harian + mingguan)
    - Deteksi akumulasi & breakout
    - MACD momentum, RSI, EMA 20/50
    - Market regime pakai **S&P 500 (SPY)** sebagai patokan
    
    ### ⏰ Jam Market US (Waktu Indonesia/WIB)
    - **Reguler:** 20:30 - 03:00 WIB (malam-dini hari)
    - **Saat WIB siang**, market US tutup → data = penutupan terakhir
    - Untuk swing, ini OK. Tapi sadari datanya bukan live saat siang WIB.
    
    ### ⚠️ Hal Penting untuk Trading Saham US
    - **Perlu broker yang support saham US** (Interactive Brokers, dll) atau lokal yang ada akses US
    - **Pajak & regulasi berbeda** dari saham IDX — pelajari dulu
    - **Kurs USD/IDR** memengaruhi hasil dalam Rupiah
    - **Modal lebih besar** biasanya dibutuhkan (1 saham bisa ratusan USD)
    
    ### ⚠️ Disclaimer
    - TIDAK ADA prediksi pasti — ini probabilitas
    - Win rate realistis swing: 50-65%
    - Selalu pakai stop loss · jangan invest uang yang tak siap rugi
    - Tools edukasi · keputusan & risiko di tangan kamu
    """)
