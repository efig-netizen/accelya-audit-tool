import streamlit as st
import pandas as pd
import io

# הגדרות עיצוב לממשק (CSS) - סגול עמוק
def apply_custom_style():
    st.markdown("""
        <style>
        .main {
            background-color: #1e1b2e;
            color: #e0d7ff;
        }
        .stButton>button {
            background-color: #6a1b9a;
            color: white;
            border-radius: 8px;
            border: none;
            padding: 10px 24px;
        }
        .stButton>button:hover {
            background-color: #8e24aa;
            border: 1px solid #e0d7ff;
        }
        h1 {
            color: #ba68c8;
            text-align: center;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            text-shadow: 2px 2px 4px #000000;
        }
        .stFileUploader {
            background-color: #2d2942;
            padding: 20px;
            border-radius: 15px;
            border: 1px dashed #ba68c8;
        }
        </style>
    """, unsafe_allow_html=True)

def process_data(df):
    # נירמול שמות עמודות לאותיות גדולות
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    df['S'] = ""
    df['S_COLOR'] = ""
    df['CHECK_COMMENTS'] = ""

    luggage_airlines = ['J2', 'GQ', 'AZ', 'LA', 'UX', 'EY']

    for index, row in df.iterrows():
        accelya_abs = abs(pd.to_numeric(row.get('ACCELYA AMOUNT', 0), errors='coerce') or 0)
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

        # --- החרגות (BLUE) ---
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

        # --- בדיקות כספיות ---
        if ecom == 'SUCCESS':
            apply_extras_reduction = airline in luggage_airlines and extra_cat == 'luggage'
            base_amount = grand_total - total_extras if apply_extras_reduction else grand_total

            # AIRLINE_REFUND
            if cust == 'UNDER_AIRLINE_REFUND':
                diff = base_amount - accelya_abs
                df.at[index, 'S'] = round(diff, 2)
                df.at[index, 'S_COLOR'] = 'green' if -300 <= diff <= 50 else 'red'

            # TICKET_RULE
            elif cust == 'UNDER_TICKET_RULE':
                if single_penalty > 0:
                    expected = base_amount - (single_penalty * pax_count)
                    diff_rule = expected - accelya_abs
                    df.at[index, 'S'] = round(diff_rule, 2)
                    df.at[index, 'S_COLOR'] = 'green' if -300 <= diff_rule <= 50 else 'red'
                else:
                    df.at[index, 'S'] = "N/A (No Penalty)"
                    df.at[index, 'S_COLOR'] = 'purple'
                    df.at[index, 'CHECK_COMMENTS'] = "חוק כרטיס ללא נתון קנס - דורש בדיקה ידנית"

            # PARTIAL / CONSUMER LAW
            elif cust in ['UNDER_PARTIAL_AIRLINE_REFUND', 'UNDER_CONSUMER_LAW']:
                ratio = accelya_abs / grand_total if grand_total != 0 else 0
                df.at[index, 'S'] = f"{ratio:.2%}"
                if cust == 'UNDER_CONSUMER_LAW' and ratio > 2.0:
                    df.at[index, 'S_COLOR'] = 'purple'
                    df.at[index, 'CHECK_COMMENTS'] = "בדיקה ידנית - מעל 200%"
                else:
                    df.at[index, 'S_COLOR'] = 'green' if ratio > 0.25 else 'red'

    return df

# הפעלת האפליקציה
st.set_page_config(page_title="Purple Rain Auditor", layout="wide")
apply_custom_style()

st.title("☔ Purple Rain Auditor")
st.write("---")

uploaded_file = st.file_uploader("גרור לכאן את קובץ ה-Snowflake שלך (CSV או Excel)", type=['csv', 'xlsx'])

if uploaded_file:
    with st.spinner('מעבד נתונים...'):
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file, engine='openpyxl')
            
        processed_df = process_data(df)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            processed_df.to_excel(writer, index=False, sheet_name='Sheet1')
            workbook, worksheet = writer.book, writer.sheets['Sheet1']
            
            formats = {
                'green': workbook.add_format({'bg_color': '#C6EFCE'}),
                'red': workbook.add_format({'bg_color': '#FFC7CE'}),
                'blue': workbook.add_format({'bg_color': '#BDD7EE'}),
                'purple': workbook.add_format({'bg_color': '#E1BEE7'})
            }
            
            for row_num in range(1, len(processed_df) + 1):
                color = processed_df.iloc[row_num-1]['S_COLOR']
                if color in formats:
                    worksheet.set_row(row_num, None, formats[color])

    st.success("העיבוד הושלם בהצלחה!")
    st.download_button(
        label="📥 הורד תוצאות מעובדות",
        data=output.getvalue(),
        file_name="Purple_Rain_Result.xlsx",
        mime="application/vnd.ms-excel"
    )
