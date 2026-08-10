"""
app.py
Sistem Cleaning Dataset Peserta (Register & Login) dengan Human-in-the-Loop.
Jalankan: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import io

from cleaning import clean_register_dataset, clean_login_dataset
from matching import find_internal_duplicates, match_login_to_register

st.set_page_config(page_title="Cleaning Dataset Peserta", layout="wide")

# ---------------------------------------------------------------------------
# SESSION STATE INIT
# ---------------------------------------------------------------------------
DEFAULTS = {
    'df_register': None,
    'df_login': None,
    'dup_register': None,
    'dup_login': None,
    'review_match': None,
    'dropped_register_idx': set(),
    'dropped_login_idx': set(),
    'processed': False,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


def reset_all():
    for k, v in DEFAULTS.items():
        st.session_state[k] = v


# ---------------------------------------------------------------------------
# SIDEBAR — UPLOAD & RUN
# ---------------------------------------------------------------------------
st.sidebar.header("⚙️ Input Dataset")

file_register = st.sidebar.file_uploader("Upload CSV Register", type=['csv'])
file_login = st.sidebar.file_uploader("Upload CSV Login", type=['csv'])

sep = st.sidebar.selectbox("Delimiter CSV", [';', ','], index=0)

threshold = st.sidebar.slider(
    "Threshold Similarity untuk Flag Duplikat (%)", min_value=70, max_value=100, value=90
)

col_run, col_reset = st.sidebar.columns(2)
run_btn = col_run.button("🚀 Jalankan Cleaning & Matching", use_container_width=True)
if col_reset.button("🔄 Reset", use_container_width=True):
    reset_all()
    st.rerun()

if run_btn:
    if file_register is None or file_login is None:
        st.sidebar.error("Upload kedua file (register & login) dulu.")
    else:
        raw_register = pd.read_csv(file_register, sep=sep, dtype=str)
        raw_login = pd.read_csv(file_login, sep=sep, dtype=str)

        with st.spinner("Membersihkan dataset register..."):
            df_register = clean_register_dataset(raw_register)

        with st.spinner("Membersihkan dataset login..."):
            df_login = clean_login_dataset(raw_login)

        with st.spinner("Mendeteksi duplikat internal register..."):
            dup_register = find_internal_duplicates(df_register, threshold=threshold)

        with st.spinner("Mendeteksi duplikat internal login..."):
            event_cols = [c for c in ['judul_kegiatan', 'tanggal_kegiatan'] if c in df_login.columns]
            dup_login = find_internal_duplicates(df_login, threshold=threshold, event_cols=event_cols)

        with st.spinner("Mencocokkan login <-> register..."):
            df_login, review_match = match_login_to_register(df_login, df_register, fuzzy_threshold=threshold)

        st.session_state.df_register = df_register
        st.session_state.df_login = df_login
        st.session_state.dup_register = dup_register
        st.session_state.dup_login = dup_login
        st.session_state.review_match = review_match
        st.session_state.dropped_register_idx = set()
        st.session_state.dropped_login_idx = set()
        st.session_state.processed = True
        st.sidebar.success("Selesai. Lihat tab review di halaman utama.")

st.title("🧹 Sistem Cleaning Dataset Peserta Lapangan")
st.caption("Register (unique reach) & Login (kehadiran per kegiatan) — dengan human-in-the-loop review.")

if not st.session_state.processed:
    st.info("Upload file CSV register & login di sidebar, lalu klik **Jalankan Cleaning & Matching**.")
    st.stop()

df_register = st.session_state.df_register
df_login = st.session_state.df_login

tab_summary, tab_match, tab_dup_reg, tab_dup_login, tab_export = st.tabs(
    ["📊 Ringkasan", "🔗 Review Login↔Register", "👥 Duplikat Register", "👥 Duplikat Login", "⬇️ Export"]
)

# ---------------------------------------------------------------------------
# TAB: RINGKASAN
# ---------------------------------------------------------------------------
with tab_summary:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Register", len(df_register))
    c2.metric("Total Login (baris kehadiran)", len(df_login))
    exact = (df_login['match_status'] == 'exact').sum()
    pending = (df_login['match_status'] == 'pending_review').sum()
    unmatched = (df_login['match_status'] == 'unmatched').sum()
    c3.metric("Login Ter-link Otomatis", int(exact))
    c4.metric("Perlu Review / Unmatched", int(pending + unmatched))

    st.subheader("Distribusi Status Matching Login")
    st.dataframe(df_login['match_status'].value_counts().rename_axis('status').reset_index(name='jumlah'),
                 use_container_width=True)

    st.subheader("Preview Register (clean)")
    st.dataframe(df_register.drop(columns=['id_peserta_calc'], errors='ignore').head(20), use_container_width=True)

    st.subheader("Preview Login (clean)")
    st.dataframe(df_login.drop(columns=['id_peserta_calc'], errors='ignore').head(20), use_container_width=True)

# ---------------------------------------------------------------------------
# TAB: REVIEW LOGIN <-> REGISTER (kandidat match fuzzy / typo)
# ---------------------------------------------------------------------------
with tab_match:
    review_match = st.session_state.review_match
    st.write("Baris login yang **tidak exact match** ke register, tapi ada kandidat mirip (kemungkinan typo). "
             "Putuskan apakah ini orang yang sama (link) atau memang beda orang (biarkan unmatched → perlu isi form register).")

    if review_match is None or review_match.empty:
        st.success("Tidak ada kandidat match yang perlu direview. 🎉")
    else:
        for i, r in review_match.iterrows():
            if r['status'] != 'pending':
                continue
            with st.container(border=True):
                cols = st.columns([3, 3, 2, 2])
                cols[0].markdown(f"**Login:** {r['nama_login']}  \n"
                                  f"TTL: {r['tanggal_lahir_login']} | Kel: {r['kelurahan_login']}")
                cols[1].markdown(f"**Register:** {r['nama_register']}  \n"
                                  f"TTL: {r['tanggal_lahir_register']} | Kel: {r['kelurahan_register']}")
                cols[2].metric("Similarity", f"{r['similarity_score']}%")
                b1, b2 = cols[3].columns(2)
                if b1.button("✅ Sama", key=f"match_same_{i}"):
                    login_idx = r['login_index']
                    reg_idx = r['register_index']
                    reg_id = df_register.loc[reg_idx, 'id_peserta_calc']
                    df_login.at[login_idx, 'id_peserta'] = reg_id
                    df_login.at[login_idx, 'match_status'] = 'linked_manual'
                    st.session_state.review_match.at[i, 'status'] = 'linked'
                    st.rerun()
                if b2.button("❌ Beda", key=f"match_diff_{i}"):
                    login_idx = r['login_index']
                    df_login.at[login_idx, 'match_status'] = 'unmatched'
                    st.session_state.review_match.at[i, 'status'] = 'rejected'
                    st.rerun()

# ---------------------------------------------------------------------------
# TAB: DUPLIKAT REGISTER
# ---------------------------------------------------------------------------
with tab_dup_reg:
    dup_register = st.session_state.dup_register
    st.write("Pasangan baris di dataset **Register** dengan similarity tinggi (kemungkinan orang yang sama "
             "terdaftar dua kali dengan typo). Pilih baris mana yang di-keep, mana yang dihapus.")

    if dup_register is None or dup_register.empty:
        st.success("Tidak ada dugaan duplikat di register. 🎉")
    else:
        for i, r in dup_register.iterrows():
            if r['status'] != 'pending':
                continue
            idx_a, idx_b = int(r['index_a']), int(r['index_b'])
            if idx_a in st.session_state.dropped_register_idx or idx_b in st.session_state.dropped_register_idx:
                continue
            with st.container(border=True):
                cols = st.columns([3, 3, 2, 3])
                cols[0].markdown(f"**A:** {r['nama_a']}  \nTTL: {r['tanggal_lahir_a']} | Kel: {r['kelurahan_a']}")
                cols[1].markdown(f"**B:** {r['nama_b']}  \nTTL: {r['tanggal_lahir_b']} | Kel: {r['kelurahan_b']}")
                cols[2].metric("Similarity", f"{r['similarity_score']}%")
                b1, b2, b3 = cols[3].columns(3)
                if b1.button("Keep A", key=f"reg_keepA_{i}"):
                    st.session_state.dropped_register_idx.add(idx_b)
                    dup_register.at[i, 'status'] = 'resolved_keep_a'
                    st.rerun()
                if b2.button("Keep B", key=f"reg_keepB_{i}"):
                    st.session_state.dropped_register_idx.add(idx_a)
                    dup_register.at[i, 'status'] = 'resolved_keep_b'
                    st.rerun()
                if b3.button("Keep Keduanya", key=f"reg_keepboth_{i}"):
                    dup_register.at[i, 'status'] = 'resolved_keep_both'
                    st.rerun()

# ---------------------------------------------------------------------------
# TAB: DUPLIKAT LOGIN
# ---------------------------------------------------------------------------
with tab_dup_login:
    dup_login = st.session_state.dup_login
    st.write("Pasangan baris di dataset **Login** dengan similarity tinggi (kemungkinan submit form dobel "
             "untuk kegiatan yang sama). Pilih baris mana yang di-keep, mana yang dihapus.")

    if dup_login is None or dup_login.empty:
        st.success("Tidak ada dugaan duplikat di login. 🎉")
    else:
        for i, r in dup_login.iterrows():
            if r['status'] != 'pending':
                continue
            idx_a, idx_b = int(r['index_a']), int(r['index_b'])
            if idx_a in st.session_state.dropped_login_idx or idx_b in st.session_state.dropped_login_idx:
                continue
            with st.container(border=True):
                badge = "🔁 Double-Submit (event sama)" if r.get('flag_type') == 'exact_duplicate_submission' else "✏️ Mirip/Typo"
                st.caption(badge)
                cols = st.columns([3, 3, 2, 3])
                cols[0].markdown(f"**A:** {r['nama_a']}  \nTTL: {r['tanggal_lahir_a']} | Kel: {r['kelurahan_a']}")
                cols[1].markdown(f"**B:** {r['nama_b']}  \nTTL: {r['tanggal_lahir_b']} | Kel: {r['kelurahan_b']}")
                cols[2].metric("Similarity", f"{r['similarity_score']}%")
                b1, b2, b3 = cols[3].columns(3)
                if b1.button("Keep A", key=f"login_keepA_{i}"):
                    st.session_state.dropped_login_idx.add(idx_b)
                    dup_login.at[i, 'status'] = 'resolved_keep_a'
                    st.rerun()
                if b2.button("Keep B", key=f"login_keepB_{i}"):
                    st.session_state.dropped_login_idx.add(idx_a)
                    dup_login.at[i, 'status'] = 'resolved_keep_b'
                    st.rerun()
                if b3.button("Keep Keduanya", key=f"login_keepboth_{i}"):
                    dup_login.at[i, 'status'] = 'resolved_keep_both'
                    st.rerun()

# ---------------------------------------------------------------------------
# TAB: EXPORT
# ---------------------------------------------------------------------------
with tab_export:
    st.write("Data final = hasil cleaning setelah keputusan review diterapkan "
             "(baris yang ditandai 'dihapus' di tab duplikat akan dikeluarkan).")

    final_register = df_register.drop(index=list(st.session_state.dropped_register_idx), errors='ignore')
    final_login = df_login.drop(index=list(st.session_state.dropped_login_idx), errors='ignore')

    pending_match_left = 0
    if st.session_state.review_match is not None and not st.session_state.review_match.empty:
        pending_match_left = (st.session_state.review_match['status'] == 'pending').sum()
    pending_dup_reg_left = 0
    if st.session_state.dup_register is not None and not st.session_state.dup_register.empty:
        pending_dup_reg_left = (st.session_state.dup_register['status'] == 'pending').sum()
    pending_dup_login_left = 0
    if st.session_state.dup_login is not None and not st.session_state.dup_login.empty:
        pending_dup_login_left = (st.session_state.dup_login['status'] == 'pending').sum()

    total_pending = pending_match_left + pending_dup_reg_left + pending_dup_login_left
    if total_pending > 0:
        st.warning(f"Masih ada {total_pending} flag yang belum diputuskan (pending). "
                   f"Export tetap bisa dilakukan, tapi flag yang pending akan ikut apa adanya di data.")
    else:
        st.success("Semua flag sudah direview. Data siap diexport.")

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Total Register (final)", len(final_register))
        csv_reg = final_register.to_csv(index=False).encode('utf-8-sig')
        st.download_button("⬇️ Download Register (CSV)", csv_reg, "register_clean_final.csv", "text/csv")

    with c2:
        st.metric("Total Login (final)", len(final_login))
        csv_login = final_login.to_csv(index=False).encode('utf-8-sig')
        st.download_button("⬇️ Download Login (CSV)", csv_login, "login_clean_final.csv", "text/csv")

    # Gabungan satu file Excel (2 sheet) — memudahkan sumber Power BI
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        final_register.to_excel(writer, sheet_name='register_clean', index=False)
        final_login.to_excel(writer, sheet_name='login_clean', index=False)
    st.download_button(
        "⬇️ Download Excel Gabungan (2 sheet, untuk Power BI)",
        buffer.getvalue(),
        "peserta_clean_final.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
