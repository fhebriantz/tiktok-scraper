"""Cari lagu yang lagi tren di TikTok Indonesia (1 minggu terakhir).

Strategi: scrape video dari beberapa hashtag goyang/dance Indonesia,
group by music_id, lalu rangking berdasarkan total view.
"""

import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Windows: force stdout/stderr ke UTF-8 + enable VT100 (ANSI) console mode
# supaya emoji, Rich markup, dan OSC 8 hyperlink ter-render benar
# (bukan muncul sebagai escape codes mentah).
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    try:
        # Enable ENABLE_VIRTUAL_TERMINAL_PROCESSING (0x0004) supaya ANSI
        # escape sequences (warna, bold, hyperlink) ke-proses oleh console.
        # Tersedia sejak Windows 10 build 14393 (Anniversary Update, 2016).
        import ctypes

        _kernel32 = ctypes.windll.kernel32
        for _handle_id in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
            _handle = _kernel32.GetStdHandle(_handle_id)
            _mode = ctypes.c_uint32()
            if _kernel32.GetConsoleMode(_handle, ctypes.byref(_mode)):
                _kernel32.SetConsoleMode(_handle, _mode.value | 0x0004)
    except Exception:
        pass

from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.table import Table
from TikTokApi import TikTokApi

load_dotenv()

# Box style: ASCII di Windows supaya tabel rapi di cmd.exe/PowerShell yang gak
# render box-drawing unicode dengan baik. Linux/macOS pakai default heavy-head.
TABLE_BOX = box.ASCII if sys.platform == "win32" else box.HEAVY_HEAD

DEFAULT_HASHTAGS = [
    "goyangviral",
    "fakesituation⚠️",
    "fakebodyy⚠️",
    "fakebody⚠️",
    "geolgelol",
    "crt",
    "pulen"
]
DEFAULT_DAYS_BACK = 7
VIDEOS_PER_HASHTAG = 50
DEFAULT_TOP_N_SONGS = 15
TOP_N_CREATORS_PER_SONG = 5

SORT_OPTIONS = {
    "1": ("total_plays", "views"),
    "2": ("total_likes", "likes"),
    "3": ("total_comments", "komentar"),
}
DEFAULT_SORT_KEY = "1"

MODE_OPTIONS = {
    "1": "hashtag",
    "2": "list_username",
}
DEFAULT_MODE = "1"

VIDEOS_PER_USER = 20
WARN_THRESHOLD_USERNAMES = 40  # Warning: di atas ~40 user, bot-detect TikTok kemungkinan besar aktif
MAX_POSTS_PER_USER_IN_TOP = 3
SILENT_PREVIEW_COUNT = 20

# Delay antar user untuk hindari TikTok bot-detection. Set 0 buat disable.
SCRAPE_DELAY_SECONDS = float(os.environ.get("SCRAPE_DELAY", "0"))
# Berhenti scrape kalau N user beruntun error (kemungkinan besar ke-rate-limit).
ABORT_AFTER_CONSECUTIVE_ERRORS = 5

USERNAME_LIST_PATH = Path("username_list.txt")

# Default false (browser muncul) — bantu lolos bot-detection. Set HEADLESS=true di .env buat sembunyikan.
HEADLESS = os.environ.get("HEADLESS", "false").strip().lower() == "true"

ENV_PATH = Path(".env")

console = Console(legacy_windows=False)


def read_env_value(key: str) -> str:
    if not ENV_PATH.exists():
        return ""
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def write_env_value(key: str, value: str) -> None:
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _read_username_file() -> list[str]:
    """Baca username_list.txt → list username (tanpa @, dedupe). Skip baris komentar/kosong."""
    if not USERNAME_LIST_PATH.exists():
        return []
    seen: set[str] = set()
    out: list[str] = []
    for line in USERNAME_LIST_PATH.read_text(encoding="utf-8").splitlines():
        un = line.strip().lstrip("@")
        if not un or un.startswith("#"):
            continue
        if un in seen:
            continue
        seen.add(un)
        out.append(un)
    return out


