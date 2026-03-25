import streamlit as st
import pandas as pd
import io
import re  # ספרייה לבדיקת תבניות טקסט (עבור PNR מספרי)

# --- 1. הגדרות עיצוב לממשק (Purple Rain Edition) ---
def apply_custom_style():
    st.markdown("""
        <style>
        .stApp {
            background-color: #1e1b2e;
            color: #e0d7ff;
        }
        [data-testid="stHeader"] {
            background-color: rgba(0,0,0,0);
        }
        .stButton>button {
            background-color: #6a1b9a;
            color: white;
            border-radius: 12px;
            border: none;
            padding: 12px 30px;
            font-weight: bold;
            transition: 0.3s;
        }
        .stButton>button:hover {
            background-color: #8e24aa;
            box-shadow: 0px 0px 20px #ba68c8;
            transform: scale(1.02);
        }
        h1 {
            color: #ba68c8;
            text-align: center;
            font-family: 'Trebuchet MS', sans-serif;
            text-shadow: 3px 3px 6px #000000;
            font-size: 3.5rem;
        }
        .subtitle {
            text-align: center;
            color: #ba68c8;
            font-style: italic;
            margin-bottom: 30px;
        }
        .stFileUploader {
            background-color: #2d2942;
            padding: 30px;
            border-radius: 20px;
            border: 2px dashed #ba68c8;
        }
        </style>
    """, unsafe_allow_html=True)

