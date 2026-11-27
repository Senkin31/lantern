#!/usr/bin/env python3
"""
Lantern: сбор кадров с дорожных камер Fintraffic (Финляндия).

Что делает:
  1. При старте скачивает историю за последние 24 часа по каждой камере.
  2. Дальше раз в N минут (по умолчанию 10) забирает текущий кадр.
     Если кадр не обновился, сервер отвечает 304 и ничего не сохраняется.
  3. Каждый кадр пишется в data/fintraffic/<PRESET>/<UTC-время>.jpg,
     а строка о нём - в data/fintraffic/manifest.csv.

Только стандартная библиотека Python 3.8+, ничего ставить не нужно.

Запуск (из корня репозитория):
  python tools/collect_fintraffic.py                  # камеры по умолчанию, раз в 10 минут
  python tools/collect_fintraffic.py --once           # один проход и выход (проверка)
  python tools/collect_fintraffic.py --presets C1254701 C0462200
  python tools/collect_fintraffic.py --list Tampere   # найти камеры по названию

Данные: Fintraffic / digitraffic.fi, лицензия CC BY 4.0
(https://creativecommons.org/licenses/by/4.0/). Указывать источник в README и на слайдах.
"""

import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import signal
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# Адреса можно переопределить переменными окружения (нужно только для тестов).
API_BASE = os.environ.get("LANTERN_FT_API", "https://tie.digitraffic.fi/api/weathercam/v1")
IMG_BASE = os.environ.get("LANTERN_FT_IMG", "https://weathercam.digitraffic.fi")

# Сервис просит представляться этим заголовком; без него быстрее упираешься в лимит.
USER_HEADER = {
    "Digitraffic-User": "Lantern/RobotHack2026",
    "User-Agent": "Lantern/RobotHack2026",
    # API Digitraffic отвечает 406 без этого заголовка
    "Accept-Encoding": "gzip",
}

# Камеры, отобранные 24.11.2026 (тротуар, переход или обочина в кадре).
DEFAULT_PRESETS = {
    "C1254701": "Kajaani, Tie 6 - path with snow ridge",
    "C0462200": "Lahti, Uudenmaankatu - city street",
    "C0952003": "Jyvaskyla, Palokka - street with sidewalk",
    "C1052301": "Vaasa, Kotiranta - street with sidewalk",
    "C0454801": "Tampere, Lielahti - intersection",
    "C0454802": "Tampere, Lielahti - side path",
    "C1257002": "Oulu, Limingantie - intersection",
    "C1259401": "Oulu, Kaukovainio - intersection",
}

PAUSE_BETWEEN_REQUESTS = 2.0   # секунд между запросами, чтобы не словить 429
BACKOFF_ON_429 = 180           # если сервер просит притормозить, а Retry-After нет

_stop = False


