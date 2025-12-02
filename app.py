import streamlit as st
import os
from openai import OpenAI
import tiktoken
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

# --- CONFIGURATION (The "PM logic") ---
# We define our "Business Rules" here.
PRICE_GPT4 = 0.03       # Estimated cost per 1k tokens
PRICE_MINI = 0.00015    # Much cheaper model
TOKEN_THRESHOLD = 50    # If prompt is longer than this, use the smart model
WARN_COST = 0.0002       # Warn user if a single prompt costs more than this

# Initialize the engines (The "Tech Stack")
analyzer = AnalyzerEngine()
anonymizer = AnonymizerEngine()

# --- HELPER FUNCTIONS ---
def get_token_count(text, model="gpt-4o"):
    """Calculates strict token count to estimate costs."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))

def scan_and_redact(text):
    """The Guardrail: Scans for PII and redact it."""
    # 1. Analyze: Find the PII
    results = analyzer.analyze(text=text, 
                               entities=["PHONE_NUMBER", "EMAIL_ADDRESS", "CREDIT_CARD", "US_SSN"], 
                               language='en')
    
    # 2. Anonymize: Replace it with <REDACTED>
    anonymized_result = anonymizer.anonymize(text=text, analyzer_results=results)
    
    return anonymized_result.text, len(results)

# --- THE APP UI ---
st.set_page_config(page_title="Enterprise AI Gateway", page_icon="🛡️", layout="wide")

st.title("🛡️ Enterprise AI Gateway")
st.markdown("### Internal Proxy for Secure & Cost-Effective AI Adoption")

# Sidebar: The "Admin/Ops" View
with st.sidebar:
    st.header("⚙️ Governance Settings")
    st.info("You are acting as the 'Platform Admin'. Tweak these guardrails.")
    
    compliance_mode = st.radio("Data Compliance Mode", ["Strict (Block & Redact)", "Audit Only (Log It)"])
    st.divider()
    
    # Session state for cost tracking
    if "total_savings" not in st.session_state:
        st.session_state.total_savings = 0.0
    
    st.metric(label="💰 Session Savings (vs. GPT-4o)", value=f"${st.session_state.total_savings:.5f}")
    
    # API Key Input (So you don't need env vars for a quick demo)
    api_key = st.text_input("OpenAI API Key", type="password", placeholder="sk-...")
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key

# Main Chat Interface
prompt = st.chat_input("Enter a prompt (Try: 'Call me at 555-0199 about the Project X budget')...")

if prompt:
    # 1. ANALYSIS LAYER (The "Gateway" Logic)
    tokens = get_token_count(prompt)
    est_cost_high = (tokens / 1000) * PRICE_GPT4
    
    clean_prompt, pii_count = scan_and_redact(prompt)
    
    # 2. ROUTING LOGIC (The "Cost Optimization" Logic)
    # Simple rule: Short prompts go to cheap model. Long prompts go to smart model.
    if tokens < TOKEN_THRESHOLD:
        model_used = "gpt-4o-mini"
        est_cost_actual = (tokens / 1000) * PRICE_MINI
        route_reason = "Low complexity (Token count < 50)"
    else:
        model_used = "gpt-4o"
        est_cost_actual = est_cost_high
        route_reason = "High complexity"

    savings = est_cost_high - est_cost_actual
    st.session_state.total_savings += savings

    # 3. DISPLAY THE DECISION (Transparency for the user)
    with st.status("🚦 Gateway Processing...", expanded=True) as status:
        st.write(f"**Token Audit:** {tokens} tokens detected.")
        
        # PII Check
        if pii_count > 0:
            st.warning(f"⚠️ **PII DETECTED:** {pii_count} sensitive entities found.")
            if compliance_mode == "Strict (Block & Redact)":
                st.success("✅ PII Redacted automatically before sending to OpenAI.")
                final_prompt = clean_prompt
            else:
                st.error("🛑 Logging violation for Audit. Sending raw data (NOT RECOMMENDED).")
                final_prompt = prompt
        else:
            st.info("✅ No PII detected. Safe to send.")
            final_prompt = prompt
            
        st.write(f"**Routing Decision:** Sending to `{model_used}`")
        st.caption(f"Reason: {route_reason}")
        status.update(label="Request Authorized & Sent", state="complete")

    # 4. EXECUTION LAYER
    # Show the chat UI
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        if not api_key:
            st.warning("Please enter an OpenAI API Key in the sidebar to run the actual model.")
            st.write(f"**Simulated Output ({model_used}):**")
            st.code(f"Received Prompt: {final_prompt}")
        else:
            try:
                client = OpenAI(api_key=api_key)
                stream = client.chat.completions.create(
                    model=model_used,
                    messages=[{"role": "user", "content": final_prompt}],
                    stream=True,
                )
                st.write_stream(stream)
            except Exception as e:
                st.error(f"OpenAI API Error: {e}")