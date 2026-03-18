import tempfile
from io import BytesIO
from pathlib import Path
import re
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from docx import Document

from filler_core import run_filler
from scraper_core import run_scraper


PROMPT_TEMPLATE_DIR = Path("prompt_templates")
TEMPLATE_DIR_DEFAULT = "sablony"

st.set_page_config(page_title="Warhammer Content App", layout="wide")
st.title("Warhammer Content App")

st.markdown("""
<style>
/* celý tab button */
button[data-baseweb="tab"] {
    min-height: 60px !important;
    padding: 10px 24px !important;
}

/* text uvnitř tabu */
button[data-baseweb="tab"] p {
    font-size: 28px !important;
    font-weight: 700 !important;
    margin: 0 !important;
}

/* aktivní tab */
button[data-baseweb="tab"][aria-selected="true"] {
    border-bottom: 4px solid #ff4b4b !important;
}
</style>
""", unsafe_allow_html=True)

if "generated_prompt_text" not in st.session_state:
    st.session_state["generated_prompt_text"] = ""

if "generated_prompt_type" not in st.session_state:
    st.session_state["generated_prompt_type"] = ""

if "filled_csv_bytes" not in st.session_state:
    st.session_state["filled_csv_bytes"] = None

if "create_csv_bytes" not in st.session_state:
    st.session_state["create_csv_bytes"] = None

if "fill_product_name" not in st.session_state:
    st.session_state["fill_product_name"] = ""

def save_uploaded_file_to_temp(uploaded_file, suffix: str) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        return tmp.name


def make_docx_bytes(text: str) -> bytes:
    doc = Document()

    for line in text.splitlines():
        doc.add_paragraph(line)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


tab1, tab2, tab3 = st.tabs(["Scraper", "Prompt", "Fill"])


with tab1:
    st.header("Scraper")
    st.subheader("Odkazy k produktům")
    st.caption("Do prvního sloupce vlož odkaz na produkt z Herního Prostoru, do druhého odpovídající odkaz z Games Workshopu. GW odkaz může zůstat prázdný.")

    links_df = pd.DataFrame([
        {"Herní Prostor URL": "", "Games Workshop URL": ""}
    ])

    edited_links_df = st.data_editor(
        links_df,
        num_rows="dynamic",
        use_container_width=True,
        key="scraper_links_editor",
    )

    template_dir = TEMPLATE_DIR_DEFAULT

    split_by_type = st.checkbox(
        "Split podle typu produktu",
        value=True,
        key="scraper_split_by_type",
    )

    verbose_mode = st.checkbox(
        "Verbose log",
        value=True,
        key="scraper_verbose_mode",
    )

    if st.button("Spustit scraper", key="scraper_run_button"):
        try:
            valid_links_df = edited_links_df.copy().fillna("")
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
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", encoding="utf-8-sig") as tmp_links:
                    valid_links_df.to_csv(tmp_links.name, sep=";", index=False)
                    temp_links_path = tmp_links.name

                temp_main_output = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
                temp_main_output.close()

                temp_split_dir = tempfile.mkdtemp(prefix="warhammer_split_")

                result = run_scraper(
                    input_links=temp_links_path,
                    output=temp_main_output.name,
                    tpl_dir=template_dir,
                    split_out_dir=temp_split_dir,
                    split_by_type=split_by_type,
                    verbose=verbose_mode,
                )

                st.success("Scraper proběhl úspěšně.")
                st.write("Počet produktů:", result["row_count"])

                main_csv_bytes = Path(result["output_csv"]).read_bytes()

                first_product_name = "shoptet_CREATE_CZ"
                if result.get("rows"):
                    first_product_name = result["rows"][0].get("name:cs", "") or "shoptet_CREATE_CZ"

                safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", first_product_name)
                file_name = f"{safe_name}_CREATE_CZ.csv"

                st.download_button(
                    label="Stáhnout hlavní CSV",
                    data=main_csv_bytes,
                    file_name=file_name,
                    mime="text/csv",
                    key="download_main_scraper_csv",
                )

                if result["split_files"]:
                    st.subheader("Vygenerované split CSV soubory")
                    for file_path in result["split_files"][:50]:
                        p = Path(file_path)
                        st.download_button(
                            label=f"Stáhnout {p.name}",
                            data=p.read_bytes(),
                            file_name=p.name,
                            mime="text/csv",
                            key=f"download_split_{p.name}",
                        )

        except Exception as e:
            st.error(f"Chyba při scrapování: {e}")


