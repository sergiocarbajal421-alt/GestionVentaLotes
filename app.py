import streamlit as st
import pandas as pd
import sqlitecloud
from datetime import date
from dateutil.relativedelta import relativedelta

import streamlit as st
import plotly.express as px
import pandas as pd

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Gestión de Lotes", layout="wide")
hoy = date.today()


# --- CONEXIÓN A LA BD ---
def connection():
    return sqlitecloud.connect(
        "sqlitecloud://cg4uwk4rvk.g3.sqlite.cloud:8860/dbLotes.db?apikey=XWNiUbNaDRwC0kzEwUvgLN0YH8bshqybwpyVzob78vw"
    )


# --- CONSULTAR ---
# @st.cache_data
def consultar_bd(query):
    with connection() as con:
        cursor = con.execute(query)
        columnas = [desc[0] for desc in cursor.description]
        datos = cursor.fetchall()
        return pd.DataFrame(datos, columns=columnas)


# --- EJECUTAR SQL ---
def ejecutar_bd(query, params=()):
    with connection() as con:
        con.execute(query, params)
        con.commit()


# TITULO
st.markdown(
    """
<h1 style="
    text-align: center;
    color: #2c3e50;
    background-color: #f4f6f8;
    padding: 15px;
    border-radius: 12px;
    font-family: 'Segoe UI', sans-serif;
    box-shadow: 0px 2px 5px rgba(0,0,0,0.1);
">
📋 Gestión de Venta de Lotes
</h1>
""",
    unsafe_allow_html=True,
)


query_lote = """WITH monto_pagado AS (
    SELECT 
        Lote, 
        SUM(Monto) AS Monto_Pagado
    FROM Letras
    WHERE Estado = 'Pagado'
    GROUP BY Lote
),
monto_atrasado AS (
    SELECT 
        Lote, 
        SUM(Monto) AS Monto_Atrasado
    FROM Letras
    WHERE Estado = 'Pendiente' 
    AND DATE(Fecha_pago) < DATE('now')
    GROUP BY Lote
)
SELECT 
    lo.Lote,
    lo.Estado,
    lo.Area,
    COALESCE(lo.Precio, 0) AS Precio,
    COALESCE(lo.Inicial, 0) AS Inicial,     
    lo.Cliente,
    lo.Fecha_contrato,
    SUBSTR(lo.Lote, 1, INSTR(lo.Lote, '-') - 1) AS Manzana,
    
    -- Cálculo de montos
    COALESCE(lo.Precio, 0) - COALESCE(lo.Inicial, 0) AS Monto_Letras,
    COALESCE(mp.Monto_Pagado, 0) AS Monto_Pagado,
    COALESCE(
        (COALESCE(lo.Precio, 0) - COALESCE(lo.Inicial, 0)) - COALESCE(mp.Monto_Pagado, 0),
        0
    ) AS Monto_Pendiente,
    COALESCE(ma.Monto_Atrasado, 0) AS Monto_Atrasado

FROM Lotes lo
LEFT JOIN monto_pagado mp ON mp.Lote = lo.Lote
LEFT JOIN monto_atrasado ma ON ma.Lote = lo.Lote
    """

df_lotes = consultar_bd(query_lote)


lotes_disponibles = df_lotes[df_lotes.Estado == "Disponible"]["Lote"].tolist()
lotes_vendidos = df_lotes[df_lotes.Estado == "Vendido"]["Lote"].tolist()
clientes = df_lotes[~df_lotes.Cliente.isna()]["Cliente"].unique().tolist()


