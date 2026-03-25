import streamlit as st
import pandas as pd
import io
import re

# --- 1. עיצוב ממשק: רקע סגול, תיבת העלאה שחורה, טקסט שחור פנימי ---
def apply_custom_style():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
        
        .stApp {
            background: linear-gradient(135deg, #6d28d9 0%, #4c1d95 100%);
            color: #ffffff;
            font-family: 'Inter', sans-serif;
        }

        h1, h2, h3 {
            color: #ffffff !important;
            font-weight: 700 !important;
            text-align: center;
        }

        .main-title { font-size: 3.5rem; margin-top: 2rem; }
        .subtitle { text-align: center; color: #e9d5ff; margin-bottom: 3rem; }

        /* תיבת העלאת קבצים בשחור */
        section[data-testid="stFileUploader"] {
            background-color: #000000 !important;
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 25px;
        }
        
        /* טקסט שחור בתוך אזור ההעלאה הלבן */
        section[data-testid="stFileUploader"] div, 
        section[data-testid="stFileUploader"] span, 
        section[data-testid="stFileUploader"] small,
        section[data-testid="stFileUploader"] button p {
            color: #000000 !important;
            font-weight: 600 !important;
        }

        /* כפתור הורדה לבן עם טקסט שחור */
        .stDownloadButton button {
            width: 100%;
            background-color: #ffffff;
            color: #000000;
            border: none;
            padding: 1rem;
            border-radius: 8px;
            font-weight: 700;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        }
        </style>
    """, unsafe_allow_html=True)

# --- 2. לוגיקת העיבוד המרכזית (v5.1 - עם הערות מפורטות) ---
def process_data(df):
    # הגדרה 0: נרמול שמות עמודות (UPPERCASE והסרת רווחים)
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    # יצירת עמודות עזר לתוצאות
    df['S'] = ""
    df['S_COLOR'] = ""
    df['CHECK_COMMENTS'] = ""

    # רשימת חברות תעופה שדורשות הוספת מזוודות (הגדרה 4)
    luggage_airlines = ['J2', 'GQ', 'AZ', 'LA', 'UX', 'EY']

    for index, row in df.iterrows():
        # הגדרה 5: הפיכת סכום אקסליה לערך מוחלט (פלוס)
        acc_raw = row.get('ACCELYA AMOUNT', 0)
        accelya_base = abs(pd.to_numeric(acc_raw, errors='coerce') or 0)
        
        # המרת נתונים מספריים נוספים מהדאטה
        grand_total = pd.to_numeric(row.get('GRANDTOTAL', 0), errors='coerce') or 0
        single_penalty = pd.to_numeric(row.get('SINGLEPENALTYFEE', 0), errors='coerce') or 0
        pax_count = pd.to_numeric(row.get('ACTIVEPASSENGERSCOUNT', 0), errors='coerce') or 1
        total_extras = pd.to_numeric(row.get('TOTALEXTRAS', 0), errors='coerce') or 0
        
        # פונקציה פנימית לניקוי טקסטים (NaN/None הופך למחרוזת ריקה)
        def get_val(col):
            val = str(row.get(col, '')).strip().upper()
            return "" if val in ['NAN', 'NONE', 'NULL'] else val

        # שליפת סטטוסים ונתוני מפתח
        ecom = get_val('ECOMMERCEORDERSTATUS')
        cust = get_val('CUSTOMERORDERSTATUS')
        oper = get_val('OPERATIONALORDERSTATUS')
        update = get_val('ORDERUPDATESTATUS')
        talma = get_val('TALMAORDERSTATUS')
        airline = get_val('OUTAIRLINES')
        extra_cat_raw = str(row.get('EXTRA_CATEGORIES', '')).lower()
        search_pnr = str(row.get('SEARCHPNR', '')).strip()

        # הגדרה 1+9: קביעת סטטוס סופי (חוק הסתירה - תעדוף ל-Refund אם יש כפל)
        statuses = [cust, update]
        if 'UNDER_AIRLINE_REFUND' in statuses and any(s in statuses for s in ['UNDER_TICKET_RULE', 'UNDER_PARTIAL_AIRLINE_REFUND', 'UNDER_CONSUMER_LAW']):
            final_status = 'UNDER_AIRLINE_REFUND'
            df.at[index, 'CHECK_COMMENTS'] = "Conflict: Auto-Refund Applied"
        else:
            final_status = cust if cust != "" else update

        # הגדרה 2: החרגות כחולות (Blue) - עסקאות שלא הצליחו או כבר טופלו בטלמה
        if ecom != 'SUCCESS' or (ecom == 'SUCCESS' and talma in ['REFUND', 'NOT_FOR_REFUND']):
            df.at[index, 'S_COLOR'] = 'blue'
            continue

        # הגדרה 3: Safe Cancellation - ירוק אוטומטי אם בוטל בחינם (קנס 0)
        if (ecom == 'SUCCESS' and oper == 'CANCELLED' and cust == 'UNDER_SAFE_CANCELLATION' and update == 'UNDER_TICKET_RULE' and single_penalty == 0):
            df.at[index, 'S'] = round(grand_total - accelya_base, 2)
            df.at[index, 'S_COLOR'] = 'green'
            df.at[index, 'CHECK_COMMENTS'] = "Safe Cancellation - OK"
            continue

        # --- שלב תיקון אקסליה (Addition Only) ---
        adjusted_accelya = accelya_base
        
        # הגדרה 10: תיקון טרולי אל-על (הוספה לאקסליה)
        if airline == 'LY' and 'carryonluggage' in extra_cat_raw:
            adjusted_accelya += total_extras
            df.at[index, 'CHECK_COMMENTS'] += " | LY CarryOn Added"

        # הגדרה 4: חוק המזוודות (הוספה לאקסליה לחברות ספציפיות, כולל זיהוי גמיש ברשימה)
        if airline in luggage_airlines and 'luggage' in extra_cat_raw:
            adjusted_accelya += total_extras
            df.at[index, 'CHECK_COMMENTS'] += " | Luggage Added"

        # --- שלב החישוב והשוואה מול GrandTotal ---
        if final_status in ['UNDER_AIRLINE_REFUND', 'UNDER_TICKET_RULE']:
            if final_status == 'UNDER_AIRLINE_REFUND':
                # חישוב ישיר של הפרש (מחיר מלא פחות אקסליה מתוקנת)
                res = grand_total - adjusted_accelya
            else: # TICKET_RULE
                # הגדרה 11: החרגת PNR מספרי בלבד עם קנס 0 -> ירוק אוטומטי
                pnr_is_only_digits = bool(re.fullmatch(r'\d+', search_pnr))
                if pnr_is_only_digits and single_penalty == 0:
                    res = grand_total - adjusted_accelya
                    df.at[index, 'S_COLOR'] = 'green'
                    df.at[index, 'CHECK_COMMENTS'] += " | Numeric PNR Zero Penalty"
                elif single_penalty > 0:
                    # הגדרה 6: חישוב בסיס בניכוי קנסות (קנס * נוסעים)
                    expected = grand_total - (single_penalty * pax_count)
                    res = expected - adjusted_accelya
                else:
                    # סימון סגול במקרה שחסרים נתוני קנס ב-Ticket Rule
                    res = 0
                    df.at[index, 'S_COLOR'] = 'purple'
                    df.at[index, 'CHECK_COMMENTS'] += " | Missing Penalty Info"

            # צביעה לפי טווח (300- עד 50+)
            if df.at[index, 'S_COLOR'] != 'purple' and df.at[index, 'S_COLOR'] != 'green':
                df.at[index, 'S'] = round(res, 2)
                df.at[index, 'S_COLOR'] = 'green' if -300 <= res <= 50 else 'red'
            elif df.at[index, 'S_COLOR'] == 'green':
                df.at[index, 'S'] = round(res, 2)

        # הגדרה 7+8: חישוב אחוזים (Consumer Law / Partial Refund)
        elif final_status in ['UNDER_CONSUMER_LAW', 'UNDER_PARTIAL_AIRLINE_REFUND']:
            ratio = adjusted_accelya / grand_total if grand_total != 0 else 0
            df.at[index, 'S'] = f"{ratio:.2%}"
            # חוק הגנת הצרכן דורש 90% החזר, החזר חלקי דורש 25%
            limit = 0.90 if final_status == 'UNDER_CONSUMER_LAW' else 0.25
            df.at[index, 'S_COLOR'] = 'green' if ratio >= limit else 'red'
            # הגנה מפני אחוזים חריגים מדי
            if ratio > 2.0: df.at[index, 'S_COLOR'] = 'purple'

    return df

# --- 3. ממשק האפליקציה ---
st.set_page_config(page_title="Purple Rain v5.1", layout="centered")
apply_custom_style()

st.markdown("<h1 class='main-title'>Purple Rain Auditor</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>V5.1 | Stable Production Build | Fully Commented</p>", unsafe_allow_html=True)

uploaded_file = st.file_uploader("", type=['csv', 'xlsx'])

if uploaded_file:
    with st.spinner("Executing Audit Logic..."):
        try:
            # טעינת הקובץ (CSV או Excel)
            df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            processed_df = process_data(df)
            
            # יצירת הקובץ להורדה עם פורמטים של צבעים באקסל
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                processed_df.to_excel(writer, index=False, sheet_name='Audit_Report')
                workbook, worksheet = writer.book, writer.sheets['Audit_Report']
                
                # הגדרת צבעי התאים באקסל המופק
                formats = {
                    'green': workbook.add_format({'bg_color': '#D1FAE5', 'font_color': '#064E3B'}),
                    'red': workbook.add_format({'bg_color': '#FEE2E2', 'font_color': '#7F1D1D'}),
                    'blue': workbook.add_format({'bg_color': '#DBEAFE', 'font_color': '#1E3A8A'}),
                    'purple': workbook.add_format({'bg_color': '#F3E8FF', 'font_color': '#581C87'})
                }
                # צביעת שורות לפי עמודת S_COLOR
                for row_num in range(1, len(processed_df) + 1):
                    color = processed_df.iloc[row_num-1]['S_COLOR']
                    if color in formats:
                        worksheet.set_row(row_num, None, formats[color])
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.download_button("📥 DOWNLOAD AUDIT REPORT", output.getvalue(), f"Audit_Final_{uploaded_file.name}.xlsx")
            st.success("Audit complete. File is ready.")
        except Exception as e:
            st.error(f"Error during processing: {e}")
