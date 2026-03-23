import streamlit as st
import pandas as pd
import io

# --- 1. הגדרות עיצוב לממשק (CSS) - Purple Rain Edition ---
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
            margin-bottom: 0px;
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
        footer {visibility: hidden;}
        </style>
    """, unsafe_allow_html=True)

# --- 2. לוגיקת העיבוד המרכזית ---
def process_data(df):
    # הגדרה 0: נרמול שמות עמודות (Upper + Strip)
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    # הוספת עמודות עזר לתוצאות
    df['S'] = ""
    df['S_COLOR'] = ""
    df['CHECK_COMMENTS'] = ""

    # הגדרה 4: חברות תעופה להחרגת מזוודות
    luggage_airlines = ['J2', 'GQ', 'AZ', 'LA', 'UX', 'EY']

    for index, row in df.iterrows():
        # המרה בטוחה למספרים
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
        extra_cat = get_val('EXTRA_CATEGORIES').lower()

        # הגדרה 1: מנגנון הגיבוי (Fallback)
        final_status = cust if cust != "" else update

        # --- הגדרה 2: החרגות בכחול (BLUE) ---
        if ecom == 'SUCCESS' and talma in ['REFUND', 'NOT_FOR_REFUND']:
            df.at[index, 'S_COLOR'] = 'blue'
            continue

        if oper == 'ACTIVE':
            others_empty = all(s == "" for s in [cust, fin, talma])
            update_ignore = update in ["", "ORDER_TRIP_CHANGED"]
            if others_empty and update_ignore:
                df.at[index, 'S_COLOR'] = 'blue'
                continue

        if ecom != 'SUCCESS' and all(s == "" for s in [oper, cust, fin, talma, update]):
            df.at[index, 'S_COLOR'] = 'blue'
            continue

        # --- הגדרה 3: חוק ה-SAFE CANCELLATION (ירוק אוטומטי) ---
        if (ecom == 'SUCCESS' and 
            oper == 'CANCELLED' and 
            cust == 'UNDER_SAFE_CANCELLATION' and 
            update == 'UNDER_TICKET_RULE' and 
            single_penalty == 0):
            
            diff_safe = grand_total - accelya_abs
            df.at[index, 'S'] = round(diff_safe, 2)
            df.at[index, 'S_COLOR'] = 'green'
            df.at[index, 'CHECK_COMMENTS'] = "Safe Cancellation - OK"
            continue

        # --- שלב הבדיקות הכספיות (SUCCESS בלבד) ---
        if ecom == 'SUCCESS':
            
            # הגדרה 4: חוק המזוודות - הכנת ה-Base Amount
            apply_extras = airline in luggage_airlines and extra_cat == 'luggage'
            base_amount = grand_total - total_extras if apply_extras else grand_total

            if apply_extras:
                df.at[index, 'CHECK_COMMENTS'] = "הופחת TOTALEXTRAS (Luggage)"

            # הגדרה 5: AIRLINE_REFUND
            if final_status == 'UNDER_AIRLINE_REFUND':
                diff = base_amount - accelya_abs
                df.at[index, 'S'] = round(diff, 2)
                df.at[index, 'S_COLOR'] = 'green' if -300 <= diff <= 50 else 'red'

            # הגדרה 6: TICKET_RULE (החזר בניכוי קנס)
            elif final_status == 'UNDER_TICKET_RULE':
                if single_penalty > 0:
                    expected = base_amount - (single_penalty * pax_count)
                    diff_rule = expected - accelya_abs
                    df.at[index, 'S'] = round(diff_rule, 2)
                    df.at[index, 'S_COLOR'] = 'green' if -300 <= diff_rule <= 50 else 'red'
                else:
                    # הגנת ה"סגול" - חסר קנס בדאטה
                    df.at[index, 'S'] = "N/A (No Penalty)"
                    df.at[index, 'S_COLOR'] = 'purple'
                    df.at[index, 'CHECK_COMMENTS'] = (df.at[index, 'CHECK_COMMENTS'] + " | חסר נתון קנס").strip(" | ")

            # הגדרה 7: CONSUMER LAW (90% ומעלה)
            elif final_status == 'UNDER_CONSUMER_LAW':
                ratio = accelya_abs / grand_total if grand_total != 0 else 0
                df.at[index, 'S'] = f"{ratio:.2%}"
                if ratio > 2.0:
                    df.at[index, 'S_COLOR'] = 'purple'
                    df.at[index, 'CHECK_COMMENTS'] = "בדיקה ידנית > 200%"
                else:
                    df.at[index, 'S_COLOR'] = 'green' if ratio >= 0.90 else 'red'

            # הגדרה 8: PARTIAL AIRLINE REFUND (25% ומעלה)
            elif final_status == 'UNDER_PARTIAL_AIRLINE_REFUND':
                ratio = accelya_abs / grand_total if grand_total != 0 else 0
                df.at[index, 'S'] = f"{ratio:.2%}"
                df.at[index, 'S_COLOR'] = 'green' if ratio >= 0.25 else 'red'

    return df

# --- 3. הרצת הממשק (Streamlit App) ---
st.set_page_config(page_title="Purple Rain Auditor", layout="wide")
apply_custom_style()

st.markdown("<h1>☔ Purple Rain Auditor</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>The ultimate snowflake-accelya auditor</p>", unsafe_allow_html=True)
st.write("---")

uploaded_file = st.file_uploader("Upload your data (CSV or Excel)", type=['csv', 'xlsx'])

if uploaded_file:
    with st.spinner('🎸 Processing through the rain...'):
        try:
            # קריאת הקובץ
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file, engine='openpyxl')
            
            # עיבוד נתונים
            processed_df = process_data(df)
            
            # יצירת קובץ אקסל מעוצב בזיכרון
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
                
                # צביעת השורות באקסל לפי עמודת S_COLOR
                for row_num in range(1, len(processed_df) + 1):
                    color = processed_df.iloc[row_num-1]['S_COLOR']
                    if color in formats:
                        worksheet.set_row(row_num, None, formats[color])

            st.success("✅ Analysis Complete!")
            st.download_button(
                label="📥 Download Processed Results",
                data=output.getvalue(),
                file_name="Purple_Rain_Audit_Result.xlsx",
                mime="application/vnd.ms-excel"
            )
        except Exception as e:
            st.error(f"❌ Error during processing: {e}")

st.write("---")
st.caption("Purple Rain Auditor v3.6 | All conditions included.")