# 1️⃣ FORMULARIO EMERGENTE *********************************************************
@st.dialog("📝 Registrar nuevo lote")
def gestionar_venta():

    if not lotes_disponibles:
        st.warning("⚠️ No hay lotes disponibles.")
        return

    id_lote = st.selectbox("Lote disponible", lotes_disponibles)
    cliente = st.text_input("Cliente")
    fecha_contrato = st.date_input("Fecha de contrato")
    inicial = st.number_input("Monto inicial", min_value=0, step=1, format="%d")

    st.markdown("### Letras")
    col_a, col_b, col_c = st.columns([1, 1, 1])
    with col_a:
        letras = st.number_input("Cantidad de letras", min_value=0, step=1, format="%d")
    with col_b:
        monto = st.number_input("Monto mensual", min_value=0, step=1, format="%d")
    with col_c:
        cuota_final = st.number_input("Cuota final", min_value=0, step=1, format="%d")

    if letras and monto and cuota_final:
        st.info(
            f"💰 Precio total estimado: S/ {((letras - 1) * monto) + cuota_final + inicial:,.2f}"
        )

    if st.button("✅ Generar Venta", use_container_width=True):
        if (
            not cliente
            or not fecha_contrato
            or letras == 0
            or monto == 0
            or cuota_final == 0
        ):
            st.error("Por favor, completa todos los campos obligatorios.")
            return

        Precio = ((letras - 1) * monto) + cuota_final
        # Actualizar datos del lote
        ejecutar_bd(
            """
            UPDATE Lotes 
            SET Cliente = ?, Fecha_contrato = ?, Inicial = ?, Precio = ?, Estado = 'Vendido'
            WHERE Lote = ?
            """,
            (
                cliente,
                fecha_contrato.strftime("%Y-%m-%d"),
                inicial,
                (Precio + inicial),
                id_lote,
            ),
        )

        # 🔹 Crear todas las letras en una lista
        letras_data = []
        for i in range(1, letras + 1):
            fecha_pago = fecha_contrato + relativedelta(months=i)
            monto_letra = monto if i < letras else cuota_final
            letras_data.append(
                (id_lote, i, fecha_pago.strftime("%Y-%m-%d"), monto_letra)
            )

        # 🔹 Insertar todas las letras de golpe
        with connection() as con:
            con.executemany(
                """
                INSERT INTO Letras (Lote, Numero_Letra, Fecha_pago, Monto )
                VALUES (?, ?, ?, ?)
                """,
                letras_data,
            )
            con.commit()

        st.success(
            f"✅ Venta del lote {id_lote} registrada correctamente con {letras} letras."
        )
        st.rerun()


@st.dialog(
    "📝 Gestionar Abono"
)  # ********************************************************************
def editar_abono(id_lote_consulta):
    st.subheader(f"💵 Letras del lote {id_lote_consulta}")

    letras = consultar_bd(
        f"SELECT Numero_Letra FROM Letras WHERE Lote = '{id_lote_consulta}'"
    )["Numero_Letra"].tolist()

    if not letras:
        st.warning("⚠️ No hay letras registradas para este lote.")
        return

    letra_seleccion = st.selectbox("Selecciona una letra", letras)
    letra_df = consultar_bd(
        f"""
        SELECT Numero_Letra, Fecha_pago, Monto, Estado 
        FROM Letras 
        WHERE Lote = '{id_lote_consulta}' 
        AND Numero_Letra = {letra_seleccion}
        """
    )

    # Extraer datos
    letra_info = letra_df.iloc[0]
    fecha_pago = letra_info["Fecha_pago"]
    monto = letra_info["Monto"]
    estado = letra_info["Estado"]

    st.write(f"📅 Fecha de pago: **{fecha_pago}**")
    st.write(f"💰 Monto: **{monto}**")

    nuevo_estado = st.selectbox(
        "Estado de pago",
        ["Pendiente", "Pagado"],
        index=(0 if estado == "Pendiente" else 1),
    )

    if st.button("✅ Guardar cambios", use_container_width=True):
        ejecutar_bd(
            """
            UPDATE Letras 
            SET Estado = ?
            WHERE Lote = ? AND Numero_Letra = ?
            """,
            (nuevo_estado, id_lote_consulta, letra_seleccion),
        )
        st.success(
            f"✅ Letra {letra_seleccion} del lote {id_lote_consulta} actualizada correctamente."
        )
        st.rerun()


# MENSAJE DE ALERTA
atrasados = df_lotes[df_lotes["Monto_Atrasado"] > 0]
if not atrasados.empty:
    st.warning(
        f"⚠️ {len(atrasados)} lotes tienen pagos vencidos. Revisa la sección de letras."
    )
