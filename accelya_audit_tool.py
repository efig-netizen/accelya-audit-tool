import streamlit as st
import pandas as pd
import io
import re

# --- 1. עיצוב ממשק פרימיום (v4.5 Glassmorphism) ---
def apply_custom_style():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@400;600;700&display=swap');
        
        .stApp {
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
            color: #f8fafc;
            font-family: 'Segoe UI', sans-serif;
        }

        .main-title {
            font-size: 3.5rem;
            font-weight: 700;
            text-align: center;
            background: linear-gradient(to right, #c084fc, #6366f1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.2rem;
        }

        .version-tag {
            text-align: center;
            color: #94a3b8;
            font-size: 0.8rem;
            margin-bottom: 2rem;
            letter-spacing: 2px;
        }

        .upload-container {
            background: rgba(255, 255, 255, 0.03);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .stDownloadButton button {
            width: 100%;
            background: linear-gradient(90deg, #7c3aed 0%, #4f46e5 100%);
            border: none; color: white; padding: 0.8rem;
            border-radius: 10px; font-weight: 600;
            transition: all 0.3s ease;
        }

        .stDownloadButton button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(79, 70, 229, 0.4);
        }
        </style>
    """, unsafe_allow_html=True)

# --- 2. לוגיקת העיבוד המרכזית (כל 12 ההגדרות) ---
def process_data(df):
    # הגדרה 0: נרמול עמודות
    df.columns = [str(c).strip().upper() for c in df.columns]
    df['S'] = ""
    df['S_COLOR'] = ""
    df['CHECK_COMMENTS'] = ""

    luggage_airlines = ['J2', 'GQ', 'AZ', 'LA', 'UX', 'EY']

    for index, row in df.iterrows():
        # המרה למספרים (שימוש בערך מוחלט חיובי לאקסליה)
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

        # הגדרה 1+9: קביעת סטטוס סופי (חוק הסתירה והחמרה לטובת Refund)
        statuses = [cust, update]
        if 'UNDER_AIRLINE_REFUND' in statuses and any(s in statuses for s in ['UNDER_TICKET_RULE', 'UNDER_PARTIAL_AIRLINE_REFUND', 'UNDER_CONSUMER_LAW']):
            final_status = 'UNDER_AIRLINE_REFUND'
            df.at[index, 'CHECK_COMMENTS'] = "Conflict Found: Strict Refund Applied"
        else:
            final_status = cust if cust != "" else update

        # הגדרה 2: החרגות בכחול (Blue)
        if ecom == 'SUCCESS' and talma in ['REFUND', 'NOT_FOR_REFUND']:
            df.at[index, 'S_COLOR'] = 'blue'; continue
        if oper == 'ACTIVE' and all(s == "" for s in [cust, fin, talma]) and update in ["", "ORDER_TRIP_CHANGED"]:
            df.at[index, 'S_COLOR'] = 'blue'; continue
        if ecom != 'SUCCESS' and all(s == "" for s in [oper, cust, fin, talma, update]):
            df.at[index, 'S_COLOR'] = 'blue'; continue

        # הגדרה 3: Safe Cancellation (ירוק אוטומטי)
        if (ecom == 'SUCCESS' and oper == 'CANCELLED' and 
            cust == 'UNDER_SAFE_CANCELLATION' and update == 'UNDER_TICKET_RULE' and 
            single_penalty == 0):
            df.at[index, 'S'] = round(grand_total - accelya_abs, 2)
            df.at[index, 'S_COLOR'] = 'green'
            df.at[index, 'CHECK_COMMENTS'] = "Safe Cancellation"
            continue

        # --- שלב החישובים הכספיים (רק ל-SUCCESS) ---
        if ecom == 'SUCCESS':
            
            # הגדרה 10: תיקון LY Carry-On (הוספת אקסטרות לאקסליה)
            is_ly_carryon = (airline == 'LY' and extra_cat == 'carryOnLuggage')
            effective_accelya = accelya_abs + total_extras if is_ly_carryon else accelya_abs
            if is_ly_carryon: df.at[index, 'CHECK_COMMENTS'] += " | LY CarryOn Adj"

            # הגדרה 4: חוק המזוודות (הפחתה מהטוטאל ל-J2 וחברותיה)
            apply_luggage = airline in luggage_airlines and extra_cat.lower() == 'luggage'
            base_amount = grand_total - total_extras if apply_luggage else grand_total

            # בדיקה שקלית (Refund / Ticket Rule)
            if final_status in ['UNDER_AIRLINE_REFUND', 'UNDER_TICKET_RULE']:
                if final_status == 'UNDER_AIRLINE_REFUND':
                    res = base_amount - effective_accelya
                else: # TICKET_RULE
                    # הגדרה 11: PNR מספרי בלבד עם קנס 0 -> ירוק
                    pnr_is_only_digits = bool(re.fullmatch(r'\d+', search_pnr))
                    if pnr_is_only_digits and single_penalty == 0:
                        res = base_amount - effective_accelya
                        df.at[index, 'S_COLOR'] = 'green'
                        df.at[index, 'CHECK_COMMENTS'] += " | Numeric PNR Zero Penalty"
                    elif single_penalty > 0:
                        res = (base_amount - (single_penalty * pax_count)) - effective_accelya
                    else:
                        # הגדרה 6: חוסר נתוני קנס ב-Ticket Rule רגיל
                        res = 0; df.at[index, 'S_COLOR'] = 'purple'; df.at[index, 'CHECK_COMMENTS'] += " | Missing Penalty"
                
                if df.at[index, 'S_COLOR'] != 'purple':
                    df.at[index, 'S'] = round(res, 2)
                    df.at[index, 'S_COLOR'] = 'green' if -300 <= res <= 50 else 'red'

            # הגדרות 7+8: חישוב אחוזים (Consumer Law / Partial)
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
st.set_page_config(page_title="Purple Rain v4.5", layout="wide")
apply_custom_style()

st.markdown("<div class='main-title'>Purple Rain Auditor</div>", unsafe_allow_html=True)
st.markdown("<div class='version-tag'>STABLE PRODUCTION BUILD v4.5</div>", unsafe_allow_html=True)

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.markdown("<div class='upload-container'>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("", type=['csv', 'xlsx'])
    
    if uploaded_file:
        with st.status("Analyzing Dataset...", expanded=True) as status:
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
                
                status.update(label="Audit Successful!", state="complete", expanded=False)
                st.download_button("📥 DOWNLOAD FINAL AUDIT REPORT", output.getvalue(), "Purple_Rain_v4.5.xlsx")
            except Exception as e:
                st.error(f"Error: {e}")
    st.markdown("</div>", unsafe_allow_html=True)
