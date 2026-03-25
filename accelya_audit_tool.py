import streamlit as st
import pandas as pd
import io
import re

# --- 1. עיצוב ממשק פרימיום (Glassmorphism & Neon) ---
def apply_custom_style():
    st.markdown("""
        <style>
        /* ייבוא פונט מודרני */
        @import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@400;600;700&display=swap');
        
        .stApp {
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
            color: #f8fafc;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }

        /* כותרת ניאון */
        .main-title {
            font-size: 4rem;
            font-weight: 700;
            text-align: center;
            background: linear-gradient(to right, #c084fc, #6366f1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
            filter: drop-shadow(0 0 10px rgba(192, 132, 252, 0.3));
        }

        .version-tag {
            text-align: center;
            color: #94a3b8;
            font-size: 0.9rem;
            margin-bottom: 3rem;
            letter-spacing: 2px;
        }

        /* כרטיס העלאת קבצים מעוצב */
        .upload-container {
            background: rgba(255, 255, 255, 0.03);
            backdrop-filter: blur(10px);
            border-radius: 24px;
            padding: 40px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 20px 50px rgba(0,0,0,0.3);
            margin-bottom: 2rem;
        }

        /* עיצוב כפתור ההורדה */
        .stDownloadButton button {
            width: 100%;
            background: linear-gradient(90deg, #7c3aed 0%, #4f46e5 100%);
            border: none;
            color: white;
            padding: 1rem;
            border-radius: 12px;
            font-weight: 600;
            font-size: 1.1rem;
            transition: all 0.3s ease;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .stDownloadButton button:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 20px rgba(79, 70, 229, 0.4);
            filter: brightness(1.1);
        }

        /* התראות וסטטוס */
        .stStatus {
            background: rgba(15, 23, 42, 0.6);
            border-radius: 15px;
            border: 1px solid #4f46e5;
        }
        
        /* הסתרת תפריטים מיותרים של Streamlit */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}

        </style>
    """, unsafe_allow_html=True)

# --- 2. לוגיקת העיבוד (ללא שינוי - הגדרות 0-11) ---
def process_data(df):
    df.columns = [str(c).strip().upper() for c in df.columns]
    df['S'] = ""
    df['S_COLOR'] = ""
    df['CHECK_COMMENTS'] = ""
    luggage_airlines = ['J2', 'GQ', 'AZ', 'LA', 'UX', 'EY']

    for index, row in df.iterrows():
        acc_raw = row.get('ACCELYA AMOUNT', 0)
        accelya_abs = abs(pd.to_numeric(acc_raw, errors='coerce') or 0)
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
        fin = get_val('FINANCEORDERSTATUS')
        airline = get_val('OUTAIRLINES')
        extra_cat = get_val('EXTRA_CATEGORIES')
        search_pnr = str(row.get('SEARCHPNR', '')).strip()

        # חוק הסתירה
        statuses = [cust, update]
        if 'UNDER_AIRLINE_REFUND' in statuses and any(s in statuses for s in ['UNDER_TICKET_RULE', 'UNDER_PARTIAL_AIRLINE_REFUND', 'UNDER_CONSUMER_LAW']):
            final_status = 'UNDER_AIRLINE_REFUND'
            df.at[index, 'CHECK_COMMENTS'] = "Conflict: Using Strict Refund"
        else:
            final_status = cust if cust != "" else update

        # החרגות כחולות
        if ecom == 'SUCCESS' and talma in ['REFUND', 'NOT_FOR_REFUND']:
            df.at[index, 'S_COLOR'] = 'blue'; continue
        if oper == 'ACTIVE' and all(s == "" for s in [cust, fin, talma]) and update in ["", "ORDER_TRIP_CHANGED"]:
            df.at[index, 'S_COLOR'] = 'blue'; continue
        if ecom != 'SUCCESS' and all(s == "" for s in [oper, cust, fin, talma, update]):
            df.at[index, 'S_COLOR'] = 'blue'; continue

        # Safe Cancellation
        if (ecom == 'SUCCESS' and oper == 'CANCELLED' and 
            cust == 'UNDER_SAFE_CANCELLATION' and update == 'UNDER_TICKET_RULE' and 
            single_penalty == 0):
            df.at[index, 'S'] = round(grand_total - accelya_abs, 2)
            df.at[index, 'S_COLOR'] = 'green'
            df.at[index, 'CHECK_COMMENTS'] = "Safe Cancellation - OK"
            continue

        if ecom == 'SUCCESS':
            # החרגת LY טרולי
            is_ly_carryon = (airline == 'LY' and extra_cat == 'carryOnLuggage')
            effective_accelya = accelya_abs + total_extras if is_ly_carryon else accelya_abs
            if is_ly_carryon: df.at[index, 'CHECK_COMMENTS'] = (df.at[index, 'CHECK_COMMENTS'] + " | LY Carry-On Adjusted").strip(" | ")

            # החרגת מזוודות חו"ל
            apply_luggage = airline in luggage_airlines and extra_cat.lower() == 'luggage'
            base_amount = grand_total - total_extras if apply_luggage else grand_total

            # חישוב שקלי
            if final_status in ['UNDER_AIRLINE_REFUND', 'UNDER_TICKET_RULE']:
                if final_status == 'UNDER_AIRLINE_REFUND':
                    res = base_amount - effective_accelya
                else: # TICKET_RULE
                    pnr_is_only_digits = bool(re.fullmatch(r'\d+', search_pnr))
                    if pnr_is_only_digits and single_penalty == 0:
                        res = base_amount - effective_accelya
                        df.at[index, 'CHECK_COMMENTS'] = (df.at[index, 'CHECK_COMMENTS'] + " | Numeric PNR Zero Penalty").strip(" | ")
                    elif single_penalty > 0:
                        res = (base_amount - (single_penalty * pax_count)) - effective_accelya
                    else:
                        res = 0; df.at[index, 'S_COLOR'] = 'purple'; df.at[index, 'CHECK_COMMENTS'] = "Missing Penalty"
                
                if df.at[index, 'S_COLOR'] != 'purple':
                    df.at[index, 'S'] = round(res, 2)
                    df.at[index, 'S_COLOR'] = 'green' if -300 <= res <= 50 else 'red'

            # חישוב אחוזים
            elif final_status in ['UNDER_CONSUMER_LAW', 'UNDER_PARTIAL_AIRLINE_REFUND']:
                ratio = effective_accelya / grand_total if grand_total != 0 else 0
                df.at[index, 'S'] = f"{ratio:.2%}"
                if final_status == 'UNDER_CONSUMER_LAW':
                    df.at[index, 'S_COLOR'] = 'green' if ratio >= 0.90 else 'red'
                else:
                    df.at[index, 'S_COLOR'] = 'green' if ratio >= 0.25 else 'red'
                if ratio > 2.0: df.at[index, 'S_COLOR'] = 'purple'

    return df

