import re
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(
    page_title="Cuentas del negocio",
    page_icon="💼",
    layout="wide",
)

CREDIT_OPTIONS = [15, 30, 45, 60]
PAYMENT_METHODS = ["Transferencia", "Efectivo", "Cheque", "Tarjeta", "Otro"]
MONTHS = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

st.markdown("""
<style>
.cover-heading {
    text-align: center;
    margin: 0 auto 2rem auto;
}open -e ~/Documents/cuentas-online/app.py


.cover-heading h1 {
    font-family: Georgia, serif;
    font-size: 2.6rem;
    color: #171914;
    margin-bottom: 0.2rem;
}

.cover-heading p {
    color: #665c4c;
    font-family: Georgia, serif;
    font-size: 1.2rem;
    font-style: italic;
}

.hero-card {
    background: #263d32;
    color: #ffffff;
    border-radius: 18px;
    padding: 1.4rem;
    min-height: 145px;
    box-shadow: 0 5px 18px rgba(25, 40, 30, 0.15);
}

.hero-card div {
    font-size: 0.75rem;
    letter-spacing: 0.08em;
    opacity: 0.8;
}

.hero-card h2 {
    color: white;
    font-size: 2rem;
    margin: 0.8rem 0 0.2rem 0;
}

.hero-card p {
    margin: 0;
    opacity: 0.8;
}

<style>
.stApp {
    background: #f5f3eb;
    color: #202923;
}

div.block-container {
    max-width: 1450px;
    padding-top: 2rem;
}

section[data-testid="stSidebar"] {
    background: #ebe9df;
    border-right: 1px solid #deddd3;
}

h1 {
    color: #17231c;
    font-family: Georgia, serif;
    font-size: 2.7rem;
}

h2, h3 {
    color: #202923;
}

div[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e8e6dd;
    border-radius: 18px;
    padding: 20px;
    box-shadow: 0 4px 16px rgba(32, 41, 35, 0.06);
}

div[data-testid="stMetricLabel"] {
    color: #6d756e;
}

div[data-testid="stMetricValue"] {
    color: #263d32;
    font-weight: 700;
}

div.stButton > button {
    border-radius: 13px;
    border: 1px solid #e5e3d9;
    background: #ffffff;
    color: #263d32;
    min-height: 44px;
    font-weight: 600;
}

div.stButton > button:hover {
    border-color: #87977a;
    color: #263d32;
}

div[data-testid="stDataFrame"] {
    background: white;
    border: 1px solid #e8e6dd;
    border-radius: 16px;
    overflow: hidden;
}
</style>
</style>
""", unsafe_allow_html=True)


def find_logo():
    folder = Path(__file__).resolve().parent
    for name in ("logo.png", "logo.jpg", "logo.jpeg"):
        image_path = folder / name
        if image_path.is_file():
            return image_path
    return None


def login_screen():
    logo = find_logo()
    if logo:
        left, center, right = st.columns([1, 2, 1])
        with center:
            st.image(str(logo), width=180)

    st.title("💼 Cuentas del negocio")
    st.write("Inicia sesión con el correo y la contraseña que creaste.")

    with st.form("login_form"):
        email = st.text_input("Correo")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Iniciar sesión")

    if submitted:
        try:
            client = create_client(
                st.secrets["SUPABASE_URL"],
                st.secrets["SUPABASE_KEY"],
            )
            response = client.auth.sign_in_with_password({
                "email": email.strip(),
                "password": password,
            })
            user = response.user

            profile = (
                client.table("profiles")
                .select("role")
                .eq("id", str(user.id))
                .limit(1)
                .execute()
                .data
            )

            if not profile:
                st.error("Esta cuenta no tiene un permiso asignado. Contacta al administrador.")
                return

            st.session_state["db"] = client
            st.session_state["email"] = user.email
            st.session_state["role"] = profile[0]["role"]
            st.session_state["page"] = "Resumen"
            st.rerun()
        except Exception:
            st.error("No se pudo iniciar sesión. Revisa el correo y la contraseña.")


def db_rows(table, columns="*"):
    return (
        st.session_state["db"]
        .table(table)
        .select(columns)
        .execute()
        .data or []
    )


def flash(message):
    st.session_state["_flash"] = message
    st.rerun()


def is_duplicate_error(error):
    text = str(error).lower()
    return "23505" in text or "duplicate" in text or "unique" in text


def get_staff_full_name(person):
    return " ".join(
        part for part in [person.get("name", ""), person.get("last_name", "")]
        if part
    )


def account_status(account, paid_amount):
    balance = round(float(account["amount"]) - paid_amount, 2)
    due_date = date.fromisoformat(str(account["due_date"])[:10])
    days_left = (due_date - date.today()).days

    if balance <= 0.005:
        status = "Pagado"
    elif days_left < 0:
        status = "Vencido"
    elif paid_amount > 0:
        status = "Parcial"
    else:
        status = "Pendiente"

    return balance, status, days_left


def load_accounts(kind=None):
    query = st.session_state["db"].table("accounts").select("*")
    if kind:
        query = query.eq("kind", kind)

    accounts = query.order("due_date").execute().data or []
    payments_by_account = {}

    if accounts:
        account_ids = [str(account["id"]) for account in accounts]
        payments = (
            st.session_state["db"]
            .table("payments")
            .select("account_id,amount")
            .in_("account_id", account_ids)
            .execute()
            .data or []
        )
        for payment in payments:
            account_id = str(payment["account_id"])
            payments_by_account[account_id] = (
                payments_by_account.get(account_id, 0.0)
                + float(payment["amount"])
            )

    return accounts, payments_by_account


