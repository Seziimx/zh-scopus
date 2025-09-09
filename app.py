import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
from datetime import datetime
from utils_pdf import dataframe_to_pdf_bytes

st.set_page_config(
    page_title="Zh Scopus — Жубанов",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Header with logo and title
col_logo, col_title = st.columns([1, 4])
with col_logo:
    st.image("assets/logo.png", use_container_width=True)
with col_title:
    st.title("Zh Scopus — портал публикаций")
    st.caption("Университет Жубанова • Аналитика Scopus")

@st.cache_data
def load_data(path: str, sheet: str = "ARTICLE") -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet, engine="openpyxl")
    # Normalize columns
    rename_map = {
        "Автор (ы)": "authors_raw",
        "Author full names": "authors_full",
        "Название документа": "title",
        "Год": "year",
        "Название источника": "source",
        "Цитирования": "cited_by",
        "DOI": "doi",
        "Ссылка": "url",
        "ISSN": "issn",
        "Квартиль": "quartile",
        "Процентиль 2024": "percentile_2024",
    }
    df = df.rename(columns=rename_map)
    # Ensure types
    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    if "cited_by" in df.columns:
        df["cited_by"] = pd.to_numeric(df["cited_by"], errors="coerce").fillna(0).astype(int)
    if "percentile_2024" in df.columns:
        df["percentile_2024"] = pd.to_numeric(df["percentile_2024"], errors="coerce")
    # For search: lowercase helpers
    for col in ["authors_raw", "authors_full", "title", "source"]:
        if col in df.columns:
            df[f"_{col}_lc"] = df[col].astype(str).str.lower()
    return df

df = load_data("data/zhubanov_scopus_issn.xlsx")

# ============ Sidebar Filters ============
st.sidebar.header("Фильтры")

years = df["year"].dropna().unique()
years = np.sort(years[~pd.isna(years)])
if len(years) == 0:
    st.error("В данных нет валидных значений года.")
    st.stop()

min_year, max_year = int(years.min()), int(years.max())
preset = st.sidebar.radio("Быстрые интервалы", ["Все годы", "Последние 5 лет", "Последние 10 лет"], index=0)

if preset == "Все годы":
    year_range = st.sidebar.slider("Диапазон лет", min_value=min_year, max_value=max_year,
                                   value=(min_year, max_year), step=1)
elif preset == "Последние 5 лет":
    year_range = (max(max_year - 4, min_year), max_year)
    st.sidebar.info(f"Выбрано: {year_range[0]}–{year_range[1]}")
else:
    year_range = (max(max_year - 9, min_year), max_year)
    st.sidebar.info(f"Выбрано: {year_range[0]}–{year_range[1]}")

quartiles_all = ["Q1", "Q2", "Q3", "Q4"]
selected_quartiles = st.sidebar.multiselect("Квартиль", quartiles_all, default=quartiles_all)

percentile_range = st.sidebar.slider("Процентиль 2024", min_value=0, max_value=100,
                                     value=(0, 100), step=1)

search_query = st.sidebar.text_input("Поиск (автор/название/источник)", value="").strip().lower()

# ============ Filtering Logic ============
mask = pd.Series(True, index=df.index)

mask &= df["year"].between(year_range[0], year_range[1])

if "quartile" in df.columns:
    mask &= df["quartile"].astype(str).isin(selected_quartiles)

if "percentile_2024" in df.columns:
    p = df["percentile_2024"].fillna(-1)
    mask &= (p >= percentile_range[0]) & (p <= percentile_range[1])

if search_query:
    any_field = (
        df.get("_authors_raw_lc", pd.Series("", index=df.index)).str.contains(search_query, na=False) |
        df.get("_authors_full_lc", pd.Series("", index=df.index)).str.contains(search_query, na=False) |
        df.get("_title_lc", pd.Series("", index=df.index)).str.contains(search_query, na=False) |
        df.get("_source_lc", pd.Series("", index=df.index)).str.contains(search_query, na=False)
    )
    mask &= any_field

filtered = df[mask].copy()

# ============ Sorting ============
sort_column = st.sidebar.selectbox(
    "Сортировать по",
    options=["year", "cited_by", "percentile_2024", "quartile", "title"],
    format_func=lambda x: {
        "year": "Год",
        "cited_by": "Цитирования",
        "percentile_2024": "Процентиль 2024",
        "quartile": "Квартиль",
        "title": "Название"
    }.get(x, x),
    index=0
)
sort_order = st.sidebar.radio("Порядок", ["По возрастанию", "По убыванию"], index=1)
ascending = (sort_order == "По возрастанию")
if sort_column in filtered.columns:
    filtered = filtered.sort_values(by=sort_column, ascending=ascending)

