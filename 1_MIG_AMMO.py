from io import BytesIO
import pandas as pd
import streamlit as st

from mig_core import (
    create_mig_card_row,
    build_mig_prompt,
    make_docx_bytes,
    apply_mig_output_to_csv,
)

st.set_page_config(page_title="MIG / AMMO Content App", layout="wide")
st.title("MIG / AMMO Content App")

if "mig_generated_prompt_text" not in st.session_state:
    st.session_state["mig_generated_prompt_text"] = ""

if "mig_generated_prompt_type" not in st.session_state:
    st.session_state["mig_generated_prompt_type"] = ""

if "mig_export_csv_bytes" not in st.session_state:
    st.session_state["mig_export_csv_bytes"] = None

tab1, tab2 = st.tabs(["Barvy", "Štětce / Příslušenství"])


def mig_ui(product_type_label: str, prompt_type: str, item_type: str):
    subtab1, subtab2 = st.tabs(["Nová karta", "Prompt + Fill"])

    with subtab1:
        st.subheader(f"{product_type_label} – nová karta")

        name = st.text_input("Název produktu", key=f"{prompt_type}_name")
        code = st.text_input("Code", key=f"{prompt_type}_code")
        ean = st.text_input("EAN", key=f"{prompt_type}_ean")
        price = st.number_input("Cena", min_value=0.0, step=1.0, key=f"{prompt_type}_price")
        description = st.text_area("Základní popis", key=f"{prompt_type}_desc")

        if st.button("Vytvořit CREATE CSV", key=f"{prompt_type}_create_btn"):
            if not name or not code:
                st.warning("Vyplň alespoň název produktu a code.")
            else:
                df = create_mig_card_row(
                    name=name,
                    code=code,
                    ean=ean,
                    price=price,
                    product_type=item_type,
                    description=description,
                )
                csv_bytes = df.to_csv(index=False).encode("utf-8-sig")

                st.download_button(
                    "Stáhnout CREATE CSV",
                    data=csv_bytes,
                    file_name=f"{code}_CREATE.csv",
                    mime="text/csv",
                    key=f"{prompt_type}_download_create",
                )

    with subtab2:
        st.subheader(f"{product_type_label} – prompt + fill")

        uploaded_csv = st.file_uploader(
            "Nahraj CSV produktu",
            type=["csv"],
            key=f"{prompt_type}_uploaded_csv",
        )

        df = None
        row_index = None
        product_name = ""
        product_ean = ""

        if uploaded_csv is not None:
            try:
                df = pd.read_csv(uploaded_csv, dtype=str).fillna("")
                if "name" in df.columns:
                    product_options = [f"{i} | {row['name']}" for i, row in df.iterrows()]
                    selected = st.selectbox("Vyber produkt", product_options, key=f"{prompt_type}_select_product")
                    row_index = int(selected.split("|")[0].strip())
                    product_name = df.iloc[row_index].get("name", "")
                    product_ean = df.iloc[row_index].get("ean", "")

                    st.info(f"Produkt: {product_name}")
                    st.write(f"EAN: {product_ean}")
            except Exception as e:
                st.error(f"Nepodařilo se načíst CSV: {e}")

        if st.button("Vygenerovat prompt", key=f"{prompt_type}_generate_prompt"):
            if not product_name:
                st.warning("Nejdřív nahraj CSV a vyber produkt.")
            else:
                st.session_state["mig_generated_prompt_text"] = build_mig_prompt(
                    prompt_type=prompt_type,
                    product_name=product_name,
                    product_ean=product_ean,
                )
                st.session_state["mig_generated_prompt_type"] = prompt_type

        if st.session_state["mig_generated_prompt_text"]:
            st.text_area(
                "Vygenerovaný prompt",
                value=st.session_state["mig_generated_prompt_text"],
                height=320,
                key=f"{prompt_type}_prompt_preview",
            )

        ai_output = st.text_area(
            "AI Output",
            height=420,
            key=f"{prompt_type}_ai_output",
            placeholder="""[LANG=cs]
nazev_produktu:
...

[LANG=en]
...

[LANG=sk]
...""",
        )

        if ai_output.strip():
            prompt_docx_bytes = make_docx_bytes(ai_output)
            st.download_button(
                "Stáhnout vystup_prompt.docx",
                data=prompt_docx_bytes,
                file_name="vystup_prompt.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key=f"{prompt_type}_download_docx",
            )

        if st.button("Zpracovat do CSV", key=f"{prompt_type}_fill_btn"):
            if df is None or row_index is None:
                st.warning("Nejdřív nahraj CSV a vyber produkt.")
            elif not ai_output.strip():
                st.warning("Vlož AI output.")
            else:
                try:
                    out_df = apply_mig_output_to_csv(
                        df=df,
                        row_index=row_index,
                        ai_output=ai_output,
                        template_kind=prompt_type,
                    )
                    st.session_state["mig_export_csv_bytes"] = out_df.to_csv(index=False).encode("utf-8-sig")
                    st.success("CSV připraveno ke stažení.")
                except Exception as e:
                    st.error(f"Chyba při zpracování: {e}")

        if st.session_state["mig_export_csv_bytes"] is not None:
            st.download_button(
                "Stáhnout FILLED CSV",
                data=st.session_state["mig_export_csv_bytes"],
                file_name=f"{prompt_type}_FILLED.csv",
                mime="text/csv",
                key=f"{prompt_type}_download_filled",
            )


with tab1:
    mig_ui(
        product_type_label="MIG Barvy",
        prompt_type="mig_paints",
        item_type="mig_paint",
    )

with tab2:
    mig_ui(
        product_type_label="MIG Štětce / Příslušenství",
        prompt_type="mig_tools",
        item_type="mig_tool",
    )