def _create_username_template() -> None:
    template = (
        "# Daftar username TikTok yang mau di-scrape (mode list_username).\n"
        "# Aturan:\n"
        "#   - Satu username per baris, tanpa @\n"
        "#   - Berapapun jumlahnya boleh, tapi:\n"
        f"#     ⚠  TikTok biasanya bot-detect setelah ~{WARN_THRESHOLD_USERNAMES} user beruntun.\n"
        "#     Kalau >threshold, sebagian user kemungkinan ke-skip dengan error.\n"
        "#   - Baris diawali # = komentar (diabaikan)\n"
        "#   - File ini di-gitignore\n"
        "#\n"
        "# Contoh:\n"
        "# rizkypoetra\n"
        "# fadilfaza\n"
    )
    USERNAME_LIST_PATH.write_text(template, encoding="utf-8")


def load_username_list() -> list[str]:
    """Load semua username dari username_list.txt.

    Kalau file gak ada → bikin template + exit dengan instruksi.
    Kalau kosong → exit dengan instruksi.
    Kalau > WARN_THRESHOLD_USERNAMES → kasih warning (tapi tetap di-load semua).
    """
    if not USERNAME_LIST_PATH.exists():
        _create_username_template()
        console.print()
        console.print(f"[bold yellow]File {USERNAME_LIST_PATH} belum ada — saya buatkan template.[/bold yellow]")
        console.print(
            f"[yellow]Edit file tersebut, isi list username (1 per baris, tanpa @), lalu jalankan ulang.[/yellow]"
        )
        return []

    usernames = _read_username_file()
    if not usernames:
        console.print()
        console.print(f"[bold red]{USERNAME_LIST_PATH} kosong.[/bold red]")
        console.print(
            f"[red]Isi file dengan list username (1 per baris, tanpa @) lalu jalankan ulang.[/red]"
        )
        return []

    if len(usernames) > WARN_THRESHOLD_USERNAMES:
        console.print(
            f"[yellow]⚠ List berisi {len(usernames)} username — "
            f"di atas {WARN_THRESHOLD_USERNAMES} bot-detect TikTok kadang aktif (tidak selalu).[/yellow]"
        )
        console.print(
            "[dim]Faktor lain berperan: freshness MS_TOKEN, IP, session age. "
            "Kalau kena abort dini → refresh token, naikkan SCRAPE_DELAY, atau kurangi list.[/dim]"
        )

    return usernames


def prompt_ms_token() -> str:
    console.print()
    console.print("[bold yellow]MS_TOKEN dibutuhkan untuk scrape TikTok.[/bold yellow]")
    console.print("Cara ambil:")
    console.print("  1. Buka https://www.tiktok.com di Chrome/Firefox, login.")
    console.print("  2. F12 → tab Application → Cookies → https://www.tiktok.com")
    console.print("  3. Cari cookie [bold]msToken[/bold] domain [bold].tiktok.com[/bold], copy Value.")
    console.print()
    token = input("Paste MS_TOKEN di sini: ").strip()
    if not token:
        console.print("[red]Token kosong. Keluar.[/red]")
        sys.exit(1)
    write_env_value("MS_TOKEN", token)
    console.print("[green]✓ Token disimpan ke .env[/green]")
    return token


def prompt_mode() -> str:
    console.print()
    console.print("[bold]Pilih mode:[/bold]")
    console.print("  1) hashtag       — scrape lagu tren dari hashtag")
    console.print(
        f"  2) list_username — top video dari list username (file {USERNAME_LIST_PATH})"
    )
    raw = input(f"Mode? [{DEFAULT_MODE}]: ").strip() or DEFAULT_MODE
    if raw not in MODE_OPTIONS:
        console.print("[yellow]Pilihan tidak valid, pakai default (hashtag).[/yellow]")
        raw = DEFAULT_MODE
    return raw


