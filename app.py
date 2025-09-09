import streamlit as st  
import pandas as pd
import numpy as np
from io import BytesIO
from utils_pdf import dataframe_to_pdf_bytes

st.set_page_config(
    page_title="Zh Scopus — Жубанов",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)
# Включаем перенос строк в dataframe
st.markdown("""
    <style>
    .stDataFrame td {
        white-space: normal !important;
        word-wrap: break-word !important;
        max-width: 300px; /* можно менять ширину ячеек */
    }
    </style>
""", unsafe_allow_html=True)

# Header
col_logo, col_title = st.columns([1, 4])
with col_logo:
    st.image("assets/logo.png", use_container_width=True)
with col_title:
    st.title("Zh Scopus — портал публикаций")
    st.caption("Университет Жубанова • Аналитика Scopus")

# ================= DATA ==================
@st.cache_data
def load_data(path: str, sheet: str = "ARTICLE") -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet, engine="openpyxl")
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

    # types
    df["year"] = pd.to_numeric(df.get("year"), errors="coerce").astype("Int64")
    df["cited_by"] = pd.to_numeric(df.get("cited_by"), errors="coerce").fillna(0).astype(int)
    df["percentile_2024"] = pd.to_numeric(df.get("percentile_2024"), errors="coerce")

    # DOI link
    df["doi_link"] = df.get("doi").apply(
        lambda x: f"https://doi.org/{x.strip()}" if pd.notna(x) and str(x).strip() else None
    )

    # lowercase helpers
    for col in ["authors_full", "title", "source"]:
        if col in df.columns:
            df[f"_{col}_lc"] = df[col].astype(str).str.lower()

    return df

df = load_data("data/zhubanov_scopus_issn.xlsx")

# ================= SIDEBAR ==================
st.sidebar.header("Фильтры")

# Годы
years = df["year"].dropna().unique()
years = np.sort(years)
min_year, max_year = int(years.min()), int(years.max())

preset = st.sidebar.radio("Интервал", ["Все годы", "Последние 5 лет", "Последние 10 лет"], index=0)
if preset == "Все годы":
    year_range = st.sidebar.slider("Диапазон лет", min_value=min_year, max_value=max_year,
                                   value=(min_year, max_year), step=1)
elif preset == "Последние 5 лет":
    year_range = (max(max_year - 4, min_year), max_year)
else:
    year_range = (max(max_year - 9, min_year), max_year)

# Источники
st.sidebar.markdown("### Фильтр по источникам")
source_counts = df["source"].value_counts()
selected_sources = st.sidebar.multiselect(
    "Выберите источники",
    options=source_counts.index.tolist(),
    format_func=lambda x: f"{x} ({source_counts[x]})"
)

# Авторы
st.sidebar.markdown("### Фильтр по авторам")
author_counts = (df["authors_full"].astype(str)
                 .str.split(";").explode().str.strip().value_counts())
selected_authors = st.sidebar.multiselect(
    "Выберите авторов",
    options=author_counts.index.tolist(),
    format_func=lambda x: f"{x} ({author_counts[x]})"
)

# Квартиль и процентиль
quartiles_all = ["Q1", "Q2", "Q3", "Q4"]
selected_quartiles = st.sidebar.multiselect("Квартиль", quartiles_all, default=quartiles_all)
percentile_range = st.sidebar.slider("Процентиль 2024", 0, 100, (0, 100), step=1)

# Поиск
search_query = st.sidebar.text_input("Поиск (автор/название/источник)").strip().lower()

# Сортировка
sort_option = st.sidebar.selectbox(
    "Сортировка",
    [
        "Дата (новые → старые)",
        "Дата (старые → новые)",
        "Цитирования (много → мало)",
        "Цитирования (мало → много)",
        "Автор (A–Z)",
        "Автор (Z–A)",
        "Источник (A–Z)",
        "Источник (Z–A)",
    ],
    index=0
)

# ================= FILTERING ==================
mask = df["year"].between(year_range[0], year_range[1])

if selected_sources:
    mask &= df["source"].isin(selected_sources)

if selected_authors:
    mask &= df["authors_full"].astype(str).apply(
        lambda x: any(a in x for a in selected_authors)
    )

mask &= df["quartile"].astype(str).isin(selected_quartiles)
mask &= df["percentile_2024"].fillna(-1).between(percentile_range[0], percentile_range[1])

if search_query:
    mask &= (
        df["_authors_full_lc"].str.contains(search_query, na=False) |
        df["_title_lc"].str.contains(search_query, na=False) |
        df["_source_lc"].str.contains(search_query, na=False)
    )

filtered = df[mask].copy()

# Сортировка
if sort_option == "Дата (новые → старые)":
    filtered = filtered.sort_values("year", ascending=False)
elif sort_option == "Дата (старые → новые)":
    filtered = filtered.sort_values("year", ascending=True)
elif sort_option == "Цитирования (много → мало)":
    filtered = filtered.sort_values("cited_by", ascending=False)
elif sort_option == "Цитирования (мало → много)":
    filtered = filtered.sort_values("cited_by", ascending=True)
elif sort_option == "Автор (A–Z)":
    filtered = filtered.sort_values("authors_full", ascending=True)