def _on_signal(signum, frame):
    global _stop
    _stop = True
    log("Получен сигнал остановки, заканчиваю текущий проход...")


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def http_get(url, headers=None, timeout=30):
    """GET с ретраем на 429. Возвращает (status, headers, body) или (None, None, None)."""
    h = dict(USER_HEADER)
    if headers:
        h.update(headers)
    for attempt in range(3):
        req = urllib.request.Request(url, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
                if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                    body = gzip.decompress(body)
                return r.status, dict(r.headers), body
        except urllib.error.HTTPError as e:
            if e.code == 304:
                return 304, dict(e.headers), b""
            if e.code == 429:
                wait = int(e.headers.get("Retry-After") or BACKOFF_ON_429)
                log(f"429 (слишком много запросов), жду {wait} с")
                _sleep(wait)
                continue
            log(f"HTTP {e.code} для {url}")
            return e.code, dict(e.headers), b""
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            log(f"Сеть: {e} ({url}), попытка {attempt + 1}/3")
            _sleep(10 * (attempt + 1))
    return None, None, None


def _sleep(seconds):
    end = time.time() + seconds
    while not _stop and time.time() < end:
        time.sleep(min(1.0, end - time.time()))


def utc_stamp(dt):
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def stamp_from_headers(headers):
    lm = (headers or {}).get("Last-Modified")
    if lm:
        try:
            return utc_stamp(parsedate_to_datetime(lm))
        except (TypeError, ValueError):
            pass
    return utc_stamp(datetime.now(timezone.utc))


class Store:
    """Сохранение кадров и manifest.csv, без дублей (по хэшу содержимого внутри одной камеры)."""

    def __init__(self, out_dir):
        self.out = out_dir
        os.makedirs(out_dir, exist_ok=True)
        self.manifest = os.path.join(out_dir, "manifest.csv")
        self.seen = set()
        if os.path.exists(self.manifest):
            with open(self.manifest, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    self.seen.add((row["preset"], row["sha1"]))
        else:
            with open(self.manifest, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(["preset", "time_utc", "file", "source", "bytes", "sha1"])

    def save(self, preset, stamp, data, source):
        if not data or data[:2] != b"\xff\xd8":   # не JPEG - пропускаем
            return False
        sha = hashlib.sha1(data).hexdigest()
        if (preset, sha) in self.seen:
            return False
        folder = os.path.join(self.out, preset)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{stamp}.jpg")
        if os.path.exists(path):
            path = os.path.join(folder, f"{stamp}_{sha[:6]}.jpg")
        with open(path, "wb") as f:
            f.write(data)
        with open(self.manifest, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([preset, stamp, os.path.relpath(path, self.out), source, len(data), sha])
        self.seen.add((preset, sha))
        return True


def _walk_history(obj, found):
    """Ищет в ответе API ссылки на кадры и время рядом с ними (формат ответа не фиксируем)."""
    if isinstance(obj, dict):
        url = None
        for v in obj.values():
            if isinstance(v, str) and re.search(r"\.jpe?g(\?|$)", v):
                url = v
                break
        if url:
            when = None
            for k, v in obj.items():
                if isinstance(v, str) and re.search(r"time|modified|date", k, re.I):
                    when = v
                    break
            found.append((url, when))
        for v in obj.values():
            _walk_history(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _walk_history(v, found)


def history_items(preset):
    status, _, body = http_get(f"{API_BASE}/stations/{preset}/history", {"Accept": "application/json"})
    if status != 200 or not body:
        return []
    try:
        data = json.loads(body.decode("utf-8"))
    except ValueError:
        return []
    found = []
    _walk_history(data, found)
    # оставляем только ссылки этого ракурса и убираем повторы
    seen, items = set(), []
    for url, when in found:
        if preset in url and url not in seen:
            seen.add(url)
            items.append((url, when))
    return items


def fetch_history(store, presets):
    for preset in presets:
        if _stop:
            return
        items = history_items(preset)
        saved = 0
        log(f"{preset}: в истории {len(items)} кадров, скачиваю (~{len(items) * 2 // 60 + 1} мин)...")
        for i, (url, when) in enumerate(items, 1):
            if _stop:
                return
            if i % 20 == 0:
                log(f"{preset}: история {i}/{len(items)}, сохранено {saved}")
            status, headers, body = http_get(url)
            if status == 200:
                stamp = stamp_from_headers(headers)
                if when:
                    try:
                        stamp = utc_stamp(datetime.fromisoformat(when.replace("Z", "+00:00")))
                    except ValueError:
                        pass
                if store.save(preset, stamp, body, "history"):
                    saved += 1
            time.sleep(PAUSE_BETWEEN_REQUESTS)
        log(f"{preset}: история за сутки - найдено {len(items)}, сохранено {saved}")


def fetch_current(store, presets, etags):
    saved = 0
    for preset in presets:
        if _stop:
            break
        headers = {"If-None-Match": etags[preset]} if etags.get(preset) else None
        status, rh, body = http_get(f"{IMG_BASE}/{preset}.jpg", headers=headers)
        if status == 200:
            if rh and rh.get("ETag"):
                etags[preset] = rh["ETag"]
            if store.save(preset, stamp_from_headers(rh), body, "live"):
                saved += 1
        time.sleep(PAUSE_BETWEEN_REQUESTS)
    return saved


def list_stations(pattern):
    status, _, body = http_get(f"{API_BASE}/stations", {"Accept": "application/json"})
    if status != 200:
        log("Не удалось получить список камер")
        return
    feats = json.loads(body.decode("utf-8")).get("features", [])
    rx = re.compile(pattern, re.I)
    n = 0
    for f in feats:
        p = f.get("properties", {})
        if not rx.search(p.get("name", "")):
            continue
        presets = [q["id"] for q in p.get("presets", []) if q.get("inCollection")]
        print(f"{p.get('id')}  {p.get('name')}  presets: {' '.join(presets)}")
        print(f"   пример: {IMG_BASE}/{presets[0]}.jpg" if presets else "   (нет активных ракурсов)")
        n += 1
    print(f"Найдено станций: {n}")


def main():
    ap = argparse.ArgumentParser(description="Сбор кадров с камер Fintraffic для Lantern")
    ap.add_argument("--presets", nargs="+", help="ID ракурсов (например C1254701). По умолчанию - отобранные камеры")
    ap.add_argument("--interval", type=int, default=10, help="интервал в минутах (по умолчанию 10)")
    ap.add_argument("--out", default=os.path.join("data", "fintraffic"), help="папка для кадров")
    ap.add_argument("--no-history", action="store_true", help="не скачивать историю за сутки при старте")
    ap.add_argument("--once", action="store_true", help="один проход и выход")
    ap.add_argument("--list", metavar="ТЕКСТ", help="показать камеры, в названии которых есть ТЕКСТ, и выйти")
    args = ap.parse_args()

    if args.list:
        list_stations(args.list)
        return

    presets = args.presets or list(DEFAULT_PRESETS)
    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    store = Store(args.out)
    log(f"Камер: {len(presets)}, интервал: {args.interval} мин, папка: {os.path.abspath(args.out)}")
    for p in presets:
        log(f"  {p}  {DEFAULT_PRESETS.get(p, '')}")

    if not args.no_history:
        log("Скачиваю историю за последние 24 часа...")
        fetch_history(store, presets)

    etags = {}
    while not _stop:
        n = fetch_current(store, presets, etags)
        log(f"Проход завершён: новых кадров {n}, всего в базе {len(store.seen)}")
        if args.once:
            break
        _sleep(args.interval * 60)
    log("Остановлено. Кадры и manifest.csv - в папке " + os.path.abspath(args.out))


if __name__ == "__main__":
    sys.exit(main())
