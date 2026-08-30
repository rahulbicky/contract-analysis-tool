import os
import json
import time
import streamlit as st
import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = os.environ.get("CONTRACTLENS_API_URL", "http://localhost:8000")
API_KEY = os.environ.get("CONTRACTLENS_API_KEY", "")
AUTH_HEADERS = {"X-API-Key": API_KEY}

st.set_page_config(
    page_title="ContractLens - AI Contract Analysis",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('"'"'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap'"'"');
html, body, [class*="css"] { font-family: '"'"'Inter'"'"', sans-serif; }
.stApp { background: linear-gradient(135deg, #0a0e1a 0%, #0d1526 50%, #0a1020 100%); }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #0f1729 0%, #0a1020 100%); border-right: 1px solid rgba(99,179,237,0.12); }
.hero-title { font-size: 2.4rem; font-weight: 800; background: linear-gradient(135deg,#63b3ed,#a78bfa,#f472b6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; margin: 0 0 8px 0; }
.hero-sub { color: #94a3b8; font-size: 1rem; margin: 0; }
.status-online { display:inline-flex; align-items:center; gap:6px; background:rgba(34,197,94,.12); border:1px solid rgba(34,197,94,.3); border-radius:20px; padding:4px 12px; font-size:.78rem; color:#4ade80; font-weight:500; }
.status-offline { display:inline-flex; align-items:center; gap:6px; background:rgba(239,68,68,.12); border:1px solid rgba(239,68,68,.3); border-radius:20px; padding:4px 12px; font-size:.78rem; color:#f87171; font-weight:500; }
.dot-g { width:7px; height:7px; border-radius:50%; background:#4ade80; display:inline-block; animation:pg 2s infinite; }
.dot-r { width:7px; height:7px; border-radius:50%; background:#f87171; display:inline-block; }
@keyframes pg { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.5;transform:scale(1.3)} }
.risk-high { background:linear-gradient(135deg,rgba(127,29,29,.6),rgba(153,27,27,.4)); border-left:4px solid #ef4444; border-top:1px solid rgba(239,68,68,.2); border-right:1px solid rgba(239,68,68,.1); border-bottom:1px solid rgba(239,68,68,.1); padding:18px 20px; margin:10px 0; border-radius:0 12px 12px 0; color:#fef2f2; }
.risk-medium { background:linear-gradient(135deg,rgba(120,53,15,.6),rgba(146,64,14,.4)); border-left:4px solid #f59e0b; border-top:1px solid rgba(245,158,11,.2); border-right:1px solid rgba(245,158,11,.1); border-bottom:1px solid rgba(245,158,11,.1); padding:18px 20px; margin:10px 0; border-radius:0 12px 12px 0; color:#fffbeb; }
.risk-low { background:linear-gradient(135deg,rgba(20,83,45,.6),rgba(21,128,61,.4)); border-left:4px solid #22c55e; border-top:1px solid rgba(34,197,94,.2); border-right:1px solid rgba(34,197,94,.1); border-bottom:1px solid rgba(34,197,94,.1); padding:18px 20px; margin:10px 0; border-radius:0 12px 12px 0; color:#f0fdf4; }
.metric-row { display:flex; gap:14px; margin:16px 0; }
.mcard { flex:1; background:rgba(15,25,50,.8); border:1px solid rgba(99,179,237,.12); border-radius:12px; padding:16px; text-align:center; }
.mval { font-size:2rem; font-weight:800; line-height:1; margin-bottom:4px; }
.mlbl { font-size:.72rem; color:#64748b; text-transform:uppercase; letter-spacing:.8px; }
.tag { display:inline-block; background:rgba(99,179,237,.12); border:1px solid rgba(99,179,237,.25); border-radius:20px; padding:3px 12px; font-size:.78rem; color:#93c5fd; font-weight:500; margin:2px 2px 2px 0; }
.div { height:1px; background:linear-gradient(90deg,transparent,rgba(99,179,237,.15),transparent); margin:24px 0; }
#MainMenu{visibility:hidden} footer{visibility:hidden} header{visibility:hidden}
</style>
""", unsafe_allow_html=True)

for k in ["thread_id","status","triage","report"]:
    if k not in st.session_state: st.session_state[k] = None

def api_ok():
    try: return requests.get(f"{API_URL}/health", timeout=3).status_code == 200
    except: return False

online = api_ok()

# SIDEBAR
with st.sidebar:
    st.markdown("<div style='font-size:1.4rem;font-weight:800;background:linear-gradient(135deg,#63b3ed,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;padding:8px 0 4px'>⚖️ ContractLens</div>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:.78rem;color:#475569;margin-bottom:16px;'>AI Contract Risk Analysis</div>", unsafe_allow_html=True)
    if online:
        st.markdown('<span class="status-online"><span class="dot-g"></span> API Connected</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-offline"><span class="dot-r"></span> API Offline</span>', unsafe_allow_html=True)
    st.markdown("<div class='div'></div>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:.8rem;font-weight:600;color:#63b3ed;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;'>💰 Cost Tracker</div>", unsafe_allow_html=True)
    if online:
        try:
            c = requests.get(f"{API_URL}/costs", headers=AUTH_HEADERS, timeout=3).json()
            a,b = st.columns(2)
            a.metric("Requests", c.get("total_requests",0))
            b.metric("Total Cost", f"${c.get('total_cost_usd',0):.4f}")
            a2,b2 = st.columns(2)
            a2.metric("Avg Cost", f"${c.get('avg_cost_per_request',0):.4f}")
            b2.metric("Avg Time", f"{c.get('avg_elapsed_seconds',0)}s")
            st.metric("Human Reviews", f"{c.get('requests_requiring_human',0)}/{c.get('total_requests',0)}")
        except: st.info("Could not load costs")
    else:
        st.markdown("<div style='color:#475569;font-size:.85rem;padding:10px;background:rgba(15,25,50,.5);border-radius:8px;text-align:center;'>Start API server to see metrics</div>", unsafe_allow_html=True)
    st.markdown("<div class='div'></div>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:.8rem;font-weight:600;color:#63b3ed;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;'>📊 Eval Scores</div>", unsafe_allow_html=True)
    try:
        ep = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"data","evaluation","results.json")
        with open(ep) as f: er = json.load(f)
        import pandas as pd; df = pd.DataFrame(er)
        for m in ["exact_match","faithfulness","answer_relevancy","context_precision"]:
            if m in df.columns:
                v=df[m].mean(); c2="#4ade80" if v>.8 else "#fbbf24" if v>.6 else "#f87171"
                i="🟢" if v>.8 else "🟡" if v>.6 else "uD83D\uDD34"
                st.markdown(f"<div style='display:flex;justify-content:space-between;padding:8px 10px;margin:3px 0;background:rgba(15,25,50,.6);border:1px solid rgba(99,179,237,.1);border-radius:7px;'><span style='font-size:.8rem;color:#94a3b8;'>{m.replace(\"_\",\" \").title()}</span><span style='font-size:.82rem;font-weight:700;color:{c2};'>{v:.3f}</span></div>", unsafe_allow_html=True)
    except:
        st.markdown("<div style='color:#475569;font-size:.82rem;padding:10px;background:rgba(15,25,50,.5);border-radius:8px;text-align:center;'>Run evaluation to see scores</div>", unsafe_allow_html=True)
    st.markdown("<div class='div'></div>", unsafe_allow_html=True)
    if st.button("🔄 Analyze New Contract", use_container_width=True):
        for k in ["thread_id","status","triage","report"]: st.session_state[k]=None
        st.rerun()

# HERO
st.markdown("""
<div style='background:linear-gradient(135deg,rgba(14,28,60,.95),rgba(10,20,45,.95));border:1px solid rgba(99,179,237,.18);border-radius:20px;padding:32px 36px;margin-bottom:24px;'>
  <h1 class="hero-title">⚖️ ContractLens</h1>
  <p class="hero-sub">Autonomous multi-agent AI that reads contracts, identifies risks, and generates structured reports — with human-in-the-loop oversight.</p>
  <div style='margin-top:14px;'>
    <span class="tag">🤖 Groq LLM</span>
    <span class="tag">🔍 Hybrid RAG</span>
    <span class="tag">📐 LangGraph Agents</span>
    <span class="tag">👤 Human-in-the-Loop</span>
    <span class="tag">⚡ Cross-Encoder Reranker</span>
  </div>
</div>
""", unsafe_allow_html=True)

# UPLOAD + DOC INFO
c1, c2 = st.columns([1,1], gap="large")

with c1:
    st.markdown("<div style='font-size:.82rem;font-weight:600;color:#63b3ed;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;'>📤 Upload Contract PDF</div>", unsafe_allow_html=True)
    uf = st.file_uploader("Drag & drop or click to browse", type=["pdf"], label_visibility="collapsed")
    if uf:
        st.markdown(f"<div style='display:flex;align-items:center;gap:12px;padding:12px 16px;background:rgba(99,179,237,.08);border:1px solid rgba(99,179,237,.2);border-radius:10px;margin:10px 0;'><span style='font-size:1.5rem;'>📄</span><div><div style='font-size:.9rem;font-weight:600;color:#e2e8f0;'>{uf.name}</div><div style='font-size:.78rem;color:#64748b;'>{uf.size/1024:.1f} KB</div></div></div>", unsafe_allow_html=True)
        if not online:
            st.error("⚠️ API server is offline. Start the backend first.")
        if online and st.button("⚡ Analyze Contract", type="primary", use_container_width=True):
            pb = st.progress(0)
            try:
                for p,msg in [(20,"📄 Parsing PDF..."),(45,"🔍 Building index..."),(65,"🤖 Triage agent..."),(82,"🔬 Research agent..."),(92,"📋 Generating report...")]:
                    pb.progress(p, text=msg); time.sleep(0.25)
                r = requests.post(f"{API_URL}/analyze", headers=AUTH_HEADERS, files={"file":(uf.name,uf,"application/pdf")}, timeout=300)
                if r.status_code == 200:
                    d=r.json(); st.session_state.thread_id=d["thread_id"]; st.session_state.status=d["status"]
                    st.session_state.triage=d.get("triage"); st.session_state.report=d.get("report")
                    pb.progress(100, text="✅ Done!"); time.sleep(0.5); st.rerun()
                else: pb.empty(); st.error(f"API Error {r.status_code}: {r.text}")
            except requests.exceptions.Timeout: pb.empty(); st.error("u23F1uFE0F Timed out. Try again.")
            except Exception as e: pb.empty(); st.error(f"Error: {e}")
    else:
        st.markdown("<div style='padding:32px;background:rgba(15,25,50,.5);border:2px dashed rgba(99,179,237,.15);border-radius:14px;text-align:center;color:#475569;'><div style='font-size:2.5rem;margin-bottom:10px;'>📋</div><div style='font-size:.9rem;'>Upload a contract PDF to get started</div><div style='font-size:.78rem;margin-top:6px;color:#334155;'>NDA · Service Agreement · Employment · Lease</div></div>", unsafe_allow_html=True)

with c2:
    st.markdown("<div style='font-size:.82rem;font-weight:600;color:#63b3ed;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;'>📄 Document Info</div>", unsafe_allow_html=True)
    if st.session_state.triage:
        t=st.session_state.triage
        dt=t.get("document_type","Unknown"); cx=t.get("complexity","Unknown")
        ra=t.get("risk_areas",[]); rh=t.get("requires_human",False); rn=t.get("reasoning","")
        cc={"low":"#4ade80","medium":"#fbbf24","high":"#f87171"}.get(cx.lower(),"#94a3b8")
        chips="".join(f'<span class="tag">{r}</span>' for r in ra) if ra else '<span style="color:#475569">None</span>'
        tid=(st.session_state.thread_id or "")[:8]
        st.markdown(f"""<div style='background:rgba(15,25,50,.7);border:1px solid rgba(99,179,237,.12);border-radius:14px;padding:20px;'>
          <div style='display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px;'>
            <div><div style='font-size:1.25rem;font-weight:700;color:#e2e8f0;'>{dt}</div>
            <div style='font-size:.78rem;color:#475569;margin-top:2px;'>ID: <code style='color:#63b3ed;'>{tid}...</code></div></div>
            <div style='background:rgba(0,0,0,.3);border-radius:8px;padding:8px 14px;text-align:center;'>
              <div style='font-size:.68rem;color:#475569;text-transform:uppercase;letter-spacing:1px;'>Complexity</div>
              <div style='font-size:1rem;font-weight:700;color:{cc};text-transform:capitalize;'>{cx}</div>
            </div>
          </div>
          <div style='margin-bottom:12px;'><div style='font-size:.73rem;color:#64748b;margin-bottom:6px;text-transform:uppercase;letter-spacing:.8px;'>Risk Areas</div><div>{chips}</div></div>
          <div style='font-size:.82rem;color:#64748b;padding:10px 14px;background:rgba(0,0,0,.2);border-radius:8px;line-height:1.5;'>💭 {rn}</div>
        </div>""", unsafe_allow_html=True)
        if rh: st.warning("👤 This contract requires human review before processing continues.")
        else:  st.success("✅ Auto-processed — no human review required.")
    else:
        st.markdown("<div style='background:rgba(15,25,50,.5);border:1px solid rgba(99,179,237,.08);border-radius:14px;padding:32px;text-align:center;'><div style='font-size:2rem;margin-bottom:10px;'>🔍</div><div style='color:#475569;font-size:.9rem;'>Document details appear here after analysis</div></div>", unsafe_allow_html=True)

# HUMAN GATE
if st.session_state.status == "pending_approval":
    st.markdown("<div class='div'></div>", unsafe_allow_html=True)
    st.markdown("<div style='background:linear-gradient(135deg,rgba(120,53,15,.4),rgba(146,64,14,.25));border:1px solid rgba(245,158,11,.35);border-radius:16px;padding:20px;margin-bottom:16px;'><div style='font-size:1.1rem;font-weight:700;color:#fbbf24;margin-bottom:6px;'>🛑 Human Review Required</div><div style='color:#fde68a;font-size:.88rem;'>This contract was flagged for human review. Please approve or reject below.</div></div>", unsafe_allow_html=True)
    t=st.session_state.triage or {}
    if t.get("reasoning"): st.markdown(f"<div style='padding:10px 14px;background:rgba(15,25,50,.6);border-left:3px solid #f59e0b;border-radius:0 8px 8px 0;color:#94a3b8;font-size:.86rem;margin-bottom:16px;'><b style='color:#fbbf24;'>Reasoning:</b> {t['reasoning']}</div>", unsafe_allow_html=True)
    ca,cr=st.columns(2,gap="large")
    with ca:
        notes=st.text_area("Notes (optional)", placeholder="e.g. Standard contract, proceed", key="notes", height=80)
        if st.button("✅ Approve & Continue", type="primary", use_container_width=True):
            with st.spinner("Resuming..."):
                try:
                    r=requests.post(f"{API_URL}/approve/{st.session_state.thread_id}",headers=AUTH_HEADERS,json={"approved":True,"notes":notes},timeout=300)
                    if r.status_code==200: d=r.json(); st.session_state.status="completed"; st.session_state.report=d.get("report"); st.rerun()
                    else: st.error(f"Error: {r.text}")
                except Exception as e: st.error(f"Error: {e}")
    with cr:
        reason=st.text_area("Reason for rejection", placeholder="e.g. Wrong document", key="reason", height=80)
        if st.button("❌ Reject Contract", use_container_width=True):
            try:
                requests.post(f"{API_URL}/approve/{st.session_state.thread_id}",headers=AUTH_HEADERS,json={"approved":False,"notes":reason},timeout=30)
                st.session_state.status="rejected"; st.rerun()
            except Exception as e: st.error(f"Error: {e}")

# REJECTED
if st.session_state.status == "rejected":
    st.markdown("<div class='div'></div>", unsafe_allow_html=True)
    st.markdown("<div style='background:rgba(127,29,29,.3);border:1px solid rgba(239,68,68,.3);border-radius:14px;padding:24px;text-align:center;'><div style='font-size:2rem;margin-bottom:8px;'>❌</div><div style='font-size:1.1rem;font-weight:600;color:#f87171;'>Contract Rejected</div><div style='color:#94a3b8;font-size:.88rem;margin-top:6px;'>This contract was rejected and will not be processed further.</div></div>", unsafe_allow_html=True)

# REPORT
if st.session_state.status == "completed" and st.session_state.report:
    rpt=st.session_state.report
    st.markdown("<div class='div'></div>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:.82rem;font-weight:600;color:#63b3ed;text-transform:uppercase;letter-spacing:1px;margin-bottom:16px;'>📊 Risk Report</div>", unsafe_allow_html=True)
    ov=rpt.get("overall_risk","unknown").lower()
    if ov=="high":   bc="rgba(127,29,29,.5)"; bbd="rgba(239,68,68,.4)"; bi="🚨"; bclr="#f87171"
    elif ov=="medium": bc="rgba(120,53,15,.5)"; bbd="rgba(245,158,11,.4)"; bi="⚠️"; bclr="#fbbf24"
    else:            bc="rgba(20,83,45,.5)"; bbd="rgba(34,197,94,.4)"; bi="✅"; bclr="#4ade80"
    st.markdown(f"<div style='background:{bc};border:1px solid {bbd};border-radius:14px;padding:20px;text-align:center;margin-bottom:16px;'><div style='font-size:2.2rem;margin-bottom:6px;'>{bi}</div><div style='font-size:1.4rem;font-weight:800;color:{bclr};'>{ov.upper()} RISK</div><div style='color:#94a3b8;font-size:.88rem;margin-top:8px;max-width:600px;margin-left:auto;margin-right:auto;'>{rpt.get('summary','')}</div></div>", unsafe_allow_html=True)
    if rpt.get("recommended_action"):
        st.markdown(f"<div style='padding:12px 16px;background:rgba(99,179,237,.08);border:1px solid rgba(99,179,237,.18);border-radius:10px;margin-bottom:16px;'><span style='color:#63b3ed;font-weight:600;font-size:.84rem;'>→ RECOMMENDED ACTION: </span><span style='color:#e2e8f0;font-size:.88rem;'>{rpt.get('recommended_action')}</span></div>", unsafe_allow_html=True)
    fbr=rpt.get("findings_by_risk",{}); hi=fbr.get("high",[]); me=fbr.get("medium",[]); lo=fbr.get("low",[])
    st.markdown(f"<div class='metric-row'><div class='mcard'><div class='mval' style='color:#f87171;'>{len(hi)}</div><div class='mlbl'>🚨 High</div></div><div class='mcard'><div class='mval' style='color:#fbbf24;'>{len(me)}</div><div class='mlbl'>⚠️ Medium</div></div><div class='mcard'><div class='mval' style='color:#4ade80;'>{len(lo)}</div><div class='mlbl'>✅ Low</div></div><div class='mcard'><div class='mval' style='color:#94a3b8;'>{len(hi)+len(me)+len(lo)}</div><div class='mlbl'>📋 Total</div></div></div>", unsafe_allow_html=True)
    if hi:
        st.markdown("<div class='div'></div><div style='font-size:1rem;font-weight:700;color:#f87171;margin-bottom:10px;'>🚨 High Risk Findings</div>", unsafe_allow_html=True)
        for f in hi:
            src=f.get("source_chunk",""); sp=f'<div style="font-size:.78rem;opacity:.6;font-style:italic;margin-top:6px;">📌 "{src[:200]}{"..." if len(src)>200 else ""}"</div>' if src else ""
            st.markdown(f'<div class="risk-high"><div style="font-size:.72rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;opacity:.8;margin-bottom:6px;">{f.get("clause_type","").upper()}</div><div style="font-size:.95rem;line-height:1.6;margin-bottom:8px;">{f.get("finding","")}</div>{sp}<div style="font-size:.85rem;opacity:.85;padding:8px 12px;background:rgba(0,0,0,.2);border-radius:8px;margin-top:8px;">→ <b>Recommendation:</b> {f.get("recommendation","")}</div></div>', unsafe_allow_html=True)
    if me:
        st.markdown("<div class='div'></div><div style='font-size:1rem;font-weight:700;color:#fbbf24;margin-bottom:10px;'>⚠️ Medium Risk Findings</div>", unsafe_allow_html=True)
        for f in me:
            st.markdown(f'<div class="risk-medium"><div style="font-size:.72rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;opacity:.8;margin-bottom:6px;">{f.get("clause_type","").upper()}</div><div style="font-size:.95rem;line-height:1.6;margin-bottom:8px;">{f.get("finding","")}</div><div style="font-size:.85rem;opacity:.85;padding:8px 12px;background:rgba(0,0,0,.2);border-radius:8px;margin-top:8px;">→ <b>Recommendation:</b> {f.get("recommendation","")}</div></div>', unsafe_allow_html=True)
    if lo:
        st.markdown("<div class='div'></div><div style='font-size:1rem;font-weight:700;color:#4ade80;margin-bottom:10px;'>✅ Low Risk Findings</div>", unsafe_allow_html=True)
        for f in lo:
            st.markdown(f'<div class="risk-low"><div style="font-size:.72rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;opacity:.8;margin-bottom:6px;">{f.get("clause_type","").upper()}</div><div style="font-size:.95rem;line-height:1.6;">{f.get("finding","")}</div></div>', unsafe_allow_html=True)
    st.markdown("<div class='div'></div>", unsafe_allow_html=True)
    tid2=(st.session_state.thread_id or "report")[:8]
    st.download_button("📥 Download Full Report (JSON)", data=json.dumps(rpt,indent=2), file_name=f"contractlens_{tid2}.json", mime="application/json", use_container_width=True)

# HOW IT WORKS
if st.session_state.status is None and not (st.session_state.triage):
    st.markdown("<div class='div'></div>", unsafe_allow_html=True)
    st.markdown("<div style='text-align:center;font-size:.82rem;font-weight:600;color:#334155;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:24px;'>How It Works</div>", unsafe_allow_html=True)
    cols=st.columns(4,gap="medium")
    items=[("📄","Upload","Drop any PDF contract — NDA, service agreement, employment"),("🤖","Analyze","AI agents triage, retrieve, and analyze risk clauses"),("👤","Review","Approve or override AI decisions on high-stakes contracts"),("📊","Report","Get structured HIGH / MEDIUM / LOW findings + recommendations")]
    for col,(icon,title,desc) in zip(cols,items):
        col.markdown(f"<div style='background:rgba(15,25,50,.7);border:1px solid rgba(99,179,237,.1);border-radius:14px;padding:22px;text-align:center;'><div style='font-size:2rem;margin-bottom:10px;'>{icon}</div><div style='font-size:.85rem;font-weight:600;color:#93c5fd;margin-bottom:6px;'>{title}</div><div style='font-size:.78rem;color:#475569;line-height:1.5;'>{desc}</div></div>", unsafe_allow_html=True)