def get_lookups():
    agencies = db_rows("agencies", "id,name")
    staff = db_rows("staff", "id,name,last_name")
    projects = db_rows("projects")
    assignments = db_rows("assignments")

    return (
        {str(row["id"]): row["name"] for row in agencies},
        {str(row["id"]): get_staff_full_name(row) for row in staff},
        {str(row["id"]): row for row in projects},
        {str(row["id"]): row for row in assignments},
    )


def make_report_dataframe(accounts, paid, agency_names, staff_names, project_map):
    records = []

    for account in accounts:
        account_id = str(account["id"])
        paid_amount = paid.get(account_id, 0.0)
        balance, status, _ = account_status(account, paid_amount)
        period = account.get("period") or str(account["invoice_date"])[:7]
        project = project_map.get(str(account.get("project_id")), {})

        records.append({
            "Mes": period,
            "Agencia": agency_names.get(str(account.get("agency_id")), ""),
            "Persona": staff_names.get(str(account.get("staff_id")), ""),
            "Proyecto": project.get("name", ""),
            "Factura": account.get("invoice_number") or "",
            "Fecha factura": str(account["invoice_date"])[:10],
            "Vencimiento": str(account["due_date"])[:10],
            "Monto": float(account["amount"]),
"ITBMS": float(account.get("itbms_amount") or 0),

            "Pagado": round(paid_amount, 2),
            "Saldo": balance,
            "Estado": status,
        })

    return pd.DataFrame(records)