# --- PAGINA ---
col_a1, col_a_, col_a2 = st.columns([0.6, 0.02, 0.38])
with col_a1:
    # --- TABLA LOTES *******************************************************************
    st.markdown("<hr style='border:1px solid #ddd;'>", unsafe_allow_html=True)
    st.markdown("## 🏡 Lotes")

    col_b1, col_b2, col_b3, col_b_, col_b4 = st.columns([0.3, 0.1, 0.35, 0.05, 0.2])
    with col_b1:
        Estado_lote = st.multiselect("Estado", ["Vendido", "Disponible"])

    with col_b2:
        manzana = st.multiselect("Manzana", ["D", "E", "F"])
    with col_b3:
        cliente = st.multiselect("Clientes", clientes)

    with col_b4:
        st.write("")
        if st.button("➕ Gestionar Venta"):
            gestionar_venta()

    # --- CUADROS DE RESUMEN DE LOTES ---
    total_vendidos = len(df_lotes[df_lotes["Estado"] == "Vendido"])
    total_disponibles = len(df_lotes[df_lotes["Estado"] == "Disponible"])
    monto_total = df_lotes["Precio"].sum()
    monto_recaudado = df_lotes["Monto_Pagado"].sum()
    monto_pendiente = df_lotes["Monto_Pendiente"].sum()
    monto_atrasado = df_lotes["Monto_Atrasado"].sum()

    st.markdown("### 📊 Resumen General de Lotes")
    c1, c2, c3, c4, c5, c6 = st.columns([0.01, 0.01, 0.02, 0.02, 0.02, 0.02])
    c1.metric("✅ Vendidos", f"{total_vendidos}")
    c2.metric("📦 Disponibles", f"{total_disponibles}")

    c3.metric("💰 Venta", f"S/ {monto_total:.0f}")
    c4.metric("💰 Recaudado", f"S/ {monto_recaudado}")
    c5.metric("🧾 Pendiente", f"S/ {monto_pendiente}")
    c6.metric("⏰ Atrasado", f"S/ {monto_atrasado}")

    def resaltar_lotes(row):
        if row["Monto_Atrasado"] > 0:
            return ["background-color: #ffb3b3"] * len(row)
        elif row["Estado"] == "Vendido":
            return ["background-color: #ADD8E6"] * len(row)
        else:
            return [""] * len(row)

    mask = pd.Series(True, index=df_lotes.index)
    if Estado_lote:
        mask &= df_lotes["Estado"].isin(Estado_lote)
    if manzana:
        mask &= df_lotes["Manzana"].isin(manzana)
    if cliente:
        mask &= df_lotes["Cliente"].isin(cliente)

    df = df_lotes[mask]
    df = df.drop(columns=["Manzana"])

    df_estilado = df.style.apply(resaltar_lotes, axis=1).format(
        {
            "Precio": "S/ {:,.2f}",
            "Inicial": "S/ {:,.2f}",
            "Monto_Letras": "S/ {:,.2f}",
            "Monto_Pagado": "S/ {:,.2f}",
            "Monto_Atrasado": "S/ {:,.2f}",
            "Monto_Pendiente": "S/ {:,.2f}",
        }
    )
    st.dataframe(df_estilado, hide_index=True, use_container_width=True, height=500)


with col_a2:
    # --- TABLA LETRAS ***************************************************************
    st.markdown("<hr style='border:1px solid #ddd;'>", unsafe_allow_html=True)
    st.markdown("## 💰 Letras de Pago:")
    col_b1, col_b_, col_b2 = st.columns([0.45, 0.1, 0.45])
    with col_b1:
        id_lote_consulta = st.selectbox("Selecciona un Lote", lotes_vendidos)
        lote_consulta = df_lotes[df_lotes.Lote == id_lote_consulta]
    with col_b2:
        st.write("")
        if st.button("➕ Gestionar Abono"):
            editar_abono(id_lote_consulta)

    st.markdown(f"### Letras del  Lote {id_lote_consulta}")
    df_letras = consultar_bd(
        f"""
        SELECT 
        Numero_Letra,
        Fecha_pago,
        Monto,
        Estado
        FROM Letras 
        WHERE Lote = '{id_lote_consulta}'
        """
    )
    df_letras["Fecha_pago"] = pd.to_datetime(
        df_letras["Fecha_pago"], errors="coerce"
    ).dt.date

    # --- Definir función de estilo ---
    def resaltar_pagado(row):
        if row["Estado"] == "Pagado":
            return ["background-color: #C3E6CB"] * len(row)
        elif row["Estado"] == "Pendiente" and hoy > row["Fecha_pago"]:
            return ["background-color: #ffb3b3"] * len(row)
        else:
            return ["background-color: #f9f9f9"] * len(row)

    # --- Aplicar estilo ---

    # --- Calcular totales ---
    monto_letras = lote_consulta.Monto_Letras.sum()
    monto_pagado = lote_consulta.Monto_Pagado.sum()
    monto_vencido = lote_consulta.Monto_Atrasado.sum()
    monto_pendiente = lote_consulta.Monto_Pendiente.sum()

    # --- Mostrar resumen en 4 columnas ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📊 Total Letras", f"S/ {monto_letras}")
    col2.metric("💰 Monto Pagado", f"S/ {monto_pagado}")
    col3.metric("🧾 Pendiente", f"S/ {monto_pendiente}")
    col4.metric("⏰ Monto Vencido", f"S/ {monto_vencido}")

    df_estilado = df_letras.style.apply(resaltar_pagado, axis=1).format(
        {"Monto": "S/ {:,.2f}"}
    )  # Formato moneda
    st.dataframe(df_estilado, hide_index=True, use_container_width=True, height=500)