with tab2:
    st.header("Prompt")

    uploaded_split_csv = st.file_uploader(
        "Nahraj produktové split CSV  - soubor co jsi vygeneroval v předchozím kroku - v záložce Scraper",
        type=["csv"],
        key="prompt_uploaded_csv",
    )

    product_name = ""
    product_ean = ""

    if uploaded_split_csv is not None:
        try:
            df_preview = pd.read_csv(uploaded_split_csv, sep=";", dtype=str).fillna("")

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
        if uploaded_split_csv is None:
            st.warning("Nejdřív nahraj produktové split CSV.")
            return

        try:
            template_path = PROMPT_TEMPLATE_DIR / f"{prompt_type}.txt"

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
            key="generated_prompt_preview",
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
            height=50,
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
""",
    )

    if ai_output.strip():
        prompt_docx_bytes = make_docx_bytes(ai_output)

        st.download_button(
            label="Stáhnout vystup_prompt.docx",
            data=prompt_docx_bytes,
            file_name="vystup_prompt.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="download_prompt_docx",
        )


with tab3:
    st.header("Fill")

    template_type = st.selectbox(
        "Typ šablony",
        ["miniatures", "books", "warscroll", "dice", "upgrades"],
        key="fill_template_type",
    )

    uploaded_product_csv = st.file_uploader(
        "Nahraj produktové split CSV - první soubor co jsi vygeneroval v záložce Scraper",
        type=["csv"],
        key="fill_uploaded_csv",
    )

    uploaded_prompt_docx = st.file_uploader(
        "Nahraj vystup_prompt.docx - soubor co jsi vygeneroval v záložce Prompt",
        type=["docx"],
        key="fill_uploaded_prompt_docx",
    )

    template_dir = TEMPLATE_DIR_DEFAULT

    target_ean = st.text_input(
        "Cílový EAN (volitelné)",
        value="",
        key="fill_target_ean",
    )

    target_product_name = st.text_input(
        "Cílový název produktu (volitelné)",
        value="",
        key="fill_target_product_name",
    )

    debug_mode = st.checkbox("Debug výpis", value=True, key="fill_debug_mode")

    if uploaded_product_csv is not None:
        try:
            df_preview = pd.read_csv(uploaded_product_csv, sep=";", dtype=str).fillna("")
            if not df_preview.empty:
                name_col = "name:cs" if "name:cs" in df_preview.columns else "name"
                product_name_preview = df_preview.iloc[0].get(name_col, "")
                product_ean_preview = df_preview.iloc[0].get("ean", "")
                st.info(f"Produkt: {product_name_preview}")
                st.write(f"EAN: {product_ean_preview}")
        except Exception as e:
            st.warning(f"Nepodařilo se načíst CSV: {e}")

    if st.button("Spustit fill", key="fill_run_button"):
        try:
            if uploaded_product_csv is None:
                st.error("Nahraj produktové split CSV.")
            elif uploaded_prompt_docx is None:
                st.error("Nahraj vystup_prompt.docx.")
            else:
                temp_csv_path = save_uploaded_file_to_temp(uploaded_product_csv, ".csv")
                temp_prompt_docx_path = save_uploaded_file_to_temp(uploaded_prompt_docx, ".docx")

                temp_filled_output = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
                temp_filled_output.close()

                temp_create_output = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
                temp_create_output.close()

                result = run_filler(
                    template_type=template_type,
                    csv_path=temp_csv_path,
                    template_dir=template_dir,
                    prompt_output_docx_path=temp_prompt_docx_path,
                    output_csv_path=temp_filled_output.name,
                    output_create_csv_path=temp_create_output.name,
                    target_product_name=target_product_name or None,
                    target_ean=target_ean or None,
                    debug=debug_mode,
                )

                st.success("Fill proběhl úspěšně.")
                st.write("Produkt:", result["product_name"])

                filled_csv_bytes = Path(result["output_csv"]).read_bytes()
                create_csv_bytes = Path(result["output_create_csv"]).read_bytes()

                st.session_state["filled_csv_bytes"] = filled_csv_bytes
                st.session_state["create_csv_bytes"] = create_csv_bytes
                st.session_state["fill_product_name"] = result["product_name"]

                st.success("Výstupy jsou připravené ke stažení níže.")

        except Exception as e:
            st.exception(e)

    if st.session_state["filled_csv_bytes"] and st.session_state["create_csv_bytes"]:
        st.subheader("Výstupy ke stažení")

        if st.session_state["fill_product_name"]:
            st.write("Produkt:", st.session_state["fill_product_name"])

        st.download_button(
            label="Stáhnout FILLED CSV",
            data=st.session_state["filled_csv_bytes"],
            file_name="0_FILLED.csv",
            mime="text/csv",
            key="download_filled_csv_persistent",
        )

        st.download_button(
            label="Stáhnout CREATE CSV",
            data=st.session_state["create_csv_bytes"],
            file_name="0_CREATE.csv",
            mime="text/csv",
            key="download_create_csv_persistent",
        )

        if st.button("Vymazat výstupy", key="clear_fill_outputs"):
            st.session_state["filled_csv_bytes"] = None
            st.session_state["create_csv_bytes"] = None
            st.session_state["fill_product_name"] = ""
            st.rerun()

       