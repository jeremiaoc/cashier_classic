import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
from fpdf import FPDF

# Load the secrets
gsheets_secrets = st.secrets["connections"]["gsheets"]

# Set up credentials from the secrets
credentials_dict = {
    "type": gsheets_secrets["type"],
    "project_id": gsheets_secrets["project_id"],
    "private_key_id": gsheets_secrets["private_key_id"],
    "private_key": gsheets_secrets["private_key"].replace('\\n', '\n'),
    "client_email": gsheets_secrets["client_email"],
    "client_id": gsheets_secrets["client_id"],
    "auth_uri": gsheets_secrets["auth_uri"],
    "token_uri": gsheets_secrets["token_uri"],
    "auth_provider_x509_cert_url": gsheets_secrets["auth_provider_x509_cert_url"],
    "client_x509_cert_url": gsheets_secrets["client_x509_cert_url"]
}

# Authenticate and connect to Google Sheets
credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
client = gspread.authorize(credentials)

# Open the Google Sheet by URL
spreadsheet = client.open_by_url(gsheets_secrets["spreadsheet"])

# Load menu items from "Menu" sheet
menu_sheet = spreadsheet.worksheet("Menu")
menu_data = menu_sheet.get_all_records()
menu_items = {}
for item in menu_data:
    category = item['Kategori']
    if category not in menu_items:
        menu_items[category] = []
    menu_items[category].append((item['Menu'], item['Price']))

# Define transaction sheet globally
transaction_sheet = spreadsheet.worksheet("Transaction")

# Initialize session state for summary
if 'summary' not in st.session_state:
    st.session_state['summary'] = {}

def get_next_transaction_id():
    existing_ids = transaction_sheet.col_values(1)
    if len(existing_ids) > 1:
        last_id = int(existing_ids[-1])
        return f"{last_id + 1:03d}"
    else:
        return "001"

def add_transaction(id, waktu, item, quantity, price, subtotal, total, given_cash, change):
    transaction_sheet.append_row([
        id,
        waktu,
        item,
        int(quantity),
        int(price),
        int(subtotal),
        int(total),
        int(given_cash),
        int(change)
    ])
    st.success(f"Transaction for {item} added successfully!")

def update_transaction(id, item, quantity, price):
    transaction_data = transaction_sheet.get_all_records()
    for i, transaction in enumerate(transaction_data):
        if transaction['ID'] == id and transaction['Item'] == item:
            if quantity > 0:
                transaction_sheet.update_cell(i + 2, 4, int(quantity))
                transaction_sheet.update_cell(i + 2, 6, int(quantity * price))
            else:
                transaction_sheet.delete_row(i + 2)
            break

def add_menu_item_to_transaction(id, item, price, quantity):
    total = price * quantity
    add_transaction(id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), item, quantity, price, total, 0, 0)
    st.experimental_rerun()

def generate_pdf(transaction_id, transactions):
    pdf = FPDF()
    pdf.add_page()
    
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Receipt for Transaction ID: {transaction_id}", ln=True, align='C')
    pdf.cell(200, 10, txt=f"Waktu: {transactions[0]['Waktu']}", ln=True, align='C')
    
    pdf.ln(10)
    pdf.set_font("Arial", size=10)
    for transaction in transactions:
        pdf.cell(200, 10, txt=f"Item: {transaction['Item']} - Quantity: {transaction['Quantity']} - Harga: ¥ {transaction['Harga']:,} - Subtotal: ¥ {transaction['Subtotal']:,}", ln=True)
    
    total_price = sum([transaction['Subtotal'] for transaction in transactions])
    given_cash = transactions[0]['Bayar']
    change = transactions[0]['Kembalian']
    
    pdf.ln(10)
    pdf.cell(200, 10, txt=f"Total Price: ¥ {total_price:,}", ln=True)
    pdf.cell(200, 10, txt=f"Given Cash: ¥ {given_cash:,}", ln=True)
    pdf.cell(200, 10, txt=f"Change: ¥ {change:,}", ln=True)
    
    return pdf.output(dest='S').encode('latin1')

st.set_page_config(page_title="Warung Nusantara Indonesia", page_icon="🍜")

st.title("🍜 Warung Nusantara Indonesia")

# Display menu items categorized by 'Kategori'
for category, items in menu_items.items():
    st.write(f"### {category}")
    cols = st.columns(3)
    for i, (item, price) in enumerate(items):
        col = cols[i % 3]
        with col:
            if st.button(item):
                if item in st.session_state['summary']:
                    st.session_state['summary'][item]['quantity'] += 1
                else:
                    st.session_state['summary'][item] = {
                        'price': price,
                        'quantity': 1
                    }
            st.write(f"Price: ¥ {price:,}")