def prompt_count_and_sort(label_unit: str) -> tuple[int, int, str]:
    console.print(f"[dim]Default rentang waktu: {DEFAULT_DAYS_BACK} hari terakhir[/dim]")
    days_raw = input(f"Ambil {label_unit} dari berapa hari terakhir? ").strip()
    try:
        days_back = int(days_raw) if days_raw else DEFAULT_DAYS_BACK
        if days_back <= 0:
            raise ValueError
    except ValueError:
        console.print("[yellow]Input tidak valid, pakai default.[/yellow]")
        days_back = DEFAULT_DAYS_BACK

    console.print(f"[dim]Default top N: {DEFAULT_TOP_N_SONGS}[/dim]")
    n_raw = input(f"Tampilkan berapa {label_unit}? ").strip()
    try:
        top_n = int(n_raw) if n_raw else DEFAULT_TOP_N_SONGS
        if top_n <= 0:
            raise ValueError
    except ValueError:
        console.print("[yellow]Input tidak valid, pakai default.[/yellow]")
        top_n = DEFAULT_TOP_N_SONGS

    console.print("[dim]Pilihan sort: 1) views  2) likes  3) komentar[/dim]")
    sort_raw = input(f"Sort by? [{DEFAULT_SORT_KEY}]: ").strip() or DEFAULT_SORT_KEY
    if sort_raw not in SORT_OPTIONS:
        console.print("[yellow]Pilihan tidak valid, pakai default (views).[/yellow]")
        sort_raw = DEFAULT_SORT_KEY

    return days_back, top_n, sort_raw


def prompt_hashtag_options() -> tuple[list[str], int, int, str]:
    console.print()
    console.print("[bold]Konfigurasi hashtag (Enter = pakai default)[/bold]")

    default_tags_str = " ".join(DEFAULT_HASHTAGS)
    console.print(f"[dim]Default hashtag: {default_tags_str}[/dim]")
    tags_raw = input("Hashtag (pisah spasi, tanpa #): ").strip()
    if tags_raw:
        tags = [t.lstrip("#") for t in tags_raw.split() if t.strip()]
    else:
        tags = DEFAULT_HASHTAGS

    days_back, top_n, sort_raw = prompt_count_and_sort("lagu")
    return tags, days_back, top_n, sort_raw


async def collect(ms_token: str, hashtags: list[str], days_back: int) -> dict[str, dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    music_stats: dict[str, dict] = defaultdict(
        lambda: {
            "music_id": None,
            "title": None,
            "author_name": None,
            "videos": [],
            "total_plays": 0,
            "total_likes": 0,
            "total_comments": 0,
        }
    )
    seen_video_ids: set[str] = set()

    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=1,
            sleep_after=3,
            browser="chromium",
            headless=HEADLESS,
        )

        for tag in hashtags:
            console.print(f"[cyan]Scraping #{tag}...[/cyan]")
            try:
                hashtag = api.hashtag(name=tag)
                count = 0
                async for video in hashtag.videos(count=VIDEOS_PER_HASHTAG):
                    data = video.as_dict
                    video_id = str(data.get("id") or "")
                    if not video_id or video_id in seen_video_ids:
                        continue
                    create_ts = data.get("createTime", 0)
                    if not create_ts:
                        continue
                    created = datetime.fromtimestamp(create_ts, tz=timezone.utc)
                    if created < cutoff:
                        continue
                    seen_video_ids.add(video_id)

                    music = data.get("music") or {}
                    music_id = str(music.get("id") or "")
                    if not music_id:
                        continue

                    stats = music_stats[music_id]
                    stats["music_id"] = music_id
                    stats["title"] = music.get("title") or "Unknown"
                    stats["author_name"] = music.get("authorName") or "Unknown"

                    author = data.get("author") or {}
                    username = author.get("uniqueId") or "unknown"
                    vstats = data.get("stats") or {}
                    plays = int(vstats.get("playCount") or 0)
                    likes = int(vstats.get("diggCount") or 0)
                    comments = int(vstats.get("commentCount") or 0)

                    stats["videos"].append(
                        {
                            "username": username,
                            "url": f"https://www.tiktok.com/@{username}/video/{video_id}",
                            "plays": plays,
                            "likes": likes,
                            "comments": comments,
                            "created_at": created.isoformat(),
                        }
                    )
                    stats["total_plays"] += plays
                    stats["total_likes"] += likes
                    stats["total_comments"] += comments
                    count += 1
                console.print(f"  [green]→ {count} video dalam {days_back} hari terakhir[/green]")
            except Exception as exc:
                console.print(f"  [red]Error: {exc}[/red]")
                continue

    return music_stats