# --- 2. לוגיקת העיבוד המרכזית (הגדרות 0-11) ---
def process_data(df):
    # הגדרה 0: נרמול עמודות (Upper + Strip)
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    df['S'] = ""
    df['S_COLOR'] = ""
    df['CHECK_COMMENTS'] = ""

    # הגדרה 4: חברות תעופה להחרגת מזוודות (Base Amount)
    luggage_airlines = ['J2', 'GQ', 'AZ', 'LA', 'UX', 'EY']

    for index, row in df.iterrows():
        # --- המרה לערכים מספריים (שימוש בערך מוחלט לאקסליה) ---
        acc_raw = row.get('ACCELYA AMOUNT', 0)
        accelya_abs = abs(pd.to_numeric(acc_raw, errors='coerce') or 0)
        
        grand_total = pd.to_numeric(row.get('GRANDTOTAL', 0), errors='coerce') or 0
        single_penalty = pd.to_numeric(row.get('SINGLEPENALTYFEE', 0), errors='coerce') or 0
        pax_count = pd.to_numeric(row.get('ACTIVEPASSENGERSCOUNT', 0), errors='coerce') or 1
        total_extras = pd.to_numeric(row.get('TOTALEXTRAS', 0), errors='coerce') or 0
        
        # פונקציית עזר לניקוי טקסט
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

        # הגדרה 9 & 1: בדיקת סתירות סטטוסים והחמרה לטובת Refund
        statuses = [cust, update]
        if 'UNDER_AIRLINE_REFUND' in statuses and any(s in statuses for s in ['UNDER_TICKET_RULE', 'UNDER_PARTIAL_AIRLINE_REFUND', 'UNDER_CONSUMER_LAW']):
            final_status = 'UNDER_AIRLINE_REFUND'
            df.at[index, 'CHECK_COMMENTS'] = "Conflict: Using Strict Refund"
        else:
            final_status = cust if cust != "" else update

        # הגדרה 2: החרגות בכחול (Blue)
        if ecom == 'SUCCESS' and talma in ['REFUND', 'NOT_FOR_REFUND']:
            df.at[index, 'S_COLOR'] = 'blue'
            continue
        if oper == 'ACTIVE':
            if all(s == "" for s in [cust, fin, talma]) and update in ["", "ORDER_TRIP_CHANGED"]:
                df.at[index, 'S_COLOR'] = 'blue'
                continue
        if ecom != 'SUCCESS' and all(s == "" for s in [oper, cust, fin, talma, update]):
            df.at[index, 'S_COLOR'] = 'blue'
            continue

        # הגדרה 3: Safe Cancellation (ירוק אוטומטי)
        if (ecom == 'SUCCESS' and oper == 'CANCELLED' and 
            cust == 'UNDER_SAFE_CANCELLATION' and update == 'UNDER_TICKET_RULE' and 
            single_penalty == 0):
            df.at[index, 'S'] = round(grand_total - accelya_abs, 2)
            df.at[index, 'S_COLOR'] = 'green'
            df.at[index, 'CHECK_COMMENTS'] = "Safe Cancellation - OK"
            continue

        # --- תחילת בדיקות כספיות (רק אם ECOM הצליח) ---
        if ecom == 'SUCCESS':
            
            # הגדרה 10: תיקון LY Carry-On (הוספת Extras לאקסליה לצורך חישוב הוגן)
            is_ly_carryon = (airline == 'LY' and extra_cat == 'carryOnLuggage')
            effective_accelya = accelya_abs + total_extras if is_ly_carryon else accelya_abs
            if is_ly_carryon:
                df.at[index, 'CHECK_COMMENTS'] = (df.at[index, 'CHECK_COMMENTS'] + " | LY Carry-On Adjusted").strip(" | ")

            # הגדרה 4: חוק המזוודות (הפחתה מה-Base Amount עבור J2 וכו')
            apply_luggage = airline in luggage_airlines and extra_cat.lower() == 'luggage'
            base_amount = grand_total - total_extras if apply_luggage else grand_total
            if apply_luggage:
                df.at[index, 'CHECK_COMMENTS'] = (df.at[index, 'CHECK_COMMENTS'] + " | Luggage Base Reduction").strip(" | ")

            # --- חישובים לפי סטטוס ---
            if final_status == 'UNDER_AIRLINE_REFUND':
                res = base_amount - effective_accelya
                df.at[index, 'S'] = round(res, 2)
                df.at[index, 'S_COLOR'] = 'green' if -300 <= res <= 50 else 'red'

            elif final_status == 'UNDER_TICKET_RULE':
                # הגדרה 11: החרגת PNR שמכיל ספרות בלבד עם קנס 0
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
                    # הגנת ה"סגול" - חסר קנס ב-Ticket Rule
                    df.at[index, 'S'] = "N/A (No Penalty)"
                    df.at[index, 'S_COLOR'] = 'purple'
                    df.at[index, 'CHECK_COMMENTS'] = (df.at[index, 'CHECK_COMMENTS'] + " | Missing Penalty Data").strip(" | ")

            elif final_status in ['UNDER_CONSUMER_LAW', 'UNDER_PARTIAL_AIRLINE_REFUND']:
                ratio = effective_accelya / grand_total if grand_total != 0 else 0
                df.at[index, 'S'] = f"{ratio:.2%}"
                
                if final_status == 'UNDER_CONSUMER_LAW':
                    df.at[index, 'S_COLOR'] = 'green' if ratio >= 0.90 else 'red'
                else: # PARTIAL
                    df.at[index, 'S_COLOR'] = 'green' if ratio >= 0.25 else 'red'
                
                if ratio > 2.0:
                    df.at[index, 'S_COLOR'] = 'purple'
                    df.at[index, 'CHECK_COMMENTS'] = (df.at[index, 'CHECK_COMMENTS'] + " | Check Manual > 200%").strip(" | ")

    return df

# --- 3. ממשק האפליקציה (Streamlit) ---
st.set_page_config(page_title="Purple Rain Auditor v4.2", layout="wide")
apply_custom_style()

st.markdown("<h1>☔ Purple Rain Auditor v4.2</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>The Ultimate Audit Logic - All 12 Rules Integrated</p>", unsafe_allow_html=True)

uploaded_file = st.file_uploader("Upload Snowflake Data (CSV or Excel)", type=['csv', 'xlsx'])

if uploaded_file:
    with st.spinner('🎸 Auditing through the rain...'):
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file, engine='openpyxl')
            
            processed_df = process_data(df)
            
            # יצירת אקסל בזיכרון
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                processed_df.to_excel(writer, index=False, sheet_name='Audit_Results')
                workbook, worksheet = writer.book, writer.sheets['Audit_Results']
                
                # פורמטים לצביעה
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

            st.success("✅ Audit Complete!")
            st.download_button(
                label="📥 Download Audit Report (v4.2)",
                data=output.getvalue(),
                file_name="Purple_Rain_Final_Audit.xlsx",
                mime="application/vnd.ms-excel"
            )
        except Exception as e:
            st.error(f"❌ Error during processing: {e}")

st.write("---")
st.caption("Purple Rain Auditor v4.2 | Logic by User Intent | 2026")
