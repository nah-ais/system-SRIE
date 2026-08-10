# Sistem Cleaning Dataset Peserta (Register & Login)

Streamlit app untuk membersihkan dataset REGISTER (unique reach) dan LOGIN
(kehadiran per kegiatan), dengan human-in-the-loop review untuk kasus duplikat/typo.

## Struktur File
- `cleaning.py` — cleaning generik (dipakai untuk register & login), diadaptasi dari
  `cleanLoginFormCSV.py` milikmu. Kalau nama kolom Kobo berbeda, edit
  `LOGIN_COLUMN_MAPPING` / `REGISTER_COLUMN_MAPPING` di file ini.
- `matching.py` — deteksi duplikat internal (fuzzy similarity) + pencocokan login↔register.
- `app.py` — aplikasi Streamlit (upload, review, export). **Jalankan file ini.**
- `requirements.txt` — dependencies.

## Cara Menjalankan (lokal / EC2)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Kalau di EC2 dan ingin diakses dari browser luar:
```bash
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```
(pastikan port 8501 terbuka di security group EC2)

## Alur Pemakaian
1. Upload CSV **Register** dan CSV **Login** di sidebar (export dari Kobo).
2. Set threshold similarity (default 90%).
3. Klik **Jalankan Cleaning & Matching**.
4. Cek tab **Ringkasan** untuk gambaran umum.
5. Review satu-satu di tab **Review Login↔Register** (kandidat typo) dan
   tab **Duplikat Register / Duplikat Login** (klik Keep A / Keep B / Keep Keduanya).
6. Setelah semua flag selesai direview, ke tab **Export** untuk download
   CSV atau Excel (2 sheet: register_clean & login_clean) — file ini yang
   dikoneksikan ke Power BI.

## Catatan Desain
- **id_peserta_calc**: hash deterministik dari `nama_clean + tanggal_lahir_clean + kelurahan_clean`.
  Ini yang jadi dasar exact-match otomatis antara login dan register.
- Data hanya tersimpan selama sesi browser (session_state) — belum ada
  penyimpanan permanen/database. Kalau nanti proses berjalan berkala
  (bukan cuma demo sekali jalan), pertimbangkan tambahkan database supaya
  histori keputusan review tidak hilang tiap refresh.
- Similarity dihitung dari gabungan `nama_clean | tanggal_lahir_clean | kelurahan_clean`
  (token_sort_ratio, rapidfuzz) — bukan cuma nama, supaya lebih akurat.