def render(music_stats: dict[str, dict], top_n: int, days_back: int, sort_key: str) -> None:
    sort_field, sort_label = SORT_OPTIONS[sort_key]
    video_sort_field = {"total_plays": "plays", "total_likes": "likes", "total_comments": "comments"}[sort_field]

    sorted_music = sorted(
        music_stats.values(),
        key=lambda m: m.get(sort_field, 0) or 0,
        reverse=True,
    )

    if not sorted_music:
        return

    console.print()
    console.rule(
        f"[bold magenta]TOP {top_n} LAGU TREN — {days_back} HARI TERAKHIR (ID) • sort by {sort_label}"
    )

    for idx, m in enumerate(sorted_music[:top_n], 1):
        title = m["title"][:60]
        console.rule(f"[bold]#{idx} {title}  •  by {m['author_name']}")

        table = Table(show_header=True, header_style="bold cyan", expand=False, box=TABLE_BOX)
        table.add_column("Username", style="bold", no_wrap=True)
        table.add_column("Likes", justify="right", no_wrap=True)
        table.add_column("Views", justify="right", no_wrap=True)
        table.add_column("Komentar", justify="right", no_wrap=True)
        table.add_column("Link", no_wrap=True)

        top_videos = sorted(
            m["videos"], key=lambda v: v.get(video_sort_field, 0) or 0, reverse=True
        )[:TOP_N_CREATORS_PER_SONG]
        for v in top_videos:
            link_cell = f"[link={v['url']}]▶ buka video[/link]"
            table.add_row(
                f"@{v['username']}",
                f"{v.get('likes', 0):,}",
                f"{v.get('plays', 0):,}",
                f"{v.get('comments', 0):,}",
                link_cell,
            )
        console.print(table)
        console.print(
            f"[dim]Σ {m.get('total_plays', 0):,} views • {m.get('total_likes', 0):,} likes • "
            f"{m.get('total_comments', 0):,} komentar • {len(m['videos'])} video[/dim]\n"
        )

    out_path = "trending_output.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(sorted_music, f, indent=2, ensure_ascii=False)
    console.print(f"[green]✓ Hasil lengkap disimpan ke {out_path}[/green]")


