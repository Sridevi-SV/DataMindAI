import streamlit as st

def apply_custom_style():
    """
    Applies modern styling rules to the Streamlit app.
    Colors matching: Primary #2563EB, Secondary #14B8A6, Accent #8B5CF6,
    Success #22C55E, Background #F8FAFC, Surface #FFFFFF, Text #0F172A, Border #E2E8F0.
    """
    custom_css = """
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        /* Base page styling */
        html, body, [class*="view-container"] {
            font-family: 'Inter', sans-serif;
            background-color: #F8FAFC !important;
            color: #0F172A !important;
        }
        
        /* Title styling */
        h1, h2, h3, h4, h5, h6 {
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
            color: #0F172A;
            margin-top: 0.5rem;
        }
        
        /* Custom Sidebar style */
        [data-testid="stSidebar"] {
            background-color: #0F172A !important;
            color: #FFFFFF !important;
            border-right: 1px solid #1E293B;
        }
        
        [data-testid="stSidebar"] * {
            color: #E2E8F0 !important;
        }
        
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2 {
            color: #FFFFFF !important;
            font-family: 'Outfit', sans-serif;
            font-weight: 700;
        }
        
        /* Streamlit main block margins */
        .block-container {
            padding-top: 2rem !important;
            padding-bottom: 2rem !important;
            max-width: 95% !important;
        }
        
        /* Modern Cards styling */
        .premium-card {
            background-color: #FFFFFF;
            padding: 1.5rem;
            border-radius: 12px;
            border: 1px solid #E2E8F0;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px 0 rgba(0, 0, 0, 0.03);
            margin-bottom: 1rem;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        
        .premium-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
        }
        
        /* Metric card styling override */
        div[data-testid="stMetricValue"] {
            font-size: 2.2rem !important;
            font-weight: 700 !important;
            color: #2563EB !important;
            font-family: 'Outfit', sans-serif;
        }
        
        div[data-testid="stMetricLabel"] {
            color: #64748B !important;
            font-weight: 500 !important;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-size: 0.8rem !important;
        }
        
        /* Button overrides */
        .stButton>button {
            background-color: #2563EB !important;
            color: #FFFFFF !important;
            font-weight: 500 !important;
            border-radius: 8px !important;
            border: none !important;
            padding: 0.5rem 1rem !important;
            transition: all 0.2s ease !important;
            box-shadow: 0 1px 2px 0 rgba(37, 99, 235, 0.2) !important;
        }
        
        .stButton>button:hover {
            background-color: #1D4ED8 !important;
            transform: translateY(-1px) !important;
            box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.3) !important;
        }
        
        .stButton>button:active {
            transform: translateY(0px) !important;
        }
        
        /* Secondary / Custom alert checks styling */
        .check-item {
            display: flex;
            align-items: center;
            padding: 0.6rem 1rem;
            margin-bottom: 0.5rem;
            background-color: #F1F5F9;
            border-left: 4px solid #94A3B8;
            border-radius: 4px;
            font-weight: 500;
        }
        
        .check-item.completed {
            background-color: #ECFDF5;
            border-left: 4px solid #22C55E;
            color: #065F46;
        }
        
        .check-item.failed {
            background-color: #FEF2F2;
            border-left: 4px solid #EF4444;
            color: #991B1B;
        }
        
        /* AI Chat Panel */
        .ai-chat-bubble {
            background-color: #FFFFFF;
            padding: 1.25rem;
            border-radius: 12px;
            border: 1px solid #E2E8F0;
            margin-bottom: 1rem;
            position: relative;
        }
        
        .ai-meta-badge {
            display: inline-block;
            padding: 0.2rem 0.5rem;
            font-size: 0.75rem;
            font-weight: 600;
            border-radius: 4px;
            margin-right: 0.5rem;
            text-transform: uppercase;
        }
        
        .ai-badge-model {
            background-color: #EEF2FF;
            color: #4F46E5;
        }
        
        .ai-badge-tool {
            background-color: #F0FDF4;
            color: #16A34A;
        }
        
        .ai-badge-conf {
            background-color: #FFF7ED;
            color: #EA580C;
        }
        
        /* Custom tables */
        .premium-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
            margin-bottom: 1rem;
        }
        
        .premium-table th {
            background-color: #F1F5F9;
            color: #475569;
            text-align: left;
            padding: 0.75rem 1rem;
            font-weight: 600;
            border-bottom: 2px solid #E2E8F0;
        }
        
        .premium-table td {
            padding: 0.75rem 1rem;
            border-bottom: 1px solid #F1F5F9;
            color: #0F172A;
        }
        
        .premium-table tr:hover {
            background-color: #F8FAFC;
        }
    </style>
    """
    st.markdown(custom_css, unsafe_allow_html=True)

def draw_header(title, subtitle=None):
    st.markdown(f"""
        <div style="margin-bottom: 2rem;">
            <h1 style="font-size: 2.2rem; font-weight: 700; margin-bottom: 0.2rem; color: #0F172A;">{title}</h1>
            {f'<p style="color: #64748B; font-size: 1.1rem; margin-top: 0;">{subtitle}</p>' if subtitle else ''}
            <hr style="border: none; border-top: 1px solid #E2E8F0; margin-top: 1rem; margin-bottom: 1rem;" />
        </div>
    """, unsafe_allow_html=True)

def render_premium_card(title, value, subtitle=None, icon=None):
    st.markdown(f"""
        <div class="premium-card">
            <div style="font-size: 0.8rem; font-weight: 600; text-transform: uppercase; color: #64748B; letter-spacing: 0.05em; display: flex; align-items: center;">
                {f'<span style="margin-right: 0.5rem;">{icon}</span>' if icon else ''} {title}
            </div>
            <div style="font-size: 2.2rem; font-weight: 700; color: #2563EB; font-family: Outfit; margin-top: 0.5rem; margin-bottom: 0.2rem;">
                {value}
            </div>
            {f'<div style="font-size: 0.8rem; color: #94A3B8;">{subtitle}</div>' if subtitle else ''}
        </div>
    """, unsafe_allow_html=True)

def render_progress_item(label, status):
    """
    Renders checklist item: 'pending', 'completed', or 'failed'
    """
    if status == 'completed':
        st.markdown(f'<div class="check-item completed">✓ {label}</div>', unsafe_allow_html=True)
    elif status == 'failed':
        st.markdown(f'<div class="check-item failed">✗ {label} (Error)</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="check-item">○ {label}</div>', unsafe_allow_html=True)
