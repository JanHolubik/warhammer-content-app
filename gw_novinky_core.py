from typing import Dict, Optional
from gw_browser_client import fetch_gw_product_browser


def build_novinka_from_gw(
    gw_url: str,
    custom_code: str = "",
    sale_price_czk: Optional[float] = None,
    keep_360: bool = False,
    only_first_image: bool = False,
    vat: float = 21.0,
    warranty: str = "2 roky",
    supplier: str = "Games Workshop",
    stock: str = "0",
    percent_vat: str = "21",
    oss_tax_rate_cz: str = "",
    availability_in_stock: str = "Skladem",
    availability_out_of_stock: str = "Na dotaz",
    product_visibility: str = "hidden",
    google_category_id_in_feed: str = "1246",
    heureka_category_id: str = "1475",
    zbozi_category_id: str = "412",
    google_category_id: str = "1246",
) -> Dict[str, object]:
    gw_data = fetch_gw_product_browser(
        gw_url,
        keep_360=keep_360,
        debug=False,
    )

    html = str(gw_data.get("html", "") or "")
    final_url = str(gw_data.get("final_url", gw_url) or gw_url)
    raw_name = str(gw_data.get("name", "") or "")
    images = list(gw_data.get("images", []) or [])
    gw_price = gw_data.get("price_value")
    gw_currency = gw_data.get("price_currency")
    features = list(gw_data.get("features", []) or [])

    soup = BeautifulSoup(html, "lxml") if html else None

    if not raw_name and soup is not None:
        raw_name = gw_extract_name(soup, final_url)

    if not features and soup is not None:
        features = gw_extract_features(soup)

    if gw_price is None or gw_currency is None:
        gw_price, gw_currency = gw_extract_price(html)

    images = keep_real_product_images(images)
    images = dedupe_by_filename(uniq_keep_order(images))
    images = images[:20]

    if only_first_image and images:
        images = [images[0]]

    image_code = extract_code_from_images(images)

    print("----- KONTROLA DAT -----")
    print("Raw název z GW:", raw_name)
    print("Finální URL:", final_url)
    print("Počet obrázků:", len(images))
    print("------------------------")

    system = gw_detect_system(raw_name, features, final_url)
    faction = gw_detect_faction(raw_name, features, final_url)
    product_type = detect_product_type(raw_name, system, faction, features)

    final_name = build_final_name(system, faction, raw_name)

    standard_price = (
        round(gw_price * FX_RATES[gw_currency], 2)
        if (gw_price is not None and gw_currency in FX_RATES)
        else None
    )

    price = sale_price_czk if sale_price_czk is not None else standard_price
    price_wo_vat = price_without_vat(price, vat) if price is not None else None

    if custom_code.strip():
        code = custom_code.strip()
        external_code = image_code
    else:
        code = image_code
        external_code = image_code

    ean = ""

    xml_feed_name = make_xml_feed_name_from_name(final_name)
    seo_title = make_seo_title_from_name(final_name)

    create_row: Dict[str, str] = {c: "" for c in CREATE_COLUMNS}
    source_row: Dict[str, str] = {c: "" for c in SOURCE_COLUMNS}

    create_row.update({
        "code": code,
        "pairCode": "",
        "name": final_name,
        "price": f"{price:.2f}".replace(".", ",") if price is not None else "",
        "description": "",
    })

    source_row.update({
        "code": code,
        "pairCode": "",
        "name": final_name,
        "ean": ean,
        "externalCode": external_code,
        "price": f"{price:.2f}".replace(".", ",") if price is not None else "",
        "priceWithoutVat": f"{price_wo_vat:.2f}".replace(".", ",") if price_wo_vat is not None else "",
        "standardPrice": f"{standard_price:.2f}".replace(".", ",") if standard_price is not None else "",
        "categoryText": "Warhammer",
        "warranty": warranty,
        "supplier": supplier,
        "googleCategoryIdInFeed": google_category_id_in_feed,
        "heurekaCategoryId": heureka_category_id,
        "zboziCategoryId": zbozi_category_id,
        "googleCategoryId": google_category_id,
        "stock": stock,
        "percentVat": percent_vat,
        "ossTaxRate:CZ": oss_tax_rate_cz,
        "availabilityInStock": availability_in_stock,
        "availabilityOutOfStock": availability_out_of_stock,
        "productVisibility": product_visibility,
        "xmlFeedName": xml_feed_name,
        "seoTitle": seo_title,
        "system": system,
        "faction": faction,
        "productType": product_type,
        "hp_url": "",
        "gw_url": final_url,
    })

    if images:
        create_row["image"] = images[0]
        source_row["image"] = images[0]

        for i in range(1, min(20, len(images))):
            col = f"image{i + 1}"
            create_row[col] = images[i]
            source_row[col] = images[i]

    create_df = pd.DataFrame([create_row], columns=CREATE_COLUMNS)
    source_df = pd.DataFrame([source_row], columns=SOURCE_COLUMNS)

    return {
        "raw_name": raw_name,
        "final_name": final_name,
        "system": system,
        "faction": faction,
        "product_type": product_type,
        "code": code,
        "standard_price": standard_price,
        "price": price,
        "features": features,
        "images": images,
        "create_df": create_df,
        "source_df": source_df,
    }