# --- 3. ממשק האפליקציה ---
st.set_page_config(page_title="Purple Rain v4.4", layout="wide")
apply_custom_style()

# אזור הכותרת
st.markdown("<div class='main-title'>Purple Rain Auditor</div>", unsafe_allow_html=True)
st.markdown("<div class='version-tag'>PREMIUM DATA VERIFICATION ENGINE v4.4</div>", unsafe_allow_html=True)

# אזור העלאת קבצים מרוכז
col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    st.markdown("<div class='upload-container'>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("", type=['csv', 'xlsx'])
    
    if uploaded_file:
        with st.status("🚀 Processing Neural Audit...", expanded=True) as status:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file, engine='openpyxl')
                
                processed_df = process_data(df)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    processed_df.to_excel(writer, index=False, sheet_name='Audit_Report')
                    workbook, worksheet = writer.book, writer.sheets['Audit_Report']
                    formats = {
                        'green': workbook.add_format({'bg_color': '#D1FAE5', 'font_color': '#065F46'}),
                        'red': workbook.add_format({'bg_color': '#FEE2E2', 'font_color': '#991B1B'}),
                        'blue': workbook.add_format({'bg_color': '#DBEAFE', 'font_color': '#1E40AF'}),
                        'purple': workbook.add_format({'bg_color': '#F3E8FF', 'font_color': '#6B21A8'})
                    }
                    for row_num in range(1, len(processed_df) + 1):
                        color = processed_df.iloc[row_num-1]['S_COLOR']
                        if color in formats:
                            worksheet.set_row(row_num, None, formats[color])
                
                status.update(label="Audit Complete!", state="complete", expanded=False)
                
                st.markdown("<br>", unsafe_allow_html=True)
                st.download_button(
                    label="📥 Download Audit Report",
                    data=output.getvalue(),
                    file_name="Purple_Rain_Final_v4.4.xlsx",
                    mime="application/vnd.ms-excel"
                )
            except Exception as e:
                st.error(f"Error: {e}")
    st.markdown("</div>", unsafe_allow_html=True)

# תחתית העמוד
st.markdown("<p style='text-align: center; color: #475569; margin-top: 50px;'>Proprietary Audit Logic | Optimized for Snowflake Datasets</p>", unsafe_allow_html=True)
