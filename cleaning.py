"""
cleaning.py
Modul cleaning generik untuk dataset REGISTER dan LOGIN.
Diadaptasi dari cleanLoginFormCSV.py (logic sama, dibuat reusable untuk 2 dataset).
"""

import pandas as pd
import numpy as np
import re
from typing import Optional, Dict


# ---------------------------------------------------------------------------
# 1. COLUMN MAPPING PER DATASET
#    Sesuaikan key (nama kolom asli dari Kobo) jika berbeda di lapangan.
# ---------------------------------------------------------------------------

LOGIN_COLUMN_MAPPING = {
    '_id': 'id_kobo',
    '_submission_time': 'timestamp_submit',
    'Masukkan Nama Anda:': 'nama',
    'Masukkan Tanggal Lahir:': 'tanggal_lahir',
    'Kelurahan': 'kelurahan',
    'Tuliskan Kelurahannya': 'kelurahan_lainnya',
    'Area Program': 'area_program',
    'Judul Kegiatan': 'judul_kegiatan',
    'Tanggal Kegiatan': 'tanggal_kegiatan',
}

REGISTER_COLUMN_MAPPING = {
    '_id': 'id_kobo',
    '_submission_time': 'timestamp_submit',
    'Masukkan Nama Anda:': 'nama',
    'Masukkan Tanggal Lahir:': 'tanggal_lahir',
    'Kelurahan': 'kelurahan',
    'Tuliskan Kelurahannya': 'kelurahan_lainnya',
    'Area Program': 'area_program',
    # tambahkan field khusus register di sini kalau ada, mis:
    # 'Nama Kepala Keluarga': 'nama_kepala_keluarga',
}


# ---------------------------------------------------------------------------
# 2. HELPER FUNCTIONS TEKS & TANGGAL
# ---------------------------------------------------------------------------

def clean_text_display(val: Optional[str]) -> str:
    """Merapikan teks untuk tampilan UI / Power BI (Title Case)."""
    if pd.isna(val) or val is None:
        return ""
    text = str(val).strip()
    text = re.sub(r'\s+', ' ', text)
    return text.title()


def clean_text_matching(val: Optional[str]) -> str:
    """Merapikan teks untuk matching engine (lowercase, hapus prefiks & simbol)."""
    if pd.isna(val) or val is None:
        return ""
    text = str(val).lower().strip()
    text = re.sub(r'\b(kel(?:urahan)?|kec(?:amatan)?)\.?\s*', '', text)
    text = re.sub(r'[^a-z0-9\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_date_iso(series: pd.Series) -> pd.Series:
    """Konversi tanggal ke format ISO YYYY-MM-DD (aman untuk format Indonesia DD/MM/YYYY)."""
    parsed = pd.to_datetime(series, errors='coerce', format='mixed', dayfirst=True)
    return parsed.dt.strftime('%Y-%m-%d').fillna('')


# ---------------------------------------------------------------------------
# 3. PIPELINE CLEANING GENERIK
# ---------------------------------------------------------------------------

def clean_dataset(df_raw: pd.DataFrame, column_mapping: Dict[str, str], dataset_label: str = "DATASET") -> pd.DataFrame:
    """
    Cleaning generik dipakai baik untuk REGISTER maupun LOGIN.
    - Filter & rename kolom esensial sesuai column_mapping.
    - Konsolidasi kelurahan & penanganan input 'Lainnya'.
    - Pemisahan versi Display (Reporting) dan Clean (Matching).
    - Format tanggal standar ISO.
    """
    existing_cols = [col for col in column_mapping.keys() if col in df_raw.columns]
    df = df_raw[existing_cols].rename(columns=column_mapping).copy()

    # Konsolidasi Kelurahan
    if 'kelurahan' in df.columns and 'kelurahan_lainnya' in df.columns:
        cond_other = df['kelurahan'].astype(str).str.strip().str.lower().isin(['lainnya', 'other'])
        custom_val = df['kelurahan_lainnya'].fillna('').astype(str).str.strip()
        has_custom = custom_val != ''
        df['kelurahan_final'] = np.where(cond_other & has_custom, df['kelurahan_lainnya'], df['kelurahan'])
    elif 'kelurahan' in df.columns:
        df['kelurahan_final'] = df['kelurahan']
    else:
        df['kelurahan_final'] = ""

    if 'id_kobo' in df.columns:
        df['id_kobo'] = df['id_kobo'].astype(str).str.strip()

    if 'timestamp_submit' in df.columns:
        df['timestamp_submit'] = pd.to_datetime(df['timestamp_submit'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')

    if 'nama' in df.columns:
        df['nama_display'] = df['nama'].apply(clean_text_display)
        df['nama_clean'] = df['nama'].apply(clean_text_matching)
        df.drop(columns=['nama'], inplace=True)

    if 'tanggal_lahir' in df.columns:
        df['tanggal_lahir_clean'] = parse_date_iso(df['tanggal_lahir'])
        df.drop(columns=['tanggal_lahir'], inplace=True)

    df['kelurahan_display'] = df['kelurahan_final'].apply(clean_text_display)
    df['kelurahan_clean'] = df['kelurahan_final'].apply(clean_text_matching)
    df.drop(columns=[c for c in ['kelurahan', 'kelurahan_lainnya', 'kelurahan_final'] if c in df.columns],
            inplace=True)

    for meta_col in ['area_program', 'judul_kegiatan', 'tanggal_kegiatan']:
        if meta_col in df.columns:
            df[meta_col] = df[meta_col].apply(clean_text_display)

    # id_peserta: kunci identitas deterministik dari 3 variabel validasi
    if {'nama_clean', 'tanggal_lahir_clean', 'kelurahan_clean'}.issubset(df.columns):
        df['id_peserta_calc'] = (
            df['nama_clean'] + '|' + df['tanggal_lahir_clean'] + '|' + df['kelurahan_clean']
        ).apply(lambda s: __import__('hashlib').md5(s.encode('utf-8')).hexdigest()[:12])

    # QC report
    print("=" * 60)
    print(f"📋 REPORT QUALITY CONTROL CLEANING — {dataset_label}")
    print("=" * 60)
    print(f"• Total Data Masuk         : {len(df)} baris")
    if 'id_kobo' in df.columns:
        print(f"• ID Kobo Kosong           : {df['id_kobo'].eq('').sum()} baris")
    if 'nama_clean' in df.columns:
        print(f"• Nama Kosong              : {df['nama_clean'].eq('').sum()} baris")
    if 'tanggal_lahir_clean' in df.columns:
        print(f"• Tanggal Lahir Tidak Valid: {df['tanggal_lahir_clean'].eq('').sum()} baris")
    if 'kelurahan_clean' in df.columns:
        print(f"• Kelurahan Kosong         : {df['kelurahan_clean'].eq('').sum()} baris")
    print("=" * 60 + "\n")

    return df


def clean_login_dataset(df_raw: pd.DataFrame) -> pd.DataFrame:
    return clean_dataset(df_raw, LOGIN_COLUMN_MAPPING, dataset_label="FORM LOGIN")


def clean_register_dataset(df_raw: pd.DataFrame) -> pd.DataFrame:
    return clean_dataset(df_raw, REGISTER_COLUMN_MAPPING, dataset_label="FORM REGISTER")