st.write("")
st.write("")
# --- TÍTULO PRINCIPAL CENTRADO ---***********************************************************
st.markdown(
    """
<h1 style="
    text-align: center;
    color: #2c3e50;
    background-color: #f4f6f8;
    padding: 15px;
    border-radius: 12px;
    font-family: 'Segoe UI', sans-serif;
    box-shadow: 0px 2px 5px rgba(0,0,0,0.1);
">
📈 Análisis Visual de Lotes y Pagos
</h1>
""",
    unsafe_allow_html=True,
)


# --- CREAR TABS ---
tab_lotes, tab_pagos = st.tabs(["🏡 Análisis de Lotes", "💵 Análisis de Pagos"])

# --- TAB LOTES ---
with tab_lotes:
    col1, col2 = st.columns(2)

    # --- Pie de Lotes por Estado ---
    with col1:
        fig_estado = px.pie(
            df_lotes,
            names="Estado",
            title="Distribución de Lotes por Estado",
            color_discrete_map={"Vendido": "#3498db", "Disponible": "#2ecc71"},
            hole=0.4,
        )
        fig_estado.update_traces(
            textinfo="percent+label",
            textfont_size=16,
            marker=dict(line=dict(color="#ffffff", width=2)),
        )
        fig_estado.update_layout(title={"x": 0.5})
        st.plotly_chart(fig_estado, use_container_width=True)

    # --- Recaudación por Cliente ---
    with col2:
        df_clientes = (
            df_lotes[df_lotes["Estado"] == "Vendido"]
            .groupby("Cliente", as_index=False)["Monto_Pagado"]
            .sum()
            .sort_values("Monto_Pagado", ascending=False)
        )
        fig_clientes = px.bar(
            df_clientes,
            x="Cliente",
            y="Monto_Pagado",
            text_auto=".2s",
            color="Monto_Pagado",
            color_continuous_scale="Blues",
            title="Recaudación Total por Cliente",
        )
        fig_clientes.update_layout(
            title={"x": 0.5}, xaxis_title=None, yaxis_title="Monto Pagado (S/)"
        )
        st.plotly_chart(fig_clientes, use_container_width=True)

# --- TAB PAGOS ---
with tab_pagos:
    # --- Comparativo de Montos Generales ---
    st.markdown("### 💰 Comparativo de Montos Generales")
    df_montos = pd.DataFrame(
        {
            "Tipo": ["Venta Total", "Pagado", "Pendiente", "Atrasado"],
            "Monto": [
                df_lotes["Precio"].sum(),
                df_lotes["Monto_Pagado"].sum(),
                df_lotes["Monto_Pendiente"].sum(),
                df_lotes["Monto_Atrasado"].sum(),
            ],
        }
    )
    fig_montos = px.bar(
        df_montos,
        x="Monto",
        y="Tipo",
        text="Monto",
        orientation="h",
        color="Tipo",
        color_discrete_sequence=["#3498db", "#2ecc71", "#f1c40f", "#e74c3c"],
        title="Estado General de Pagos",
    )
    fig_montos.update_traces(texttemplate="S/ %{x:,.0f}", textposition="outside")
    fig_montos.update_layout(
        title={"x": 0.5}, xaxis_title="Monto (S/)", yaxis_title=None
    )
    st.plotly_chart(fig_montos, use_container_width=True)

    # --- Evolución Mensual de Pagos ---
    st.markdown("### 📅 Evolución de Pagos Mensual")
    df_mes = consultar_bd(
        """
        SELECT strftime('%Y-%m', Fecha_pago) AS Mes, SUM(Monto) AS Total
        FROM Letras
        WHERE Estado = 'Pagado'
        GROUP BY Mes
        ORDER BY Mes
    """
    )
    fig_mes = px.line(
        df_mes,
        x="Mes",
        y="Total",
        markers=True,
        text="Total",
        title="Pagos Mensuales Recibidos",
    )
    fig_mes.update_traces(
        texttemplate="S/ %{y:,.0f}",
        textposition="top center",
        line=dict(color="#3498db", width=3),
    )
    fig_mes.update_layout(title={"x": 0.5})
    st.plotly_chart(fig_mes, use_container_width=True)

# --- FOOTER ---
st.markdown(
    """
<hr style='border: 1px solid #ddd; margin-top: 40px;'>
<div style='text-align:center; padding:10px 0; color:gray; font-size:14px;'>
    <p>📋 <b>Gestión de Venta de Lotes</b> | Desarrollado por <b>Sergio Carbajal</b></p>
    <p>
        © 2025 · Todos los derechos reservados · 
        <a href='mailto:SergioCarbajal421@gmail.com' style='color:gray; text-decoration:none;'>Correo</a> |
        <a href='https://www.linkedin.com/in/sergiocarbajal/' target='_blank' style='color:gray; text-decoration:none;'>LinkedIn</a> |
    </p>
</div>
""",
    unsafe_allow_html=True,
)
