import streamlit as st
import pandas as pd
import io
import re

# --- 1. עיצוב ממשק משודרג (Modern & Clean Dark Mode) ---
def apply_custom_style():
    st.markdown("""
        <style>
        /* הגדרות כלליות */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
            background-color: #0e1117;
        }

        .stApp {
            background: radial-gradient(circle at top right, #1d1b2e, #0e1117);
            color: #ffffff;
        }

        /* כותרות */
        h1 {
            font-weight: 800;
            letter-spacing: -1px;
            background: linear-gradient(90deg, #ba68c8, #7b1fa2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-align: center;
            font-size: 3.5rem;
            margin-bottom: 10px;
        }

        .subtitle {
            text-align: center;
            color: #94a3b8;
            font-size: 1.1rem;
            margin-bottom: 40px;
            font-weight: 400;
        }

        /* כפתור הורדה והעלאה */
        .stButton>button {
            background: linear-gradient(135deg, #6a1b9a 0%, #4a148c 100%);
            color: white;
            border-radius: 8px;
            border: none;
            padding: 15px 40px;
            font-weight: 600;
            width: 100%;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(106, 27, 154, 0.3);
        }

        .stButton>button:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(106, 27, 154, 0.5);
            color: #f3e5f5;
        }

        /* תיבת העלאת קבצים */
        section[data-testid="stFileUploader"] {
            background-color: rgba(255, 255, 255, 0.03);
            border: 2px dashed #4a148c;
            border-radius: 15px;
            padding: 20px;
            transition: border 0.3s ease;
        }

        section[data-testid="stFileUploader"]:hover {
            border-color: #ba68c8;
        }

        /* הודעות הצלחה */
        .stAlert {
            background-color: rgba(106, 27, 154, 0.1);
            color: #e1bee7;
            border: 1px solid #6a1b9a;
            border-radius: 10px;
        }

        /* קו מפריד */
        hr {
            border: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, #4a148c, transparent);
            margin: 40px 0;
        }
        </style>
    """, unsafe_allow_html=True)

# --- 2. לוגיקת העיבוד (ללא שינוי - גרסה 4.2) ---
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

        statuses = [cust, update]
        if 'UNDER_AIRLINE_REFUND' in statuses and any(s in statuses for s in ['UNDER_TICKET_RULE', 'UNDER_PARTIAL_AIRLINE_REFUND', 'UNDER_CONSUMER_LAW']):
            final_status = 'UNDER_AIRLINE_REFUND'
            df.at[index, 'CHECK_COMMENTS'] = "Conflict: Using Strict Refund"
        else:
            final_status = cust if cust != "" else update

        if ecom == 'SUCCESS' and talma in ['REFUND', 'NOT_FOR_REFUND']:
            df.at[index, 'S_COLOR'] = 'blue'; continue
        if oper == 'ACTIVE' and all(s == "" for s in [cust, fin, talma]) and update in ["", "ORDER_TRIP_CHANGED"]:
            df.at[index, 'S_COLOR'] = 'blue'; continue
        if ecom != 'SUCCESS' and all(s == "" for s in [oper, cust, fin, talma, update]):
            df.at[index, 'S_COLOR'] = 'blue'; continue

        if (ecom == 'SUCCESS' and oper == 'CANCELLED' and 
            cust == 'UNDER_SAFE_CANCELLATION' and update == 'UNDER_TICKET_RULE' and 
            single_penalty == 0):
            df.at[index, 'S'] = round(grand_total - accelya_abs, 2)
            df.at[index, 'S_COLOR'] = 'green'
            df.at[index, 'CHECK_COMMENTS'] = "Safe Cancellation - OK"
            continue

        if ecom == 'SUCCESS':
            is_ly_carryon = (airline == 'LY' and extra_cat == 'carryOnLuggage')
            effective_accelya = accelya_abs + total_extras if is_ly_carryon else accelya_abs
            if is_ly_carryon: df.at[index, 'CHECK_COMMENTS'] = (df.at[index, 'CHECK_COMMENTS'] + " | LY Carry-On Adjusted").strip(" | ")

            apply_luggage = airline in luggage_airlines and extra_cat.lower() == 'luggage'
            base_amount = grand_total - total_extras if apply_luggage else grand_total
            if apply_luggage: df.at[index, 'CHECK_COMMENTS'] = (df.at[index, 'CHECK_COMMENTS'] + " | Luggage Base Reduction").strip(" | ")

            if final_status == 'UNDER_AIRLINE_REFUND':
                res = base_amount - effective_accelya
                df.at[index, 'S'] = round(res, 2)
                df.at[index, 'S_COLOR'] = 'green' if -300 <= res <= 50 else 'red'

            elif final_status == 'UNDER_TICKET_RULE':
                pnr_is_only_digits = bool(re.fullmatch(r'\d+', search_pnr))
                if pnr_is_only_digits and single_penalty == 0:
                    res = base_amount - effective_accelya
                    df.at[index, 'S'] = round(res, 2)
                    df.at[index, 'S_COLOR'] = 'green'
                    df.at[index, 'CHECK_COMMENTS'] = (df.at[index, 'CHECK_COMMENTS'] + " | Numeric PNR Zero Penalty").strip(" | ")
                elif single_penalty > 0:
                    res = (base_amount - (single_penalty * pax_count)) - effective_accelya
                    df.at[index, 'S'] = round(res, 2)
                    df.at[index, 'S_COLOR'] = 'green' if -300 <= res <= 50 else 'red'
                else:
                    df.at[index, 'S'] = "N/A (No Penalty)"
                    df.at[index, 'S_COLOR'] = 'purple'
                    df.at[index, 'CHECK_COMMENTS'] = (df.at[index, 'CHECK_COMMENTS'] + " | Missing Penalty Data").strip(" | ")

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
st.set_page_config(page_title="Purple Rain Auditor v4.3", layout="centered")
apply_custom_style()

st.markdown("<h1>Purple Rain Auditor</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>Advanced Refund Verification Engine v4.3</p>", unsafe_allow_html=True)

# שימוש ב-Columns למראה נקי יותר
col1, col2, col3 = st.columns([1, 6, 1])

with col2:
    uploaded_file = st.file_uploader("Drop your Snowflake file here", type=['csv', 'xlsx'])

    if uploaded_file:
        with st.status("Analyzing Data...", expanded=True) as status:
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
                        'green': workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'}),
                        'red': workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'}),
                        'blue': workbook.add_format({'bg_color': '#BDD7EE', 'font_color': '#000000'}),
                        'purple': workbook.add_format({'bg_color': '#E1BEE7', 'font_color': '#000000'})
                    }
                    for row_num in range(1, len(processed_df) + 1):
                        color = processed_df.iloc[row_num-1]['S_COLOR']
                        if color in formats:
                            worksheet.set_row(row_num, None, formats[color])
                
                status.update(label="Audit Complete!", state="complete", expanded=False)
                st.success("Analysis successful. Your report is ready.")
                
                st.download_button(
                    label="📥 Download Audit Report",
                    data=output.getvalue(),
                    file_name="Purple_Rain_Audit_v4.3.xlsx",
                    mime="application/vnd.ms-excel"
                )
            except Exception as e:
                st.error(f"Error during processing: {e}")

st.markdown("<hr>", unsafe_allow_html=True)
