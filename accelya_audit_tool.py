import streamlit as st
import pandas as pd
import io

def process_data(df):
    # נירמול שמות עמודות לאותיות גדולות
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    df['S'] = ""
    df['S_COLOR'] = ""
    df['CHECK_COMMENTS'] = ""

    # רשימת חברות התעופה הרלוונטיות להחרגת מזוודות
    luggage_airlines = ['J2', 'GQ', 'AZ', 'LA', 'UX', 'EY']

    for index, row in df.iterrows():
        # המרה בטוחה למספרים
        accelya_abs = abs(pd.to_numeric(row.get('ACCELYA AMOUNT', 0), errors='coerce') or 0)
        grand_total = pd.to_numeric(row.get('GRANDTOTAL', 0), errors='coerce') or 0
        single_penalty = pd.to_numeric(row.get('SINGLEPENALTYFEE', 0), errors='coerce') or 0
        pax_count = pd.to_numeric(row.get('ACTIVEPASSENGERSCOUNT', 0), errors='coerce') or 1
        total_extras = pd.to_numeric(row.get('TOTALEXTRAS', 0), errors='coerce') or 0
        
        # שליפת נתונים וניקוי
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
        extra_cat = get_val('EXTRA_CATEGORIES').lower() # קטגוריות ב-lowercase להשוואה נוחה

        # --- שלב החרגות (BLUE) ---
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

        # --- שלב בדיקות כספיות (ירוק/אדום) ---
        if ecom == 'SUCCESS':
            
            # בדיקה האם להפחית TOTALEXTRAS (לפי התנאי החדש שלך)
            # התנאי: חברת תעופה ברשימה וגם הקטגוריה היא luggage בלבד
            apply_extras_reduction = airline in luggage_airlines and extra_cat == 'luggage'
            
            base_amount = grand_total
            if apply_extras_reduction:
                base_amount = grand_total - total_extras
                df.at[index, 'CHECK_COMMENTS'] = "הופחת TOTALEXTRAS (Luggage Rule)"

            # מקרה 1: AIRLINE_REFUND
            if cust == 'UNDER_AIRLINE_REFUND':
                diff = base_amount - accelya_abs
                df.at[index, 'S'] = round(diff, 2)
                df.at[index, 'S_COLOR'] = 'green' if -300 <= diff <= 50 else 'red'

            # מקרה 2: TICKET_RULE (הפחתת קנסות מהבסיס)
            elif cust == 'UNDER_TICKET_RULE':
                expected = base_amount - (single_penalty * pax_count)
                diff_rule = expected - accelya_abs
                df.at[index, 'S'] = round(diff_rule, 2)
                df.at[index, 'S_COLOR'] = 'green' if -300 <= diff_rule <= 50 else 'red'

            # מקרה 3: אחוזים (תמיד מול ה-GrandTotal המקורי)
            elif cust in ['UNDER_PARTIAL_AIRLINE_REFUND', 'UNDER_CONSUMER_LAW']:
                ratio = accelya_abs / grand_total if grand_total != 0 else 0
                df.at[index, 'S'] = f"{ratio:.2%}"
                if cust == 'UNDER_CONSUMER_LAW' and ratio > 2.0:
                    df.at[index, 'S_COLOR'] = 'purple'
                else:
                    df.at[index, 'S_COLOR'] = 'green' if ratio > 0.25 else 'red'

    return df

st.set_page_config(page_title="Accelya Auditor", layout="wide")
st.title("Accelya Auditor - גירסה 2.1")

uploaded_file = st.file_uploader("Upload CSV or Excel", type=['csv', 'xlsx'])

if uploaded_file:
    df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, engine='openpyxl')
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

    st.success("Analysis Complete!")
    st.download_button(label="Download Processed Excel", data=output.getvalue(), file_name="Audit_Result.xlsx")
