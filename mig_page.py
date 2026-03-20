import json
import pandas as pd
import streamlit as st

from mig_core import (
    create_mig_card_row,
    build_mig_prompt,
    make_docx_bytes,
    apply_mig_output_to_csv,
)


def render_mig_page():
    st.title("MIG AMMO")

    if "mig_generated_prompt_text" not in st.session_state:
        st.session_state["mig_generated_prompt_text"] = ""

    if "mig_generated_prompt_type" not in st.session_state:
        st.session_state["mig_generated_prompt_type"] = ""

    if "mig_export_csv_bytes" not in st.session_state:
        st.session_state["mig_export_csv_bytes"] = None

    tab1, tab2 = st.tabs(["Barvy", "Štětce / Příslušenství"])

    with tab1:
        render_mig_section(
            product_type_label="MIG Barvy",
            prompt_type="mig_paints",
            item_type="mig_paint",
        )

    with tab2:
        render_mig_section(
            product_type_label="MIG Štětce / Příslušenství",
            prompt_type="mig_tools",
            item_type="mig_tool",
        )


def render_mig_section(product_type_label: str, prompt_type: str, item_type: str):
    subtab1, subtab2 = st.tabs(["Nová karta", "Prompt + Fill"])

    with subtab1:
        st.subheader(f"{product_type_label} – vytvoření nové karty")

        st.markdown("""
        <div style="
            background:#0f172a;
            padding:16px 20px;
            border-radius:12px;
            border:1px solid #1e293b;
            margin-bottom:16px;
        ">
        <b style="font-size:16px;">🧩 Nová karta – MIG</b><br>
        <span style="color:#94a3b8;">
        Tato sekce vytvoří základní produkt pro Shoptet (CREATE CSV).<br><br>

        Vyplňuješ pouze:
        <ul>
        <li>Název produktu</li>
        <li>Code (nebo kód výrobce)</li>
        <li>EAN (pokud existuje)</li>
        <li>Prodejní cenu</li>
        <li>Doporučenou cenu výrobce</li>
        </ul>

        ➡️ Automaticky se dopočítá:
        <ul>
        <li>Cena bez DPH (priceWithoutVat)</li>
        <li>Dostupnost produktu</li>
        <li>Výrobce</li>
        </ul>

        <b style="color:#38bdf8;">⚡ Tip:</b> CREATE slouží jen pro založení produktu – popisy řeš v záložce níže přes AI.
        </span>
        </div>
        """, unsafe_allow_html=True)

        name = st.text_input("Název produktu", key=f"{prompt_type}_name")
        code = st.text_input("Code – Kód produktu - vždycky", key=f"{prompt_type}_code")
        ean = st.text_input("EAN kód - ze záložky sklad", key=f"{prompt_type}_ean")
        price = st.number_input(
            "Naše prodejní cena (s DPH)",
            min_value=0.0,
            step=1.0,
            key=f"{prompt_type}_price"
        )
        standard_price = st.number_input(
            "Doporučená cena výrobce",
            min_value=0.0,
            step=1.0,
            key=f"{prompt_type}_standard_price"
        )
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
                    standard_price=standard_price,
                    product_type=item_type,
                    description=description,
                )

                csv_bytes = df.to_csv(index=False, sep=";").encode("utf-8-sig")

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
                df = pd.read_csv(uploaded_csv, sep=";", dtype=str).fillna("")

                name_col = None
                if "name" in df.columns:
                    name_col = "name"
                elif "name:cs" in df.columns:
                    name_col = "name:cs"

                if name_col:
                    product_options = [f"{i} | {row.get(name_col, '')}" for i, row in df.iterrows()]
                    selected = st.selectbox(
                        "Vyber produkt",
                        product_options,
                        key=f"{prompt_type}_select_product"
                    )

                    row_index = int(selected.split("|")[0].strip())
                    product_name = df.iloc[row_index].get(name_col, "")
                    product_ean = df.iloc[row_index].get("ean", "")

                    st.info(f"Produkt: {product_name}")
                    st.write(f"EAN: {product_ean}")
                else:
                    st.error(f"CSV neobsahuje sloupec 'name' ani 'name:cs'. Nalezené sloupce: {list(df.columns)}")

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

        if st.session_state["mig_generated_prompt_text"] and st.session_state["mig_generated_prompt_type"] == prompt_type:
            prompt_text = st.session_state["mig_generated_prompt_text"]

            st.text_area(
                "Vygenerovaný prompt",
                value=prompt_text,
                height=320,
                key=f"{prompt_type}_prompt_preview",
            )

            copy_text = json.dumps(prompt_text)

            st.components.v1.html(
                f"""
                <button onclick='navigator.clipboard.writeText({copy_text})'
                style="
                    background-color:#1f77b4;
                    color:white;
                    padding:8px 16px;
                    border:none;
                    border-radius:6px;
                    cursor:pointer;
                    font-size:14px;
                    margin-top:8px;
                ">
                📋 Kopírovat prompt
                </button>
                """,
                height=50,
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

        st.markdown("### Odkazy na obrázky")

        img1_src = st.text_input(
            "Odkaz na obrázek 1",
            key=f"{prompt_type}_img1_src"
        )
        img2_src = st.text_input(
            "Odkaz na obrázek 2",
            key=f"{prompt_type}_img2_src"
        )
        img3_src = st.text_input(
            "Odkaz na obrázek 3",
            key=f"{prompt_type}_img3_src"
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
                    extra_values = {
                        "img1_src": img1_src.strip(),
                        "img2_src": img2_src.strip(),
                        "img3_src": img3_src.strip(),
                    }
                    extra_values = {k: v for k, v in extra_values.items() if v}

                    out_df = apply_mig_output_to_csv(
                        df=df,
                        row_index=row_index,
                        ai_output=ai_output,
                        template_kind=prompt_type,
                        extra_values=extra_values,
                    )
                    st.session_state["mig_export_csv_bytes"] = out_df.to_csv(
                        index=False,
                        sep=";"
                    ).encode("utf-8-sig")
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