# TikTok Trending Scraper (Indonesia)

Tools CLI untuk scrape TikTok dengan dua mode:

1. **Hashtag** — cari **lagu yang lagi tren** dari hashtag goyang/dance, group by music, rangking by total views/likes/komentar.
2. **List username** — scrape **top video** dari daftar username manual yang kamu pilih, tanpa filter lagu.

Hasil ditampilkan rapi di terminal (pakai [Rich](https://github.com/Textualize/rich)) plus disimpan ke JSON.

## Fitur

- 2 mode: hashtag (group lagu) & list_username (top video dari list).
- Scrape multi-hashtag (default: 8 hashtag goyang/dance ID).
- Mode list_username pakai file manual `username_list.txt` — jumlah username bebas (warning kalau > ~40 karena TikTok cenderung bot-detect).
- Filter rentang waktu fleksibel (default 7 hari).
- Sort by views / likes / komentar.
- Anti rate-limit: delay antar user (default 2 detik), auto-abort kalau 5 user beruntun error.
- Hasil lengkap diekspor ke JSON (`trending_output.json` / `trending_following_output.json`).
- Auto-prompt & simpan `MS_TOKEN` ke `.env`.

## Demo Output

```
──── TOP 15 LAGU TREN — 7 HARI TERAKHIR (ID) ────

──── #1 Judul Lagu  •  by Artis ────
┏━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Username      ┃   Likes ┃    Views ┃ Link                                ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ @creator1     │ 120,500 │ 2,340,000 │ https://www.tiktok.com/@…           │
│ @creator2     │  98,210 │ 1,820,500 │ https://www.tiktok.com/@…           │
└───────────────┴────────┴──────────┴─────────────────────────────────────┘
Σ 8,420,300 views • 612,450 likes • 47 video
```

## Persyaratan

- Python 3.10+
- Browser Chromium (di-install otomatis lewat Playwright)
- Akun TikTok aktif untuk ambil cookie `msToken`
- OS: **Linux**, **macOS**, atau **Windows**
  - Di Windows, **disarankan pakai Windows Terminal atau VS Code Terminal** (bukan legacy `cmd.exe` warisan).
  - Script auto-enable ANSI/VT100 mode di Windows 10+ supaya hyperlink `▶ buka video` clickable & emoji ke-render benar.
  - Kalau masih ada karakter aneh (`\x1b[1m`), berarti terminal-nya **Windows lama (<10)** atau **PowerShell ISE** — install [Windows Terminal](https://aka.ms/terminal) gratis dari Microsoft Store.

## Cara Pakai

### Linux / macOS

```bash
./run.sh
```

### Windows

```bat
run.bat
```

Script `run.*` otomatis bikin virtualenv, install dependencies, install Playwright Chromium, dan jalanin scraper.

### Manual (kalau mau setup sendiri)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
python main.py
```

## Setup MS_TOKEN

Tanpa `MS_TOKEN`, TikTok akan langsung blokir scraper. Cara ambil token:

1. Buka [https://www.tiktok.com](https://www.tiktok.com) di Chrome/Firefox, **login**.
2. Buka DevTools (`F12`) → tab **Application** → **Cookies** → `https://www.tiktok.com`.
3. Cari cookie bernama **`msToken`** dengan domain `.tiktok.com`, copy **Value**-nya.
4. Paste ke prompt saat script jalan, atau langsung ke file `.env`:

   ```env
   MS_TOKEN=isi_token_disini
   ```

Token akan otomatis di-refresh ke `.env` kalau di-input lewat prompt.

> ⚠️ Token bisa expired dalam beberapa jam–hari. Kalau hasil scrape tiba-tiba kosong, kemungkinan besar token-nya udah mati — script akan nawarin input ulang.

## Konfigurasi

Saat dijalankan, script pertama akan tanya **mode**:

| Mode | Deskripsi                                                            |
| ---- | -------------------------------------------------------------------- |
| `1`  | hashtag — top lagu tren dari hashtag (default).                      |
| `2`  | following — top video dari user yang kamu follow / list manual.      |

### Mode 1: hashtag

| Parameter           | Default                                                                                        |
| ------------------- | ---------------------------------------------------------------------------------------------- |
| Hashtag             | `goyangviral dancetiktok joget goyang fypindonesia danceindonesia jogetviral goyangtiktok`     |
| Rentang waktu (hari)| `7`                                                                                            |
| Top N lagu          | `15`                                                                                           |
| Sort by             | `1` (views) — pilihan: `1`=views, `2`=likes, `3`=komentar                                      |

### Mode 2: list_username

Tujuan: dari daftar username yang kamu tentukan sendiri, lihat **siapa yang posting** dalam N hari terakhir dan **mana yang terbaik**.

> ⚠ TikTok cenderung bot-detect setelah ~40 user beruntun (anecdotal — tergantung kondisi token, IP, session). Kalau list > 40, sebagian user kemungkinan kena `rate-limited / bot-detect`. Auto-abort akan stop scraping setelah 5 error beruntun. Pakai sesuai kebutuhan, naikkan `SCRAPE_DELAY` kalau mau coba lebih banyak.

**Setup `username_list.txt`:**

Saat pertama kali pilih mode 2, script akan auto-bikin template `username_list.txt` (gitignored). Edit file tersebut, isi list username:

```
# Daftar username TikTok yang mau di-scrape
# Satu per baris, tanpa @
rizkypoetra
fadilfaza
ardiansyahad
...
```

Aturan file:
- 1 username per baris, tanpa `@`
- Baris diawali `#` = komentar (diabaikan)
- Jumlah bebas, warning otomatis kalau > ~40

**Konfigurasi run:**

| Parameter              | Default                                                                                |
| ---------------------- | -------------------------------------------------------------------------------------- |
| Username list          | `username_list.txt` (jumlah bebas)                                                     |
| Rentang waktu (hari)   | `7`                                                                                    |
| Top N video            | `15`                                                                                   |
| Sort by                | `1` (views) — pilihan: `1`=views, `2`=likes, `3`=komentar                              |
| Max post per user      | `3` (cap di top, supaya 1 user prolific gak dominasi top 15)                           |
| Scrape per user        | `20` video terbaru                                                                     |
| Delay antar user       | `0` detik (env `SCRAPE_DELAY` — naikkan kalau bot-detect)                              |
| Auto-abort             | 5 user beruntun error → stop, sisanya di-skip                                          |

**Output mode list_username:**
- Summary: `X user di-track • Y posting • Z silent • W error`
- Tabel top N video (mix dari semua user, max 3 per user)
- List user silent + errored (preview di terminal, lengkap di JSON)
- File JSON: `trending_following_output.json`

Konstanta lain (edit langsung di `main.py` kalau mau):

```python
VIDEOS_PER_HASHTAG = 50          # jumlah video di-scrape per hashtag
TOP_N_CREATORS_PER_SONG = 5      # top creator yang ditampilkan per lagu
```

## Struktur Project

```
tiktok-scraper/
├── main.py              # entry point — scraping, ranking, render
├── requirements.txt     # dependencies Python
├── run.sh / run.bat     # one-shot runner (Linux/macOS & Windows)
├── .env.example         # template environment variables
└── trending_output.json # hasil lengkap (dihasilkan setelah run)
```

## Output JSON

File `trending_output.json` berisi array lagu yang sudah diurutkan dari views terbanyak:

```json
[
  {
    "music_id": "7123456789...",
    "title": "Judul Lagu",
    "author_name": "Nama Artis",
    "total_plays": 8420300,
    "total_likes": 612450,
    "total_comments": 18230,
    "videos": [
      {
        "username": "creator1",
        "url": "https://www.tiktok.com/@creator1/video/...",
        "plays": 2340000,
        "likes": 120500,
        "comments": 5400,
        "created_at": "2026-04-30T10:23:11+00:00"
      }
    ]
  }
]
```

## Troubleshooting

| Masalah                                        | Solusi                                                                  |
| ---------------------------------------------- | ----------------------------------------------------------------------- |
| `Tidak ada data dari TikTok`                   | Token kemungkinan expired — input ulang saat diminta.                   |
| `playwright._impl._api_types.Error: Executable doesn't exist` | Jalankan `python -m playwright install chromium`.                       |
| Hashtag tertentu nge-error                     | Hashtag mungkin diblokir / tidak ada — coba ganti list hashtag.         |
| Hasil sedikit walaupun token valid             | Naikkan `VIDEOS_PER_HASHTAG` atau tambahkan hashtag lain.               |

## Catatan

- Project ini untuk keperluan **edukasi & riset tren musik**. Patuhi [Terms of Service TikTok](https://www.tiktok.com/legal/terms-of-service) saat penggunaan.
- API TikTok tidak resmi — perubahan struktur dari sisi TikTok bisa bikin scraper sewaktu-waktu break.
- Library inti: [`TikTokApi`](https://github.com/davidteather/TikTok-Api) by David Teather.

## Lisensi

MIT — silakan dipakai, dimodifikasi, dan dijadiin acuan.

## Author

**Lutfi Febrianto** — Full Stack Developer
