import tempfile
import streamlit.components.v1 as components
import pandas as pd
import streamlit as st
from pathlib import Path
from filler_core import run_filler
from scraper_core import run_scraper

BASE_SPLIT_DIR = "/Users/janholubik/Downloads/shoptet_split"
PROMPT_TEMPLATE_DIR = "/Users/janholubik/Downloads/XML/warhammer_streamlit_app/prompt_templates"

st.set_page_config(page_title="Warhammer Content App", layout="wide")

st.title("Warhammer Content App")

if "generated_prompt_text" not in st.session_state:
    st.session_state["generated_prompt_text"] = ""

if "generated_prompt_type" not in st.session_state:
    st.session_state["generated_prompt_type"] = ""

tab1, tab2, tab3 = st.tabs(["Scraper", "Prompt", "Fill"])

with tab1:
    st.header("Scraper")

    st.subheader("Odkazy k produktům")
    st.caption("Do prvního sloupce vlož odkaz na produkt z Herního Prostoru, do druhého odpovídající odkaz z Games Workshopu. GW odkaz může zůstat prázdný.")

    links_df = pd.DataFrame(
        [
            {
                "Herní Prostor URL": "",
                "Games Workshop URL": ""
            }
        ]
    )

    edited_links_df = st.data_editor(
        links_df,
        num_rows="dynamic",
        use_container_width=True,
        key="scraper_links_editor"
    )

    output_csv_path = st.text_input(
        "Cesta pro výstupní hlavní CSV",
        value="/Users/janholubik/Downloads/shoptet_CREATE_CZ.csv",
        key="scraper_output_csv"
    )

    template_dir = st.text_input(
        "Cesta ke složce se šablonami",
        value="/Users/janholubik/Downloads/XML/XML_plastic/sablony",
        key="scraper_template_dir"
    )

    split_out_dir = st.text_input(
        "Složka pro split CSV",
        value="/Users/janholubik/Downloads/shoptet_split/",
        key="scraper_split_out_dir"
    )

    split_by_type = st.checkbox(
        "Split podle typu produktu",
        value=True,
        key="scraper_split_by_type"
    )

    verbose_mode = st.checkbox(
        "Verbose log",
        value=True,
        key="scraper_verbose_mode"
    )

    if st.button("Spustit scraper", key="scraper_run_button"):
        try:
            valid_links_df = edited_links_df.copy()
            valid_links_df = valid_links_df.fillna("")

            valid_links_df = valid_links_df.rename(columns={
                "Herní Prostor URL": "hp_url",
                "Games Workshop URL": "gw_url",
            })

            valid_links_df["hp_url"] = valid_links_df["hp_url"].astype(str).str.strip()
            valid_links_df["gw_url"] = valid_links_df["gw_url"].astype(str).str.strip()

            valid_links_df = valid_links_df[valid_links_df["hp_url"] != ""]

            if valid_links_df.empty:
                st.error("Zadej alespoň jeden odkaz do sloupce Herní Prostor URL.")
            else:
                with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8-sig") as tmp:
                    temp_csv_path = tmp.name
                    valid_links_df.to_csv(tmp.name, sep=";", index=False)

                result = run_scraper(
                    input_links=temp_csv_path,
                    output=output_csv_path,
                    tpl_dir=template_dir,
                    split_out_dir=split_out_dir,
                    split_by_type=split_by_type,
                    verbose=verbose_mode,
                )

                st.success("Scraper proběhl úspěšně.")
                st.write("Hlavní CSV:", result["output_csv"])
                st.write("Počet produktů:", result["row_count"])

                if result["split_dir"]:
                    st.write("Split složka:", result["split_dir"])

                if result["split_files"]:
                    st.subheader("Vygenerované split CSV soubory")
                    for f in result["split_files"][:30]:
                        st.write(f)

        except Exception as e:
            st.error(f"Chyba při scrapování: {e}")