elif sort_option == "Автор (Z–A)":
    filtered = filtered.sort_values("authors_full", ascending=False)
elif sort_option == "Источник (A–Z)":
    filtered = filtered.sort_values("source", ascending=True)
elif sort_option == "Источник (Z–A)":
    filtered = filtered.sort_values("source", ascending=False)

# ================= KPI ==================
k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("Публикаций", f"{len(filtered):,}".replace(",", " "))
with k2:
    st.metric("Суммарные цитирования", f"{filtered['cited_by'].sum():,}".replace(",", " "))
with k3:
    avg_pct = filtered["percentile_2024"].mean()
    st.metric("Средний процентиль (2024)", f"{avg_pct:.1f}" if pd.notna(avg_pct) else "—")
with k4:
    top_q = filtered["quartile"].value_counts().head(1)
    st.metric("Чаще всего квартиль", top_q.index[0] if len(top_q) > 0 else "—")

# ================= TABS ==================
tab_table, tab_cards, tab_sources, tab_authors = st.tabs(
    ["📊 Таблица", "📚 Scopus-вид", "🏛 Топ источники", "👨‍💻 Топ авторы"]
)

with tab_table:
    st.subheader("Результаты фильтрации")

    filtered_display = filtered.copy().reset_index(drop=True)
    filtered_display.index = filtered_display.index + 1
    filtered_display.insert(0, "№", filtered_display.index)

    # Авторы: заменяем ";" на перенос строки
    if "authors_raw" in filtered_display.columns:
        filtered_display["authors_fmt"] = (
            filtered_display["authors_raw"]
            .astype(str)
            .str.replace(";", "\n")
        )
    else:
        filtered_display["authors_fmt"] = "—"

    show_cols = ["№", "authors_fmt", "title", "year", "source",
                 "quartile", "percentile_2024", "cited_by",
                 "doi_link", "url", "issn"]
    show_cols = [c for c in show_cols if c in filtered_display.columns]

    st.dataframe(filtered_display[show_cols], use_container_width=True, height=500)






    # Экспорт
    st.markdown("### Экспорт")

    export_cols = [c for c in show_cols if c in filtered_display.columns]

    csv_bytes = filtered_display[export_cols].to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ Скачать CSV", csv_bytes, file_name="zh_scopus_export.csv", mime="text/csv")

    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        filtered_display[export_cols].to_excel(writer, index=False, sheet_name="Export")
    st.download_button("⬇️ Скачать Excel", excel_buffer.getvalue(), file_name="zh_scopus_export.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    try:
        pdf_bytes = dataframe_to_pdf_bytes(filtered_display[export_cols], title="Zh Scopus — Отчёт (фильтр)")
        st.download_button("⬇️ Скачать PDF (бета)", pdf_bytes, file_name="zh_scopus_report.pdf", mime="application/pdf")
    except Exception as e:
        st.warning(f"PDF экспорт недоступен: {e}")

with tab_cards:
    st.subheader("Публикации в стиле Scopus")

    for idx, row in enumerate(filtered.itertuples(), start=1):
        with st.container():
            st.markdown(f"### {idx}. {getattr(row, 'title', 'Без названия')}")
            
            # Авторы из "authors_raw", через перенос строки
            authors_fmt = str(getattr(row, "authors_raw", "—")).replace(";", "\n")
            st.markdown(f"**Авторы:**\n{authors_fmt}")
            
            st.markdown(f"**Источник:** {getattr(row, 'source', '—')}")
            st.markdown(
                f"**Год:** {getattr(row, 'year', '—')} | "
                f"**Квартиль:** {getattr(row, 'quartile', '—')} | "
                f"**Процентиль:** {getattr(row, 'percentile_2024', '—')}"
            )
            st.markdown(f"**Цитирования:** {getattr(row, 'cited_by', 0)}")

            # 🔹 Ссылки
            links = []
            if pd.notna(getattr(row, "doi_link", None)):
                links.append(f"[DOI]({row.doi_link})")
            if pd.notna(getattr(row, "url", None)):
                links.append(f"[Scopus ссылка]({row.url})")
            if links:
                st.markdown(" | ".join(links))

            st.markdown("---")



with tab_sources:
    st.subheader("Топ источников")
    top_sources = (filtered.groupby("source")
                   .agg(pub_count=("title", "count"), cites=("cited_by", "sum"))
                   .sort_values("pub_count", ascending=False)
                   .head(20))
    st.bar_chart(top_sources["pub_count"])
    st.dataframe(top_sources, use_container_width=True)

with tab_authors:
    st.subheader("Топ авторов")
    exploded = (filtered.assign(_authors=filtered["authors_full"].astype(str).str.split(";"))
                .explode("_authors"))
    exploded["_authors"] = exploded["_authors"].str.strip()
    top_authors = (exploded[exploded["_authors"] != ""]
                   .groupby("_authors").agg(pub_count=("title", "count"),
                                            cites=("cited_by", "sum"))
                   .sort_values("pub_count", ascending=False).head(20))
    st.bar_chart(top_authors["pub_count"])
    st.dataframe(top_authors, use_container_width=True)

st.caption("© Zh Scopus / Университет Жубанова")