# Display summary of all selected items
st.write("## Summary")
if st.session_state['summary']:
    summary_data = []
    for item, details in st.session_state['summary'].items():
        subtotal = details['price'] * details['quantity']
        summary_data.append({
            "Item": item,
            "Price": details['price'],
            "Quantity": details['quantity'],
            "Subtotal": subtotal
        })

    summary = pd.DataFrame(summary_data)
    total_quantity = summary["Quantity"].sum()
    total_price = summary["Subtotal"].sum()

    for item, details in st.session_state['summary'].items():
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.write(item)
        with col2:
            st.write(f"¥ {details['price']:,}")
        with col3:
            if st.button(f"➖", key=f"decrease_{item}"):
                if details['quantity'] > 1:
                    st.session_state['summary'][item]['quantity'] -= 1
                else:
                    del st.session_state['summary'][item]
                st.rerun()
            st.write(details['quantity'])
            if st.button(f"➕", key=f"increase_{item}"):
                st.session_state['summary'][item]['quantity'] += 1
                st.rerun()
        with col4:
            st.write(f"¥ {details['price'] * details['quantity']:,}")
        with col5:
            if st.button(f"❌ Remove", key=f"remove_{item}"):
                del st.session_state['summary'][item]
                st.rerun()

    st.write(f"**Total Quantity: {total_quantity}**")
    st.write(f"**Total Price: ¥ {total_price:,}**")

    # Input for given cash
    given_cash = st.number_input("Given Cash (¥)", min_value=0, step=1000)
    change = given_cash - total_price if given_cash >= total_price else 0
    st.write(f"**Change: ¥ {change:,}**")

    # Disable the checkout button if given cash is less than the total price
    can_checkout = given_cash >= total_price
    checkout_button = st.button("Check Out", disabled=not can_checkout)

    if checkout_button:
        checkout_id = get_next_transaction_id()
        checkout_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item, details in st.session_state['summary'].items():
            subtotal = details['price'] * details['quantity']
            add_transaction(
                checkout_id,
                checkout_time,
                item,
                details['quantity'],
                details['price'],
                subtotal,
                total_price,
                given_cash,
                change
            )

        st.write(f"## Receipt for Transaction ID: {checkout_id}")
        st.write(f"**Waktu:** {checkout_time}")
        st.write(f"**Total Price:** ¥ {total_price:,}")
        st.write(f"**Given Cash:** ¥ {given_cash:,}")
        st.write(f"**Change:** ¥ {change:,}")

        st.session_state['summary'] = {}
        st.rerun()
else:
    st.write("No items added to the summary.")

# Sidebar for transaction history
st.sidebar.title("Transaction History")

# Load transaction history from "Transaction" sheet
transaction_data = transaction_sheet.get_all_records()

transaction_ids = sorted(list(set([transaction['ID'] for transaction in transaction_data])))
selected_transaction_id = st.sidebar.selectbox("Select Transaction ID", transaction_ids)

if selected_transaction_id:
    selected_transactions = [transaction for transaction in transaction_data if transaction['ID'] == selected_transaction_id]
    if selected_transactions:
        st.sidebar.write(f"### Transaction ID: {selected_transaction_id}")
        st.sidebar.write(f"**Waktu:** {selected_transactions[0]['Waktu']}")

        for transaction in selected_transactions:
            item = transaction['Item']
            price = transaction['Harga']
            quantity = transaction['Quantity']
            subtotal = transaction['Subtotal']
            total = transaction['Total']
            given_cash = transaction['Bayar']
            change = transaction['Kembalian']

            col1, col2, col3, col4, col5 = st.sidebar.columns(5)
            with col1:
                st.sidebar.write(item)
            with col2:
                st.sidebar.write(f"¥ {int(price):,}")
            with col3:
                new_quantity = st.sidebar.number_input(f"Quantity ({item})", min_value=0, value=int(quantity), key=f"qty_{item}_{selected_transaction_id}")
                if new_quantity != quantity:
                    update_transaction(selected_transaction_id, item, new_quantity, int(price))
            with col4:
                st.sidebar.write(f"Subtotal: ¥ {int(subtotal):,}")
            with col5:
                st.sidebar.write(f"Total: ¥ {int(total):,}")

        transaction_df = pd.DataFrame(selected_transactions)
        transaction_df = transaction_df[["Item", "Quantity", "Harga", "Subtotal"]]
        st.sidebar.write("### Transaction Details")
        st.sidebar.dataframe(transaction_df)

        total_price = transaction_df["Subtotal"].sum()
        st.sidebar.write(f"**Total Price: ¥ {total_price:,}**")
        st.sidebar.write(f"**Given Cash: ¥ {given_cash:,}**")
        st.sidebar.write(f"**Change: ¥ {change:,}**")

        # Add new menu item to the selected transaction
        st.sidebar.write("### Add Menu Item")
        selected_menu_item = st.sidebar.selectbox("Select Menu Item", [(item, price) for cat, items in menu_items.items() for item, price in items])
        if selected_menu_item:
            item, price = selected_menu_item
            new_quantity = st.sidebar.number_input(f"Quantity ({item})", min_value=1, step=1, key=f"new_qty_{item}_{selected_transaction_id}")
            if st.sidebar.button("Add Item"):
                add_menu_item_to_transaction("00" + str(selected_transaction_id), item, price, new_quantity)

        # Download receipt as PDF
        if st.sidebar.button("Generate Receipt as PDF"):
            with st.spinner('Please wait...'):
                pdf_content = generate_pdf(selected_transaction_id, selected_transactions)
                st.sidebar.download_button(
                    label="Download Receipt",
                    data=pdf_content,
                    file_name=f"receipt_{selected_transaction_id}.pdf",
                    mime="application/pdf"
                )
