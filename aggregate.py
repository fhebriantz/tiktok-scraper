"""Aggregate batch_results.json → ranking user dari views terbaik ke terendah."""

import json
import sys
from collections import defaultdict
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    try:
        import ctypes

        _kernel32 = ctypes.windll.kernel32
        for _handle_id in (-11, -12):
            _handle = _kernel32.GetStdHandle(_handle_id)
            _mode = ctypes.c_uint32()
            if _kernel32.GetConsoleMode(_handle, ctypes.byref(_mode)):
                _kernel32.SetConsoleMode(_handle, _mode.value | 0x0004)
    except Exception:
        pass

from rich import box
from rich.console import Console
from rich.table import Table

console = Console(legacy_windows=False)
TABLE_BOX = box.ASCII if sys.platform == "win32" else box.HEAVY_HEAD


def main():
    data = json.loads(Path("batch_results.json").read_text(encoding="utf-8"))

    all_videos = []
    silent_all = set()
    errored_all = set()
    all_input_usernames = set()

    for batch in data["batches"]:
        all_videos.extend(batch["videos"])
        silent_all.update(batch["silent"])
        errored_all.update(batch["errored"])
        all_input_usernames.update(batch.get("usernames_input", []))

    # Dedup: kalau user pernah errored tapi kemudian sukses (posting / silent) di batch lain,
    # status final-nya adalah yang sukses — bukan errored.
    posters_set = {v["username"] for v in all_videos}
    silent_all -= posters_set
    errored_all -= posters_set
    errored_all -= silent_all

    # Group video per user
    user_videos: dict[str, list[dict]] = defaultdict(list)
    for v in all_videos:
        user_videos[v["username"]].append(v)

    # Untuk tiap user: hitung best_views, total_views, total_likes, total_comments, video_count, best_url
    user_stats = []
    for un, vids in user_videos.items():
        vids_sorted = sorted(vids, key=lambda v: v.get("plays", 0), reverse=True)
        best = vids_sorted[0]
        user_stats.append({
            "username": un,
            "video_count": len(vids),
            "best_views": best.get("plays", 0),
            "best_likes": best.get("likes", 0),
            "best_comments": best.get("comments", 0),
            "best_url": best.get("url"),
            "best_caption": (best.get("caption") or "")[:60],
            "total_views": sum(v.get("plays", 0) for v in vids),
            "total_likes": sum(v.get("likes", 0) for v in vids),
        })

    # Sort by best_views desc
    user_stats.sort(key=lambda u: u["best_views"], reverse=True)

    # ===== Ranking table =====
    console.rule("[bold magenta]RANKING USER — Best Video Views (descending)")
    console.print(
        f"[bold]Total: {len(user_stats)} posting[/bold] • "
        f"[yellow]{len(silent_all)} silent[/yellow] • "
        f"[red]{len(errored_all)} error[/red]"
    )
    console.print()

    table = Table(show_header=True, header_style="bold cyan", expand=False, box=TABLE_BOX)
    table.add_column("#", justify="right", no_wrap=True, min_width=3)
    table.add_column("Username", style="bold", no_wrap=True, min_width=22)
    table.add_column("Best views", justify="right", no_wrap=True, min_width=11)
    table.add_column("Best likes", justify="right", no_wrap=True, min_width=10)
    table.add_column("Best komen", justify="right", no_wrap=True, min_width=10)
    table.add_column("Σ views", justify="right", no_wrap=True, min_width=11)
    table.add_column("Vid", justify="right", no_wrap=True, min_width=3)
    table.add_column("Best video", no_wrap=True)

    for idx, u in enumerate(user_stats, 1):
        link = f"[link={u['best_url']}]▶ buka[/link]"
        table.add_row(
            str(idx),
            f"@{u['username']}",
            f"{u['best_views']:,}",
            f"{u['best_likes']:,}",
            f"{u['best_comments']:,}",
            f"{u['total_views']:,}",
            str(u["video_count"]),
            link,
        )
    console.print(table)

    # Silent + error info
    if silent_all:
        console.print()
        console.print(f"[yellow]Silent ({len(silent_all)}):[/yellow] " + ", ".join(f"@{u}" for u in sorted(silent_all)))
    if errored_all:
        console.print()
        console.print(f"[red]Errored ({len(errored_all)}):[/red] " + ", ".join(f"@{u}" for u in sorted(errored_all)))

    # Save aggregated
    out = {
        "summary": {
            "total_posters": len(user_stats),
            "total_silent": len(silent_all),
            "total_errored": len(errored_all),
            "silent_users": sorted(silent_all),
            "errored_users": sorted(errored_all),
        },
        "ranking": user_stats,
    }
    Path("ranking_output.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print()
    console.print("[green]✓ Hasil ranking disimpan ke ranking_output.json[/green]")

    # Sort username_list.txt: posting (rank desc) → silent → errored (di bottom)
    username_list_path = Path("username_list.txt")
    if username_list_path.exists():
        ranked_users = [u["username"] for u in user_stats]
        sorted_silent = sorted(silent_all)
        sorted_errored = sorted(errored_all)
        ordered = ranked_users + sorted_silent + sorted_errored
        username_list_path.write_text("\n".join(ordered) + "\n", encoding="utf-8")
        console.print(
            f"[green]✓ {username_list_path} di-sort: "
            f"{len(ranked_users)} posting (rank) → {len(sorted_silent)} silent → "
            f"{len(sorted_errored)} errored[/green]"
        )

    # ===== Export link ke output_link.txt =====
    # Tabel di atas = 1 row per user (best video per user), urut by best_views.
    # output_link.txt mengikuti urutan & jumlah yang persis sama dengan tabel.
    links = [u.get("best_url") for u in user_stats if u.get("best_url")]
    if links:
        Path("output_link.txt").write_text("\n".join(links) + "\n", encoding="utf-8")
        console.print()
        console.print(
            f"[green]✓ {len(links)} link disimpan ke output_link.txt "
            f"(sama dengan tabel di atas)[/green]"
        )


if __name__ == "__main__":
    main()
