import streamlit as st
import pandas as pd
import io
import re

# --- 1. עיצוב ממשק נקי (Clean White & Dark Mode) ---
def apply_custom_style():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
        
        .stApp {
            background-color: #0f172a;
            color: #f8fafc;
            font-family: 'Inter', sans-serif;
        }

        /* כותרות בלבן נקי */
        h1, h2, h3 {
            color: #ffffff !important;
            font-weight: 700 !important;
            text-align: center;
        }

        .main-title {
            font-size: 3.5rem;
            margin-top: 2rem;
            margin-bottom: 0.5rem;
            letter-spacing: -1px;
        }

        .subtitle {
            text-align: center;
            color: #94a3b8;
            font-size: 1.1rem;
            margin-bottom: 3rem;
        }

        /* תיבת העלאה */
        .upload-card {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 40px;
            margin-bottom: 2rem;
        }

        /* כפתור הורדה בולט */
        .stDownloadButton button {
            width: 100%;
            background-color: #ffffff;
            color: #0f172a;
            border: none;
            padding: 1rem;
            border-radius: 8px;
            font-weight: 700;
            font-size: 1rem;
            transition: 0.2s;
            cursor: pointer;
        }

        .stDownloadButton button:hover {
            background-color: #e2e8f0;
            transform: scale(1.01);
        }

        /* הסתרת אלמנטים של Streamlit */
        header {visibility: hidden;}
        footer {visibility: hidden;}
        </style>
    """, unsafe_allow_html=True)

# --- 2. לוגיקת העיבוד המרכזית (v4.8 - All Rules Included) ---
def process_data(df):
    # הגדרה 0: נרמול עמודות
    df.columns = [str(c).strip().upper() for c in df.columns]
    df['S'] = ""
    df['S_COLOR'] = ""
    df['CHECK_COMMENTS'] = ""

    luggage_airlines = ['J2', 'GQ', 'AZ', 'LA', 'UX', 'EY']

    for index, row in df.iterrows():
        # שלב 1: אקסליה תמיד הופכת לפלוס (ערך מוחלט)
        acc_raw = row.get('ACCELYA AMOUNT', 0)
        accelya_base = abs(pd.to_numeric(acc_raw, errors='coerce') or 0)
        
        grand_total = pd.to_numeric(row.get('GRANDTOTAL', 0), errors='coerce') or 0
        single_penalty = pd.to_numeric(row.get('SINGLEPENALTYFEE', 0), errors='coerce') or 0
        pax_count = pd.to_numeric(row.get('ACTIVEPASSENGERSCOUNT', 0), errors='coerce') or 1
        total_extras = pd.to_numeric(row.get('TOTALEXTRAS', 0), errors='coerce') or 0
        
        def get_val(col):
            val = str(row.get(col, '')).strip().upper()
            return "" if val in ['NAN', 'NONE', 'NULL'] else val

        ecom = get_val('ECOMMERCEORDERSTATUS')
        cust = get_val('CUSTOMERORDERSTATUS')
        oper = get_val('OPERATIONALORDERSTATUS')
        update = get_val('ORDERUPDATESTATUS')
        talma = get_val('TALMAORDERSTATUS')
        airline = get_val('OUTAIRLINES')
        extra_cat_raw = str(row.get('EXTRA_CATEGORIES', '')).lower()
        search_pnr = str(row.get('SEARCHPNR', '')).strip()

        # חוק הסתירה (הגדרה 9)
        statuses = [cust, update]
        if 'UNDER_AIRLINE_REFUND' in statuses and any(s in statuses for s in ['UNDER_TICKET_RULE', 'UNDER_PARTIAL_AIRLINE_REFUND', 'UNDER_CONSUMER_LAW']):
            final_status = 'UNDER_AIRLINE_REFUND'
        else:
            final_status = cust if cust != "" else update

        # החרגות כחולות (הגדרה 2)
        if ecom == 'SUCCESS' and talma in ['REFUND', 'NOT_FOR_REFUND']:
            df.at[index, 'S_COLOR'] = 'blue'; continue
        if ecom != 'SUCCESS':
            df.at[index, 'S_COLOR'] = 'blue'; continue

        # Safe Cancellation (הגדרה 3)
        if (ecom == 'SUCCESS' and oper == 'CANCELLED' and cust == 'UNDER_SAFE_CANCELLATION' and update == 'UNDER_TICKET_RULE' and single_penalty == 0):
            df.at[index, 'S'] = round(grand_total - accelya_base, 2)
            df.at[index, 'S_COLOR'] = 'green'
            df.at[index, 'CHECK_COMMENTS'] = "Safe Cancellation"
            continue

        # --- שלב 2: לוגיקת הוספה לאקסליה (Addition Only) ---
        adjusted_accelya = accelya_base
        
        # טרולי אל-על (הגדרה 10)
        if airline == 'LY' and 'carryonluggage' in extra_cat_raw:
            adjusted_accelya += total_extras
            df.at[index, 'CHECK_COMMENTS'] += " | LY CarryOn Added"

        # מזוודות (הגדרה 4 + עדכון רשימה)
        if airline in luggage_airlines and 'luggage' in extra_cat_raw:
            adjusted_accelya += total_extras
            df.at[index, 'CHECK_COMMENTS'] += " | Luggage Added"

        # --- שלב 3: חישוב הפרשים ---
        if final_status in ['UNDER_AIRLINE_REFUND', 'UNDER_TICKET_RULE']:
            if final_status == 'UNDER_AIRLINE_REFUND':
                res = grand_total - adjusted_accelya
            else: # TICKET_RULE
                # החרגת PNR מספרי (הגדרה 11)
                pnr_is_only_digits = bool(re.fullmatch(r'\d+', search_pnr))
                if pnr_is_only_digits and single_penalty == 0:
                    res = grand_total - adjusted_accelya
                    df.at[index, 'S_COLOR'] = 'green'
                    df.at[index, 'CHECK_COMMENTS'] += " | Numeric PNR OK"
                elif single_penalty > 0:
                    expected_after_penalty = grand_total - (single_penalty * pax_count)
                    res = expected_after_penalty - adjusted_accelya
                else:
                    res = 0; df.at[index, 'S_COLOR'] = 'purple'; df.at[index, 'CHECK_COMMENTS'] += " | Missing Penalty"

            if df.at[index, 'S_COLOR'] != 'purple':
                df.at[index, 'S'] = round(res, 2)
                df.at[index, 'S_COLOR'] = 'green' if -300 <= res <= 50 else 'red'

        # חישוב אחוזים (הגדרות 7, 8)
        elif final_status in ['UNDER_CONSUMER_LAW', 'UNDER_PARTIAL_AIRLINE_REFUND']:
            ratio = adjusted_accelya / grand_total if grand_total != 0 else 0
            df.at[index, 'S'] = f"{ratio:.2%}"
            if final_status == 'UNDER_CONSUMER_LAW':
                df.at[index, 'S_COLOR'] = 'green' if ratio >= 0.90 else 'red'
            else: # PARTIAL
                df.at[index, 'S_COLOR'] = 'green' if ratio >= 0.25 else 'red'

    return df

# --- 3. ממשק האפליקציה ---
st.set_page_config(page_title="Audit Tool v4.8", layout="wide")
apply_custom_style()

st.markdown("<h1 class='main-title'>Purple Rain Auditor</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>Advanced Refund Verification Engine | Version 4.8</p>", unsafe_allow_html=True)

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.markdown("<div class='upload-card'>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Upload Snowflake CSV/Excel", type=['csv', 'xlsx'])
    
    if uploaded_file:
        with st.spinner("Analyzing..."):
            try:
                df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
                processed_df = process_data(df)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    processed_df.to_excel(writer, index=False, sheet_name='Audit')
                    workbook, worksheet = writer.book, writer.sheets['Audit']
                    formats = {
                        'green': workbook.add_format({'bg_color': '#D1FAE5', 'font_color': '#064E3B'}),
                        'red': workbook.add_format({'bg_color': '#FEE2E2', 'font_color': '#7F1D1D'}),
                        'blue': workbook.add_format({'bg_color': '#DBEAFE', 'font_color': '#1E3A8A'}),
                        'purple': workbook.add_format({'bg_color': '#F3E8FF', 'font_color': '#581C87'})
                    }
                    for row_num in range(1, len(processed_df) + 1):
                        color = processed_df.iloc[row_num-1]['S_COLOR']
                        if color in formats: worksheet.set_row(row_num, None, formats[color])
                
                st.markdown("<br>", unsafe_allow_html=True)
                st.download_button("📥 DOWNLOAD REPORT", output.getvalue(), f"Audit_Report_{uploaded_file.name}.xlsx")
                st.success("Audit completed successfully.")
            except Exception as e:
                st.error(f"Error: {e}")
    st.markdown("</div>", unsafe_allow_html=True)
