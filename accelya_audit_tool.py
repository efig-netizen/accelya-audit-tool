import streamlit as st
import pandas as pd
import io
import re

# --- 1. עיצוב ממשק מודרני ונקי (Professional Blue & Gray) ---
def apply_custom_style():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@400;600&display=swap');
        
        .stApp { 
            background-color: #f8fafc; 
            color: #1e293b; 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
        }
        
        h1 { 
            color: #0f172a !important; 
            font-weight: 600 !important; 
            text-align: center;
            margin-bottom: 0.5rem;
        }
        
        .subtitle { 
            text-align: center; 
            color: #64748b; 
            margin-bottom: 2rem;
            font-size: 1.1rem;
        }
        
        /* עיצוב תיבת העלאת הקבצים */
        section[data-testid="stFileUploader"] { 
            background-color: #ffffff !important; 
            border: 1px solid #e2e8f0 !important; 
            border-radius: 12px; 
            padding: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        
        /* עיצוב כפתור ההורדה */
        .stDownloadButton button { 
            width: 100%; 
            background-color: #2563eb !important; 
            color: white !important; 
            border: none !important; 
            padding: 0.75rem !important; 
            border-radius: 8px !important; 
            font-weight: 600 !important;
            transition: all 0.2s ease;
        }
        
        .stDownloadButton button:hover { 
            background-color: #1d4ed8 !important; 
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }

        /* הסתרת אלמנטים מיותרים */
        header {visibility: hidden;} 
        footer {visibility: hidden;}
        </style>
    """, unsafe_allow_html=True)

# --- 2. לוגיקת העיבוד (v5.9 - יציבות מלאה) ---
def process_data(df):
    df.columns = [str(c).strip().upper() for c in df.columns]
    
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

        # החרגות (Blue)
        if ecom == 'SUCCESS' and talma in ['REFUND', 'NOT_FOR_REFUND']:
            df.at[index, 'S_COLOR'] = 'blue'; continue
        if oper == 'ACTIVE' and not any([cust, fin, talma]) and update in ["", "ORDER_TRIP_CHANGED"]:
            df.at[index, 'S_COLOR'] = 'blue'; continue
        if ecom != 'SUCCESS' and not any([oper, cust, fin, talma, update]):
            df.at[index, 'S_COLOR'] = 'blue'; continue

        # Safe Cancellation
        if ecom == 'SUCCESS' and oper == 'CANCELLED' and cust == 'UNDER_SAFE_CANCELLATION' and single_penalty == 0:
            df.at[index, 'S'] = str(round(grand_total - accelya_base, 2))
            df.at[index, 'S_COLOR'] = 'green'
            df.at[index, 'CHECK_COMMENTS'] = "Safe Cancellation"
            continue

        # תיקוני אקסליה
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

            df.at[index, 'S'] = str(round(res_val, 2))
            if df.at[index, 'S_COLOR'] not in ['purple', 'green']:
                df.at[index, 'S_COLOR'] = 'green' if -300 <= res_val <= 50 else 'red'

        elif final_status in ['UNDER_CONSUMER_LAW', 'UNDER_PARTIAL_AIRLINE_REFUND']:
            ratio = adj_accelya / grand_total if grand_total != 0 else 0
            df.at[index, 'S'] = f"{ratio:.2%}"
            limit = 0.90 if final_status == 'UNDER_CONSUMER_LAW' else 0.25
            df.at[index, 'S_COLOR'] = 'green' if ratio >= limit else 'red'
            if ratio > 2.0: df.at[index, 'S_COLOR'] = 'purple'

    return df

# --- 3. ממשק האפליקציה ---
st.set_page_config(page_title="Auditor Pro v5.9", layout="centered")
apply_custom_style()

st.markdown("<h1>Auditor Report Tool</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>Professional Audit System | Clean UI</p>", unsafe_allow_html=True)

uploaded_file = st.file_uploader("Upload your CSV or Excel file", type=['csv', 'xlsx'])

if uploaded_file:
    with st.spinner("Analyzing data..."):
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            processed_df = process_data(df)
            
            # וידוא שכל עמודות התוצאה הן טקסט למניעת שגיאת ה-Float
            for col in ['S', 'S_COLOR', 'CHECK_COMMENTS']:
                processed_df[col] = processed_df[col].astype(str)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                processed_df.to_excel(writer, index=False, sheet_name='Audit')
                workbook, worksheet = writer.book, writer.sheets['Audit']
                
                # צבעים עדינים יותר לדוח האקסל
                formats = {
                    'green': workbook.add_format({'bg_color': '#E8F5E9', 'font_color': '#2E7D32'}),
                    'red': workbook.add_format({'bg_color': '#FFEBEE', 'font_color': '#C62828'}),
                    'blue': workbook.add_format({'bg_color': '#E3F2FD', 'font_color': '#1565C0'}),
                    'purple': workbook.add_format({'bg_color': '#F3E5F5', 'font_color': '#7B1FA2'})
                }
                
                for row_num in range(1, len(processed_df) + 1):
                    color = processed_df.iloc[row_num-1]['S_COLOR']
                    if color in formats:
                        worksheet.set_row(row_num, None, formats[color])
            
            st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
            st.download_button(
                label="📥 DOWNLOAD AUDIT REPORT",
                data=output.getvalue(),
                file_name=f"Audit_Final_{uploaded_file.name.split('.')[0]}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except Exception as e:
            st.error(f"Error: {e}")
