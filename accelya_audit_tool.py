import streamlit as st
import pandas as pd
import io

def process_data(df):
    # יצירת העמודות החדשות
    df['S'] = ""
    df['S_Color'] = ""
    df['Check_Comments'] = ""

    for index, row in df.iterrows():
        # המרת ערכים למספרים (טיפול בשגיאות והפיכה ל-0 אם ריק)
        accelya_abs = abs(pd.to_numeric(row.get('Accelya Amount', 0), errors='coerce') or 0)
        grand_total = pd.to_numeric(row.get('GrandTotal', 0), errors='coerce') or 0
        single_penalty = pd.to_numeric(row.get('SinglePenaltyFee', 0), errors='coerce') or 0
        active_passengers = pd.to_numeric(row.get('ActivePassengersCount', 0), errors='coerce') or 0
        
        # שליחת סטטוסים למשתנים (ניקוי רווחים)
        ecom_status = str(row.get('ECOMMERCEORDERSTATUS', '')).strip()
        cust_status = str(row.get('CUSTOMERORDERSTATUS', '')).strip()
        oper_status = str(row.get('OPERATIONALORDERSTATUS', '')).strip()
        update_status = str(row.get('ORDERUPDATESTATUS', '')).strip()
        talma_status = str(row.get('TALMAORDERSTATUS', '')).strip()
        fin_status = str(row.get('FINANCEORDERSTATUS', '')).strip()

        # --- שלב 1: החרגות (כחול) ---
        if ecom_status == 'SUCCESS' and talma_status in ['REFUND', 'NOT_FOR_REFUND']:
            df.at[index, 'S_Color'] = 'blue'
            continue

        if oper_status == 'ACTIVE' and \
           (not cust_status or cust_status == 'nan') and \
           (not fin_status or fin_status == 'nan') and \
           (not talma_status or talma_status == 'nan') and \
           (not update_status or update_status == 'nan' or update_status == 'ORDER_TRIP_CHANGED'):
            df.at[index, 'S_Color'] = 'blue'
            continue

        if ecom_status != 'SUCCESS' and \
           (not oper_status or oper_status == 'nan') and \
           (not cust_status or cust_status == 'nan') and \
           (not fin_status or fin_status == 'nan') and \
           (not talma_status or talma_status == 'nan') and \
           (not update_status or update_status == 'nan'):
            df.at[index, 'S_Color'] = 'blue'
            continue

        # --- שלב 2: בדיקות כספיות (ירוק/אדום/סגול) ---
        if ecom_status == 'SUCCESS':
            
            # תנאי: AIRLINE_REFUND -> מציג הפרש כספי
            if cust_status == 'UNDER_AIRLINE_REFUND':
                diff = grand_total - accelya_abs
                df.at[index, 'S'] = round(diff, 2) # כתיבת ההפרש לעמודה S
                if -300 <= diff <= 50:
                    df.at[index, 'S_Color'] = 'green'
                else:
                    df.at[index, 'S_Color'] = 'red'

            # תנאי: PARTIAL_AIRLINE_REFUND -> מציג אחוזים
            elif cust_status == 'UNDER_PARTIAL_AIRLINE_REFUND':
                ratio = accelya_abs / grand_total if grand_total != 0 else 0
                df.at[index, 'S'] = f"{ratio:.2%}" # כתיבת האחוז לעמודה S
                if ratio > 0.25:
                    df.at[index, 'S_Color'] = 'green'
                else:
                    df.at[index, 'S_Color'] = 'red'

            # תנאי: CONSUMER_LAW -> מציג אחוזים
            elif cust_status == 'UNDER_CONSUMER_LAW':
                ratio = accelya_abs / grand_total if grand_total != 0 else 0
                df.at[index, 'S'] = f"{ratio:.2%}" # כתיבת האחוז לעמודה S
                if ratio > 2.0:
                    df.at[index, 'S_Color'] = 'purple'
                    df.at[index, 'Check_Comments'] = "בדיקה ידנית - מעל 200%"
                elif ratio > 0.9:
                    df.at[index, 'S_Color'] = 'green'
                else:
                    df.at[index, 'S_Color'] = 'red'

            # תנאי: TICKET_RULE -> מציג הפרש כספי (לפי נוסחת קנס)
            elif cust_status == 'UNDER_TICKET_RULE':
                total_penalty = single_penalty * active_passengers
                expected_refund = grand_total - total_penalty
                diff_rule = expected_refund - accelya_abs
                df.at[index, 'S'] = round(diff_rule, 2) # כתיבת ההפרש לעמודה S
                if -300 <= diff_rule <= 50:
                    df.at[index, 'S_Color'] = 'green'
                else:
                    df.at[index, 'S_Color'] = 'red'

    return df

# הגדרות ממשק Streamlit
st.set_page_config(page_title="Accelya Auditor", layout="wide")
st.title("מערכת בדיקת Accelya")

uploaded_file = st.file_uploader("Upload CSV or Excel from Snowflake", type=['csv', 'xlsx'])

if uploaded_file:
    # קריאת הקובץ לפי הסיומת שלו
    if uploaded_file.name.endswith('.csv'):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)
        
    # עיבוד הנתונים
    processed_df = process_data(df)
    
    # יצירת קובץ אקסל להורדה עם עיצוב
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        processed_df.to_excel(writer, index=False, sheet_name='Sheet1')
        workbook  = writer.book
        worksheet = writer.sheets['Sheet1']
        
        # הגדרת פורמטים לצבעים
        formats = {
            'green': workbook.add_format({'bg_color': '#C6EFCE'}),
            'red': workbook.add_format({'bg_color': '#FFC7CE'}),
            'blue': workbook.add_format({'bg_color': '#BDD7EE'}),
            'purple': workbook.add_format({'bg_color': '#E1BEE7'})
        }
        
        # צביעת השורות לפי עמודת S_Color
        for row_num in range(1, len(processed_df) + 1):
            color = processed_df.iloc[row_num-1]['S_Color']
            if color in formats:
                worksheet.set_row(row_num, None, formats[color])

    st.success("העיבוד הסתיים בהצלחה!")
    st.download_button(
        label="הורד אקסל תוצאות",
        data=output.getvalue(),
        file_name="Accelya_Check_Result.xlsx",
        mime="application/vnd.ms-excel"
    ) 
