"""
matching.py
Modul untuk:
1. Mencocokkan baris LOGIN <-> REGISTER (link id_peserta).
2. Mendeteksi duplikat/near-duplicate di dalam masing-masing dataset (fuzzy similarity).

Menggunakan rapidfuzz untuk fuzzy string matching.
"""

import pandas as pd
from rapidfuzz import fuzz
from itertools import combinations


def _combined_string(row: pd.Series) -> str:
    """Gabungkan field identitas jadi satu string untuk similarity scoring."""
    parts = [
        str(row.get('nama_clean', '')),
        str(row.get('tanggal_lahir_clean', '')),
        str(row.get('kelurahan_clean', '')),
    ]
    return ' | '.join(parts)


def find_internal_duplicates(df: pd.DataFrame, threshold: int = 90, id_col: str = None) -> pd.DataFrame:
    """
    Cari pasangan baris yang mirip (similarity >= threshold) DI DALAM satu dataset.
    Mengembalikan dataframe flag: index_a, index_b, score, field-field pembanding.
    Baris dengan id_peserta_calc identik dilewati (memang orang yang sama, bukan kandidat duplikat).
    """
    df = df.reset_index(drop=True)
    strings = df.apply(_combined_string, axis=1).tolist()
    n = len(df)
    flags = []

    for i, j in combinations(range(n), 2):
        # skip kalau id_peserta_calc sudah identik (bukan kasus duplikat, tapi orang sama)
        if 'id_peserta_calc' in df.columns and df.loc[i, 'id_peserta_calc'] == df.loc[j, 'id_peserta_calc']:
            continue
        score = fuzz.token_sort_ratio(strings[i], strings[j])
        if score >= threshold:
            flags.append({
                'index_a': i,
                'index_b': j,
                'similarity_score': round(score, 1),
                'nama_a': df.loc[i, 'nama_display'] if 'nama_display' in df.columns else '',
                'nama_b': df.loc[j, 'nama_display'] if 'nama_display' in df.columns else '',
                'tanggal_lahir_a': df.loc[i].get('tanggal_lahir_clean', ''),
                'tanggal_lahir_b': df.loc[j].get('tanggal_lahir_clean', ''),
                'kelurahan_a': df.loc[i].get('kelurahan_display', ''),
                'kelurahan_b': df.loc[j].get('kelurahan_display', ''),
                'status': 'pending',
            })

    return pd.DataFrame(flags)


def match_login_to_register(df_login: pd.DataFrame, df_register: pd.DataFrame,
                             fuzzy_threshold: int = 90) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Cocokkan setiap baris login ke register:
    - Exact match (id_peserta_calc sama)   -> langsung linked, match_type='exact'
    - Tidak exact tapi fuzzy score tinggi   -> flagged untuk review manual (kemungkinan typo)
    - Tidak ada kandidat sama sekali        -> flagged 'unmatched' (perlu diarahkan isi form register)

    Return: (df_login dengan kolom tambahan match_status/id_peserta/match_score,
             df_flags_review berisi kandidat match yang perlu keputusan manusia)
    """
    df_login = df_login.reset_index(drop=True).copy()
    df_register = df_register.reset_index(drop=True).copy()

    reg_strings = df_register.apply(_combined_string, axis=1).tolist()
    reg_ids = df_register['id_peserta_calc'].tolist() if 'id_peserta_calc' in df_register.columns else [None] * len(df_register)

    df_login['id_peserta'] = None
    df_login['match_status'] = 'unmatched'
    df_login['match_score'] = 0.0

    review_rows = []

    for idx, row in df_login.iterrows():
        login_id = row.get('id_peserta_calc')
        # 1. exact match
        if login_id in reg_ids:
            df_login.at[idx, 'id_peserta'] = login_id
            df_login.at[idx, 'match_status'] = 'exact'
            df_login.at[idx, 'match_score'] = 100.0
            continue

        # 2. fuzzy candidate search
        login_str = _combined_string(row)
        best_score = -1
        best_j = None
        for j, reg_str in enumerate(reg_strings):
            score = fuzz.token_sort_ratio(login_str, reg_str)
            if score > best_score:
                best_score = score
                best_j = j

        if best_j is not None and best_score >= fuzzy_threshold:
            df_login.at[idx, 'match_status'] = 'pending_review'
            df_login.at[idx, 'match_score'] = round(best_score, 1)
            review_rows.append({
                'login_index': idx,
                'register_index': best_j,
                'similarity_score': round(best_score, 1),
                'nama_login': row.get('nama_display', ''),
                'nama_register': df_register.loc[best_j, 'nama_display'] if 'nama_display' in df_register.columns else '',
                'tanggal_lahir_login': row.get('tanggal_lahir_clean', ''),
                'tanggal_lahir_register': df_register.loc[best_j].get('tanggal_lahir_clean', ''),
                'kelurahan_login': row.get('kelurahan_display', ''),
                'kelurahan_register': df_register.loc[best_j].get('kelurahan_display', ''),
                'status': 'pending',
            })
        else:
            df_login.at[idx, 'match_status'] = 'unmatched'
            df_login.at[idx, 'match_score'] = round(best_score, 1) if best_score > 0 else 0.0

    return df_login, pd.DataFrame(review_rows)
