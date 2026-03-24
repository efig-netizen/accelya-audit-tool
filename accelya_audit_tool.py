import streamlit as st
import pandas as pd
import io

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
        </style>
    """, unsafe_allow_html=True)

# --- 2. לוגיקת העיבוד המרכזית (כל ההגדרות 0-10) ---
def process_data(df):
    # הגדרה 0: נרמול עמודות
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    df['S'] = ""
    df['S_COLOR'] = ""
    df['CHECK_COMMENTS'] = ""

    # רשימת חברות להחרגת מזוודות (הגדרה 4)
    luggage_airlines = ['J2', 'GQ', 'AZ', 'LA', 'UX', 'EY']

    for index, row in df.iterrows():
        # המרה לערך מוחלט חיובי (Absolute Value) - הכרחי לחישובים המעודכנים
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

        # הגדרה 9 & 1: מנגנון הגיבוי ובדיקת סתירות (החמרה לטובת Refund)
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
            df.at[index, 'CHECK_COMMENTS'] = "Safe Cancellation"
            continue

        # --- שלב החישובים הכספיים (SUCCESS בלבד) ---
        if ecom == 'SUCCESS':
            
            # הגדרה 10: תיקון סכום אקסליה עבור אל-על (הוספת Extras למונה/למחסר)
            is_ly_carryon = (airline == 'LY' and extra_cat == 'carryOnLuggage')
            effective_accelya = accelya_abs + total_extras if is_ly_carryon else accelya_abs
            
            if is_ly_carryon:
                df.at[index, 'CHECK_COMMENTS'] = (df.at[index, 'CHECK_COMMENTS'] + " | LY Carry-On Added").strip(" | ")

            # הגדרה 4: חוק המזוודות (הפחתה מהטוטאל ל-J2 וחברותיה)
            apply_luggage = airline in luggage_airlines and extra_cat.lower() == 'luggage'
            base_amount = grand_total - total_extras if apply_luggage else grand_total
            if apply_luggage:
                df.at[index, 'CHECK_COMMENTS'] = (df.at[index, 'CHECK_COMMENTS'] + " | Luggage Base Adj").strip(" | ")

            # הגדרה 5 + 6: חישובים שקליים (Refund / Ticket Rule)
            if final_status in ['UNDER_AIRLINE_REFUND', 'UNDER_TICKET_RULE']:
                if final_status == 'UNDER_AIRLINE_REFUND':
                    res = base_amount - effective_accelya
                else: # TICKET_RULE
                    if single_penalty > 0:
                        res = (base_amount - (single_penalty * pax_count)) - effective_accelya
                    else:
                        res = 0
                        df.at[index, 'S_COLOR'] = 'purple'
                        df.at[index, 'CHECK_COMMENTS'] = (df.at[index, 'CHECK_COMMENTS'] + " | Missing Penalty Data").strip(" | ")
                
                df.at[index, 'S'] = round(res, 2)
                # צביעה לפי טווח (300- עד 50+)
                if df.at[index, 'S_COLOR'] != 'purple':
                    df.at[index, 'S_COLOR'] = 'green' if -300 <= res <= 50 else 'red'

            # הגדרה 7 + 8: חישוב אחוזים (Consumer Law / Partial)
            elif final_status in ['UNDER_CONSUMER_LAW', 'UNDER_PARTIAL_AIRLINE_REFUND']:
                ratio = effective_accelya / grand_total if grand_total != 0 else 0
                df.at[index, 'S'] = f"{ratio:.2%}"
                
                if final_status == 'UNDER_CONSUMER_LAW':
                    df.at[index, 'S_COLOR'] = 'green' if ratio >= 0.90 else 'red'
                else: # PARTIAL
                    df.at[index, 'S_COLOR'] = 'green' if ratio >= 0.25 else 'red'
                
                # בדיקה ידנית מעל 200%
                if ratio > 2.0:
                    df.at[index, 'S_COLOR'] = 'purple'
                    df.at[index, 'CHECK_COMMENTS'] = (df.at[index, 'CHECK_COMMENTS'] + " | Manual Check > 200%").strip(" | ")

    return df

# --- 3. ממשק האפליקציה (Streamlit) ---
st.set_page_config(page_title="Purple Rain Auditor v4.0", layout="wide")
apply_custom_style()

st.markdown("<h1>☔ Purple Rain Auditor v4.0</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>The Complete Audit Engine | 11 Business Rules Applied</p>", unsafe_allow_html=True)

uploaded_file = st.file_uploader("Upload Snowflake Data", type=['csv', 'xlsx'])

if uploaded_file:
    with st.spinner('🎸 Running audit logic...'):
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
                
                # עיצובים לאקסל
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

            st.success("✅ Analysis Complete! You can now download the results.")
            st.download_button(
                label="📥 Download Final Audit (v4.0)",
                data=output.getvalue(),
                file_name="Purple_Rain_Final_Report.xlsx",
                mime="application/vnd.ms-excel"
            )
        except Exception as e:
            st.error(f"❌ Error during processing: {e}")

st.write("---")
st.caption("Purple Rain Auditor v4.0 | Fully Optimized logic for LY Carry-On and Status Conflicts.")
