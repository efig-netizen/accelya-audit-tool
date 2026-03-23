import streamlit as st
import pandas as pd
import io

# --- 1. עיצוב הממשק ---
def apply_custom_style():
    st.markdown("""
        <style>
        .stApp { background-color: #1e1b2e; color: #e0d7ff; }
        .stButton>button { background-color: #6a1b9a; color: white; border-radius: 12px; font-weight: bold; transition: 0.3s; }
        .stButton>button:hover { background-color: #8e24aa; box-shadow: 0px 0px 20px #ba68c8; }
        h1 { color: #ba68c8; text-align: center; text-shadow: 3px 3px 6px #000000; font-size: 3rem; }
        .subtitle { text-align: center; color: #ba68c8; font-style: italic; margin-bottom: 20px; }
        .stFileUploader { background-color: #2d2942; padding: 20px; border-radius: 15px; border: 2px dashed #ba68c8; }
        </style>
    """, unsafe_allow_html=True)

# --- 2. לוגיקת העיבוד ---
def process_data(df):
    df.columns = [str(c).strip().upper() for c in df.columns]
    df['S'] = ""
    df['S_COLOR'] = ""
    df['CHECK_COMMENTS'] = ""

    luggage_airlines = ['J2', 'GQ', 'AZ', 'LA', 'UX', 'EY']

    for index, row in df.iterrows():
        # המרת נתונים
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
        extra_cat = get_val('EXTRA_CATEGORIES').lower()

        # --- הגדרה 9 & 1: קביעת סטטוס סופי עם בדיקת סתירות (Conflict Check) ---
        statuses = [cust, update]
        if 'UNDER_AIRLINE_REFUND' in statuses and (
            'UNDER_TICKET_RULE' in statuses or 
            'UNDER_PARTIAL_AIRLINE_REFUND' in statuses or 
            'UNDER_CONSUMER_LAW' in statuses):
            final_status = 'UNDER_AIRLINE_REFUND'
            df.at[index, 'CHECK_COMMENTS'] = "Conflict Detected: Using Strict Refund"
        else:
            final_status = cust if cust != "" else update

        # --- הגדרה 2: החרגות כחולות ---
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

        # --- הגדרה 3: Safe Cancellation ---
        if (ecom == 'SUCCESS' and oper == 'CANCELLED' and 
            cust == 'UNDER_SAFE_CANCELLATION' and update == 'UNDER_TICKET_RULE' and 
            single_penalty == 0):
            diff_safe = grand_total - accelya_abs
            df.at[index, 'S'] = round(diff_safe, 2)
            df.at[index, 'S_COLOR'] = 'green'
            df.at[index, 'CHECK_COMMENTS'] = "Safe Cancellation - OK"
            continue

        # --- בדיקות כספיות ---
        if ecom == 'SUCCESS':
            # הגדרה 4: מזוודות
            apply_extras = airline in luggage_airlines and extra_cat == 'luggage'
            base_amount = grand_total - total_extras if apply_extras else grand_total
            if apply_extras: df.at[index, 'CHECK_COMMENTS'] += " | Luggage Adjusted"

            # הגדרה 5: Airline Refund (החמרה של הגדרה 9 מתנקזת לכאן)
            if final_status == 'UNDER_AIRLINE_REFUND':
                diff = base_amount - accelya_abs
                df.at[index, 'S'] = round(diff, 2)
                df.at[index, 'S_COLOR'] = 'green' if -300 <= diff <= 50 else 'red'

            # הגדרה 6: Ticket Rule
            elif final_status == 'UNDER_TICKET_RULE':
                if single_penalty > 0:
                    expected = base_amount - (single_penalty * pax_count)
                    diff_rule = expected - accelya_abs
                    df.at[index, 'S'] = round(diff_rule, 2)
                    df.at[index, 'S_COLOR'] = 'green' if -300 <= diff_rule <= 50 else 'red'
                else:
                    df.at[index, 'S'] = "N/A (No Penalty)"
                    df.at[index, 'S_COLOR'] = 'purple'
                    df.at[index, 'CHECK_COMMENTS'] += " | Missing Penalty Data"

            # הגדרה 7: Consumer Law
            elif final_status == 'UNDER_CONSUMER_LAW':
                ratio = accelya_abs / grand_total if grand_total != 0 else 0
                df.at[index, 'S'] = f"{ratio:.2%}"
                df.at[index, 'S_COLOR'] = 'green' if ratio >= 0.90 else 'red'
                if ratio > 2.0: df.at[index, 'S_COLOR'] = 'purple'

            # הגדרה 8: Partial Refund
            elif final_status == 'UNDER_PARTIAL_AIRLINE_REFUND':
                ratio = accelya_abs / grand_total if grand_total != 0 else 0
                df.at[index, 'S'] = f"{ratio:.2%}"
                df.at[index, 'S_COLOR'] = 'green' if ratio >= 0.25 else 'red'

    return df

# --- 3. ממשק Streamlit ---
st.set_page_config(page_title="Purple Rain Auditor", layout="wide")
apply_custom_style()

st.markdown("<h1>☔ Purple Rain Auditor v3.7</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>The Audit Master: All 10 Rules Applied</p>", unsafe_allow_html=True)

uploaded_file = st.file_uploader("Upload File", type=['csv', 'xlsx'])

if uploaded_file:
    with st.spinner('🎸 Audit in progress...'):
        try:
            df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            processed_df = process_data(df)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                processed_df.to_excel(writer, index=False, sheet_name='Audit')
                workbook, worksheet = writer.book, writer.sheets['Audit']
                formats = {'green': workbook.add_format({'bg_color': '#C6EFCE'}),
                           'red': workbook.add_format({'bg_color': '#FFC7CE'}),
                           'blue': workbook.add_format({'bg_color': '#BDD7EE'}),
                           'purple': workbook.add_format({'bg_color': '#E1BEE7'})}
                for row_num in range(1, len(processed_df) + 1):
                    color = processed_df.iloc[row_num-1]['S_COLOR']
                    if color in formats: worksheet.set_row(row_num, None, formats[color])

            st.success("Analysis Complete!")
            st.download_button("📥 Download Results", output.getvalue(), "Purple_Rain_Audit_Final.xlsx")
        except Exception as e:
            st.error(f"Error: {e}")