def make_pdf(dataframe, title):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    small = ParagraphStyle(
        "small", parent=styles["BodyText"], fontSize=7, leading=8
    )
    header_style = ParagraphStyle(
        "header",
        parent=small,
        textColor=colors.white,
        fontName="Helvetica-Bold",
    )

    table_data = [[
        Paragraph(escape(str(column)), header_style)
        for column in dataframe.columns
    ]]

    for row in dataframe.itertuples(index=False, name=None):
        table_data.append([
            Paragraph(escape(str(value)), small)
            for value in row
        ])

    widths = [45, 58, 58, 58, 48, 48, 48, 48, 42, 48, 48, 48]

    table = Table(table_data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#167D78")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D5DEDC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F0F7F6")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))

    document.build([
        Paragraph(escape(title), styles["Title"]),
        Spacer(1, 8),
        table,
    ])
    return buffer.getvalue()


def show_summary(role):
    accounts, paid = load_accounts()

    visible = [
        a for a in accounts
        if role == "admin" or a["kind"] == "pagar"
    ]

    receivable = [a for a in visible if a["kind"] == "cobrar"]
    payable = [a for a in visible if a["kind"] == "pagar"]

    total_receivable = sum(
        account_status(a, paid.get(str(a["id"]), 0))[0] for a in receivable
    )
    total_payable = sum(
        account_status(a, paid.get(str(a["id"]), 0))[0] for a in payable
    )

    today = date.today()
    month_name = MONTHS[today.month - 1]

    # Encabezado del tablero y acceso a generar el mes.
    header, action = st.columns([4, 1])
    with header:
        st.markdown(f"### {month_name} {today.year}")
        st.markdown("## Buenos días")
    with action:
        if role == "admin" and st.button("＋ Generar mes", key="home_generate"):
            st.session_state["page"] = "Generar mes"
            st.rerun()

    # Tarjeta principal y saldos.
    if role == "admin":
        hero, cobrar, pagar = st.columns([1.4, 1, 1])

        with hero:
            st.markdown(
                f"""
                <div class="hero-card">
                  <div>RESUMEN DEL MES</div>
                  <h2>${total_receivable - total_payable:,.2f}</h2>
                  <p>Balance pendiente neto</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        cobrar.metric("Por cobrar", f"${total_receivable:,.2f}")
        pagar.metric("Por pagar", f"${total_payable:,.2f}")
    else:
        hero, pagar = st.columns([1.4, 1])

        with hero:
            st.markdown(
                f"""
                <div class="hero-card">
                  <div>CUENTAS POR PAGAR</div>
                  <h2>${total_payable:,.2f}</h2>
                  <p>Saldo pendiente al personal</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        pagar.metric("Pendiente por pagar", f"${total_payable:,.2f}")

    # Selector y gráfico mensual.
    st.subheader("Ingresos y pagos")
    period_choice = st.radio(
        "Periodo",
        ["6 meses", "Trimestre", "Año"],
        horizontal=True,
        label_visibility="collapsed",
        key="summary_period",
    )
    count = {"6 meses": 6, "Trimestre": 3, "Año": 12}[period_choice]

    current = pd.Period(today, freq="M")
    months = [str(current - offset) for offset in range(count - 1, -1, -1)]
    chart = pd.DataFrame(
        0.0,
        index=months,
        columns=["Por cobrar", "Por pagar"],
    )

    for account in visible:
        month = account.get("period") or str(account["invoice_date"])[:7]
        if month in chart.index:
            column = "Por cobrar" if account["kind"] == "cobrar" else "Por pagar"
            chart.loc[month, column] += float(account["amount"])

    chart_col, alerts_col = st.columns([1.6, 1])

    with chart_col:
        st.bar_chart(chart, use_container_width=True)

    # Avisos de vencimiento.
    overdue = []
    upcoming = []

    for account in visible:
        balance, status, days_left = account_status(
            account, paid.get(str(account["id"]), 0)
        )
        if balance <= 0:
            continue

        line = (
            f"{account['party']} · Factura "
            f"{account.get('invoice_number') or 'sin número'} · "
            f"${balance:,.2f} · vence {account['due_date']}"
        )

        if status == "Vencido":
            overdue.append(line)
        elif 0 <= days_left <= 7:
            upcoming.append(line)

    with alerts_col:
        st.markdown("#### Próximos vencimientos")
        if overdue:
            st.error("Vencidas:\n\n" + "\n\n".join(overdue))
        if upcoming:
            st.warning("Vencen en 7 días:\n\n" + "\n\n".join(upcoming))
        if not overdue and not upcoming:
            st.success("No hay cuentas próximas a vencer.")

    # Últimas cinco cuentas.
    recent = sorted(
        visible,
        key=lambda a: a["invoice_date"],
        reverse=True,
    )[:5]

    if recent:
        rows = []
        for account in recent:
            balance, status, _ = account_status(
                account, paid.get(str(account["id"]), 0)
            )
            rows.append({
                "Tipo": "Por cobrar" if account["kind"] == "cobrar" else "Por pagar",
                "Agencia / persona": account["party"],
                "Factura": account.get("invoice_number") or "",
                "Vencimiento": account["due_date"],
                "Saldo": balance,
                "Estado": status,
            })

        st.subheader("Cuentas recientes")
        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            use_container_width=True,
        )


def import_excel_page():
    import unicodedata

    st.header("Importar facturas desde Excel")
    st.caption(
        "Se importarán el cliente, la factura, la fecha de emisión, "
        "el ITBMS y el total."
    )

    uploaded = st.file_uploader(
        "Selecciona el archivo Excel",
        type=["xlsx"],
        key="invoice_excel_upload",
    )
    if uploaded is None:
        return

    try:
        df = pd.read_excel(uploaded)
    except Exception as error:
        st.error(f"No se pudo leer el Excel: {error}")
        return

    if df.empty:
        st.warning("El archivo no tiene filas de facturas.")
        return

    columns = list(df.columns)

    def normalize(value):
        text = unicodedata.normalize("NFD", str(value).strip().lower())
        text = "".join(char for char in text if unicodedata.category(char) != "Mn")
        return re.sub(r"[^a-z0-9]", "", text)

    def suggested_index(tokens):
        for index, column in enumerate(columns):
            header = normalize(column)
            if all(token in header for token in tokens):
                return index
        return 0

    col1, col2 = st.columns(2)
    client_col = col1.selectbox(
        "Columna del cliente",
        columns,
        index=suggested_index(["receptor"]),
        key="excel_client_column",
    )
    invoice_col = col2.selectbox(
        "Columna del número de factura",
        columns,
        index=suggested_index(["numero", "factura"]),
        key="excel_invoice_column",
    )

    col3, col4, col5 = st.columns(3)
    date_col = col3.selectbox(
        "Columna de fecha de emisión",
        columns,
        index=suggested_index(["fecha", "emision"]),
        key="excel_date_column",
    )
    tax_col = col4.selectbox(
        "Columna de Valor ITBMS",
        columns,
        index=suggested_index(["valor", "itbms"]),
        key="excel_tax_column",
    )
    total_col = col5.selectbox(
        "Columna de Valor total de la Factura",
        columns,
        index=suggested_index(["valor", "total", "factura"]),
        key="excel_total_column",
    )

    agencies = db_rows("agencies", "id,name")
    agency_by_name = {normalize(a["name"]): a for a in agencies}

    if not agency_by_name:
        st.warning("Primero registra las agencias en la aplicación.")
        return

    existing_accounts = (
        st.session_state["db"]
        .table("accounts")
        .select("agency_id,invoice_number")
        .eq("kind", "cobrar")
        .execute()
        .data or []
    )
    existing_keys = {
        (str(a["agency_id"]), normalize(a["invoice_number"]))
        for a in existing_accounts
        if a.get("invoice_number")
    }
    seen_in_file = set()
    prepared = []

    def read_money(value):
        if pd.isna(value):
            return None

        text = str(value).strip().replace("$", "").replace(" ", "")
        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif "," in text:
            text = text.replace(",", ".")

        try:
            return round(float(text), 2)
        except ValueError:
            return None

    def read_invoice_number(value):
        if pd.isna(value):
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()

    for _, row in df.iterrows():
        client_name = str(row[client_col]).strip()
        invoice_number = read_invoice_number(row[invoice_col])
        invoice_date = pd.to_datetime(row[date_col], errors="coerce", dayfirst=True)
        tax = read_money(row[tax_col])
        total = read_money(row[total_col])
        agency = agency_by_name.get(normalize(client_name))
        status = "Lista"

        if not agency:
            status = "Agencia no encontrada"
        elif not invoice_number:
            status = "Falta el número de factura"
        elif pd.isna(invoice_date):
            status = "Fecha de emisión inválida"
        elif total is None or total <= 0:
            status = "Total inválido"
        elif tax is None:
            status = "ITBMS inválido"
        elif tax < 0 or tax > total:
            status = "ITBMS inválido"
        else:
            duplicate_key = (str(agency["id"]), normalize(invoice_number))
            if duplicate_key in existing_keys or duplicate_key in seen_in_file:
                status = "Factura duplicada"
            else:
                seen_in_file.add(duplicate_key)

        credit_days = (
            60
            if "marketmedios" in normalize(client_name)
            or (agency and "marketmedios" in normalize(agency["name"]))
            else 30
        )

        prepared.append({
            "Cliente": client_name,
            "Factura": invoice_number,
            "Fecha de emisión": (
                invoice_date.strftime("%Y-%m-%d")
                if not pd.isna(invoice_date) else ""
            ),
            "ITBMS": tax if tax is not None else "",
            "Total factura": total if total is not None else "",
            "Crédito (días)": credit_days,
            "Estado": status,
            "_agency_id": str(agency["id"]) if agency else None,
            "_date": (
                invoice_date.date().isoformat()
                if not pd.isna(invoice_date) else None
            ),
        })

    st.subheader("Revisar antes de importar")
    preview = pd.DataFrame(prepared)
    st.dataframe(
        preview.drop(columns=["_agency_id", "_date"]),
        hide_index=True,
        use_container_width=True,
    )

    ready = [item for item in prepared if item["Estado"] == "Lista"]
    if not ready:
        st.warning("No hay facturas listas para importar.")
        return

    if st.button(f"Importar {len(ready)} facturas", key="import_excel_button"):
        imported = 0
        errors = []

        for item in ready:
            try:
                st.session_state["db"].table("accounts").insert({
                    "kind": "cobrar",
                    "party": item["Cliente"],
                    "agency_id": item["_agency_id"],
                    "invoice_number": item["Factura"],
                    "invoice_date": item["_date"],
                    "credit_days": item["Crédito (días)"],
                    "amount": item["Total factura"],
                    "itbms_amount": item["ITBMS"],
                }).execute()
                imported += 1
            except Exception as error:
                errors.append(
                    f"Factura {item['Factura']}: {error}"
                )

        if imported:
            st.success(f"Se importaron {imported} facturas.")
        if errors:
            st.error("Algunas facturas no se importaron:\n\n" + "\n\n".join(errors))


def show_accounts(kind):
    is_receivable = kind == "cobrar"
    st.header("Cuentas por cobrar" if is_receivable else "Cuentas por pagar")

    accounts, paid = load_accounts(kind)
    agency_names, staff_names, project_map, _ = get_lookups()

    if not accounts:
        st.info("Todavía no hay cuentas de este tipo.")
        return

    if is_receivable:
        entity_field = "agency_id"
        entity_label = "Agencia"
        entity_names = agency_names
    else:
        entity_field = "staff_id"
        entity_label = "Persona"
        entity_names = staff_names

    entity_ids = sorted({
        str(a[entity_field]) for a in accounts if a.get(entity_field)
    }, key=lambda value: entity_names.get(value, "").lower())

    month_values = sorted({
        a.get("period") or str(a["invoice_date"])[:7]
        for a in accounts
    })
    project_ids = sorted({
        str(a["project_id"]) for a in accounts if a.get("project_id")
    }, key=lambda value: project_map.get(value, {}).get("name", "").lower())

    c1, c2, c3, c4 = st.columns(4)
    selected_entity = c1.selectbox(
        entity_label,
        ["Todas"] + entity_ids,
        format_func=lambda value: (
            "Todas" if value == "Todas"
            else entity_names.get(value, "Sin nombre")
        ),
    )
    selected_month = c2.selectbox("Mes", ["Todos"] + month_values)
    selected_status = c3.selectbox(
        "Estado", ["Todos", "Pendiente", "Parcial", "Vencido", "Pagado"]
    )
    selected_project = c4.selectbox(
        "Proyecto",
        ["Todos"] + project_ids,
        format_func=lambda value: (
            "Todos" if value == "Todos"
            else project_map.get(value, {}).get("name", "Sin nombre")
        ),
    )

    name_search = st.text_input(
        f"Buscar por nombre de {entity_label.lower()}"
    ).strip().casefold()

    filtered = []
    for account in accounts:
        _, status, _ = account_status(
            account, paid.get(str(account["id"]), 0)
        )
        period = account.get("period") or str(account["invoice_date"])[:7]
        entity_name = entity_names.get(
            str(account.get(entity_field)), account.get("party", "")
        )

        if selected_entity != "Todas" and str(account.get(entity_field)) != selected_entity:
            continue
        if selected_month != "Todos" and period != selected_month:
            continue
        if selected_status != "Todos" and status != selected_status:
            continue
        if selected_project != "Todos" and str(account.get("project_id")) != selected_project:
            continue
        if name_search and name_search not in entity_name.casefold():
            continue

        filtered.append(account)

    dataframe = make_report_dataframe(
        filtered, paid, agency_names, staff_names, project_map
    )
    total_balance = sum(
        account_status(a, paid.get(str(a["id"]), 0))[0]
        for a in filtered
    )

    metrics = st.columns(3)
    metrics[0].metric("Total facturado", f"${sum(float(a['amount']) for a in filtered):,.2f}")
    metrics[1].metric("Total cobrado", f"${sum(paid.get(str(a['id']), 0) for a in filtered):,.2f}")
    metrics[2].metric("Saldo por cobrar", f"${total_balance:,.2f}")

    st.dataframe(dataframe, hide_index=True, use_container_width=True)
    if st.session_state.get("role") == "admin" and filtered:
        st.subheader("Eliminar factura duplicada")

        delete_labels = {
            str(account["id"]): (
                f'{account["party"]} · Factura '
                f'{account.get("invoice_number") or "sin número"} · '
                f'${float(account["amount"]):,.2f}'
            )
            for account in filtered
        }

        delete_id = st.selectbox(
            "Selecciona la factura que quieres eliminar",
            list(delete_labels),
            format_func=lambda account_id: delete_labels[account_id],
            key=f"delete_invoice_{kind}",
        )

        confirm_delete = st.checkbox(
            "Confirmo que seleccioné la factura duplicada",
            key=f"confirm_delete_{kind}",
        )

        if st.button(
            "Eliminar factura seleccionada",
            disabled=not confirm_delete,
            key=f"delete_button_{kind}",
        ):
            try:
                payments = (
                    st.session_state["db"]
                    .table("payments")
                    .select("id")
                    .eq("account_id", delete_id)
                    .execute()
                    .data or []
                )

                if payments:
                    st.error(
                        "Esta factura tiene pagos registrados. "
                        "No se eliminó para conservar el historial."
                    )
                else:
                    (
                        st.session_state["db"]
                        .table("accounts")
                        .delete()
                        .eq("id", delete_id)
                        .execute()
                    )
                    flash("Factura eliminada.")
            except Exception as error:
                st.error(f"No se pudo eliminar la factura: {error}")


    if not dataframe.empty:
        excel_buffer = BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            dataframe.to_excel(writer, index=False, sheet_name="Cuentas")

        col1, col2 = st.columns(2)
        col1.download_button(
            "Descargar Excel",
            data=excel_buffer.getvalue(),
            file_name=f"cuentas_{kind}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        col2.download_button(
            "Descargar PDF",
            data=make_pdf(dataframe, "Reporte de cuentas"),
            file_name=f"cuentas_{kind}.pdf",
            mime="application/pdf",
        )

    st.divider()
    st.subheader("Registrar un pago o cobro")

    unpaid = [
        a for a in filtered
        if account_status(a, paid.get(str(a["id"]), 0))[0] > 0.005
    ]

    if unpaid:
        labels = {
            str(a["id"]): (
                f'{a["party"]} · Factura '
                f'{a.get("invoice_number") or "sin número"} · '
                f'Saldo ${account_status(a, paid.get(str(a["id"]), 0))[0]:,.2f}'
            )
            for a in unpaid
        }
        selected_id = st.selectbox(
            "Cuenta",
            list(labels),
            format_func=lambda value: labels[value],
            key=f"payment_account_{kind}",
        )
        selected_account = next(
            a for a in unpaid if str(a["id"]) == selected_id
        )
        balance = account_status(
            selected_account, paid.get(selected_id, 0)
        )[0]

        with st.form(f"payment_form_{kind}"):
            payment_amount = st.number_input(
                "Cantidad",
                min_value=0.01,
                max_value=balance,
                value=balance,
                step=1.0,
                format="%.2f",
            )
            payment_date = st.date_input("Fecha del pago", value=date.today())
            method = st.selectbox("Método de pago", PAYMENT_METHODS)
            reference = st.text_input("Referencia (opcional)")
            save_payment = st.form_submit_button("Guardar pago")

        if save_payment:
            try:
                st.session_state["db"].table("payments").insert({
                    "account_id": selected_id,
                    "amount": payment_amount,
                    "paid_at": payment_date.isoformat(),
                    "method": method,
                    "reference": reference.strip() or None,
                }).execute()
                flash("Pago guardado con su fecha y método.")
            except Exception:
                st.error("No se pudo guardar el pago.")

    st.subheader("Historial de pagos")
    if filtered:
        history_id = st.selectbox(
            "Ver pagos de esta cuenta",
            [str(a["id"]) for a in filtered],
            format_func=lambda value: next(
                f'{a["party"]} · Factura '
                f'{a.get("invoice_number") or "sin número"}'
                for a in filtered if str(a["id"]) == value
            ),
            key=f"history_account_{kind}",
        )
        history = (
            st.session_state["db"]
            .table("payments")
            .select("paid_at,method,reference,amount")
            .eq("account_id", history_id)
            .order("paid_at", desc=True)
            .execute()
            .data or []
        )
        if history:
            st.dataframe(
                pd.DataFrame(history),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("Esta cuenta todavía no tiene pagos registrados.")


def show_catalogs():
    st.header("Agencias, personal y proyectos")
    tab_agencies, tab_staff, tab_projects, tab_assignments = st.tabs(
        ["Agencias", "Personal", "Proyectos", "Asignaciones"]
    )

    with tab_agencies:
        with st.form("agency_form", clear_on_submit=True):
            agency_name = st.text_input("Nombre de la agencia")
            save_agency = st.form_submit_button("Agregar agencia")

        if save_agency:
            if not agency_name.strip():
                st.error("Escribe el nombre de la agencia.")
            else:
                try:
                    st.session_state["db"].table("agencies").insert({
                        "name": agency_name.strip(),
                    }).execute()
                    flash("Agencia agregada.")
                except Exception as error:
                    if is_duplicate_error(error):
                        st.error("Esa agencia ya está registrada.")
                    else:
                        st.error(f"No se pudo guardar la agencia: {error}")

        agencies = db_rows("agencies", "id,name")
        st.dataframe(
            pd.DataFrame(agencies),
            hide_index=True,
            use_container_width=True,
        )

    with tab_staff:
        with st.form("staff_form", clear_on_submit=True):
            first_name = st.text_input("Nombre")
            last_name = st.text_input("Apellido")
            cedula = st.text_input("Número de cédula")
            save_staff = st.form_submit_button("Agregar persona")

        if save_staff:
            normalized_cedula = re.sub(
                r"[^A-Za-z0-9]", "", cedula
            ).upper()

            if not first_name.strip() or not last_name.strip() or not normalized_cedula:
                st.error("Escribe nombre, apellido y cédula.")
            else:
                try:
                    st.session_state["db"].table("staff").insert({
                        "name": first_name.strip(),
                        "last_name": last_name.strip(),
                        "cedula": normalized_cedula,
                    }).execute()
                    flash("Persona agregada.")
                except Exception as error:
                    if is_duplicate_error(error):
                        st.error("Esa cédula ya está registrada.")
                    else:
                        st.error(f"No se pudo guardar la persona: {error}")

        staff = db_rows("staff", "id,name,last_name")
        staff_view = [{
            "Nombre": get_staff_full_name(person)
        } for person in staff]
        st.dataframe(
            pd.DataFrame(staff_view),
            hide_index=True,
            use_container_width=True,
        )
        st.caption("La cédula se usa para evitar duplicados y no se muestra en la lista.")

    with tab_projects:
        agencies = db_rows("agencies", "id,name")
        if not agencies:
            st.info("Agrega primero una agencia.")
        else:
            agency_names = {
                str(a["id"]): a["name"] for a in agencies
            }

            with st.form("project_form", clear_on_submit=True):
                agency_id = st.selectbox(
                    "Agencia del proyecto",
                    list(agency_names),
                    format_func=lambda value: agency_names[value],
                )
                project_name = st.text_input("Nombre del proyecto")
                save_project = st.form_submit_button("Agregar proyecto")

            if save_project:
                if not project_name.strip():
                    st.error("Escribe el nombre del proyecto.")
                else:
                    try:
                        st.session_state["db"].table("projects").insert({
                            "agency_id": agency_id,
                            "name": project_name.strip(),
                        }).execute()
                        flash("Proyecto agregado.")
                    except Exception as error:
                        if is_duplicate_error(error):
                            st.error("Ese proyecto ya existe para esa agencia.")
                        else:
                            st.error(f"No se pudo guardar el proyecto: {error}")

            projects = db_rows("projects")
            project_view = [{
                "Agencia": agency_names.get(str(project["agency_id"]), ""),
                "Proyecto": project["name"],
                "Activo": project["active"],
            } for project in projects]
            st.dataframe(
                pd.DataFrame(project_view),
                hide_index=True,
                use_container_width=True,
            )

    with tab_assignments:
        staff = db_rows("staff", "id,name,last_name")
        projects = db_rows("projects")

        if not staff or not projects:
            st.info("Agrega primero personal y proyectos.")
        else:
            staff_names = {
                str(person["id"]): get_staff_full_name(person)
                for person in staff
            }
            project_map = {
                str(project["id"]): project for project in projects
            }

            with st.form("assignment_form"):
                staff_id = st.selectbox(
                    "Persona",
                    list(staff_names),
                    format_func=lambda value: staff_names[value],
                )
                project_id = st.selectbox(
                    "Proyecto",
                    list(project_map),
                    format_func=lambda value: project_map[value]["name"],
                )
                charge = st.number_input(
                    "Cobro mensual a la agencia", min_value=0.0, step=10.0
                )
                pay = st.number_input(
                    "Pago mensual a la persona", min_value=0.0, step=10.0
                )
                charge_days = st.selectbox(
                    "Crédito para cobrar (días)", CREDIT_OPTIONS, index=1
                )
                pay_days = st.selectbox(
                    "Crédito para pagar (días)", CREDIT_OPTIONS, index=1
                )
                active = st.checkbox("Asignación activa", value=True)
                save_assignment = st.form_submit_button("Crear asignación")

            if save_assignment:
                try:
                    st.session_state["db"].table("assignments").insert({
                        "staff_id": staff_id,
                        "project_id": project_id,
                        "monthly_charge": charge,
                        "monthly_pay": pay,
                        "charge_days": charge_days,
                        "pay_days": pay_days,
                        "active": active,
                    }).execute()
                    flash("Asignación creada.")
                except Exception as error:
                    st.error(f"No se pudo crear la asignación: {error}")

            agencies = db_rows("agencies", "id,name")
            agency_names = {
                str(a["id"]): a["name"] for a in agencies
            }
            assignments = db_rows("assignments")
            assignment_view = []

            for assignment in assignments:
                project = project_map.get(
                    str(assignment["project_id"]), {}
                )
                assignment_view.append({
                    "Persona": staff_names.get(
                        str(assignment["staff_id"]), ""
                    ),
                    "Agencia": agency_names.get(
                        str(project.get("agency_id")), ""
                    ),
                    "Proyecto": project.get("name", ""),
                    "Cobro mensual": assignment["monthly_charge"],
                    "Pago mensual": assignment["monthly_pay"],
                    "Activa": assignment["active"],
                })

            st.dataframe(
                pd.DataFrame(assignment_view),
                hide_index=True,
                use_container_width=True,
            )


def register_account(role):

    st.header("Registrar cuenta")

    agencies = db_rows("agencies", "id,name")
    staff = db_rows("staff", "id,name,last_name")
    projects = db_rows("projects")

    agency_names = {str(a["id"]): a["name"] for a in agencies}
    staff_names = {
        str(person["id"]): get_staff_full_name(person)
        for person in staff
    }
    project_map = {str(project["id"]): project for project in projects}

    if role == "admin":
        kind_label = st.radio(
            "Tipo de cuenta",
            ["Por cobrar", "Por pagar"],
            horizontal=True,
            key="register_account_kind",
        )
        kind = "cobrar" if kind_label == "Por cobrar" else "pagar"
    else:
        kind = "pagar"
        st.info("Esta cuenta se registrará como una cuenta por pagar.")

    agency_id = None
    staff_id = None
    project_id = None
    party = ""
    person_mode = None

    if kind == "cobrar":
        # Crear agencia y proyecto aquí mismo, sin salir de Registrar cuenta.
        with st.expander("＋ Agregar proyecto o agencia aquí"):
            agency_modes = (
                ["Elegir agencia registrada", "Crear agencia nueva"]
                if agencies
                else ["Crear agencia nueva"]
            )

            with st.form("quick_agency_project_form", clear_on_submit=True):
                agency_mode = st.radio(
                    "Agencia",
                    agency_modes,
                    key="quick_agency_mode",
                )

                if agency_mode == "Elegir agencia registrada":
                    selected_agency_id = st.selectbox(
                        "Selecciona una agencia existente",
                        [str(a["id"]) for a in agencies],
                        format_func=lambda value: agency_names[value],
                    )
                    new_agency_name = ""
                else:
                    selected_agency_id = None
                    new_agency_name = st.text_input("Nombre de la agencia nueva")

                new_project_name = st.text_input("Nombre del proyecto")
                save_agency_project = st.form_submit_button(
                    "Guardar proyecto"
                )

            if save_agency_project:
                project_name = new_project_name.strip()

                if not project_name:
                    st.error("Escribe el nombre del proyecto.")
                elif (
                    agency_mode == "Crear agencia nueva"
                    and not new_agency_name.strip()
                ):
                    st.error("Escribe el nombre de la agencia.")
                else:
                    try:
                        if agency_mode == "Elegir agencia registrada":
                            new_agency_id = selected_agency_id
                        else:
                            agency_name = new_agency_name.strip()
                            existing_agency = next(
                                (
                                    agency for agency in agencies
                                    if agency["name"].strip().casefold()
                                    == agency_name.casefold()
                                ),
                                None,
                            )

                            if existing_agency:
                                new_agency_id = str(existing_agency["id"])
                            else:
                                result = (
                                    st.session_state["db"]
                                    .table("agencies")
                                    .insert({"name": agency_name})
                                    .select("id")
                                    .execute()
                                )
                                new_agency_id = str(result.data[0]["id"])

                        current_projects = (
                            st.session_state["db"]
                            .table("projects")
                            .select("id,name")
                            .eq("agency_id", new_agency_id)
                            .execute()
                            .data or []
                        )

                        project_exists = any(
                            project["name"].strip().casefold()
                            == project_name.casefold()
                            for project in current_projects
                        )

                        if not project_exists:
                            st.session_state["db"].table("projects").insert({
                                "agency_id": new_agency_id,
                                "name": project_name,
                            }).execute()

                        flash(
                            "Proyecto agregado a la agencia. "
                            "Ahora selecciónalo para registrar la cuenta."
                        )
                    except Exception as error:
                        st.error(f"No se pudo guardar: {error}")


        agencies = db_rows("agencies", "id,name")
        projects = db_rows("projects")
        agency_names = {str(a["id"]): a["name"] for a in agencies}
        project_map = {
            str(project["id"]): project for project in projects
        }

        if not agencies:
            st.info("Agrega una agencia usando el recuadro de arriba.")
            return

        agency_id = st.selectbox(
            "Agencia que debe pagar",
            list(agency_names),
            format_func=lambda value: agency_names[value],
            key="receivable_agency",
        )
        party = agency_names[agency_id]

        available_projects = {
            project_id: project
            for project_id, project in project_map.items()
            if str(project["agency_id"]) == agency_id
        }

        if not available_projects:
            st.warning(
                "Esta agencia todavía no tiene proyectos. "
                "Usa el recuadro «Agregar agencia y proyecto aquí»."
            )
            return

    else:
        person_mode = st.radio(
            "Persona",
            ["Elegir personal registrado", "Agregar persona nueva"],
            horizontal=True,
            key="register_payable_person_mode",
        )

        if person_mode == "Elegir personal registrado" and not staff:
            st.warning(
                "No hay personal registrado. "
                "Elige «Agregar persona nueva»."
            )
            return

        if not project_map:
            st.warning("Primero debe existir un proyecto para elegir.")
            return

    with st.form("manual_account_form"):
        if kind == "pagar":
            if person_mode == "Elegir personal registrado":
                staff_id = st.selectbox(
                    "Persona",
                    list(staff_names),
                    format_func=lambda value: staff_names[value],
                )
                party = staff_names[staff_id]
            else:
                first_name = st.text_input("Nombre")
                last_name = st.text_input("Apellido")
                cedula = st.text_input("Número de cédula")

            project_options = project_map
        else:
            project_options = available_projects

        project_id = st.selectbox(
            "Proyecto",
            list(project_options),
            format_func=lambda value: project_options[value]["name"],
        )

        invoice_number = st.text_input("Número de factura")
        amount = st.number_input(
            "Monto",
            min_value=0.01,
            step=10.0,
            format="%.2f",
        )
        invoice_date = st.date_input("Fecha de factura", value=date.today())
        credit_days = st.selectbox(
            "Tiempo de crédito (días)",
            CREDIT_OPTIONS,
            index=1,
        )
        due_date = invoice_date + timedelta(days=credit_days)
        st.caption(f"Fecha de vencimiento: {due_date.strftime('%d/%m/%Y')}")

        save_account = st.form_submit_button("Guardar cuenta")

    if not save_account:
        return

    if kind == "pagar" and person_mode == "Agregar persona nueva":
        normalized_cedula = re.sub(
            r"[^A-Za-z0-9]", "", cedula
        ).upper()

        if not first_name.strip() or not last_name.strip() or not normalized_cedula:
            st.error("Escribe nombre, apellido y cédula.")
            return

        try:
            result = (
                st.session_state["db"]
                .table("staff")
                .insert({
                    "name": first_name.strip(),
                    "last_name": last_name.strip(),
                    "cedula": normalized_cedula,
                })
                .select("id")
                .execute()
            )
            staff_id = result.data[0]["id"]
            party = f"{first_name.strip()} {last_name.strip()}"
        except Exception as error:
            if is_duplicate_error(error):
                st.error(
                    "Esa cédula ya está registrada. "
                    "Elige a la persona de la lista."
                )
            else:
                st.error(f"No se pudo guardar la persona: {error}")
            return

    project_id = str(project_id)
    project = project_map[project_id]
    agency_id = str(project["agency_id"])

    try:
        st.session_state["db"].table("accounts").insert({
            "kind": kind,
            "party": party,
            "agency_id": agency_id if kind == "cobrar" else None,
            "staff_id": staff_id if kind == "pagar" else None,
            "project_id": project_id,
            "invoice_number": invoice_number.strip() or None,
            "invoice_date": invoice_date.isoformat(),
            "credit_days": credit_days,
            "amount": amount,
        }).execute()

        flash("Cuenta guardada correctamente.")
    except Exception as error:
        st.error(f"No se pudo guardar la cuenta: {error}")


def generate_month():
    st.header("Generar mes")
    today = date.today()
    col1, col2, col3 = st.columns(3)

    year = col1.number_input(
        "Año", min_value=2020, max_value=2100, value=today.year
    )
    month = col2.selectbox(
        "Mes",
        list(range(1, 13)),
        index=today.month - 1,
        format_func=lambda value: MONTHS[value - 1],
    )
    invoice_date = col3.date_input("Fecha de factura", value=today)

    st.caption("Se crearán cuentas de las asignaciones activas.")
    if not st.button("Generar cuentas del mes"):
        return

    try:
        assignments = [
            assignment for assignment in db_rows("assignments")
            if assignment["active"]
        ]
        agencies = db_rows("agencies", "id,name")
        staff = db_rows("staff", "id,name,last_name")
        projects = db_rows("projects")

        agency_names = {str(a["id"]): a["name"] for a in agencies}
        staff_names = {
            str(person["id"]): get_staff_full_name(person)
            for person in staff
        }
        project_map = {
            str(project["id"]): project for project in projects
        }
        period = f"{int(year)}-{month:02d}"
        created = 0

        for assignment in assignments:
            project_id = str(assignment["project_id"])
            project = project_map.get(project_id)
            if not project:
                continue

            agency_id = str(project["agency_id"])
            staff_id = str(assignment["staff_id"])

            items = [
                (
                    "cobrar",
                    agency_names.get(agency_id, "Agencia"),
                    float(assignment["monthly_charge"]),
                    int(assignment["charge_days"]),
                ),
                (
                    "pagar",
                    staff_names.get(staff_id, "Personal"),
                    float(assignment["monthly_pay"]),
                    int(assignment["pay_days"]),
                ),
            ]

            for kind, party, amount, credit_days in items:
                if amount <= 0:
                    continue

                existing = (
                    st.session_state["db"]
                    .table("accounts")
                    .select("id")
                    .eq("kind", kind)
                    .eq("assignment_id", str(assignment["id"]))
                    .eq("period", period)
                    .execute()
                    .data or []
                )
                if existing:
                    continue

                st.session_state["db"].table("accounts").insert({
                    "kind": kind,
                    "party": party,
                    "agency_id": agency_id,
                    "staff_id": staff_id,
                    "project_id": project_id,
                    "assignment_id": str(assignment["id"]),
                    "period": period,
                    "invoice_date": invoice_date.isoformat(),
                    "credit_days": credit_days,
                    "amount": amount,
                }).execute()
                created += 1

        flash(
            f"Se generaron {created} cuentas. "
            "Las que ya existían no se duplicaron."
        )
    except Exception as error:
        st.error(f"No se pudo generar el mes: {error}")


if "db" not in st.session_state:
    login_screen()
    st.stop()

if st.sidebar.button("Cerrar sesión"):
    for key in ("db", "email", "role", "page"):
        st.session_state.pop(key, None)
    st.rerun()

role = st.session_state["role"]
st.sidebar.caption(f"Sesión: {st.session_state['email']}")

if "_flash" in st.session_state:
    st.success(st.session_state.pop("_flash"))

logo = find_logo()
if logo:
    st.sidebar.image(str(logo), width=150)

st.markdown("""
<div class="cover-heading">
  <h1>Cuentas por cobrar y por pagar</h1>
  <p>Agencias, proyectos, facturas y pagos en un solo lugar.</p>
</div>
""", unsafe_allow_html=True)

st.caption("Ingresos, gastos y facturas bajo control desde un único lugar.")


if role == "admin":
    menu = [
        ("📊 Resumen", "Resumen"),
        ("🧾 Por cobrar", "Por cobrar"),
        ("💸 Por pagar", "Por pagar"),
        ("➕ Registrar cuenta", "Registrar cuenta"),
        ("👥 Catálogos", "Catálogos"),
        ("📅 Generar mes", "Generar mes"),
("📥 Importar Excel", "Importar Excel"),

    ]
else:
    menu = [
        ("📊 Resumen", "Resumen"),
        ("💸 Por pagar", "Por pagar"),
        ("➕ Registrar cuenta", "Registrar cuenta"),
    ]

valid_pages = [name for _, name in menu]
if st.session_state.get("page") not in valid_pages:
    st.session_state["page"] = "Resumen"

st.sidebar.markdown("### Navegación")
menu_labels = [label for label, _ in menu]
label_to_page = {label: name for label, name in menu}
current_label = next(
    label for label, name in menu if name == st.session_state["page"]
)

selected_label = st.sidebar.radio(
    "Secciones",
    menu_labels,
    index=menu_labels.index(current_label),
    label_visibility="collapsed",
)

page = label_to_page[selected_label]
st.session_state["page"] = page

if page == "Resumen":
    show_summary(role)
elif page == "Por cobrar":
    show_accounts("cobrar")
elif page == "Por pagar":
    show_accounts("pagar")
elif page == "Registrar cuenta":
    register_account(role)
elif page == "Catálogos" and role == "admin":
    show_catalogs()
elif page == "Importar Excel" and role == "admin":
    import_excel_page()

elif page == "Generar mes" and role == "admin":
    generate_month()