with tab2:
    st.header("Prompt")

    split_dir = st.text_input(
        "Složka se split CSV produkty",
        value=str(Path(BASE_SPLIT_DIR) / "miniatures"),
        key="prompt_split_dir"
    )

    csv_options = []
    if split_dir:
        split_path = Path(split_dir).expanduser()
        if split_path.exists() and split_path.is_dir():
            csv_options = sorted([str(p) for p in split_path.glob("*.csv")])

    selected_csv = st.selectbox(
        "Vyber produktové CSV",
        options=csv_options if csv_options else [""],
        key="prompt_selected_csv"
    )

    product_name = ""
    product_ean = ""

    if selected_csv:
        try:
            df_preview = pd.read_csv(selected_csv, sep=";", dtype=str).fillna("")

            if not df_preview.empty:
                name_col = "name:cs" if "name:cs" in df_preview.columns else "name"

                product_name = df_preview.iloc[0].get(name_col, "")
                product_ean = df_preview.iloc[0].get("ean", "")

                st.info(f"Produkt: {product_name}")
                st.write(f"EAN: {product_ean}")

        except Exception as e:
            st.warning(f"Nepodařilo se načíst CSV: {e}")

    st.subheader("Prompt šablony")

    col1, col2, col3, col4, col5 = st.columns(5)

    def generate_prompt(prompt_type: str) -> None:
        if not selected_csv:
            st.warning("Nejdřív vyber produktové CSV.")
            return

        try:
            template_path = Path(PROMPT_TEMPLATE_DIR) / f"{prompt_type}.txt"

            if not template_path.exists():
                st.error(f"Šablona nenalezena: {template_path}")
                return

            template_text = template_path.read_text(encoding="utf-8")

            prompt_text = f"""{template_text}

--------------------------------------------------
PRODUKT
{product_name}

EAN
{product_ean}
--------------------------------------------------
"""

            st.session_state["generated_prompt_text"] = prompt_text
            st.session_state["generated_prompt_type"] = prompt_type

        except Exception as e:
            st.error(f"Chyba při načítání promptu: {e}")

    with col1:
        if st.button("Miniatures", key="prompt_btn_miniatures"):
            generate_prompt("miniatures")

    with col2:
        if st.button("Books", key="prompt_btn_books"):
            generate_prompt("books")

    with col3:
        if st.button("Dice", key="prompt_btn_dice"):
            generate_prompt("dice")

    with col4:
        if st.button("Warscroll", key="prompt_btn_warscroll"):
            generate_prompt("warscroll")

    with col5:
        if st.button("Upgrades", key="prompt_btn_upgrades"):
            generate_prompt("upgrades")

    if st.session_state["generated_prompt_text"]:
        prompt_text = st.session_state["generated_prompt_text"]

        st.text_area(
            f"Vygenerovaný prompt ({st.session_state['generated_prompt_type']})",
            value=prompt_text,
            height=350,
            key="generated_prompt_preview"
        )

        copy_text = (
            prompt_text
            .replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace("'", "\\'")
        )

        components.html(
            f"""
            <button onclick="navigator.clipboard.writeText('{copy_text}')" 
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
            height=50
        )

    st.subheader("⬇ VLOŽ SEM AI OUTPUT")

    ai_output = st.text_area(
        "AI Output",
        height=400,
        key="prompt_ai_output",
        placeholder="""
[LANG=cs]
nazev_produktu:
...

[LANG=en]
...

[LANG=sk]
...
"""
    )

    output_prompt_path = st.text_input(
        "Kam uložit vystup_prompt.docx",
        value="/Users/janholubik/Downloads/shoptet_split/vystup_prompt.docx",
        key="prompt_output_path"
    )

    if st.button("Uložit prompt output", key="prompt_save_button"):
        try:
            from docx import Document

            doc = Document()
            doc.add_paragraph(ai_output)
            doc.save(output_prompt_path)

            st.success(f"Prompt uložen do: {output_prompt_path}")

        except Exception as e:
            st.error(f"Chyba při ukládání: {e}")

with tab3:
    st.header("Fill")

    template_type = st.selectbox(
        "Typ šablony",
        ["miniatures", "books", "warscroll", "dice", "upgrades"],
        key="fill_template_type"
    )

    type_to_folder = {
        "miniatures": "miniatures",
        "books": "book",
        "warscroll": "warscroll",
        "dice": "dice",
        "upgrades": "upgrades",
    }

    default_split_dir = str(Path(BASE_SPLIT_DIR) / type_to_folder[template_type])

    split_dir = st.text_input(
        "Složka se split CSV produkty",
        value=default_split_dir,
        key="fill_split_dir"
    )

    csv_options = []
    if split_dir:
        split_path = Path(split_dir).expanduser()
        if split_path.exists() and split_path.is_dir():
            csv_options = sorted([str(p) for p in split_path.glob("*.csv")])

    selected_csv = st.selectbox(
        "Vyber produktové CSV",
        options=csv_options if csv_options else [""],
        key="fill_selected_csv"
    )

    csv_path = selected_csv

    if csv_path:
        try:
            df_preview = pd.read_csv(csv_path, sep=";", dtype=str).fillna("")

            if not df_preview.empty:
                name_col = "name:cs" if "name:cs" in df_preview.columns else "name"

                product_name_preview = df_preview.iloc[0].get(name_col, "")
                product_ean_preview = df_preview.iloc[0].get("ean", "")

                st.info(f"Produkt: {product_name_preview}")
                st.write(f"EAN: {product_ean_preview}")

        except Exception as e:
            st.warning(f"Nepodařilo se načíst CSV: {e}")

    prompt_docx_path = st.text_input(
        "Cesta k vystup_prompt.docx",
        value="/Users/janholubik/Downloads/shoptet_split/vystup_prompt.docx",
        key="fill_prompt_docx_path"
    )

    template_dir = st.text_input(
        "Cesta ke složce se šablonami",
        value="/Users/janholubik/Downloads/XML/XML_plastic/sablony",
        key="fill_template_dir"
    )

    output_filled_csv = st.text_input(
        "Cesta pro výstupní FILLED CSV",
        value="/Users/janholubik/Downloads/0_FILLED.csv",
        key="fill_output_filled_csv"
    )

    output_create_csv = st.text_input(
        "Cesta pro výstupní CREATE CSV",
        value="/Users/janholubik/Downloads/0_CREATE.csv",
        key="fill_output_create_csv"
    )

    target_ean = st.text_input(
        "Cílový EAN (volitelné)",
        value="",
        key="fill_target_ean"
    )

    target_product_name = st.text_input(
        "Cílový název produktu (volitelné)",
        value="",
        key="fill_target_product_name"
    )

    debug_mode = st.checkbox("Debug výpis", value=True, key="fill_debug_mode")

    if st.button("Spustit fill", key="fill_run_button"):
        try:
            result = run_filler(
                template_type=template_type,
                csv_path=csv_path,
                template_dir=template_dir,
                prompt_output_docx_path=prompt_docx_path,
                output_csv_path=output_filled_csv,
                output_create_csv_path=output_create_csv,
                target_product_name=target_product_name or None,
                target_ean=target_ean or None,
                debug=debug_mode,
            )

            st.success("Fill proběhl úspěšně.")
            st.write("Produkt:", result["product_name"])
            st.write("FILLED CSV:", result["output_csv"])
            st.write("CREATE CSV:", result["output_create_csv"])

        except Exception as e:
            st.error(f"Chyba při fill: {e}")