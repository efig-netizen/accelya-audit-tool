import streamlit as st
import pandas as pd
import io

def process_data(df):
    df['S'] = ""
    df['S_Color'] = ""
    df['Check_Comments'] = ""

    for index, row in df.iterrows():
        # המרת עמודות למספרים בצורה נקייה
        accelya_val = abs(pd.to_numeric(row.get('Accelya Amount', 0), errors='coerce') or 0)
        grand_total = pd.to_numeric(row.get('GrandTotal', 0), errors='coerce') or 0
        
        # סטטוסים
        ecom_status = str(row.get('ECOMMERCEORDERSTATUS', '')).strip()
        cust_status = str(row.get('CUSTOMERORDERSTATUS', '')).strip()
        oper_status = str(row.get('OPERATIONALORDERSTATUS', '')).strip()
        talma_status = str(row.get('TALMAORDERSTATUS', '')).strip()

        # --- 1. החרגות (כחול) ---
        if ecom_status == 'SUCCESS' and talma_status in ['REFUND', 'NOT_FOR_REFUND']:
            df.at[index, 'S_Color'] = 'blue'
            continue

        # --- 2. בדיקות כספיות ---
        if ecom_status == 'SUCCESS':
            
            # מקרה א': דורש הפרש כספי (GrandTotal פחות Accelya)
            if cust_status in ['UNDER_AIRLINE_REFUND', 'UNDER_TICKET_RULE']:
                diff = grand_total - accelya_val
                df.at[index, 'S'] = round(diff, 2)
                # תנאי צבע: אם ההפרש בין -300 ל-50 זה תקין (ירוק), אחרת אדום
                if -300 <= diff <= 50:
                    df.at[index, 'S_Color'] = 'green'
                else:
                    df.at[index, 'S_Color'] = 'red'

            # מקרה ב': דורש אחוזים (Accelya חלקי GrandTotal)
            elif cust_status in ['UNDER_PARTIAL_AIRLINE_REFUND', 'UNDER_CONSUMER_LAW']:
                ratio = accelya_val / grand_total if grand_total != 0 else 0
                df.at[index, 'S'] = f"{ratio:.2%}"
                
                if cust_status == 'UNDER_CONSUMER_LAW' and ratio > 2.0:
                    df.at[index, 'S_Color'] = 'purple'
                    df.at[index, 'Check_Comments'] = "בדיקה ידנית - מעל 200%"
                elif ratio > 0.25: # סף כללי לירוק ב-Partial/Consumer
                    df.at[index, 'S_Color'] = 'green'
                else:
                    df.at[index, 'S_Color'] = 'red'

    return df

st.set_page_config(page_title="Accelya Auditor", layout="wide")
st.title("מערכת בדיקת Accelya")

uploaded_file = st.file_uploader("Upload CSV or Excel", type=['csv', 'xlsx'])

if uploaded_file:
    if uploaded_file.name.endswith('.csv'):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)
        
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
        
        for row_num in range(1, len(processed_df) + 1):
            color = processed_df.iloc[row_num-1]['S_Color']
            if color in formats:
                worksheet.set_row(row_num, None, formats[color])

    st.success("העיבוד הושלם!")
    st.download_button(label="הורד אקסל תוצאות", data=output.getvalue(), file_name="Audit_Result.xlsx")
