import streamlit as st
import pandas as pd
import io
import re

# --- 1. עיצוב ממשק ---
def apply_custom_style():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
        .stApp { background: linear-gradient(135deg, #6d28d9 0%, #4c1d95 100%); color: #ffffff; font-family: 'Inter', sans-serif; }
        h1, h2, h3 { color: #ffffff !important; font-weight: 700 !important; text-align: center; }
        .main-title { font-size: 3.5rem; margin-top: 2rem; }
        .subtitle { text-align: center; color: #e9d5ff; margin-bottom: 3rem; }
        section[data-testid="stFileUploader"] { background-color: #000000 !important; border: 2px solid rgba(255, 255, 255, 0.1); border-radius: 16px; padding: 25px; }
        .stDownloadButton button { width: 100%; background-color: #ffffff; color: #000000; border: none; padding: 1rem; border-radius: 8px; font-weight: 700; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
        header {visibility: hidden;} footer {visibility: hidden;}
        </style>
    """, unsafe_allow_html=True)

# --- 2. לוגיקת העיבוד (v5.8 - התיקון הסופי לסוגי נתונים) ---
def process_data(df):
    # נרמול שמות עמודות
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    # אתחול עמודות עם ערכי ברירת מחדל כדי למנוע ערבוב סוגים
    df['S'] = ""
    df['S_COLOR'] = ""
    df['CHECK_COMMENTS'] = ""

    luggage_airlines = ['J2', 'GQ', 'AZ', 'LA', 'UX', 'EY']

    def to_num(val):
        if pd.isna(val) or val == "": return 0.0
        try:
            return float(pd.to_numeric(val, errors='coerce'))
        except:
            return 0.0

    def get_val(row, col):
        v = row.get(col)
        if pd.isna(v) or v is None: return ""
        s = str(v).strip()
        if s.endswith('.0'): s = s[:-2]
        return s.upper()

    for index, row in df.iterrows():
        accelya_base = abs(to_num(row.get('ACCELYA AMOUNT')))
        grand_total = to_num(row.get('GRANDTOTAL'))
        single_penalty = to_num(row.get('SINGLEPENALTYFEE'))
        pax_count = max(to_num(row.get('ACTIVEPASSENGERSCOUNT')), 1)
        total_extras = to_num(row.get('TOTALEXTRAS'))
        
        ecom = get_val(row, 'ECOMMERCEORDERSTATUS')
        cust = get_val(row, 'CUSTOMERORDERSTATUS')
        oper = get_val(row, 'OPERATIONALORDERSTATUS')
        update = get_val(row, 'ORDERUPDATESTATUS')
        talma = get_val(row, 'TALMAORDERSTATUS')
        fin = get_val(row, 'FINANCEORDERSTATUS')
        airline = get_val(row, 'OUTAIRLINES')
        extra_cat_raw = str(row.get('EXTRA_CATEGORIES', '')).lower()
        search_pnr = get_val(row, 'SEARCHPNR')

        # קביעת סטטוס
        if 'UNDER_AIRLINE_REFUND' in [cust, update]:
            final_status = 'UNDER_AIRLINE_REFUND'
        elif 'MEDICAL_CANCELLATION' in [cust, update]:
            final_status = 'UNDER_TICKET_RULE'
            df.at[index, 'CHECK_COMMENTS'] = "Medical Cancellation"
        else:
            final_status = cust if cust != "" else update

        # החרגות
        if ecom == 'SUCCESS' and talma in ['REFUND', 'NOT_FOR_REFUND']:
            df.at[index, 'S_COLOR'] = 'blue'; continue
        if oper == 'ACTIVE' and not any([cust, fin, talma]) and update in ["", "ORDER_TRIP_CHANGED"]:
            df.at[index, 'S_COLOR'] = 'blue'; continue
        if ecom != 'SUCCESS' and not any([oper, cust, fin, talma, update]):
            df.at[index, 'S_COLOR'] = 'blue'; continue

        # Safe Cancellation
        if ecom == 'SUCCESS' and oper == 'CANCELLED' and cust == 'UNDER_SAFE_CANCELLATION' and single_penalty == 0:
            df.at[index, 'S'] = str(round(grand_total - accelya_base, 2)) # המרה לסטרינג
            df.at[index, 'S_COLOR'] = 'green'
            df.at[index, 'CHECK_COMMENTS'] = "Safe Cancellation"
            continue

        # אקסליה
        adj_accelya = accelya_base
        if airline == 'LY' and 'carryonluggage' in extra_cat_raw:
            adj_accelya += total_extras
            df.at[index, 'CHECK_COMMENTS'] += " | LY CarryOn Adj"
        if airline in luggage_airlines and 'luggage' in extra_cat_raw:
            adj_accelya += total_extras
            df.at[index, 'CHECK_COMMENTS'] += " | Luggage Adj"

        # חישובים
        res_val = 0
        if final_status in ['UNDER_AIRLINE_REFUND', 'UNDER_TICKET_RULE']:
            if final_status == 'UNDER_AIRLINE_REFUND':
                res_val = grand_total - adj_accelya
            else:
                pnr_is_only_digits = bool(re.fullmatch(r'\d+', search_pnr))
                if pnr_is_only_digits and single_penalty == 0:
                    res_val = grand_total - adj_accelya
                    df.at[index, 'S_COLOR'] = 'green'
                    df.at[index, 'CHECK_COMMENTS'] += " | Numeric PNR OK"
                elif single_penalty > 0:
                    res_val = (grand_total - (single_penalty * pax_count)) - adj_accelya
                else:
                    res_val = 0; df.at[index, 'S_COLOR'] = 'purple'; df.at[index, 'CHECK_COMMENTS'] += " | Missing Penalty"

            if df.at[index, 'S_COLOR'] not in ['purple', 'green']:
                df.at[index, 'S'] = str(round(res_val, 2))
                df.at[index, 'S_COLOR'] = 'green' if -300 <= res_val <= 50 else 'red'
            else:
                df.at[index, 'S'] = str(round(res_val, 2))

        elif final_status in ['UNDER_CONSUMER_LAW', 'UNDER_PARTIAL_AIRLINE_REFUND']:
            ratio = adj_accelya / grand_total if grand_total != 0 else 0
            df.at[index, 'S'] = f"{ratio:.2%}"
            limit = 0.90 if final_status == 'UNDER_CONSUMER_LAW' else 0.25
            df.at[index, 'S_COLOR'] = 'green' if ratio >= limit else 'red'
            if ratio > 2.0: df.at[index, 'S_COLOR'] = 'purple'

    return df

# --- 3. ממשק האפליקציה ---
st.set_page_config(page_title="Purple Rain v5.8", layout="centered")
apply_custom_style()

st.markdown("<h1 class='main-title'>Purple Rain Auditor</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>V5.8 | Stable Export Edition</p>", unsafe_allow_html=True)

uploaded_file = st.file_uploader("", type=['csv', 'xlsx'])

if uploaded_file:
    with st.spinner("Processing..."):
        try:
            # טעינה גמישה
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            processed_df = process_data(df)
            
            # וידוא שכל עמודות התוצאה הן טקסט לפני כתיבה לאקסל
            processed_df['S'] = processed_df['S'].astype(str)
            processed_df['S_COLOR'] = processed_df['S_COLOR'].astype(str)
            processed_df['CHECK_COMMENTS'] = processed_df['CHECK_COMMENTS'].astype(str)
            
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
                    if color in formats:
                        worksheet.set_row(row_num, None, formats[color])
            
            st.download_button("📥 DOWNLOAD AUDIT REPORT", output.getvalue(), f"Audit_{uploaded_file.name}.xlsx")
        except Exception as e:
            st.error(f"Error: {e}")
