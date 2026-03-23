import streamlit as st
import pandas as pd
import io

def process_data(df):
    # ניקוי שמות עמודות - הופך הכל לאותיות גדולות ומוריד רווחים
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    df['S'] = ""
    df['S_COLOR'] = ""
    df['CHECK_COMMENTS'] = ""

    for index, row in df.iterrows():
        # שליפת נתונים לפי שמות עמודות באותיות גדולות
        accelya_abs = abs(pd.to_numeric(row.get('ACCELYA AMOUNT', 0), errors='coerce') or 0)
        grand_total = pd.to_numeric(row.get('GRANDTOTAL', 0), errors='coerce') or 0
        single_penalty = pd.to_numeric(row.get('SINGLEPENALTYFEE', 0), errors='coerce') or 0
        pax_count = pd.to_numeric(row.get('ACTIVEPASSENGERSCOUNT', 0), errors='coerce') or 0
        
        # סטטוסים
        ecom_status = str(row.get('ECOMMERCEORDERSTATUS', '')).strip().upper()
        cust_status = str(row.get('CUSTOMERORDERSTATUS', '')).strip().upper()
        oper_status = str(row.get('OPERATIONALORDERSTATUS', '')).strip().upper()
        talma_status = str(row.get('TALMAORDERSTATUS', '')).strip().upper()

        # --- 1. החרגות (כחול) ---
        if oper_status == 'ACTIVE' or talma_status in ['REFUND', 'NOT_FOR_REFUND'] or ecom_status != 'SUCCESS':
            df.at[index, 'S_COLOR'] = 'blue'
            continue

        # --- 2. בדיקות כספיות ---
        if ecom_status == 'SUCCESS':
            
            # מקרה: AIRLINE_REFUND
            if cust_status == 'UNDER_AIRLINE_REFUND':
                diff = grand_total - accelya_abs
                df.at[index, 'S'] = round(diff, 2)
                df.at[index, 'S_COLOR'] = 'green' if -300 <= diff <= 50 else 'red'

            # מקרה: TICKET_RULE (הפחתת קנסות מהטוטאל לפני השוואה לאקסליה)
            elif cust_status == 'UNDER_TICKET_RULE':
                expected_refund = grand_total - (single_penalty * pax_count)
                diff_rule = expected_refund - accelya_abs
                df.at[index, 'S'] = round(diff_rule, 2)
                df.at[index, 'S_COLOR'] = 'green' if -300 <= diff_rule <= 50 else 'red'

            # מקרה: אחוזים
            elif cust_status in ['UNDER_PARTIAL_AIRLINE_REFUND', 'UNDER_CONSUMER_LAW']:
                ratio = accelya_abs / grand_total if grand_total != 0 else 0
                df.at[index, 'S'] = f"{ratio:.2%}"
                if cust_status == 'UNDER_CONSUMER_LAW' and ratio > 2.0:
                    df.at[index, 'S_COLOR'] = 'purple'
                else:
                    df.at[index, 'S_COLOR'] = 'green' if ratio > 0.25 else 'red'

    return df

st.set_page_config(page_title="Accelya Auditor", layout="wide")
st.title("מערכת בדיקת Accelya - גירסה סופית")

uploaded_file = st.file_uploader("Upload CSV or Excel", type=['csv', 'xlsx'])

if uploaded_file:
    if uploaded_file.name.endswith('.csv'):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file, engine='openpyxl')
        
    processed_df = process_data(df)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        processed_df.to_excel(writer, index=False, sheet_name='Sheet1')
        workbook  = writer.book
        worksheet = writer.sheets['Sheet1']
        
        formats = {
            'green': workbook.add_format({'bg_color': '#C6EFCE'}),
            'red': workbook.add_format({'bg_color': '#FFC7CE'}),
            'blue': workbook.add_format({'bg_color': '#BDD7EE'}),
            'purple': workbook.add_format({'bg_color': '#E1BEE7'})
        }
        
        # צביעה לפי עמודת S_COLOR
        for row_num in range(1, len(processed_df) + 1):
            color = processed_df.iloc[row_num-1]['S_COLOR']
            if color in formats:
                worksheet.set_row(row_num, None, formats[color])

    st.success("העיבוד הושלם!")
    st.download_button(label="הורד אקסל תוצאות", data=output.getvalue(), file_name="Audit_Result.xlsx")