async def collect_following(
    ms_token: str, usernames: list[str], days_back: int
) -> tuple[list[dict], list[str], list[str]]:
    """Return (videos, silent, errored). errored = user yg gagal di-scrape (rate-limit/blok)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    all_videos: list[dict] = []
    silent: list[str] = []
    errored: list[str] = []
    seen_video_ids: set[str] = set()
    consecutive_errors = 0
    aborted = False

    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=1,
            sleep_after=3,
            browser="chromium",
            headless=HEADLESS,
        )

        for idx, un in enumerate(usernames):
            if idx > 0 and SCRAPE_DELAY_SECONDS > 0:
                await asyncio.sleep(SCRAPE_DELAY_SECONDS)

            console.print(f"[cyan]Scraping @{un}...[/cyan]")
            user_error: str | None = None
            count = 0
            try:
                user = api.user(username=un)
                async for video in user.videos(count=VIDEOS_PER_USER):
                    data = video.as_dict
                    video_id = str(data.get("id") or "")
                    if not video_id or video_id in seen_video_ids:
                        continue
                    create_ts = data.get("createTime", 0)
                    if not create_ts:
                        continue
                    created = datetime.fromtimestamp(create_ts, tz=timezone.utc)
                    if created < cutoff:
                        continue
                    seen_video_ids.add(video_id)

                    author = data.get("author") or {}
                    actual_username = author.get("uniqueId") or un
                    vstats = data.get("stats") or {}
                    music = data.get("music") or {}

                    all_videos.append(
                        {
                            "video_id": video_id,
                            "username": actual_username,
                            "url": f"https://www.tiktok.com/@{actual_username}/video/{video_id}",
                            "plays": int(vstats.get("playCount") or 0),
                            "likes": int(vstats.get("diggCount") or 0),
                            "comments": int(vstats.get("commentCount") or 0),
                            "created_at": created.isoformat(),
                            "music_title": music.get("title") or "",
                            "music_author": music.get("authorName") or "",
                            "caption": (data.get("desc") or "")[:120],
                        }
                    )
                    count += 1
            except KeyError as exc:
                # Biasanya 'id' atau 'author' — TikTok return userInfo kosong (bot-detect)
                user_error = f"rate-limited / bot-detect (response kosong: KeyError {exc})"
            except Exception as exc:
                exc_name = type(exc).__name__
                if "Empty" in exc_name:
                    user_error = "rate-limited / bot-detect (empty response)"
                else:
                    user_error = f"{exc_name}: {exc}"

            if user_error:
                errored.append(un)
                consecutive_errors += 1
                console.print(f"  [red]Error: {user_error}[/red]")
                if consecutive_errors >= ABORT_AFTER_CONSECUTIVE_ERRORS:
                    remaining = len(usernames) - idx - 1
                    console.print()
                    console.print(
                        f"[bold red]✋ Abort: {ABORT_AFTER_CONSECUTIVE_ERRORS} user beruntun error.[/bold red]"
                    )
                    console.print(
                        f"[red]Kemungkinan besar token sudah ke-rate-limit. {remaining} user sisanya di-skip.[/red]"
                    )
                    console.print(
                        "[yellow]Tunggu 10-30 menit lalu coba lagi, atau refresh MS_TOKEN.[/yellow]"
                    )
                    aborted = True
                    break
                continue

            consecutive_errors = 0
            if count == 0:
                silent.append(un)
                console.print(f"  [dim]→ silent (gak posting dalam {days_back} hari)[/dim]")
            else:
                console.print(f"  [green]→ {count} video[/green]")

        if aborted:
            # Tandai user yg belum sempat di-scrape sebagai "skipped" — tambahin ke errored
            scraped_total = idx + 1
            for skipped in usernames[scraped_total:]:
                errored.append(skipped)

    return all_videos, silent, errored


def _pick_top_with_user_cap(
    videos: list[dict], top_n: int, max_per_user: int
) -> list[dict]:
    """Iterasi videos urut, ambil sampai top_n, tapi cap max_per_user post per username."""
    result: list[dict] = []
    user_count: dict[str, int] = defaultdict(int)
    for v in videos:
        un = v.get("username", "")
        if user_count[un] >= max_per_user:
            continue
        result.append(v)
        user_count[un] += 1
        if len(result) >= top_n:
            break
    return result


def render_videos(
    videos: list[dict],
    silent: list[str],
    errored: list[str],
    total_tracked: int,
    top_n: int,
    days_back: int,
    sort_key: str,
) -> None:
    sort_field, sort_label = SORT_OPTIONS[sort_key]
    video_sort_field = {"total_plays": "plays", "total_likes": "likes", "total_comments": "comments"}[sort_field]

    sorted_videos = sorted(videos, key=lambda v: v.get(video_sort_field, 0) or 0, reverse=True)
    top_videos = _pick_top_with_user_cap(sorted_videos, top_n, MAX_POSTS_PER_USER_IN_TOP)

    posters = total_tracked - len(silent) - len(errored)

    console.print()
    console.rule(
        f"[bold magenta]Following digest — {days_back} HARI TERAKHIR • sort by {sort_label}"
    )
    console.print(
        f"[bold]📊 {total_tracked}[/bold] user di-track  •  "
        f"[green]{posters}[/green] posting  •  "
        f"[yellow]{len(silent)}[/yellow] silent  •  "
        f"[red]{len(errored)}[/red] error"
    )

    if not top_videos:
        console.print()
        console.print("[red]Tidak ada video dalam window. Semua user silent.[/red]")
    else:
        console.print()
        console.rule(f"[bold]TOP {len(top_videos)} POSTERS (max {MAX_POSTS_PER_USER_IN_TOP} per user)")

        table = Table(show_header=True, header_style="bold cyan", expand=False, box=TABLE_BOX)
        table.add_column("#", justify="right", no_wrap=True)
        table.add_column("Username", style="bold", no_wrap=True)
        table.add_column("Views", justify="right", no_wrap=True)
        table.add_column("Likes", justify="right", no_wrap=True)
        table.add_column("Komentar", justify="right", no_wrap=True)
        table.add_column("Lagu", max_width=28, overflow="ellipsis")
        table.add_column("Link", no_wrap=True)

        for idx, v in enumerate(top_videos, 1):
            link_cell = f"[link={v['url']}]▶ buka video[/link]"
            music_label = (v.get("music_title") or "-")[:28]
            table.add_row(
                str(idx),
                f"@{v['username']}",
                f"{v.get('plays', 0):,}",
                f"{v.get('likes', 0):,}",
                f"{v.get('comments', 0):,}",
                music_label,
                link_cell,
            )
        console.print(table)

    if silent:
        console.print()
        console.rule(f"[bold yellow]{len(silent)} SILENT (gak posting dalam {days_back} hari)")
        preview = silent[:SILENT_PREVIEW_COUNT]
        console.print("  " + ", ".join(f"@{u}" for u in preview))
        if len(silent) > SILENT_PREVIEW_COUNT:
            console.print(
                f"  [dim]... dan {len(silent) - SILENT_PREVIEW_COUNT} lainnya (lengkap di JSON output)[/dim]"
            )

    if errored:
        console.print()
        console.rule(f"[bold red]{len(errored)} ERROR (rate-limited / skip)")
        preview = errored[:SILENT_PREVIEW_COUNT]
        console.print("  " + ", ".join(f"@{u}" for u in preview))
        if len(errored) > SILENT_PREVIEW_COUNT:
            console.print(
                f"  [dim]... dan {len(errored) - SILENT_PREVIEW_COUNT} lainnya (lengkap di JSON output)[/dim]"
            )

    out_path = "trending_following_output.json"
    payload = {
        "days_back": days_back,
        "sort_by": sort_label,
        "total_tracked": total_tracked,
        "posters_count": posters,
        "silent_count": len(silent),
        "silent_users": silent,
        "errored_count": len(errored),
        "errored_users": errored,
        "top_videos": top_videos,
        "all_videos_sorted": sorted_videos,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    console.print()
    console.print(f"[green]✓ Hasil lengkap disimpan ke {out_path}[/green]")


async def main() -> None:
    token = os.environ.get("MS_TOKEN") or read_env_value("MS_TOKEN")
    if not token:
        token = prompt_ms_token()

    mode = prompt_mode()

    if mode == "1":
        hashtags, days_back, top_n, sort_key = prompt_hashtag_options()

        console.print()
        music_stats = await collect(token, hashtags, days_back)

        if not music_stats:
            console.print()
            console.print("[bold red]Tidak ada data dari TikTok — token kemungkinan expired atau diblokir.[/bold red]")
            retry = input("Mau input token baru dan coba lagi? [Y/n]: ").strip().lower()
            if retry in ("", "y", "yes"):
                token = prompt_ms_token()
                console.print()
                music_stats = await collect(token, hashtags, days_back)

        if not music_stats:
            console.print("[red]Tetap kosong. Coba refresh cookie di browser, atau ganti hashtag.[/red]")
            sys.exit(2)

        render(music_stats, top_n, days_back, sort_key)
        return

    usernames = load_username_list()
    if not usernames:
        sys.exit(2)

    console.print()
    console.print(
        f"[bold]Akan scrape {len(usernames)} user:[/bold] "
        + ", ".join(f"@{u}" for u in usernames)
    )

    days_back, top_n, sort_key = prompt_count_and_sort("video")

    console.print()
    videos, silent, errored = await collect_following(token, usernames, days_back)

    render_videos(videos, silent, errored, len(usernames), top_n, days_back, sort_key)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Dibatalkan.[/yellow]")
        sys.exit(130)
