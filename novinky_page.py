# novinky_page.py
from __future__ import annotations

import streamlit as st

from gw_novinky_core import build_novinka_from_gw


def render_novinky_page():
    st.title("Warhammer – Novinky")

    st.markdown("""
    <div style="
        background:#0f172a;
        padding:16px 20px;
        border-radius:12px;
        border:1px solid #1e293b;
        margin-bottom:16px;
    ">
    <b style="font-size:16px;">🆕 GW Only novinky</b><br>
    <span style="color:#94a3b8;">
    Tato sekce slouží pro nové produkty, které ještě nemají stránku na HP a existují pouze na Games Workshopu.<br><br>
    Vložíš jen GW URL a aplikace automaticky vytáhne:
    <ul>
        <li>název produktu</li>
        <li>systém</li>
        <li>frakci</li>
        <li>doporučenou cenu</li>
        <li>obrázky</li>
        <li>kód z obrázků</li>
    </ul>
    Potom si stáhneš <b>SOURCE</b> a <b>CREATE</b> CSV a pokračuješ přes Prompt + Fill.
    </span>
    </div>
    """, unsafe_allow_html=True)

    gw_url = st.text_input(
        "GW URL produktu",
        placeholder="https://www.warhammer.com/en-US/shop/Imperial-Guard-Catachan-Heavy-Weapon-Squad?queryID=...",
        key="novinky_gw_url",
    )

    sale_price_mode = st.radio(
        "Prodejní cena",
        [
            "Použít stejnou jako standardPrice",
            "Zadat ručně",
        ],
        key="novinky_price_mode",
    )

    manual_price = None
    if sale_price_mode == "Zadat ručně":
        manual_price = st.number_input(
            "Moje prodejní cena (s DPH, CZK)",
            min_value=0.0,
            step=1.0,
            key="novinky_manual_price",
        )

    keep_360 = st.checkbox("Zahrnout 360 obrázky", value=False, key="novinky_keep_360")
    only_first_image = st.checkbox("Pouze první obrázek", value=False, key="novinky_only_first_image")

    if st.button("Načíst z GW", key="novinky_load_btn"):
        if not gw_url.strip():
            st.warning("Vlož GW URL.")
        else:
            try:
                result = build_novinka_from_gw(
                    gw_url=gw_url.strip(),
                    sale_price_czk=manual_price if sale_price_mode == "Zadat ručně" else None,
                    keep_360=keep_360,
                    only_first_image=only_first_image,
                )
                st.session_state["novinky_result"] = result
                st.success("Novinka byla načtena.")
            except Exception as e:
                st.error(f"Chyba při načítání GW produktu: {e}")

    result = st.session_state.get("novinky_result")

    if result:
        st.subheader("Kontrola dat")

        st.write(f"**Raw název z GW:** {result['raw_name']}")
        st.write(f"**Finální název:** {result['final_name']}")
        st.write(f"**Systém:** {result['system'] or '-'}")
        st.write(f"**Frakce:** {result['faction'] or '-'}")
        st.write(f"**Typ produktu:** {result['product_type'] or '-'}")
        st.write(f"**Code:** {result['code'] or '-'}")
        st.write(f"**Standardní cena:** {result['standard_price'] if result['standard_price'] is not None else '-'} Kč")
        st.write(f"**Prodejní cena:** {result['price'] if result['price'] is not None else '-'} Kč")
        st.write(f"**Počet obrázků:** {len(result['images'])}")

        with st.expander("Feature texty z GW"):
            for item in result["features"]:
                st.write(f"- {item}")

        with st.expander("Obrázky"):
            for i, img in enumerate(result["images"], start=1):
                st.write(f"**{i}.** {img}")

        create_csv_bytes = result["create_df"].to_csv(
            sep=";",
            index=False,
            encoding="utf-8-sig"
        ).encode("utf-8-sig")

        source_csv_bytes = result["source_df"].to_csv(
            sep=";",
            index=False,
            encoding="utf-8-sig"
        ).encode("utf-8-sig")

        col1, col2 = st.columns(2)

        with col1:
            st.download_button(
                "Stáhnout NOVINKA_CREATE.csv",
                data=create_csv_bytes,
                file_name="NOVINKA_CREATE.csv",
                mime="text/csv",
                key="novinky_download_create",
            )

        with col2:
            st.download_button(
                "Stáhnout NOVINKA_SOURCE.csv",
                data=source_csv_bytes,
                file_name="NOVINKA_SOURCE.csv",
                mime="text/csv",
                key="novinky_download_source",
            )