import os
import streamlit as st
import requests
import json
from dotenv import load_dotenv

load_dotenv()

API_URL = os.environ.get("CONTRACTLENS_API_URL", "http://localhost:8000")
API_KEY = os.environ.get("CONTRACTLENS_API_KEY", "")
AUTH_HEADERS = {"X-API-Key": API_KEY}

# ── Page Config ────────────────────────────────────────────
st.set_page_config(
    page_title="ContractLens",
    page_icon="📋",
    layout="wide"
)

# ── Styling ────────────────────────────────────────────────
st.markdown("""
<style>
    .risk-high {
        background-color: #7f1d1d;
        border-left: 4px solid #ef4444;
        padding: 12px 16px;
        margin: 8px 0;
        border-radius: 6px;
        color: #fef2f2;
    }
    .risk-medium {
        background-color: #78350f;
        border-left: 4px solid #f59e0b;
        padding: 12px 16px;
        margin: 8px 0;
        border-radius: 6px;
        color: #fffbeb;
    }
    .risk-low {
        background-color: #14532d;
        border-left: 4px solid #22c55e;
        padding: 12px 16px;
        margin: 8px 0;
        border-radius: 6px;
        color: #f0fdf4;
    }
    .risk-high strong, .risk-medium strong, .risk-low strong {
        font-size: 1.05rem;
        letter-spacing: 0.5px;
    }
    .risk-high em, .risk-medium em, .risk-low em {
        opacity: 0.85;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)
# ── Session State ──────────────────────────────────────────
for key in ["thread_id", "status", "triage", "report"]:
    if key not in st.session_state:
        st.session_state[key] = None

# ── Header ─────────────────────────────────────────────────
st.title("📋 ContractLens")
st.caption("Autonomous Contract Risk Analysis")
st.divider()

# ── Sidebar ────────────────────────────────────────────────
with st.sidebar:
    st.header("💰 Cost Tracker")
    try:
        costs = requests.get(f"{API_URL}/costs", headers=AUTH_HEADERS, timeout=3).json()
        st.metric("Total Requests", costs.get("total_requests", 0))
        st.metric("Total Cost", f"${costs.get('total_cost_usd', 0):.4f}")
        st.metric("Avg per Request", f"${costs.get('avg_cost_per_request', 0):.4f}")
        st.metric("Avg Latency", f"{costs.get('avg_elapsed_seconds', 0)}s")
        st.metric(
            "Human Reviews",
            f"{costs.get('requests_requiring_human', 0)}/{costs.get('total_requests', 0)}"
        )
    except Exception:
        st.warning("API not connected")

    st.divider()

    st.header("📊 Evaluation Scores")
    try:
        with open("./data/evaluation/results.json", "r") as f:
            eval_results = json.load(f)
        import pandas as pd
        df = pd.DataFrame(eval_results)
        for m in ["exact_match", "faithfulness", "answer_relevancy", "context_precision"]:
            val = df[m].mean()
            color = "🟢" if val > 0.8 else "🟡" if val > 0.6 else "🔴"
            st.write(f"{color} **{m}**: {val:.3f}")
    except Exception:
        st.info("Run evaluation to see scores")

    st.divider()

    # Reset button
    if st.button("🔄 Analyze New Contract"):
        for key in ["thread_id", "status", "triage", "report"]:
            st.session_state[key] = None
        st.rerun()

# ── Upload Section ─────────────────────────────────────────
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📤 Upload Contract")
    uploaded_file = st.file_uploader(
        "Choose a PDF contract",
        type=["pdf"],
        help="Upload NDA, Service Agreement, Employment Contract etc."
    )

    if uploaded_file and st.button("🔍 Analyze Contract", type="primary"):
        progress = st.progress(0, text="Uploading document...")

        with st.spinner("Analyzing — this takes 30-90 seconds..."):
            try:
                progress.progress(20, text="Parsing PDF...")
                response = requests.post(
                    f"{API_URL}/analyze",
                    headers=AUTH_HEADERS,
                    files={
                        "file": (
                            uploaded_file.name,
                            uploaded_file,
                            "application/pdf"
                        )
                    },
                    timeout=300
                )
                progress.progress(90, text="Almost done...")

                if response.status_code == 200:
                    data = response.json()
                    st.session_state.thread_id = data["thread_id"]
                    st.session_state.status = data["status"]
                    st.session_state.triage = data.get("triage")
                    st.session_state.report = data.get("report")
                    progress.progress(100, text="Done!")
                    st.success(f"✅ {data['message']}")
                    st.rerun()
                else:
                    progress.empty()
                    st.error(f"API Error: {response.text}")

            except requests.exceptions.Timeout:
                progress.empty()
                st.error("⏱️ Timed out — contract may be too large. Try again.")
            except Exception as e:
                progress.empty()
                st.error(f"Connection error: {e}")

with col2:
    st.subheader("📄 Document Info")
    if st.session_state.triage:
        triage = st.session_state.triage
        st.markdown(f"**Type:** `{triage.get('document_type', 'Unknown')}`")
        st.markdown(f"**Complexity:** `{triage.get('complexity', 'Unknown')}`")

        risk_areas = triage.get("risk_areas", [])
        if risk_areas:
            tags = " ".join([f"`{r}`" for r in risk_areas])
            st.markdown(f"**Risk Areas:** {tags}")

        if triage.get("requires_human"):
            st.warning("👤 Human review required")
        else:
            st.success("✅ Auto-processed")

        st.caption(f"Thread: {st.session_state.thread_id}")
    else:
        st.info("Upload a contract to see document info here")

st.divider()

# ── Human Approval Gate ────────────────────────────────────
if st.session_state.status == "pending_approval":
    st.subheader("🛑 Human Review Required")
    st.warning("This contract needs your review before analysis continues.")

    triage = st.session_state.triage or {}
    st.markdown(f"**Reasoning:** {triage.get('reasoning', '')}")

    st.divider()

    col_a, col_r = st.columns(2)

    with col_a:
        st.markdown("### ✅ Approve")
        notes = st.text_area(
            "Notes (optional)",
            placeholder="e.g. Standard contract, proceed with analysis",
            key="approval_notes"
        )
        if st.button("✅ Approve & Continue Analysis", type="primary"):
            with st.spinner("Resuming analysis — please wait..."):
                try:
                    response = requests.post(
                        f"{API_URL}/approve/{st.session_state.thread_id}",
                        headers=AUTH_HEADERS,
                        json={"approved": True, "notes": notes},
                        timeout=300
                    )
                    if response.status_code == 200:
                        data = response.json()
                        st.session_state.status = "completed"
                        st.session_state.report = data.get("report")
                        st.success("✅ Approved — analysis complete")
                        st.rerun()
                    else:
                        st.error(f"Error: {response.text}")
                except Exception as e:
                    st.error(f"Error: {e}")

    with col_r:
        st.markdown("### ❌ Reject")
        reason = st.text_area(
            "Reason for rejection",
            placeholder="e.g. Wrong document uploaded",
            key="rejection_reason"
        )
        if st.button("❌ Reject Contract", type="secondary"):
            try:
                requests.post(
                    f"{API_URL}/approve/{st.session_state.thread_id}",
                    headers=AUTH_HEADERS,
                    json={"approved": False, "notes": reason},
                    timeout=30
                )
                st.session_state.status = "rejected"
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    st.divider()

# ── Risk Report ────────────────────────────────────────────
if st.session_state.status == "completed" and st.session_state.report:
    report = st.session_state.report

    st.subheader("📊 Risk Report")

    # Overall risk banner
    overall = report.get("overall_risk", "unknown").upper()
    if overall == "HIGH":
        st.error(f"🚨 Overall Risk Level: {overall}")
    elif overall == "MEDIUM":
        st.warning(f"⚠️ Overall Risk Level: {overall}")
    else:
        st.success(f"✅ Overall Risk Level: {overall}")

    st.markdown(f"**Summary:** {report.get('summary', '')}")
    st.markdown(f"**Recommended Action:** {report.get('recommended_action', '')}")

    st.divider()

    findings_by_risk = report.get("findings_by_risk", {})
    high   = findings_by_risk.get("high", [])
    medium = findings_by_risk.get("medium", [])
    low    = findings_by_risk.get("low", [])

    # Counts
    c1, c2, c3 = st.columns(3)
    c1.metric("🚨 High Risk",   len(high))
    c2.metric("⚠️ Medium Risk", len(medium))
    c3.metric("✅ Low Risk",    len(low))

    st.divider()

    # High findings
    if high:
        st.markdown("### 🚨 High Risk Findings")
        for f in high:
            st.markdown(f"""
<div class="risk-high">
<strong>{f['clause_type'].upper()}</strong><br><br>
{f['finding']}<br><br>
<em>📌 Clause: "{f.get('source_chunk', '')[:250]}..."</em><br><br>
<strong>→ Recommendation:</strong> {f['recommendation']}
</div>
""", unsafe_allow_html=True)

    # Medium findings
    if medium:
        st.markdown("### ⚠️ Medium Risk Findings")
        for f in medium:
            st.markdown(f"""
<div class="risk-medium">
<strong>{f['clause_type'].upper()}</strong><br><br>
{f['finding']}<br><br>
<strong>→ Recommendation:</strong> {f['recommendation']}
</div>
""", unsafe_allow_html=True)

    # Low findings
    if low:
        st.markdown("### ✅ Low Risk Findings")
        for f in low:
            st.markdown(f"""
<div class="risk-low">
<strong>{f['clause_type'].upper()}</strong><br><br>
{f['finding']}
</div>
""", unsafe_allow_html=True)

    st.divider()

    # Download
    st.download_button(
        label="📥 Download Full Report (JSON)",
        data=json.dumps(report, indent=2),
        file_name=f"report_{st.session_state.thread_id[:8]}.json",
        mime="application/json"
    )

elif st.session_state.status == "rejected":
    st.error("❌ This contract was rejected and will not be processed.")

elif st.session_state.status is None:
    st.info("👆 Upload a contract above to get started")