# ============ KPI Cards ============
k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("Публикаций", f"{len(filtered):,}".replace(",", " "))
with k2:
    st.metric("Суммарные цитирования", f"{filtered['cited_by'].sum():,}".replace(",", " "))
with k3:
    avg_pct = filtered["percentile_2024"].mean() if "percentile_2024" in filtered else np.nan
    st.metric("Средний процентиль (2024)", f"{avg_pct:.1f}" if pd.notna(avg_pct) else "—")
with k4:
    top_q = filtered["quartile"].value_counts().head(1)
    st.metric("Чаще всего квартиль", top_q.index[0] if len(top_q) > 0 else "—")

# ============ Tabs ============
tab_table, tab_cards, tab_sources, tab_authors = st.tabs(["📊 Таблица", "📚 Scopus-вид", "🏛 Топ источники", "👨‍💻 Топ авторы"])

with tab_table:
    st.subheader("Результаты фильтрации")
    show_cols = ["authors_full", "title", "year", "source", "quartile", "percentile_2024", "cited_by", "doi", "url", "issn"]
    show_cols = [c for c in show_cols if c in filtered.columns]
    st.dataframe(filtered[show_cols], use_container_width=True, height=500)

    # Export buttons
    st.markdown("### Экспорт")
    csv_bytes = filtered[show_cols].to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ Скачать CSV", csv_bytes, file_name="zh_scopus_export.csv", mime="text/csv")

    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        filtered[show_cols].to_excel(writer, index=False, sheet_name="Export")
    st.download_button("⬇️ Скачать Excel", excel_buffer.getvalue(), file_name="zh_scopus_export.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    try:
        pdf_bytes = dataframe_to_pdf_bytes(filtered[show_cols], title="Zh Scopus — Отчёт (фильтр)")
        st.download_button("⬇️ Скачать PDF (бета)", pdf_bytes, file_name="zh_scopus_report.pdf", mime="application/pdf")
    except Exception as e:
        st.warning(f"PDF экспорт недоступен: {e}")

with tab_cards:
    st.subheader("Результаты (карточки в стиле Scopus)")
    for _, row in filtered.iterrows():
        with st.container():
            st.markdown(f"### {row.get('title', 'Без названия')}")
            st.markdown(f"**Авторы:** {row.get('authors_full', '—')}")
            st.markdown(f"**Источник:** {row.get('source', '—')}")
            st.markdown(
                f"**Год:** {row.get('year', '—')} | "
                f"**Квартиль:** {row.get('quartile', '—')} | "
                f"**Процентиль:** {row.get('percentile_2024', '—')}"
            )
            st.markdown(f"**Цитирования:** {row.get('cited_by', 0)}")
            if pd.notna(row.get("doi", None)):
                st.markdown(f"[DOI]({row['doi']})")
            elif pd.notna(row.get("url", None)):
                st.markdown(f"[Ссылка]({row['url']})")
            st.markdown("---")

with tab_sources:
    st.subheader("Топ 10 источников по числу публикаций")
    if "source" in filtered.columns:
        top_sources = (filtered.groupby("source")
                       .agg(pub_count=("title", "count"), cites=("cited_by", "sum"))
                       .sort_values("pub_count", ascending=False)
                       .head(10))
        st.bar_chart(top_sources["pub_count"])
        st.dataframe(top_sources, use_container_width=True)
    else:
        st.info("Поле 'Название источника' отсутствует.")

with tab_authors:
    st.subheader("Топ 10 авторов по числу публикаций")
    if "authors_full" in filtered.columns:
        exploded = (filtered.assign(_authors=filtered["authors_full"].astype(str).str.split(";"))
                    .explode("_authors"))
        exploded["_authors"] = exploded["_authors"].str.strip()
        top_authors = (exploded[exploded["_authors"] != ""]
                       .groupby("_authors").agg(pub_count=("title", "count"),
                                                cites=("cited_by", "sum"))
                       .sort_values("pub_count", ascending=False).head(10))
        st.bar_chart(top_authors["pub_count"])
        st.dataframe(top_authors, use_container_width=True)
    else:
        st.info("Поле 'Author full names' отсутствует.")

st.caption("© Zh Scopus / Университет Жубанова")
